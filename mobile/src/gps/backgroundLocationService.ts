import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Crypto from "expo-crypto";
import {
  deleteOfflineRecord,
  getOfflineRecord,
  setOfflineRecord
} from "../offline/offlineStore";
import * as SecureStore from "expo-secure-store";
import * as Location from "expo-location";
import * as TaskManager from "expo-task-manager";

import { apiClient } from "../api/client";
import {
  sendTechnicianAvailabilityPing
} from "./gpsService";
import { logError, logEvent } from "../observability/logger";

const LOCATION_TASK_NAME = "fieldops-technician-background-location-v1";
const ACTIVE_CONTEXT_KEY = "fieldops:gps:active-context:v1";
const QUEUE_PREFIX = "fieldops:gps:pending:v1:";
const LOCATION_CONSENT_PREFIX = "fieldops:gps:consent:v1:";

const MAX_PENDING_PINGS = 1000;
const BATCH_SIZE = 100;
const GPS_QUEUE_RETENTION_MS = 30 * 24 * 60 * 60 * 1000;

const GPS_BATCH_COOLDOWN_PREFIX =
  "fieldops:gps:batch-cooldown:v1:";

const DEFAULT_GPS_BATCH_RETRY_DELAY_MS = 60_000;

const SECURE_STORE_KEY_PREFIX = "fieldops_secure_v1_";

async function getSecureStoreKey(
  logicalKey: string
): Promise<string> {
  const digest = await Crypto.digestStringAsync(
    Crypto.CryptoDigestAlgorithm.SHA256,
    logicalKey
  );

  return `${SECURE_STORE_KEY_PREFIX}${digest}`;
}

async function readProtectedValue(
  key: string
): Promise<string | null> {
  if (!(await SecureStore.isAvailableAsync())) {
    throw new Error("Secure storage is unavailable.");
  }

  const secureKey = await getSecureStoreKey(key);
  const protectedValue =
    await SecureStore.getItemAsync(secureKey);

  if (protectedValue !== null) {
    await AsyncStorage.removeItem(key).catch(
      () => undefined
    );

    return protectedValue;
  }

  // Migrate an existing plaintext value only after
  // secure storage has returned a valid result.
  const legacyValue = await AsyncStorage.getItem(key);

  if (legacyValue !== null) {
    await SecureStore.setItemAsync(
      secureKey,
      legacyValue
    );

    await AsyncStorage.removeItem(key).catch(
      () => undefined
    );

    return legacyValue;
  }

  return null;
}

async function writeProtectedValue(
  key: string,
  value: string
): Promise<void> {
  if (!(await SecureStore.isAvailableAsync())) {
    throw new Error("Secure storage is unavailable.");
  }

  const secureKey = await getSecureStoreKey(key);

  await SecureStore.setItemAsync(secureKey, value);

  // Keep the old logical key only for legacy-cache cleanup.
  await AsyncStorage.removeItem(key).catch(
    () => undefined
  );
}

async function deleteProtectedValue(
  key: string
): Promise<void> {
  if (await SecureStore.isAvailableAsync()) {
    const secureKey = await getSecureStoreKey(key);

    await SecureStore.deleteItemAsync(secureKey);
  }

  await AsyncStorage.removeItem(key).catch(
    () => undefined
  );
}

export interface TechnicianLocationIdentity {
  technicianId: string | number;
  tenantId: string | number;
}

interface TrackingContext {
  technicianId: string;
  tenantId: string;
  activeJobId?: string;
  pendingJobIds?: string[];
  trackingEnabled?: boolean;
}

interface PendingGpsPing {
  technician_id: string;
  job_id: string;
  latitude: number;
  longitude: number;
  timestamp: string;
  accuracy: number | null;
  altitude: number | null;
}

function isPendingGpsPing(
  value: unknown,
  context: TrackingContext,
  jobId: string
): value is PendingGpsPing {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const ping = value as Record<string, unknown>;

  const validMeasurement = (measurement: unknown): boolean =>
    measurement === null ||
    (typeof measurement === "number" &&
      Number.isFinite(measurement));

  return (
    ping.technician_id === context.technicianId &&
    ping.job_id === jobId &&
    typeof ping.latitude === "number" &&
    Number.isFinite(ping.latitude) &&
    ping.latitude >= -90 &&
    ping.latitude <= 90 &&
    typeof ping.longitude === "number" &&
    Number.isFinite(ping.longitude) &&
    ping.longitude >= -180 &&
    ping.longitude <= 180 &&
    typeof ping.timestamp === "string" &&
    Number.isFinite(Date.parse(ping.timestamp)) &&
    validMeasurement(ping.accuracy) &&
    validMeasurement(ping.altitude)
  );
}

