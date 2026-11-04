import { useCallback, useEffect, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  deleteOfflineRecord,
  getOfflineRecord,
  setOfflineRecord,
  type OfflineScope
} from "../../../src/offline/offlineStore";
import { isAxiosError } from "axios";
import {
  ActivityIndicator,
  Animated,
  Alert,
  Easing,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { LinearGradient } from "expo-linear-gradient";
import * as Location from "expo-location";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useAuthStore } from "../../../src/auth/authStore";
import { apiClient, isNetworkUnavailableError } from "../../../src/api/client";
import { setActiveGpsJob } from "../../../src/gps/backgroundLocationService";
import { getTechnicianAvailabilityLocation } from "../../../src/gps/gpsService";
import {
  getTechnicianJob,
  getTechnicianJobs,
  type TechnicianJob
} from "../../../src/api/technician";
import {
  performTechnicianJobAction,
  type TechnicianJobAction
} from "../../../src/api/jobActions";
import {
  enqueueJobAction,
  getJobActionQueue,
  type QueueableTechnicianJobAction,
  type QueuedJobAction
} from "../../../src/offline/jobActionQueue";
import { useNetworkStatus } from "../../../src/hooks/useNetworkStatus";
import {
  ErrorState,
  LoadingState
} from "../../../src/components/ScreenState";
import {
  getJobActionOptions,
  getJobStatusLabel,
  normalizeJobStatus
} from "../../../src/utils/jobStatus";

type IconName = keyof typeof Ionicons.glyphMap;

type CacheIdentifier = string | number | null | undefined;

interface CachedTechnicianJob {
  job: TechnicianJob;
  cachedAt: string;
}

interface OlaRouteSummary {
  distance_meters: number;
  duration_seconds: number;
  duration_in_traffic_seconds?: number | null;
}

interface TechnicianTrackingApiSummary {
  job_id: string | number;
  distance_travelled_km?: number | null;
  technician_latitude?: number | null;
  technician_longitude?: number | null;
  technician_last_ping?: string | null;
  has_route_data?: boolean;
}

interface TechnicianTrackingSummary {
  distanceToCustomerKm: number | null;
  estimatedMinutes: number | null;
  distanceTravelledKm: number | null;
  isWaitingForGps: boolean;
  isLoading: boolean;
}

interface Coordinate {
  latitude: number;
  longitude: number;
}

function isValidCoordinate(value: Coordinate | null): value is Coordinate {
  return Boolean(
    value && Number.isFinite(value.latitude) && Number.isFinite(value.longitude) &&
      value.latitude >= -90 && value.latitude <= 90 &&
      value.longitude >= -180 && value.longitude <= 180 &&
      !(value.latitude === 0 && value.longitude === 0)
  );
}

function formatOnsiteDuration(
  startValue: string | null | undefined,
  now: number,
  completedAt?: string | null
): string {
  if (!startValue) return "Pending";
  const start = Date.parse(startValue);
  if (!Number.isFinite(start)) return "Pending";
  const completed = completedAt ? Date.parse(completedAt) : Number.NaN;
  const end = Number.isFinite(completed) ? completed : now;
  const minutes = Math.max(0, Math.floor((end - start) / 60_000));
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

function getCustomerInitials(name?: string | null): string {
  const parts = (name || "Customer").trim().split(/\s+/).filter(Boolean);
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase() ?? "").join("") || "CU";
}

function getJobCacheKey(
  tenantId: CacheIdentifier,
  userId: CacheIdentifier,
  jobId: string
): string | null {
  if (tenantId == null || userId == null || !jobId.trim()) {
    return null;
  }

  const tenantKey = String(tenantId).trim();
  const technicianKey = String(userId).trim();

  if (!tenantKey || !technicianKey) {
    return null;
  }

  return [
    "fieldops:offline:job-detail:v1",
    encodeURIComponent(tenantKey),
    encodeURIComponent(technicianKey),
    encodeURIComponent(jobId)
  ].join(":");
}

function getJobCacheScope(
  tenantId: CacheIdentifier,
  userId: CacheIdentifier
): OfflineScope | null {
  if (tenantId == null || userId == null) {
    return null;
  }

  const tenantKey = String(tenantId).trim();
  const technicianKey = String(userId).trim();

  if (!tenantKey || !technicianKey) {
    return null;
  }

  return {
    tenantId: tenantKey,
    technicianId: technicianKey
  };
}

function isValidCachedTechnicianJob(
  value: unknown,
  expectedJobId: string
): value is CachedTechnicianJob {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as {
    job?: unknown;
    cachedAt?: unknown;
  };

  if (
    typeof candidate.job !== "object" ||
    candidate.job === null ||
    typeof candidate.cachedAt !== "string"
  ) {
    return false;
  }

  const cachedJob = candidate.job as Partial<TechnicianJob>;

  return String(cachedJob.id) === expectedJobId;
}

async function readCachedTechnicianJob(
  scope: OfflineScope | null,
  legacyCacheKey: string | null,
  expectedJobId: string
): Promise<CachedTechnicianJob | null> {
  if (!scope) {
    return null;
  }

  try {
    let parsedValue = await getOfflineRecord<unknown>(
      scope,
      "job-detail",
      expectedJobId
    );

    if (parsedValue === null && legacyCacheKey) {
      const rawValue = await AsyncStorage.getItem(legacyCacheKey);

      if (rawValue) {
        const legacyValue: unknown = JSON.parse(rawValue);

        if (isValidCachedTechnicianJob(legacyValue, expectedJobId)) {
          // Migration succeeds only if encrypted storage accepts the record.
          await setOfflineRecord(
            scope,
            "job-detail",
            expectedJobId,
            legacyValue
          );

          parsedValue = legacyValue;
        }

        // Remove the old plaintext copy after attempting migration.
        await AsyncStorage.removeItem(legacyCacheKey);
      }
    } else if (legacyCacheKey) {
      // The encrypted copy already exists; discard the plaintext copy.
      await AsyncStorage.removeItem(legacyCacheKey);
    }

    if (!isValidCachedTechnicianJob(parsedValue, expectedJobId)) {
      if (parsedValue !== null) {
        await deleteOfflineRecord(
          scope,
          "job-detail",
          expectedJobId
        );
      }

      return null;
    }

    return parsedValue;
  } catch {
    // Do not use legacy plaintext data if encrypted storage fails.
    if (legacyCacheKey) {
      try {
        await AsyncStorage.removeItem(legacyCacheKey);
      } catch {
        // Cache cleanup must not block the authoritative API request.
      }
    }

    return null;
  }
}

async function saveCachedTechnicianJob(
  scope: OfflineScope | null,
  jobId: string,
  job: TechnicianJob
): Promise<string> {
  const cachedAt = new Date().toISOString();

  if (!scope) {
    return cachedAt;
  }

  try {
    const cachedValue: CachedTechnicianJob = {
      job,
      cachedAt
    };

    await setOfflineRecord(
      scope,
      "job-detail",
      jobId,
      cachedValue
    );
  } catch {
    // A cache write failure must not turn a successful API request into a failure.
  }

  return cachedAt;
}

function canUseCachedJobAfterError(error: unknown): boolean {
  if (isNetworkUnavailableError(error)) {
    return true;
  }

  if (!isAxiosError(error) || !error.response) {
    return false;
  }

  const status = error.response.status;

  return (
    status === 408 ||
    status === 425 ||
    status === 429 ||
    status >= 500
  );
}

function formatCachedTimestamp(value: string | null): string {
  if (!value) {
    return "Last saved time unavailable.";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Last saved time unavailable.";
  }

  return `Last saved ${date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  })}.`;
}

