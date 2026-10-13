
import {
  getCurrentTechnicianLocation,
  type TechnicianLocation
} from "./locationService";
import {
  sendGpsPing,
  type GpsPingResponse
} from "./gpsService";

export interface GpsTrackingResult {
  location: TechnicianLocation;
  response: GpsPingResponse;
}

/**
 * Gets the technician's current foreground location and submits one GPS ping.
 *
 * This function does not start background tracking or repeatedly collect
 * location data. It should be called only when the app needs a GPS update.
 */
export async function captureAndSendGpsPing(): Promise<GpsTrackingResult> {
  const location = await getCurrentTechnicianLocation();
  const response = await sendGpsPing(location);

  return {
    location,
    response
  };
}
