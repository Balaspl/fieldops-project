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

  IndianRupee,

  User,

  LoaderCircle,

  Navigation,

  MessageSquare,

  Briefcase as BriefcaseIcon,

  CalendarDays,

  FileText,

  ChevronRight,

  Wrench,

} from "lucide-react";

import {

  getTechnicianJobs,

  acceptTechnicianJob,

  rejectTechnicianJob,

  startTechnicianJob,

  onSiteTechnicianJob,

  completeTechnicianJob,

} from "../../services/technicianPortalService";

import { JobClosureModal } from "../../components/jobs/JobClosureModal";

import CustomerSignatureModal from "../../components/jobs/CustomerSignatureModal";

import JobLiveTrackingMap from "../../components/customer-tracking/JobLiveTrackingMap";

import JobMessagePanel from "../../components/customer-tracking/JobMessagePanel";

import type { JobClosureData } from "../../services/planningService";

import useAuthStore from "../../store/authStore";
import {
  formatAcceptanceCountdown,
  useAcceptanceCountdowns,
} from "../../hooks/useAcceptanceCountdown";
import TechnicianJobAssignmentPopup from "../../components/technician/TechnicianJobAssignmentPopup";
import {
  TECHNICIAN_GPS_MAX_AGE_MS,
  isValidTechnicianGpsFix,
  useTechnicianGpsStore,
} from "../../store/technicianGpsStore";
import {
  haversineDistanceKm,
  parseCoordinates,
} from "../../utils/geo";

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

