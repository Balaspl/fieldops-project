
import { apiClient } from "./client";

export type TechnicianStatusResponse = Record<string, unknown>;

/**
 * Retrieves the authenticated technician's current status.
 * The backend remains authoritative for availability and permissions.
 */
export async function getTechnicianStatus(): Promise<TechnicianStatusResponse> {
  const response = await apiClient.get<TechnicianStatusResponse>(
    "/api/technician/status"
  );

  return response.data;
}