export default function JobDetailScreen() {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const { jobId, source } = useLocalSearchParams<{ jobId: string; source?: string }>();
  const openedFromHistory = source === "history";
  const { isOffline } = useNetworkStatus();

  const [job, setJob] = useState<TechnicianJob | null>(null);
  const [otherStartedJob, setOtherStartedJob] = useState<TechnicianJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [dataSource, setDataSource] =
    useState<"server" | "cache" | null>(null);
  const [cachedAt, setCachedAt] = useState<string | null>(null);
  const [activeAction, setActiveAction] =
    useState<TechnicianJobAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [queuedActions, setQueuedActions] = useState<QueuedJobAction[]>([]);
  const [trackingSummary, setTrackingSummary] = useState<TechnicianTrackingSummary>({
    distanceToCustomerKm: null,
    estimatedMinutes: null,
    distanceTravelledKm: null,
    isWaitingForGps: false,
    isLoading: false
  });
  const [trackingClock, setTrackingClock] = useState(Date.now());
  const [isRejectModalVisible, setIsRejectModalVisible] = useState(false);
  const [rejectionReason, setRejectionReason] = useState("");
  const [currentTimeMs, setCurrentTimeMs] = useState(() => Date.now());

  const assignedStatus = job
    ? normalizeJobStatus(job.status)
    : "UNKNOWN";

  const assignedAtMs = job?.assigned_at
    ? Date.parse(job.assigned_at)
    : Number.NaN;

  const acceptanceRemainingSeconds =
    assignedStatus === "ASSIGNED" && Number.isFinite(assignedAtMs)
      ? Math.max(
          0,
          Math.floor(
            (assignedAtMs + 10 * 60 * 1000 - currentTimeMs) / 1000
          )
        )
      : null;

  const acceptanceExpired = acceptanceRemainingSeconds === 0;

  const loadJob = useCallback(async () => {
    if (!jobId) {
      setError("The job ID is missing.");
      setLoading(false);
      return;
    }

    const requestedJobId = String(jobId);
    const cacheKey = getJobCacheKey(
      user?.tenant_id,
      user?.id,
      requestedJobId
    );
    const cacheScope = getJobCacheScope(
      user?.tenant_id,
      user?.id
    );

    setLoading(true);
    setError(null);
    setOtherStartedJob(null);

    let cachedDetails = await readCachedTechnicianJob(
      cacheScope,
      cacheKey,
      requestedJobId
    );

    if (cachedDetails) {
      setJob(cachedDetails.job);
      setDataSource("cache");
      setCachedAt(cachedDetails.cachedAt);
      setLoading(false);
    }

    try {
      const result = await getTechnicianJob(requestedJobId);
      void getTechnicianJobs().then((assignedJobs) => {
        const startedElsewhere = assignedJobs.find((candidate) => {
          const status = normalizeJobStatus(candidate.status);
          return String(candidate.id) !== requestedJobId &&
            ["EN_ROUTE", "ON_SITE", "IN_PROGRESS", "PAUSED"].includes(status);
        }) ?? null;
        setOtherStartedJob(startedElsewhere);
      }).catch(() => setOtherStartedJob(null));
      const savedAt = await saveCachedTechnicianJob(
        cacheScope,
        requestedJobId,
        result
      );

      setJob(result);
      setDataSource("server");
      setCachedAt(savedAt);
      setError(null);
    } catch (loadError: unknown) {
      if (canUseCachedJobAfterError(loadError)) {
        if (!cachedDetails) {
          cachedDetails = await readCachedTechnicianJob(
            cacheScope,
            cacheKey,
            requestedJobId
          );
        }

        if (cachedDetails) {
          setJob(cachedDetails.job);
          setDataSource("cache");
          setCachedAt(cachedDetails.cachedAt);
          setError(null);
        } else {
          setJob(null);
          setDataSource(null);
          setCachedAt(null);
          setError(
            "You're offline or FieldOps is temporarily unavailable, and this job has no saved offline details. Reconnect and try again."
          );
        }
      } else {
        setJob(null);
        setDataSource(null);
        setCachedAt(null);
        setError(
          "Unable to load this job. Your access may have changed, or the job may no longer be available."
        );

        if (
          isAxiosError(loadError) &&
          [401, 403, 404].includes(loadError.response?.status ?? 0)
        ) {
          try {
            if (cacheScope) {
              await deleteOfflineRecord(
                cacheScope,
                "job-detail",
                requestedJobId
              );
            }

            if (cacheKey) {
              await AsyncStorage.removeItem(cacheKey);
            }
          } catch {
            // A cache cleanup failure must not hide the API error.
          }
        }
      }
    } finally {
      setLoading(false);
    }
  }, [jobId, user?.id, user?.tenant_id]);

  const refreshQueuedActions = useCallback(async () => {
    if (
      !jobId ||
      user?.id == null ||
      user.tenant_id == null
    ) {
      setQueuedActions([]);
      return;
    }

    try {
      const items = await getJobActionQueue({
        tenantId: String(user.tenant_id),
        technicianId: String(user.id)
      });

      setQueuedActions(
        items.filter(
          (item) =>
            item.jobId === String(jobId) &&
            item.status !== "synced"
        )
      );
    } catch {
      setQueuedActions([]);
    }
  }, [jobId, user?.id, user?.tenant_id]);

  useEffect(() => {
    void loadJob();
  }, [loadJob]);

  useEffect(() => {
    void refreshQueuedActions();
  }, [refreshQueuedActions]);

  useEffect(() => {
    if (
      assignedStatus !== "ASSIGNED" ||
      !Number.isFinite(assignedAtMs)
    ) {
      return;
    }

    const deadlineMs = assignedAtMs + 10 * 60 * 1000;

    setCurrentTimeMs(Date.now());

    if (Date.now() >= deadlineMs) {
      return;
    }

    const interval = setInterval(() => {
      const now = Date.now();
      setCurrentTimeMs(now);

      if (now >= deadlineMs) {
        clearInterval(interval);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [assignedStatus, assignedAtMs]);

  useEffect(() => {
    const trackingJob = job;
    const trackingUser = user;
    if (!trackingJob || trackingUser?.id == null || trackingUser.tenant_id == null) {
      setTrackingSummary({
        distanceToCustomerKm: null,
        estimatedMinutes: null,
        distanceTravelledKm: null,
        isWaitingForGps: false,
        isLoading: false
      });
      return;
    }

    const trackingJobId = String(trackingJob.id);
    const trackingJobStatus = trackingJob.status;
    const destinationLatitude = trackingJob.site_latitude;
    const destinationLongitude = trackingJob.site_longitude;
    const destinationAddress = trackingJob.site_address || trackingJob.address || trackingJob.location;
    const tenantId = trackingUser.tenant_id;

    const trackingStatuses = [
      "ACCEPTED", "EN_ROUTE", "ON_SITE", "IN_PROGRESS", "PAUSED", "COMPLETED"
    ];
    if (!trackingStatuses.includes(normalizeJobStatus(trackingJobStatus))) {
      setTrackingSummary({
        distanceToCustomerKm: null,
        estimatedMinutes: null,
        distanceTravelledKm: null,
        isWaitingForGps: false,
        isLoading: false
      });
      return;
    }

    let active = true;

    async function refreshTravelSummary() {
      setTrackingSummary((current) => ({
        ...current,
        isLoading: current.distanceToCustomerKm === null && current.estimatedMinutes === null
      }));

      const trackingRequest = apiClient.get<TechnicianTrackingApiSummary>(
        `/api/technician/jobs/${encodeURIComponent(trackingJobId)}/tracking-summary`
      ).then((response) => response.data).catch(() => null);

      const availabilityRequest = getTechnicianAvailabilityLocation(tenantId)
        .catch(() => null);

      const [trackingData, availability] = await Promise.all([
        trackingRequest,
        availabilityRequest
      ]);

      let origin: Coordinate | null = trackingData &&
        trackingData.technician_latitude != null &&
        trackingData.technician_longitude != null &&
        Number.isFinite(trackingData.technician_latitude) &&
        Number.isFinite(trackingData.technician_longitude)
        ? { latitude: Number(trackingData.technician_latitude), longitude: Number(trackingData.technician_longitude) }
        : availability &&
        Number.isFinite(availability.latitude) && Number.isFinite(availability.longitude)
        ? { latitude: Number(availability.latitude), longitude: Number(availability.longitude) }
        : null;

      if (!isValidCoordinate(origin)) {
        try {
          const permission = await Location.getForegroundPermissionsAsync();
          if (permission.status === "granted") {
            const lastKnown = await Location.getLastKnownPositionAsync({
              maxAge: 120_000,
              requiredAccuracy: 1_000
            });
            if (lastKnown) {
              origin = {
                latitude: lastKnown.coords.latitude,
                longitude: lastKnown.coords.longitude
              };
            } else {
              const position = await Promise.race([
                Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Low }),
                new Promise<never>((_, reject) => setTimeout(() => reject(new Error("Location request timed out")), 6_000))
              ]);
              origin = {
                latitude: position.coords.latitude,
                longitude: position.coords.longitude
              };
            }
          }
        } catch {
          origin = null;
        }
      }

      let destination: Coordinate | null = null;
      const savedDestination = {
        latitude: Number(destinationLatitude),
        longitude: Number(destinationLongitude)
      };
      if (isValidCoordinate(savedDestination)) {
        destination = savedDestination;
      } else {
        if (destinationAddress) {
          try {
            const matches = await Location.geocodeAsync(destinationAddress);
            if (matches[0]) {
              destination = {
                latitude: matches[0].latitude,
                longitude: matches[0].longitude
              };
            }
          } catch {
            destination = null;
          }
        }
      }

      let distanceToCustomerKm: number | null = null;
      let estimatedMinutes: number | null = null;
      if (isValidCoordinate(origin) && isValidCoordinate(destination)) {
        try {
          const routeResponse = await apiClient.get<OlaRouteSummary>(
            "/api/v1/gps/route",
            {
              params: {
                origin_lat: origin.latitude,
                origin_lng: origin.longitude,
                dest_lat: destination.latitude,
                dest_lng: destination.longitude
              }
            }
          );
          const route = routeResponse.data;
          if (Number.isFinite(route.distance_meters) && route.distance_meters > 0) {
            distanceToCustomerKm = route.distance_meters / 1000;
          }
          const routeSeconds = route.duration_in_traffic_seconds ?? route.duration_seconds;
          if (Number.isFinite(routeSeconds) && routeSeconds >= 0) {
            estimatedMinutes = Math.max(1, Math.round(routeSeconds / 60));
          }
        } catch {
          // Keep the displayed distance and ETA unavailable when road routing fails.
        }
      }

      const normalizedCurrentStatus = normalizeJobStatus(trackingJobStatus);
      const distanceTravelledKm = trackingData?.has_route_data
        ? trackingData.distance_travelled_km ?? null
        : normalizedCurrentStatus === "ACCEPTED" ? 0 : null;

      if (active) {
        setTrackingSummary({
          distanceToCustomerKm,
          estimatedMinutes,
          distanceTravelledKm,
          isWaitingForGps: Boolean(trackingData && !trackingData.has_route_data && normalizedCurrentStatus !== "ACCEPTED"),
          isLoading: false
        });
      }
    }

    void refreshTravelSummary();
    const interval = setInterval(() => void refreshTravelSummary(), 30_000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [
    job?.id,
    job?.status,
    job?.site_latitude,
    job?.site_longitude,
    job?.site_address,
    job?.address,
    job?.location,
    user?.id,
    user?.tenant_id
  ]);

  useEffect(() => {
    if (!job?.on_site_at || !["ON_SITE", "IN_PROGRESS", "PAUSED", "COMPLETED"].includes(assignedStatus)) return;
    const interval = setInterval(() => setTrackingClock(Date.now()), 60_000);
    return () => clearInterval(interval);
  }, [assignedStatus, job?.on_site_at]);


  async function queueOfflineJobAction(
    action: QueueableTechnicianJobAction
  ) {
    if (
      !job ||
      activeAction ||
      user?.id == null ||
      user.tenant_id == null
    ) {
      Alert.alert(
        "Cannot save action",
        "A valid technician session and job are required."
      );
      return;
    }

    setActiveAction(action);
    setError(null);

    try {
      await enqueueJobAction({
        tenantId: String(user.tenant_id),
        technicianId: String(user.id),
        jobId: job.id,
        action
      });

      await refreshQueuedActions();

      Alert.alert(
        "Action saved offline",
        `Your ${action.replace(/-/g, " ")} action is saved on this device and is pending synchronization. The server has not yet confirmed a status change.`
      );
    } catch (queueError: unknown) {
      setError(
        queueError instanceof Error
          ? queueError.message
          : "Unable to save the job action offline."
      );
    } finally {
      setActiveAction(null);
    }
  }

  async function handleAction(action: TechnicianJobAction) {
    if (!job || activeAction) {
      return;
    }

    if (action === "reject") {
      if (isOffline || dataSource !== "server") {
        Alert.alert(
          "Connection required",
          "Reconnect and refresh the job before rejecting it."
        );
        return;
      }

      setRejectionReason("");
      setIsRejectModalVisible(true);
      setError(null);
      return;
    }

    if (action === "complete") {
      if (isOffline || dataSource !== "server") {
        Alert.alert(
          "Connection required",
          "Reconnect and refresh the job before completing it."
        );
        return;
      }

      router.push({
        pathname: "/(app)/jobs/[jobId]/completion",
        params: { jobId: String(job.id) }
      });
      return;
    }

    if (isOffline) {
      await queueOfflineJobAction(action);
      return;
    }

    if (dataSource !== "server") {
      Alert.alert(
        "Reconnect to update this job",
        "These saved details may be outdated. Reconnect and refresh the job before submitting an action."
      );
      return;
    }

    await submitJobAction(action);
  }

  async function submitJobAction(
    action: TechnicianJobAction,
    payload: { reason?: string } = {}
  ) {
    if (!job || activeAction) {
      return;
    }

    if (
      isOffline &&
      (action === "reject" || action === "complete")
    ) {
      Alert.alert(
        "Connection required",
        "Reconnect and refresh the job before submitting this action."
      );
      return;
    }

    if (dataSource !== "server") {
      Alert.alert(
        "Reconnect to update this job",
        "These are saved offline details and may be outdated. Reconnect and refresh the job before submitting an action."
      );
      return;
    }

    setActiveAction(action);
    setError(null);

    let gpsWarning = false;

    try {
      const response = await performTechnicianJobAction(
        job.id,
        action,
        payload
      );

      if (action === "start" || action === "on-site") {
        if (user?.id == null || user.tenant_id == null) {
          gpsWarning = true;
        } else {
          try {
            await setActiveGpsJob(job.id);
          } catch {
            gpsWarning = true;
          }
        }
      }

      if (action === "reject") {
        setIsRejectModalVisible(false);
        setJob(null);
        router.replace("/(app)/jobs");

        Alert.alert(
          "Job rejected",
          "This job has been removed from your active jobs."
        );
        return;
      }

      if (response.status) {
        setJob((currentJob) =>
          currentJob
            ? { ...currentJob, status: response.status! }
            : currentJob
        );
      }

      await loadJob();

      if (
        ["start", "en-route", "en_route", "enroute"].includes(action)
      ) {
        router.push({
          pathname: "/(app)/jobs/[jobId]/live-map",
          params: { jobId: String(job.id) }
        });
        return;
      }

      Alert.alert(
        "Job updated",
        gpsWarning
          ? "Your status was updated, but your location could not be sent. Check location permission and connection."
          : "The action was submitted to FieldOps."
      );
    } catch (actionError: unknown) {
      if (canUseCachedJobAfterError(actionError)) {
        setDataSource("cache");
      }

      setError(
        action === "start" && isAxiosError(actionError) &&
          actionError.response?.status === 409
          ? "Another job is already in progress. Complete it before starting a new job."
          : "The job action could not be confirmed by the server. Refresh the job before trying again."
      );
    } finally {
      setActiveAction(null);
    }
  }

 

  if (loading) {
    return <LoadingState label="Loading job details..." variant="detail" />;
  }

  if (error && !job) {
    return (
      <ErrorState
        title="Job details unavailable"
        message={error}
        onRetry={() => void loadJob()}
      />
    );
  }

  if (!job) {
    return (
      <ErrorState
        title="Job not found"
        message="This job is unavailable to your account."
        onRetry={() => void loadJob()}
      />
    );
  }

  const canRejectJob =
    assignedStatus === "AWAITING_ACCEPTANCE" ||
    assignedStatus === "ASSIGNED" ||
    assignedStatus === "ACTIVE";

  const availableActions = getJobActionOptions(job.status).filter(
    ({ action }) => action !== "reject" || canRejectJob
  );
  const showTravelSummary = [
    "ACCEPTED", "EN_ROUTE", "ON_SITE", "IN_PROGRESS", "PAUSED", "COMPLETED"
  ].includes(assignedStatus);
  const showLiveMapAction = ["EN_ROUTE", "ON_SITE", "IN_PROGRESS", "PAUSED"].includes(assignedStatus);
  const shimmerButtonCount = Number(showLiveMapAction) +
    availableActions.filter(({ action }) => action !== "reject").length;

  const isUrgent = job.priority?.toUpperCase() === "URGENT";

  const statusStyle =
    assignedStatus === "COMPLETED"
      ? styles.statusCompleted
      : assignedStatus === "ASSIGNED" ||
          assignedStatus === "AWAITING_ACCEPTANCE"
        ? styles.statusWaiting
        : styles.statusActive;

  const priorityStyle = isUrgent
    ? styles.priorityUrgent
    : styles.priorityNormal;

  const jobStages = [
    { label: "Assigned", icon: "briefcase-outline" as const },
    { label: "Accepted", icon: "paper-plane-outline" as const },
    { label: "On the way", icon: "car-outline" as const },
    { label: "Arrived", icon: "location-outline" as const },
    { label: "Working", icon: "construct-outline" as const },
    { label: "Completed", icon: "checkmark-done-outline" as const }
  ];
  const currentStageIndex =
    assignedStatus === "COMPLETED" ? 5
      : assignedStatus === "IN_PROGRESS" || assignedStatus === "PAUSED" ? 4
        : assignedStatus === "ON_SITE" ? 3
          : assignedStatus === "EN_ROUTE" ? 2
            : assignedStatus === "ACCEPTED" ? 1
              : 0;

  return (
    <View style={styles.screen}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        {/* Green branded job header */}
        <LinearGradient
          colors={["#063D32", "#087A57", "#10A875"]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={styles.hero}
        >
          <View style={styles.headerRow}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Go back"
              onPress={() => router.replace(openedFromHistory ? "/(app)/history" : "/(app)/jobs")}
              style={({ pressed }) => [
                styles.backButton,
                pressed && styles.pressed
              ]}
            >
              <Ionicons
                name="arrow-back"
                size={23}
                color="#FFFFFF"
              />
            </Pressable>

            <View style={styles.headerReference}>
              <Text style={styles.headerEyebrow}>
                FIELD SERVICE
              </Text>

              <Text style={styles.headerJobNumber}>
                JOB #{job.job_number ?? String(job.id)}
              </Text>
            </View>

            <View style={styles.headerDecoration}>
              <Ionicons
                name="construct-outline"
                size={25}
                color="#A8E6C8"
              />
            </View>
          </View>

          <Text style={styles.jobTitle}>
            {job.title || "Service job"}
          </Text>

          <View style={styles.headerBottomRow}>
            <View style={[styles.statusBadge, statusStyle]}>
              <View style={styles.statusDot} />

              <Text style={styles.statusText}>
                {getJobStatusLabel(job.status)}
              </Text>
            </View>

            {job.priority ? (
              <View
                style={[
                  styles.priorityBadge,
                  priorityStyle
                ]}
              >
                <Ionicons
                  name="alert-circle"
                  size={15}
                  color={isUrgent ? "#C62836" : "#087653"}
                />

                <Text
                  style={[
                    styles.priorityText,
                    isUrgent
                      ? styles.priorityTextUrgent
                      : styles.priorityTextNormal
                  ]}
                >
                  {job.priority.toUpperCase()}
                </Text>
              </View>
            ) : null}
          </View>
        </LinearGradient>
        {queuedActions.length > 0 ? (
          <View style={styles.pendingActionBanner}>
            <Text style={styles.pendingActionTitle}>
              Pending job actions
            </Text>

            <Text style={styles.pendingActionText}>
              These actions are saved locally and have not all been
              confirmed by the server.
            </Text>

            {queuedActions.map((item) => (
              <Text
                key={item.id}
                style={styles.pendingActionDetail}
              >
                {item.action.replace(/-/g, " ")} —{" "}
                {item.status.toUpperCase()}
                {item.lastError ? `: ${item.lastError}` : ""}
              </Text>
            ))}
          </View>
        ) : null}
        {dataSource === "cache" ? (
          <View style={styles.offlineBanner}>
            <Ionicons
              name="cloud-offline-outline"
              size={23}
              color="#92400E"
            />

            <View style={styles.offlineBannerContent}>
              <Text style={styles.offlineBannerTitle}>
                Saved offline details — may be outdated
              </Text>

              <Text style={styles.offlineBannerText}>
                {formatCachedTimestamp(cachedAt)} Reconnect and refresh to confirm the current job status. Job actions are disabled until the server confirms this job.
              </Text>
            </View>
          </View>
        ) : null}

        <View style={styles.progressCard}>
          <View style={styles.progressHeading}>
            <View style={styles.progressIcon}>
              <Ionicons name="navigate-outline" size={21} color="#087653" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.progressTitle}>Job progress</Text>
              <Text style={styles.progressSubtitle}>
                {assignedStatus === "COMPLETED"
                  ? "This service job is complete"
                  : `Current stage · ${getJobStatusLabel(job.status)}`}
              </Text>
            </View>
          </View>
          <View style={styles.progressSteps}>
            {jobStages.map((stage, index) => {
              const isDone = index < currentStageIndex || assignedStatus === "COMPLETED";
              const isCurrent = index === currentStageIndex && assignedStatus !== "COMPLETED";
              return (
                <View key={stage.label} style={styles.progressStep}>
                  <View style={styles.progressNodeRow}>
                    {index > 0 ? (
                      <View style={[styles.progressConnector, index <= currentStageIndex && styles.progressConnectorDone]} />
                    ) : null}
                    <View style={[
                      styles.progressNode,
                      isDone && styles.progressNodeDone,
                      isCurrent && styles.progressNodeCurrent
                    ]}>
                      <Ionicons
                        name={isDone ? "checkmark" : stage.icon}
                        size={13}
                        color={isDone || isCurrent ? "#FFFFFF" : "#92A49B"}
                      />
                    </View>
                    {index < jobStages.length - 1 ? (
                      <View style={[styles.progressConnector, index < currentStageIndex && styles.progressConnectorDone]} />
                    ) : null}
                  </View>
                  <Text style={[
                    styles.progressStepLabel,
                    (isDone || isCurrent) && styles.progressStepLabelActive
                  ]} numberOfLines={2}>{stage.label}</Text>
                </View>
              );
            })}
          </View>
        </View>

        {showTravelSummary ? (
          <View style={styles.customerDetailsCard}>
            <View style={styles.customerDetailsAvatar}>
              <Text style={styles.customerDetailsInitials}>{getCustomerInitials(job.customer_name)}</Text>
            </View>
            <View style={styles.customerDetailsInfo}>
              <Text style={styles.customerDetailsEyebrow}>CUSTOMER</Text>
              <Text style={styles.customerDetailsName} numberOfLines={1}>
                {job.customer_name || "Customer"}
              </Text>
              <Text style={styles.customerDetailsPhone} numberOfLines={1}>
                {job.contact_number || "Phone number unavailable"}
              </Text>
            </View>
            <View style={styles.customerDetailsActions}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Call customer"
                disabled={!job.contact_number}
                onPress={() => {
                  const phone = job.contact_number?.replace(/[^\d+]/g, "");
                  if (phone) void Linking.openURL(`tel:${phone}`).catch(() => Alert.alert("Call unavailable", "This device could not open the phone app."));
                }}
                style={({ pressed }) => [styles.customerDetailsAction, !job.contact_number && styles.customerDetailsActionDisabled, pressed && styles.pressed]}
              >
                <Ionicons name="call-outline" size={18} color="#087653" />
                <Text style={styles.customerDetailsActionLabel}>Call</Text>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Chat with customer"
                onPress={() => router.push({ pathname: "/(app)/jobs/[jobId]/chat", params: { jobId: String(job.id) } } as never)}
                style={({ pressed }) => [styles.customerDetailsAction, pressed && styles.pressed]}
              >
                <Ionicons name="chatbubble-ellipses-outline" size={18} color="#087653" />
                <Text style={styles.customerDetailsActionLabel}>Chat</Text>
              </Pressable>
            </View>
          </View>
        ) : null}

        {showTravelSummary ? (
          <View style={styles.travelMetricsCard}>
            <View style={styles.travelMetricsHeading}>
              <View style={styles.travelMetricsIcon}>
                <Ionicons name="navigate-outline" size={17} color="#087653" />
              </View>
              <View>
                <Text style={styles.travelMetricsTitle}>Travel & timing</Text>
                <Text style={styles.travelMetricsSubtitle}>Updates while this job is active</Text>
              </View>
            </View>
            <View style={styles.travelMetricGrid}>
              <View style={styles.travelMetric}>
                <Ionicons name="car-outline" size={18} color="#087653" />
                <Text style={styles.travelMetricLabel}>To customer</Text>
                <Text style={styles.travelMetricValue} numberOfLines={1}>
                  {trackingSummary.distanceToCustomerKm !== null
                    ? `${trackingSummary.distanceToCustomerKm.toFixed(1)} km`
                    : trackingSummary.isLoading ? "Calculating…" : "Unavailable"}
                </Text>
                <Text style={styles.travelMetricHint}>Road distance</Text>
              </View>
              <View style={styles.travelMetricDivider} />
              <View style={styles.travelMetric}>
                <Ionicons name="time-outline" size={18} color="#087653" />
                <Text style={styles.travelMetricLabel}>Estimated arrival</Text>
                <Text style={styles.travelMetricValue} numberOfLines={1}>
                  {trackingSummary.estimatedMinutes !== null
                    ? `${trackingSummary.estimatedMinutes} min`
                    : trackingSummary.isLoading ? "Calculating…" : "Unavailable"}
                </Text>
                <Text style={styles.travelMetricHint}>Live route estimate</Text>
              </View>
              <View style={styles.travelMetricDivider} />
              <View style={styles.travelMetric}>
                <Ionicons name="navigate-outline" size={18} color="#087653" />
                <Text style={styles.travelMetricLabel}>Travelled</Text>
                <Text style={styles.travelMetricValue} numberOfLines={1}>
                  {trackingSummary.distanceTravelledKm !== null
                    ? `${trackingSummary.distanceTravelledKm.toFixed(1)} km`
                    : trackingSummary.isWaitingForGps ? "Waiting for GPS" : "Unavailable"}
                </Text>
                <Text style={styles.travelMetricHint}>From GPS route history</Text>
              </View>
              <View style={styles.travelMetricDivider} />
              <View style={styles.travelMetric}>
                <Ionicons name="hourglass-outline" size={18} color="#087653" />
                <Text style={styles.travelMetricLabel}>Time on site</Text>
                <Text style={styles.travelMetricValue} numberOfLines={1}>
                  {formatOnsiteDuration(job.on_site_at, trackingClock, job.completed_at)}
                </Text>
                <Text style={styles.travelMetricHint}>
                  {job.on_site_at ? "Since arrival" : "Starts when you arrive"}
                </Text>
              </View>
            </View>
          </View>
        ) : null}

        {/* Job information */}
        <View style={styles.sectionHeading}>
          <View>
            <Text style={styles.sectionTitle}>
              Service details
            </Text>

            <Text style={styles.sectionSubtitle}>
              Customer, appointment and work order
            </Text>
          </View>

          <View style={styles.sectionIcon}>
            <Ionicons
              name="document-text-outline"
              size={22}
              color="#087653"
            />
          </View>
        </View>

        <View style={styles.detailsCard}>
          {job.service_type ? (
            <DetailRow
              icon="construct-outline"
              label="Service type"
              value={job.service_type}
              iconColor="#8756C8"
              iconBackground="#F2EAFF"
            />
          ) : null}

          {job.address ? (
            <DetailRow
              icon="location-outline"
              label="Service location"
              value={job.address}
              iconColor="#E16A4B"
              iconBackground="#FFF0E9"
            />
          ) : null}

          {job.preferred_service_date || job.scheduled_at ? (
            <DetailRow
              icon="calendar-outline"
              label="Scheduled appointment"
              value={formatPreferredSchedule(
                job.preferred_service_date || job.scheduled_at,
                job.preferred_service_time
              )}
              iconColor="#C08A13"
              iconBackground="#FFF6D9"
            />
          ) : null}

          {job.description ? (
            <View style={styles.descriptionSection}>
              <View style={styles.descriptionHeading}>
                <Ionicons name="reader-outline" size={19} color="#3973D6" />

                <Text style={styles.detailLabel}>
                  Description
                </Text>
              </View>

              <Text style={styles.descriptionText}>
                {job.description}
              </Text>
            </View>
          ) : null}

          {!job.address &&
          !job.scheduled_at &&
          !job.preferred_service_date &&
          !job.service_type &&
          !job.description ? (
            <Text style={styles.emptyDetails}>
              No additional job information is available.
            </Text>
          ) : null}
        </View>

        {/* Acceptance timer */}
        {assignedStatus === "ASSIGNED" ? (
          <View
            style={[
              styles.timerCard,
              acceptanceExpired && styles.timerCardExpired
            ]}
          >
            <View style={styles.timerIcon}>
              <Ionicons
                name="time-outline"
                size={25}
                color={acceptanceExpired ? "#B42332" : "#087653"}
              />
            </View>

            <View style={styles.timerContent}>
              <Text
                style={[
                  styles.timerTitle,
                  acceptanceExpired && styles.expiredText
                ]}
              >
                TIME TO ACCEPT
              </Text>

              <Text
                style={[
                  styles.timerValue,
                  acceptanceExpired && styles.expiredText
                ]}
              >
                {acceptanceRemainingSeconds === null
                  ? "--:--"
                  : acceptanceExpired
                    ? "EXPIRED"
                    : `${String(
                        Math.floor(acceptanceRemainingSeconds / 60)
                      ).padStart(2, "0")}:${String(
                        acceptanceRemainingSeconds % 60
                      ).padStart(2, "0")}`}
              </Text>

              <Text
                style={[
                  styles.timerMessage,
                  acceptanceExpired && styles.expiredText
                ]}
              >
                {acceptanceRemainingSeconds === null
                  ? "Assignment time unavailable. Refresh the job."
                  : acceptanceExpired
                    ? "The acceptance window has expired."
                    : "Accept the job before time runs out."}
              </Text>
            </View>
          </View>
        ) : null}


        {/* Error message */}
        {error ? (
          <View style={styles.errorCard}>
            <Ionicons
              name="alert-circle-outline"
              size={22}
              color="#B42332"
            />

            <View style={styles.errorContent}>
              <Text
                accessibilityRole="alert"
                style={styles.errorText}
              >
                {error}
              </Text>

              <Pressable
                accessibilityRole="button"
                onPress={() => void loadJob()}
              >
                <Text style={styles.retryText}>
                  Refresh job details
                </Text>
              </Pressable>
            </View>
          </View>
        ) : null}

        {/* Rejection form */}
        {isRejectModalVisible ? (
          <View style={styles.rejectForm}>
            <View style={styles.rejectHeading}>
              <View style={styles.rejectIcon}>
                <Ionicons
                  name="close-circle-outline"
                  size={23}
                  color="#B42332"
                />
              </View>

              <View style={styles.rejectHeadingText}>
                <Text style={styles.rejectTitle}>
                  Reject this job
                </Text>

                <Text style={styles.rejectSubtitle}>
                  Explain why you cannot accept this assignment.
                </Text>
              </View>
            </View>

            <TextInput
              accessibilityLabel="Job rejection reason"
              value={rejectionReason}
              onChangeText={setRejectionReason}
              placeholder="Enter your reason (at least 10 characters)"
              placeholderTextColor="#91A09A"
              multiline
              maxLength={1000}
              textAlignVertical="top"
              style={styles.rejectionInput}
            />

            <Text style={styles.characterHint}>
              {rejectionReason.trim().length}/1000 characters
            </Text>

            <Pressable
              accessibilityRole="button"
              disabled={activeAction !== null}
              onPress={() => {
                const reason = rejectionReason.trim();

                if (reason.length < 10) {
                  Alert.alert(
                    "Reason required",
                    "Please enter at least 10 characters."
                  );
                  return;
                }

                setIsRejectModalVisible(false);
                void submitJobAction("reject", { reason });
              }}
              style={({ pressed }) => [
                styles.confirmRejectButton,
                pressed && styles.pressed,
                activeAction !== null && styles.buttonDisabled
              ]}
            >
              {activeAction === "reject" ? (
                <ActivityIndicator color="#FFFFFF" />
              ) : (
                <Text style={styles.actionButtonText}>
                  Confirm Rejection
                </Text>
              )}
            </Pressable>

            <Pressable
              accessibilityRole="button"
              onPress={() => setIsRejectModalVisible(false)}
              style={styles.cancelButton}
            >
              <Text style={styles.cancelButtonText}>
                Cancel
              </Text>
            </Pressable>
          </View>
        ) : null}

        {/* Job actions are only relevant when opened from My Jobs. */}
        {!openedFromHistory ? <View style={styles.actionsSection}>
          <Text style={styles.sectionTitle}>
            Available actions
          </Text>

          <Text style={styles.sectionSubtitle}>
            Update the job as you complete each stage.
          </Text>

          {otherStartedJob ? (
            <View style={styles.singleJobNotice}>
              <Ionicons name="lock-closed-outline" size={19} color="#9A5B08" />
              <Text style={styles.singleJobNoticeText}>
                Job #{otherStartedJob.job_number ?? otherStartedJob.id} is already active. Complete it before starting another job.
              </Text>
            </View>
          ) : null}

          {showLiveMapAction ? (
            <Pressable
              key="live-map"
              accessibilityRole="button"
              accessibilityLabel="Open live route map"
              disabled={activeAction !== null || dataSource !== "server"}
              onPress={() => {
                router.push({
                  pathname: "/(app)/jobs/[jobId]/live-map",
                  params: { jobId: String(job.id) }
                });
              }}
              style={({ pressed }) => [
                styles.actionButton,
                styles.gradientButtonShell,
                pressed && styles.gradientButtonPressed,
                (activeAction !== null || dataSource !== "server") &&
                  styles.buttonDisabled
              ]}
            >
              {() => (
                <>
                  <LinearGradient
                    colors={["#07543B", "#078A4D", "#26A96C"]}
                    start={{ x: 0, y: 0 }}
                    end={{ x: 1, y: 0 }}
                    style={styles.gradientButtonContent}
                  >
                    <Ionicons name="map-outline" size={22} color="#FFFFFF" />
                    <Text style={styles.actionButtonText}>Live Map</Text>
                    <Ionicons name="arrow-forward" size={19} color="#FFFFFF" />
                  </LinearGradient>
                  <SilverTouchShimmer
                    order={0}
                    total={shimmerButtonCount}
                  />
                </>
              )}
            </Pressable>
          ) : null}

          {availableActions.length > 0 ? (
            availableActions.map(({ action, label }, actionIndex) => {
              const actionIcons: Record<string, IconName> = {
                accept: "checkmark-circle-outline",
                reject: "close-circle-outline",
                "en-route": "navigate-outline",
                en_route: "navigate-outline",
                enroute: "navigate-outline",
                "on-site": "location-outline",
                on_site: "location-outline",
                complete: "checkmark-done-circle-outline"
              };

              const isReject = action === "reject";
              const isGradientAction = action !== "reject";
              const blockedByOtherStartedJob = action === "start" && otherStartedJob !== null;
              const canQueueOfflineAction =
                isOffline &&
                action !== "reject" &&
                action !== "complete";
              const offlineBlockedAction =
                isOffline &&
                (action === "reject" || action === "complete");
              const cannotUseCachedData =
                dataSource !== "server" &&
                !canQueueOfflineAction;

              return (
                <Pressable
                  key={action}
                  accessibilityRole="button"
                  disabled={
                    activeAction !== null ||
                    blockedByOtherStartedJob ||
                    cannotUseCachedData ||
                    offlineBlockedAction ||
                    (action === "accept" && acceptanceExpired)
                  }
                  onPress={() => void handleAction(action)}
                  style={({ pressed }) => [
                    styles.actionButton,
                    isReject && styles.rejectButton,
                    action === "complete" && styles.completeButton,
                    isGradientAction && styles.gradientButtonShell,
                    pressed && (isGradientAction ? styles.gradientButtonPressed : styles.pressed),
                    (activeAction !== null ||
                      cannotUseCachedData ||
                      offlineBlockedAction) &&
                      styles.buttonDisabled,
                    action === "accept" &&
                      acceptanceExpired &&
                      styles.buttonDisabled
                  ]}
                >
                  {() => {
                    const content = activeAction === action ? (
                      <ActivityIndicator color="#FFFFFF" />
                    ) : (
                      <>
                        <Ionicons name={actionIcons[action] ?? "construct-outline"} size={22} color="#FFFFFF" />
                        <Text style={styles.actionButtonText}>{label}</Text>
                        <Ionicons name="arrow-forward" size={19} color="#FFFFFF" />
                      </>
                    );
                    return isGradientAction ? (
                      <>
                        <LinearGradient
                          colors={["#07543B", "#078A4D", "#26A96C"]}
                          start={{ x: 0, y: 0 }}
                          end={{ x: 1, y: 0 }}
                          style={styles.gradientButtonContent}
                        >{content}</LinearGradient>
                        <SilverTouchShimmer
                          order={Number(showLiveMapAction) + actionIndex}
                          total={shimmerButtonCount}
                        />
                      </>
                    ) : content;
                  }}
                </Pressable>
              );
            })
          ) : (
            <View style={styles.noActionsCard}>
              <Ionicons
                name="checkmark-circle-outline"
                size={25}
                color="#087653"
              />

              <Text style={styles.noActions}>
                No actions are available for this job status.
              </Text>
            </View>
          )}
        </View> : null}

        <Text style={styles.footerText}>
          FieldOps Commander · Technician workspace
        </Text>
      </ScrollView>
    </View>
  );
}

function formatSchedule(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  });
}

function formatPreferredSchedule(
  dateValue?: string | null,
  timeValue?: string | null
): string {
  if (!dateValue) return "Not scheduled";
  const date = new Date(dateValue);
  const formattedDate = Number.isNaN(date.getTime())
    ? dateValue
    : date.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric"
      });
  return [formattedDate, timeValue].filter(Boolean).join(" · ");
}