interface GpsBatchResponse {
  total?: number;
  succeeded?: number;
  failed?: number;
  errors?: Array<{
    index?: number;
    reason?: string;
  }>;
}

let flushing = false;

function queueKey(
  context: TrackingContext,
  jobIdInput?: string
): string {
  const jobId = String(
    jobIdInput ?? context.activeJobId ?? ""
  ).trim();

  if (!jobId) {
    throw new Error("A job ID is required for the GPS queue.");
  }

  return (
    `${QUEUE_PREFIX}${encodeURIComponent(context.tenantId)}:` +
    `${encodeURIComponent(context.technicianId)}:` +
    `${encodeURIComponent(jobId)}`
  );
}

function locationConsentKey(
  identity: TechnicianLocationIdentity
): string {
  const technicianId = String(
    identity.technicianId ?? ""
  ).trim();

  const tenantId = String(
    identity.tenantId ?? ""
  ).trim();

  if (!technicianId || !tenantId) {
    throw new Error(
      "Technician and tenant IDs are required for location consent."
    );
  }

  return (
    `${LOCATION_CONSENT_PREFIX}` +
    `${encodeURIComponent(tenantId)}:` +
    `${encodeURIComponent(technicianId)}`
  );
}

export async function hasTechnicianLocationConsent(
  identity: TechnicianLocationIdentity
): Promise<boolean> {
  const value = await readProtectedValue(
    locationConsentKey(identity)
  );

  // No saved preference means consent has not been granted.
  return value === "granted";
}

export async function setTechnicianLocationConsent(
  identity: TechnicianLocationIdentity,
  granted: boolean
): Promise<void> {
  await writeProtectedValue(
    locationConsentKey(identity),
    granted ? "granted" : "denied"
  );
}

async function readContext(): Promise<TrackingContext | null> {
  const raw = await readProtectedValue(ACTIVE_CONTEXT_KEY);

  if (!raw) {
    return null;
  }

  try {
    const parsed: unknown = JSON.parse(raw);

    if (
      typeof parsed !== "object" ||
      parsed === null ||
      Array.isArray(parsed)
    ) {
      await deleteProtectedValue(ACTIVE_CONTEXT_KEY);
      return null;
    }

    const value = parsed as Record<string, unknown>;
    const technicianId = value.technicianId;
    const tenantId = value.tenantId;
    const activeJobId = value.activeJobId;
    const pendingJobIds = value.pendingJobIds;
    const trackingEnabled = value.trackingEnabled;

    const validPendingJobIds =
      pendingJobIds === undefined ||
      (
        Array.isArray(pendingJobIds) &&
        pendingJobIds.every(
          (jobId) =>
            typeof jobId === "string" &&
            jobId.trim().length > 0
        )
      );

    if (
      typeof technicianId !== "string" ||
      !technicianId.trim() ||
      typeof tenantId !== "string" ||
      !tenantId.trim() ||
      (
        activeJobId !== undefined &&
        (
          typeof activeJobId !== "string" ||
          !activeJobId.trim()
        )
      ) ||
      !validPendingJobIds ||
      (trackingEnabled !== undefined &&
        typeof trackingEnabled !== "boolean")
    ) {
      await deleteProtectedValue(ACTIVE_CONTEXT_KEY);
      return null;
    }

    return {
      technicianId: technicianId.trim(),
      tenantId: tenantId.trim(),
      ...(typeof activeJobId === "string"
        ? { activeJobId: activeJobId.trim() }
        : {}),
      ...(Array.isArray(pendingJobIds)
        ? {
            pendingJobIds: [
              ...new Set(
                pendingJobIds.map(
                  (jobId: string) => jobId.trim()
                )
              )
            ]
          }
        : {})
    };
  } catch {
    await deleteProtectedValue(ACTIVE_CONTEXT_KEY);
    return null;
  }
}

