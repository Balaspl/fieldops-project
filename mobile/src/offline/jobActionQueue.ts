import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  getOfflineRecord,
  setOfflineRecord
} from "./offlineStore";
import type { TechnicianJobAction } from "../api/jobActions";

export type QueueableTechnicianJobAction = Exclude<
  TechnicianJobAction,
  "reject" | "complete"
>;

export type JobActionQueueStatus =
  | "pending"
  | "syncing"
  | "synced"
  | "conflict"
  | "failed";

export interface JobActionQueueScope {
  tenantId: string | number;
  technicianId: string | number;
}

export interface QueueableJobActionPayload {
  latitude?: number;
  longitude?: number;
  accuracy?: number | null;
  captured_at?: string;
}

export interface EnqueueJobActionInput
  extends JobActionQueueScope {
  jobId: string | number;
  action: QueueableTechnicianJobAction;
  payload?: QueueableJobActionPayload;
}

export interface QueuedJobAction {
  id: string;
  tenantId: string;
  technicianId: string;
  jobId: string;
  action: QueueableTechnicianJobAction;
  payload: QueueableJobActionPayload;
  status: JobActionQueueStatus;
  createdAt: string;
  updatedAt: string;
  attemptCount: number;
  lastAttemptAt?: string;
  syncedAt?: string;
  serverStatus?: string;
  lastError?: string;
  reconciliationRequired: boolean;
}

interface NormalizedQueueScope {
  tenantId: string;
  technicianId: string;
}

interface StoredQueue {
  version: 1;
  items: QueuedJobAction[];
}

const QUEUE_VERSION = 1;
const QUEUE_RETENTION_MS = 30 * 24 * 60 * 60 * 1000;

const QUEUE_KEY_PREFIX = "fieldops:offline:job-actions:v1";

const QUEUEABLE_ACTIONS: readonly QueueableTechnicianJobAction[] = [
  "accept",
  "start",
  "on-site",
  "pause",
  "resume"
];

const ALLOWED_PAYLOAD_KEYS = new Set([
  "latitude",
  "longitude",
  "accuracy",
  "captured_at"
]);

const MAX_ERROR_LENGTH = 500;

let queueOperation: Promise<void> = Promise.resolve();
let localIdCounter = 0;

function withQueueLock<T>(
  operation: () => Promise<T>
): Promise<T> {
  const result = queueOperation.then(
    () => operation(),
    () => operation()
  );

  queueOperation = result.then(
    () => undefined,
    () => undefined
  );

  return result;
}

function normalizeIdentifier(
  value: string | number,
  label: string
): string {
  const normalized = String(value).trim();

  if (!normalized) {
    throw new Error(`${label} is required for the offline queue.`);
  }

  return normalized;
}

function normalizeScope(
  scope: JobActionQueueScope
): NormalizedQueueScope {
  if (
    !scope ||
    scope.tenantId === undefined ||
    scope.tenantId === null ||
    scope.technicianId === undefined ||
    scope.technicianId === null
  ) {
    throw new Error(
      "A valid tenant ID and technician ID are required."
    );
  }

  return {
    tenantId: normalizeIdentifier(scope.tenantId, "Tenant ID"),
    technicianId: normalizeIdentifier(
      scope.technicianId,
      "Technician ID"
    )
  };
}

function getStorageKey(
  scope: NormalizedQueueScope
): string {
  return [
    QUEUE_KEY_PREFIX,
    encodeURIComponent(scope.tenantId),
    encodeURIComponent(scope.technicianId)
  ].join(":");
}

function isRecord(
  value: unknown
): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  );
}

function isQueueableAction(
  value: unknown
): value is QueueableTechnicianJobAction {
  return (
    typeof value === "string" &&
    QUEUEABLE_ACTIONS.includes(
      value as QueueableTechnicianJobAction
    )
  );
}

function isQueueStatus(
  value: unknown
): value is JobActionQueueStatus {
  return (
    value === "pending" ||
    value === "syncing" ||
    value === "synced" ||
    value === "conflict" ||
    value === "failed"
  );
}

function getNow(): string {
  return new Date().toISOString();
}

function createQueueItemId(): string {
  localIdCounter += 1;

  return [
    "job-action",
    Date.now().toString(36),
    localIdCounter.toString(36),
    Math.random().toString(36).slice(2, 12)
  ].join("-");
}

function normalizeError(error: unknown): string {
  const message =
    error instanceof Error
      ? error.message
      : typeof error === "string"
        ? error
        : "An unexpected synchronization error occurred.";

  return message.slice(0, MAX_ERROR_LENGTH);
}

