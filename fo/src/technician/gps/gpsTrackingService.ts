import {
  getCurrentTechnicianLocation,
  type TechnicianLocation
} from "./locationService";

import {
  sendGpsPing,
  type GpsPingContext,
  type GpsPingResponse
} from "./gpsService";

export interface GpsTrackingResult {
  location: TechnicianLocation;
  response: GpsPingResponse;
}

/**
 * Captures one foreground location and submits it for an active job.
 *
 * The caller must supply identifiers from the authenticated session and
 * the job currently returned by the backend. This function does not
 * authorize a technician or determine whether a job is active.
 */
export async function captureAndSendGpsPing(
  context: GpsPingContext
): Promise<GpsTrackingResult> {
  const location = await getCurrentTechnicianLocation();
  const response = await sendGpsPing(location, context);

  return {
    location,
    response
  };
}