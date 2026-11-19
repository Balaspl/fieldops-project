/**
 * dispatchQueue.ts
 * TypeScript types for the Dispatch Queue Table, mirroring backend Pydantic schemas.
 */

export interface QueueTechnicianDetail {
  tech_id: string;
  name: string;
  status: string;
}

export interface SLADetail {
  deadline: string | null;
  minutes_remaining: number | null;
  risk_level: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
}

export interface DispatchQueueJob {
  job_id: string;
  title: string;
  status: "QUEUED" | "ASSIGNED" | "EN_ROUTE" | "ON_SITE";
  priority: string;
  customer: string;
  location: string;
  technician: QueueTechnicianDetail | null;
  sla: SLADetail;
  assigned_at: string | null;
  acceptance_expires_at: string | null;
}

export interface DispatchQueuePagination {
  next_cursor: string | null;
  has_more: boolean;
}

export interface DispatchQueueResponse {
  data: DispatchQueueJob[];
  pagination: DispatchQueuePagination;
}

export type DispatchQueueSortField =
  | "job_id"
  | "customer"
  | "location"
  | "status"
  | "priority"
  | "timer";

export type SortDirection = "asc" | "desc";