const SILVER_SWEEP_DURATION_MS = 2_600;

function SilverTouchShimmer({
  order,
  total
}: {
  order: number;
  total: number;
}) {
  const [progress] = useState(() => new Animated.Value(0));
  const [width, setWidth] = useState(0);

  useEffect(() => {
    if (total === 0 || width === 0) return;
    progress.setValue(0);
    const animation = Animated.sequence([
      Animated.delay(1_600 + order * SILVER_SWEEP_DURATION_MS),
      Animated.loop(
        Animated.sequence([
          Animated.timing(progress, {
            toValue: 1,
            duration: SILVER_SWEEP_DURATION_MS,
            easing: Easing.inOut(Easing.cubic),
            useNativeDriver: true
          }),
          Animated.timing(progress, {
            toValue: 0,
            duration: 0,
            useNativeDriver: true
          }),
          Animated.delay(Math.max(0, total - 1) * SILVER_SWEEP_DURATION_MS)
        ]),
        { iterations: -1 }
      )
    ]);
    animation.start();
    return () => animation.stop();
  }, [order, progress, total, width]);

  const translateX = progress.interpolate({
    inputRange: [0, 1],
    outputRange: [-Math.max(width, 1) * 0.65, Math.max(width, 1) * 1.4]
  });

  return (
    <View
      pointerEvents="none"
      onLayout={(event) => setWidth(event.nativeEvent.layout.width)}
      style={styles.silverShimmerClip}
    >
      {width > 0 ? (
        <Animated.View
          style={[
            styles.silverShimmerBand,
            { width: width * 0.48, transform: [{ translateX }, { rotate: "18deg" }] }
          ]}
        >
          <LinearGradient
            colors={[
              "rgba(255,255,255,0.02)",
              "rgba(232,242,248,0.24)",
              "rgba(255,255,255,0.82)",
              "rgba(220,235,244,0.28)",
              "rgba(255,255,255,0.02)"
            ]}
            locations={[0, 0.28, 0.5, 0.72, 1]}
            start={{ x: 0, y: 0.5 }}
            end={{ x: 1, y: 0.5 }}
            style={styles.silverShimmerGradient}
          />
        </Animated.View>
      ) : null}
    </View>
  );
}

