/**
 * NotificationDetail.tsx
 * Refactored to use modular CountdownTimer, ActionButtons, and WaitingState components.
 */
import React, { useState, useEffect } from "react";
import { MapPin, Phone, User, DollarSign, Navigation, AlertTriangle, X } from "lucide-react";
import { motion } from "framer-motion";
import { NotificationDetailProps } from "../../types/notifications";
import CountdownTimer from "./CountdownTimer";
import ActionButtons from "./ActionButtons";
import WaitingState from "./WaitingState";
import useActionState from "../../hooks/useActionState";
import { getOverrideHistory } from "../../services/planningService";
import OverrideWarning from "./OverrideWarning";
import OverrideHistory from "./OverrideHistory";
import { io } from "socket.io-client";

const styles = {
  backdrop: {
    position: "fixed",
    top: 0,
    left: 0,
    width: "100%",
    height: "100%",
    backgroundColor: "rgba(15, 23, 42, 0.4)",
    backdropFilter: "blur(4px)",
    zIndex: 1001,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "20px",
  } as React.CSSProperties,

  card: {
    backgroundColor: "#ffffff",
    borderRadius: "12px",
    border: "1px solid #e2e8f0",
    boxShadow: "0 4px 12px rgba(15, 23, 42, 0.05)",
    padding: "24px",
    maxWidth: "600px",
    width: "100%",
    marginRight: "auto",
    marginLeft: "auto",
    boxSizing: "border-box",
    position: "relative",
    fontFamily: "'Inter', sans-serif",
  } as React.CSSProperties,

  closeBtn: {
    position: "absolute",
    top: "12px",
    right: "12px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: "28px",
    height: "28px",
    borderRadius: "50%",
    border: "none",
    background: "#f1f5f9",
    cursor: "pointer",
    color: "#64748b",
    transition: "background-color 0.2s, color 0.2s",
    padding: 0,
    zIndex: 10,
  } as React.CSSProperties,

  header: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    marginBottom: "16px",
    flexWrap: "wrap",
    gap: "8px",
  } as React.CSSProperties,

  headerTitle: {
    margin: 0,
    fontSize: "20px",
    fontWeight: 700,
    color: "#0f172a",
  } as React.CSSProperties,

  priorityBadge: {
    padding: "4px 8px",
    fontSize: "11px",
    fontWeight: 700,
    borderRadius: "4px",
    textTransform: "uppercase",
  } as React.CSSProperties,

  rowGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
    gap: "16px",
    marginBottom: "18px",
  } as React.CSSProperties,

  gridItem: {
    display: "flex",
    flexDirection: "column",
  } as React.CSSProperties,

  gridLabel: {
    fontSize: "12px",
    color: "#94a3b8",
    textTransform: "uppercase",
    fontWeight: 600,
    letterSpacing: "0.05em",
    marginBottom: "4px",
  } as React.CSSProperties,

  gridValue: {
    fontSize: "14px",
    color: "#334155",
    fontWeight: 500,
  } as React.CSSProperties,

  description: {
    fontSize: "13.5px",
    color: "#475569",
    lineHeight: 1.5,
    margin: "8px 0",
  } as React.CSSProperties,

  skillsContainer: {
    display: "flex",
    flexWrap: "wrap",
    gap: "6px",
    marginBottom: "16px",
  } as React.CSSProperties,

  skillChip: {
    padding: "4px 10px",
    fontSize: "12px",
    fontWeight: 500,
    borderRadius: "12px",
    backgroundColor: "#f1f5f9",
    color: "#475569",
  } as React.CSSProperties,
};

const priorities: Record<string, { bg: string; color: string }> = {
  critical: { bg: "#fee2e2", color: "#ef4444" },
  high: { bg: "#fee2e2", color: "#ef4444" },
  medium: { bg: "#fef3c7", color: "#d97706" },
  low: { bg: "#f1f5f9", color: "#64748b" },
};

const localCss = `
  .detail-close-btn-style:hover { background-color: #e2e8f0 !important; color: #0f172a !important; }
`;