function normalizeActionPayload(
  value: unknown
): QueueableJobActionPayload {
  if (value === undefined || value === null) {
    return {};
  }

  if (!isRecord(value)) {
    throw new Error("The queued job-action payload is invalid.");
  }

  const unsupportedKeys = Object.keys(value).filter(
    (key) => !ALLOWED_PAYLOAD_KEYS.has(key)
  );

  if (unsupportedKeys.length > 0) {
    throw new Error(
      "Only supported GPS metadata can be stored in the generic job-action queue."
    );
  }

  const payload: QueueableJobActionPayload = {};

  if (value.latitude !== undefined) {
    if (
      typeof value.latitude !== "number" ||
      !Number.isFinite(value.latitude) ||
      value.latitude < -90 ||
      value.latitude > 90
    ) {
      throw new Error("The GPS latitude is invalid.");
    }

    payload.latitude = value.latitude;
  }

  if (value.longitude !== undefined) {
    if (
      typeof value.longitude !== "number" ||
      !Number.isFinite(value.longitude) ||
      value.longitude < -180 ||
      value.longitude > 180
    ) {
      throw new Error("The GPS longitude is invalid.");
    }

    payload.longitude = value.longitude;
  }

  if (
    (payload.latitude === undefined) !==
    (payload.longitude === undefined)
  ) {
    throw new Error(
      "GPS latitude and longitude must be provided together."
    );
  }

  if (value.accuracy !== undefined) {
    if (
      value.accuracy !== null &&
      (
        typeof value.accuracy !== "number" ||
        !Number.isFinite(value.accuracy) ||
        value.accuracy < 0
      )
    ) {
      throw new Error("The GPS accuracy value is invalid.");
    }

    payload.accuracy = value.accuracy as number | null;
  }

  if (value.captured_at !== undefined) {
    if (
      typeof value.captured_at !== "string" ||
      !value.captured_at.trim() ||
      !Number.isFinite(Date.parse(value.captured_at))
    ) {
      throw new Error("The GPS capture timestamp is invalid.");
    }

    payload.captured_at = value.captured_at.trim();
  }

  return payload;
}

function isValidDateString(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.trim().length > 0 &&
    Number.isFinite(Date.parse(value))
  );
}

function optionalStoredString(
  value: unknown,
  fieldName: string
): string | undefined {
  if (value === undefined || value === null) {
    return undefined;
  }

  if (typeof value !== "string") {
    throw new Error(
      `The stored offline queue field '${fieldName}' is invalid.`
    );
  }

  return value;
}

function validateStoredItem(
  value: unknown,
  scope: NormalizedQueueScope
): QueuedJobAction {
  if (!isRecord(value)) {
    throw new Error("The stored offline job-action entry is invalid.");
  }

  if (
    typeof value.id !== "string" ||
    !value.id.trim() ||
    typeof value.tenantId !== "string" ||
    typeof value.technicianId !== "string" ||
    typeof value.jobId !== "string" ||
    !value.jobId.trim() ||
    !isQueueableAction(value.action) ||
    !isQueueStatus(value.status) ||
    !isValidDateString(value.createdAt) ||
    !isValidDateString(value.updatedAt) ||
    typeof value.attemptCount !== "number" ||
    !Number.isSafeInteger(value.attemptCount) ||
    value.attemptCount < 0 ||
    typeof value.reconciliationRequired !== "boolean"
  ) {
    throw new Error(
      "The stored offline job-action entry has invalid fields."
    );
  }

  if (
    value.tenantId !== scope.tenantId ||
    value.technicianId !== scope.technicianId
  ) {
    throw new Error(
      "The stored offline queue does not match the authenticated technician."
    );
  }

  const lastAttemptAt = optionalStoredString(
    value.lastAttemptAt,
    "lastAttemptAt"
  );

  const syncedAt = optionalStoredString(
    value.syncedAt,
    "syncedAt"
  );

  const serverStatus = optionalStoredString(
    value.serverStatus,
    "serverStatus"
  );

  const lastError = optionalStoredString(
    value.lastError,
    "lastError"
  );

  if (
    lastAttemptAt !== undefined &&
    !isValidDateString(lastAttemptAt)
  ) {
    throw new Error("The stored last-attempt timestamp is invalid.");
  }

  if (syncedAt !== undefined && !isValidDateString(syncedAt)) {
    throw new Error("The stored synchronization timestamp is invalid.");
  }

  return {
    id: value.id,
    tenantId: value.tenantId,
    technicianId: value.technicianId,
    jobId: value.jobId,
    action: value.action,
    payload: normalizeActionPayload(value.payload),
    status: value.status,
    createdAt: value.createdAt,
    updatedAt: value.updatedAt,
    attemptCount: value.attemptCount,
    reconciliationRequired: value.reconciliationRequired,
    ...(lastAttemptAt !== undefined ? { lastAttemptAt } : {}),
    ...(syncedAt !== undefined ? { syncedAt } : {}),
    ...(serverStatus !== undefined ? { serverStatus } : {}),
    ...(lastError !== undefined ? { lastError } : {})
  };
}

