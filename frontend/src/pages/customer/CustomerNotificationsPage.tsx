
import { useState, useEffect, useCallback, useRef } from "react";
import { io, Socket } from "socket.io-client";
import {
  Bell, Check, CheckCheck, CircleCheck, Clock3, Hammer,
  MapPin, Navigation, PartyPopper, RefreshCw, Wrench,
} from "lucide-react";
import "./CustomerNotificationsPage.css";

import {
  getCustomerNotifications,
  getCustomerJobs,
  markCustomerNotificationRead,
  markAllCustomerNotificationsRead,
} from "../../services/customerPortalService";
import AnimatedJobProgress from "../../components/customer-tracking/AnimatedJobProgress";
import type { CustomerJobTrackingResponse } from "../../services/customerPortalService";

interface CustomerNotification {
  id: string;
  title?: string;
  message?: string;
  isRead?: boolean;
  createdAt?: string;
  jobId?: string | number;
  groupKey?: string;
  eventVersion?: number;
  type?: string;
  metadata?: Record<string, unknown>;
  liveEvent?: boolean;
  [key: string]: unknown;
}

interface NotificationPayload {
  id?: string | number;
  title?: string;
  message?: string;
  body?: string;
  status?: string;
  isRead?: boolean;
  created_at?: string;
  createdAt?: string;
  job_id?: string | number;
  jobId?: string | number;
  group_key?: string;
  groupKey?: string;
  event_version?: number | string;
  eventVersion?: number | string;
  type?: string;
  event?: string;
  metadata?: Record<string, unknown>;
  [key: string]: unknown;
}

const SOCKET_URL = (
  import.meta.env.VITE_SOCKET_URL ||
  import.meta.env.VITE_API_BASE_URL ||
  "http://localhost:8000"
).replace(/\/+$/, "");

/**
 * Keep Socket.IO authentication aligned with api.ts:
 * - local auth: send the existing access token through Socket.IO's auth payload
 * - SSO auth: rely on the HttpOnly session cookie
 */
const getSocketAuth = (): { token?: string } => {
  try {
    const authMode = localStorage.getItem("auth_mode");
    if (authMode === "sso") {
      return {};
    }

    const token =
      localStorage.getItem("access_token") ||
      localStorage.getItem("token");

    return token ? { token } : {};
  } catch {
    // Storage may be unavailable in restricted browser contexts.
    return {};
  }
};

const getNotificationErrorMessage = (error: any): string => {
  const status = error?.response?.status;

  if (status === 401) {
    return "Your session has expired. Please sign in again.";
  }

  if (status === 403) {
    return "You do not have permission to view customer notifications.";
  }

  return "We couldn't load your notifications. Please try again.";
};

const parseVersion = (
  value: unknown,
): number | undefined => {
  const version =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim()
        ? Number(value)
        : undefined;

  return version !== undefined &&
    Number.isSafeInteger(version) &&
    version >= 1
    ? version
    : undefined;
};

const normalizeNotification = (
  raw: NotificationPayload,
): CustomerNotification => {
  const jobId = raw.job_id ?? raw.jobId;
  const groupKey =
    raw.group_key ??
    raw.groupKey ??
    (jobId !== undefined && jobId !== null
      ? `job_${jobId}`
      : undefined);

  const version = parseVersion(
    raw.event_version ?? raw.eventVersion,
  );

  return {
    ...raw,
    id: String(
      raw.id ??
        `notification-${Date.now()}-${Math.random()
          .toString(36)
          .slice(2)}`,
    ),
    title: raw.title || "Notification",
    message: raw.body || raw.message || "",
    isRead:
      raw.status === "READ" ||
      raw.isRead === true,
    createdAt:
      raw.created_at ||
      raw.createdAt ||
      new Date().toISOString(),
    jobId,
    groupKey,
    eventVersion: version,
    type: raw.type || raw.event || "SYSTEM",
  };
};

