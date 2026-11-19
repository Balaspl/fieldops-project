
import { apiClient } from "./client";

export type TechnicianDashboardData = Record<string, unknown>;

export async function getTechnicianDashboard(): Promise<TechnicianDashboardData> {
  const response = await apiClient.get<TechnicianDashboardData>(
    "/api/technician/dashboard"
  );

  return response.data;
}
