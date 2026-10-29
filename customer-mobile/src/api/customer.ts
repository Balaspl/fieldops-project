import { apiClient } from "./client";
import type {
  CustomerFeedback,
  CustomerInvoice,
  CustomerJob,
  CustomerNotification,
  DashboardStats,
  NotificationFeed,
  NotificationPreferences,
  PaymentHistoryItem,
  PaymentStatus,
  ReverseLocation,
  ServiceCatalogItem,
  ServiceHistoryItem,
  ServiceRequest,
  CustomerProfile,
  CustomerProfilePayload,
  SupportRequest,
  LocationSearchResult,
  JobConversation,
  JobMessage,
} from "../types/api";

function arrayFrom<T>(data: unknown, keys: string[] = []): T[] {
  if (Array.isArray(data)) return data as T[];

  if (data && typeof data === "object") {
    const record = data as Record<string, unknown>;

    for (const key of keys) {
      if (Array.isArray(record[key])) {
        return record[key] as T[];
      }
    }
  }

  return [];
}

export type CustomerChatMessage = {
  id: number;
  sender: "customer" | "assistant";
  content: string;
  created_at: string;
  intent?: string | null;
  components?: CustomerChatComponent[];
  follow_up_suggestions?: string[];
};

export type CustomerChatComponent = {
  type: "job_status" | "service_catalog" | "support";
  title: string;
  job_id?: number | null;
  status?: string | null;
  preferred_service_date?: string | null;
  arrival_estimate?: string | null;
  completed_at?: string | null;
  closure_report_available?: boolean;
  items?: string[];
  action?:
    | "service_requests"
    | "tracking"
    | "support"
    | "download_report"
    | null;
};