interface DetailRowProps {
  icon: IconName;
  label: string;
  value: string;
  iconColor?: string;
  iconBackground?: string;
}

function DetailRow({
  icon,
  label,
  value,
  iconColor = "#0A8A62",
  iconBackground = "#EAF7F0"
}: DetailRowProps) {
  return (
    <View style={styles.detailRow}>
      <View style={[styles.detailIcon, { backgroundColor: iconBackground }]}>
        <Ionicons
          name={icon}
          size={18}
          color={iconColor}
        />
      </View>

      <View style={styles.detailContent}>
        <Text style={styles.detailLabel}>
          {label}
        </Text>

        <Text style={styles.detailValue}>
          {value}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#F3F8F6"
  },

  scroll: {
    flex: 1
  },

  content: {
    paddingBottom: 30
  },

  /* Header */

  hero: {
    overflow: "hidden",
    paddingHorizontal: 20,
    paddingTop: 22,
    paddingBottom: 25,
    borderBottomLeftRadius: 27,
    borderBottomRightRadius: 27
  },

  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 24
  },

  backButton: {
    width: 43,
    height: 43,
    borderRadius: 15,
    backgroundColor: "rgba(255,255,255,0.18)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.20)",
    alignItems: "center",
    justifyContent: "center"
  },

  headerReference: {
    flex: 1,
    marginLeft: 12
  },

  headerEyebrow: {
    color: "#A8DCC5",
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 1.5
  },

  headerJobNumber: {
    color: "#FFFFFF",
    fontSize: 16,
    fontWeight: "800",
    marginTop: 3
  },

  headerDecoration: {
    width: 43,
    height: 43,
    borderRadius: 15,
    backgroundColor: "rgba(255,255,255,0.16)",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.15)",
    alignItems: "center",
    justifyContent: "center"
  },

  jobTitle: {
    color: "#FFFFFF",
    fontSize: 29,
    lineHeight: 36,
    fontWeight: "800",
    letterSpacing: -0.5
  },

  headerBottomRow: {
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 9,
    marginTop: 16
  },

  statusBadge: {
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    borderRadius: 20,
    paddingHorizontal: 12,
    paddingVertical: 9
  },

  statusActive: {
    backgroundColor: "#D9F5E6"
  },

  statusWaiting: {
    backgroundColor: "#FFF0CB"
  },

  statusCompleted: {
    backgroundColor: "#CFF4DF"
  },

  statusDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: "#087653"
  },

  statusText: {
    color: "#075C40",
    fontSize: 11,
    fontWeight: "800"
  },

  priorityBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    borderRadius: 20,
    paddingHorizontal: 11,
    paddingVertical: 9
  },

  priorityUrgent: {
    backgroundColor: "#FFE5E8"
  },

  priorityNormal: {
    backgroundColor: "#E4F4EB"
  },

  priorityText: {
    fontSize: 11,
    fontWeight: "800"
  },

  priorityTextUrgent: {
    color: "#B42332"
  },

  priorityTextNormal: {
    color: "#087653"
  },

  progressCard: {
    marginHorizontal: 15,
    marginTop: 18,
    padding: 16,
    backgroundColor: "#FBFFFD",
    borderRadius: 21,
    borderWidth: 1,
    borderColor: "#CFEBDD",
    shadowColor: "#087653",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.09,
    shadowRadius: 13,
    elevation: 3
  },

  progressHeading: {
    flexDirection: "row",
    alignItems: "center",
    gap: 11,
    marginBottom: 20
  },

  progressIcon: {
    width: 42,
    height: 42,
    borderRadius: 14,
    backgroundColor: "#DDF8EB",
    alignItems: "center",
    justifyContent: "center"
  },

  progressTitle: {
    color: "#16372A",
    fontSize: 16,
    fontWeight: "800"
  },

  progressSubtitle: {
    color: "#71847A",
    fontSize: 11,
    marginTop: 3
  },

  progressSteps: {
    flexDirection: "row",
    alignItems: "flex-start",
    marginHorizontal: -3
  },

  progressStep: {
    flex: 1,
    alignItems: "center"
  },

  progressNodeRow: {
    width: "100%",
    height: 30,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center"
  },

  progressNode: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: "#F1F5F3",
    borderWidth: 1,
    borderColor: "#DFE8E3",
    alignItems: "center",
    justifyContent: "center"
  },

  progressNodeDone: {
    backgroundColor: "#087653",
    borderColor: "#087653"
  },

  progressNodeCurrent: {
    backgroundColor: "#10A875",
    borderColor: "#B8EBD2",
    borderWidth: 3,
    elevation: 3
  },

  progressConnector: {
    flex: 1,
    height: 2,
    backgroundColor: "#E2EAE6"
  },

  progressConnectorDone: {
    backgroundColor: "#10A875"
  },

  progressStepLabel: {
    color: "#8A9A92",
    fontSize: 9,
    fontWeight: "700",
    textAlign: "center",
    marginTop: 7,
    minHeight: 24
  },

  progressStepLabelActive: {
    color: "#075C45"
  },

  travelMetricsCard: {
    marginHorizontal: 15,
    marginTop: 13,
    padding: 14,
    backgroundColor: "#F0F8F3",
    borderRadius: 19,
    borderWidth: 1,
    borderColor: "#D8EADF"
  },

  customerDetailsCard: {
    marginHorizontal: 15,
    marginTop: 13,
    padding: 11,
    minHeight: 76,
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
    backgroundColor: "#FFFFFF",
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "#DCEAE2",
    shadowColor: "#164E3B",
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.06,
    shadowRadius: 7,
    elevation: 2
  },

  customerDetailsAvatar: {
    width: 42,
    height: 42,
    flexShrink: 0,
    borderRadius: 21,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#075C45"
  },

  customerDetailsInitials: {
    color: "#FFFFFF",
    fontSize: 13,
    fontWeight: "800"
  },

  customerDetailsInfo: {
    flex: 1,
    minWidth: 0
  },

  customerDetailsEyebrow: {
    color: "#829188",
    fontSize: 8,
    fontWeight: "800",
    letterSpacing: 0.8
  },

  customerDetailsName: {
    color: "#17392B",
    fontSize: 13,
    fontWeight: "800",
    marginTop: 2
  },

  customerDetailsPhone: {
    color: "#64766C",
    fontSize: 10,
    fontWeight: "600",
    marginTop: 3
  },

  customerDetailsActions: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5
  },

  customerDetailsAction: {
    minWidth: 39,
    height: 47,
    paddingHorizontal: 4,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    gap: 2,
    backgroundColor: "#EAF5EF"
  },

  customerDetailsActionDisabled: {
    opacity: 0.45
  },

  customerDetailsActionLabel: {
    color: "#35614A",
    fontSize: 9,
    fontWeight: "700"
  },

  travelMetricsHeading: {
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
    marginBottom: 13
  },

  travelMetricsIcon: {
    width: 34,
    height: 34,
    borderRadius: 11,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#DDF1E5"
  },

  travelMetricsTitle: {
    color: "#17392B",
    fontSize: 14,
    fontWeight: "800"
  },

  travelMetricsSubtitle: {
    color: "#75877D",
    fontSize: 10,
    marginTop: 2
  },

  travelMetricGrid: {
    flexDirection: "row",
    alignItems: "stretch"
  },

  travelMetric: {
    flex: 1,
    minWidth: 0,
    alignItems: "flex-start",
    paddingHorizontal: 5,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: "#DCEAE1"
  },

  travelMetricDivider: {
    width: 1,
    backgroundColor: "#D9E7DE",
    marginTop: 10
  },

  travelMetricLabel: {
    minHeight: 26,
    color: "#74867C",
    fontSize: 9,
    lineHeight: 12,
    fontWeight: "600",
    marginTop: 6
  },

  travelMetricValue: {
    color: "#153B2B",
    fontSize: 12,
    lineHeight: 16,
    fontWeight: "800",
    marginTop: 2
  },

  travelMetricHint: {
    minHeight: 24,
    color: "#87968D",
    fontSize: 8,
    lineHeight: 11,
    marginTop: 4
  },

  pendingActionBanner: {
    marginHorizontal: 15,
    marginTop: 16,
    padding: 14,
    borderRadius: 16,
    backgroundColor: "#E5F6EC",
    borderWidth: 1,
    borderColor: "#BDE8CF"
  },

  pendingActionTitle: {
    color: "#075C40",
    fontSize: 14,
    fontWeight: "800"
  },

  pendingActionText: {
    color: "#426C57",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 5
  },

  pendingActionDetail: {
    color: "#075C40",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 7,
    textTransform: "capitalize"
  },

  offlineBanner: {
    marginHorizontal: 15,
    marginTop: 16,
    padding: 14,
    borderRadius: 16,
    backgroundColor: "#FFF4D7",
    borderWidth: 1,
    borderColor: "#F2D790",
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10
  },

  offlineBannerContent: {
    flex: 1
  },

  offlineBannerTitle: {
    color: "#92400E",
    fontSize: 13,
    lineHeight: 19,
    fontWeight: "800"
  },

  offlineBannerText: {
    color: "#854D0E",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 4
  },

  /* Section headings */

  sectionHeading: {
    marginTop: 19,
    marginBottom: 9,
    paddingHorizontal: 19,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between"
  },

  sectionTitle: {
    color: "#16372A",
    fontSize: 19,
    fontWeight: "800"
  },

  sectionSubtitle: {
    color: "#7B8C84",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 4
  },

  sectionIcon: {
    width: 43,
    height: 43,
    borderRadius: 14,
    backgroundColor: "#E2F4EA",
    alignItems: "center",
    justifyContent: "center"
  },

  /* Details card */

  detailsCard: {
    marginHorizontal: 15,
    paddingHorizontal: 12,
    paddingVertical: 2,
    backgroundColor: "#FFFFFF",
    borderRadius: 21,
    borderWidth: 1,
    borderColor: "#DCECE4",
    shadowColor: "#087653",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.075,
    shadowRadius: 12,
    elevation: 3
  },

  detailRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    paddingVertical: 9,
    gap: 10,
    borderBottomWidth: 1,
    borderBottomColor: "#EEF3F0"
  },

  detailIcon: {
    width: 34,
    height: 34,
    borderRadius: 12,
    backgroundColor: "#EAF6F0",
    alignItems: "center",
    justifyContent: "center"
  },

  detailContent: {
    flex: 1,
    paddingTop: 1
  },

  detailLabel: {
    color: "#75877D",
    fontSize: 10,
    lineHeight: 14,
    marginBottom: 2
  },

  detailValue: {
    color: "#18372B",
    fontSize: 13,
    lineHeight: 18,
    fontWeight: "600"
  },

  descriptionSection: {
    paddingVertical: 11
  },

  descriptionHeading: {
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
    marginBottom: 9
  },

  descriptionText: {
    color: "#42584D",
    fontSize: 13,
    lineHeight: 19
  },

  emptyDetails: {
    color: "#7A8B82",
    fontSize: 13,
    lineHeight: 20,
    paddingVertical: 17
  },

  /* Acceptance timer */

  timerCard: {
    marginHorizontal: 15,
    marginTop: 17,
    backgroundColor: "#E5F6EC",
    borderWidth: 1,
    borderColor: "#BDE8CF",
    borderRadius: 20,
    padding: 17,
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 13
  },

  timerCardExpired: {
    backgroundColor: "#FFF0F0",
    borderColor: "#F4C5C9"
  },

  timerIcon: {
    width: 46,
    height: 46,
    borderRadius: 15,
    backgroundColor: "#FFFFFF",
    alignItems: "center",
    justifyContent: "center"
  },

  timerContent: {
    flex: 1
  },

  timerTitle: {
    color: "#087653",
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 1.2
  },

  timerValue: {
    color: "#075C40",
    fontSize: 29,
    fontWeight: "900",
    fontVariant: ["tabular-nums"],
    marginTop: 5
  },

  timerMessage: {
    color: "#426C57",
    fontSize: 12,
    lineHeight: 19,
    marginTop: 3
  },

  expiredText: {
    color: "#B42332"
  },


  /* Error card */

  errorCard: {
    marginHorizontal: 15,
    marginTop: 16,
    padding: 14,
    borderRadius: 16,
    backgroundColor: "#FFF0F0",
    borderWidth: 1,
    borderColor: "#F4C5C9",
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10
  },

  errorContent: {
    flex: 1
  },

  errorText: {
    color: "#A61B2B",
    fontSize: 13,
    lineHeight: 20
  },

  retryText: {
    color: "#087653",
    fontSize: 13,
    fontWeight: "800",
    marginTop: 9
  },

  /* Rejection form */

  rejectForm: {
    marginHorizontal: 15,
    marginTop: 20,
    padding: 17,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#F2D1D4",
    borderRadius: 20
  },

  rejectHeading: {
    flexDirection: "row",
    alignItems: "center",
    gap: 11,
    marginBottom: 15
  },

  rejectIcon: {
    width: 43,
    height: 43,
    borderRadius: 14,
    backgroundColor: "#FFE9EB",
    alignItems: "center",
    justifyContent: "center"
  },

  rejectHeadingText: {
    flex: 1
  },

  rejectTitle: {
    color: "#92212B",
    fontSize: 17,
    fontWeight: "800"
  },

  rejectSubtitle: {
    color: "#8E7779",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 3
  },

  rejectionInput: {
    minHeight: 115,
    borderWidth: 1,
    borderColor: "#E2E8E4",
    borderRadius: 14,
    padding: 13,
    color: "#18372B",
    fontSize: 14,
    lineHeight: 21,
    backgroundColor: "#FAFCFB"
  },

  characterHint: {
    color: "#87968D",
    fontSize: 11,
    textAlign: "right",
    marginTop: 7,
    marginBottom: 12
  },

  confirmRejectButton: {
    minHeight: 52,
    backgroundColor: "#B42332",
    borderRadius: 15,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 15
  },

  cancelButton: {
    minHeight: 47,
    marginTop: 9,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#E0E7E2",
    alignItems: "center",
    justifyContent: "center"
  },

  cancelButtonText: {
    color: "#53675B",
    fontSize: 14,
    fontWeight: "700"
  },

  /* Job actions */

  actionsSection: {
    marginTop: 25,
    paddingHorizontal: 15
  },

  singleJobNotice: {
    marginTop: 12,
    padding: 12,
    borderRadius: 14,
    backgroundColor: "#FFF5DF",
    borderWidth: 1,
    borderColor: "#F2D89A",
    flexDirection: "row",
    alignItems: "center",
    gap: 9
  },

  singleJobNoticeText: {
    flex: 1,
    color: "#81500D",
    fontSize: 12,
    lineHeight: 18,
    fontWeight: "600"
  },

  actionButton: {
    minHeight: 59,
    marginTop: 12,
    paddingHorizontal: 17,
    borderRadius: 17,
    backgroundColor: "#087653",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 11
  },

  gradientButtonShell: {
    paddingHorizontal: 0,
    paddingVertical: 0,
    overflow: "hidden",
    backgroundColor: "transparent",
    borderWidth: 1,
    borderColor: "rgba(6,92,62,0.22)",
    elevation: 4,
    shadowColor: "#087653",
    shadowOffset: { width: 0, height: 5 },
    shadowOpacity: 0.22,
    shadowRadius: 9
  },

  gradientButtonContent: {
    flex: 1,
    minHeight: 59,
    paddingHorizontal: 17,
    borderRadius: 16,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 11
  },

  silverShimmerClip: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    borderRadius: 16,
    overflow: "hidden"
  },

  silverShimmerBand: {
    position: "absolute",
    top: -12,
    bottom: -12,
    left: 0
  },

  silverShimmerGradient: {
    flex: 1
  },

  gradientButtonPressed: {
    transform: [{ scale: 0.985 }],
    elevation: 7
  },

  rejectButton: {
    backgroundColor: "#B42332"
  },

  completeButton: {
    backgroundColor: "#064E3B"
  },

  actionButtonText: {
    flex: 1,
    color: "#FFFFFF",
    fontSize: 14,
    fontWeight: "800"
  },

  noActionsCard: {
    marginTop: 13,
    borderRadius: 17,
    padding: 17,
    backgroundColor: "#E5F6EC",
    flexDirection: "row",
    alignItems: "center",
    gap: 11
  },

  noActions: {
    flex: 1,
    color: "#426C57",
    fontSize: 13,
    lineHeight: 20
  },

  /* Shared */

  pressed: {
    opacity: 0.8
  },

  buttonDisabled: {
    opacity: 0.5
  },

  footerText: {
    color: "#91A098",
    fontSize: 11,
    textAlign: "center",
    marginTop: 27,
    marginBottom: 10
  }
});
