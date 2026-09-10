import { useState, useEffect } from "react";
import {
  CheckCircle,
  XCircle,
  Play,
  Pause,
  RotateCcw,
  AlertTriangle,
  MapPin,
  Phone,
  Clock,
  X,
  Check,
  IndianRupee,
  User,
  Navigation,
} from "lucide-react";
import {
  getTechnicianJobs,
  acceptTechnicianJob,
  rejectTechnicianJob,
  startTechnicianJob,
  pauseTechnicianJob,
  resumeTechnicianJob,
  completeTechnicianJob,
} from "../../services/technicianPortalService";
import { JobClosureModal } from "../../components/jobs/JobClosureModal";

const s = {
  page: {
    padding: "24px",
    height: "100%",
    overflowY: "auto" as const,
    background: "#EEF4F1",
    fontFamily: "'Inter', sans-serif",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "20px",
  },
  title: { fontSize: "22px", fontWeight: 700, color: "#1F2933" },
  card: {
    background: "#fff",
    borderRadius: "14px",
    padding: "20px",
    boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
    border: "1px solid #E3ECE7",
    marginBottom: "14px",
  },
  cardHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: "12px",
  },
  jobId: { fontSize: "11px", color: "#9CA3AF", fontWeight: 600 },
  jobTitle: { fontSize: "16px", fontWeight: 700, color: "#1F2933" },
  meta: {
    display: "flex",
    flexWrap: "wrap" as const,
    gap: "14px",
    marginBottom: "14px",
  },
  metaItem: {
    display: "flex",
    alignItems: "center",
    gap: "5px",
    fontSize: "13px",
    color: "#6B7280",
  },
  badge: (bg: string, fg: string) => ({
    fontSize: "11px",
    fontWeight: 600,
    padding: "3px 10px",
    borderRadius: "20px",
    background: bg,
    color: fg,
    display: "inline-block",
  }),
  actions: {
    display: "flex",
    gap: "8px",
    flexWrap: "wrap" as const,
    marginTop: "12px",
    paddingTop: "12px",
    borderTop: "1px solid #F0F0F0",
  },
  btn: (bg: string, fg: string) => ({
    padding: "8px 16px",
    border: "none",
    borderRadius: "8px",
    fontSize: "12px",
    fontWeight: 600,
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
    gap: "5px",
    background: bg,
    color: fg,
    transition: "opacity 0.2s",
  }),
  empty: {
    textAlign: "center" as const,
    color: "#9CA3AF",
    padding: "48px",
    fontSize: "14px",
  },
  modal: {
    position: "fixed" as const,
    inset: 0,
    zIndex: 9999,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  overlay: {
    position: "absolute" as const,
    inset: 0,
    background: "rgba(15, 23, 42, 0.5)",
    backdropFilter: "blur(4px)",
  },
  modalCard: {
    position: "relative" as const,
    background: "#fff",
    borderRadius: "20px",
    padding: "28px",
    width: "92%",
    maxWidth: "480px",
    zIndex: 1,
    boxShadow: "0 20px 60px rgba(0,0,0,0.18)",
    boxSizing: "border-box" as const,
  },
  modalTitle: {
    fontSize: "20px",
    fontWeight: 800,
    color: "#111827",
    marginBottom: "4px",
  },
  textarea: {
    width: "100%",
    padding: "10px 12px",
    border: "1.5px solid #D1D5DB",
    borderRadius: "8px",
    fontSize: "14px",
    minHeight: "100px",
    resize: "vertical" as const,
    boxSizing: "border-box" as const,
    fontFamily: "'Inter', sans-serif",
    outline: "none",
  },
  label: {
    fontSize: "12px",
    fontWeight: 600,
    color: "#374151",
    marginBottom: "6px",
    display: "block",
  },
};