async function writeContext(context: TrackingContext): Promise<void> {
  await writeProtectedValue(
    ACTIVE_CONTEXT_KEY,
    JSON.stringify(context)
  );
}

async function readQueue(
  context: TrackingContext,
  jobIdInput?: string
): Promise<PendingGpsPing[]> {
  const jobId = String(
    jobIdInput ?? context.activeJobId ?? ""
  ).trim();

  if (!jobId) {
    return [];
  }

  const key = queueKey(context, jobId);
  const scope = {
    tenantId: context.tenantId,
    technicianId: context.technicianId
  };

  // Encrypted storage is the primary source.
  const encryptedQueue = await getOfflineRecord<unknown>(
    scope,
    "gps-queue",
    jobId
  );

  if (Array.isArray(encryptedQueue)) {
    const queue = encryptedQueue
      .filter((item): item is PendingGpsPing =>
        isPendingGpsPing(item, context, jobId)
      )
      .slice(-MAX_PENDING_PINGS);

    if (queue.length !== encryptedQueue.length) {
      logEvent("gps.offline_queue_sanitized", {
        storedCount: encryptedQueue.length,
        retainedCount: queue.length
      });

      if (queue.length === 0) {
        await deleteOfflineRecord(scope, "gps-queue", jobId);
      } else {
        await setOfflineRecord(
          scope,
          "gps-queue",
          jobId,
          queue,
          GPS_QUEUE_RETENTION_MS
        );
      }
    }

    await AsyncStorage.removeItem(key).catch(() => undefined);
    return queue;
  }

  if (encryptedQueue !== null) {
    await deleteOfflineRecord(scope, "gps-queue", jobId);
  }

  // Migrate the old queue only when encrypted storage has no valid queue.
  const raw = await AsyncStorage.getItem(key);

  if (!raw) {
    return [];
  }

  let parsed: unknown;

  try {
    parsed = JSON.parse(raw);
  } catch {
    await AsyncStorage.removeItem(key);
    return [];
  }

  if (!Array.isArray(parsed)) {
    await AsyncStorage.removeItem(key);
    return [];
  }

  const queue = parsed
    .filter((item): item is PendingGpsPing =>
      isPendingGpsPing(item, context, jobId)
    )
    .slice(-MAX_PENDING_PINGS);

  if (queue.length !== parsed.length) {
    logEvent("gps.legacy_queue_sanitized", {
      storedCount: parsed.length,
      retainedCount: queue.length
    });
  }

  if (queue.length === 0) {
    await AsyncStorage.removeItem(key);
    return [];
  }

  // Keep the legacy copy until the encrypted migration succeeds.
  await setOfflineRecord(
    scope,
    "gps-queue",
    jobId,
    queue,
    GPS_QUEUE_RETENTION_MS
  );

  // Remove the plaintext copy only after the encrypted write succeeds.
  await AsyncStorage.removeItem(key).catch(() => undefined);

  return queue;
}

async function writeQueue(
  context: TrackingContext,
  queue: PendingGpsPing[],
  jobIdInput?: string
): Promise<void> {
  const jobId = String(
    jobIdInput ?? context.activeJobId ?? ""
  ).trim();

  if (!jobId) {
    throw new Error("A job ID is required to write GPS points.");
  }

  const key = queueKey(context, jobId);
  const scope = {
    tenantId: context.tenantId,
    technicianId: context.technicianId
  };

  if (queue.length === 0) {
    await deleteOfflineRecord(scope, "gps-queue", jobId);
    await AsyncStorage.removeItem(key).catch(() => undefined);
    return;
  }

  await setOfflineRecord(
    scope,
    "gps-queue",
    jobId,
    queue,
    GPS_QUEUE_RETENTION_MS
  );

  // Remove any plaintext copy only after encrypted storage succeeds.
  await AsyncStorage.removeItem(key).catch(() => undefined);
}

function httpStatus(error: unknown): number | undefined {
  if (!error || typeof error !== "object") {
    return undefined;
  }

  const response = (
    error as {
      response?: {
        status?: unknown;
      };
    }
  ).response;

  return typeof response?.status === "number"
    ? response.status
    : undefined;
}