function validateQueueEnvelope(
  value: unknown,
  scope: NormalizedQueueScope
): QueuedJobAction[] {
  if (
    !isRecord(value) ||
    value.version !== QUEUE_VERSION ||
    !Array.isArray(value.items)
  ) {
    throw new Error(
      "The saved offline queue has an unsupported format. Its contents were preserved."
    );
  }

  return value.items.map((item) =>
    validateStoredItem(item, scope)
  );
}

async function readQueue(
  scope: NormalizedQueueScope
): Promise<QueuedJobAction[]> {
  const legacyKey = getStorageKey(scope);

  // The encrypted store is always the primary source.
  const encryptedQueue = await getOfflineRecord<unknown>(
    scope,
    "job-action-queue",
    "queue"
  );

  if (encryptedQueue !== null) {
    const items = validateQueueEnvelope(encryptedQueue, scope);

    // Remove any old plaintext copy after the encrypted queue is validated.
    await AsyncStorage.removeItem(legacyKey).catch(
      () => undefined
    );

    return items;
  }

  // Migrate the existing queue only when encrypted storage has no entry.
  const raw = await AsyncStorage.getItem(legacyKey);

  if (raw === null) {
    return [];
  }

  let parsed: unknown;

  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error(
      "The saved offline queue is unreadable. Its contents were preserved."
    );
  }

  // Validate every entry before migrating so malformed data is preserved.
  const items = validateQueueEnvelope(parsed, scope);

  await setOfflineRecord(
    scope,
    "job-action-queue",
    "queue",
    {
      version: QUEUE_VERSION,
      items
    },
    QUEUE_RETENTION_MS
  );

  // Only remove the old queue after encrypted storage succeeds.
  await AsyncStorage.removeItem(legacyKey).catch(
    () => undefined
  );

  return items;
}

async function writeQueue(
  scope: NormalizedQueueScope,
  items: QueuedJobAction[]
): Promise<void> {
  const stored: StoredQueue = {
    version: QUEUE_VERSION,
    items
  };

  await setOfflineRecord(
    scope,
    "job-action-queue",
    "queue",
    stored,
    QUEUE_RETENTION_MS
  );

  // The encrypted write must succeed before removing the legacy copy.
  await AsyncStorage.removeItem(getStorageKey(scope)).catch(
    () => undefined
  );
}

function sortQueue(
  items: QueuedJobAction[]
): QueuedJobAction[] {
  return [...items].sort((a, b) =>
    a.createdAt.localeCompare(b.createdAt)
  );
}

async function updateQueueItem(
  scopeInput: JobActionQueueScope,
  itemId: string,
  update: (item: QueuedJobAction) => QueuedJobAction
): Promise<QueuedJobAction> {
  const scope = normalizeScope(scopeInput);

  return withQueueLock(async () => {
    const items = await readQueue(scope);
    const index = items.findIndex((item) => item.id === itemId);

    if (index < 0) {
      throw new Error("The queued job action was not found.");
    }

    const currentItem = items[index];

    if (!currentItem) {
      throw new Error("The queued job action was not found.");
    }

    const updated = update(currentItem);

    const savedItem: QueuedJobAction = {
      ...updated,
      updatedAt: getNow()
    };

    items.splice(index, 1, savedItem);

    await writeQueue(scope, items);

    return savedItem;
  });
}

/**
 * Adds a safe, status-changing job action to persistent local storage.
 *
 * This function does not send requests to the backend. A queued action
 * is not a server-confirmed job status.
 *
 * Reject and complete actions are intentionally excluded.
 */