const priorityStyle: Record<string, { bg: string; fg: string }> = {
  CRITICAL: { bg: "#FEE2E2", fg: "#991B1B" },
  HIGH: { bg: "#FEE2E2", fg: "#991B1B" },
  MEDIUM: { bg: "#FEF3C7", fg: "#92400E" },
  LOW: { bg: "#D1FAE5", fg: "#065F46" },
};

const statusStyle: Record<string, { bg: string; fg: string }> = {
  ASSIGNED: { bg: "#DBEAFE", fg: "#1E40AF" },
  ACCEPTED: { bg: "#D1FAE5", fg: "#065F46" },
  IN_PROGRESS: { bg: "#FEF3C7", fg: "#92400E" },
  PAUSED: { bg: "#E5E7EB", fg: "#374151" },
  EN_ROUTE: { bg: "#EDE9FE", fg: "#5B21B6" },
};

export default function TechnicianJobsPage() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [rejectModal, setRejectModal] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [completeModal, setCompleteModal] = useState<number | null>(null);
  const [completeNotes, setCompleteNotes] = useState("");
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  // Pop-up modal for newly assigned job
  const [assignedPopupJob, setAssignedPopupJob] = useState<any | null>(null);
  const [timerSeconds, setTimerSeconds] = useState(7194); // 119:54 default timer

  const loadJobs = () => {
    setLoading(true);
    getTechnicianJobs()
      .then((r) => {
        const list = r.data || [];
        setJobs(list);
        // Auto show popup modal for the first pending ASSIGNED job if not dismissed
        const pendingAssigned = list.find(
          (j: any) =>
            (j.status || "").toUpperCase() === "ASSIGNED" ||
            (j.status || "").toUpperCase() === "ACTIVE",
        );
        if (pendingAssigned) {
          setAssignedPopupJob(pendingAssigned);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(loadJobs, []);

  // Timer countdown effect for pop-up modal
  useEffect(() => {
    if (!assignedPopupJob) return;
    const interval = setInterval(() => {
      setTimerSeconds((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);
    return () => clearInterval(interval);
  }, [assignedPopupJob]);

  const formatTimer = (secs: number) => {
    const mins = Math.floor(secs / 60);
    const remainderSecs = secs % 60;
    return `${mins}:${remainderSecs < 10 ? "0" : ""}${remainderSecs}`;
  };

  const doAction = async (id: number, action: () => Promise<any>) => {
    setActionLoading(id);
    try {
      await action();
      loadJobs();
    } catch (e: any) {
      alert(e.response?.data?.detail || "Action failed");
    } finally {
      setActionLoading(null);
    }
  };

  const handlePopupAccept = async () => {
    if (!assignedPopupJob) return;
    const jobId = assignedPopupJob.id;
    setActionLoading(jobId);
    try {
      await acceptTechnicianJob(jobId);
      setAssignedPopupJob(null);
      loadJobs();
    } catch (e: any) {
      alert(e.response?.data?.detail || "Failed to accept job.");
    } finally {
      setActionLoading(null);
    }
  };

  const handlePopupRejectClick = () => {
    if (!assignedPopupJob) return;
    const jobId = assignedPopupJob.id;
    setAssignedPopupJob(null);
    setRejectModal(jobId);
  };

  const handleReject = async () => {
    if (!rejectModal || rejectReason.length < 10) return;
    setActionLoading(rejectModal);
    try {
      await rejectTechnicianJob(rejectModal, rejectReason);
      setJobs((prev) => prev.filter((j) => j.id !== rejectModal));
      setRejectModal(null);
      setRejectReason("");
      loadJobs();
    } catch (e: any) {
      alert(e.response?.data?.detail || "Reject failed");
    } finally {
      setActionLoading(null);
    }
  };

  const handleComplete = async () => {
    if (!completeModal) return;
    setActionLoading(completeModal);
    try {
      await completeTechnicianJob(completeModal, {
        completion_notes: completeNotes,
      });

      setCompleteModal(null);
      setCompleteNotes("");

      loadJobs();

      // Refresh technician dashboard statistics
      window.dispatchEvent(new CustomEvent("technician-dashboard-refresh"));
    } catch (e: any) {
      alert(e.response?.data?.detail || "Complete failed");
    } finally {
      setActionLoading(null);
    }
  };

  const getActions = (job: any) => {
    const st = (job.status || "").toUpperCase();
    const btns = [];
    if (["ASSIGNED", "ACTIVE"].includes(st)) {
      btns.push(
        <button
          key="accept"
          style={s.btn("#D1FAE5", "#065F46")}
          onClick={() => doAction(job.id, () => acceptTechnicianJob(job.id))}
        >
          <CheckCircle size={14} /> Accept
        </button>,
      );
      btns.push(
        <button
          key="reject"
          style={s.btn("#FEE2E2", "#991B1B")}
          onClick={() => setRejectModal(job.id)}
        >
          <XCircle size={14} /> Reject
        </button>,
      );
    }
    if (["ACCEPTED", "EN_ROUTE"].includes(st)) {
      btns.push(
        <button
          key="start"
          style={s.btn("#DBEAFE", "#1E40AF")}
          onClick={() => doAction(job.id, () => startTechnicianJob(job.id))}
        >
          <Play size={14} /> Start
        </button>,
      );
    }
    if (["IN_PROGRESS", "PAUSED"].includes(st)) {
      btns.push(
        <button
          key="complete"
          style={{
            background: "rgba(220, 252, 231, 0.35)",
            color: "#059669",
            border: "1.5px solid #059669",
            borderRadius: "8px",
            padding: "10px 20px",
            minWidth: "120px",
            height: "40px",
            fontSize: "12px",
            fontWeight: 700,
            cursor: "pointer",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "6px",
            textTransform: "uppercase",
            letterSpacing: "0.5px",
            transition: "all 0.2s ease",
          }}
          onClick={() => setCompleteModal(job.id)}
        >
          Complete
        </button>,
      );
    }
    return btns;
  };

  if (loading)
    return (
      <div style={s.page}>
        <div style={s.empty}>Loading jobs...</div>
      </div>
    );

  return (
    <div style={s.page}>
      <div style={s.header}>
        <h2 style={s.title}>Assigned Jobs</h2>
        <span style={{ fontSize: "13px", color: "#6B7280" }}>
          {jobs.length} job(s)
        </span>
      </div>

      {jobs.length === 0 ? (
        <div style={s.empty}>No active jobs assigned to you</div>
      ) : (
        jobs.map((job) => (
          <div key={job.id} style={s.card}>
            <div style={s.cardHeader}>
              <div>
                <span style={s.jobId}>JOB #{job.id}</span>
                <div style={s.jobTitle}>
                  {job.service_type || "Service Request"}
                </div>
              </div>
              <div style={{ display: "flex", gap: "6px" }}>
                <span
                  style={s.badge(
                    priorityStyle[job.priority]?.bg || "#E5E7EB",
                    priorityStyle[job.priority]?.fg || "#374151",
                  )}
                >
                  {job.priority || "MEDIUM"}
                </span>
              </div>
            </div>
            <div style={s.meta}>
              <span style={s.metaItem}>
                <MapPin size={14} /> {job.location || "N/A"}
              </span>
              <span style={s.metaItem}>
                <Phone size={14} /> {job.contact_number || "N/A"}
              </span>
              <span style={s.metaItem}>
                <Clock size={14} /> {job.preferred_service_date || "N/A"}
              </span>
            </div>
            {job.issue_description && (
              <div
                style={{
                  fontSize: "13px",
                  color: "#4B5563",
                  marginBottom: "8px",
                  lineHeight: 1.5,
                }}
              >
                {job.issue_description}
              </div>
            )}
            <div
              style={{
                ...s.actions,
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <span
                style={{
                  fontSize: "12px",
                  fontWeight: 700,
                  color:
                    job.status === "COMPLETED"
                      ? "#059669"
                      : job.status === "IN_PROGRESS"
                        ? "#D97706"
                        : "#5B21B6",
                }}
              >
                {job.status === "COMPLETED" ? "✓ COMPLETED" : job.status}
              </span>

              <div style={{ display: "flex", gap: "8px" }}>
                {getActions(job)}
              </div>
            </div>
          </div>
        ))
      )}

      {/* ── JOB ASSIGNED POPUP MODAL (Matching requested design without Reassign button) ── */}
      {assignedPopupJob && (
        <div style={s.modal}>
          <div style={s.overlay} onClick={() => setAssignedPopupJob(null)} />
          <div style={s.modalCard}>
            {/* Header row: ID + Priority badge + Close button */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "4px",
              }}
            >
              <span
                style={{ fontSize: "13px", fontWeight: 700, color: "#6B7280" }}
              >
                Job ID: #{assignedPopupJob.id}
              </span>
              <div
                style={{ display: "flex", alignItems: "center", gap: "10px" }}
              >
                <span
                  style={s.badge(
                    priorityStyle[assignedPopupJob.priority]?.bg || "#FEF3C7",
                    priorityStyle[assignedPopupJob.priority]?.fg || "#92400E",
                  )}
                >
                  {assignedPopupJob.priority || "MEDIUM"}
                </span>
                <button
                  onClick={() => setAssignedPopupJob(null)}
                  style={{
                    background: "#F3F4F6",
                    border: "none",
                    borderRadius: "50%",
                    width: "30px",
                    height: "30px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    cursor: "pointer",
                    color: "#6B7280",
                  }}
                >
                  <X size={18} />
                </button>
              </div>
            </div>

            <h3 style={s.modalTitle}>Job Assigned</h3>

            {/* Countdown Banner */}
            <div
              style={{
                background: "#ECFDF5",
                border: "1px solid #A7F3D0",
                borderRadius: "12px",
                padding: "12px 16px",
                display: "flex",
                alignItems: "center",
                gap: "10px",
                marginTop: "12px",
                marginBottom: "20px",
              }}
            >
              <Clock size={20} color="#059669" />
              <div
                style={{ display: "flex", alignItems: "baseline", gap: "8px" }}
              >
                <span
                  style={{
                    fontSize: "18px",
                    fontWeight: 800,
                    color: "#065F46",
                    fontFamily: "monospace",
                    letterSpacing: "0.05em",
                  }}
                >
                  {formatTimer(timerSeconds)}
                </span>
                <span
                  style={{
                    fontSize: "12px",
                    fontWeight: 700,
                    color: "#047857",
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                  }}
                >
                  REMAINING
                </span>
              </div>
            </div>

            {/* 2x2 Grid Info */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "16px",
                marginBottom: "18px",
              }}
            >
              <div>
                <div
                  style={{
                    fontSize: "11px",
                    fontWeight: 700,
                    color: "#9CA3AF",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    marginBottom: "4px",
                  }}
                >
                  CUSTOMER
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    fontSize: "14px",
                    fontWeight: 600,
                    color: "#1F2933",
                  }}
                >
                  <User size={15} color="#6B7280" />
                  {assignedPopupJob.customer_name || "Demo Customer"}
                </div>
              </div>

              <div>
                <div
                  style={{
                    fontSize: "11px",
                    fontWeight: 700,
                    color: "#9CA3AF",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    marginBottom: "4px",
                  }}
                >
                  CONTACT
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    fontSize: "14px",
                    fontWeight: 600,
                    color: "#2563EB",
                  }}
                >
                  <Phone size={15} color="#2563EB" />
                  {assignedPopupJob.contact_number || "+91 9876543210"}
                </div>
              </div>

              <div>
                <div
                  style={{
                    fontSize: "11px",
                    fontWeight: 700,
                    color: "#9CA3AF",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    marginBottom: "4px",
                  }}
                >
                  DISTANCE
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    fontSize: "14px",
                    fontWeight: 600,
                    color: "#4B5563",
                  }}
                >
                  <Navigation size={15} color="#4B5563" />
                  1.2 km
                </div>
              </div>

              <div>
                <div
                  style={{
                    fontSize: "11px",
                    fontWeight: 700,
                    color: "#9CA3AF",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    marginBottom: "4px",
                  }}
                >
                  EST. VALUE
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    fontSize: "14px",
                    fontWeight: 700,
                    color: "#059669",
                  }}
                >
                  <IndianRupee size={15} color="#059669" />
                  ₹250
                </div>
              </div>
            </div>

            {/* Service & Location Description */}
            <div
              style={{
                background: "#F9FAFB",
                borderRadius: "10px",
                padding: "12px 14px",
                marginBottom: "20px",
                border: "1px solid #F3F4F6",
              }}
            >
              <div
                style={{
                  fontSize: "14px",
                  fontWeight: 700,
                  color: "#1F2933",
                  marginBottom: "6px",
                }}
              >
                {assignedPopupJob.service_type || "Plumbing Service"}
              </div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  fontSize: "13px",
                  color: "#6B7280",
                }}
              >
                <MapPin size={15} color="#EF4444" />
                {assignedPopupJob.location || "paramakudi"}
              </div>
            </div>

            {/* Action Buttons (Accept Job + Reject ONLY, NO Reassign) */}
            <div style={{ display: "flex", gap: "12px", marginTop: "12px" }}>
              <button
                onClick={handlePopupAccept}
                disabled={actionLoading === assignedPopupJob.id}
                style={{
                  flex: 1,
                  height: "46px",
                  background: "#059669",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: "12px",
                  fontSize: "15px",
                  fontWeight: 700,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "8px",
                  boxShadow: "0 4px 12px rgba(5, 150, 105, 0.25)",
                }}
              >
                <Check size={18} />
                {actionLoading === assignedPopupJob.id
                  ? "Accepting..."
                  : "Accept Job"}
              </button>

              <button
                onClick={handlePopupRejectClick}
                style={{
                  flex: 1,
                  height: "46px",
                  background: "#EF4444",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: "12px",
                  fontSize: "15px",
                  fontWeight: 700,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "8px",
                  boxShadow: "0 4px 12px rgba(239, 68, 68, 0.25)",
                }}
              >
                <X size={18} />
                Reject
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reject Reason Modal */}
      {rejectModal && (
        <div style={s.modal}>
          <div style={s.overlay} onClick={() => setRejectModal(null)} />
          <div style={s.modalCard}>
            <button
              onClick={() => setRejectModal(null)}
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
            <div style={s.modalTitle}>
              <AlertTriangle
                size={20}
                color="#E53E3E"
                style={{ marginRight: "8px", verticalAlign: "middle" }}
              />
              Reject Job #{rejectModal}
            </div>
            <label style={s.label}>
              Rejection Reason (min 10 characters) *
            </label>
            <textarea
              style={s.textarea as any}
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Explain why you're rejecting this job..."
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
                style={s.btn("#E5E7EB", "#374151")}
                onClick={() => setRejectModal(null)}
              >
                Cancel
              </button>
              <button
                style={{
                  ...s.btn("#FEE2E2", "#991B1B"),
                  opacity: rejectReason.length < 10 ? 0.5 : 1,
                }}
                onClick={handleReject}
                disabled={rejectReason.length < 10}
              >
                Confirm Reject
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Job Closure Form Modal */}
      {completeModal && (
        <JobClosureModal
          jobId={completeModal}
          isOpen={!!completeModal}
          onClose={() => setCompleteModal(null)}
          onSuccess={() => {
            setCompleteModal(null);
            loadJobs();

            // Refresh technician dashboard statistics
            window.dispatchEvent(
              new CustomEvent("technician-dashboard-refresh"),
            );
          }}
        />
      )}
    </div>
  );
}