function gpsBatchCooldownKey(
  context: TrackingContext
): string {
  return (
    `${GPS_BATCH_COOLDOWN_PREFIX}` +
    `${encodeURIComponent(context.tenantId)}:` +
    `${encodeURIComponent(context.technicianId)}`
  );
}

function gpsBatchRetryDelayMs(error: unknown): number {
  if (!error || typeof error !== "object") {
    return DEFAULT_GPS_BATCH_RETRY_DELAY_MS;
  }

  const response = (
    error as {
      response?: {
        headers?: unknown;
      };
    }
  ).response;

  const headers = response?.headers;

  if (!headers || typeof headers !== "object") {
    return DEFAULT_GPS_BATCH_RETRY_DELAY_MS;
  }

  const headerBag = headers as {
    get?: (name: string) => unknown;
    "retry-after"?: unknown;
    "Retry-After"?: unknown;
  };

  const retryAfter =
    typeof headerBag.get === "function"
      ? headerBag.get("retry-after")
      : headerBag["retry-after"] ??
        headerBag["Retry-After"];

  if (
    typeof retryAfter === "number" &&
    Number.isFinite(retryAfter) &&
    retryAfter > 0
  ) {
    return retryAfter * 1000;
  }

  if (typeof retryAfter === "string") {
    const value = retryAfter.trim();
    const seconds = Number(value);

    if (Number.isFinite(seconds) && seconds > 0) {
      return seconds * 1000;
    }

    const retryAt = Date.parse(value);

    if (Number.isFinite(retryAt) && retryAt > Date.now()) {
      return retryAt - Date.now();
    }
  }

  return DEFAULT_GPS_BATCH_RETRY_DELAY_MS;
}


/**
 * Synchronize queued GPS points using the existing authenticated batch API.
 * The backend remains authoritative for technician identity, tenant access,
 * assignment and job status.
 */
async function flushJobQueue(
  context: TrackingContext,
  jobIdInput?: string
): Promise<void> {
  const jobId = String(
    jobIdInput ?? context.activeJobId ?? ""
  ).trim();

  if (!jobId || flushing) {
    return;
  }

  // Acquire the lock before any asynchronous storage reads.
  // This prevents overlapping calls from sending concurrent batches.
  flushing = true;

  try {
    const cooldownKey = gpsBatchCooldownKey(context);
    const rawCooldown =
      await readProtectedValue(cooldownKey);

    if (rawCooldown !== null) {
      const retryAt = Number(rawCooldown);

      if (Number.isFinite(retryAt) && retryAt > Date.now()) {
        logEvent("gps.offline_batch_retry_deferred", {
          retryInMs: retryAt - Date.now()
        });

        return;
      }

      // The saved cooldown has expired or is invalid.
      await deleteProtectedValue(cooldownKey);
    }

    const initialQueue = await readQueue(context, jobId);

    if (initialQueue.length === 0) {
      return;
    }

    while (true) {
      const currentQueue = await readQueue(context, jobId);

      if (currentQueue.length === 0) {
        break;
      }

      const batch = currentQueue.slice(0, BATCH_SIZE);

      try {
        const response = await apiClient.post<GpsBatchResponse>(
          "/api/v1/gps/batch",
          { pings: batch },
          {
            headers: {
              "X-Tenant-ID": context.tenantId
            }
          }
        );

        const result = response.data;

        if (
          typeof result.failed === "number" &&
          result.failed > 0
        ) {
          // Keep the entire batch until the rejection can be resolved.
          // Do not discard GPS points without confirmed synchronization.
          logEvent("gps.offline_batch_rejected", {
            count: batch.length,
            rejected: result.failed
          });

          break;
        }

        // Keep the queued points unless the backend confirms
        // that every point in this batch succeeded.
        if (result.succeeded !== batch.length) {
          logEvent("gps.offline_batch_unconfirmed", {
            count: batch.length
          });

          break;
        }

        await writeQueue(
          context,
          currentQueue.slice(batch.length),
          jobId
        );

        await deleteProtectedValue(cooldownKey);

        logEvent("gps.offline_batch_synced", {
          count: batch.length
        });
      } catch (error: unknown) {
        const status = httpStatus(error);

        // Respect the backend's rate limit. Retain every point
        // in this batch and defer another attempt.
        if (status === 429) {
          const retryDelayMs =
            gpsBatchRetryDelayMs(error);

          await writeProtectedValue(
            cooldownKey,
            String(Date.now() + retryDelayMs)
          );

          logEvent("gps.offline_batch_rate_limited", {
            status,
            retryInMs: retryDelayMs
          });

          break;
        }

        if (
          status === 400 ||
          status === 403 ||
          status === 404 ||
          status === 409 ||
          status === 413 ||
          status === 422
        ) {
          await writeProtectedValue(
            cooldownKey,
            String(
              Date.now() + DEFAULT_GPS_BATCH_RETRY_DELAY_MS
            )
          );

          logEvent("gps.offline_batch_rejected_and_retained", {
            count: batch.length,
            status
          });

          break;
        }

        const errorDetails =
          error && typeof error === "object"
            ? (error as {
                code?: unknown;
                request?: unknown;
                response?: unknown;
              })
            : undefined;

        logEvent("gps.offline_batch_sync_failed", {
          status: status ?? null,
          code:
            typeof errorDetails?.code === "string"
              ? errorDetails.code
              : null,
          hasResponse: Boolean(errorDetails?.response),
          hasRequest: Boolean(errorDetails?.request),
          errorName:
            error instanceof Error
              ? error.name
              : typeof error,
          errorMessage:
            error instanceof Error
              ? error.message.slice(0, 160)
              : String(error).slice(0, 160)
        });

        break;
      }
    }
  } finally {
    flushing = false;
  }
}