const relativeTime = (value?: string): string => {
  if (!value) return "";
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return "";
  const seconds = Math.round((timestamp - Date.now()) / 1000);
  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["year", 31_536_000], ["month", 2_592_000], ["week", 604_800],
    ["day", 86_400], ["hour", 3_600], ["minute", 60], ["second", 1],
  ];
  const [unit, size] = units.find(([, size]) => Math.abs(seconds) >= size) ?? ["second", 1];
  return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(
    Math.round(seconds / size), unit,
  );
};

const notificationVisual = (notification: CustomerNotification) => {
  const event = `${notification.type ?? ""} ${notification.title ?? ""} ${notification.metadata?.state ?? ""}`.toLowerCase();
  if (/complet|closed|done/.test(event)) return { Icon: CircleCheck, tone: "complete" };
  if (/cancel/.test(event)) return { Icon: RefreshCw, tone: "cancelled" };
  if (/on_site|arrived/.test(event)) return { Icon: MapPin, tone: "arrived" };
  if (/en_route|on the way|eta/.test(event)) return { Icon: Navigation, tone: "travel" };
  if (/progress|work/.test(event)) return { Icon: Hammer, tone: "working" };
  if (/accept|assigned/.test(event)) return { Icon: Wrench, tone: "assigned" };
  if (/delay/.test(event)) return { Icon: Clock3, tone: "delayed" };
  return { Icon: PartyPopper, tone: "update" };
};

const progressStatusFromEvent = (eventType?: string): string | undefined => {
  switch (String(eventType ?? "").toLowerCase()) {
    case "job_created":
    case "technician_rejected":
      return "CREATED";
    case "technician_accepted":
      return "ACCEPTED";
    case "delayed":
      return "ASSIGNED";
    case "en_route":
      return "EN_ROUTE";
    case "on_site":
      return "ON_SITE";
    case "completed":
      return "COMPLETED";
    case "cancelled":
      return "CANCELLED";
    case "closed":
      return "CLOSED";
    default:
      return undefined;
  }
};

/**
 * Replace an existing card for the same job.
 * Do not allow an older or equal event version to overwrite it.
 */
const mergeNotification = (
  current: CustomerNotification[],
  incoming: CustomerNotification,
): CustomerNotification[] => {
  const incomingGroup =
    incoming.groupKey ??
    (incoming.jobId !== undefined
      ? `job_${incoming.jobId}`
      : undefined);

  const index = current.findIndex((item) => {
    const existingGroup =
      item.groupKey ??
      (item.jobId !== undefined
        ? `job_${item.jobId}`
        : undefined);

    if (incomingGroup && existingGroup) {
      return incomingGroup === existingGroup;
    }

    return item.id === incoming.id;
  });

  if (index === -1) {
    return [incoming, ...current];
  }

  const existing = current[index];
  const oldVersion = parseVersion(existing.eventVersion);
  const newVersion = parseVersion(incoming.eventVersion);

  // When the stored card has a version, an incoming event must
  // have a strictly newer version to replace it.
  if (
    oldVersion !== undefined &&
    (newVersion === undefined || newVersion <= oldVersion)
  ) {
    return current;
  }

  // An identical notification ID with no newer version is a duplicate.
  if (
    existing.id === incoming.id &&
    (newVersion === undefined ||
      (oldVersion !== undefined && newVersion <= oldVersion))
  ) {
    return current;
  }

  const updated = [...current];
  updated[index] = {
    ...existing,
    ...incoming,
  };

  return updated;
};

