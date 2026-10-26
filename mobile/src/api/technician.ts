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
  service_type?: string;
  issue_description?: string;
  location?: string;
  site_address?: string;
  site_latitude?: number | null;
  site_longitude?: number | null;
  preferred_service_date?: string;
  contact_number?: string;
  required_skill?: string;
  sla_deadline?: string;
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
  status?: string;
}

interface TechnicianJobApiResponse {
  id: string | number;
  job_number?: string | number | null;
  title?: string | null;
  description?: string | null;
  status?: string | null;
  priority?: string | null;
  scheduled_at?: string | null;
  assigned_at?: string | null;
  customer_name?: string | null;
  address?: string | null;
  service_type?: string | null;
  issue_description?: string | null;
  location?: string | null;
  site_address?: string | null;
  site_latitude?: number | null;
  site_longitude?: number | null;
  preferred_service_date?: string | null;
  contact_number?: string | null;
  required_skill?: string | null;
  sla_deadline?: string | null;
  [key: string]: unknown;
}

function firstText(
  ...values: (string | null | undefined)[]
): string | undefined {
  return values.find(
    (value) => typeof value === "string" && value.trim().length > 0
  )?.trim();
}

/**
 * Adapts the backend's job response fields for the existing mobile screens.
 * Authorization and job state remain backend responsibilities.
 */
function normalizeTechnicianJob(
  job: TechnicianJobApiResponse
): TechnicianJob {
  return {
    ...job,
    id: job.id,
    job_number: String(job.job_number ?? job.id),
    title: firstText(job.title, job.service_type) ?? "Service job",
    description: firstText(job.description, job.issue_description),
    status: firstText(job.status) ?? "UNKNOWN",
    priority: firstText(job.priority),
    scheduled_at:
      firstText(job.scheduled_at, job.preferred_service_date),
    assigned_at: firstText(job.assigned_at) ?? null,
    customer_name: firstText(job.customer_name),
    address: firstText(job.address, job.site_address, job.location),
    service_type: firstText(job.service_type),
    issue_description: firstText(job.issue_description),
    location: firstText(job.location),
    site_address: firstText(job.site_address),
    site_latitude: job.site_latitude,
    site_longitude: job.site_longitude,
    preferred_service_date: firstText(job.preferred_service_date),
    contact_number: firstText(job.contact_number),
    required_skill: firstText(job.required_skill),
    sla_deadline: firstText(job.sla_deadline)
  };
}

export async function getTechnicianJobs(
  query: TechnicianJobQuery = {}
): Promise<TechnicianJob[]> {
  const response = await apiClient.get<TechnicianJobApiResponse[]>(
    "/api/technician/jobs",
    { params: query }
  );

  return response.data.map(normalizeTechnicianJob);
}

export async function getTechnicianJobHistory(): Promise<TechnicianJob[]> {
  const response = await apiClient.get<TechnicianJobApiResponse[]>(
    "/api/technician/jobs/history"
  );

  return response.data.map(normalizeTechnicianJob);
}

export async function getTechnicianJob(
  jobId: string | number
): Promise<TechnicianJob> {
  const response = await apiClient.get<TechnicianJobApiResponse>(
    `/api/technician/jobs/${encodeURIComponent(String(jobId))}`
  );

  return normalizeTechnicianJob(response.data);
}