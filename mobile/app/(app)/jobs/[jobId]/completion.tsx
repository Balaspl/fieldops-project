
import { useCallback, useEffect, useRef, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  deleteOfflineRecord,
  getOfflineRecord,
  setOfflineRecord
} from "../../../../src/offline/offlineStore";
import {
  ActivityIndicator,
  Image,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View
} from "react-native";
import {
  CameraView,
  useCameraPermissions
} from "expo-camera";
import SignatureCanvas from "react-native-signature-canvas";
import {
  copyAsync,
  deleteAsync,
  documentDirectory,
  getInfoAsync,
  makeDirectoryAsync
} from "expo-file-system/legacy";
import { useLocalSearchParams, useRouter } from "expo-router";

import {
  apiClient,
  isNetworkUnavailableError
} from "../../../../src/api/client";
import { useAuthStore } from "../../../../src/auth/authStore";
import { getApiErrorMessage } from "../../../../src/api/apiError";
import {
  deleteCompletionPhoto,
  uploadCompletionPhoto,
  type CompletionDocument,
  type CompletionPhotoAsset,
  type CompletionPhotoCategory
} from "../../../../src/api/completionDocuments";

import { clearActiveGpsJob } from "../../../../src/gps/backgroundLocationService";
import {
  logError,
  logEvent
} from "../../../../src/observability/logger";

const MAX_PHOTO_SIZE_BYTES = 10 * 1024 * 1024;

interface PhotoDraft {
  localId: string;
  asset: CompletionPhotoAsset;
  category: CompletionPhotoCategory;
  document?: CompletionDocument;
  uploadError?: string;
}

interface CompletionDraft {
  version: 1;
  tenantId: string;
  technicianId: string;
  jobId: string;
  savedAt: string;
  serviceChargeText: string;
  materialCostText: string;
  notes: string;
  partsUsedText: string;
  durationMinutes: string;
  isCostStep: boolean;
  photos: PhotoDraft[];
}

type CompletionDraftOverrides = Partial<
  Pick<
    CompletionDraft,
    | "serviceChargeText"
    | "materialCostText"
    | "notes"
    | "partsUsedText"
    | "durationMinutes"
    | "isCostStep"
    | "photos"
  >
>;

function safeStorageSegment(value: string): string {
  return encodeURIComponent(value).replace(/%/g, "_");
}

function getCompletionDraftKey(
  tenantId: string,
  technicianId: string,
  jobId: string
): string {
  return [
    "fieldops:completion-draft:v1",
    safeStorageSegment(tenantId),
    safeStorageSegment(technicianId),
    safeStorageSegment(jobId)
  ].join(":");
}

function getCompletionDraftPhotoDirectory(
  tenantId: string,
  technicianId: string,
  jobId: string
): string | null {
  if (!documentDirectory) {
    return null;
  }

  return `${documentDirectory}fieldops-completion-drafts/${safeStorageSegment(
    tenantId
  )}/${safeStorageSegment(technicianId)}/${safeStorageSegment(jobId)}/`;
}

function isPhotoDraft(value: unknown): value is PhotoDraft {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const photo = value as {
    localId?: unknown;
    asset?: unknown;
    category?: unknown;
    document?: unknown;
    uploadError?: unknown;
  };
  const asset = photo.asset as {
    uri?: unknown;
    fileName?: unknown;
    contentType?: unknown;
    sizeBytes?: unknown;
  } | null | undefined;

  return (
    typeof photo.localId === "string" &&
    typeof asset === "object" &&
    asset !== null &&
    typeof asset.uri === "string" &&
    typeof asset.fileName === "string" &&
    typeof asset.contentType === "string" &&
    typeof asset.sizeBytes === "number" &&
    (photo.category === "BEFORE" || photo.category === "AFTER") &&
    (photo.document === undefined ||
      (typeof photo.document === "object" && photo.document !== null)) &&
    (photo.uploadError === undefined ||
      typeof photo.uploadError === "string")
  );
}

function isCompletionDraft(
  value: unknown,
  tenantId: string,
  technicianId: string,
  jobId: string
): value is CompletionDraft {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const draft = value as Partial<CompletionDraft>;

  return (
    draft.version === 1 &&
    draft.tenantId === tenantId &&
    draft.technicianId === technicianId &&
    draft.jobId === jobId &&
    typeof draft.savedAt === "string" &&
    typeof draft.serviceChargeText === "string" &&
    typeof draft.materialCostText === "string" &&
    typeof draft.notes === "string" &&
    typeof draft.partsUsedText === "string" &&
    typeof draft.durationMinutes === "string" &&
    typeof draft.isCostStep === "boolean" &&
    Array.isArray(draft.photos) &&
    draft.photos.every(isPhotoDraft)
  );
}

async function isPhotoFileAvailable(uri: string): Promise<boolean> {
  try {
    const fileInfo = await getInfoAsync(uri);
    return fileInfo.exists;
  } catch {
    return false;
  }
}

async function persistCapturedPhoto(
  sourceUri: string,
  directoryUri: string,
  localId: string
): Promise<string> {
  await makeDirectoryAsync(directoryUri, { intermediates: true });

  const destinationUri = `${directoryUri}${safeStorageSegment(localId)}.jpg`;
  await copyAsync({ from: sourceUri, to: destinationUri });

  const fileInfo = await getInfoAsync(destinationUri);

  if (
    !fileInfo.exists ||
    typeof fileInfo.size !== "number" ||
    fileInfo.size <= 0
  ) {
    await deleteAsync(destinationUri, { idempotent: true }).catch(() => undefined);
    throw new Error(
      "The captured photo could not be saved for offline use. Please capture it again."
    );
  }

  return destinationUri;
}

async function deleteManagedDraftPhoto(uri: string): Promise<void> {
  if (!documentDirectory) {
    return;
  }

  const managedDirectory = `${documentDirectory}fieldops-completion-drafts/`;

  if (!uri.startsWith(managedDirectory)) {
    return;
  }

  try {
    await deleteAsync(uri, { idempotent: true });
  } catch {
    // A local-file cleanup failure must not undo a confirmed server action.
  }
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }

  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function parseMoneyParam(
  value: string | string[] | undefined
): number | null {
  const raw = (
    Array.isArray(value) ? value[0] : value
  )?.trim();

  // Preserve compatibility with completion routes that
  // do not provide cost parameters.
  if (raw === undefined || raw === "") {
    return 0;
  }

  if (!/^\d+(?:\.\d{1,2})?$/.test(raw)) {
    return null;
  }

  const amount = Number(raw);
  const paise = Math.round(amount * 100);

  if (
    !Number.isFinite(amount) ||
    !Number.isSafeInteger(paise) ||
    paise < 0
  ) {
    return null;
  }

  return paise / 100;
}