async function processLocation(
  location: Location.LocationObject,
  context: TrackingContext
): Promise<void> {
  const coords = location.coords;
  const timestamp = new Date(location.timestamp).toISOString();

  // Update the backend's short-lived technician availability location.
  try {
    await sendTechnicianAvailabilityPing(
      {
        latitude: coords.latitude,
        longitude: coords.longitude,
        accuracy: coords.accuracy,
        capturedAt: timestamp
      },
      context.tenantId
    );
  } catch (error: unknown) {
    const response =
      error && typeof error === "object" && "response" in error
        ? (
            error as {
              response?: {
                status?: unknown;
                data?: unknown;
              };
            }
          ).response
        : undefined;

    const responseData = response?.data;
    const detail =
      responseData &&
      typeof responseData === "object" &&
      "detail" in responseData
        ? (responseData as { detail?: unknown }).detail
        : null;

    logEvent("gps.availability_response_details", {
      status: response?.status ?? null,
      detail: detail ?? null,
    });

    logError("gps.availability_update_failed", error);
  }

  // Availability tracking applies while signed in.
  // Job history is recorded only when an active job context exists.
  if (!context.activeJobId) {
    return;
  }

  const ping: PendingGpsPing = {
    technician_id: context.technicianId,
    job_id: context.activeJobId,
    latitude: coords.latitude,
    longitude: coords.longitude,
    timestamp,
    accuracy: coords.accuracy,
    altitude: coords.altitude
  };

  const queue = await readQueue(context);

  // Avoid duplicate points if the native task replays a callback.
  if (
    !queue.some(
      (item) =>
        item.timestamp === ping.timestamp &&
        item.job_id === ping.job_id
    )
  ) {
    queue.push(ping);
  }

  if (queue.length > MAX_PENDING_PINGS) {
    queue.splice(0, queue.length - MAX_PENDING_PINGS);

    logEvent("gps.offline_queue_capacity_reached", {
      retained: MAX_PENDING_PINGS
    });
  }

  await writeQueue(context, queue);
  await flushJobQueue(context);
}

/**
 * Expo requires the task to be defined at module scope.
 * Import this module from app/_layout.tsx before navigation mounts.
 */
