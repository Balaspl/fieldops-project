import api from "./api";

export type ChatMessage = {
  id: number;
  sender: "customer" | "assistant";
  content: string;
  created_at: string;
  intent?: string | null;
  components?: ChatComponent[];
  follow_up_suggestions?: string[];
};

export type ChatComponent = {
  type: "job_status" | "service_catalog" | "support";
  title: string;
  job_id?: number | null;
  status?: string | null;
  preferred_service_date?: string | null;
  arrival_estimate?: string | null;
  completed_at?: string | null;
  closure_report_available?: boolean;
  items?: string[];
  action?: "service_requests" | "tracking" | "support" | "download_report" | null;
};

export type ChatConversation = {
  id: string;
  title: string | null;
  status: string;
  messages: ChatMessage[];
};

export async function listCustomerChatConversations() {
  const response = await api.get<{ conversations: Array<{ id: string; updated_at: string }> }>("/api/v1/customer/chat/conversations");
  return response.data.conversations;
}

export async function getCustomerChatConversation(id: string) {
  const response = await api.get<ChatConversation>(`/api/v1/customer/chat/conversations/${encodeURIComponent(id)}`);
  return response.data;
}

export async function createCustomerChatConversation() {
  const response = await api.post<{ id: string }>("/api/v1/customer/chat/conversations", {});
  return response.data;
}

export async function deleteCustomerChatConversation(id: string) {
  await api.delete(`/api/v1/customer/chat/conversations/${encodeURIComponent(id)}`);
}

export async function sendCustomerChatMessage(conversationId: string | null, message: string, clientMessageId: string) {
  const response = await api.post<{ conversation_id: string; answer: string; intent: string | null; escalation: boolean; components: ChatComponent[]; follow_up_suggestions: string[] }>("/api/v1/customer/chat", {
    conversation_id: conversationId,
    message,
    client_message_id: clientMessageId,
  });
  return response.data;
}

export async function downloadCustomerJobReport(jobId: number) {
  const response = await api.get<Blob>(`/api/customer/jobs/${jobId}/report`, { responseType: "blob" });
  const url = URL.createObjectURL(response.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = `fieldops-job-${jobId}-report.pdf`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
