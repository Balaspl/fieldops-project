/**
 * Technician Portal API service.
 * All API calls for the technician portal.
 */
import api from "./api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface TechnicianDashboardResponse {
  total_assigned?: number;
  active_jobs?: number;
  completed_today?: number;
  pending_acceptance?: number;
  total_completed?: number;
  rejected_jobs?: number;
  technician_status?: string | null;
  profile_completed?: boolean;
}

export interface TechnicianStatusUpdateResponse {
  technician_id: number;
  technician_status: string;
}




// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------

export const getTechnicianProfile = () =>
  api.get("/api/technician/profile");

export const createTechnicianProfile = (data: any) =>
  api.post("/api/technician/profile", data);

export const updateTechnicianProfile = (data: any) =>
  api.put("/api/technician/profile", data);

export const changeTechnicianPassword = (data: any) =>
  api.post("/api/technician/change-password", data);

// ---------------------------------------------------------------------------
// Jobs
// ---------------------------------------------------------------------------

export const getTechnicianJobs = (status?: string) =>
  api.get("/api/technician/jobs", {
    params: status ? { status } : {},
  });

export const getTechnicianJobHistory = () =>
  api.get("/api/technician/jobs/history");

export const getTechnicianJobDetail = (jobId: number) =>
  api.get(`/api/technician/jobs/${jobId}`);

export const acceptTechnicianJob = (jobId: number) =>
  api.post(`/api/technician/jobs/${jobId}/accept`);

export const rejectTechnicianJob = (
  jobId: number,
  reason: string,
) =>
  api.post(`/api/technician/jobs/${jobId}/reject`, {
    reason,
  });

export const startTechnicianJob = (jobId: number) =>
  api.post(`/api/technician/jobs/${jobId}/start`);

export const onSiteTechnicianJob = (jobId: number) =>
  api.post(`/api/technician/jobs/${jobId}/on-site`);

// ---------------------------------------------------------------------------
// Job expenses
// ---------------------------------------------------------------------------

export interface TechnicianJobExpense {
  id: number;
  job_id: number;
  technician_id: number;
  amount: string | number;
  description: string;
  submitted_at: string;
  created_at: string;
  updated_at: string;
}

export interface TechnicianJobExpenseCreate {
  amount: string;
  description: string;
}

export const submitTechnicianJobExpense = (
  jobId: number,
  data: TechnicianJobExpenseCreate,
) =>
  api.post<TechnicianJobExpense>(
    `/api/technician/jobs/${jobId}/expenses`,
    data,
  );

export const pauseTechnicianJob = (jobId: number) =>
  api.post(`/api/technician/jobs/${jobId}/pause`);

export const resumeTechnicianJob = (jobId: number) =>
  api.post(`/api/technician/jobs/${jobId}/resume`);

export const completeTechnicianJob = (
  jobId: number,
  data: any,
) =>
  api.post(
    `/api/technician/jobs/${jobId}/complete`,
    data,
  );

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

export const getTechnicianNotifications = () =>
  api.get("/api/technician/notifications");

export const markTechnicianNotificationRead = (
  id: string,
) =>
  api.put(
    `/api/technician/notifications/${id}/read`,
  );

export const markAllTechnicianNotificationsRead = () =>
  api.put("/api/technician/notifications/read-all");

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

export const getTechnicianDashboard = () =>
  api.get<TechnicianDashboardResponse>(
    "/api/technician/dashboard",
  );

// ---------------------------------------------------------------------------
// Billing Reports
// ---------------------------------------------------------------------------

export const getTechnicianBillingReports = () =>
  api.get("/api/technician/billing-reports");

export const downloadTechnicianBillingReport = async (
  closureId: number,
) => {
  const response = await api.get<Blob>(
    `/api/technician/billing-reports/${closureId}/pdf`,
    {
      responseType: "blob",
    },
  );

  const blob = new Blob(
    [response.data],
    {
      type: "application/pdf",
    },
  );

  const url = window.URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = url;
  link.download = `billing_report_${closureId}.pdf`;

  document.body.appendChild(link);
  link.click();
  link.remove();

  window.setTimeout(() => {
    window.URL.revokeObjectURL(url);
  }, 1000);

  return response;
};

// ---------------------------------------------------------------------------
// Technician Attendance / Availability
// ---------------------------------------------------------------------------

export const updateTechnicianStatus = (
  technician_status: string,
) =>
  api.put<TechnicianStatusUpdateResponse>(
    "/api/technician/status",
    {
      technician_status,
    },
  );