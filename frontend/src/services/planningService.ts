/**
 * planningService.ts
 * Centralized API service for the Planning Dashboard.
 */

import api from "./api";

// Common error handler
const handleApiError = (error: any) => {
  console.error("API Error:", error?.response?.data || error.message);
  throw error;
};

/**
 * Fetch all technicians.
 */
export const getTechnicians = async (): Promise<any> => {
  try {
    return await api.get("/technicians");
  } catch (error) {
    handleApiError(error);
  }
};

/**
 * Fetch available technicians.
 */
export const getAvailableTechnicians = async (): Promise<any> => {
  try {
    return await api.get("/technicians/available");
  } catch (error) {
    handleApiError(error);
  }
};

/**
 * Update technician availability.
 */
export const updateTechnicianAvailability = async (
  technicianId: string | number,
  technician_status: string
): Promise<any> => {
  try {
    return await api.put(`/technicians/${technicianId}/availability`, {
      technician_status,
    });
  } catch (error) {
    handleApiError(error);
  }
};

/**
 * Fetch pending jobs.
 */
export const getPendingJobs = async (params?: {
  search?: string;
  page?: number;
  limit?: number;
  active_filter?: string;
}): Promise<any> => {
  try {
    return await api.get("/jobs/pending", { params });
  } catch (error) {
    handleApiError(error);
  }
};

/**
 * Fetch planned assignments.
 */
export const getPlannedAssignments = async (params?: {
  search?: string;
  page?: number;
  limit?: number;
}): Promise<any> => {
  try {
    return await api.get("/planned-assignments", { params });
  } catch (error) {
    handleApiError(error);
  }
};

/**
 * Assign technician to job.
 */
export const assignJob = async (jobId: string | number, technicianId: string | number): Promise<any> => {
  try {
    return await api.post("/assign-job", {
      job_id: jobId,
      technician_id: technicianId,
    });
  } catch (error) {
    handleApiError(error);
  }
};

/**
 * Fetch dashboard stats.
 */
export const getDashboardStats = async (timeRange?: string): Promise<any> => {
  try {
    return await api.get("/jobs/stats", {
      params: timeRange ? { time_range: timeRange } : undefined
    });
  } catch (error) {
    handleApiError(error);
  }
};

/**
 * Fetch all jobs.
 */
export const getJobs = async (): Promise<any> => {
  try {
    return await api.get("/jobs");
  } catch (error) {
    handleApiError(error);
  }
};

export const manualAssign = async (jobId: string | number, technicianId: string | number): Promise<any> => {
  try {
    return await api.post(`/assign-job`, {
      job_id: jobId,
      technician_id: technicianId,
    });
  } catch (error) {
    handleApiError(error);
  }
};

/**
 * Force assign a technician to a job, bypassing planning constraints.
 */
export const forceAssignJob = async (jobId: string | number, technicianId: string | number, justification: string, role = "dispatcher"): Promise<any> => {
  try {
    return await api.post(`/technicians/assignments/${jobId}/override`, {
      technician_id: String(technicianId),
      justification: justification
    });
  } catch (error) {
    handleApiError(error);
  }
};

/**
 * Fetch a single job by ID.
 */
export const getJob = async (jobId: string | number): Promise<any> => {
  try {
    return await api.get(`/jobs/${jobId}`);
  } catch (error) {
    handleApiError(error);
  }
};

/**
 * Fetch manual override history for a job.
 */
export const getOverrideHistory = async (jobId: string | number): Promise<any> => {
  try {
    return await api.get(`/jobs/${jobId}/override-history`);
  } catch (error) {
    handleApiError(error);
  }
};

/**
 * Trigger AI candidate ranking for a job.
 */
export const getJobPlan = async (jobId: string | number, tenantId: string = "default-tenant", adminOverride: boolean = false): Promise<any> => {
  try {
    const response = await api.post(`/jobs/${jobId}/plan`, null, {
      params: { admin_override: adminOverride },
      headers: { "X-Tenant-ID": tenantId }
    });
    return response.data;
  } catch (error) {
    handleApiError(error);
  }
};

/**
 * Fetch override audit trail for a job.
 */
export const getAuditOverrides = async (jobId: string | number, tenantId: string = "default-tenant"): Promise<any> => {
  try {
    const response = await api.get(`/audit/overrides/${jobId}`, {
      headers: { "X-Tenant-ID": tenantId }
    });
    return response.data;
  } catch (error) {
    handleApiError(error);
  }
};

/**
 * Assign job directly (via jobs router assign endpoint).
 */
export const assignJobDirect = async (
  jobId: string | number,
  techId: string,
  justification: string,
  skipSkillCheck: boolean = false,
  skipWorkloadCheck: boolean = false,
  tenantId: string = "default-tenant"
): Promise<any> => {
  try {
    const response = await api.post(`/jobs/${jobId}/assign`, {
      tech_id: techId,
      justification,
      skip_skill_check: skipSkillCheck,
      skip_workload_check: skipWorkloadCheck
    }, {
      headers: { "X-Tenant-ID": tenantId }
    });
    return response.data;
  } catch (error) {
    handleApiError(error);
  }
};

export interface JobClosureData {
  work_summary: string;
  before_images?: string[];
  after_images: string[];
  labour_cost: number;
  material_cost: number;
}

/**
  Submit job closure details.
 */
export const closeJob = async (jobId: string | number, data: JobClosureData): Promise<any> => {
  try {
    const response = await api.post(`/jobs/${jobId}/close`, data);
    return response.data;
  } catch (error: any) {
    try {
      const fallback = await api.post(`/api/technician/jobs/${jobId}/complete`, {
        completion_notes: data.work_summary,
        photos: data.after_images,
        labour_cost: data.labour_cost,
        material_cost: data.material_cost,
      });
      return fallback.data;
    } catch (fallbackError) {
      handleApiError(error);
    }
  }
};

/**
  Fetch job closure details for a completed job.
 */
export const getJobClosure = async (jobId: string | number): Promise<any> => {
  try {
    const response = await api.get(`/jobs/${jobId}/closure`);
    return response.data;
  } catch (error) {
    handleApiError(error);
  }
};



