
import { io, Socket } from "socket.io-client";
import api from "./api";
import { TechnicianNotification } from "../types/notifications";

const SOCKET_URL = import.meta.env.VITE_SOCKET_URL;

/**
 * Extra fields used by the live notification-card flow.
 * These fields may be added to your shared notification type later.
 */
export type RealtimeTechnicianNotification = TechnicianNotification & {
  groupKey?: string;
  eventVersion?: number;
};

export interface FetchNotificationsResult {
  notifications: TechnicianNotification[];
  unreadCount: number;
  total: number;
}

interface NotificationApiPayload {
  id?: string | number;
  type?: string;
  title?: string;
  body?: string;
  message?: string;
  status?: string;
  created_at?: string;
  createdAt?: string;
  job_id?: string | number;
  jobId?: string | number;
  group_key?: string;
  groupKey?: string;
  event_version?: number | string;
  eventVersion?: number | string;
  job?: unknown;
  notification_metadata?: {
    job?: unknown;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

const toPositiveVersion = (
  value: unknown
): number | undefined => {
  const version =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : undefined;

  if (
    version === undefined ||
    !Number.isSafeInteger(version) ||
    version < 1
  ) {
    return undefined;
  }

  return version;
};

const getNotificationGroupKey = (
  notification: {
    groupKey?: string;
    jobId?: string | number;
  }
): string | undefined => {
  if (notification.groupKey) {
    return notification.groupKey;
  }

  if (
    notification.jobId !== undefined &&
    notification.jobId !== null
  ) {
    return `job_${notification.jobId}`;
  }

  return undefined;
};

const normalizeNotification = (
  payload: NotificationApiPayload
): RealtimeTechnicianNotification => {
  const jobId = payload.job_id ?? payload.jobId;

  const groupKey =
    payload.group_key ??
    payload.groupKey ??
    (jobId !== undefined && jobId !== null
      ? `job_${jobId}`
      : undefined);

  const eventVersion = toPositiveVersion(
    payload.event_version ?? payload.eventVersion
  );

  return {
    id: String(
      payload.id ??
        `notif-${Date.now()}-${Math.random().toString(36).slice(2)}`
    ),
    type: payload.type || "SYSTEM",
    title: payload.title || "Alert",
    message: payload.body || payload.message || "",
    isRead:
      payload.isRead === true ||
      payload.status === "READ" ||
      (typeof payload.status === "string" &&
        payload.status.toUpperCase() !== "UNREAD"),
    createdAt:
      payload.created_at ||
      payload.createdAt ||
      new Date().toISOString(),
    jobId,
    job:
      payload.job ??
      payload.notification_metadata?.job ??
      null,
    groupKey,
    eventVersion,
  } as RealtimeTechnicianNotification;
};

/**
 * Merge an incoming notification into the current list.
 *
 * Notifications belonging to the same job card are replaced instead
 * of appended. If both versions are available, older or equal versions
 * cannot replace the currently displayed card.
 */
export const mergeNotificationList = (
  current: TechnicianNotification[],
  incoming: RealtimeTechnicianNotification
): TechnicianNotification[] => {
  const existingExtended = current as RealtimeTechnicianNotification[];
  const incomingGroupKey = getNotificationGroupKey(incoming);

  const existingIndex = existingExtended.findIndex((item) => {
    const existingGroupKey = getNotificationGroupKey(item);

    if (incomingGroupKey && existingGroupKey) {
      return incomingGroupKey === existingGroupKey;
    }

    return String(item.id) === String(incoming.id);
  });

  if (existingIndex === -1) {
    return [incoming, ...current];
  }

  const existing = existingExtended[existingIndex];

  const oldVersion = toPositiveVersion(existing.eventVersion);
  const newVersion = toPositiveVersion(incoming.eventVersion);

  if (
    oldVersion !== undefined &&
    newVersion !== undefined &&
    newVersion <= oldVersion
  ) {
    return current;
  }

  // If both versions exist, always use the newer version.
  // If the server did not send a version, retain compatibility with
  // the existing notification API and replace the matching card.
  const updated = [...current];
  updated[existingIndex] = {
    ...existing,
    ...incoming,
    id: String(incoming.id),
  };

  return updated;
};

// ─── Fetch notifications ─────────────────────────────────────────────

export const fetchNotifications = async (
  recipientId: string | number,
  audience: "technician" | "admin" | "customer" = "technician",
): Promise<FetchNotificationsResult> => {
  try {
    const response = audience === "admin"
      ? await api.get("/admin/notifications")
      : audience === "customer"
        ? await api.get("/api/customer/notifications")
        : await api.get(`/technicians/${recipientId}/notifications`);

    const data = response.data;
    const rawNotifications: NotificationApiPayload[] =
      Array.isArray(data.notifications)
        ? data.notifications
        : [];

    const notifications = rawNotifications.map(
      (notification) =>
        normalizeNotification(notification)
    );

    return {
      notifications,
      unreadCount: Number(data.unread_count ?? 0),
      total: Number(data.total ?? notifications.length),
    };
  } catch (error) {
    console.error(
      "Failed to fetch notifications from backend",
      error
    );

    throw error;
  }
};

export const fetchUnreadCount = async (
  recipientId: string | number,
  audience: "technician" | "admin" | "customer" = "technician",
): Promise<number> => {
  const data = await fetchNotifications(recipientId, audience);
  return data.unreadCount;
};

// ─── Read and dismiss ────────────────────────────────────────────────

export const markNotificationAsRead = async (
  notificationId: string | number
): Promise<any> => {
  try {
    try {
      const response = await api.put(
        `/api/customer/notifications/${notificationId}/read`
      );
      return response.data;
    } catch {
      const response = await api.patch(
        `/notifications/${notificationId}/read`
      );
      return response.data;
    }
  } catch (error) {
    console.error(
      "Failed to mark notification as read",
      error
    );
    throw error;
  }
};

export const batchMarkAsRead = async (
  notificationIds: string[]
): Promise<any> => {
  try {
    try {
      const response = await api.put(
        "/api/customer/notifications/read-all"
      );
      return response.data;
    } catch {
      const response = await api.patch(
        "/notifications/batch-read",
        { notification_ids: notificationIds }
      );
      return response.data;
    }
  } catch (error) {
    console.error(
      "Failed to batch mark notifications as read",
      error
    );
    throw error;
  }
};

export const dismissNotification = async (
  notificationId: string | number
): Promise<any> => {
  try {
    const response = await api.patch(
      `/notifications/${notificationId}/dismiss`
    );
    return response.data;
  } catch (error) {
    console.error(
      `Failed to dismiss notification ${notificationId}`,
      error
    );
    throw error;
  }
};

export const cleanupNotifications = async (): Promise<any> => {
  try {
    const response = await api.delete(
      "/notifications/system/cleanup"
    );
    return response.data;
  } catch (error) {
    console.error(
      "Failed to cleanup old notifications",
      error
    );
    throw error;
  }
};

// ─── Job actions ────────────────────────────────────────────────────

export const acceptJob = async (
  jobId: string | number
): Promise<any> => {
  try {
    const response = await api.post(`/jobs/${jobId}/accept`);
    return response.data;
  } catch (error) {
    console.error(`Failed to accept job ${jobId}`, error);
    throw error;
  }
};

export const rejectJob = async (
  jobId: string | number,
  reason: string
): Promise<any> => {
  try {
    const response = await api.post(`/jobs/${jobId}/reject`, {
      reason,
    });
    return response.data;
  } catch (error) {
    console.error(`Failed to reject job ${jobId}`, error);
    throw error;
  }
};

export const reassignJob = async (
  jobId: string | number,
  colleagueId: string | number,
  reason: string
): Promise<any> => {
  try {
    const response = await api.post(`/jobs/${jobId}/reassign`, {
      new_tech_id: String(colleagueId),
      reason: reason || "Reassigned from notification detail",
    });
    return response.data;
  } catch (error) {
    console.error(`Failed to reassign job ${jobId}`, error);
    throw error;
  }
};

// ─── FCM token ──────────────────────────────────────────────────────

export const registerFCMToken = async (
  techId: string | number,
  token: string
): Promise<any> => {
  try {
    const response = await api.post(
      `/technicians/${techId}/fcm-token`,
      {
        token,
        device_type: "web",
      }
    );
    return response.data;
  } catch (error) {
    console.error(
      "Failed to register FCM token with backend",
      error
    );
    throw error;
  }
};

// ─── Real-time notification socket ──────────────────────────────────

export interface SocketHandlers {
  onConnect?: () => void;
  onDisconnect?: (reason?: string) => void;
  onNewNotification?: (
    notification: RealtimeTechnicianNotification
  ) => void;
  onUnreadCount?: (count: number) => void;
  onRead?: (data: any) => void;
}

/**
 * Connect to the existing Socket.IO server.
 *
 * Pass the technician ID as the first argument, matching the
 * existing call sites. Supply tenantId when the backend requires it.
 *
 * The backend must authorize the connection and room membership.
 */
export const connectNotificationSocket = (
  accessToken: string | null | undefined,
  handlers: SocketHandlers = {}
): Socket => {
  if (!SOCKET_URL) {
    console.warn(
      "notificationService: VITE_SOCKET_URL is not configured."
    );
  }

  // Authenticate with the access token when available. For SSO sessions
  // that use an HttpOnly cookie, withCredentials allows the browser to send
  // the cookie; the backend must validate the token or cookie before joining
  // any user/tenant notification rooms.
  const socket = io(
    SOCKET_URL || "http://localhost:8000",
    {
      auth: accessToken ? { token: accessToken } : {},
      withCredentials: true,
      reconnection: true,
      reconnectionAttempts: 5,
      reconnectionDelay: 2000,
      timeout: 10000,
      transports: ["websocket", "polling"],
    }
  );

  // Keep the newest received version per job card during this
  // socket connection. This also prevents duplicate delivery when
  // the backend emits both supported event aliases.
  const latestVersionByGroup = new Map<string, number>();

  // When a payload has no event version, use its content signature
  // to avoid processing the same alias payload twice.
  const lastSignatureByGroup = new Map<string, string>();

  socket.on("connect", () => {
    console.log("Authenticated notification socket connected.");
    handlers.onConnect?.();
  });

  socket.on("connect_error", (error) => {
    console.warn(
      "notificationService: Socket connection error:",
      error.message
    );
  });

  socket.on("disconnect", (reason: string) => {
    console.log("Notification socket disconnected:", reason);
    handlers.onDisconnect?.(reason);
  });

  const handleNewNotification = (
    payload: NotificationApiPayload
  ) => {
    if (!payload || typeof payload !== "object") {
      return;
    }

    const nestedPayload = payload.payload;
    if (nestedPayload && typeof nestedPayload === "object") {
      payload = nestedPayload as NotificationApiPayload;
    }

    const notification = normalizeNotification(payload);
    const groupKey =
      getNotificationGroupKey(notification) ??
      `notification_${notification.id}`;

    const version = toPositiveVersion(
      notification.eventVersion
    );

    if (version !== undefined) {
      const latestVersion = latestVersionByGroup.get(groupKey);

      if (
        latestVersion !== undefined &&
        version <= latestVersion
      ) {
        return;
      }

      latestVersionByGroup.set(groupKey, version);
    } else {
      const signature = JSON.stringify({
        id: notification.id,
        type: notification.type,
        title: notification.title,
        message: notification.message,
        createdAt: notification.createdAt,
      });

      if (lastSignatureByGroup.get(groupKey) === signature) {
        return;
      }

      lastSignatureByGroup.set(groupKey, signature);
    }

    console.log(
      "Real-time notification received:",
      notification
    );

    handlers.onNewNotification?.(notification);
  };

  // Register only one canonical handler to avoid processing the
  // same event twice if the backend emits both aliases.
  socket.on("new_notification", handleNewNotification);
  // Communication Agent publishes persisted admin/customer events using
  // this event name; admin sessions join the tenant dispatchers room.
  socket.on("notification", handleNewNotification);

  // Keep this alias for compatibility with existing backend emitters.
  socket.on("notification:new", handleNewNotification);

  socket.on(
    "notification:unread_count",
    (payload: number | { unread_count?: number; count?: number }) => {
      const count =
        typeof payload === "number"
          ? payload
          : Number(payload?.unread_count ?? payload?.count ?? 0);

      handlers.onUnreadCount?.(count);
    }
  );

  socket.on("notification:read", (data: any) => {
    handlers.onRead?.(data);
  });

  return socket;
};

export const disconnectNotificationSocket = (
  socket: Socket | null
): void => {
  if (socket) {
    socket.removeAllListeners();
    socket.disconnect();
  }
};

// ─── Dispatch event → toast mapping ─────────────────────────────────

const DISPATCH_EVENT_CONFIG: Record<
  string,
  {
    type: "success" | "warning" | "error" | "info";
    title: string;
    autoDismiss: number;
    priority: "normal" | "critical";
  }
> = {
  "job.assigned": {
    type: "info",
    title: "Job Assigned",
    autoDismiss: 5000,
    priority: "normal",
  },
  "job.accepted": {
    type: "success",
    title: "Job Accepted",
    autoDismiss: 5000,
    priority: "normal",
  },
  "job.rejected": {
    type: "warning",
    title: "Job Rejected",
    autoDismiss: 8000,
    priority: "critical",
  },
  "job.expired": {
    type: "error",
    title: "Job Expired",
    autoDismiss: 10000,
    priority: "critical",
  },
  "job.en_route": {
    type: "info",
    title: "Tech En Route",
    autoDismiss: 5000,
    priority: "normal",
  },
};

export const subscribeToDispatchEvents = (
  socket: Socket | null,
  onDispatchEvent: (toast: any) => void
): (() => void) => {
  if (!socket) {
    return () => {};
  }

  const handlers: Record<
    string,
    (payload?: any) => void
  > = {};

  Object.entries(DISPATCH_EVENT_CONFIG).forEach(
    ([event, config]) => {
      const handler = (payload: any = {}) => {
        const jobTitle =
          payload.job_title ||
          payload.title ||
          "Unknown Job";

        const techName =
          payload.tech_name ||
          payload.technician_name ||
          "";

        const reason = payload.reason || "";
        const eta = payload.eta || "";

        let message = jobTitle;

        if (event === "job.accepted" && techName) {
          message = `${techName} accepted ${jobTitle}`;
        }

        if (event === "job.rejected" && techName) {
          message =
            `${techName} rejected ${jobTitle}` +
            (reason ? ` — ${reason}` : "");
        }

        if (event === "job.expired") {
          message = `${jobTitle} — Re-dispatching…`;
        }

        if (event === "job.en_route" && techName) {
          message =
            `${techName} is en route` +
            (eta ? ` — ETA ${eta}` : "");
        }

        if (event === "job.assigned" && techName) {
          message = `${jobTitle} → ${techName}`;
        }

        onDispatchEvent({
          type: config.type,
          title: config.title,
          message,
          jobId: payload.job_id || payload.jobId,
          autoDismiss: config.autoDismiss,
          priority: config.priority,
          eventType: event,
        });
      };

      handlers[event] = handler;
      socket.on(event, handler);
    }
  );

  return () => {
    Object.entries(handlers).forEach(([event, handler]) => {
      socket.off(event, handler);
    });
  };
};

// ─── Notification → toast mapping ───────────────────────────────────

export const createToastFromNotification = (
  notification: TechnicianNotification
): any => {
  const typeMap: Record<
    string,
    {
      type: "success" | "warning" | "error" | "info";
      autoDismiss: number;
      priority: "normal" | "critical";
      eventType?: string;
    }
  > = {
    JOB_ASSIGNED: {
      type: "info",
      autoDismiss: 5000,
      priority: "normal",
      eventType: "job.assigned",
    },
    SLA_WARNING: {
      type: "warning",
      autoDismiss: 8000,
      priority: "critical",
    },
    JOB_UPDATED: {
      type: "info",
      autoDismiss: 5000,
      priority: "normal",
    },
    SYSTEM: {
      type: "info",
      autoDismiss: 5000,
      priority: "normal",
    },
  };

  const config =
    typeMap[notification.type] || typeMap.SYSTEM;

  return {
    type: config.type,
    title: notification.title || "Notification",
    message: notification.message || "",
    jobId: notification.jobId,
    autoDismiss: config.autoDismiss,
    priority: config.priority,
    eventType: config.eventType,
  };
};
