import { apiClient } from "./client";

export const customerApi = {
  dashboard: async () => (await apiClient.get("/api/customer/dashboard")).data,
  requests: async () => (await apiClient.get("/api/customer/service-requests")).data,
  request: async (id: string) => (await apiClient.get(`/api/customer/service-requests/${encodeURIComponent(id)}`)).data,
  jobs: async () => (await apiClient.get("/api/customer/jobs")).data,
  job: async (id: string) => (await apiClient.get(`/api/customer/jobs/${encodeURIComponent(id)}`)).data,
};

export const technicianApi = {
  dashboard: async () => (await apiClient.get("/api/technician/dashboard")).data,
  jobs: async () => (await apiClient.get("/api/technician/jobs")).data,
  job: async (id: string) => (await apiClient.get(`/api/technician/jobs/${encodeURIComponent(id)}`)).data,
  action: async (id: string, action: string, payload?: unknown) =>
    (await apiClient.post(`/api/technician/jobs/${encodeURIComponent(id)}/${action}`, payload ?? {})).data,
};

export const superAdminApi = {
  dashboard: async () => {
    const results = await Promise.allSettled([
      apiClient.get("/jobs/stats", { params: { time_range: "week" } }),
      apiClient.get("/planning/kpi"),
      apiClient.get("/jobs", { params: { page: 1, limit: 8 } }),
      apiClient.get("/technicians", { params: { page: 1, limit: 100 } }),
    ]);
    return results.map((result) => result.status === "fulfilled" ? result.value.data : null);
  },
  jobs: async () => (await apiClient.get("/jobs", { params: { page: 1, limit: 50 } })).data,
  users: async () => (await apiClient.get("/technicians", { params: { page: 1, limit: 100 } })).data,
  organizations: async () => (await apiClient.get("/organizations", { params: { page: 1, limit: 50, all_tenants: true } })).data,
};

export function recordsFrom(value: unknown): Record<string, unknown>[] {
  if (Array.isArray(value)) return value.filter((item): item is Record<string, unknown> => !!item && typeof item === "object");
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["items", "results", "jobs", "requests", "technicians", "organizations", "data"]) {
      if (Array.isArray(record[key])) return recordsFrom(record[key]);
    }
  }
  return [];
}
