import { apiClient, isNetworkUnavailableError } from "./client";
import { getApiErrorMessage } from "./apiError";
import {
  logError,
  logEvent
} from "../observability/logger";

export type CompletionPhotoCategory = "BEFORE" | "AFTER";

export type CompletionPhotoContentType =
  | "image/jpeg"
  | "image/png"
  | "image/webp";

export interface CompletionPhotoAsset {
  uri: string;
  fileName: string;
  contentType: CompletionPhotoContentType;
  sizeBytes: number;
}

export interface CompletionDocument {
  id: number;
  job_id: number;
  job_closure_id: number | null;
  tenant_id: string;
  category: CompletionPhotoCategory;
  document_type: "PHOTO";
  original_filename: string;
  content_type: string;
  file_size: number;
  checksum_sha256: string;
  storage_key: string;
  status: "PENDING" | "AVAILABLE" | "REJECTED";
  scan_status: "PENDING" | "CLEAN" | "REJECTED";
  scanned_at: string | null;
  uploaded_by: string;
}

export type CompletionDocumentOperation = "upload" | "delete";

export type CompletionDocumentFailureKind =
  | "NETWORK_UNAVAILABLE"
  | "SERVER_ERROR"
  | "REQUEST_REJECTED"
  | "UNKNOWN";

/**
 * Describes a failed completion-document request without assuming that
 * a request with no conclusive response was not processed by the backend.
 * Callers must not automatically retry uncertain operations.
 */
export class CompletionDocumentOperationError extends Error {
  readonly operation: CompletionDocumentOperation;
  readonly kind: CompletionDocumentFailureKind;
  readonly status?: number;
  readonly outcomeUncertain: boolean;

  constructor(args: {
    operation: CompletionDocumentOperation;
    kind: CompletionDocumentFailureKind;
    message: string;
    status?: number;
    outcomeUncertain: boolean;
  }) {
    super(args.message);
    this.name = "CompletionDocumentOperationError";
    this.operation = args.operation;
    this.kind = args.kind;
    this.status = args.status;
    this.outcomeUncertain = args.outcomeUncertain;
  }
}

const MAX_PHOTO_SIZE_BYTES = 10 * 1024 * 1024;

const ALLOWED_PHOTO_TYPES: Record<
  CompletionPhotoContentType,
  string
> = {
  "image/jpeg": ".jpg",
  "image/png": ".png",
  "image/webp": ".webp"
};

function validatePhoto(
  photo: CompletionPhotoAsset,
  category: CompletionPhotoCategory
): string {
  if (category !== "BEFORE" && category !== "AFTER") {
    throw new Error("Choose a valid photo category.");
  }

  if (!photo.uri?.trim()) {
    throw new Error("The captured photo is unavailable. Take it again.");
  }

  if (
    !Number.isSafeInteger(photo.sizeBytes) ||
    photo.sizeBytes <= 0
  ) {
    throw new Error("The photo file could not be validated. Try again.");
  }

  if (photo.sizeBytes > MAX_PHOTO_SIZE_BYTES) {
    throw new Error("The photo exceeds the 10 MB upload limit.");
  }

  const expectedExtension = ALLOWED_PHOTO_TYPES[photo.contentType];

  if (!expectedExtension) {
    throw new Error("Unsupported image format. Use JPEG, PNG or WEBP.");
  }

  const fileName = photo.fileName
    .replace(/\\/g, "/")
    .split("/")
    .pop()
    ?.trim();

  if (
    !fileName ||
    fileName.length > 255 ||
    fileName === "." ||
    fileName === ".."
  ) {
    throw new Error("The photo filename is invalid.");
  }

  const actualExtension =
    fileName.slice(fileName.lastIndexOf(".")).toLowerCase();

  if (actualExtension !== expectedExtension) {
    throw new Error(
      "The photo filename and image format do not match."
    );
  }

  return fileName;
}

function getHttpStatus(error: unknown): number | undefined {
  if (typeof error !== "object" || error === null || !("response" in error)) {
    return undefined;
  }

  const response = (error as {
    response?: { status?: unknown } | null;
  }).response;

  return typeof response?.status === "number"
    ? response.status
    : undefined;
}

