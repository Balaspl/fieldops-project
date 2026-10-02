import { useState, useEffect, useCallback } from "react";
import { Bell, Check, CheckCheck } from "lucide-react";
import {
  getCustomerNotifications,
  markCustomerNotificationRead,
  markAllCustomerNotificationsRead,
} from "../../services/customerPortalService";

type CustomerNotification = {
  id: string;
  title?: string;
  message?: string;
  isRead?: boolean;
  createdAt?: string;
};

const getNotificationErrorMessage = (
  error: any,
): string => {
  const status = error?.response?.status;

  if (status === 401) {
    return "Your session has expired. Please sign in again.";
  }

  if (status === 403) {
    return "You do not have permission to view customer notifications.";
  }

  return "We couldn't load your notifications. Please try again.";
};

export default function CustomerNotificationsPage() {
  const [notifications, setNotifications] = useState<
    CustomerNotification[]
  >([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<
    string | null
  >(null);
  const [markingReadId, setMarkingReadId] = useState<
    string | null
  >(null);
  const [markingAllRead, setMarkingAllRead] =
    useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response =
        await getCustomerNotifications();

      const data = response?.data ?? {};
      const nextNotifications = Array.isArray(
        data.notifications,
      )
        ? data.notifications
        : [];

      const nextUnread =
        typeof data.unread_count === "number"
          ? Math.max(0, data.unread_count)
          : nextNotifications.filter(
                (notification: CustomerNotification) =>
                  !notification.isRead,
              ).length;

      setNotifications(nextNotifications);
      setUnread(nextUnread);
    } catch (requestError: any) {
      setError(
        getNotificationErrorMessage(requestError),
      );

      /*
       * Do not expose or derive internal backend details
       * in the customer-facing UI.
       */
      setNotifications([]);
      setUnread(0);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const markRead = async (id: string) => {
    if (markingReadId || markingAllRead) {
      return;
    }

    setMutationError(null);
    setMarkingReadId(id);

    try {
      await markCustomerNotificationRead(id);

      setNotifications((current) =>
        current.map((notification) =>
          notification.id === id
            ? {
                ...notification,
                isRead: true,
              }
            : notification,
        ),
      );

      setUnread((current) => {
        const target = notifications.find(
          (notification) =>
            notification.id === id,
        );

        return target?.isRead
          ? current
          : Math.max(0, current - 1);
      });
    } catch (requestError: any) {
      const status =
        requestError?.response?.status;

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

      setNotifications((current) =>
        current.map((notification) => ({
          ...notification,
          isRead: true,
        })),
      );

      setUnread(0);
    } catch (requestError: any) {
      const status =
        requestError?.response?.status;

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
    <div
      style={{
        padding: "24px",
        height: "100%",
        overflowY: "auto",
        background: "#EEF4F1",
        fontFamily: "'Inter', sans-serif",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "20px",
          gap: "12px",
          flexWrap: "wrap",
        }}
      >
        <h2
          style={{
            fontSize: "22px",
            fontWeight: 700,
            color: "#1F2933",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            margin: 0,
          }}
        >
          <Bell size={22} color="#7AAE8A" />
          Notifications

          {unread > 0 && (
            <span
              style={{
                fontSize: "12px",
                background: "#E53E3E",
                color: "#fff",
                borderRadius: "20px",
                padding: "2px 8px",
                fontWeight: 700,
              }}
            >
              {unread}
            </span>
          )}
        </h2>

        {unread > 0 && (
          <button
            type="button"
            onClick={() => void markAllRead()}
            disabled={markingAllRead || Boolean(markingReadId)}
            aria-busy={markingAllRead}
            style={{
              background: "none",
              border: "1px solid #D1D5DB",
              borderRadius: "8px",
              padding: "6px 14px",
              fontSize: "12px",
              fontWeight: 600,
              color: "#374151",
              cursor:
                markingAllRead || markingReadId
                  ? "not-allowed"
                  : "pointer",
              display: "flex",
              alignItems: "center",
              gap: "5px",
              opacity:
                markingAllRead || markingReadId
                  ? 0.6
                  : 1,
            }}
          >
            <CheckCheck size={14} />
            {markingAllRead
              ? "Updating..."
              : "Mark All Read"}
          </button>
        )}
      </div>

      {mutationError && (
        <div
          role="alert"
          style={{
            marginBottom: "12px",
            padding: "10px 12px",
            borderRadius: "10px",
            border: "1px solid #FCD34D",
            background: "#FFFBEB",
            color: "#92400E",
            fontSize: "13px",
          }}
        >
          {mutationError}
        </div>
      )}

      {loading ? (
        <div
          style={{
            textAlign: "center",
            padding: "48px",
            color: "#9CA3AF",
          }}
          role="status"
          aria-live="polite"
        >
          Loading notifications...
        </div>
      ) : error ? (
        <div
          style={{
            textAlign: "center",
            padding: "32px",
            background: "#fff",
            borderRadius: "14px",
            border: "1px solid #E3ECE7",
          }}
          role="alert"
        >
          <div
            style={{
              color: "#374151",
              fontSize: "14px",
              fontWeight: 600,
              marginBottom: "14px",
            }}
          >
            {error}
          </div>

          <button
            type="button"
            onClick={() => void load()}
            style={{
              background: "#7AAE8A",
              border: "none",
              borderRadius: "8px",
              padding: "8px 14px",
              color: "#fff",
              fontSize: "12px",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            Try Again
          </button>
        </div>
      ) : notifications.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: "48px",
            color: "#9CA3AF",
            background: "#fff",
            borderRadius: "14px",
            border: "1px solid #E3ECE7",
          }}
        >
          No notifications yet
        </div>
      ) : (
        notifications.map((notification) => {
          const isMarkingThisRead =
            markingReadId ===
            notification.id;

          return (
            <div
              key={notification.id}
              style={{
                background: notification.isRead
                  ? "#fff"
                  : "#F0FFF4",
                borderRadius: "12px",
                padding: "14px 18px",
                marginBottom: "10px",
                boxShadow:
                  "0 1px 4px rgba(0,0,0,0.04)",
                border: `1px solid ${
                  notification.isRead
                    ? "#E3ECE7"
                    : "#C6F6D5"
                }`,
                cursor: notification.isRead
                  ? "default"
                  : "pointer",
                display: "flex",
                justifyContent:
                  "space-between",
                alignItems: "flex-start",
                gap: "12px",
              }}
              onClick={() =>
                !notification.isRead &&
                void markRead(notification.id)
              }
            >
              <div>
                <div
                  style={{
                    fontSize: "14px",
                    fontWeight: 600,
                    color: "#1F2933",
                  }}
                >
                  {notification.title ||
                    "Notification"}
                </div>

                <div
                  style={{
                    fontSize: "13px",
                    color: "#6B7280",
                    marginTop: "2px",
                  }}
                >
                  {notification.message || ""}
                </div>

                <div
                  style={{
                    fontSize: "11px",
                    color: "#9CA3AF",
                    marginTop: "4px",
                  }}
                >
                  {notification.createdAt
                    ? new Date(
                        notification.createdAt,
                      ).toLocaleString()
                    : ""}
                </div>
              </div>

              {!notification.isRead && (
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    void markRead(
                      notification.id,
                    );
                  }}
                  disabled={
                    Boolean(markingReadId) ||
                    markingAllRead
                  }
                  aria-label="Mark as read"
                  aria-busy={isMarkingThisRead}
                  title="Mark as read"
                  style={{
                    background: "none",
                    border: "none",
                    cursor:
                      markingReadId ||
                      markingAllRead
                        ? "not-allowed"
                        : "pointer",
                    color: "#7AAE8A",
                    padding: "4px",
                    opacity:
                      markingReadId ||
                      markingAllRead
                        ? 0.5
                        : 1,
                  }}
                >
                  <Check size={16} />
                </button>
              )}
            </div>
          );
        })
      )}
    </div>
  );
}
