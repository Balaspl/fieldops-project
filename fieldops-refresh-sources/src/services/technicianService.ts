/**
 * technicianService.ts
 * Centralized API service for the Technician module.
 */

import api from "./api";

/** Fetch all technicians */
export const getAllTechnicians = (params?: {
  search?: string;
  status?: string;
  zone?: string;
  skill?: string;
  page?: number;
  limit?: number;
}): Promise<any> => api.get("/technicians", { params });

/** Fetch all unique zones */
export const getUniqueZones = (): Promise<any> => api.get("/technicians/zones");

/** Fetch available technicians with workload details */
export const getAvailableTechnicians = (): Promise<any> => api.get("/technicians/available");

/** Update technician availability status */
export const updateTechnicianAvailability = (technicianId: string | number, technician_status: string): Promise<any> =>
  api.put(`/technicians/${technicianId}/availability`, { technician_status });

/** Get a single technician by ID */
export const getTechnicianById = (id: string | number): Promise<any> => api.get(`/technicians/${id}`);

/** Update technician details */
export const updateTechnician = (technicianId: string | number, technicianData: any): Promise<any> =>
  api.put(`/technicians/${technicianId}`, technicianData);

/** Delete a technician */
export const deleteTechnician = (technicianId: string | number): Promise<any> =>
  api.delete(`/technicians/${technicianId}`);

/** Create a technician */
export const createTechnician = (technicianData: any): Promise<any> =>
  api.post("/technicians", technicianData);

/** Fetch notification preferences for a technician */
export const getPreferences = (techId: string | number): Promise<any> =>
  api.get(`/technicians/${techId}/preferences`);

/** Update notification preferences for a technician */
export const updatePreferences = (techId: string | number, preferences: any): Promise<any> =>
  api.patch(`/technicians/${techId}/preferences`, preferences);

/** Reset notification preferences for a technician to defaults */
export const resetPreferences = (techId: string | number): Promise<any> =>
  api.post(`/technicians/${techId}/preferences/reset`);

/** Get nearest available technician for a job */
export const getNearestTechnician = (jobId: string | number): Promise<any> =>
  api.get(`/technicians/nearest`, { params: { job_id: jobId } });