function createOperationError(
  error: unknown,
  operation: CompletionDocumentOperation,
  fallbackMessage: string
): CompletionDocumentOperationError {
  const status = getHttpStatus(error);
  const networkUnavailable = isNetworkUnavailableError(error);
  const serverError = status !== undefined && status >= 500;
  const outcomeUncertain = networkUnavailable || serverError;

  const kind: CompletionDocumentFailureKind = networkUnavailable
    ? "NETWORK_UNAVAILABLE"
    : serverError
      ? "SERVER_ERROR"
      : status !== undefined
        ? "REQUEST_REJECTED"
        : "UNKNOWN";

  let message = getApiErrorMessage(error, fallbackMessage);

  if (outcomeUncertain) {
    message = operation === "upload"
      ? "The photo upload did not receive a conclusive response. It may have reached the server. Check the job's evidence before retrying to avoid duplicates."
      : "The photo removal did not receive a conclusive response. Refresh the job's evidence before trying again.";
  }

  return new CompletionDocumentOperationError({
    operation,
    kind,
    message,
    status,
    outcomeUncertain
  });
}

/**
 * Uploads technician-captured job evidence through the existing
 * backend completion-document workflow.
 *
 * The backend remains authoritative for authentication, tenant
 * isolation, job ownership, file-content validation and scanning.
 * Upload failures with an uncertain outcome are surfaced to the caller;
 * this function never retries an upload automatically.
 */
export async function uploadCompletionPhoto(
  jobId: string | number,
  category: CompletionPhotoCategory,
  photo: CompletionPhotoAsset
): Promise<CompletionDocument> {
  const numericJobId = Number(String(jobId).trim());

  if (
    !Number.isSafeInteger(numericJobId) ||
    numericJobId <= 0
  ) {
    throw new Error("A valid job ID is required.");
  }

  const fileName = validatePhoto(photo, category);

  const formData = new FormData();

  formData.append("category", category);

  formData.append(
    "file",
    {
      uri: photo.uri,
      name: fileName,
      type: photo.contentType
    } as unknown as Blob
  );

  logEvent("completion_photo.upload_started", {
    category,
    fileSizeBytes: photo.sizeBytes
  });

  try {
    const response = await apiClient.post<CompletionDocument>(
      `/jobs/${numericJobId}/completion-documents/photos`,
      formData,
      {
        headers: {
          Accept: "application/json",
          "Content-Type": "multipart/form-data"
        }
      }
    );

    logEvent("completion_photo.upload_succeeded", {
      category,
      status: response.data.status,
      scanStatus: response.data.scan_status
    });

    return response.data;
  } catch (error: unknown) {
    logError("completion_photo.upload_failed", error, {
      category
    });

    throw createOperationError(
      error,
      "upload",
      "Photo upload failed. Check your connection and try again."
    );
  }
}

/**
 * Deletes a photo uploaded before job completion.
 * The backend remains authoritative for deletion permissions
 * and document retention rules. This function never retries deletion
 * automatically when the outcome may be uncertain.
 */
export async function deleteCompletionPhoto(
  jobId: string | number,
  documentId: number,
  reason: string
): Promise<void> {
  const numericJobId = Number(String(jobId).trim());

  if (
    !Number.isSafeInteger(numericJobId) ||
    numericJobId <= 0
  ) {
    throw new Error("A valid job ID is required.");
  }

  if (!Number.isSafeInteger(documentId) || documentId <= 0) {
    throw new Error("A valid document ID is required.");
  }

  if (!reason.trim() || reason.trim().length < 3) {
    throw new Error("A reason is required to remove the photo.");
  }

  try {
    await apiClient.delete(
      `/jobs/${numericJobId}/documents/${documentId}`,
      {
        data: {
          reason: reason.trim(),
          override: false
        }
      }
    );

    logEvent("completion_photo.deleted", {});
  } catch (error: unknown) {
    logError("completion_photo.delete_failed", error);

    throw createOperationError(
      error,
      "delete",
      "Unable to remove the uploaded photo. Please try again."
    );
  }
}