export async function enqueueJobAction(
  input: EnqueueJobActionInput
): Promise<QueuedJobAction> {
  if (!isQueueableAction(input.action)) {
    throw new Error(
      "This job action is not supported by the generic offline queue."
    );
  }

  const scope = normalizeScope(input);

  const numericJobId = Number(String(input.jobId).trim());

  if (
    !Number.isSafeInteger(numericJobId) ||
    numericJobId <= 0
  ) {
    throw new Error("A valid numeric job ID is required.");
  }

  const payload = normalizeActionPayload(input.payload);

  return withQueueLock(async () => {
    const items = await readQueue(scope);
    const jobId = String(numericJobId);

    // Prevent duplicate local actions while an earlier action for
    // the same job and action remains unresolved.
    const existing = items.find(
      (item) =>
        item.jobId === jobId &&
        item.action === input.action &&
        item.status !== "synced"
    );

    if (existing) {
      return existing;
    }

    const now = getNow();

    const item: QueuedJobAction = {
      id: createQueueItemId(),
      tenantId: scope.tenantId,
      technicianId: scope.technicianId,
      jobId,
      action: input.action,
      payload,
      status: "pending",
      createdAt: now,
      updatedAt: now,
      attemptCount: 0,
      reconciliationRequired: false
    };

    items.push(item);

    await writeQueue(scope, items);

    return item;
  });
}

/**
 * Returns queue entries in creation order, including resolved entries.
 */
export async function getJobActionQueue(
  scopeInput: JobActionQueueScope
): Promise<QueuedJobAction[]> {
  const scope = normalizeScope(scopeInput);

  return withQueueLock(async () => {
    const items = await readQueue(scope);
    return sortQueue(items);
  });
}

/**
 * Returns pending actions. Consumers must inspect
 * reconciliationRequired before attempting to send an action.
 */
export async function getPendingJobActions(
  scope: JobActionQueueScope
): Promise<QueuedJobAction[]> {
  const items = await getJobActionQueue(scope);

  return items.filter((item) => item.status === "pending");
}

/**
 * Marks an unattempted or reconciled pending action as syncing.
 *
 * An action with an uncertain previous result must be reconciled
 * against authoritative backend state before it can be sent again.
 */
export async function markJobActionSyncing(
  scope: JobActionQueueScope,
  itemId: string
): Promise<QueuedJobAction> {
  return updateQueueItem(scope, itemId, (item) => {
    if (item.status !== "pending") {
      throw new Error("Only pending actions can enter syncing state.");
    }

    if (item.reconciliationRequired) {
      throw new Error(
        "Refresh the authoritative job state before retrying this action."
      );
    }

    return {
      ...item,
      status: "syncing",
      attemptCount: item.attemptCount + 1,
      lastAttemptAt: getNow(),
      lastError: undefined
    };
  });
}

/**
 * Marks an action as server-confirmed.
 *
 * Call this only after a successful response or after authoritative
 * state reconciliation proves the action already succeeded.
 */
export async function markJobActionSynced(
  scope: JobActionQueueScope,
  itemId: string,
  serverStatus?: string
): Promise<QueuedJobAction> {
  return updateQueueItem(scope, itemId, (item) => {
    if (
      item.status !== "pending" &&
      item.status !== "syncing"
    ) {
      throw new Error(
        "Only pending or syncing actions can be marked as synced."
      );
    }

    return {
      ...item,
      status: "synced",
      syncedAt: getNow(),
      reconciliationRequired: false,
      lastError: undefined,
      ...(serverStatus !== undefined ? { serverStatus } : {})
    };
  });
}

/**
 * Returns an attempted action to pending after a transient or uncertain
 * result. The caller MUST reconcile server state before resubmitting it.
 */
export async function markJobActionPendingAfterUncertainResult(
  scope: JobActionQueueScope,
  itemId: string,
  error: unknown
): Promise<QueuedJobAction> {
  return updateQueueItem(scope, itemId, (item) => {
    if (item.status !== "syncing") {
      throw new Error(
        "Only syncing actions can be returned to pending."
      );
    }

    return {
      ...item,
      status: "pending",
      reconciliationRequired: true,
      lastError: normalizeError(error)
    };
  });
}

/**
 * Marks an action as conflicted when the server rejects it because
 * of current job state, assignment, or a similar business rule.
 */
export async function markJobActionConflict(
  scope: JobActionQueueScope,
  itemId: string,
  reason: string,
  serverStatus?: string
): Promise<QueuedJobAction> {
  return updateQueueItem(scope, itemId, (item) => {
    if (
      item.status !== "pending" &&
      item.status !== "syncing"
    ) {
      throw new Error(
        "Only pending or syncing actions can become conflicts."
      );
    }

    return {
      ...item,
      status: "conflict",
      reconciliationRequired: true,
      lastError: normalizeError(reason),
      ...(serverStatus !== undefined ? { serverStatus } : {})
    };
  });
}

