import {
  apiClient,
  isNetworkUnavailableError
} from "./client";

export type TechnicianJobAction =
  | "accept"
  | "reject"
  | "start"
  | "on-site"
  | "pause"
  | "resume"
  | "complete";

export interface TechnicianJobActionPayload {
  reason?: string;
  notes?: string;
  completion_notes?: string;
  photos?: string[];
  signature?: string | null;
  labour_cost?: number;
  material_cost?: number;
  latitude?: number;
  longitude?: number;
  accuracy?: number | null;
  captured_at?: string;
  [key: string]: unknown;
}

export interface TechnicianJobActionResponse {
  success?: boolean;
  message?: string;
  status?: string;
  job?: Record<string, unknown>;
  [key: string]: unknown;
}

/**
 * Indicates that a job action failed without a server response.
 * The server may still have received the request, so callers must
 * refresh the job state before allowing the technician to retry it.
 */
export class TechnicianJobActionNetworkError extends Error {
  readonly jobId: string;
  readonly action: TechnicianJobAction;
  readonly originalError: unknown;

  constructor(
    jobId: string,
    action: TechnicianJobAction,
    originalError: unknown
  ) {
    super(
      `Connection was lost while submitting the ${action} action for job ${jobId}. ` +
        "The server may have received the request. Refresh the job status before retrying."
    );

    this.name = "TechnicianJobActionNetworkError";
    this.jobId = jobId;
    this.action = action;
    this.originalError = originalError;
  }
}

/**
 * Sends a technician job action to the FieldOps backend.
 *
 * The backend remains responsible for validating job ownership,
 * tenant access, permissions, and legal status transitions.
 *
 * Job actions are not automatically queued or retried here because
 * the backend's idempotency guarantees are not established by this
 * API contract. A network failure is reported as an uncertain result.
 */
export async function performTechnicianJobAction(
  jobId: string | number,
  action: TechnicianJobAction,
  payload: TechnicianJobActionPayload = {}
): Promise<TechnicianJobActionResponse> {
  const jobIdString = String(jobId);
  const safeJobId = encodeURIComponent(jobIdString);

  const requestPayload: TechnicianJobActionPayload = {
    ...payload
  };

  if (action === "complete") {
    const completionNotes =
      requestPayload.completion_notes ?? requestPayload.notes;

    delete requestPayload.notes;

    if (completionNotes !== undefined) {
      requestPayload.completion_notes = completionNotes;
    }
  }

  try {
    const response =
      await apiClient.post<TechnicianJobActionResponse>(
        `/api/technician/jobs/${safeJobId}/${action}`,
        requestPayload
      );

    return response.data;
  } catch (error: unknown) {
    if (isNetworkUnavailableError(error)) {
      throw new TechnicianJobActionNetworkError(
        jobIdString,
        action,
        error
      );
    }

    throw error;
  }
}
