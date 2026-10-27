import axios from "axios";
import * as Network from "expo-network";

import { useAuthStore } from "../auth/authStore";
import { getTechnicianJob } from "../api/technician";
import {
  performTechnicianJobAction,
  type TechnicianJobActionPayload
} from "../api/jobActions";
import {
  isNetworkUnavailableError
} from "../api/client";

import {
  getPendingJobActions,
  markJobActionConflict,
  markJobActionFailed,
  markJobActionPendingAfterUncertainResult,
  markJobActionSynced,
  markJobActionSyncing,
  recoverInterruptedJobActions,
  type JobActionQueueScope,
  type QueuedJobAction
} from "./jobActionQueue";

export type JobActionSyncResult =
  | "synced"
  | "empty"
  | "offline"
  | "authentication-required"
  | "session-changed"
  | "network-error"
  | "server-error"
  | "conflict"
  | "failed"
  | "already-syncing";

export interface JobActionSyncSummary {
  result: JobActionSyncResult;
  processed: number;
  synced: number;
  conflicts: number;
  failed: number;
  message?: string;
}

interface ActionTransition {
  targetStatuses: string[];
  allowedSourceStatuses: string[];
}

let activeSyncPromise: Promise<JobActionSyncSummary> | null = null;

function createSummary(
  result: JobActionSyncResult,
  processed: number,
  synced: number,
  conflicts: number,
  failed: number,
  message?: string
): JobActionSyncSummary {
  return {
    result,
    processed,
    synced,
    conflicts,
    failed,
    ...(message ? { message } : {})
  };
}

function normalizeStatus(status: string): string {
  return status
    .trim()
    .toUpperCase()
    .replace(/[_\-\s]+/g, "_");
}

function getActionTransition(
  action: QueuedJobAction["action"]
): ActionTransition {
  switch (action) {
    case "accept":
      return {
        targetStatuses: ["ACCEPTED"],
        allowedSourceStatuses: [
          "ASSIGNED",
          "AWAITING_ACCEPTANCE",
          "ACTIVE"
        ]
      };

    case "start":
      return {
        targetStatuses: ["EN_ROUTE"],
        allowedSourceStatuses: ["ACCEPTED"]
      };

    case "on-site":
      return {
        targetStatuses: ["IN_PROGRESS"],
        allowedSourceStatuses: ["EN_ROUTE"]
      };

    case "pause":
      return {
        targetStatuses: ["PAUSED"],
        allowedSourceStatuses: ["IN_PROGRESS"]
      };

    case "resume":
      return {
        targetStatuses: ["IN_PROGRESS"],
        allowedSourceStatuses: ["PAUSED"]
      };
  }
}

function getHttpStatus(error: unknown): number | undefined {
  if (!axios.isAxiosError(error)) {
    return undefined;
  }

  return error.response?.status;
}

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }

  return "An unexpected synchronization error occurred.";
}

function isSessionValidForScope(
  scope: JobActionQueueScope
): boolean {
  const auth = useAuthStore.getState();
  const user = auth.user;

  if (
    !auth.isAuthenticated ||
    !user ||
    typeof user.role !== "string" ||
    user.role.trim().toLowerCase() !== "technician" ||
    user.id == null ||
    user.tenant_id == null
  ) {
    return false;
  }

  return (
    String(user.id).trim() === String(scope.technicianId).trim() &&
    String(user.tenant_id).trim() === String(scope.tenantId).trim()
  );
}

async function isNetworkAvailable(): Promise<boolean> {
  try {
    const state = await Network.getNetworkStateAsync();

    if (
      state.isConnected === false ||
      state.isInternetReachable === false
    ) {
      return false;
    }

    return true;
  } catch {
    // If connectivity cannot be determined, do not start replaying
    // pending state-changing actions.
    return false;
  }
}

