
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
  [key: string]: unknown;
}

export interface NotificationListResponse {
  items: TechnicianNotification[];
  total?: number;
  unread_count?: number;
}

export type NotificationCollection =
  | TechnicianNotification[]
  | NotificationListResponse;

export async function getTechnicianNotifications(): Promise<NotificationCollection> {
  const response = await apiClient.get<NotificationCollection>(
    "/api/technician/notifications"
  );

  return response.data;
}
