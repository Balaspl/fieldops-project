import api from "./api";

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
  delivery_status?: string;
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

export const getJobConversation = (jobId: number) =>
  api.get<JobConversation>(`/api/v1/job-messages/jobs/${jobId}`);

export const sendJobMessage = (jobId: number, body: string) =>
  api.post<JobMessage>(`/api/v1/job-messages/jobs/${jobId}`, { body });

export const acknowledgeJobMessageDelivered = (jobId: number, messageId: string) =>
  api.post(`/api/v1/job-messages/jobs/${jobId}/messages/${messageId}/delivered`);

export const getJobUnreadCount = (jobId: number) =>
  api.get<{ job_id: number; unread_count: number }>(`/api/v1/job-messages/jobs/${jobId}/unread-count`);