TaskManager.defineTask(
  LOCATION_TASK_NAME,
  async ({ data, error }) => {
    if (error) {
      logError("gps.background_task_failed", error);
      return;
    }

    const locations = (
      data as
        | {
            locations?: Location.LocationObject[];
          }
        | undefined
    )?.locations ?? [];

    logEvent("gps.background_task_callback", {
      locationCount: locations.length,
    });

    if (locations.length === 0) {
      logEvent("gps.background_task_empty");
      return;
    }

    let failedStage = "read_context";

    try {
      const context = await readContext();

      if (!context) {
        logEvent("gps.background_task_skipped_no_context");
        return;
      }

      if (context.trackingEnabled === false) {
        logEvent("gps.background_task_skipped_tracking_stopped");
        return;
      }

      failedStage = context.activeJobId
        ? "process_location_with_active_job"
        : "process_location_without_active_job";

      for (const location of locations) {
        await processLocation(location, context);
      }
    } catch (taskError: unknown) {
      logEvent("gps.background_location_processing_stage_failed", {
        stage: failedStage,
        errorName:
          taskError instanceof Error
            ? taskError.name
            : typeof taskError,
        errorMessage:
          taskError instanceof Error
            ? taskError.message.slice(0, 160)
            : String(taskError).slice(0, 160)
      });

      logError(
        "gps.background_location_processing_failed",
        taskError
      );
    }
  }
);

/**
 * Start GPS for a verified technician session.
 * Permission failure is reported to the caller; the caller must not block
 * dashboard access when location permission is denied.
 */
export async function startTechnicianLocationTracking(
  identity: TechnicianLocationIdentity
): Promise<void> {
  let startupStage = "validate_identity";

  try {
    const technicianId = String(
      identity.technicianId ?? ""
    ).trim();

    const tenantId = String(
      identity.tenantId ?? ""
    ).trim();

    if (!technicianId || !tenantId) {
      throw new Error(
        "Authenticated technician and tenant IDs are required for GPS tracking."
      );
    }

    startupStage = "read_location_consent";

    const consentGranted =
      await hasTechnicianLocationConsent({
        technicianId,
        tenantId
      });

    if (!consentGranted) {
      startupStage = "stop_tracking_without_consent";

      await stopTechnicianLocationTracking();

      logEvent("gps.tracking_skipped_no_consent", {
        platform: "native"
      });
      return;
    }

    startupStage = "read_existing_context";

    const existing = await readContext();

    const sameIdentity =
      existing?.technicianId === technicianId &&
      existing?.tenantId === tenantId;

    // Never carry one account's tracking context into another account.
    if (existing && !sameIdentity) {
      startupStage = "check_previous_tracking";

      const previousTrackingStarted =
        await Location.hasStartedLocationUpdatesAsync(
          LOCATION_TASK_NAME
        );

      if (previousTrackingStarted) {
        startupStage = "stop_previous_tracking";

        await Location.stopLocationUpdatesAsync(
          LOCATION_TASK_NAME
        );
      }

      const previousJobIds = new Set([
        ...(existing.pendingJobIds ?? []),
        ...(existing.activeJobId ? [existing.activeJobId] : [])
      ]);

      for (const previousJobId of previousJobIds) {
        startupStage = "delete_previous_encrypted_queue";

        await deleteOfflineRecord(
          {
            tenantId: existing.tenantId,
            technicianId: existing.technicianId
          },
          "gps-queue",
          previousJobId
        );

        startupStage = "delete_previous_legacy_queue";

        await AsyncStorage.removeItem(
          queueKey(existing, previousJobId)
        ).catch(() => undefined);
      }
    }

    startupStage = "check_foreground_permission";

    let foreground =
      await Location.getForegroundPermissionsAsync();

    if (foreground.status !== "granted") {
      startupStage = "request_foreground_permission";

      foreground =
        await Location.requestForegroundPermissionsAsync();
    }

    if (foreground.status !== "granted") {
      logEvent("gps.permission_denied", {
        permission: "foreground"
      });

      throw new Error(
        "Foreground location permission was not granted."
      );
    }

    startupStage = "check_background_permission";

    let background =
      await Location.getBackgroundPermissionsAsync();

    if (background.status !== "granted") {
      startupStage = "request_background_permission";

      background =
        await Location.requestBackgroundPermissionsAsync();
    }

    if (background.status !== "granted") {
      logEvent("gps.permission_denied", {
        permission: "background"
      });

      throw new Error(
        "Background location permission was not granted."
      );
    }

    const context: TrackingContext = {
      technicianId,
      tenantId,
      ...(sameIdentity && existing?.activeJobId
        ? { activeJobId: existing.activeJobId }
        : {}),
      ...(sameIdentity && existing?.pendingJobIds?.length
        ? { pendingJobIds: [...existing.pendingJobIds] }
        : {})
    };

    startupStage = "write_tracking_context";

    await writeContext(context);

    startupStage = "check_native_tracking_state";

    const alreadyStarted =
      await Location.hasStartedLocationUpdatesAsync(
        LOCATION_TASK_NAME
      );

    if (!alreadyStarted) {
      startupStage = "start_native_location_updates";

      await Location.startLocationUpdatesAsync(
        LOCATION_TASK_NAME,
        {
          accuracy: Location.Accuracy.Balanced,
          timeInterval: 30_000,
          distanceInterval: 25,
          deferredUpdatesInterval: 30_000,
          pausesUpdatesAutomatically: false,
          showsBackgroundLocationIndicator: true,
          foregroundService: {
            notificationTitle: "FieldOps location active",
            notificationBody:
              "Sharing location for technician assignment and active jobs.",
            notificationColor: "#0F766E"
          }
        }
      );
    }

    logEvent("gps.background_tracking_started", {
      platform: "native"
    });

    try {
      const providerStatus =
        await Location.getProviderStatusAsync();

      const registeredTasks =
        await TaskManager.getRegisteredTasksAsync();

      const locationUpdatesStarted =
        await Location.hasStartedLocationUpdatesAsync(
          LOCATION_TASK_NAME
        );

      logEvent("gps.task_diagnostics", {
        taskDefined: TaskManager.isTaskDefined(
          LOCATION_TASK_NAME
        ),
        taskRegistered: registeredTasks.some(
          (task) => task.taskName === LOCATION_TASK_NAME
        ),
        locationUpdatesStarted,
        locationServicesEnabled:
          providerStatus.locationServicesEnabled,
        gpsAvailable: providerStatus.gpsAvailable,
        networkAvailable: providerStatus.networkAvailable
      });
    } catch (error: unknown) {
      logError("gps.task_diagnostics_failed", error);
    }

    startupStage = "initial_location_sync";

    // Preserve the existing behavior: a failed initial location read
    // or sync is logged without rejecting the entire startup operation.
    try {
      const location = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.High
      });

      await processLocation(location, context);
    } catch (error: unknown) {
      logError("gps.initial_location_sync_failed", error);
    }
  } catch (error: unknown) {
    logEvent("gps.tracking_start_stage_failed", {
      stage: startupStage,
      errorName:
        error instanceof Error ? error.name : typeof error,
      errorMessage:
        error instanceof Error
          ? error.message.slice(0, 160)
          : "Non-Error value thrown"
    });

    throw error;
  }
}

