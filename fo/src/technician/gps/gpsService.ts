
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
    throw new Error(
      "Authenticated tenant context is required for GPS."
    );
  }

  return value;
}

function validateCoordinates(location: TechnicianLocation): void {
  if (
    !Number.isFinite(location.latitude) ||
    !Number.isFinite(location.longitude) ||
    location.latitude < -90 ||
    location.latitude > 90 ||
    location.longitude < -180 ||
    location.longitude > 180
  ) {
    throw new Error("Invalid GPS coordinates.");
  }
}

/**
 * Send technician GPS location for an active job.
 * Backend endpoint: POST /api/v1/gps/ping
 */
export async function sendGpsPing(
  location: TechnicianLocation,
  context: GpsPingContext
): Promise<GpsPingResponse> {
  const technicianId = String(context.technicianId).trim();
  const jobId = String(context.jobId).trim();
  const tenantId = requireTenantId(context.tenantId);

  if (!technicianId || !jobId) {
    throw new Error(
      "Technician and job identifiers are required for GPS."
    );
  }

  validateCoordinates(location);

  const payload = {
    technician_id: technicianId,
    job_id: jobId,
    latitude: location.latitude,
    longitude: location.longitude,
    accuracy: location.accuracy,
    timestamp: location.capturedAt,
  };

  console.log("[GPS PING] Sending active-job location", {
    technicianId,
    jobId,
    tenantId,
    latitude: location.latitude,
    longitude: location.longitude,
    accuracy: location.accuracy,
    capturedAt: location.capturedAt,
  });

  try {
    const response = await apiClient.post<GpsPingResponse>(
      "/api/v1/gps/ping",
      payload,
      {
        headers: {
          "X-Tenant-ID": tenantId,
        },
      }
    );

    console.log("[GPS PING] Backend response", {
      httpStatus: response.status,
      response: response.data,
      jobId,
      technicianId,
    });

    return response.data;
  } catch (error: any) {
    console.error("[GPS PING] Request failed", {
      message: error?.message,
      httpStatus: error?.response?.status,
      responseData: error?.response?.data,
      url: error?.config?.url,
      method: error?.config?.method,
      jobId,
      technicianId,
      tenantId,
    });

    throw error;
  }
}

/**
 * Send technician GPS location when available,
 * without requiring an active job.
 * Backend endpoint: POST /api/v1/gps/availability
 */
export async function sendTechnicianAvailabilityPing(
  location: TechnicianLocation,
  tenantIdValue: string | number
): Promise<GpsAvailabilityResponse> {
  const tenantId = requireTenantId(tenantIdValue);

  validateCoordinates(location);

  const payload = {
    latitude: location.latitude,
    longitude: location.longitude,
    accuracy: location.accuracy,
    timestamp: location.capturedAt,
  };

  console.log("[GPS AVAILABILITY] Sending location", {
    tenantId,
    latitude: location.latitude,
    longitude: location.longitude,
    accuracy: location.accuracy,
    capturedAt: location.capturedAt,
  });

  try {
    const response = await apiClient.post<GpsAvailabilityResponse>(
      "/api/v1/gps/availability",
      payload,
      {
        headers: {
          "X-Tenant-ID": tenantId,
        },
      }
    );

    console.log("[GPS AVAILABILITY] Backend response", {
      httpStatus: response.status,
      response: response.data,
    });

    return response.data;
  } catch (error: any) {
    console.error("[GPS AVAILABILITY] Request failed", {
      message: error?.message,
      httpStatus: error?.response?.status,
      responseData: error?.response?.data,
      url: error?.config?.url,
      method: error?.config?.method,
      tenantId,
    });

    throw error;
  }
}

/**
 * Retrieve the technician's latest availability location.
 * Backend endpoint: GET /api/v1/gps/availability
 */
export async function getTechnicianAvailabilityLocation(
  tenantIdValue: string | number
): Promise<GpsAvailabilityResponse> {
  const tenantId = requireTenantId(tenantIdValue);

  console.log("[GPS AVAILABILITY] Fetching latest location", {
    tenantId,
  });

  try {
    const response = await apiClient.get<GpsAvailabilityResponse>(
      "/api/v1/gps/availability",
      {
        headers: {
          "X-Tenant-ID": tenantId,
        },
      }
    );

    console.log("[GPS AVAILABILITY] Latest location response", {
      httpStatus: response.status,
      response: response.data,
    });

    return response.data;
  } catch (error: any) {
    console.error("[GPS AVAILABILITY] Fetch failed", {
      message: error?.message,
      httpStatus: error?.response?.status,
      responseData: error?.response?.data,
      url: error?.config?.url,
      tenantId,
    });

    throw error;
  }
}
