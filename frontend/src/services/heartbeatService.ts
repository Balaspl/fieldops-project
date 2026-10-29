/**
 * heartbeatService.ts
 * Manages the technician heartbeat loop, availability queries, and cache control.
 * Covers: POST /technicians/{id}/heartbeat
 *         GET  /technicians/{id}/availability
 *         POST /technicians/{id}/invalidate-cache
 *         GET  /technicians/metrics
 */

import api from "./api";

let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
export const HEARTBEAT_INTERVAL_MS = 35_000;

export interface HeartbeatPayload {
  last_lat?: number | null;
  last_lng?: number | null;
}

/** Send a single heartbeat ping to keep the technician marked as online */
export const sendHeartbeat = async (
  techId: string,
  payload: HeartbeatPayload = {}
): Promise<any> => {
  try {
    console.log(
      "HEARTBEAT REQUEST:",
      techId
    );

    const response = await api.post(
      `/technicians/${techId}/heartbeat`,
      payload
    );

    console.log(
      "HEARTBEAT SUCCESS:",
      response.status,
      response.data
    );

    return response.data;
  } catch (error: any) {
    console.error(
      "HEARTBEAT FAILED:",
      error?.response?.status,
      error?.response?.data,
      error
    );

    return null;
  }
};

/**
 * Start a recurring heartbeat loop every 35 seconds. The gap exceeds the
 * backend's 25-second anti-burst TTL to tolerate timer and network jitter.
 * Call stopHeartbeatLoop() to cancel on logout/unmount.
 */
export const startHeartbeatLoop = (
  techId: string,
  intervalMs = HEARTBEAT_INTERVAL_MS,
  getLocation?: () => HeartbeatPayload
): void => {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
  }

  console.log("STARTING HEARTBEAT LOOP:", techId);

  const sendHeartbeatWithLocation = async () => {
    let payload: HeartbeatPayload = {};

    try {
      if (getLocation) {
        payload = getLocation();
      } else if (
        typeof navigator !== "undefined" &&
        navigator.geolocation
      ) {
        payload = await new Promise<HeartbeatPayload>((resolve) => {
          navigator.geolocation.getCurrentPosition(
            (position) => {
              resolve({
                last_lat: position.coords.latitude,
                last_lng: position.coords.longitude,
              });
            },
            (error) => {
              console.warn(
                "Could not read technician GPS location:",
                error.message
              );
              resolve({});
            },
            {
              enableHighAccuracy: true,
              maximumAge: 10000,
              timeout: 10000,
            }
          );
        });
      }

      console.log("HEARTBEAT GPS PAYLOAD:", payload);
      await sendHeartbeat(techId, payload);
    } catch (error) {
      console.error("Heartbeat GPS error:", error);
      await sendHeartbeat(techId, {});
    }
  };

  // Send a heartbeat immediately, then at the configured interval.
  void sendHeartbeatWithLocation();

  heartbeatTimer = setInterval(() => {
    void sendHeartbeatWithLocation();
  }, intervalMs);
};

/** Stop the heartbeat loop */
export const stopHeartbeatLoop = (): void => {
  if (heartbeatTimer) {
    console.log("STOPPING HEARTBEAT LOOP");

    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
};

/** Get real-time availability status from Redis cache (or DB fallback) */
export const getTechnicianAvailability = async (
  techId: string
): Promise<any> => {
  try {
    const response = await api.get(
      `/technicians/${techId}/availability`
    );

    return response.data;
  } catch (error) {
    console.error(
      "Failed to fetch technician availability:",
      error
    );

    return null;
  }
};

/** Invalidate the Redis availability cache for a technician */
export const invalidateTechnicianCache = async (
  techId: string
): Promise<any> => {
  try {
    const response = await api.post(
      `/technicians/${techId}/invalidate-cache`
    );

    return response.data;
  } catch (error) {
    console.error(
      "Failed to invalidate technician cache:",
      error
    );

    return null;
  }
};

/** Get offline event metrics for the current hour (from Redis) */
export const getTechnicianMetrics = async (): Promise<{
  offline_events_current_hour: number;
}> => {
  try {
    const response = await api.get(
      "/technicians/metrics"
    );

    return response.data;
  } catch (error) {
    console.error(
      "Failed to fetch technician metrics:",
      error
    );

    return {
      offline_events_current_hour: 0,
    };
  }
};