/**
 * Called only after a backend-authoritative job action succeeds.
 */
export async function setActiveGpsJob(
  jobIdInput: string | number
): Promise<void> {
  const jobId = String(jobIdInput ?? "").trim();

  if (!jobId) {
    throw new Error(
      "A job ID is required to track job GPS."
    );
  }

  const context = await readContext();

  if (!context) {
    logEvent("gps.active_job_tracking_skipped", {
      reason: "tracking_not_started"
    });

    return;
  }

  if (
    context.activeJobId &&
    context.activeJobId !== jobId
  ) {
    const previousJobId = context.activeJobId;

    await flushJobQueue(context, previousJobId);

    const previousQueue = await readQueue(
      context,
      previousJobId
    );

    const pendingJobIds = new Set(
      context.pendingJobIds ?? []
    );

    if (previousQueue.length > 0) {
      pendingJobIds.add(previousJobId);

      logEvent("gps.previous_job_pings_retained", {
        count: previousQueue.length
      });
    } else {
      pendingJobIds.delete(previousJobId);
    }

    context.pendingJobIds = [...pendingJobIds];

    if (context.pendingJobIds.length === 0) {
      delete context.pendingJobIds;
    }
  }

  context.pendingJobIds = (
    context.pendingJobIds ?? []
  ).filter((pendingJobId) => pendingJobId !== jobId);

  if (context.pendingJobIds.length === 0) {
    delete context.pendingJobIds;
  }

  context.activeJobId = jobId;
  await writeContext(context);

  logEvent("gps.active_job_tracking_started");

  try {
    const location = await Location.getCurrentPositionAsync({
      accuracy: Location.Accuracy.Balanced
    });

    await processLocation(location, context);
  } catch (error: unknown) {
    logError("gps.active_job_initial_ping_failed", error);
  }
}

