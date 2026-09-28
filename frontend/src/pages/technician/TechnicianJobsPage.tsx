import {
  useState,
  useEffect,
  useRef,
  type ReactNode,
} from "react";
import {
  CheckCircle,
  XCircle,
  Play,
  AlertTriangle,
  MapPin,
  Phone,
  Clock,
  X,
  Check,
  User,
  LoaderCircle,
  Navigation,
} from "lucide-react";

import {
  getTechnicianJobs,
  acceptTechnicianJob,
  rejectTechnicianJob,
  startTechnicianJob,
  onSiteTechnicianJob,
} from "../../services/technicianPortalService";

import { JobClosureModal } from "../../components/jobs/JobClosureModal";
import CustomerSignatureModal from "../../components/jobs/CustomerSignatureModal";
import JobLiveTrackingMap from "../../components/customer-tracking/JobLiveTrackingMap";

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
  title: {
    fontSize: "22px",
    fontWeight: 700,
    color: "#1F2933",
  },
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
  jobId: {
    fontSize: "11px",
    color: "#9CA3AF",
    fontWeight: 600,
  },
  jobTitle: {
    fontSize: "16px",
    fontWeight: 700,
    color: "#1F2933",
  },
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
  ACTIVE: { bg: "#DBEAFE", fg: "#1E40AF" },
  ACCEPTED: { bg: "#D1FAE5", fg: "#16A34A" },
  ON_SITE: { bg: "#FFEDD5", fg: "#C2410C" },
  IN_PROGRESS: { bg: "#FFEDD5", fg: "#C2410C" },
  PAUSED: { bg: "#E5E7EB", fg: "#374151" },
  EN_ROUTE: { bg: "#EDE9FE", fg: "#5B21B6" },
  COMPLETED: { bg: "#D1FAE5", fg: "#059669" },
  CLOSED: { bg: "#D1FAE5", fg: "#059669" },
};

const normalizeStatus = (status: unknown): string =>
  String(status ?? "").trim().toUpperCase();

const getStatusLabel = (status: unknown): string => {
  switch (normalizeStatus(status)) {
    case "ASSIGNED":
    case "ACTIVE":
      return "AWAITING ACCEPTANCE";
    case "ACCEPTED":
      return "ACCEPTED";
    case "EN_ROUTE":
      return "EN ROUTE";
    case "ON_SITE":
    case "IN_PROGRESS":
    case "PAUSED":
      return "IN PROGRESS";
    case "COMPLETED":
    case "CLOSED":
      return "COMPLETED";
    default:
      return String(status || "UNKNOWN");
  }
};

const formatSchedule = (job: any): string => {
  const date = job?.preferred_service_date;
  const time = job?.preferred_service_time;

  if (date && time) return `${date} ${time}`;
  return date || time || "N/A";
};

const getBackendActionErrorMessage = (
  error: unknown,
  fallback: string,
): string => {
  const response = (error as any)?.response;
  const detail = response?.data?.detail;

  if (typeof detail === "string" && detail.trim()) return detail;

  if (detail && typeof detail === "object") {
    if (typeof detail.message === "string" && detail.message.trim()) {
      return detail.message;
    }
    if (typeof detail.error === "string" && detail.error.trim()) {
      return detail.error;
    }
  }

  if (
    typeof response?.data?.message === "string" &&
    response.data.message.trim()
  ) {
    return response.data.message;
  }

  if (error instanceof Error && error.message) return error.message;

  return fallback;
};

const hasValidCoordinates = (job: any): boolean => {
  const lat = Number(job?.site_latitude);
  const lng = Number(job?.site_longitude);

  return (
    Number.isFinite(lat) &&
    Number.isFinite(lng) &&
    lat >= -90 &&
    lat <= 90 &&
    lng >= -180 &&
    lng <= 180
  );
};

