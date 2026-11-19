import { useState, useEffect } from "react";
import {
  Bell,
  Check,
  CheckCheck,
  CheckCircle,
  XCircle,
  Briefcase,
  AlertTriangle,
  Clock,
  X,
  RefreshCw,
} from "lucide-react";
import {
  getTechnicianNotifications,
  markTechnicianNotificationRead,
  markAllTechnicianNotificationsRead,
  acceptTechnicianJob,
  rejectTechnicianJob,
} from "../../services/technicianPortalService";

export default function TechnicianNotificationsPage() {
  const [notifications, setNotifications] = useState<any[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // Reject Modal State
  const [rejectModalJobId, setRejectModalJobId] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [actionLoading, setActionLoading] = useState<string | number | null>(null);
  const [successBanner, setSuccessBanner] = useState("");

  const getNotificationErrorMessage = (error: any) => {
    const status = error?.response?.status;

    if (status === 403) {
      return "You are not authorized to view technician notifications.";
    }

    if (status === 404) {
      return "Technician notification history is currently unavailable.";
    }

    return "Unable to load notifications. Please try again.";
  };

  const loadNotifications = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await getTechnicianNotifications();
      const nextNotifications = Array.isArray(response?.data?.notifications)
        ? response.data.notifications
        : [];
      const nextUnread = Number(response?.data?.unread_count ?? 0);

      setNotifications(nextNotifications);
      setUnread(Number.isFinite(nextUnread) ? Math.max(0, nextUnread) : 0);
      setLastUpdated(new Date());
    } catch (loadError) {
      console.error("Failed to load technician notifications:", loadError);
      setError(getNotificationErrorMessage(loadError));
      // Preserve already-rendered notifications so a refresh failure is explicit
      // without replacing known-good data with an empty state.
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadNotifications();

    // Reconcile the notification center after existing technician/job workflows
    // dispatch the shared dashboard refresh event.
    const handleDashboardRefresh = () => {
      void loadNotifications();
    };

    window.addEventListener(
      "technician-dashboard-refresh",
      handleDashboardRefresh,
    );

    return () => {
      window.removeEventListener(
        "technician-dashboard-refresh",
        handleDashboardRefresh,
      );
    };
  }, []);

  const markRead = async (id: string) => {
    const notification = notifications.find(
      (item) => String(item.id) === String(id),
    );

    if (!notification || notification.isRead) {
      return;
    }

    setActionLoading(id);

    try {
      await markTechnicianNotificationRead(id);
      setNotifications((ns) =>
        ns.map((n) =>
          String(n.id) === String(id)
            ? { ...n, isRead: true }
            : n,
        ),
      );
      setUnread((u) => Math.max(0, u - 1));
      setError(null);
    } catch (markError) {
      console.error("Failed to mark notification as read:", markError);
      setError(
        getNotificationErrorMessage(markError),
      );
    } finally {
      setActionLoading(null);
    }
  };

  const markAllRead = async () => {
    if (unread <= 0) {
      return;
    }

    setActionLoading("all");

    try {
      await markAllTechnicianNotificationsRead();
      setNotifications((ns) =>
        ns.map((n) => ({ ...n, isRead: true })),
      );
      setUnread(0);
      setError(null);
    } catch (markAllError) {
      console.error(
        "Failed to mark all notifications as read:",
        markAllError,
      );
      setError(
        getNotificationErrorMessage(markAllError),
      );
    } finally {
      setActionLoading(null);
    }
  };

  const handleAccept = async (jobId: number, notifId: string) => {
    setActionLoading(notifId);
    try {
      await acceptTechnicianJob(jobId);
      await markRead(notifId);
      setSuccessBanner(`Job #${jobId} accepted successfully.`);
      setTimeout(() => setSuccessBanner(""), 4000);
      await loadNotifications();
    } catch (e: any) {
      console.error("Failed to accept job from notification center:", e);
      setError(
        e?.response?.data?.detail ||
          "Failed to accept job. Please try again.",
      );
    } finally {
      setActionLoading(null);
    }
  };

  const handleConfirmReject = async () => {
    if (!rejectModalJobId || rejectReason.length < 10) return;
    setActionLoading(rejectModalJobId);
    try {
      await rejectTechnicianJob(rejectModalJobId, rejectReason);
      setSuccessBanner(`Job #${rejectModalJobId} declined.`);
      setTimeout(() => setSuccessBanner(""), 4000);
      setRejectModalJobId(null);
      setRejectReason("");
      await loadNotifications();
    } catch (e: any) {
      console.error("Failed to decline job from notification center:", e);
      setError(
        e?.response?.data?.detail ||
          "Failed to decline job. Please try again.",
      );
    } finally {
      setActionLoading(null);
    }
  };

  const typeColor: Record<string, string> = {
    JOB_ASSIGNED: "#1E40AF",
    JOB_REASSIGNED: "#5B21B6",
    JOB_ACCEPTED: "#065F46",
    JOB_REJECTED: "#991B1B",
    JOB_UPDATED: "#92400E",
    JOB_CANCELLED: "#991B1B",
    SYSTEM: "#6B7280",
  };

  return (
    <div
      style={{
        padding: "20px 24px",
        height: "100%",
        overflowY: "auto",
        background: "#EEF4F1",
        fontFamily: "'Inter', sans-serif",
        boxSizing: "border-box",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "20px",
          background: "#FFFFFF",
          padding: "16px 20px",
          borderRadius: "12px",
          border: "1px solid #E3ECE7",
          boxShadow: "0 1px 4px rgba(47, 79, 62, 0.03)",
        }}
      >
        <div>
          <h2
            style={{
              fontSize: "20px",
              fontWeight: 700,
              color: "#2F4F3E",
              margin: 0,
              display: "flex",
              alignItems: "center",
              gap: "10px",
            }}
          >
            <Bell size={22} color="#7AAE8A" /> Job Assignment Notifications
            {unread > 0 && (
              <span
                style={{
                  fontSize: "12px",
                  background: "#E53E3E",
                  color: "#fff",
                  borderRadius: "20px",
                  padding: "2px 9px",
                  fontWeight: 700,
                }}
              >
                {unread} Unread
              </span>
            )}
          </h2>
          <p style={{ fontSize: "13px", color: "#6B7280", margin: "4px 0 0" }}>
            Real-time notifications sent by Super Admins, Admins, and Dispatchers
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <button
            type="button"
            onClick={() => void loadNotifications()}
            disabled={loading}
            aria-label="Refresh notifications"
            style={{
              background: "#FFFFFF",
              border: "1px solid #D1D5DB",
              borderRadius: "8px",
              padding: "8px 12px",
              fontSize: "12px",
              fontWeight: 600,
              color: "#374151",
              cursor: loading ? "not-allowed" : "pointer",
              display: "flex",
              alignItems: "center",
              gap: "6px",
              opacity: loading ? 0.6 : 1,
            }}
          >
            <RefreshCw size={14} /> Refresh
          </button>

          {unread > 0 && (
            <button
              type="button"
              onClick={() => void markAllRead()}
              disabled={actionLoading === "all"}
              style={{
                background: "#FFFFFF",
                border: "1px solid #D1D5DB",
                borderRadius: "8px",
                padding: "8px 16px",
                fontSize: "12px",
                fontWeight: 600,
                color: "#374151",
                cursor: actionLoading === "all" ? "not-allowed" : "pointer",
                display: "flex",
                alignItems: "center",
                gap: "6px",
                opacity: actionLoading === "all" ? 0.6 : 1,
              }}
            >
              <CheckCheck size={14} />
              {actionLoading === "all" ? "Marking..." : "Mark All Read"}
            </button>
          )}
        </div>
      </div>

      {successBanner && (
        <div
          style={{
            background: "#F0FFF4",
            border: "1px solid #C6F6D5",
            borderRadius: "8px",
            padding: "12px 16px",
            color: "#22543D",
            fontSize: "13px",
            fontWeight: 600,
            marginBottom: "16px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <CheckCircle size={16} /> {successBanner}
        </div>
      )}

      {error && (
        <div
          role="alert"
          style={{
            background: "#FEF2F2",
            border: "1px solid #FECACA",
            borderRadius: "8px",
            padding: "12px 16px",
            color: "#991B1B",
            fontSize: "13px",
            fontWeight: 600,
            marginBottom: "16px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "12px",
          }}
        >
          <span>{error}</span>
          <button
            type="button"
            onClick={() => void loadNotifications()}
            style={{
              border: "1px solid #FCA5A5",
              background: "#FFFFFF",
              color: "#991B1B",
              borderRadius: "6px",
              padding: "5px 9px",
              fontSize: "11px",
              fontWeight: 700,
              cursor: "pointer",
              flexShrink: 0,
            }}
          >
            Retry
          </button>
        </div>
      )}

      {lastUpdated && !loading && !error && (
        <div
          style={{
            marginBottom: "12px",
            fontSize: "11px",
            color: "#6B7280",
            textAlign: "right",
          }}
        >
          Last updated: {lastUpdated.toLocaleString()}
        </div>
      )}

      {/* Notifications List - Orderwise (1, 2, 3...) */}
      {loading && notifications.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: "60px",
            color: "#6B7280",
            background: "#FFFFFF",
            borderRadius: "12px",
            border: "1px solid #E3ECE7",
          }}
        >
          Loading notifications...
        </div>
      ) : notifications.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: "60px",
            color: "#9CA3AF",
            background: "#FFFFFF",
            borderRadius: "12px",
            border: "1px solid #E3ECE7",
          }}
        >
          No notifications found.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {notifications.map((n, index) => {
            const orderNum = index + 1; // Orderwise numbering 1, 2, 3...
            const isJobAssigned =
              ["JOB_ASSIGNED", "JOB_REASSIGNED"].includes(n.type) ||
              n.title?.toLowerCase().includes("assigned");
            const jobId = n.jobId ? parseInt(n.jobId, 10) : null;
            const canTakeAction =isJobAssigned && jobId &&["ASSIGNED", "PLANNED", "QUEUED","ACTIVE"].includes((n.jobStatus || "").toUpperCase());
            return (
              <div
                key={n.id}
                style={{
                  background: n.isRead ? "#FFFFFF" : "#F0FFF4",
                  borderRadius: "12px",
                  padding: "18px 20px",
                  boxShadow: "0 1px 4px rgba(0,0,0,0.04)",
                  border: `1.5px solid ${n.isRead ? "#E3ECE7" : "#B0D4BC"}`,
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                  gap: "16px",
                }}
              >
                {/* Order Index & Content */}
                <div style={{ display: "flex", gap: "14px", flex: 1 }}>
                  {/* Orderwise Badge */}
                  <div
                    style={{
                      minWidth: "32px",
                      height: "32px",
                      borderRadius: "8px",
                      background: n.isRead ? "#F1F5F9" : "#DCFCE7",
                      color: n.isRead ? "#64748B" : "#15803D",
                      fontSize: "13px",
                      fontWeight: 800,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}
                  >
                    #{orderNum}
                  </div>

                  <div style={{ flex: 1 }}>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "8px",
                        marginBottom: "6px",
                      }}
                    >
                      <span
                        style={{
                          fontSize: "10px",
                          fontWeight: 700,
                          padding: "2px 8px",
                          borderRadius: "10px",
                          background: (typeColor[n.type] || "#6B7280") + "18",
                          color: typeColor[n.type] || "#6B7280",
                          textTransform: "uppercase",
                        }}
                      >
                        {n.type || "NOTIFICATION"}
                      </span>
                      {!n.isRead && (
                        <span
                          style={{
                            fontSize: "10px",
                            fontWeight: 700,
                            color: "#15803D",
                            background: "#DCFCE7",
                            padding: "2px 6px",
                            borderRadius: "4px",
                          }}
                        >
                          NEW
                        </span>
                      )}
                    </div>

                    <div
                      style={{
                        fontSize: "15px",
                        fontWeight: 700,
                        color: "#1F2933",
                        marginBottom: "4px",
                      }}
                    >
                      {n.title}
                    </div>
                    <div
                      style={{
                        fontSize: "13px",
                        color: "#4B5563",
                        lineHeight: 1.5,
                      }}
                    >
                      {n.message}
                    </div>

                    <div
                      style={{
                        fontSize: "11px",
                        color: "#9CA3AF",
                        marginTop: "8px",
                        display: "flex",
                        alignItems: "center",
                        gap: "4px",
                      }}
                    >
                      <Clock size={12} />
                      {n.createdAt ? new Date(n.createdAt).toLocaleString() : ""}
                    </div>

                    {/* Quick Job Action Buttons */}
                    {canTakeAction && (
                      <div
                        style={{
                          display: "flex",
                          gap: "8px",
                          marginTop: "12px",
                          paddingTop: "10px",
                          borderTop: "1px solid #F0F0F0",
                        }}
                      >
                        <button
                          style={{
                            padding: "7px 16px",
                            border: "none",
                            borderRadius: "6px",
                            background: "#7AAE8A",
                            color: "#fff",
                            fontSize: "12px",
                            fontWeight: 700,
                            cursor: "pointer",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "5px",
                            opacity: actionLoading === n.id ? 0.7 : 1,
                          }}
                          disabled={actionLoading === n.id}
                          onClick={() => handleAccept(jobId, n.id)}
                        >
                          <CheckCircle size={14} /> Accept Job #{jobId}
                        </button>

                        <button
                          style={{
                            padding: "7px 16px",
                            border: "none",
                            borderRadius: "6px",
                            background: "#FEE2E2",
                            color: "#991B1B",
                            fontSize: "12px",
                            fontWeight: 700,
                            cursor: "pointer",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "5px",
                          }}
                          onClick={() => {
                            setRejectModalJobId(jobId);
                            setRejectReason("");
                          }}
                        >
                          <XCircle size={14} /> Decline
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                {/* Mark Read button */}
                {!n.isRead && (
                  <button
                    onClick={() => markRead(n.id)}
                    style={{
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                      color: "#7AAE8A",
                      padding: "4px",
                      borderRadius: "4px",
                    }}
                    title="Mark as read"
                    aria-label={`Mark notification ${n.id} as read`}
                    disabled={actionLoading === n.id}
                  >
                    <Check size={18} />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Reject Modal */}
      {rejectModalJobId && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 9999,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            style={{
              position: "absolute",
              inset: 0,
              background: "rgba(0,0,0,0.4)",
            }}
            onClick={() => setRejectModalJobId(null)}
          />
          <div
            style={{
              position: "relative",
              background: "#fff",
              borderRadius: "16px",
              padding: "24px",
              width: "90%",
              maxWidth: "420px",
              zIndex: 1,
            }}
          >
            <button
              onClick={() => setRejectModalJobId(null)}
              style={{
                position: "absolute",
                top: "12px",
                right: "12px",
                background: "none",
                border: "none",
                cursor: "pointer",
              }}
            >
              <X size={20} color="#6B7280" />
            </button>
            <h3
              style={{
                fontSize: "17px",
                fontWeight: 700,
                color: "#1F2933",
                marginBottom: "12px",
                display: "flex",
                alignItems: "center",
                gap: "8px",
              }}
            >
              <AlertTriangle size={18} color="#E53E3E" /> Decline Job #{rejectModalJobId}
            </h3>
            <label
              style={{
                fontSize: "12px",
                fontWeight: 600,
                color: "#374151",
                marginBottom: "6px",
                display: "block",
              }}
            >
              Rejection Reason (min 10 characters) *
            </label>
            <textarea
              style={{
                width: "100%",
                padding: "10px 12px",
                border: "1.5px solid #D1D5DB",
                borderRadius: "8px",
                fontSize: "13px",
                minHeight: "90px",
                resize: "vertical",
                boxSizing: "border-box",
                fontFamily: "'Inter', sans-serif",
                outline: "none",
              }}
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="State your reason for declining this job..."
            />
            <div
              style={{
                display: "flex",
                gap: "10px",
                marginTop: "16px",
                justifyContent: "flex-end",
              }}
            >
              <button
                style={{
                  padding: "8px 16px",
                  border: "1px solid #D1D5DB",
                  borderRadius: "8px",
                  background: "#fff",
                  fontSize: "12px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
                onClick={() => setRejectModalJobId(null)}
              >
                Cancel
              </button>
              <button
                style={{
                  padding: "8px 16px",
                  border: "none",
                  borderRadius: "8px",
                  background: "#FEE2E2",
                  color: "#991B1B",
                  fontSize: "12px",
                  fontWeight: 700,
                  cursor: "pointer",
                  opacity: rejectReason.length < 10 ? 0.5 : 1,
                }}
                disabled={rejectReason.length < 10}
                onClick={handleConfirmReject}
              >
                Confirm Decline
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
