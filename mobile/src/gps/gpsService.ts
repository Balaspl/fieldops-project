
import { apiClient } from "../api/client";
import type { TechnicianLocation } from "./locationService";

export interface GpsPingResponse {
  success?: boolean;
  message?: string;
}

export async function sendGpsPing(
  location: TechnicianLocation
): Promise<GpsPingResponse> {
  const response = await apiClient.post<GpsPingResponse>(
    "/api/v1/gps/ping",
    {
      latitude: location.latitude,
      longitude: location.longitude,
      accuracy: location.accuracy,
      captured_at: location.capturedAt
    }
  );

  return response.data;
}
