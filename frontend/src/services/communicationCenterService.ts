import api from "./api";

export type CommunicationDelivery = {
  channel: "in_app" | "sms" | "email" | "push";
  status: string;
  attempts: number;
  updated_at: string | null;
};

export type CommunicationActivity = {
  id: string;
  job_id: string | null;
  type: string;
  title: string;
  message: string;
  recipient_role: string;
  priority: string;
  created_at: string | null;
  updated_at: string | null;
  channels: CommunicationDelivery[];
};

export type CommunicationCenterFilters = {
  search?: string;
  channel?: string;
  status?: string;
  limit?: number;
  offset?: number;
};

export type CommunicationCenterResponse = {
  messages: CommunicationActivity[];
  total: number;
  limit: number;
  offset: number;
  channel_counts: Record<string, number>;
  delivery_counts: Record<string, number>;
};

export async function getCommunicationActivity(
  filters: CommunicationCenterFilters = {},
): Promise<CommunicationCenterResponse> {
  const response = await api.get<CommunicationCenterResponse>(
    "/admin/communication-center",
    { params: filters },
  );
  return response.data;
}
