import { apiClient } from "./client";

export interface JobMessage {
  id: string;
  job_id: number;
  sender_user_id: string;
  sender_role: "CUSTOMER" | "TECHNICIAN";
  body: string;
  created_at: string | null;
  delivered_at: string | null;
  read_at: string | null;
  is_mine: boolean;
}

export interface JobConversation {
  job_id: number;
  job_reference: string;
  status: string;
  participant_name: string | null;
  technician_name: string | null;
  assigned: boolean;
  can_send: boolean;
  read_only_reason: string | null;
  unread_count: number;
  messages: JobMessage[];
}

export async function getTechnicianJobConversation(jobId: number) {
  const response = await apiClient.get<JobConversation>(`/api/v1/job-messages/jobs/${jobId}`);
  return response.data;
}

export async function sendTechnicianJobMessage(jobId: number, body: string) {
  const response = await apiClient.post<JobMessage>(`/api/v1/job-messages/jobs/${jobId}`, { body });
  return response.data;
}

export async function acknowledgeTechnicianMessageDelivered(jobId: number, messageId: string) {
  await apiClient.post(`/api/v1/job-messages/jobs/${jobId}/messages/${messageId}/delivered`);
}
