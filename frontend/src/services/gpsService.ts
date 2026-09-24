import api from './api';

export interface GPSPingPayload {
  technician_id: string;
  job_id: string;
  latitude: number;
  longitude: number;
  timestamp: string;
  accuracy?: number | null;
  altitude?: number | null;
}

/** Send the current device position for one authorized active technician job. */
export const sendGPSPing = (tenantId: string, payload: GPSPingPayload) =>
  api.post('/api/v1/gps/ping', payload, {
    headers: { 'X-Tenant-ID': tenantId },
  });

export interface GPSHistoryPoint {
  id: string;
  technician_id: string;
  job_id: string;
  latitude: number;
  longitude: number;
  timestamp: string;
  accuracy: number | null;
  altitude: number | null;
  tenant_id: string;
  created_at: string;
}

export const getGPSHistory = async (
  technicianId: string,
  params?: { job_id?: string; start_time?: string; end_time?: string }
): Promise<GPSHistoryPoint[]> => {
  const response = await api.get<GPSHistoryPoint[]>(`/api/v1/gps/history/${technicianId}`, { params });
  return response.data;
};