export default function TechnicianJobsPage() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [lastJobsSync, setLastJobsSync] = useState<Date | null>(null);

  const [rejectModal, setRejectModal] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const [completeModal, setCompleteModal] = useState<number | null>(null);
  const [customerSignatureModal, setCustomerSignatureModal] =
    useState<number | null>(null);

  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const startInFlightRef = useRef<Set<number>>(new Set());
  const onSiteInFlightRef = useRef<Set<number>>(new Set());

  const [liveJob, setLiveJob] = useState<any | null>(null);

  const [assignedPopupJob, setAssignedPopupJob] = useState<any | null>(null);
  const [timerSeconds, setTimerSeconds] = useState(7194);

  const loadJobs = async () => {
    setLoading(true);

    try {
      const response = await getTechnicianJobs();
      const list = Array.isArray(response?.data) ? response.data : [];

      setJobs(list);
      setJobsError(null);
      setLastJobsSync(new Date());

      const pendingAssigned = list.find((job: any) => {
        const status = normalizeStatus(job?.status);
        return status === "ASSIGNED" || status === "ACTIVE";
      });

     if (pendingAssigned) {
  setAssignedPopupJob(pendingAssigned);
}
    } catch (error) {
      console.error("Failed to load technician jobs:", error);
      setJobsError("Unable to load your assigned jobs. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadJobs();
  }, []);

  useEffect(() => {
    if (!assignedPopupJob) return;

    const interval = window.setInterval(() => {
      setTimerSeconds((prev) => (prev > 0 ? prev - 1 : 0));
    }, 1000);

    return () => window.clearInterval(interval);
  }, [assignedPopupJob]);

  const formatTimer = (secs: number) => {
    const mins = Math.floor(secs / 60);
    const remainderSecs = secs % 60;
    return `${mins}:${remainderSecs < 10 ? "0" : ""}${remainderSecs}`;
  };

  const doAction = async (id: number, action: () => Promise<any>) => {
    if (actionLoading === id) return;

    setActionLoading(id);

    try {
      await action();
      await loadJobs();
    } catch (error) {
      console.error("Assigned job action failed:", error);
      alert(
        getBackendActionErrorMessage(
          error,
          "Action failed. Please try again.",
        ),
      );
    } finally {
      setActionLoading((current) => (current === id ? null : current));
    }
  };

  const handleStart = async (jobId: number) => {
    const currentJob = jobs.find((job) => job.id === jobId);

    if (normalizeStatus(currentJob?.status) !== "ACCEPTED") {
      return;
    }

    if (
      startInFlightRef.current.has(jobId) ||
      actionLoading === jobId
    ) {
      return;
    }

    startInFlightRef.current.add(jobId);
    setActionLoading(jobId);

    try {
      await startTechnicianJob(jobId);
      await loadJobs();

      // Open the live map immediately after the authoritative
      // ACCEPTED -> EN_ROUTE transition succeeds.
      const updatedJob =
        jobs.find((job) => job.id === jobId) || currentJob;

      setLiveJob(updatedJob);
    } catch (error) {
      alert(
        getBackendActionErrorMessage(
          error,
          "Unable to start this job. Please try again.",
        ),
      );
    } finally {
      startInFlightRef.current.delete(jobId);
      setActionLoading((current) => (current === jobId ? null : current));
    }
  };

  const handleOpenLiveMap = (job: any) => {
    if (!hasValidCoordinates(job)) {
      alert(
        "Customer location coordinates are not available for this job.",
      );
      return;
    }

    setLiveJob(job);
  };

  const handleOnSite = async (jobId: number) => {
    const currentJob = jobs.find((job) => job.id === jobId);

    if (normalizeStatus(currentJob?.status) !== "EN_ROUTE") {
      return;
    }

    if (
      onSiteInFlightRef.current.has(jobId) ||
      actionLoading === jobId
    ) {
      return;
    }

    onSiteInFlightRef.current.add(jobId);
    setActionLoading(jobId);

    try {
      await onSiteTechnicianJob(jobId);
      await loadJobs();
    } catch (error) {
      alert(
        getBackendActionErrorMessage(
          error,
          "Unable to mark this job as on site. Please try again.",
        ),
      );
    } finally {
      onSiteInFlightRef.current.delete(jobId);
      setActionLoading((current) => (current === jobId ? null : current));
    }
  };

  const handleOpenCompletion = (jobId: number) => {
    const currentJob = jobs.find((job) => job.id === jobId);
    const currentStatus = normalizeStatus(currentJob?.status);

    if (!["IN_PROGRESS", "PAUSED"].includes(currentStatus)) return;

    setCompleteModal(jobId);
  };

  const handleCompletionSuccess = async () => {
    const completedJobId = completeModal;

    if (!completedJobId) return;

    setCompleteModal(null);

    try {
      await loadJobs();
    } finally {
      setCustomerSignatureModal(completedJobId);

      window.dispatchEvent(
        new CustomEvent("technician-dashboard-refresh"),
      );
    }
  };

  const handlePopupAccept = async () => {
    if (!assignedPopupJob) return;

    const jobId = assignedPopupJob.id;
    setActionLoading(jobId);

    try {
      await acceptTechnicianJob(jobId);
      setAssignedPopupJob(null);
      await loadJobs();
    } catch (error) {
      console.error("Failed to accept assigned job:", error);
      alert(
        getBackendActionErrorMessage(
          error,
          "Failed to accept job. Please try again.",
        ),
      );
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
    if (!rejectModal || rejectReason.trim().length < 10) return;

    const jobId = rejectModal;
    setActionLoading(jobId);

    try {
      await rejectTechnicianJob(jobId, rejectReason.trim());

      setJobs((prev) => prev.filter((job) => job.id !== jobId));
      setRejectModal(null);
      setRejectReason("");
      await loadJobs();
    } catch (error) {
      console.error("Failed to reject assigned job:", error);
      alert(
        getBackendActionErrorMessage(
          error,
          "Reject failed. Please try again.",
        ),
      );
    } finally {
      setActionLoading(null);
    }
  };

  const getActions = (job: any) => {
    const st = normalizeStatus(job?.status);
    const btns: ReactNode[] = [];
    const isLoading = actionLoading === job?.id;

    if (st === "ASSIGNED" || st === "ACTIVE") {
      btns.push(
        <button
          key="accept"
          type="button"
          disabled={isLoading}
          style={{
            ...s.btn("#D1FAE5", "#065F46"),
            opacity: isLoading ? 0.6 : 1,
          }}
          onClick={() =>
            doAction(job.id, () => acceptTechnicianJob(job.id))
          }
        >
          {isLoading ? (
            <>
              <LoaderCircle
                size={14}
                style={{ animation: "spin 1s linear infinite" }}
              />
              Accepting...
            </>
          ) : (
            <>
              <CheckCircle size={14} />
              Accept
            </>
          )}
        </button>,
      );

      btns.push(
        <button
          key="reject"
          type="button"
          disabled={isLoading}
          style={{
            ...s.btn("#FEE2E2", "#991B1B"),
            opacity: isLoading ? 0.6 : 1,
          }}
          onClick={() => setRejectModal(job.id)}
        >
          <XCircle size={14} />
          Reject
        </button>,
      );
    }

    if (st === "ACCEPTED") {
      const isStarting =
        actionLoading === job.id &&
        startInFlightRef.current.has(job.id);

      btns.push(
        <button
          key="start"
          type="button"
          aria-label={`Start job ${job.id}`}
          disabled={isStarting}
          style={{
            ...s.btn("#DBEAFE", "#1E40AF"),
            opacity: isStarting ? 0.6 : 1,
            cursor: isStarting ? "not-allowed" : "pointer",
          }}
          onClick={() => handleStart(job.id)}
        >
          {isStarting ? (
            <>
              <LoaderCircle
                size={14}
                style={{ animation: "spin 1s linear infinite" }}
              />
              Starting...
            </>
          ) : (
            <>
              <Play size={14} />
              Start
            </>
          )}
        </button>,
      );
    }

    // The Live Map button is available once tracking can exist.
    if (
      ["EN_ROUTE", "ON_SITE", "IN_PROGRESS", "PAUSED"].includes(st)
    ) {
      btns.push(
        <button
          key="live-map"
          type="button"
          aria-label={`Open live map for job ${job.id}`}
          disabled={!hasValidCoordinates(job)}
          style={{
            ...s.btn("#ECFDF5", "#047857"),
            opacity: hasValidCoordinates(job) ? 1 : 0.5,
            cursor: hasValidCoordinates(job) ? "pointer" : "not-allowed",
          }}
          onClick={() => handleOpenLiveMap(job)}
          title={
            hasValidCoordinates(job)
              ? "Open live tracking map"
              : "Customer coordinates are unavailable"
          }
        >
          <Navigation size={14} />
          Live Map
        </button>,
      );
    }

    if (st === "EN_ROUTE") {
      const isOnSiteLoading =
        actionLoading === job.id &&
        onSiteInFlightRef.current.has(job.id);

      btns.push(
        <button
          key="on-site"
          type="button"
          disabled={isOnSiteLoading}
          style={{
            ...s.btn("#E0F2FE", "#0369A1"),
            opacity: isOnSiteLoading ? 0.6 : 1,
            cursor: isOnSiteLoading ? "not-allowed" : "pointer",
          }}
          onClick={() => handleOnSite(job.id)}
        >
          {isOnSiteLoading ? (
            <>
              <LoaderCircle
                size={14}
                style={{ animation: "spin 1s linear infinite" }}
              />
              Updating...
            </>
          ) : (
            <>
              <MapPin size={14} />
              On Site
            </>
          )}
        </button>,
      );
    }

    if (["IN_PROGRESS", "PAUSED"].includes(st)) {
      btns.push(
        <button
          key="complete"
          type="button"
          disabled={isLoading}
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
            cursor: isLoading ? "not-allowed" : "pointer",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "6px",
            textTransform: "uppercase" as const,
            letterSpacing: "0.5px",
            opacity: isLoading ? 0.6 : 1,
          }}
          onClick={() => handleOpenCompletion(job.id)}
        >
          {isLoading ? "Completing..." : "Complete"}
        </button>,
      );
    }

    return btns;
  };

  if (loading) {
    return (
      <div style={s.page}>
        <div style={s.empty}>Loading assigned jobs...</div>
      </div>
    );
  }

  return (
    <div style={s.page}>
      <style>
        {`
          @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
          }
        `}
      </style>

      <div style={s.header}>
        <div>
          <h2 style={s.title}>Assigned Jobs</h2>
          <div
            style={{
              fontSize: "12px",
              color: "#6B7280",
              marginTop: "4px",
            }}
          >
            Jobs assigned to the authenticated technician
          </div>
        </div>

        <span style={{ fontSize: "13px", color: "#6B7280" }}>
          {jobs.length} job(s)
        </span>
      </div>

      {lastJobsSync && (
        <div
          style={{
            marginBottom: "14px",
            fontSize: "11px",
            color: "#6B7280",
            textAlign: "right",
          }}
        >
          Last synced {lastJobsSync.toLocaleTimeString()}
        </div>
      )}

      {jobsError && (
        <div
          role="alert"
          style={{
            marginBottom: "14px",
            padding: "12px 14px",
            borderRadius: "10px",
            background: "#FEF2F2",
            border: "1px solid #FECACA",
            color: "#991B1B",
            fontSize: "13px",
            lineHeight: 1.5,
          }}
        >
          {jobsError}
        </div>
      )}

      {jobs.length === 0 ? (
        <div style={s.empty} role="status">
          {jobsError
            ? "Assigned jobs are currently unavailable."
            : "No active jobs assigned to you"}
        </div>
      ) : (
        jobs.map((job) => {
          const normalizedStatus = normalizeStatus(job?.status);
          const statusMeta =
            statusStyle[normalizedStatus] || {
              bg: "#E5E7EB",
              fg: "#374151",
            };

          const priority =
            priorityStyle[normalizeStatus(job?.priority)] || {
              bg: "#E5E7EB",
              fg: "#374151",
            };

          return (
            <div key={job.id} style={s.card}>
              <div style={s.cardHeader}>
                <div>
                  <span style={s.jobId}>JOB #{job.id}</span>
                  <div style={s.jobTitle}>
                    {job.service_type || "Service Request"}
                  </div>
                </div>

                <span style={s.badge(priority.bg, priority.fg)}>
                  {job.priority || "MEDIUM"}
                </span>
              </div>

              <div style={s.meta}>
                <span style={s.metaItem}>
                  <MapPin size={14} />
                  {job.location || "N/A"}
                </span>

                <span style={s.metaItem}>
                  <Phone size={14} />
                  {job.contact_number || "N/A"}
                </span>

                <span style={s.metaItem}>
                  <Clock size={14} />
                  {formatSchedule(job)}
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
                <span style={s.badge(statusMeta.bg, statusMeta.fg)}>
                  {getStatusLabel(job.status)}
                </span>

                <div
                  style={{
                    display: "flex",
                    gap: "8px",
                    flexWrap: "wrap",
                  }}
                >
                  {getActions(job)}
                </div>
              </div>
            </div>
          );
        })
      )}

      {assignedPopupJob && (
        <div style={s.modal}>
          <div
            style={s.overlay}
            onClick={() => setAssignedPopupJob(null)}
          />

          <div style={s.modalCard}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "4px",
              }}
            >
              <span
                style={{
                  fontSize: "13px",
                  fontWeight: 700,
                  color: "#6B7280",
                }}
              >
                Job ID: #{assignedPopupJob.id}
              </span>

              <button
                type="button"
                aria-label="Close assigned job popup"
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

            <h3 style={s.modalTitle}>Job Assigned</h3>

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
              <div style={{ display: "flex", alignItems: "baseline", gap: "8px" }}>
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
                  }}
                >
                  REMAINING
                </span>
              </div>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "16px",
                marginBottom: "18px",
              }}
            >
              <div>
                <div style={s.label}>CUSTOMER</div>
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
                  {assignedPopupJob.customer_name || "N/A"}
                </div>
              </div>

              <div>
                <div style={s.label}>CONTACT</div>
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
                  {assignedPopupJob.contact_number || "N/A"}
                </div>
              </div>

              <div>
                <div style={s.label}>SCHEDULE</div>
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
                  <Clock size={15} color="#4B5563" />
                  {formatSchedule(assignedPopupJob)}
                </div>
              </div>

              <div>
                <div style={s.label}>LOCATION</div>
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
                  <MapPin size={15} color="#4B5563" />
                  {assignedPopupJob.location || "N/A"}
                </div>
              </div>
            </div>

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
                {assignedPopupJob.service_type || "Service Request"}
              </div>

              {assignedPopupJob.issue_description && (
                <div
                  style={{
                    fontSize: "13px",
                    color: "#4B5563",
                    lineHeight: 1.5,
                  }}
                >
                  {assignedPopupJob.issue_description}
                </div>
              )}
            </div>

            <div style={{ display: "flex", gap: "12px", marginTop: "12px" }}>
              <button
                type="button"
                onClick={handlePopupAccept}
                disabled={actionLoading === assignedPopupJob.id}
                style={{
                  flex: 1,
                  height: "46px",
                  background: "#059669",
                  color: "#fff",
                  border: "none",
                  borderRadius: "12px",
                  fontSize: "15px",
                  fontWeight: 700,
                  cursor:
                    actionLoading === assignedPopupJob.id
                      ? "not-allowed"
                      : "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "8px",
                  opacity: actionLoading === assignedPopupJob.id ? 0.6 : 1,
                }}
              >
                <Check size={18} />
                {actionLoading === assignedPopupJob.id
                  ? "Accepting..."
                  : "Accept Job"}
              </button>

              <button
                type="button"
                onClick={handlePopupRejectClick}
                disabled={actionLoading === assignedPopupJob.id}
                style={{
                  flex: 1,
                  height: "46px",
                  background: "#EF4444",
                  color: "#fff",
                  border: "none",
                  borderRadius: "12px",
                  fontSize: "15px",
                  fontWeight: 700,
                  cursor:
                    actionLoading === assignedPopupJob.id
                      ? "not-allowed"
                      : "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "8px",
                  opacity: actionLoading === assignedPopupJob.id ? 0.6 : 1,
                }}
              >
                <X size={18} />
                Reject
              </button>
            </div>
          </div>
        </div>
      )}

      {rejectModal && (
        <div style={s.modal}>
          <div
            style={s.overlay}
            onClick={() => setRejectModal(null)}
          />

          <div style={s.modalCard}>
            <button
              type="button"
              aria-label="Close rejection dialog"
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
              style={s.textarea}
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
                type="button"
                style={s.btn("#E5E7EB", "#374151")}
                onClick={() => setRejectModal(null)}
              >
                Cancel
              </button>

              <button
                type="button"
                style={{
                  ...s.btn("#FEE2E2", "#991B1B"),
                  opacity: rejectReason.trim().length < 10 ? 0.5 : 1,
                }}
                onClick={handleReject}
                disabled={
                  rejectReason.trim().length < 10 ||
                  actionLoading === rejectModal
                }
              >
                {actionLoading === rejectModal
                  ? "Rejecting..."
                  : "Confirm Reject"}
              </button>
            </div>
          </div>
        </div>
      )}

      {completeModal && (
        <JobClosureModal
          jobId={completeModal}
          isOpen={!!completeModal}
          onClose={() => setCompleteModal(null)}
          onSuccess={handleCompletionSuccess}
        />
      )}

      {customerSignatureModal && (
        <CustomerSignatureModal
          jobId={customerSignatureModal}
          onClose={() => setCustomerSignatureModal(null)}
          onSuccess={() => {
            setCustomerSignatureModal(null);
            void loadJobs();

            window.dispatchEvent(
              new CustomEvent("technician-dashboard-refresh"),
            );
          }}
        />
      )}

      {liveJob && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 10000,
            background: "rgba(15,23,42,0.65)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 20,
          }}
        >
          <div
            style={{
              width: "min(1000px, 96vw)",
              background: "#fff",
              borderRadius: 16,
              overflow: "hidden",
            }}
          >
            <div
              style={{
                padding: "14px 18px",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <strong>
                Live Route to Customer — Job #{liveJob.id}
              </strong>

              <button
                type="button"
                aria-label="Close live map"
                onClick={() => setLiveJob(null)}
                style={{
                  border: 0,
                  background: "transparent",
                  cursor: "pointer",
                  fontSize: 22,
                }}
              >
                ×
              </button>
            </div>

            <div style={{ height: "min(72vh, 620px)" }}>
              {hasValidCoordinates(liveJob) ? (
                <JobLiveTrackingMap
                  jobId={liveJob.id}
                  customerLatitude={Number(liveJob.site_latitude)}
                  customerLongitude={Number(liveJob.site_longitude)}
                  technicianId={liveJob.assigned_technician_id}
                  mode="technician"
                  tenantId={localStorage.getItem("tenant_id") || ""}
                  buildingAddress={liveJob.location}
                />
              ) : (
                <div
                  style={{
                    height: "100%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: "#6B7280",
                    padding: 24,
                    textAlign: "center",
                  }}
                >
                  Customer location coordinates are unavailable.
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
