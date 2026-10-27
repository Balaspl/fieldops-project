import { apiClient } from "../api/client";
import type { TechnicianLocation } from "./locationService";

export interface GpsPingResponse {
  status?: string;
  message?: string;
  ping_id?: string;
  technician_id?: string;
  job_id?: string;
  timestamp?: string;
}

export interface GpsPingContext {
  technicianId: string | number;
  jobId: string | number;
  tenantId: string | number;
}

export interface GpsAvailabilityResponse {
  status?: string;
  technician_id?: string;
  latitude?: number;
  longitude?: number;
  timestamp?: string;
}

function requireTenantId(tenantId: string | number): string {
  const value = String(tenantId).trim();

  if (!value) {
    throw new Error("Authenticated tenant context is required for GPS.");
  }

  return value;
}

export async function sendGpsPing(
  location: TechnicianLocation,
  context: GpsPingContext
): Promise<GpsPingResponse> {
  const technicianId = String(context.technicianId).trim();
  const jobId = String(context.jobId).trim();
  const tenantId = requireTenantId(context.tenantId);

  if (!technicianId || !jobId) {
    throw new Error("Technician and job identifiers are required for GPS.");
  }

  const response = await apiClient.post<GpsPingResponse>(
    "/api/v1/gps/ping",
    {
      technician_id: technicianId,
      job_id: jobId,
      latitude: location.latitude,
      longitude: location.longitude,
      accuracy: location.accuracy,
      timestamp: location.capturedAt
    },
    {
      headers: {
        "X-Tenant-ID": tenantId
      }
    }
  );

  return response.data;
}

export async function sendTechnicianAvailabilityPing(
  location: TechnicianLocation,
  tenantIdValue: string | number
): Promise<GpsAvailabilityResponse> {
  const tenantId = requireTenantId(tenantIdValue);

  const response = await apiClient.post<GpsAvailabilityResponse>(
    "/api/v1/gps/availability",
    {
      latitude: location.latitude,
      longitude: location.longitude,
      accuracy: location.accuracy,
      timestamp: location.capturedAt
    },
    {
      headers: {
        "X-Tenant-ID": tenantId
      }
    }
  );

  return response.data;
}