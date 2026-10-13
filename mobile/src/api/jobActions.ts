
import { apiClient } from "./client";

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
 * Sends a technician job action to the FieldOps backend.
 *
 * The backend remains responsible for validating job ownership,
 * tenant access, permissions, and legal status transitions.
 */
export async function performTechnicianJobAction(
  jobId: string | number,
  action: TechnicianJobAction,
  payload: TechnicianJobActionPayload = {}
): Promise<TechnicianJobActionResponse> {
  const safeJobId = encodeURIComponent(String(jobId));

  const response =
    await apiClient.post<TechnicianJobActionResponse>(
      `/api/technician/jobs/${safeJobId}/${action}`,
      payload
    );

  return response.data;
}
