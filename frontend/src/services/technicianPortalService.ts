/**
 * Technician Portal API service.
 * All API calls for the technician portal.
 */
import api from "./api";

// Profile
export const getTechnicianProfile = () => api.get("/api/technician/profile");
export const createTechnicianProfile = (data: any) => api.post("/api/technician/profile", data);
export const updateTechnicianProfile = (data: any) => api.put("/api/technician/profile", data);
export const changeTechnicianPassword = (data: any) => api.post("/api/technician/change-password", data);

// Jobs
export const getTechnicianJobs = (status?: string) =>
  api.get("/api/technician/jobs", { params: status ? { status } : {} });
export const getTechnicianJobHistory = () => api.get("/api/technician/jobs/history");
export const getTechnicianJobDetail = (jobId: number) => api.get(`/api/technician/jobs/${jobId}`);
export const acceptTechnicianJob = (jobId: number) => api.post(`/api/technician/jobs/${jobId}/accept`);
export const rejectTechnicianJob = (jobId: number, reason: string) =>
  api.post(`/api/technician/jobs/${jobId}/reject`, { reason });
export const startTechnicianJob = (jobId: number) => api.post(`/api/technician/jobs/${jobId}/start`);
export const onSiteTechnicianJob = (jobId: number) => api.post(`/api/technician/jobs/${jobId}/on-site`);
export const pauseTechnicianJob = (jobId: number) => api.post(`/api/technician/jobs/${jobId}/pause`);
export const resumeTechnicianJob = (jobId: number) => api.post(`/api/technician/jobs/${jobId}/resume`);
export const completeTechnicianJob = (jobId: number, data: any) =>
  api.post(`/api/technician/jobs/${jobId}/complete`, data);

// Notifications
export const getTechnicianNotifications = () => api.get("/api/technician/notifications");
export const markTechnicianNotificationRead = (id: string) =>
  api.put(`/api/technician/notifications/${id}/read`);
export const markAllTechnicianNotificationsRead = () =>
  api.put("/api/technician/notifications/read-all");

// Dashboard
export const getTechnicianDashboard = () => api.get("/api/technician/dashboard");


// Billing Reports
export const getTechnicianBillingReports = () =>
  api.get("/api/technician/billing-reports");

export const downloadTechnicianBillingReport = (closureId: number) =>
  api.get(`/api/technician/billing-reports/${closureId}/pdf`, {
    responseType: "blob",
  });
