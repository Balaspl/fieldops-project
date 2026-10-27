import { apiClient } from "./client";

export interface TechnicianNotification {
  id: string | number;
  title: string;
  message?: string;
  body?: string;
  read?: boolean;
  is_read?: boolean;
  created_at?: string;
  type?: string;
  jobId?: string | number | null;
  jobStatus?: string | null;
  [key: string]: unknown;
}

export interface NotificationListResponse {
  items: TechnicianNotification[];
  total?: number;
  unread_count?: number;
}

interface BackendNotification {
  id: string | number;
  title?: string | null;
  message?: string | null;
  isRead?: boolean;
  createdAt?: string | null;
  type?: string | null;
  jobId?: string | number | null;
  jobStatus?: string | null;
}

interface BackendNotificationResponse {
  notifications: BackendNotification[];
  unread_count?: number;
}

export type NotificationCollection =
  | TechnicianNotification[]
  | NotificationListResponse;

function normalizeNotification(
  notification: BackendNotification
): TechnicianNotification {
  return {
    id: notification.id,
    title: notification.title?.trim() || "FieldOps update",
    message: notification.message ?? undefined,
    body: notification.message ?? undefined,
    read: notification.isRead ?? false,
    is_read: notification.isRead ?? false,
    created_at: notification.createdAt ?? undefined,
    type: notification.type ?? undefined,
    jobId: notification.jobId,
    jobStatus: notification.jobStatus
  };
}

export async function getTechnicianNotifications(): Promise<NotificationListResponse> {
  const response =
    await apiClient.get<BackendNotificationResponse>(
      "/api/technician/notifications"
    );

  const backendData = response.data;

  return {
    items: Array.isArray(backendData.notifications)
      ? backendData.notifications.map(normalizeNotification)
      : [],
    total: Array.isArray(backendData.notifications)
      ? backendData.notifications.length
      : 0,
    unread_count: backendData.unread_count ?? 0
  };
}

export async function markTechnicianNotificationRead(
  notificationId: string | number
): Promise<void> {
  const safeId = encodeURIComponent(String(notificationId));

  await apiClient.put(
    `/api/technician/notifications/${safeId}/read`
  );
}

export async function markAllTechnicianNotificationsRead(): Promise<void> {
  await apiClient.put("/api/technician/notifications/read-all");
}

export type PushDeviceType = "android" | "ios";

export interface RegisterTechnicianPushTokenInput {
  userId: string | number;
  tenantId: string | number;
  token: string;
  deviceType: PushDeviceType;
}

/**
 * Register the authenticated technician's native device token.
 *
 * Authentication is supplied by the existing apiClient.
 * The backend remains authoritative for identity and tenant checks.
 */
export async function registerTechnicianPushToken(
  input: RegisterTechnicianPushTokenInput
): Promise<void> {
  const userId = String(input.userId).trim();
  const tenantId = String(input.tenantId).trim();
  const token = input.token.trim();

  if (!userId) {
    throw new Error("A technician user ID is required.");
  }

  if (!tenantId) {
    throw new Error("The authenticated tenant ID is required.");
  }

  if (!token || token.length > 4096) {
    throw new Error("The device push token is invalid.");
  }

  if (
    input.deviceType !== "android" &&
    input.deviceType !== "ios"
  ) {
    throw new Error("The device platform is unsupported.");
  }

  await apiClient.post(
    `/technicians/${encodeURIComponent(userId)}/fcm-token`,
    {
      token,
      device_type: input.deviceType
    },
    {
      headers: {
        "X-Tenant-ID": tenantId
      }
    }
  );
}