export default function CustomerNotificationsPage() {
  const [notifications, setNotifications] = useState<
    CustomerNotification[]
  >([]);
  const [jobsById, setJobsById] = useState<
    Record<string, CustomerJobTrackingResponse>
  >({});
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mutationError, setMutationError] =
    useState<string | null>(null);
  const [markingReadId, setMarkingReadId] =
    useState<string | null>(null);
  const [markingAllRead, setMarkingAllRead] =
    useState(false);

  const notificationsRef = useRef<CustomerNotification[]>([]);
  const socketRef = useRef<Socket | null>(null);
  const seenEventsRef = useRef(new Set<string>());

  // Keep the ref synchronized with the current React state.
  useEffect(() => {
    notificationsRef.current = notifications;
  }, [notifications]);

  const load = useCallback(async (showLoading = true) => {
    if (showLoading) {
      setLoading(true);
    }

    setError(null);

    try {
      const response = await getCustomerNotifications();
      const data = response?.data ?? {};

      const rawNotifications: NotificationPayload[] =
        Array.isArray(data.notifications)
          ? data.notifications
          : [];

      const nextNotifications =
        rawNotifications.map(normalizeNotification);

      notificationsRef.current = nextNotifications;
      setNotifications(nextNotifications);

      const nextUnread =
        typeof data.unread_count === "number"
          ? Math.max(0, data.unread_count)
          : nextNotifications.filter(
              (notification) => !notification.isRead,
            ).length;

      setUnread(nextUnread);
    } catch (requestError: any) {
      setError(getNotificationErrorMessage(requestError));
    } finally {
      if (showLoading) {
        setLoading(false);
      }
    }
  }, []);

  const refreshJobs = useCallback(async () => {
    try {
      const response = await getCustomerJobs();
      const rows = Array.isArray(response?.data) ? response.data : [];
      const next: Record<string, CustomerJobTrackingResponse> = {};
      rows.forEach((job) => {
        next[String(job.id)] = job;
      });
      setJobsById(next);
      return rows;
    } catch {
      // The notifications remain usable if the separate job snapshot is unavailable.
      return null;
    }
  }, []);

  // Reuse the authenticated customer jobs API for status, route ETA, and real event times.
  // Refresh while any notification represents an active job; socket reconnects also
  // reload notifications, which reruns this synchronization immediately.
  useEffect(() => {
    const jobIds = Array.from(
      new Set(
        notifications
          .filter((notification) => notification.jobId != null)
          .map((notification) => String(notification.jobId)),
      ),
    );
    if (jobIds.length === 0) return;

    let active = true;
    let timer: number | undefined;
    const syncJobs = async () => {
      const rows = await refreshJobs();
      if (!active) return;

      const activeJobExists = rows
        ? rows.some(
            (job) =>
              jobIds.includes(String(job.id)) &&
              !["COMPLETED", "CANCELLED", "CLOSED"].includes(
                String(job.status ?? "").toUpperCase(),
              ),
          )
        : notifications.some(
            (notification) =>
              notification.jobId != null &&
              !["completed", "cancelled", "closed"].includes(
                String(notification.type ?? "").toLowerCase(),
              ),
          );

      if (activeJobExists && timer === undefined) {
        timer = window.setInterval(() => void syncJobs(), 10_000);
      } else if (!activeJobExists && timer !== undefined) {
        window.clearInterval(timer);
        timer = undefined;
      }
    };

    void syncJobs();
    return () => {
      active = false;
      if (timer !== undefined) window.clearInterval(timer);
    };
  }, [notifications, refreshJobs]);

  // Initial load.
  useEffect(() => {
    void load();
  }, [load]);

  // Customer-specific real-time connection.
  useEffect(() => {
    if (!SOCKET_URL) {
      console.warn(
        "VITE_SOCKET_URL is not configured. " +
          "Customer notifications will use API loading only.",
      );
      return;
    }

    /*
     * The server must authenticate the customer using the app's
     * actual authentication mechanism and join the authorized room.
     *
     * This configuration uses cookie/session authentication.
     * If your application uses JWT authentication for sockets,
     * adapt this to your existing secure token mechanism.
     *
     * Do not use an untrusted customer ID query parameter as
     * authorization.
     */
    const socket = io(SOCKET_URL, {
      // The server validates this token and derives the customer identity.
      // Never pass a customer ID as a query parameter for authorization.
      auth: getSocketAuth(),
      withCredentials: true,
      reconnection: true,
      reconnectionAttempts: 5,
      reconnectionDelay: 2000,
      timeout: 10000,
      transports: ["websocket", "polling"],
    });

    socketRef.current = socket;

    const handleConnect = () => {
      console.info("Customer notification socket connected.");

      // Synchronize anything missed while disconnected.
      void load(false);
    };

    const handleNotification = (
      payload: NotificationPayload,
    ) => {
      if (!payload || typeof payload !== "object") {
        return;
      }

      const incoming = {
        ...normalizeNotification(payload),
        liveEvent: true,
      };

      const signature = [
        incoming.id,
        incoming.groupKey ?? "",
        incoming.eventVersion ?? "",
        incoming.type ?? "",
        incoming.title ?? "",
        incoming.message ?? "",
      ].join("|");

      // The backend may emit the same event under two aliases.
      if (seenEventsRef.current.has(signature)) {
        return;
      }

      seenEventsRef.current.add(signature);

      // Keep the deduplication set bounded.
      if (seenEventsRef.current.size > 500) {
        const first = seenEventsRef.current.values().next().value;
        if (first !== undefined) {
          seenEventsRef.current.delete(first);
        }
      }

      const current = notificationsRef.current;
      const incomingGroup =
        incoming.groupKey ??
        (incoming.jobId !== undefined
          ? `job_${incoming.jobId}`
          : undefined);

      const existing = current.find((item) => {
        const existingGroup =
          item.groupKey ??
          (item.jobId !== undefined
            ? `job_${item.jobId}`
            : undefined);

        if (incomingGroup && existingGroup) {
          return incomingGroup === existingGroup;
        }

        return item.id === incoming.id;
      });

      const next = mergeNotification(current, incoming);

      if (next === current) {
        return;
      }

      notificationsRef.current = next;
      setNotifications(next);

      const wasUnread = existing ? !existing.isRead : false;
      const isNowUnread = !incoming.isRead;

      if (wasUnread !== isNowUnread) {
        setUnread((count) =>
          Math.max(
            0,
            count + (isNowUnread ? 1 : 0) -
              (wasUnread ? 1 : 0),
          ),
        );
      }
    };

    const handleRead = (payload: any) => {
      const notificationId = String(
        payload?.id ?? payload?.notification_id ?? "",
      );

      if (!notificationId) {
        return;
      }

      const current = notificationsRef.current;
      const target = current.find(
        (item) => item.id === notificationId,
      );

      if (!target || target.isRead) {
        return;
      }

      const next = current.map((item) =>
        item.id === notificationId
          ? { ...item, isRead: true }
          : item,
      );

      notificationsRef.current = next;
      setNotifications(next);
      setUnread((count) => Math.max(0, count - 1));
    };

    socket.on("connect", handleConnect);
    socket.on("new_notification", handleNotification);
    socket.on("notification:new", handleNotification);
    socket.on("notification:read", handleRead);

    socket.on("notification:unread_count", (payload: any) => {
      const value =
        typeof payload === "number"
          ? payload
          : Number(
              payload?.unread_count ??
                payload?.count ??
                NaN,
            );

      if (Number.isFinite(value) && value >= 0) {
        setUnread(value);
      }
    });

    socket.on("connect_error", (socketError) => {
      console.warn(
        "Customer notification socket connection failed:",
        socketError.message,
      );
    });

    return () => {
      socket.off("connect", handleConnect);
      socket.off("new_notification", handleNotification);
      socket.off("notification:new", handleNotification);
      socket.off("notification:read", handleRead);
      socket.removeAllListeners("notification:unread_count");
      socket.disconnect();

      if (socketRef.current === socket) {
        socketRef.current = null;
      }
    };
  }, [load]);

  const markRead = async (id: string) => {
    if (markingReadId || markingAllRead) {
      return;
    }

    setMutationError(null);
    setMarkingReadId(id);

    try {
      await markCustomerNotificationRead(id);

      const current = notificationsRef.current;
      const target = current.find(
        (notification) => notification.id === id,
      );

      const next = current.map((notification) =>
        notification.id === id
          ? { ...notification, isRead: true }
          : notification,
      );

      notificationsRef.current = next;
      setNotifications(next);

      if (target && !target.isRead) {
        setUnread((count) => Math.max(0, count - 1));
      }
    } catch (requestError: any) {
      const status = requestError?.response?.status;

      if (status === 401) {
        setMutationError(
          "Your session has expired. Please sign in again.",
        );
      } else if (status === 403) {
        setMutationError(
          "You do not have permission to update this notification.",
        );
      } else {
        setMutationError(
          "We couldn't mark this notification as read.",
        );
      }
    } finally {
      setMarkingReadId(null);
    }
  };

  const markAllRead = async () => {
    if (markingReadId || markingAllRead) {
      return;
    }

    setMutationError(null);
    setMarkingAllRead(true);

    try {
      await markAllCustomerNotificationsRead();

      const next = notificationsRef.current.map(
        (notification) => ({
          ...notification,
          isRead: true,
        }),
      );

      notificationsRef.current = next;
      setNotifications(next);
      setUnread(0);
    } catch (requestError: any) {
      const status = requestError?.response?.status;

      if (status === 401) {
        setMutationError(
          "Your session has expired. Please sign in again.",
        );
      } else if (status === 403) {
        setMutationError(
          "You do not have permission to update notifications.",
        );
      } else {
        setMutationError(
          "We couldn't mark all notifications as read.",
        );
      }
    } finally {
      setMarkingAllRead(false);
    }
  };

  return (
    <main className="customer-notifications">
      <header className="customer-notifications__header">
        <div>
          <p className="customer-notifications__eyebrow">FIELDOPS | YOUR SERVICE UPDATES</p>
          <h1><span className="customer-notifications__bell"><Bell size={21} /></span> Notifications
            {unread > 0 && <span className="customer-notifications__count" aria-label={`${unread} unread`}>{unread}</span>}
          </h1>
          <p className="customer-notifications__subtitle">The latest on your service, all in one place.</p>
        </div>
        {unread > 0 && (
          <button className="customer-notifications__mark-all" type="button" onClick={() => void markAllRead()}
            disabled={markingAllRead || Boolean(markingReadId)} aria-busy={markingAllRead}>
            <CheckCheck size={16} /> {markingAllRead ? "Updating..." : "Mark all as read"}
          </button>
        )}
      </header>

      {mutationError && (
        <div role="alert" className="customer-notifications__alert">
          {mutationError}
        </div>
      )}

      {loading ? (
        <div className="customer-notifications__state" role="status" aria-live="polite">
          Loading notifications...
        </div>
      ) : error ? (
        <div className="customer-notifications__state customer-notifications__state--error" role="alert">
          <div
              className="customer-notifications__error-text"
          >
            {error}
          </div>

          <button
            type="button"
            onClick={() => void load()}
            className="customer-notifications__retry"
          >
            Try Again
          </button>
        </div>
      ) : notifications.length === 0 ? (
        <section className="customer-notifications__state customer-notifications__empty">
          <span className="customer-notifications__empty-icon"><Bell size={24} /></span>
          <h2>You're all caught up</h2><p>New updates about your service will show up here.</p>
        </section>
      ) : (
        <section className="customer-notifications__list" aria-label="Your notifications">
        {notifications.map((notification) => {
          const isMarkingThisRead =
            markingReadId === notification.id;
          const visual = notificationVisual(notification);
          const EventIcon = visual.Icon;
          const job = notification.jobId != null
            ? jobsById[String(notification.jobId)]
            : undefined;
          const eventStatus = progressStatusFromEvent(notification.type);
          const progressStatus = notification.liveEvent
            ? eventStatus ?? job?.status
            : job?.status ?? eventStatus;
          const metadataEta = Number(notification.metadata?.eta_min);
          const metadataEtaUpdatedAt =
            typeof notification.metadata?.eta_updated_at === "string"
              ? new Date(notification.metadata.eta_updated_at).getTime()
              : NaN;
          const metadataEtaIsFresh =
            Number.isFinite(metadataEta) &&
            metadataEta >= 0 &&
            Number.isFinite(metadataEtaUpdatedAt) &&
            Date.now() - metadataEtaUpdatedAt >= 0 &&
            Date.now() - metadataEtaUpdatedAt <= 15 * 60 * 1000;
          const hasProgress =
            notification.jobId != null &&
            (Boolean(eventStatus) || Array.isArray(notification.metadata?.steps));
          const technicianName =
            typeof notification.metadata?.technician === "object" &&
            notification.metadata.technician !== null &&
            "name" in notification.metadata.technician &&
            typeof notification.metadata.technician.name === "string"
              ? notification.metadata.technician.name
              : job?.assigned_technician_name;

          return (
            <article
              key={notification.id}
              className={`customer-notification-card ${notification.isRead ? "is-read" : "is-unread"}`}
              aria-label={`${notification.isRead ? "Read" : "Unread"} notification: ${notification.title}`}
            >
              <div className={`customer-notification-card__icon customer-notification-card__icon--${visual.tone}`} aria-hidden="true"><EventIcon size={20} strokeWidth={2.2} /></div>
              <div className="customer-notification-card__content">
                <div className="customer-notification-card__topline">
                  <h2>{notification.title || "Notification"}</h2>
                  <time dateTime={notification.createdAt} title={notification.createdAt ? new Date(notification.createdAt).toLocaleString() : undefined}>
                    {relativeTime(notification.createdAt)}
                  </time>
                </div>
                {notification.message && <p className="customer-notification-card__message">{notification.message}</p>}

                {hasProgress && (
                  <>
                    <div className="customer-notification-card__job-number">
                      Job #{notification.jobId}
                      {technicianName && <span>Technician: {technicianName}</span>}
                    </div>
                    <AnimatedJobProgress
                      jobId={notification.jobId!}
                      status={
                        notification.metadata?.state === "cancelled"
                          ? "CANCELLED"
                          : progressStatus
                      }
                      estimatedArrival={job?.estimated_arrival}
                      etaDurationMinutes={
                        job?.eta_duration_minutes ??
                        (metadataEtaIsFresh ? metadataEta : null)
                      }
                      etaDistanceKm={job?.eta_distance_km}
                      etaTrafficDelayMinutes={job?.eta_traffic_delay_minutes}
                      etaStatus={job?.eta_status}
                      etaUpdatedAt={job?.eta_updated_at}
                      etaMessage={job?.eta_message}
                      arrivedAt={job?.on_site_at}
                      workStartedAt={job?.work_started_at}
                      completedAt={job?.completed_at}
                      compact
                      useLiveUpdates={false}
                    />
                  </>
                )}

                <div
                  className="customer-notification-card__date"
                >
                  {notification.createdAt ? new Date(notification.createdAt).toLocaleString() : ""}
                </div>
              </div>

              <div className="customer-notification-card__actions">
              {!notification.isRead ? (
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    void markRead(notification.id);
                  }}
                  disabled={
                    Boolean(markingReadId) || markingAllRead
                  }
                  aria-label="Mark as read"
                  aria-busy={isMarkingThisRead}
                  title="Mark as read"
                  className="customer-notification-card__read-button"
                >
                  <Check size={16} />
                </button>
              ) : <span className="customer-notification-card__read-label"><Check size={14} /> Read</span>}
              </div>
            </article>
          );
        })}
        </section>
      )}
    </main>
  );
}