export const customerApi = {
  login: async (
    email: string,
    password: string,
    trusted_device_token?: string,
  ) =>
    (
      await apiClient.post("/auth/login", {
        email,
        password,
        ...(trusted_device_token ? { trusted_device_token } : {}),
      })
    ).data,

  verifyMfa: async (
    challenge: string,
    code: string,
    trust_device: boolean,
  ) =>
    (
      await apiClient.post("/auth/mfa/verify", {
        challenge,
        code,
        trust_device,
      })
    ).data,

  verifyRecovery: async (
    challenge: string,
    recovery_code: string,
  ) =>
    (
      await apiClient.post("/auth/mfa/recovery", {
        challenge,
        recovery_code,
      })
    ).data,

  currentUser: async () =>
    (await apiClient.get("/auth/me")).data,

  logout: async () =>
    apiClient.post("/auth/logout"),

  requestPasswordReset: async (email: string) =>
    (
      await apiClient.post<{ message: string }>(
        "/auth/forgot-password",
        { email: email.trim().toLowerCase() },
      )
    ).data,

  profile: async () =>
    (
      await apiClient.get<CustomerProfile>(
        "/api/customer/profile",
      )
    ).data,

  createProfile: async (payload: CustomerProfilePayload) =>
    (
      await apiClient.post<CustomerProfile>(
        "/api/customer/profile",
        payload,
      )
    ).data,

  updateProfile: async (
    payload: Partial<CustomerProfilePayload>,
  ) =>
    (
      await apiClient.put<CustomerProfile>(
        "/api/customer/profile",
        payload,
      )
    ).data,

  changePassword: async (
    current_password: string,
    new_password: string,
    confirm_password: string,
  ) =>
    (
      await apiClient.post(
        "/api/customer/change-password",
        {
          current_password,
          new_password,
          confirm_password,
        },
      )
    ).data,

  dashboard: async () =>
    (
      await apiClient.get<DashboardStats>(
        "/api/customer/dashboard",
      )
    ).data,

  requests: async (status?: string) =>
    arrayFrom<ServiceRequest>(
      (
        await apiClient.get(
          "/api/customer/service-requests",
          { params: status ? { status } : {} },
        )
      ).data,
    ),

  request: async (id: number) =>
    (
      await apiClient.get<ServiceRequest>(
        `/api/customer/service-requests/${id}`,
      )
    ).data,

  createRequest: async (payload: Record<string, unknown>) =>
    (
      await apiClient.post<ServiceRequest>(
        "/api/customer/service-requests",
        payload,
      )
    ).data,

  updateRequest: async (
    id: number,
    payload: Record<string, unknown>,
  ) =>
    (
      await apiClient.put<ServiceRequest>(
        `/api/customer/service-requests/${id}`,
        payload,
      )
    ).data,

  cancelRequest: async (id: number, reason: string) =>
    (
      await apiClient.post(
        `/api/customer/service-requests/${id}/cancel`,
        { reason: reason.trim() },
      )
    ).data,

  catalog: async () =>
    arrayFrom<ServiceCatalogItem>(
      (
        await apiClient.get("/api/services/catalog")
      ).data,
    ).filter((item) => item.is_active !== false),

  jobs: async () =>
    arrayFrom<CustomerJob>(
      (
        await apiClient.get("/api/customer/jobs")
      ).data,
    ),

  job: async (id: number) =>
    (
      await apiClient.get<CustomerJob>(
        `/api/customer/jobs/${id}`,
      )
    ).data,

  // Retrieve the conversation for a specific job.
  // The backend determines whether this customer can access it
  // and whether messaging is permitted.
  jobConversation: async (jobId: number) =>
    (
      await apiClient.get<JobConversation>(
        `/api/v1/job-messages/jobs/${jobId}`,
      )
    ).data,

  // Send a message through the existing backend messaging API.
  sendJobMessage: async (
    jobId: number,
    body: string,
  ) =>
    (
      await apiClient.post<JobMessage>(
        `/api/v1/job-messages/jobs/${jobId}`,
        { body },
      )
    ).data,

  // Acknowledge message delivery using the backend endpoint.
  acknowledgeJobMessageDelivered: async (
    jobId: number,
    messageId: string,
  ) =>
    (
      await apiClient.post(
        `/api/v1/job-messages/jobs/${jobId}/messages/${encodeURIComponent(messageId)}/delivered`,
      )
    ).data,

  history: async () =>
    arrayFrom<ServiceHistoryItem>(
      (
        await apiClient.get(
          "/api/customer/service-history",
        )
      ).data,
    ),

  invoices: async () =>
    arrayFrom<CustomerInvoice>(
      (
        await apiClient.get("/api/customer/invoices")
      ).data,
    ),

  invoice: async (jobId: number) =>
    (
      await apiClient.get<CustomerInvoice>(
        `/api/customer/invoices/${jobId}`,
      )
    ).data,

  paymentHistory: async () =>
    arrayFrom<PaymentHistoryItem>(
      (
        await apiClient.get(
          "/api/customer/payment-history",
        )
      ).data,
    ),

  paymentStatus: async (jobId: number) =>
    (
      await apiClient.get<PaymentStatus>(
        `/api/customer/invoices/${jobId}/payment-status`,
      )
    ).data,

  feedback: async (jobId: number) =>
    (
      await apiClient.get<CustomerFeedback>(
        `/api/customer/jobs/${jobId}/feedback`,
      )
    ).data,

  submitFeedback: async (
    jobId: number,
    rating: number,
    comment: string,
  ) =>
    (
      await apiClient.post<CustomerFeedback>(
        `/api/customer/jobs/${jobId}/feedback`,
        {
          rating,
          comment: comment.trim() || null,
        },
      )
    ).data,

  notificationFeed: async () =>
    (
      await apiClient.get<NotificationFeed>(
        "/api/customer/notifications",
      )
    ).data,

  markNotificationRead: async (id: string) =>
    (
      await apiClient.put(
        `/api/customer/notifications/${encodeURIComponent(id)}/read`,
      )
    ).data,

  markAllNotificationsRead: async () =>
    (
      await apiClient.put(
        "/api/customer/notifications/read-all",
      )
    ).data,

  notificationPreferences: async () =>
    (
      await apiClient.get<NotificationPreferences>(
        "/api/customer/notification-preferences",
      )
    ).data,

  updateNotificationPreferences: async (
    payload: Partial<NotificationPreferences>,
  ) =>
    (
      await apiClient.patch<NotificationPreferences>(
        "/api/customer/notification-preferences",
        payload,
      )
    ).data,

  supportRequests: async () =>
    arrayFrom<SupportRequest>(
      (
        await apiClient.get(
          "/api/customer/support-requests",
        )
      ).data,
    ),

  createSupportRequest: async (payload: {
    subject: string;
    description: string;
    related_job_id?: number | null;
  }) =>
    (
      await apiClient.post<SupportRequest>(
        "/api/customer/support-requests",
        payload,
      )
    ).data,

  searchLocations: async (query: string) => {
    const response = (
      await apiClient.get<{
        results?: LocationSearchResult[];
        message?: string;
      }>(
        "/organizations/location-search",
        { params: { q: query.trim() } },
      )
    ).data;

    return Array.isArray(response.results)
      ? response.results
      : [];
  },

  reverseLocation: async (
    latitude: number,
    longitude: number,
  ) =>
    (
      await apiClient.get<ReverseLocation>(
        "/organizations/reverse-location",
        { params: { latitude, longitude } },
      )
    ).data,

  // Customer AI chatbot — uses the existing backend endpoints.
  listChatConversations: async () =>
    (
      await apiClient.get<{
        conversations: Array<{ id: string; updated_at: string }>;
      }>("/api/v1/customer/chat/conversations")
    ).data.conversations,

  getChatConversation: async (id: string) =>
    (
      await apiClient.get<{
        id: string;
        title: string | null;
        status: string;
        messages: CustomerChatMessage[];
      }>(
        `/api/v1/customer/chat/conversations/${encodeURIComponent(id)}`,
      )
    ).data,

  createChatConversation: async () =>
    (
      await apiClient.post<{ id: string }>(
        "/api/v1/customer/chat/conversations",
        {},
      )
    ).data,

  deleteChatConversation: async (id: string) =>
    apiClient.delete(
      `/api/v1/customer/chat/conversations/${encodeURIComponent(id)}`,
    ),

  sendChatMessage: async (
    conversationId: string | null,
    message: string,
    clientMessageId: string,
  ) =>
    (
      await apiClient.post<{
        conversation_id: string;
        answer: string;
        intent: string | null;
        escalation: boolean;
        components: CustomerChatComponent[];
        follow_up_suggestions: string[];
      }>("/api/v1/customer/chat", {
        conversation_id: conversationId,
        message,
        client_message_id: clientMessageId,
      })
    ).data,
};

export function readNotificationFeed(
  value: unknown,
): NotificationFeed {
  if (Array.isArray(value)) {
    return {
      notifications: value as CustomerNotification[],
      unread_count: 0,
    };
  }

  if (value && typeof value === "object") {
    const result = value as Partial<NotificationFeed>;

    return {
      notifications: Array.isArray(result.notifications)
        ? result.notifications
        : [],
      unread_count: Number(result.unread_count ?? 0),
    };
  }

  return {
    notifications: [],
    unread_count: 0,
  };
}