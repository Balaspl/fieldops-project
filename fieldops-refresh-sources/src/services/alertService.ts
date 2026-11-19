/**
 * alertService.ts
 * API service for the Dispatcher Alerts module.
 * Covers: GET  /alerts/
 *         POST /alerts/{alert_id}/acknowledge
 */

import api from "./api";

/** Fetch all dispatcher alerts (unacknowledged, latest 50) */
export const getAlerts = async (): Promise<any[]> => {
  try {
    const response = await api.get("/alerts/");
    return response.data || [];
  } catch (error) {
    console.error("Failed to fetch alerts:", error);
    return [];
  }
};

/** Acknowledge a specific alert — marks it as seen by the dispatcher */
export const acknowledgeAlert = async (
  alertId: string,
  acknowledged = true
): Promise<any> => {
  const response = await api.post(`/alerts/${alertId}/acknowledge`, {
    acknowledged,
  });
  return response.data;
};