export const NotificationDetail: React.FC<NotificationDetailProps> = ({
  notification,
  job,
  loading = false,
  error,
  onAccept,
  onReject,
  onReassign,
  onClose
}) => {
  const jobData = job || notification.job;
  const { state: actionState, message: actionMessage, execute, retry, reset } = useActionState();
  const [overrideLogs, setOverrideLogs] = useState<any[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    if (!jobData?.id) return;

    const fetchHistory = async () => {
      try {
        const res = await getOverrideHistory(jobData.id);
        if (res && res.data) {
          setOverrideLogs(res.data);
        }
      } catch (err) {
        console.warn("Failed to fetch override history in detail view", err);
      }
    };

    fetchHistory();

    // Guard: don't connect socket if URL is not configured
    const socketUrl = import.meta.env.VITE_SOCKET_URL;
    if (!socketUrl) {
      return;
    }

    let socket: ReturnType<typeof io>;
    try {
      socket = io(socketUrl, {
        transports: ["websocket", "polling"],
        reconnectionAttempts: 5,
        reconnectionDelay: 2000,
        timeout: 10000,
      });
    } catch (err) {
      console.warn("NotificationDetail: Failed to create socket connection", err);
      return;
    }

    socket.on("connect_error", (err) => {
      console.warn("NotificationDetail: Socket connection error:", err.message);
    });

    socket.on("override:new", (data: any) => {
      if (data && (data.job_id === jobData.id || data.job_id === String(jobData.id))) {
        const newOverride = data.override || data;
        setOverrideLogs(prev => {
          if (prev.some(item => item.id === newOverride.id)) return prev;
          return [newOverride, ...prev];
        });
      }
    });

    return () => {
      socket.disconnect();
    };
  }, [jobData?.id]);

  if (loading) {
    return (
      <div style={{ boxSizing: "border-box" }}>
        <div style={{ ...styles.card, display: "flex", justifyContent: "center", alignItems: "center", height: "300px" }}>
          <div className="tld-refresh-spinner-local" style={{
            width: "24px",
            height: "24px",
            border: "2px solid #e2e8f0",
            borderTopColor: "#3b82f6",
            borderRadius: "50%",
            animation: "local-spin 1s linear infinite",
          }} />
          <style>{`@keyframes local-spin { to { transform: rotate(360deg); } }`}</style>
          <span style={{ marginLeft: "12px", color: "#64748b" }}>Loading job details…</span>
        </div>
      </div>
    );
  }

  if (error || !jobData) {
    return (
      <div style={{ boxSizing: "border-box" }}>
        <div style={{ ...styles.card, textAlign: "center", padding: "40px" }}>
          <AlertTriangle size={40} color="#ef4444" style={{ margin: "0 auto 12px auto" }} />
          <p style={{ fontWeight: 600, color: "#1e293b", margin: "0 0 8px 0" }}>Failed to load job details</p>
          <p style={{ fontSize: "14px", color: "#64748b", margin: "0 0 20px 0" }}>{error || "Job data could not be found."}</p>
          <button
            type="button"
            style={{
              height: "36px",
              padding: "0 14px",
              fontSize: "13px",
              fontWeight: 600,
              color: "#64748b",
              backgroundColor: "#f1f5f9",
              border: "none",
              borderRadius: "6px",
              cursor: "pointer",
            }}
            onClick={onClose}
          >
            Close Detail
          </button>
        </div>
      </div>
    );
  }

  // Wrap parent callbacks with useActionState lifecycle
  const handleAccept = async (jobId: string | number) => {
    await execute(
      async () => {
        await onAccept(jobId);
      },
      "Job accepted"
    );
  };

  const handleReject = async (jobId: string | number, reason: string) => {
    await execute(
      async () => {
        await onReject(jobId, reason);
      },
      "Job rejected"
    );
  };

  const handleReassign = async (
    jobId: string | number,
    colleagueId?: number,
    reason?: string
  ) => {
    await execute(
      async () => {
        await onReassign(jobId, colleagueId, reason);
      },
      "Reassignment requested"
    );
  };

  const handleExpire = () => {
    console.warn(`Timer expired for job ${jobData.id}`);
  };

  const handleWarning = () => {
    console.warn(`2 minutes remaining for job ${jobData.id}`);
  };

  const isActioned = actionState === "SUCCESS";
  const priorityLower = (jobData.priority || "medium").toLowerCase();
  const priorityColor = priorities[priorityLower] || priorities.medium;

  return (
    <div style={styles.backdrop} onClick={onClose}>
      <style>{localCss}</style>
      <motion.div
        style={{ ...styles.card, position: "relative" }}
        onClick={(e) => e.stopPropagation()}
        drag="x"
        dragConstraints={{ left: 0, right: 300 }}
        dragElastic={{ left: 0.1, right: 0.5 }}
        onDragEnd={(e, info) => {
          if (info.offset.x > 150) {
            onClose();
          }
        }}
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0 }}
      >
        {/* Close Button */}
        <button
          type="button"
          onClick={onClose}
          className="detail-close-btn-style"
          style={styles.closeBtn}
          aria-label="Close details"
          title="Close details"
        >
          <X size={18} />
        </button>

        {/* Waiting State Overlay */}
        <WaitingState
          state={actionState}
          message={actionMessage}
          onRetry={retry}
          onCancel={reset}
          onClose={onClose}
        />

        {/* Card Body */}
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          {/* Header */}
          <div style={{ ...styles.header, padding: "0 24px 0 0", borderBottom: "none", gap: "4px", marginBottom: "4px" }}>
            <div>
              <span style={{ display: "block", marginBottom: "2px", fontSize: "10px", color: "#94a3b8", fontWeight: 600 }}>
                Job ID: #{jobData.id}
              </span>
              <h2 style={{ ...styles.headerTitle, fontSize: "17px", fontWeight: 700 }}>{jobData.title}</h2>
            </div>
            <span 
              style={{ 
                ...styles.priorityBadge, 
                backgroundColor: priorityColor.bg, 
                color: priorityColor.color,
                padding: "2px 6px", 
                fontSize: "10px" 
              }}
            >
              {jobData.priority}
            </span>
          </div>

          {/* Override Warning Banner */}
          {overrideLogs.length > 0 && (
            <div style={{ marginBottom: "4px" }}>
              <OverrideWarning
                actorName={overrideLogs[0].actor_name}
                actorRole={overrideLogs[0].actor_role}
                assignedAt={overrideLogs[0].created_at}
                reason={overrideLogs[0].justification}
                onViewHistory={() => setShowHistory(true)}
              />
            </div>
          )}

          {/* Countdown Timer */}
          {jobData.sla_deadline && (
            <CountdownTimer
              expiresAt={jobData.sla_deadline}
              onExpire={handleExpire}
              onWarning={handleWarning}
              jobId={Number(jobData.id)}
              hidden={isActioned}
              condensed={true}
            />
          )}

          {/* Job Details Grid */}
          <div style={{ ...styles.rowGrid, marginBottom: "8px" }}>
            <div style={styles.gridItem}>
              <span style={styles.gridLabel}>Customer</span>
              <span style={{ ...styles.gridValue, display: "flex", alignItems: "center", gap: "4px", fontSize: "12px" }}>
                <User size={12} color="#64748b" /> {jobData.customer_name}
              </span>
            </div>
            <div style={styles.gridItem}>
              <span style={styles.gridLabel}>Contact</span>
              <span style={{ ...styles.gridValue, fontSize: "12px" }}>
                <a href={`tel:${jobData.customer_phone}`} style={{ display: "flex", alignItems: "center", gap: "4px", color: "#3b82f6", textDecoration: "none" }}>
                  <Phone size={12} /> {jobData.customer_phone}
                </a>
              </span>
            </div>
            <div style={styles.gridItem}>
              <span style={styles.gridLabel}>Distance</span>
              <span style={{ ...styles.gridValue, display: "flex", alignItems: "center", gap: "4px", fontSize: "12px" }}>
                <Navigation size={12} color="#64748b" /> {jobData.distance_km} km
              </span>
            </div>
            <div style={styles.gridItem}>
              <span style={styles.gridLabel}>Est. Value</span>
              <span style={{ ...styles.gridValue, display: "flex", alignItems: "center", gap: "2px", fontWeight: 700, color: "#10b981", fontSize: "12px" }}>
                ${jobData.estimated_value}
              </span>
            </div>
          </div>

          {/* Compact Description */}
          <p style={styles.description}>
            {jobData.description}
          </p>

          {/* Inline Location Address (No huge map placeholder!) */}
          <div style={{ display: "flex", alignItems: "center", gap: "6px", margin: "2px 0 6px 0" }}>
            <MapPin size={14} color="#ef4444" style={{ flexShrink: 0 }} />
            <span style={{ fontSize: "12px", color: "#475569", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={jobData.location}>
              {jobData.location}
            </span>
          </div>

          {/* Compact Skills Chips */}
          <div style={{ ...styles.skillsContainer, gap: "4px", marginBottom: "4px" }}>
            {jobData.required_skills?.map((skill: string) => (
              <span key={skill} style={{ ...styles.skillChip, padding: "2px 6px", fontSize: "10.5px" }}>
                {skill}
              </span>
            ))}
          </div>
        </div>

        {/* Action Buttons (Fixed Footer) */}
        <div style={{ borderTop: "1px solid #f1f5f9", paddingTop: "12px", marginTop: "4px" }}>
          <ActionButtons
            onAccept={handleAccept}
            onReject={handleReject}
            onReassign={handleReassign}
            jobId={Number(jobData.id)}
            disabled={actionState !== "IDLE"}
          />
        </div>
      </motion.div>

      {showHistory && (
        <OverrideHistory
          jobId={Number(jobData.id)}
          jobTitle={jobData.title}
          onClose={() => setShowHistory(false)}
        />
      )}
    </div>
  );
};

export default NotificationDetail;