export async function flushPendingGpsPings(): Promise<void> {
  const context = await readContext();

  if (!context) {
    return;
  }

  const pendingJobIds = new Set(
    context.pendingJobIds ?? []
  );

  if (context.activeJobId) {
    pendingJobIds.delete(context.activeJobId);
  }

  for (const jobId of pendingJobIds) {
    await flushJobQueue(context, jobId);

    const remaining = await readQueue(context, jobId);

    if (remaining.length === 0) {
      pendingJobIds.delete(jobId);
    }
  }

  if (context.activeJobId) {
    await flushJobQueue(context, context.activeJobId);
  }

  context.pendingJobIds = [...pendingJobIds];

  if (context.pendingJobIds.length === 0) {
    delete context.pendingJobIds;
  }

  await writeContext(context);
}

/**
 * Stop associating GPS points with a job after the backend accepts a
 * pause, rejection, or completion transition.
 */
export async function clearActiveGpsJob(
  jobIdInput: string | number
): Promise<void> {
  const context = await readContext();

  if (!context?.activeJobId) {
    return;
  }

  const jobId = String(jobIdInput ?? "").trim();

  if (context.activeJobId !== jobId) {
    return;
  }

  // Try to synchronize the final points for this job.
  await flushJobQueue(context, jobId);

  const remaining = await readQueue(context, jobId);
  const pendingJobIds = new Set(
    context.pendingJobIds ?? []
  );

  if (remaining.length > 0) {
    // Keep this job's queue for a later synchronization attempt.
    pendingJobIds.add(jobId);

    logEvent("gps.pending_job_pings_retained", {
      count: remaining.length
    });
  } else {
    pendingJobIds.delete(jobId);
  }

  delete context.activeJobId;

  context.pendingJobIds = [...pendingJobIds];

  if (context.pendingJobIds.length === 0) {
    delete context.pendingJobIds;
  }

  await writeContext(context);

  logEvent("gps.active_job_tracking_stopped");
}

/**
 * Stop native tracking and clear the technician's local tracking context.
 */
/**
 * Stop native GPS tracking.
 * By default, pending GPS data is cleared when tracking is stopped.
 * Callers may preserve pending queues when stopping for logout.
 */
export async function stopTechnicianLocationTracking(
  options: { preservePendingQueues?: boolean } = {},
): Promise<void> {
  let context: TrackingContext | null = null;

  const preservePendingQueues =
    options.preservePendingQueues === true;

  try {
    context = await readContext();
  } catch (contextError: unknown) {
    logError("gps.active_context_read_failed_on_stop", contextError);
  }

  try {
    if (
      await Location.hasStartedLocationUpdatesAsync(
        LOCATION_TASK_NAME
      )
    ) {
      await Location.stopLocationUpdatesAsync(
        LOCATION_TASK_NAME
      );
    }
  } finally {
    if (preservePendingQueues && context) {
      // Keep the queue references so the same technician can
      // resume synchronization after signing in again.
      await writeContext({
        ...context,
        trackingEnabled: false,
      });

      logEvent("gps.pending_pings_preserved_on_logout", {
        pendingJobCount: new Set([
          ...(context.pendingJobIds ?? []),
          ...(context.activeJobId ? [context.activeJobId] : []),
        ]).size,
      });
    } else {
      await deleteProtectedValue(ACTIVE_CONTEXT_KEY);

      if (context) {
        const jobIds = new Set([
          ...(context.pendingJobIds ?? []),
          ...(context.activeJobId ? [context.activeJobId] : []),
        ]);

        let clearedCount = 0;

        for (const jobId of jobIds) {
          const queue = await readQueue(context, jobId);

          if (queue.length > 0) {
            await writeQueue(context, [], jobId);
            clearedCount += queue.length;
          }
        }

        if (clearedCount > 0) {
          logEvent("gps.pending_pings_cleared_on_logout", {
            count: clearedCount,
          });
        }
      }
    }

    logEvent("gps.background_tracking_stopped", {
      pendingQueuesPreserved: preservePendingQueues && context !== null,
    });
  }
}