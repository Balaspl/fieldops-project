import { apiClient } from "./client";

export interface TechnicianJob {
  id: string | number;
  job_number?: string;
  title?: string;
  description?: string;
  status: string;
  priority?: string;
  scheduled_at?: string;
  assigned_at?: string | null;
  customer_name?: string;
  address?: string;
  [key: string]: unknown;
}

export interface TechnicianJobListResponse {
  items: TechnicianJob[];
  total?: number;
  page?: number;
  page_size?: number;
}

export type TechnicianJobCollection =
  | TechnicianJob[]
  | TechnicianJobListResponse;

export interface TechnicianJobQuery {
  page?: number;
  page_size?: number;
  status?: string;
  priority?: string;
  search?: string;
}

export async function getTechnicianJobs(
  query: TechnicianJobQuery = {}
): Promise<TechnicianJobCollection> {
  const response = await apiClient.get<TechnicianJobCollection>(
    "/api/technician/jobs",
    { params: query }
  );

  return response.data;
}

export async function getTechnicianJobHistory(
  query: TechnicianJobQuery = {}
): Promise<TechnicianJobCollection> {
  const response = await apiClient.get<TechnicianJobCollection>(
    "/api/technician/jobs/history",
    { params: query }
  );

  return response.data;
}

export async function getTechnicianJob(
  jobId: string | number
): Promise<TechnicianJob> {
  const response = await apiClient.get<TechnicianJob>(
    `/api/technician/jobs/${encodeURIComponent(String(jobId))}`
  );

  return response.data;
}