async function runSynchronization(
  scope: JobActionQueueScope
): Promise<JobActionSyncSummary> {
  let processed = 0;
  let synced = 0;
  let conflicts = 0;
  let failed = 0;

  if (!isSessionValidForScope(scope)) {
    return createSummary(
      "authentication-required",
      processed,
      synced,
      conflicts,
      failed,
      "An authenticated technician session matching this queue is required."
    );
  }

  if (!(await isNetworkAvailable())) {
    return createSummary(
      "offline",
      processed,
      synced,
      conflicts,
      failed,
      "No usable network connection is available. Pending actions remain saved."
    );
  }

  try {
    await recoverInterruptedJobActions(scope);
  } catch (error: unknown) {
    return createSummary(
      "failed",
      processed,
      synced,
      conflicts,
      failed,
      `Unable to recover the saved queue: ${getErrorMessage(error)}`
    );
  }

  let pendingActions: QueuedJobAction[];

  try {
    pendingActions = await getPendingJobActions(scope);
  } catch (error: unknown) {
    return createSummary(
      "failed",
      processed,
      synced,
      conflicts,
      failed,
      `Unable to read the saved queue: ${getErrorMessage(error)}`
    );
  }

  if (pendingActions.length === 0) {
    return createSummary(
      "empty",
      processed,
      synced,
      conflicts,
      failed,
      "There are no pending job actions."
    );
  }

  // Queue entries are returned in creation order. Stop at the first
  // unresolved operation so later actions cannot overtake it.
  for (const item of pendingActions) {
    if (!isSessionValidForScope(scope)) {
      return createSummary(
        "session-changed",
        processed,
        synced,
        conflicts,
        failed,
        "The authenticated technician changed. Synchronization stopped."
      );
    }

    let serverJob;

    try {
      // Always reconcile against the current server state before
      // deciding whether a queued action should be sent.
      serverJob = await getTechnicianJob(item.jobId);
    } catch (error: unknown) {
      const status = getHttpStatus(error);

      if (isNetworkUnavailableError(error)) {
        return createSummary(
          "network-error",
          processed,
          synced,
          conflicts,
          failed,
          "The server could not be reached. Pending actions were preserved."
        );
      }

      if (status === 401) {
        return createSummary(
          "authentication-required",
          processed,
          synced,
          conflicts,
          failed,
          "Authentication is required before synchronization can continue."
        );
      }

      if (status === 403 || status === 404) {
        try {
          await markJobActionConflict(
            scope,
            item.id,
            "The server no longer makes this job available to the authenticated technician."
          );

          conflicts += 1;
          processed += 1;
        } catch (queueError: unknown) {
          return createSummary(
            "failed",
            processed,
            synced,
            conflicts,
            failed,
            getErrorMessage(queueError)
          );
        }

        return createSummary(
          "conflict",
          processed,
          synced,
          conflicts,
          failed,
          "Job access or assignment changed. Review this action before continuing."
        );
      }

      if (status !== undefined && status >= 500) {
        return createSummary(
          "server-error",
          processed,
          synced,
          conflicts,
          failed,
          "The server returned an error while checking job state. No queued action was sent."
        );
      }

      return createSummary(
        "failed",
        processed,
        synced,
        conflicts,
        failed,
        `Unable to reconcile job ${item.jobId}: ${getErrorMessage(error)}`
      );
    }

    // Check authentication again before each state-changing request.
    if (!isSessionValidForScope(scope)) {
      return createSummary(
        "session-changed",
        processed,
        synced,
        conflicts,
        failed,
        "The technician session changed before the action could be sent."
      );
    }

    const currentStatus = normalizeStatus(serverJob.status);
    const transition = getActionTransition(item.action);

    // The desired state is already visible on the server. This is
    // how interrupted requests are reconciled without replaying them.
    if (transition.targetStatuses.includes(currentStatus)) {
      try {
        await markJobActionSynced(
          scope,
          item.id,
          currentStatus
        );

        synced += 1;
        processed += 1;
        continue;
      } catch (error: unknown) {
        return createSummary(
          "failed",
          processed,
          synced,
          conflicts,
          failed,
          `Unable to record confirmed server state: ${getErrorMessage(error)}`
        );
      }
    }

    // A previously attempted request has an uncertain result. If the
    // server still shows its source state, do not blindly replay it:
    // this queue version requires explicit reconciliation first.
    if (item.reconciliationRequired) {
      try {
        await markJobActionConflict(
          scope,
          item.id,
          transition.allowedSourceStatuses.includes(currentStatus)
            ? `The prior request has an uncertain result. The server still reports ${currentStatus}. Resolve this action before retrying.`
            : `The server reports ${currentStatus}, which does not confirm this action's target state.`,
          currentStatus
        );

        conflicts += 1;
        processed += 1;
      } catch (error: unknown) {
        return createSummary(
          "failed",
          processed,
          synced,
          conflicts,
          failed,
          getErrorMessage(error)
        );
      }

      return createSummary(
        "conflict",
        processed,
        synced,
        conflicts,
        failed,
        "An uncertain action requires review. Later queued actions were not sent."
      );
    }

    // Do not send an action when the server reports a state from
    // which the requested transition is not permitted.
    if (!transition.allowedSourceStatuses.includes(currentStatus)) {
      try {
        await markJobActionConflict(
          scope,
          item.id,
          `Cannot apply '${item.action}' while the server reports ${currentStatus}.`,
          currentStatus
        );

        conflicts += 1;
        processed += 1;
      } catch (error: unknown) {
        return createSummary(
          "failed",
          processed,
          synced,
          conflicts,
          failed,
          getErrorMessage(error)
        );
      }

      return createSummary(
        "conflict",
        processed,
        synced,
        conflicts,
        failed,
        `Job ${item.jobId} is now ${currentStatus}. Review the action before continuing.`
      );
    }

    let syncingItem: QueuedJobAction;

    try {
      syncingItem = await markJobActionSyncing(
        scope,
        item.id
      );
    } catch (error: unknown) {
      return createSummary(
        "failed",
        processed,
        synced,
        conflicts,
        failed,
        `Unable to mark the action as syncing: ${getErrorMessage(error)}`
      );
    }

    // Guard against an account change immediately before submission.
    if (!isSessionValidForScope(scope)) {
      try {
        await markJobActionFailed(
          scope,
          syncingItem.id,
          "The technician session changed before submission. Reconcile the server state before retrying."
        );

        failed += 1;
        processed += 1;
      } catch {
        // Keep the original session-change result.
      }

      return createSummary(
        "session-changed",
        processed,
        synced,
        conflicts,
        failed,
        "The technician session changed. Synchronization stopped."
      );
    }

    try {
      const response = await performTechnicianJobAction(
        syncingItem.jobId,
        syncingItem.action,
        syncingItem.payload as TechnicianJobActionPayload
      );

      if (response.success === false) {
        try {
          await markJobActionConflict(
            scope,
            syncingItem.id,
            response.message ?? "The server did not confirm the action.",
            response.status
          );

          conflicts += 1;
          processed += 1;
        } catch (error: unknown) {
          return createSummary(
            "failed",
            processed,
            synced,
            conflicts,
            failed,
            getErrorMessage(error)
          );
        }

        return createSummary(
          "conflict",
          processed,
          synced,
          conflicts,
          failed,
          response.message ?? "The server did not confirm the action."
        );
      }

      await markJobActionSynced(
        scope,
        syncingItem.id,
        response.status ?? transition.targetStatuses[0]
      );

      synced += 1;
      processed += 1;
    } catch (error: unknown) {
      const status = getHttpStatus(error);
      const message = getErrorMessage(error);

      if (isNetworkUnavailableError(error)) {
        try {
          await markJobActionPendingAfterUncertainResult(
            scope,
            syncingItem.id,
            error
          );
        } catch {
          // If persistence fails, do not attempt another request.
        }

        return createSummary(
          "network-error",
          processed,
          synced,
          conflicts,
          failed,
          "The action's result is uncertain. It will be reconciled against server state before any retry."
        );
      }

      if (status === 401) {
        try {
          await markJobActionFailed(
            scope,
            syncingItem.id,
            "Authentication is required before this action can be retried."
          );

          failed += 1;
          processed += 1;
        } catch {
          // Preserve the authentication result.
        }

        return createSummary(
          "authentication-required",
          processed,
          synced,
          conflicts,
          failed,
          "Sign in or restore the technician session before continuing."
        );
      }

      if (
        status === 400 ||
        status === 403 ||
        status === 404 ||
        status === 409 ||
        status === 422
      ) {
        try {
          await markJobActionConflict(
            scope,
            syncingItem.id,
            message,
            undefined
          );

          conflicts += 1;
          processed += 1;
        } catch (queueError: unknown) {
          return createSummary(
            "failed",
            processed,
            synced,
            conflicts,
            failed,
            getErrorMessage(queueError)
          );
        }

        return createSummary(
          "conflict",
          processed,
          synced,
          conflicts,
          failed,
          "The backend rejected the transition or access check. Review the current job state."
        );
      }

      // A server error may occur after the transaction commits but
      // before a successful response reaches the device.
      if (status !== undefined && status >= 500) {
        try {
          await markJobActionPendingAfterUncertainResult(
            scope,
            syncingItem.id,
            error
          );
        } catch {
          // Do not retry automatically if queue state cannot be saved.
        }

        return createSummary(
          "server-error",
          processed,
          synced,
          conflicts,
          failed,
          "The server returned an error. Reconcile the job state before retrying."
        );
      }

      try {
        await markJobActionFailed(
          scope,
          syncingItem.id,
          message
        );

        failed += 1;
        processed += 1;
      } catch {
        // Preserve the original failure.
      }

      return createSummary(
        "failed",
        processed,
        synced,
        conflicts,
        failed,
        message
      );
    }
  }

  return createSummary(
    "synced",
    processed,
    synced,
    conflicts,
    failed,
    "All eligible pending actions were reconciled or synchronized."
  );
}

/**
 * Synchronizes pending technician job actions in creation order.
 *
 * This function never submits reject or complete actions because those
 * operations have separate assignment, evidence, and completion flows.
 */
export function syncPendingJobActions(
  scope: JobActionQueueScope
): Promise<JobActionSyncSummary> {
  if (activeSyncPromise) {
    return Promise.resolve(
      createSummary(
        "already-syncing",
        0,
        0,
        0,
        0,
        "A synchronization run is already in progress."
      )
    );
  }

  const operation = runSynchronization(scope);

  activeSyncPromise = operation.finally(() => {
    activeSyncPromise = null;
  });

  return activeSyncPromise;
}