const STARTED_JOB_STATUSES = ["EN_ROUTE", "ON_SITE", "IN_PROGRESS", "PAUSED"];

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

  const [pendingClosureData, setPendingClosureData] =

    useState<JobClosureData | null>(null);

  const [completeNotes, setCompleteNotes] = useState("");

  const [actionLoading, setActionLoading] = useState<number | null>(null);

  const startInFlightRef = useRef<Set<number>>(new Set());

  const onSiteInFlightRef = useRef<Set<number>>(new Set());

  const [liveJob, setLiveJob] = useState<any | null>(null);

  const [assignedPopupJob, setAssignedPopupJob] = useState<any | null>(null);

  const authUser = useAuthStore((state) => state.user);
  const technicianGpsLocation = useTechnicianGpsStore(
    (state) => state.location,
  );
  const [gpsFreshnessNow, setGpsFreshnessNow] = useState(Date.now());

  const [messageJobId, setMessageJobId] = useState<number | null>(null);

  const assignedPopupJobIdRef = useRef<number | null>(null);

  const rejectedPopupJobIdsRef = useRef<Set<number>>(new Set());

  const countdownJobs =
    assignedPopupJob &&
    !jobs.some((job) => Number(job.id) === Number(assignedPopupJob.id))
      ? [...jobs, assignedPopupJob]
      : jobs;
  const acceptanceCountdowns = useAcceptanceCountdowns(countdownJobs);
  const timerSeconds = assignedPopupJob
    ? acceptanceCountdowns[String(assignedPopupJob.id)] ?? null
    : null;
  const legacyTimerSeconds = timerSeconds ?? 0;

  const checkForAssignedJob = async () => {
    // Never show the assignment popup while the rejection dialog is open.
    if (rejectModal !== null) return;

    try {
      const response = await getTechnicianJobs();
      const list = Array.isArray(response?.data) ? response.data : [];

      const assignedJob = list.find((job: any) => {
        const status = normalizeStatus(job?.status);
        const jobId = Number(job?.id);

        return (
          status === "ASSIGNED" &&
          !rejectedPopupJobIdsRef.current.has(jobId)
        );
      });

      if (!assignedJob) return;

      const jobId = Number(assignedJob.id);
      if (assignedPopupJobIdRef.current === jobId) return;

      assignedPopupJobIdRef.current = jobId;
      setAssignedPopupJob(assignedJob);
    } catch (error) {
      console.error("Failed to check assigned job:", error);
    }
  };

  const loadJobs = async () => {
    setLoading(true);

    try {
      const response = await getTechnicianJobs();
      const list = Array.isArray(response?.data) ? response.data : [];

      setJobs(list);
      setJobsError(null);
      setLastJobsSync(new Date());

      // A rejection dialog must be the only visible dialog.
      if (rejectModal !== null) {
        setAssignedPopupJob(null);
        assignedPopupJobIdRef.current = null;
        return;
      }

      const pendingAssigned = list.find((job: any) => {
        const status = normalizeStatus(job?.status);
        const jobId = Number(job?.id);

        return (
          (status === "ASSIGNED" || status === "ACTIVE") &&
          !rejectedPopupJobIdsRef.current.has(jobId)
        );
      });

      if (pendingAssigned) {
        const jobId = Number(pendingAssigned.id);
        assignedPopupJobIdRef.current = jobId;
        setAssignedPopupJob(pendingAssigned);
      } else {
        assignedPopupJobIdRef.current = null;
        setAssignedPopupJob(null);
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

  const interval = window.setInterval(() => {

    void checkForAssignedJob();

  }, 3000);

  return () => {

    window.clearInterval(interval);

  };

}, []);

useEffect(() => {
  setGpsFreshnessNow(Date.now());

  if (!assignedPopupJob || !technicianGpsLocation) return;

  const expiresAt =
    technicianGpsLocation.fix.timestamp + TECHNICIAN_GPS_MAX_AGE_MS;
  const staleInMs = expiresAt - Date.now() + 1;
  if (staleInMs <= 0) return;

  const timer = window.setTimeout(
    () => setGpsFreshnessNow(Date.now()),
    staleInMs,
  );
  return () => window.clearTimeout(timer);
}, [assignedPopupJob, technicianGpsLocation]);

const customerCoordinates = assignedPopupJob
  ? parseCoordinates(
      assignedPopupJob.site_latitude,
      assignedPopupJob.site_longitude,
    )
  : null;
const isValidCustomerLocation =
  customerCoordinates !== null &&
  !(customerCoordinates.latitude === 0 && customerCoordinates.longitude === 0);
const technicianLocationMatchesUser =
  technicianGpsLocation?.technicianId === String(authUser?.id ?? "") &&
  technicianGpsLocation?.tenantId === String(authUser?.tenant_id ?? "");
const technicianFix = technicianLocationMatchesUser
  ? technicianGpsLocation?.fix
  : null;
const hasFreshTechnicianLocation =
  technicianFix !== undefined &&
  technicianFix !== null &&
  isValidTechnicianGpsFix(technicianFix, gpsFreshnessNow);
const assignedJobDistanceKm =
  isValidCustomerLocation && hasFreshTechnicianLocation && technicianFix
    ? haversineDistanceKm(technicianFix, customerCoordinates)
    : null;
const assignmentDistanceDisplay = !isValidCustomerLocation
  ? "Customer location unavailable"
  : !hasFreshTechnicianLocation || assignedJobDistanceKm === null
    ? "Waiting for GPS location"
    : `${assignedJobDistanceKm.toFixed(1)} km`;

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

    const anotherJobIsStarted = jobs.some(
      (job) =>
        Number(job.id) !== Number(jobId) &&
        STARTED_JOB_STATUSES.includes(normalizeStatus(job.status)),
    );

    if (anotherJobIsStarted) return;

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

        error instanceof Error

          ? "Unable to mark this job as on site. Please try again."

          : getBackendActionErrorMessage(

              error,

              "Unable to mark this job as on site. Please try again.",

            ),

      );

      await loadJobs();

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

  const handlePaymentSubmitted = (data: JobClosureData) => {
    if (completeModal === null) return;
    setPendingClosureData(data);
    setCustomerSignatureModal(completeModal);
  };

  const handleSignatureAndComplete = async (signatureData: string) => {
    if (customerSignatureModal === null || !pendingClosureData) {
      throw new Error("Payment details are missing. Return to the payment step and try again.");
    }

    await completeTechnicianJob(customerSignatureModal, {
      completion_notes: pendingClosureData.work_summary,
      photos: pendingClosureData.after_images,
      before_images: pendingClosureData.before_images,
      labour_cost: pendingClosureData.labour_cost,
      material_cost: pendingClosureData.material_cost,
      payment_method: pendingClosureData.payment_method,
      payment_provider: pendingClosureData.payment_provider,
      payment_demo: pendingClosureData.payment_demo,
      cash_amount: pendingClosureData.cash_amount,
      upi_amount: pendingClosureData.upi_amount,
      gst_amount: pendingClosureData.gst_amount,
      total_amount: pendingClosureData.total_amount,
      signature_data: signatureData,
    });

    setCustomerSignatureModal(null);
    setCompleteModal(null);
    setPendingClosureData(null);
    await loadJobs();
    window.dispatchEvent(new CustomEvent("technician-dashboard-refresh"));
  };

  const handlePopupAccept = async () => {

  if (!assignedPopupJob || actionLoading === assignedPopupJob.id) return;

  if (timerSeconds !== null && timerSeconds <= 0) {

    alert("Acceptance window has expired.");

    return;

  }

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

    const jobId = Number(assignedPopupJob.id);

    // Suppress this offer for the rest of this page session so polling
    // cannot reopen the assignment popup while the rejection dialog is open.
    rejectedPopupJobIdsRef.current.add(jobId);
    assignedPopupJobIdRef.current = null;
    setAssignedPopupJob(null);
    setRejectReason("");
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

    const anotherJobIsStarted = jobs.some(
      (candidate) =>
        Number(candidate.id) !== Number(job?.id) &&
        STARTED_JOB_STATUSES.includes(normalizeStatus(candidate.status)),
    );

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

          disabled={isStarting || anotherJobIsStarted}

          style={{

            ...s.btn("#DBEAFE", "#1E40AF"),

            opacity: isStarting || anotherJobIsStarted ? 0.55 : 1,

            cursor: isStarting || anotherJobIsStarted ? "not-allowed" : "pointer",

          }}

          onClick={() => handleStart(job.id)}

          title={anotherJobIsStarted ? "Finish the job already in progress before starting another." : undefined}

        >

          {isStarting ? (

            <>

              <LoaderCircle

                size={14}

                style={{ animation: "spin 1s linear infinite" }}

              />

              Starting...

            </>

          ) : anotherJobIsStarted ? (

            "Finish Current Job"

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

          aria-label="On Site"

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

          {isLoading ? "Submitting..." : "Service Complete"}

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

          .technician-assigned-card {
            background: linear-gradient(115deg, #ffffff 0%, #fbfefd 100%);
            border: 1px solid #e3ece7;
            border-left: 4px solid #0aa66a;
            border-radius: 15px;
            padding: 20px 22px 14px;
            margin-bottom: 16px;
            box-shadow: 0 5px 18px rgba(21, 68, 52, 0.08);
            transition: box-shadow 180ms ease, transform 180ms ease;
          }
          .technician-assigned-card:hover {
            box-shadow: 0 10px 24px rgba(21, 68, 52, 0.12);
            transform: translateY(-2px);
          }
          .technician-assigned-details {
            display: grid;
            grid-template-columns: minmax(230px, 2fr) repeat(3, minmax(130px, 1fr)) auto;
            align-items: center;
          }
          .technician-assigned-details:not(.has-route) {
            grid-template-columns: minmax(230px, 2fr) repeat(2, minmax(130px, 1fr));
          }
          .technician-assigned-detail {
            min-width: 0;
            padding: 4px 18px;
            border-right: 1px solid #e7edf2;
          }
          .technician-assigned-detail:first-child { padding-left: 4px; }
          .technician-assigned-detail:last-child { border-right: 0; }
          .technician-assigned-footer {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
            border-top: 1px solid #e9eef2;
            padding-top: 12px;
            margin-top: 12px;
          }
          @media (max-width: 1050px) {
            .technician-assigned-details { grid-template-columns: repeat(2, minmax(0, 1fr)); row-gap: 12px; }
            .technician-assigned-detail { padding: 4px 10px; }
            .technician-assigned-detail:nth-child(2n) { border-right: 0; }
          }
          @media (max-width: 600px) {
            .technician-assigned-card { padding: 16px 14px 12px; }
            .technician-assigned-details { grid-template-columns: minmax(0, 1fr); }
            .technician-assigned-detail { border-right: 0; border-bottom: 1px solid #e7edf2; padding: 8px 2px; }
            .technician-assigned-detail:last-child { border-bottom: 0; }
            .technician-assigned-footer { align-items: flex-start; }
          }
          .technician-job-assignment-modal {
            position: fixed;
            inset: 0;
            z-index: 9999;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
            box-sizing: border-box;
            overflow-y: auto;
          }
          .technician-job-assignment-backdrop {
            position: fixed;
            inset: 0;
            background: rgba(15, 23, 42, 0.58);
            backdrop-filter: blur(5px);
          }
          .technician-job-assignment-card {
            position: relative;
            z-index: 1;
            width: min(100%, 680px);
            max-width: 680px;
            max-height: calc(100dvh - 40px);
            overflow-y: auto;
            padding: 30px;
            border-radius: 24px;
            box-sizing: border-box;
            background: #fff;
            box-shadow: 0 24px 70px rgba(15, 23, 42, 0.24);
          }
          .technician-job-assignment-header {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 16px;
            margin-bottom: 20px;
          }
          .technician-job-assignment-id {
            display: block;
            margin-bottom: 6px;
            color: #64748b;
            font-size: 13px;
            font-weight: 700;
          }
          .technician-job-assignment-title {
            margin: 0;
            color: #172033;
            font-size: 26px;
            font-weight: 800;
            line-height: 1.2;
          }
          .technician-job-assignment-subtitle {
            margin: 6px 0 0;
            color: #64748b;
            font-size: 13px;
            line-height: 1.5;
          }
          .technician-job-assignment-close {
            display: grid;
            flex: 0 0 auto;
            width: 38px;
            height: 38px;
            place-items: center;
            border: 0;
            border-radius: 50%;
            background: #f1f5f4;
            color: #64748b;
            cursor: pointer;
            transition: background 160ms ease, color 160ms ease;
          }
          .technician-job-assignment-close:hover {
            background: #e2eee9;
            color: #176b58;
          }
          .technician-job-assignment-summary {
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
            margin-bottom: 18px;
            overflow: hidden;
            border: 1px solid #a7f3d0;
            border-radius: 16px;
            background: #ecfdf5;
          }
          .technician-job-assignment-summary-cell {
            display: flex;
            min-width: 0;
            align-items: center;
            gap: 12px;
            padding: 16px;
          }
          .technician-job-assignment-summary-cell + .technician-job-assignment-summary-cell {
            border-left: 1px solid #bbebd2;
          }
          .technician-job-assignment-icon {
            display: grid;
            flex: 0 0 auto;
            width: 40px;
            height: 40px;
            place-items: center;
            border-radius: 50%;
            background: #d1fae5;
            color: #087857;
          }
          .technician-job-assignment-summary-content {
            min-width: 0;
          }
          .technician-job-assignment-eyebrow {
            display: block;
            margin-bottom: 5px;
            color: #477362;
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 0.08em;
          }
          .technician-job-assignment-summary-value {
            color: #075c43;
            font-size: 23px;
            font-weight: 800;
            line-height: 1.15;
            overflow-wrap: anywhere;
          }
          .technician-job-assignment-summary-note {
            display: block;
            margin-top: 3px;
            color: #28735a;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.05em;
          }
          .technician-job-assignment-columns {
            display: grid;
            grid-template-columns: minmax(0, 0.9fr) minmax(0, 1.1fr);
            gap: 12px;
            margin-bottom: 14px;
          }
          .technician-job-assignment-customer-stack {
            display: grid;
            gap: 10px;
          }
          .technician-job-assignment-info-card {
            display: flex;
            min-width: 0;
            align-items: flex-start;
            gap: 11px;
            padding: 13px;
            border: 1px solid #e8eeeb;
            border-radius: 14px;
            background: #fff;
          }
          .technician-job-assignment-info-icon {
            display: grid;
            flex: 0 0 auto;
            width: 34px;
            height: 34px;
            place-items: center;
            border-radius: 50%;
            background: #f1f5f4;
            color: #64748b;
          }
          .technician-job-assignment-info-icon.is-blue {
            background: #eff6ff;
            color: #2563eb;
          }
          .technician-job-assignment-info-icon.is-green {
            background: #ecfdf5;
            color: #087857;
          }
          .technician-job-assignment-info-content {
            min-width: 0;
            flex: 1;
          }
          .technician-job-assignment-info-value {
            color: #273449;
            font-size: 13px;
            font-weight: 700;
            line-height: 1.45;
            overflow-wrap: anywhere;
            white-space: pre-wrap;
          }
          .technician-job-assignment-location-card {
            min-height: 100%;
            box-sizing: border-box;
            background: #fbfdfc;
          }
          .technician-job-assignment-distance {
            display: flex;
            min-width: 0;
            align-items: center;
            justify-content: space-between;
            gap: 14px;
            margin-bottom: 14px;
            padding: 14px 16px;
            border: 1px solid #ccebdc;
            border-radius: 14px;
            background: #f0fdf6;
            color: #176b58;
          }
          .technician-job-assignment-distance-label {
            display: flex;
            min-width: 0;
            align-items: center;
            gap: 10px;
            font-size: 13px;
            font-weight: 700;
          }
          .technician-job-assignment-distance-value {
            flex: 0 0 auto;
            color: #075c43;
            font-size: 21px;
            font-weight: 800;
            text-align: right;
            overflow-wrap: anywhere;
          }
          .technician-job-assignment-service {
            margin-bottom: 18px;
            padding: 15px 16px;
            border: 1px solid #e8edf0;
            border-radius: 14px;
            background: #f8fafb;
          }
          .technician-job-assignment-service-heading {
            display: flex;
            align-items: center;
            gap: 11px;
            margin-bottom: 8px;
          }
          .technician-job-assignment-service-name {
            color: #1f2937;
            font-size: 15px;
            font-weight: 800;
            line-height: 1.4;
            overflow-wrap: anywhere;
          }
          .technician-job-assignment-service-description {
            margin: 0;
            color: #596579;
            font-size: 13px;
            line-height: 1.55;
            overflow-wrap: anywhere;
            white-space: pre-wrap;
          }
          .technician-job-assignment-actions {
            display: flex;
            gap: 12px;
          }
          .technician-job-assignment-action {
            display: flex;
            flex: 1;
            min-width: 0;
            min-height: 48px;
            align-items: center;
            justify-content: center;
            gap: 8px;
            border: 0;
            border-radius: 12px;
            color: #fff;
            font-size: 15px;
            font-weight: 800;
            cursor: pointer;
            transition: transform 140ms ease, filter 140ms ease, box-shadow 140ms ease;
          }
          .technician-job-assignment-action:hover:not(:disabled) {
            filter: brightness(1.04);
            transform: translateY(-1px);
            box-shadow: 0 5px 12px rgba(15, 23, 42, 0.12);
          }
          .technician-job-assignment-action:active:not(:disabled) {
            transform: translateY(0);
          }
          .technician-job-assignment-action:disabled {
            cursor: not-allowed;
            opacity: 0.58;
          }
          .technician-job-assignment-action.is-accept { background: #079669; }
          .technician-job-assignment-action.is-reject { background: #ef4444; }
          @media (max-width: 600px) {
            .technician-job-assignment-modal { align-items: flex-start; padding: 12px; }
            .technician-job-assignment-card {
              width: 100%;
              max-height: calc(100dvh - 24px);
              padding: 20px;
              border-radius: 20px;
            }
            .technician-job-assignment-title { font-size: 23px; }
            .technician-job-assignment-columns { grid-template-columns: minmax(0, 1fr); }
            .technician-job-assignment-location-card { min-height: auto; }
            .technician-job-assignment-summary-cell { padding: 13px 10px; gap: 8px; }
            .technician-job-assignment-icon { width: 34px; height: 34px; }
            .technician-job-assignment-summary-value { font-size: 20px; }
          }
          @media (max-width: 420px) {
            .technician-job-assignment-modal { padding: 8px; }
            .technician-job-assignment-card { max-height: calc(100dvh - 16px); padding: 16px; }
            .technician-job-assignment-summary { grid-template-columns: minmax(0, 1fr); }
            .technician-job-assignment-summary-cell + .technician-job-assignment-summary-cell {
              border-top: 1px solid #bbebd2;
              border-left: 0;
            }
            .technician-job-assignment-distance { align-items: flex-start; flex-direction: column; gap: 7px; }
            .technician-job-assignment-distance-value { text-align: left; }
            .technician-job-assignment-actions { flex-direction: column; }
          }

        `}

      </style>

      <div style={s.header}>

        <div>

          <h2 style={{ ...s.title, display: "flex", alignItems: "center", gap: 14, margin: 0, fontSize: 28 }}>
            <span style={{ width: 54, height: 54, borderRadius: 14, display: "grid", placeItems: "center", color: "#078A65", background: "linear-gradient(145deg, #E7FFF5, #D2F8E9)", border: "1px solid #BCEED8", boxShadow: "0 5px 14px rgba(10, 166, 106, .1)" }}><BriefcaseIcon size={27} /></span>
            Assigned Jobs
          </h2>

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

          const canViewRoute = STARTED_JOB_STATUSES.includes(normalizedStatus);
          const acceptanceSeconds = acceptanceCountdowns[String(job.id)];

          return (

            <article key={job.id} className="technician-assigned-card">

              <div style={s.cardHeader}>

                <div>

                  <span style={s.jobId}>JOB #{job.id}</span>

                  <div style={s.jobTitle}>

                    {job.service_type || "Service Request"}

                  </div>

                </div>

                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", justifyContent: "flex-end" }}>
                  <span style={{ ...s.badge(priority.bg, priority.fg), padding: "6px 13px", fontSize: 12 }}>
                    {job.priority || "MEDIUM"}
                  </span>
                  <span style={{ ...s.badge(statusMeta.bg, statusMeta.fg), padding: "6px 13px", fontSize: 12 }}>
                    {getStatusLabel(job.status)}
                  </span>
                </div>

              </div>

              <div className={`technician-assigned-details${canViewRoute ? " has-route" : ""}`} style={{ borderTop: "1px solid #E9EEF2", borderBottom: "1px solid #E9EEF2", padding: "14px 0" }}>

                <div className="technician-assigned-detail" style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>

                  <MapPin size={21} color="#26354D" style={{ flex: "0 0 auto", marginTop: 2 }} />

                  <div style={{ minWidth: 0 }}>
                    <strong style={{ display: "block", color: "#172033", fontSize: 14 }}>{job.customer_name || "Customer"}</strong>
                    <span style={{ display: "block", color: "#64748B", fontSize: 13, lineHeight: 1.5, marginTop: 2 }}>{job.location || job.site_address || "Location not provided"}</span>
                  </div>

                </div>

                <div className="technician-assigned-detail" style={{ display: "flex", alignItems: "flex-start", gap: 11 }}>

                  <Phone size={21} color="#26354D" style={{ flex: "0 0 auto", marginTop: 2 }} />

                  <div style={{ minWidth: 0 }}>
                    <strong style={{ display: "block", color: "#172033", fontSize: 14 }}>{job.contact_number || "Phone not provided"}</strong>
                    {job.contact_number && <a href={`tel:${String(job.contact_number).replace(/[^+\d]/g, "")}`} style={{ display: "inline-block", color: "#1769E8", fontSize: 13, marginTop: 3 }}>Call Customer</a>}
                  </div>

                </div>

                <div className="technician-assigned-detail" style={{ display: "flex", alignItems: "flex-start", gap: 11 }}>

                  <CalendarDays size={21} color="#26354D" style={{ flex: "0 0 auto", marginTop: 2 }} />

                  <div><strong style={{ display: "block", color: "#172033", fontSize: 14 }}>{formatSchedule(job)}</strong><span style={{ color: "#718096", fontSize: 12 }}>Scheduled date</span></div>

                </div>

                {canViewRoute && <>
                  <div className="technician-assigned-detail" style={{ display: "flex", alignItems: "flex-start", gap: 11 }}>
                    <Navigation size={21} color="#26354D" style={{ flex: "0 0 auto", marginTop: 2 }} />
                    <div><strong style={{ display: "block", color: "#172033", fontSize: 14 }}>Route</strong><span style={{ color: "#718096", fontSize: 12 }}>{hasValidCoordinates(job) ? "View customer location" : "Location unavailable"}</span></div>
                  </div>
                  <button type="button" aria-label={`View route for job ${job.id}`} disabled={!hasValidCoordinates(job)} onClick={() => handleOpenLiveMap(job)} style={{ border: 0, background: "transparent", color: hasValidCoordinates(job) ? "#334155" : "#CBD5E1", cursor: hasValidCoordinates(job) ? "pointer" : "not-allowed", padding: 8 }}><ChevronRight size={23} /></button>
                </>}

              </div>

              <div style={{ display: "flex", alignItems: "flex-start", gap: 12, padding: "12px 4px 2px" }}>
                <FileText size={21} color="#26354D" style={{ flex: "0 0 auto", marginTop: 1 }} />
                <div style={{ minWidth: 0 }}>
                  <strong style={{ display: "block", color: "#172033", fontSize: 14 }}>Service Details</strong>
                  <span style={{ display: "block", color: "#64748B", fontSize: 13, lineHeight: 1.5, marginTop: 2 }}>{job.issue_description || "No additional service details provided."}</span>
                </div>
              </div>

              <div

                style={{

                  ...s.actions,

                  justifyContent: "space-between",

                  alignItems: "center",

                  borderTop: "1px solid #E9EEF2",

                  paddingTop: 12,

                  marginTop: 12,

                }}

              >

                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <span style={{ width: 28, height: 28, borderRadius: "50%", background: "#D1FAE5", color: "#059669", display: "grid", placeItems: "center" }}><CheckCircle size={17} /></span>
                  <span style={s.badge(statusMeta.bg, statusMeta.fg)}>{getStatusLabel(job.status)}</span>
                  {acceptanceSeconds !== null &&
                    acceptanceSeconds !== undefined && (
                      <span
                        data-testid="assigned-job-acceptance-countdown"
                        data-job-id={job.id}
                        aria-live="off"
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 5,
                          color:
                            acceptanceSeconds <= 30
                              ? "#DC2626"
                              : acceptanceSeconds <= 120
                                ? "#D97706"
                                : "#078A4D",
                          fontSize: 12,
                          fontWeight: 700,
                          whiteSpace: "nowrap",
                        }}
                      >
                        <Clock size={14} />
                        {acceptanceSeconds === 0
                          ? "Acceptance deadline reached"
                          : `Time left to accept: ${formatAcceptanceCountdown(
                              acceptanceSeconds,
                            )}`}
                      </span>
                    )}
                  <span style={{ color: "#718096", fontSize: 12 }}>Assigned {job.assigned_at ? `on ${new Date(job.assigned_at).toLocaleString()}` : "date not recorded"}</span>
                </div>

                <div

                  style={{

                    display: "flex",

                    gap: "8px",

                    flexWrap: "wrap",

                  }}

                >

                  <button
                    type="button"
                    onClick={() => setMessageJobId(Number(job.id))}
                    style={{ height: "38px", padding: "0 11px", border: "1px solid #156B5B", borderRadius: "8px", background: "#FFFFFF", color: "#156B5B", fontSize: "12px", fontWeight: 700, display: "inline-flex", alignItems: "center", gap: "6px", cursor: "pointer" }}
                  >
                    <MessageSquare size={15} /> Message Customer
                  </button>
                  {getActions(job)}

                </div>

              </div>

            </article>

          );

        })

      )}

      {assignedPopupJob && !rejectModal && (
        <TechnicianJobAssignmentPopup
          job={assignedPopupJob}
          countdownSeconds={timerSeconds}
          distanceDisplay={assignmentDistanceDisplay}
          loading={actionLoading === assignedPopupJob.id}
          onClose={() => setAssignedPopupJob(null)}
          onAccept={() => void handlePopupAccept()}
          onReject={handlePopupRejectClick}
        />
      )}
      {false && assignedPopupJob && !rejectModal && (

        <div className="technician-job-assignment-modal">

          <div

            className="technician-job-assignment-backdrop"

            onClick={() => setAssignedPopupJob(null)}

          />

          <div
            className="technician-job-assignment-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="technician-job-assignment-title"
          >
            <header className="technician-job-assignment-header">
              <div>
                <span className="technician-job-assignment-id">
                  Job ID: #{assignedPopupJob.id}
                </span>
                <h3
                  className="technician-job-assignment-title"
                  id="technician-job-assignment-title"
                >
                  Job Assigned
                </h3>
                <p className="technician-job-assignment-subtitle">
                  You have been assigned a new service job.
                </p>
              </div>
              <button
                className="technician-job-assignment-close"
                type="button"
                aria-label="Close assigned job popup"
                onClick={() => setAssignedPopupJob(null)}
              >
                <X size={20} />
              </button>
            </header>

            <section
              className="technician-job-assignment-summary"
              aria-label="Offer time and customer distance"
            >
              <div className="technician-job-assignment-summary-cell">
                <span className="technician-job-assignment-icon">
                  <Clock size={19} />
                </span>
                <div className="technician-job-assignment-summary-content">
                  <span className="technician-job-assignment-eyebrow">
                    TIME REMAINING
                  </span>
                  <div
                    className="technician-job-assignment-summary-value"
                    data-testid="assignment-countdown"
                  >
                    {legacyTimerSeconds <= 0
                      ? "EXPIRED"
                      : formatAcceptanceCountdown(legacyTimerSeconds)}
                  </div>
                  {legacyTimerSeconds > 0 && (
                    <span className="technician-job-assignment-summary-note">
                      REMAINING
                    </span>
                  )}
                </div>
              </div>
              <div className="technician-job-assignment-summary-cell">
                <span className="technician-job-assignment-icon">
                  <Navigation size={19} />
                </span>
                <div className="technician-job-assignment-summary-content">
                  <span className="technician-job-assignment-eyebrow">
                    DISTANCE TO CUSTOMER
                  </span>
                  <div
                    className="technician-job-assignment-summary-value"
                    data-testid="assignment-top-distance"
                    aria-live="polite"
                  >
                    {assignmentDistanceDisplay}
                  </div>
                </div>
              </div>
            </section>

            <section className="technician-job-assignment-columns">
              <div className="technician-job-assignment-customer-stack">
                <article className="technician-job-assignment-info-card">
                  <span className="technician-job-assignment-info-icon">
                    <User size={17} />
                  </span>
                  <div className="technician-job-assignment-info-content">
                    <span className="technician-job-assignment-eyebrow">
                      CUSTOMER
                    </span>
                    <div className="technician-job-assignment-info-value">
                      {assignedPopupJob.customer_name || "N/A"}
                    </div>
                  </div>
                </article>
                <article className="technician-job-assignment-info-card">
                  <span className="technician-job-assignment-info-icon is-blue">
                    <Phone size={16} />
                  </span>
                  <div className="technician-job-assignment-info-content">
                    <span className="technician-job-assignment-eyebrow">
                      CONTACT
                    </span>
                    <div className="technician-job-assignment-info-value">
                      {assignedPopupJob.contact_number || "N/A"}
                    </div>
                  </div>
                </article>
                <article className="technician-job-assignment-info-card">
                  <span className="technician-job-assignment-info-icon">
                    <CalendarDays size={16} />
                  </span>
                  <div className="technician-job-assignment-info-content">
                    <span className="technician-job-assignment-eyebrow">
                      SCHEDULE
                    </span>
                    <div className="technician-job-assignment-info-value">
                      {formatSchedule(assignedPopupJob)}
                    </div>
                  </div>
                </article>
              </div>
              <article className="technician-job-assignment-info-card technician-job-assignment-location-card">
                <span className="technician-job-assignment-info-icon is-green">
                  <MapPin size={17} />
                </span>
                <div className="technician-job-assignment-info-content">
                  <span className="technician-job-assignment-eyebrow">
                    LOCATION
                  </span>
                  <div className="technician-job-assignment-info-value">
                    {assignedPopupJob.site_address ||
                      assignedPopupJob.location ||
                      "N/A"}
                  </div>
                </div>
              </article>
            </section>

            <section
              className="technician-job-assignment-distance"
              aria-live="polite"
            >
              <div className="technician-job-assignment-distance-label">
                <span className="technician-job-assignment-icon">
                  <Navigation size={18} />
                </span>
                <span>Current location to customer</span>
              </div>
              <strong
                className="technician-job-assignment-distance-value"
                data-testid="assignment-distance-summary"
              >
                {assignmentDistanceDisplay}
              </strong>
            </section>

            <section className="technician-job-assignment-service">
              <div className="technician-job-assignment-service-heading">
                <span className="technician-job-assignment-info-icon">
                  <Wrench size={17} />
                </span>
                <div>
                  <span className="technician-job-assignment-eyebrow">
                    SERVICE TYPE
                  </span>
                  <div className="technician-job-assignment-service-name">
                    {assignedPopupJob.service_type || "Service Request"}
                  </div>
                </div>
              </div>
              <p className="technician-job-assignment-service-description">
                {assignedPopupJob.issue_description ||
                  "No additional service details provided."}
              </p>
            </section>

            <div className="technician-job-assignment-actions">

              <button

                type="button"

                onClick={handlePopupAccept}

                disabled={

                  actionLoading === assignedPopupJob.id ||

                  legacyTimerSeconds <= 0

                }

                className="technician-job-assignment-action is-accept"

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

                className="technician-job-assignment-action is-reject"

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

      {/* Job Closure Form Modal */}

      {completeModal && (

        <JobClosureModal

          jobId={completeModal}

          isOpen={!!completeModal}

          paymentFlow

          onClose={() => {
            setCompleteModal(null);
            setCustomerSignatureModal(null);
            setPendingClosureData(null);
          }}

          onSuccess={handlePaymentSubmitted}

        />

      )}

      {customerSignatureModal && (

        <CustomerSignatureModal

          jobId={customerSignatureModal}

          onClose={() => setCustomerSignatureModal(null)}

          captureOnly

          onCapture={handleSignatureAndComplete}

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

      {messageJobId !== null && (
        <JobMessagePanel
          jobId={messageJobId}
          onClose={() => setMessageJobId(null)}
        />
      )}

    </div>

  );

}
