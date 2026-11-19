/**
 * escalationService.ts
 * API service for the Escalations module.
 * Covers: POST /escalations/{job_id}/extend-sla
 *         POST /escalations/{job_id}/cancel
 *         POST /escalations/{job_id}/force-assign
 */

import api from "./api";

/** Extend the SLA deadline for an escalated job by N minutes */
export const extendSLA = async (
  jobId: string | number,
  minutes: number
): Promise<any> => {
  const response = await api.post(`/escalations/${jobId}/extend-sla`, { minutes });
  return response.data;
};

/** Cancel an escalated job with a reason */
export const cancelEscalatedJob = async (
  jobId: string | number,
  reason: string
): Promise<any> => {
  const response = await api.post(`/escalations/${jobId}/cancel`, { reason });
  return response.data;
};

/** Force-assign an escalated job to a specific technician */
export const forceAssignEscalation = async (
  jobId: string | number,
  techId: string,
  reason: string
): Promise<any> => {
  const response = await api.post(`/escalations/${jobId}/force-assign`, {
    tech_id: techId,
    reason,
  });
  return response.data;
};
