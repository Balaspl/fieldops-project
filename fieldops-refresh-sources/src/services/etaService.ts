import api from "./api";

export interface ETAResponse {
  eta: string;
  duration_minutes: number;
  distance_meters: number;
  origin: { lat: number; lng: number };
  destination: { lat: number; lng: number };
}

/**
 * Calculates live ETA for a single technician to a job site based on live GPS tracking.
 */
export const getTechnicianETA = async (
  technicianId: string,
  jobId: number
): Promise<ETAResponse | null> => {
  try {
    const response = await api.get('/api/v1/eta', {
      params: {
        technician_id: technicianId,
        job_id: jobId,
      },
    });
    return response.data;
  } catch (error) {
    console.error("Failed to fetch technician ETA:", error);
    return null;
  }
};
