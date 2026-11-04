import api from "./api";

export type AgentStageState =
  | "complete"
  | "active"
  | "waiting"
  | "locked"
  | "event_driven";

export interface AgentTrackingStage {
  key: string;
  label: string;
  state: AgentStageState;
  detail: string;
  timestamp: string | null;
}

export interface AgentTrackedJob {
  job_id: number;
  job_number: number | string;
  service_type: string;
  status: string;
  priority: string;
  technician_name: string | null;
  created_at: string | null;
  updated_at: string | null;
  assigned_at: string | null;
  accepted: boolean;
  current_agent: string;
  current_detail: string;
  stages: AgentTrackingStage[];
}

export interface AgentTrackingResponse {
  jobs: AgentTrackedJob[];
  total: number;
  active: number;
  waiting_acceptance: number;
  generated_at: string;
}

export interface AgentTrackingEvent {
  timestamp: string | null;
  agent: string;
  title: string;
  detail: string;
  kind: string;
  message_id?: string | null;
  sender_role?: string | null;
  source_message_id?: string | null;
  emotion?: string | null;
  confidence?: number | null;
}

export interface AgentTrackingJobDetail extends AgentTrackedJob {
  customer_name: string | null;
  location: string | null;
  preferred_service_date: string | null;
  preferred_service_time: string | null;
  events: AgentTrackingEvent[];
}

export async function getAgentTracking(): Promise<AgentTrackingResponse> {
  const response = await api.get<AgentTrackingResponse>(
    "/api/admin/agent-tracking",
    { params: { limit: 250 } },
  );
  return response.data;
}

export async function getAgentTrackingJob(jobId: number): Promise<AgentTrackingJobDetail> {
  const response = await api.get<AgentTrackingJobDetail>(
    `/api/admin/agent-tracking/${jobId}`,
  );
  return response.data;
}