/**
 * Marks an action as failed because it cannot currently be processed.
 * Failed actions do not automatically retry.
 */
export async function markJobActionFailed(
  scope: JobActionQueueScope,
  itemId: string,
  reason: string,
  serverStatus?: string
): Promise<QueuedJobAction> {
  return updateQueueItem(scope, itemId, (item) => {
    if (
      item.status !== "pending" &&
      item.status !== "syncing"
    ) {
      throw new Error(
        "Only pending or syncing actions can become failed."
      );
    }

    return {
      ...item,
      status: "failed",
      reconciliationRequired: item.attemptCount > 0,
      lastError: normalizeError(reason),
      ...(serverStatus !== undefined ? { serverStatus } : {})
    };
  });
}

/**
 * Allows an explicit retry of a failed action.
 *
 * Reconciliation remains required if the action was attempted before.
 * Conflicted actions must be resolved separately.
 */
export async function retryFailedJobAction(
  scope: JobActionQueueScope,
  itemId: string
): Promise<QueuedJobAction> {
  return updateQueueItem(scope, itemId, (item) => {
    if (item.status !== "failed") {
      throw new Error("Only failed actions can be retried.");
    }

    return {
      ...item,
      status: "pending",
      reconciliationRequired: item.attemptCount > 0,
      lastError: undefined,
      serverStatus: undefined
    };
  });
}

/**
 * Recovers entries left in syncing state after an app interruption.
 *
 * Recovery does not send requests. The result may be uncertain because
 * the backend could have processed the request before the interruption.
 */
export async function recoverInterruptedJobActions(
  scopeInput: JobActionQueueScope
): Promise<number> {
  const scope = normalizeScope(scopeInput);

  return withQueueLock(async () => {
    const items = await readQueue(scope);
    let recoveredCount = 0;
    const now = getNow();

    const recoveredItems = items.map((item) => {
      if (item.status !== "syncing") {
        return item;
      }

      recoveredCount += 1;

      return {
        ...item,
        status: "pending" as const,
        updatedAt: now,
        reconciliationRequired: true,
        lastError:
          "Synchronization was interrupted. Verify the server state before retrying."
      };
    });

    if (recoveredCount > 0) {
      await writeQueue(scope, recoveredItems);
    }

    return recoveredCount;
  });
}

/**
 * Discards a local pending, conflicted, or failed action.
 *
 * It does not cancel a request already in flight or change backend state.
 */
export async function discardQueuedJobAction(
  scopeInput: JobActionQueueScope,
  itemId: string
): Promise<void> {
  const scope = normalizeScope(scopeInput);

  await withQueueLock(async () => {
    const items = await readQueue(scope);
    const item = items.find((entry) => entry.id === itemId);

    if (!item) {
      throw new Error("The queued job action was not found.");
    }

    if (item.status === "syncing") {
      throw new Error(
        "A syncing action cannot be discarded until its result is resolved."
      );
    }

    if (item.status === "synced") {
      throw new Error(
        "A synced action cannot be discarded using this operation."
      );
    }

    const remaining = items.filter(
      (entry) => entry.id !== itemId
    );

    await writeQueue(scope, remaining);
  });
}

/**
 * Removes only server-confirmed entries after callers no longer
 * need them for diagnostics or user-visible synchronization history.
 */
export async function removeSyncedJobActions(
  scopeInput: JobActionQueueScope
): Promise<number> {
  const scope = normalizeScope(scopeInput);

  return withQueueLock(async () => {
    const items = await readQueue(scope);

    const remaining = items.filter(
      (item) => item.status !== "synced"
    );

    const removedCount = items.length - remaining.length;

    if (removedCount > 0) {
      await writeQueue(scope, remaining);
    }

    return removedCount;
  });
}

export interface JobActionQueueCounts {
  pending: number;
  syncing: number;
  synced: number;
  conflict: number;
  failed: number;
  total: number;
}

/**
 * Returns local queue counts for offline/sync status indicators.
 */
export async function getJobActionQueueCounts(
  scope: JobActionQueueScope
): Promise<JobActionQueueCounts> {
  const items = await getJobActionQueue(scope);

  const counts: JobActionQueueCounts = {
    pending: 0,
    syncing: 0,
    synced: 0,
    conflict: 0,
    failed: 0,
    total: items.length
  };

  for (const item of items) {
    counts[item.status] += 1;
  }

  return counts;
}