export default function JobCompletionScreen() {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const tenantId = user?.tenant_id == null
    ? null
    : String(user.tenant_id).trim();
  const technicianId = user?.id == null
    ? null
    : String(user.id).trim();
  const params = useLocalSearchParams<{
    jobId?: string | string[];
    serviceCharge?: string | string[];
    materialCost?: string | string[];
  }>();

  const jobId = Array.isArray(params.jobId)
      ? params.jobId[0]
      : params.jobId;

  const [isCostStep, setIsCostStep] = useState(false);

  const [serviceChargeText, setServiceChargeText] = useState(() => {
    const value = Array.isArray(params.serviceCharge)
      ? params.serviceCharge[0]
      : params.serviceCharge;

    return value ?? "";
  });

  const [materialCostText, setMaterialCostText] = useState(() => {
    const value = Array.isArray(params.materialCost)
      ? params.materialCost[0]
      : params.materialCost;

    return value ?? "";
  });

  const serviceCharge = parseMoneyParam(serviceChargeText);
  const materialCost = parseMoneyParam(materialCostText);

  const serviceChargePaise = Math.round(
    (serviceCharge ?? 0) * 100
  );

  const materialCostPaise = Math.round(
    (materialCost ?? 0) * 100
  );

  const subtotalPaise =
    serviceChargePaise + materialCostPaise;

  const gstPaise = Math.round(
    (subtotalPaise * 5) / 100
  );

  const totalPaise = subtotalPaise + gstPaise;

  function formatINR(paise: number): string {
    return (paise / 100).toLocaleString("en-IN", {
      style: "currency",
      currency: "INR",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
  }
  const cameraRef = useRef<CameraView | null>(null);

  const [permission, requestCameraPermission] =
    useCameraPermissions();

  const [notes, setNotes] = useState("");
  const [partsUsedText, setPartsUsedText] = useState("");
  const [durationMinutes, setDurationMinutes] = useState("");
  const [photos, setPhotos] = useState<PhotoDraft[]>([]);
  const [photoCategory, setPhotoCategory] =
    useState<CompletionPhotoCategory>("AFTER");

  const [isCameraVisible, setIsCameraVisible] = useState(false);
  const [isCameraReady, setIsCameraReady] = useState(false);
  const [isCapturing, setIsCapturing] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [isSignatureStep, setIsSignatureStep] = useState(false);
  const [signatureData, setSignatureData] = useState("");
  const [isSavingSignature, setIsSavingSignature] = useState(false);

  const [uploadingPhotoId, setUploadingPhotoId] =
    useState<string | null>(null);
  const [removingPhotoId, setRemovingPhotoId] =
    useState<string | null>(null);

  const [cameraError, setCameraError] =
    useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDraftReady, setIsDraftReady] = useState(false);
  const [draftWasRestored, setDraftWasRestored] = useState(false);
  const [draftWarning, setDraftWarning] = useState<string | null>(null);
  const [draftSaveStatus, setDraftSaveStatus] = useState<
    "saving" | "saved" | "error" | null
  >(null);
  const completionConfirmedRef = useRef(false);
  const draftWritePromiseRef = useRef<Promise<void>>(Promise.resolve());

  const draftKey =
    tenantId && tenantId.length > 0 &&
    technicianId && technicianId.length > 0 &&
    jobId && jobId.length > 0
      ? getCompletionDraftKey(tenantId, technicianId, jobId)
      : null;

  const draftPhotoDirectory =
    tenantId && tenantId.length > 0 &&
    technicianId && technicianId.length > 0 &&
    jobId && jobId.length > 0
      ? getCompletionDraftPhotoDirectory(tenantId, technicianId, jobId)
      : null;

  useEffect(() => {
    let cancelled = false;
    let canWriteDraft = true;

    setIsDraftReady(false);
    setDraftWasRestored(false);
    setDraftWarning(null);
    setDraftSaveStatus(null);

    if (!draftKey || !tenantId || !technicianId || !jobId) {
      setIsDraftReady(true);
      return () => {
        cancelled = true;
      };
    }

    // Capture the validated values so TypeScript retains their non-null types
    // inside the nested asynchronous restore function.
    const validDraftKey = draftKey;
    const validTenantId = tenantId;
    const validTechnicianId = technicianId;
    const validJobId = jobId;

    async function restoreDraft() {
      try {
        const draftScope = {
          tenantId: validTenantId,
          technicianId: validTechnicianId
        };

        let parsed = await getOfflineRecord<unknown>(
          draftScope,
          "completion-draft",
          validJobId
        );

        if (parsed === null) {
          const savedDraft = await AsyncStorage.getItem(validDraftKey);

          if (!savedDraft) {
            return;
          }

          const legacyDraft: unknown = JSON.parse(savedDraft);

          if (
            !isCompletionDraft(
              legacyDraft,
              validTenantId,
              validTechnicianId,
              validJobId
            )
          ) {
            await AsyncStorage.removeItem(validDraftKey);
            return;
          }

          // Preserve the old draft if encrypted migration fails.
          await setOfflineRecord(
            draftScope,
            "completion-draft",
            validJobId,
            legacyDraft
          );

          parsed = legacyDraft;

          await AsyncStorage.removeItem(validDraftKey).catch(
            () => undefined
          );
        } else {
          // Encrypted copy exists; remove the old plaintext copy.
          await AsyncStorage.removeItem(validDraftKey).catch(
            () => undefined
          );
        }

        if (
          !isCompletionDraft(
            parsed,
            validTenantId,
            validTechnicianId,
            validJobId
          )
        ) {
          await deleteOfflineRecord(
            draftScope,
            "completion-draft",
            validJobId
          );
          return;
        }

        const availablePhotos: PhotoDraft[] = [];
        let missingLocalPhotos = 0;

        for (const photo of parsed.photos) {
          const fileAvailable = await isPhotoFileAvailable(photo.asset.uri);

          if (fileAvailable || photo.document) {
            availablePhotos.push(photo);
          } else {
            missingLocalPhotos += 1;
          }
        }

        if (cancelled) {
          return;
        }

        setServiceChargeText(parsed.serviceChargeText);
        setMaterialCostText(parsed.materialCostText);
        setNotes(parsed.notes);
        setPartsUsedText(parsed.partsUsedText);
        setDurationMinutes(parsed.durationMinutes);
        setPhotos(availablePhotos);
        setIsCostStep(parsed.isCostStep);

        // Customer signatures are deliberately not stored in the local draft.
        // After reopening the screen, the customer must sign again.
        setSignatureData("");
        setIsSignatureStep(false);
        setDraftWasRestored(true);
        setDraftSaveStatus("saved");

        if (missingLocalPhotos > 0) {
          setDraftWarning(
            `${missingLocalPhotos} local photo${missingLocalPhotos === 1 ? " was" : "s were"} unavailable after reopening and ${missingLocalPhotos === 1 ? "has" : "have"} been excluded. Capture replacement evidence before completing the job.`
          );
        }
      } catch (restoreError: unknown) {
        canWriteDraft = false;
        setDraftWarning(
          "The saved draft could not be restored. Your existing local draft was left untouched."
        );
        logError("completion.draft_restore_failed", restoreError);
      } finally {
        if (!cancelled && canWriteDraft) {
          setIsDraftReady(true);
        }
      }
    }

    void restoreDraft();

    return () => {
      cancelled = true;
    };
  }, [draftKey, tenantId, technicianId, jobId]);

  const persistDraft = useCallback(
    async (overrides: CompletionDraftOverrides = {}) => {
      if (
        completionConfirmedRef.current ||
        !isDraftReady ||
        !draftKey ||
        !tenantId ||
        !technicianId ||
        !jobId
      ) {
        return;
      }

      const draft: CompletionDraft = {
        version: 1,
        tenantId,
        technicianId,
        jobId,
        savedAt: new Date().toISOString(),
        serviceChargeText:
          overrides.serviceChargeText ?? serviceChargeText,
        materialCostText:
          overrides.materialCostText ?? materialCostText,
        notes: overrides.notes ?? notes,
        partsUsedText: overrides.partsUsedText ?? partsUsedText,
        durationMinutes: overrides.durationMinutes ?? durationMinutes,
        isCostStep: overrides.isCostStep ?? isCostStep,
        photos: overrides.photos ?? photos
      };

      setDraftSaveStatus("saving");

      let saveSucceeded = false;
      const writePromise = draftWritePromiseRef.current.then(async () => {
        if (completionConfirmedRef.current) {
          return;
        }

        await setOfflineRecord(
          { tenantId, technicianId },
          "completion-draft",
          jobId,
          draft
        );
      });

      const queuedWrite = writePromise.then(
        () => {
          saveSucceeded = true;
        },
        (storageError: unknown) => {
          setDraftSaveStatus("error");
          logError("completion.draft_save_failed", storageError);
        }
      );

      draftWritePromiseRef.current = queuedWrite;
      await queuedWrite;

      if (saveSucceeded && !completionConfirmedRef.current) {
        setDraftSaveStatus("saved");
      }
    },
    [
      isDraftReady,
      draftKey,
      tenantId,
      technicianId,
      jobId,
      serviceChargeText,
      materialCostText,
      notes,
      partsUsedText,
      durationMinutes,
      isCostStep,
      photos
    ]
  );

  useEffect(() => {
    if (!isDraftReady || !draftKey) {
      return;
    }

    const timeout = setTimeout(() => {
      void persistDraft();
    }, 250);

    return () => clearTimeout(timeout);
  }, [isDraftReady, draftKey, persistDraft]);

  const draftNotice = (
    <View style={styles.draftNotice}>
      <Text style={styles.draftNoticeTitle}>
        {draftWasRestored ? "Saved draft restored" : "Offline draft protection"}
      </Text>
      <Text style={styles.draftNoticeText}>
        {draftKey
          ? "Work notes, costs, parts and photos are saved locally as you edit. Customer signatures are not stored and must be captured again after reopening."
          : "This draft cannot be saved locally until the technician and tenant session can be identified."}
      </Text>
      {draftSaveStatus ? (
        <Text
          style={[
            styles.draftNoticeStatus,
            draftSaveStatus === "error" && styles.draftNoticeError
          ]}
        >
          {draftSaveStatus === "saving"
            ? "Saving changes on this device..."
            : draftSaveStatus === "saved"
              ? "Draft saved on this device"
              : "Local draft saving failed. Keep this screen open and retry after checking device storage."}
        </Text>
      ) : null}
      {draftWarning ? (
        <Text style={styles.draftNoticeError}>{draftWarning}</Text>
      ) : null}
    </View>
  );

  async function openCamera() {
    setError(null);
    setCameraError(null);

    try {
      const currentPermission = permission?.granted
        ? permission
        : await requestCameraPermission();

      if (!currentPermission.granted) {
        setCameraError(
          currentPermission.canAskAgain
            ? "Camera access is required to capture job evidence. Please allow camera access and try again."
            : "Camera access is disabled for FieldOps. Enable it in your device settings."
        );
        return;
      }

      setIsCameraReady(false);
      setIsCameraVisible(true);
    } catch (cameraPermissionError: unknown) {
      logError(
        "completion_photo.camera_permission_failed",
        cameraPermissionError
      );

      setCameraError(
        "Unable to request camera permission. Please try again."
      );
    }
  }

  async function capturePhoto() {
    const camera = cameraRef.current;

    if (!camera || !isCameraReady || isCapturing) {
      setCameraError(
        "The camera is not ready yet. Please wait and try again."
      );
      return;
    }

    setIsCapturing(true);
    setCameraError(null);
    setError(null);

    try {
      const picture = await camera.takePictureAsync({
        quality: 0.6,
        exif: false
      });

      if (!picture?.uri) {
        throw new Error("The camera did not return an image.");
      }

      const fileInfo = await getInfoAsync(picture.uri);

      if (
        !fileInfo.exists ||
        typeof fileInfo.size !== "number" ||
        fileInfo.size <= 0
      ) {
        throw new Error(
          "The captured photo could not be validated. Please try again."
        );
      }

      const localId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

      if (!draftPhotoDirectory) {
        throw new Error(
          "Your technician session could not be verified for local photo storage. Return to My Jobs and reopen this job before capturing evidence."
        );
      }

      const persistedPhotoUri = await persistCapturedPhoto(
        picture.uri,
        draftPhotoDirectory,
        localId
      );

      const asset: CompletionPhotoAsset = {
        uri: persistedPhotoUri,
        fileName: `fieldops-${localId}.jpg`,
        contentType: "image/jpeg",
        sizeBytes: fileInfo.size
      };

      const photo: PhotoDraft = {
        localId,
        asset,
        category: photoCategory,
        uploadError:
          fileInfo.size > MAX_PHOTO_SIZE_BYTES
            ? "This photo exceeds the 10 MB limit. Remove it and capture a smaller photo."
            : undefined
      };

      const nextPhotos = [...photos, photo];
      setPhotos(nextPhotos);
      await persistDraft({ photos: nextPhotos });
      setIsCameraVisible(false);

      logEvent("completion_photo.captured", {
        category: photoCategory,
        fileSizeBytes: fileInfo.size
      });

      if (fileInfo.size > MAX_PHOTO_SIZE_BYTES) {
        setError(
          "The captured photo exceeds 10 MB. Remove it and capture another photo before submitting."
        );
      }
    } catch (captureError: unknown) {
      logError(
        "completion_photo.capture_failed",
        captureError
      );

      setCameraError(
        captureError instanceof Error
          ? captureError.message
          : "Unable to capture the photo. Please try again."
      );
    } finally {
      setIsCapturing(false);
    }
  }

  async function removePhoto(photo: PhotoDraft) {
    if (isSubmitting || removingPhotoId) {
      return;
    }

    setError(null);

    if (photo.document && !jobId) {
      setError(
        "The job ID is missing. The uploaded photo cannot be removed."
      );
      return;
    }

    setRemovingPhotoId(photo.localId);

    try {
      if (photo.document && jobId) {
        await deleteCompletionPhoto(
          jobId,
          photo.document.id,
          "Technician removed photo before job completion"
        );
      }

      const remainingPhotos = photos.filter(
        (item) => item.localId !== photo.localId
      );
      setPhotos(remainingPhotos);
      await persistDraft({ photos: remainingPhotos });
      await deleteManagedDraftPhoto(photo.asset.uri);

      logEvent("completion_photo.removed", {
        category: photo.category,
        uploaded: Boolean(photo.document)
      });
    } catch (removeError: unknown) {
      setError(
        removeError instanceof Error
          ? removeError.message
          : "Unable to remove this photo. Please try again."
      );
    } finally {
      setRemovingPhotoId(null);
    }
  }

  async function handleComplete() {
    const numericJobId = Number(String(jobId ?? "").trim());

    if (
      !jobId ||
      !Number.isSafeInteger(numericJobId) ||
      numericJobId <= 0 ||
      isSubmitting
    ) {
      setError(
        "A valid job ID is required. Return to My Jobs and open the job again."
      );
      return;
    }

    if (!signatureData.trim()) {
      setError(
        "Capture the customer's signature before completing the job."
      );
      return;
    }


    if (
      !serviceChargeText.trim() ||
      !materialCostText.trim()
    ) {
      setError(
        "Enter both the Service Charge and Material Cost before submitting."
      );
      return;
    }

    if (
      serviceCharge === null ||
      materialCost === null
    ) {
      setError(
        "Enter valid amounts with no more than two decimal places."
      );
      return;
    }

    const reportSummary = notes.trim();

    if (!reportSummary) {
      setError("Enter a work summary before completing the job.");
      return;
    }

    if (reportSummary.length > 5000) {
      setError("The work summary cannot exceed 5000 characters.");
      return;
    }

    if (/<\s*\/?\s*[A-Za-z][^>]*>/.test(reportSummary)) {
      setError("The work summary must contain plain text, not markup tags.");
      return;
    }

    const partsUsed = partsUsedText
      .split(/\r?\n/)
      .map((part) => part.trim())
      .filter(Boolean);

    const invalidPart = partsUsed.find((part) => part.length > 200);

    if (invalidPart) {
      setError("Each part used must be 200 characters or fewer.");
      return;
    }

    const trimmedDuration = durationMinutes.trim();
    let reportDurationMinutes: number | undefined;

    if (trimmedDuration) {
      if (!/^\d+$/.test(trimmedDuration)) {
        setError("Work duration must be a whole number of minutes.");
        return;
      }

      const parsedDuration = Number(trimmedDuration);

      if (!Number.isSafeInteger(parsedDuration) || parsedDuration < 0) {
        setError("Enter a valid non-negative work duration.");
        return;
      }

      reportDurationMinutes = parsedDuration;
    }

    if (!photos.some((photo) => photo.category === "AFTER")) {
      setError(
        "Capture at least one AFTER photo before submitting the job for completion."
      );
      return;
    }

    const oversizedPhoto = photos.find(
      (photo) =>
        photo.asset.sizeBytes > MAX_PHOTO_SIZE_BYTES
    );

    if (oversizedPhoto) {
      setError(
        "One or more photos exceed 10 MB. Remove those photos and capture smaller ones."
      );
      return;
    }

    const rejectedPhoto = photos.find(
      (photo) =>
        photo.document?.status === "REJECTED" ||
        photo.document?.scan_status === "REJECTED"
    );

    if (rejectedPhoto) {
      setError(
        "A photo was rejected by the server's security scan. Remove it and capture a replacement before continuing."
      );
      return;
    }

    setIsSubmitting(true);
    setError(null);

    // Keep uploaded document IDs in local component state and persist each
    // confirmed upload so the draft can safely resume after a screen restart.
    const workingPhotos = [...photos];
    let completionRequestStarted = false;

    try {
      for (const [index, photo] of workingPhotos.entries()) {

        if (photo.document) {
          continue;
        }

        setUploadingPhotoId(photo.localId);

        let uploadedDocument: CompletionDocument;

        try {
          uploadedDocument = await uploadCompletionPhoto(
            jobId,
            photo.category,
            photo.asset
          );
        } catch (uploadError: unknown) {
          const message =
            uploadError instanceof Error
              ? uploadError.message
              : "Photo upload failed. Check your connection and retry.";

          workingPhotos[index] = {
            ...photo,
            uploadError: message
          };

          setPhotos([...workingPhotos]);

          throw new Error(message);
        } finally {
          setUploadingPhotoId(null);
        }

        workingPhotos[index] = {
          ...photo,
          document: uploadedDocument,
          uploadError: undefined
        };

        setPhotos([...workingPhotos]);
        await persistDraft({ photos: [...workingPhotos] });

        if (
          uploadedDocument.status === "REJECTED" ||
          uploadedDocument.scan_status === "REJECTED"
        ) {
          throw new Error(
            "The server rejected a photo during security scanning. Remove that photo and capture a replacement."
          );
        }
      }

      const savedPhotos = workingPhotos.filter(
        (
          photo
        ): photo is PhotoDraft & {
          document: CompletionDocument;
        } => Boolean(photo.document)
      );

      if (
        savedPhotos.some(
          (photo) =>
            photo.document.status === "REJECTED" ||
            photo.document.scan_status === "REJECTED"
        )
      ) {
        throw new Error(
          "A rejected photo must be removed before job completion."
        );
      }

      const documentDownloadPath = (
        document: CompletionDocument
      ) =>
        `/jobs/${numericJobId}/completion-documents/${document.id}/download`;

      const beforeImages = savedPhotos
        .filter((photo) => photo.category === "BEFORE")
        .map((photo) =>
          documentDownloadPath(photo.document)
        );

      const afterImages = savedPhotos
        .filter((photo) => photo.category === "AFTER")
        .map((photo) =>
          documentDownloadPath(photo.document)
        );

      if (afterImages.length === 0) {
        throw new Error(
          "At least one uploaded AFTER photo is required."
        );
      }

      // Use the canonical closure endpoint so the backend can
      // perform its authoritative lifecycle checks and link
      // pre-completion document uploads to the job closure.
      completionRequestStarted = true;
      await apiClient.post(
        `/jobs/${numericJobId}/close`,
        {
          work_summary: reportSummary,
          work_report: {
            summary: reportSummary,
            parts_used: partsUsed,
            ...(reportDurationMinutes !== undefined
              ? { duration_minutes: reportDurationMinutes }
              : {})
          },
          before_images: beforeImages,
          after_images: afterImages,
          labour_cost: serviceCharge,
          material_cost: materialCost,
          signature_data: signatureData.trim()
        }
      );

      // Stop any queued autosave from recreating the draft after the
      // backend has confirmed completion. Wait for an in-flight local
      // write before removing the saved draft.
      completionConfirmedRef.current = true;
      await draftWritePromiseRef.current;

      if (draftKey) {
        if (tenantId && technicianId && jobId) {
          try {
            await deleteOfflineRecord(
              { tenantId, technicianId },
              "completion-draft",
              jobId
            );
          } catch (draftCleanupError: unknown) {
            logError(
              "completion.draft_cleanup_failed",
              draftCleanupError
            );
          }
        }

        try {
          await AsyncStorage.removeItem(draftKey);
        } catch (legacyDraftCleanupError: unknown) {
          logError(
            "completion.draft_legacy_cleanup_failed",
            legacyDraftCleanupError
          );
        }
      }

      if (draftPhotoDirectory) {
        try {
          await deleteAsync(draftPhotoDirectory, { idempotent: true });
        } catch (draftPhotoCleanupError: unknown) {
          logError(
            "completion.draft_photo_cleanup_failed",
            draftPhotoCleanupError
          );
        }
      }

      try {
        await clearActiveGpsJob(jobId);
      } catch (gpsCleanupError: unknown) {
        logError(
          "gps.active_job_clear_failed",
          gpsCleanupError
        );
      }

      setError(null);
      setSignatureData("");

      logEvent("customer_signature.saved_with_completion", {});
      logEvent("completion.job_and_signature_succeeded", {});

      router.replace("/(app)/jobs");
    } catch (submissionError: unknown) {
      logError(
        "completion_photo.job_submission_failed",
        submissionError
      );

      if (isNetworkUnavailableError(submissionError)) {
        setError(
          completionRequestStarted
            ? "The connection was lost while waiting for the server to confirm completion. Your draft remains saved, but the final outcome is unconfirmed. Return to My Jobs, refresh the job status, and verify it before trying again."
            : "The connection failed before the final job-completion request was sent. Your draft and local photos remain saved. An evidence upload may still have reached the server, so check uploaded evidence before retrying."
        );
      } else {
        setError(
          getApiErrorMessage(
            submissionError,
            "Unable to complete the job. Check your connection and try again."
          )
        );
      }
    } finally {
      setUploadingPhotoId(null);
      setIsSubmitting(false);
    }
  }

  async function handleSaveSignature() {
    if (!signatureData.trim()) {
      setError(
        "Ask the customer to sign in the signature box before completing the job."
      );
      return;
    }

    if (isSavingSignature || isSubmitting) {
      return;
    }

    setIsSavingSignature(true);
    setError(null);

    try {
      await handleComplete();
    } finally {
      setIsSavingSignature(false);
    }
  }

  if (isCostStep) {
    return (
      <ScrollView
        style={styles.screen}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
      >
        <Pressable
          accessibilityRole="button"
          onPress={() => {
            setIsCostStep(false);
            setError(null);
          }}
          style={styles.backButton}
        >
          <Text style={styles.backText}>
            Back to Work Details
          </Text>
        </Pressable>

        <Text style={styles.title}>
          Cost Details
        </Text>

        <Text style={styles.subtitle}>
          Enter the service charge and material cost for
          this job. The subtotal, GST and total calculate
          automatically.
        </Text>

        {draftNotice}

        <View style={styles.card}>
          <Text style={styles.label}>
            Service Charge (₹) *
          </Text>

          <TextInput
            accessibilityLabel="Service charge in rupees"
            value={serviceChargeText}
            onChangeText={(value) => {
              setServiceChargeText(value);
              setError(null);
            }}
            placeholder="0.00"
            placeholderTextColor="#94A3B8"
            keyboardType="decimal-pad"
            editable={!isSubmitting}
            style={[
              styles.notesInput,
              { minHeight: 50 }
            ]}
          />

          <Text style={styles.label}>
            Material Cost (₹) *
          </Text>

          <TextInput
            accessibilityLabel="Material cost in rupees"
            value={materialCostText}
            onChangeText={(value) => {
              setMaterialCostText(value);
              setError(null);
            }}
            placeholder="0.00"
            placeholderTextColor="#94A3B8"
            keyboardType="decimal-pad"
            editable={!isSubmitting}
            style={[
              styles.notesInput,
              { minHeight: 50 }
            ]}
          />

          <View style={styles.costSummaryRow}>
            <Text style={styles.costLabel}>
              SERVICE CHARGE
            </Text>
            <Text style={styles.costValue}>
              {formatINR(serviceChargePaise)}
            </Text>
          </View>

          <View style={styles.costSummaryRow}>
            <Text style={styles.costLabel}>
              MATERIAL COST
            </Text>
            <Text style={styles.costValue}>
              {formatINR(materialCostPaise)}
            </Text>
          </View>

          <View style={styles.costDivider} />

          <View style={styles.costSummaryRow}>
            <Text style={styles.costLabel}>
              SUBTOTAL
            </Text>
            <Text style={styles.costValue}>
              {formatINR(subtotalPaise)}
            </Text>
          </View>

          <View style={styles.costSummaryRow}>
            <Text style={styles.costLabel}>
              GST (5%)
            </Text>
            <Text style={styles.costValue}>
              {formatINR(gstPaise)}
            </Text>
          </View>

          <View style={styles.costDivider} />

          <View style={styles.costSummaryRow}>
            <Text style={styles.costTotalLabel}>
              TOTAL
            </Text>
            <Text style={styles.costTotalValue}>
              {formatINR(totalPaise)}
            </Text>
          </View>
        </View>

        {error ? (
          <Text
            accessibilityRole="alert"
            style={styles.error}
          >
            {error}
          </Text>
        ) : null}

        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Continue to customer signature"
          disabled={
            isSubmitting ||
            Boolean(removingPhotoId) ||
            !jobId
          }
          onPress={() => {
            setError(null);
            setSignatureData("");
            setIsCostStep(false);
            setIsSignatureStep(true);

            logEvent("customer_signature.step_opened", {});
          }}
          style={[
            styles.primaryButton,
            styles.submitButton,
            (isSubmitting ||
              Boolean(removingPhotoId) ||
              !jobId) &&
              styles.disabled
          ]}
        >
          <Text style={styles.primaryButtonText}>
            Continue to Customer Signature
          </Text>
        </Pressable>

        <Text style={styles.notice}>
          FieldOps validates and stores the submitted costs
          through the backend. The backend remains authoritative
          for billing calculations.
        </Text>
      </ScrollView>
    );
  }

  if (isSignatureStep) {
    return (
      <ScrollView
        style={styles.screen}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        scrollEnabled={false}
        showsVerticalScrollIndicator={false}
        bounces={false}
      >
        <Pressable
          accessibilityRole="button"
          disabled={isSavingSignature || isSubmitting}
          onPress={() => {
            setIsSignatureStep(false);
            setIsCostStep(true);
            setError(null);
          }}
          style={styles.backButton}
        >
          <Text style={styles.backText}>
            Back to Cost Details
          </Text>
        </Pressable>

        <Text style={styles.title}>
          Customer Signature
        </Text>

        <Text style={styles.subtitle}>
          Ask the customer to review the completed work and sign
          below to acknowledge it. Obtain their consent before
          capturing the signature.
        </Text>

        {draftNotice}

        <View style={styles.card}>
          <Text style={styles.sectionTitle}>
            Sign below
          </Text>

          <Text style={styles.helperText}>
            The customer can sign using a finger or stylus.
            Tap Use signature when finished.
          </Text>

          <View
            style={{
              height: 250,
              marginTop: 8,
              marginBottom: 8,
              borderWidth: 1,
              borderColor: "#CBD5E1",
              borderRadius: 10,
              overflow: "hidden",
              backgroundColor: "#FFFFFF"
            }}
          >
            <SignatureCanvas
              onOK={(signature) => {
                const canonical =
                  typeof signature === "string"
                    ? signature.trim()
                    : "";

                if (!canonical) {
                  setSignatureData("");
                  setError(
                    "The signature is empty. Please ask the customer to sign."
                  );
                  return;
                }

                if (
                  canonical.length > 2_000_000 ||
                  !/^data:image\/(?:png|jpeg);base64,[A-Za-z0-9+/=]+$/.test(
                    canonical
                  )
                ) {
                  setSignatureData("");
                  setError(
                    "The signature is invalid or too large. Please clear it and sign again."
                  );
                  return;
                }

                setSignatureData(canonical);
                setError(null);

                logEvent("customer_signature.captured", {});
              }}
              onEmpty={() => {
                setSignatureData("");
                setError(
                  "Please ask the customer to sign before continuing."
                );
              }}
              onClear={() => {
                setSignatureData("");
                setError(null);
              }}
              onBegin={() => {
                setSignatureData("");
                setError(null);
              }}
              onError={() => {
                setSignatureData("");
                setError(
                  "The signature pad encountered a problem. Please try again."
                );
              }}
              descriptionText="Customer signature"
              clearText="Clear"
              confirmText="Use signature"
              imageType="image/png"
              autoClear={false}
              trimWhitespace
              backgroundColor="#FFFFFF"
              penColor="#111827"
              style={{ flex: 1 }}
              webStyle={`
                .m-signature-pad--body {
                  bottom: 64px !important;
                }

                .m-signature-pad--footer {
                  display: flex !important;
                  position: absolute;
                  left: 0;
                  right: 0;
                  bottom: 0;
                  height: 56px;
                  margin: 0;
                  padding: 4px 8px;
                  box-sizing: border-box;
                }

                .m-signature-pad--footer .button {
                  background-color: #17633A;
                  color: #FFFFFF;
                  border: none;
                  border-radius: 6px;
                  padding: 8px 12px;
                  font-size: 14px;
                }
              `}
              webviewProps={{
                allowFileAccess: false,
                allowFileAccessFromFileURLs: false,
                mixedContentMode: "never"
              }}
            />
          </View>

          <Text
            style={{
              color: signatureData ? "#17633A" : "#64748B",
              fontSize: 13,
              marginTop: 8
            }}
          >
            {signatureData
              ? "Signature captured. Review it before saving."
              : "No signature captured yet."}
          </Text>
        </View>

        {error ? (
          <Text
            accessibilityRole="alert"
            style={styles.error}
          >
            {error}
          </Text>
        ) : null}

        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Save customer signature"
          disabled={isSavingSignature || !signatureData}
          onPress={() => void handleSaveSignature()}
          style={[
            styles.primaryButton,
            (isSavingSignature || !signatureData) &&
              styles.disabled
          ]}
        >
          {isSavingSignature ? (
            <View style={styles.inlineStatus}>
              <ActivityIndicator color="#FFFFFF" />
              <Text style={styles.primaryButtonText}>
                Saving signature and completing job...
              </Text>
            </View>
          ) : (
            <Text style={styles.primaryButtonText}>
              Complete Job & Save Signature
            </Text>
          )}
        </Pressable>

        <Text style={styles.notice}>
          The customer signature and job completion are submitted
          together. The backend validates technician permissions,
          job assignment, tenant access, and completion rules.
        </Text>
      </ScrollView>
    );
  }

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      <Pressable
        accessibilityRole="button"
        disabled={isSubmitting}
        onPress={() => router.back()}
        style={styles.backButton}
      >
        <Text style={styles.backText}>
          Back to job details
        </Text>
      </Pressable>

      <Text style={styles.title}>Complete Job</Text>

      <Text style={styles.subtitle}>
        Capture the required after-work evidence, optionally add
        before-work photos, and submit your completion notes.
      </Text>

      {draftNotice}

      <View style={styles.card}>
        <Text style={styles.sectionTitle}>
          Job evidence photos
        </Text>

        <Text style={styles.helperText}>
          At least one AFTER photo is required. JPEG photos are
          captured by the device camera. Maximum upload size: 10 MB.
        </Text>

        <Text style={styles.label}>Photo category</Text>

        <View style={styles.categoryRow}>
          {(["BEFORE", "AFTER"] as const).map((category) => (
            <Pressable
              key={category}
              accessibilityRole="button"
              accessibilityState={{
                selected: photoCategory === category
              }}
              disabled={isSubmitting || isCameraVisible}
              onPress={() => setPhotoCategory(category)}
              style={[
                styles.categoryButton,
                photoCategory === category &&
                  styles.categoryButtonSelected
              ]}
            >
              <Text
                style={[
                  styles.categoryText,
                  photoCategory === category &&
                    styles.categoryTextSelected
                ]}
              >
                {category === "BEFORE"
                  ? "Before work"
                  : "After work"}
              </Text>
            </Pressable>
          ))}
        </View>

        {isCameraVisible ? (
          <View style={styles.cameraContainer}>
            <CameraView
              ref={cameraRef}
              style={styles.cameraPreview}
              facing="back"
              mode="picture"
              onCameraReady={() => setIsCameraReady(true)}
              onMountError={(event) => {
                logError(
                  "completion_photo.camera_mount_failed",
                  new Error(event.message)
                );

                setCameraError(
                  "The camera could not start. Check camera access and try again."
                );

                setIsCameraVisible(false);
                setIsCameraReady(false);
              }}
            />

            <Text style={styles.cameraHint}>
              Keep the device steady and make sure the evidence is clear.
            </Text>

            <Pressable
              accessibilityRole="button"
              disabled={!isCameraReady || isCapturing}
              onPress={() => void capturePhoto()}
              style={[
                styles.primaryButton,
                (!isCameraReady || isCapturing) &&
                  styles.disabled
              ]}
            >
              {isCapturing ? (
                <ActivityIndicator color="#FFFFFF" />
              ) : (
                <Text style={styles.primaryButtonText}>
                  Capture photo
                </Text>
              )}
            </Pressable>

            <Pressable
              accessibilityRole="button"
              disabled={isCapturing}
              onPress={() => {
                setIsCameraVisible(false);
                setIsCameraReady(false);
                setCameraError(null);
              }}
              style={styles.secondaryButton}
            >
              <Text style={styles.secondaryButtonText}>
                Cancel camera
              </Text>
            </Pressable>
          </View>
        ) : (
          <Pressable
            accessibilityRole="button"
            disabled={isSubmitting || Boolean(removingPhotoId)}
            onPress={() => void openCamera()}
            style={[
              styles.primaryButton,
              (isSubmitting || removingPhotoId) &&
                styles.disabled
            ]}
          >
            <Text style={styles.primaryButtonText}>
              {permission?.granted
                ? "Add photo"
                : "Enable camera / Add photo"}
            </Text>
          </Pressable>
        )}

        {cameraError ? (
          <Text accessibilityRole="alert" style={styles.error}>
            {cameraError}
          </Text>
        ) : null}

        {!permission?.granted &&
        permission?.canAskAgain === false &&
        !isCameraVisible ? (
          <Pressable
            accessibilityRole="button"
            onPress={() => {
              void Linking.openSettings().catch(
                (settingsError: unknown) => {
                  logError(
                    "completion_photo.settings_open_failed",
                    settingsError
                  );

                  setCameraError(
                    "Unable to open settings. Enable camera access manually in your device settings."
                  );
                }
              );
            }}
            style={styles.secondaryButton}
          >
            <Text style={styles.secondaryButtonText}>
              Open device settings
            </Text>
          </Pressable>
        ) : null}

        {photos.length > 0 ? (
          <View style={styles.photoList}>
            <Text style={styles.sectionTitle}>
              Captured photos ({photos.length})
            </Text>

            {photos.map((photo) => {
              const isUploading =
                uploadingPhotoId === photo.localId;

              const isRemoving =
                removingPhotoId === photo.localId;

              return (
                <View
                  key={photo.localId}
                  style={styles.photoCard}
                >
                  <Image
                    source={{ uri: photo.asset.uri }}
                    style={styles.thumbnail}
                    resizeMode="cover"
                    accessibilityLabel={`${photo.category} job evidence photo`}
                  />

                  <View style={styles.photoDetails}>
                    <Text style={styles.photoTitle}>
                      {photo.category === "BEFORE"
                        ? "Before work"
                        : "After work"}
                    </Text>

                    <Text style={styles.photoMeta}>
                      {formatFileSize(photo.asset.sizeBytes)}
                    </Text>

                    {photo.document ? (
                      <Text style={styles.uploadStatus}>
                        Uploaded · scan{" "}
                        {photo.document.scan_status.toLowerCase()}
                      </Text>
                    ) : isUploading ? (
                      <View style={styles.inlineStatus}>
                        <ActivityIndicator
                          size="small"
                          color="#217346"
                        />
                        <Text style={styles.photoMeta}>
                          Uploading...
                        </Text>
                      </View>
                    ) : (
                      <Text style={styles.photoMeta}>
                        Waiting for upload
                      </Text>
                    )}

                    {photo.uploadError ? (
                      <Text
                        accessibilityRole="alert"
                        style={styles.photoError}
                      >
                        {photo.uploadError}
                      </Text>
                    ) : null}

                    <Pressable
                      accessibilityRole="button"
                      disabled={
                        isSubmitting ||
                        isUploading ||
                        isRemoving ||
                        Boolean(removingPhotoId)
                      }
                      onPress={() => void removePhoto(photo)}
                      style={styles.removeButton}
                    >
                      {isRemoving ? (
                        <ActivityIndicator
                          size="small"
                          color="#B91C1C"
                        />
                      ) : (
                        <Text style={styles.removeText}>
                          Remove photo
                        </Text>
                      )}
                    </Pressable>
                  </View>
                </View>
              );
            })}
          </View>
        ) : (
          <Text style={styles.emptyText}>
            No evidence photos captured yet.
          </Text>
        )}
      </View>

      <View style={styles.card}>
        <Text style={styles.sectionTitle}>
          Work report
        </Text>

        <Text style={styles.helperText}>
          Record the work performed, parts used, and time spent.
          Your report will be submitted with the job completion.
        </Text>

        <Text style={styles.label}>
          Work summary *
        </Text>

        <TextInput
          accessibilityLabel="Work report summary"
          value={notes}
          onChangeText={setNotes}
          placeholder="Describe the fault, work performed, and outcome..."
          placeholderTextColor="#94A3B8"
          multiline
          maxLength={5000}
          editable={!isSubmitting}
          textAlignVertical="top"
          style={styles.notesInput}
        />

        <Text style={styles.counter}>
          {notes.length}/5000
        </Text>

        <Text style={styles.label}>
          Parts used (optional)
        </Text>

        <TextInput
          accessibilityLabel="Parts used"
          value={partsUsedText}
          onChangeText={setPartsUsedText}
          placeholder={"Enter one part per line\nExample: Capacitor"}
          placeholderTextColor="#94A3B8"
          multiline
          editable={!isSubmitting}
          textAlignVertical="top"
          style={styles.notesInput}
        />

        <Text style={styles.label}>
          Work duration in minutes (optional)
        </Text>

        <TextInput
          accessibilityLabel="Work duration in minutes"
          value={durationMinutes}
          onChangeText={setDurationMinutes}
          placeholder="Example: 90"
          placeholderTextColor="#94A3B8"
          keyboardType="number-pad"
          maxLength={6}
          editable={!isSubmitting}
          style={[
            styles.notesInput,
            { minHeight: 50 }
          ]}
        />
      </View>

      {error ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {error}
        </Text>
      ) : null}

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Continue to cost details"
        disabled={
          isSubmitting ||
          Boolean(removingPhotoId) ||
          !jobId
        }
        onPress={() => {
          setError(null);
          setIsCostStep(true);
        }}
        style={[
          styles.primaryButton,
          styles.submitButton,
          (isSubmitting ||
            Boolean(removingPhotoId) ||
            !jobId) &&
            styles.disabled
        ]}
      >
        <Text style={styles.primaryButtonText}>
          Continue to Cost Details
        </Text>
      </Pressable>

      <Text style={styles.notice}>
        FieldOps validates file content, job access, tenant
        authorization and completion rules on the server. If an
        upload fails, captured photos remain available on this screen
        so you can retry.
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#F8FAFC"
  },
  draftNotice: {
    marginBottom: 18,
    padding: 12,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "#B7DCC5",
    backgroundColor: "#EAF6EF"
  },
  draftNoticeTitle: {
    color: "#17633A",
    fontSize: 13,
    fontWeight: "800",
    marginBottom: 4
  },
  draftNoticeText: {
    color: "#446052",
    fontSize: 12,
    lineHeight: 18
  },
  draftNoticeStatus: {
    color: "#17633A",
    fontSize: 12,
    fontWeight: "700",
    lineHeight: 18,
    marginTop: 5
  },
  draftNoticeError: {
    color: "#B42332",
    fontSize: 12,
    lineHeight: 18,
    fontWeight: "700",
    marginTop: 5
  },
  content: {
    padding: 20,
    paddingTop: 42,
    paddingBottom: 36
  },
  backButton: {
    alignSelf: "flex-start",
    paddingVertical: 10,
    marginBottom: 20
  },
  backText: {
    color: "#217346",
    fontSize: 14,
    fontWeight: "700"
  },
  title: {
    color: "#0F172A",
    fontSize: 28,
    fontWeight: "800"
  },
  subtitle: {
    color: "#64748B",
    fontSize: 14,
    lineHeight: 21,
    marginTop: 8,
    marginBottom: 24
  },
  card: {
    backgroundColor: "#FFFFFF",
    borderColor: "#E2E8F0",
    borderWidth: 1,
    borderRadius: 12,
    padding: 16,
    marginBottom: 18
  },
  sectionTitle: {
    color: "#0F172A",
    fontSize: 17,
    fontWeight: "700",
    marginBottom: 10
  },
  label: {
    color: "#334155",
    fontSize: 14,
    fontWeight: "700",
    marginTop: 12,
    marginBottom: 10
  },
  helperText: {
    color: "#64748B",
    fontSize: 13,
    lineHeight: 19
  },
  costSummaryRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    minHeight: 38
  },
  costLabel: {
    color: "#64748B",
    fontSize: 13,
    fontWeight: "600"
  },
  costValue: {
    color: "#0F172A",
    fontSize: 14,
    fontWeight: "600",
    fontVariant: ["tabular-nums"]
  },
  costDivider: {
    borderBottomWidth: 1,
    borderColor: "#DCE6E0",
    marginVertical: 8
  },
  costTotalLabel: {
    color: "#17633A",
    fontSize: 13,
    fontWeight: "800",
    letterSpacing: 0.5
  },
  costTotalValue: {
    color: "#17633A",
    fontSize: 17,
    fontWeight: "800",
    fontVariant: ["tabular-nums"]
  },
  categoryRow: {
    flexDirection: "row",
    gap: 10,
    marginBottom: 16
  },
  categoryButton: {
    flex: 1,
    minHeight: 44,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 10,
    borderWidth: 1,
    borderColor: "#CBD5E1",
    backgroundColor: "#FFFFFF",
    paddingHorizontal: 8
  },
  categoryButtonSelected: {
    borderColor: "#217346",
    backgroundColor: "#E8F4EC"
  },
  categoryText: {
    color: "#475569",
    fontSize: 13,
    fontWeight: "600"
  },
  categoryTextSelected: {
    color: "#17633A",
    fontWeight: "800"
  },
  primaryButton: {
    minHeight: 50,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#217346",
    borderRadius: 10,
    paddingHorizontal: 16,
    marginTop: 14
  },
  primaryButtonText: {
    color: "#FFFFFF",
    fontSize: 14,
    fontWeight: "700",
    textAlign: "center"
  },
  secondaryButton: {
    minHeight: 42,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "#CBD5E1",
    borderRadius: 10,
    paddingHorizontal: 14,
    marginTop: 10
  },
  secondaryButtonText: {
    color: "#334155",
    fontSize: 13,
    fontWeight: "700"
  },
  disabled: {
    opacity: 0.55
  },
  cameraContainer: {
    marginTop: 8
  },
  cameraPreview: {
    width: "100%",
    height: 280,
    borderRadius: 12,
    overflow: "hidden"
  },
  cameraHint: {
    color: "#64748B",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 10
  },
  photoList: {
    marginTop: 24
  },
  photoCard: {
    flexDirection: "row",
    gap: 12,
    borderWidth: 1,
    borderColor: "#E2E8F0",
    borderRadius: 12,
    padding: 10,
    marginTop: 10
  },
  thumbnail: {
    width: 92,
    height: 108,
    borderRadius: 8,
    backgroundColor: "#E2E8F0"
  },
  photoDetails: {
    flex: 1,
    justifyContent: "center"
  },
  photoTitle: {
    color: "#0F172A",
    fontSize: 14,
    fontWeight: "700"
  },
  photoMeta: {
    color: "#64748B",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 4
  },
  uploadStatus: {
    color: "#17633A",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 4
  },
  inlineStatus: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8
  },
  photoError: {
    color: "#B91C1C",
    fontSize: 12,
    lineHeight: 17,
    marginTop: 5
  },
  removeButton: {
    alignSelf: "flex-start",
    paddingVertical: 8,
    paddingRight: 8
  },
  removeText: {
    color: "#B91C1C",
    fontSize: 12,
    fontWeight: "700"
  },
  emptyText: {
    color: "#64748B",
    fontSize: 13,
    lineHeight: 20,
    marginTop: 18
  },
  notesInput: {
    minHeight: 150,
    borderColor: "#CBD5E1",
    borderWidth: 1,
    borderRadius: 10,
    padding: 12,
    color: "#0F172A",
    fontSize: 15
  },
  counter: {
    color: "#64748B",
    fontSize: 12,
    textAlign: "right",
    marginTop: 8
  },
  error: {
    color: "#B91C1C",
    fontSize: 13,
    lineHeight: 20,
    marginTop: 12
  },
  submitButton: {
    minHeight: 56,
    marginTop: 8
  },
  notice: {
    color: "#64748B",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 16
  }
});
