import { useState, useEffect, useRef } from "react";
import {
  Activity,
  BarChart3,
  Briefcase,
  ArrowRight,
  CheckCircle,
  CheckCircle2,
  Clock3,
  MapPin,
  Phone,
  UserRound,
  X,
} from "lucide-react";
import {
  getTechnicianDashboard,
  getTechnicianPerformanceReport,
  getTechnicianJobs,
  acceptTechnicianJob,
  rejectTechnicianJob,
  updateTechnicianStatus,
} from "../../services/technicianPortalService";
import type {
  TechnicianDashboardResponse,
  TechnicianPerformanceReportResponse,
} from "../../services/technicianPortalService";
import TechnicianPerformanceReport from "../../components/technician/TechnicianPerformanceReport";
import { sendTechnicianAvailabilityLocation } from "../../services/gpsService";
import useAuthStore from "../../store/authStore";
import {
  formatAcceptanceCountdown,
  isAwaitingAcceptance,
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
import {
  GeolocationAcquisitionError,
  GPS_AVAILABILITY_MAX_ACCURACY_METERS,
  getTechnicianLocation,
} from "../../services/geolocationService";

const AVAILABILITY_STALE_AFTER_MS = 15000;

const normalizeTechnicianStatus = (
  status?: string | null,
): string | null => {
  const value = (status || "").toLowerCase().trim();

  const map: Record<string, string> = {
    available: "Available",
    busy: "Busy",
    assigned: "Assigned",
    offline: "Offline",
    "en route": "En Route",
    en_route: "En Route",
    "on site": "On Site",
    on_site: "On Site",
    "on break": "On Break",
    on_break: "On Break",
    suspended: "Suspended",
  };

  return map[value] ?? null;
};

// API endpoints may return a direct payload or a common wrapper. Normalize the
// response before storing it so an unexpected object is never treated as a job array.
const extractDashboardPayload = (
  payload: unknown,
): TechnicianDashboardResponse | null => {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return null;
  }

  const record = payload as Record<string, unknown>;
  const nested = record.dashboard ?? record.data;
  if (nested && typeof nested === "object" && !Array.isArray(nested)) {
    return nested as TechnicianDashboardResponse;
  }

  return payload as TechnicianDashboardResponse;
};

const extractJobsPayload = (payload: unknown): any[] | null => {
  if (Array.isArray(payload)) return payload;
  if (!payload || typeof payload !== "object") return null;

  const record = payload as Record<string, unknown>;
  for (const key of ["jobs", "items", "results", "data"]) {
    if (Array.isArray(record[key])) return record[key] as any[];
  }

  return null;
};

const s = {
  page: {
    padding: "24px",
    height: "100%",
    overflowY: "auto" as const,
    background: "#EEF4F1",
    fontFamily: "'Inter', sans-serif",
  },

  header: {
    background: "#fff",
    borderRadius: "14px",
    padding: "24px",
    marginBottom: "24px",
    boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
    border: "1px solid #E3ECE7",
  },

  title: {
    fontSize: "24px",
    fontWeight: 700,
    color: "#1F2933",
    margin: 0,
  },

  subtitle: {
    fontSize: "14px",
    color: "#6B7280",
    marginTop: "4px",
  },

  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
    gap: "10px",
    marginBottom: "24px",
  },

  card: {
    position: "relative" as const,
    zIndex: 1,
    minHeight: "160px",
    borderRadius: "18px",
    padding: "10px",
    border: "1px solid transparent",
    boxShadow: "0 12px 24px rgba(15, 23, 42, 0.08)",
    display: "flex",
    flexDirection: "column" as const,
    overflow: "hidden" as const,
    boxSizing: "border-box" as const,
  },

  cardIcon: {
    width: "32px",
    height: "32px",
    borderRadius: "10px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },

  cardLabel: {
    fontSize: "12px",
    color: "#6B7280",
    fontWeight: 500,
  },

  cardValue: {
    fontSize: "24px",
    fontWeight: 700,
    color: "#1F2933",
  },

  section: {
    background: "#fff",
    borderRadius: "14px",
    padding: "20px",
    boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
    border: "1px solid #E3ECE7",
  },

  sectionTitle: {
    fontSize: "16px",
    fontWeight: 700,
    color: "#1F2933",
    marginBottom: "16px",
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },

  jobRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "12px 0",
    borderBottom: "1px solid #f0f0f0",
  },

  jobInfo: {
    display: "flex",
    flexDirection: "column" as const,
    gap: "2px",
  },

  jobTitle: {
    fontSize: "14px",
    fontWeight: 600,
    color: "#1F2933",
  },

  jobMeta: {
    fontSize: "12px",
    color: "#6B7280",
  },

  badge: (color: string) => ({
    fontSize: "11px",
    fontWeight: 600,
    padding: "3px 10px",
    borderRadius: "20px",
    background: color + "18",
    color,
    display: "inline-block",
  }),

  empty: {
    textAlign: "center" as const,
    color: "#9CA3AF",
    padding: "32px",
    fontSize: "14px",
  },
};

export default function TechnicianPortalDashboard({
  onNavigate,
  onAvailabilityChange,
}: {
  onNavigate: (tab: string) => void;
  onAvailabilityChange?: (status: string) => void;
}) {
  const [stats, setStats] = useState<TechnicianDashboardResponse | null>(null);
  const [reportPeriod, setReportPeriod] = useState<"week" | "month">("week");
  const [performanceReport, setPerformanceReport] =
    useState<TechnicianPerformanceReportResponse | null>(null);
  const [performanceReportError, setPerformanceReportError] =
    useState<string | null>(null);
  const [recentJobs, setRecentJobs] = useState<any[]>([]);
  const [dashboardJobs, setDashboardJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [dashboardRefreshError, setDashboardRefreshError] =
    useState<string | null>(null);
  const [offerActionLoading, setOfferActionLoading] = useState(false);
  const [offerError, setOfferError] = useState<string | null>(null);
  const [rejectingOffer, setRejectingOffer] = useState(false);
  const [rejectReason, setRejectReason] = useState("");

  const [technicianStatus, setTechnicianStatus] =
    useState("Not Available");

  const [savingStatus, setSavingStatus] = useState(false);
  const [profileCompleted, setProfileCompleted] = useState(false);
  const [showProfileMessage, setShowProfileMessage] =
    useState(false);

  const [attendanceError, setAttendanceError] =
    useState<string | null>(null);

  const [lastAttendanceSync, setLastAttendanceSync] =
    useState<Date | null>(null);
  const [gpsError, setGpsError] = useState<string | null>(null);
  const tenantId = useAuthStore((state) => state.user?.tenant_id);
  const authUser = useAuthStore((state) => state.user);
  const technicianGpsLocation = useTechnicianGpsStore(
    (state) => state.location,
  );
  const [gpsFreshnessNow, setGpsFreshnessNow] = useState(Date.now());
  const transitionInFlight = useRef(false);
  const dismissedOfferIds = useRef(new Set<number>());

  useEffect(() => {
    let mounted = true;
    let requestInFlight = false;
    let refreshTimer: number | undefined;

    const loadDashboard = async () => {
      // Use one request cycle at a time. A fixed setInterval can overlap slow
      // API calls and let an older response overwrite newer data.
      if (requestInFlight) return;
      requestInFlight = true;

      try {
        // Dashboard statistics and jobs are independent resources. Update the
        // resource that succeeds instead of discarding both when one endpoint fails.
        const [dashResult, jobsResult] = await Promise.allSettled([
          getTechnicianDashboard(),
          getTechnicianJobs(),
        ]);

        if (!mounted) return;

        let dashboardUpdated = false;
        let jobsUpdated = false;

        if (dashResult.status === "fulfilled") {
          const dashboardData = extractDashboardPayload(dashResult.value.data);

          if (dashboardData) {
            dashboardUpdated = true;
            setStats(dashboardData);

            const isProfileCompleted = Boolean(
              dashboardData.profile_completed,
            );
            setProfileCompleted(isProfileCompleted);

            if (isProfileCompleted) {
              const authoritativeStatus = normalizeTechnicianStatus(
                dashboardData.technician_status,
              );

              if (authoritativeStatus) {
                setTechnicianStatus(authoritativeStatus);
                onAvailabilityChange?.(authoritativeStatus);
                setAttendanceError(null);
                setLastAttendanceSync(new Date());
              } else {
                setTechnicianStatus("Not Available");
                setAttendanceError(
                  "Attendance and availability status is currently unavailable.",
                );
                setLastAttendanceSync(null);
              }
            } else {
              setTechnicianStatus("Not Available");
              onAvailabilityChange?.("Not Available");
              setAttendanceError(null);
              setLastAttendanceSync(null);
            }
          } else {
            console.error(
              "Technician dashboard API returned an unexpected payload:",
              dashResult.value.data,
            );
          }
        } else {
          console.error(
            "Failed to load technician dashboard statistics:",
            dashResult.reason,
          );
          setAttendanceError(
            "Unable to load your attendance and availability status.",
          );
        }

        if (jobsResult.status === "fulfilled") {
          const jobs = extractJobsPayload(jobsResult.value.data);
          if (jobs !== null) {
            jobsUpdated = true;
            setDashboardJobs(jobs);
            setRecentJobs(jobs.slice(0, 5));
          } else {
            console.error(
              "Technician jobs API returned an unexpected payload:",
              jobsResult.value.data,
            );
          }
        } else {
          console.error("Failed to load technician jobs:", jobsResult.reason);
        }

        setDashboardRefreshError(
          dashboardUpdated && jobsUpdated
            ? null
            : "Some dashboard data could not be refreshed. Showing the last available values.",
        );
      } catch (error) {
        console.error("Failed to refresh technician dashboard:", error);
        if (mounted) {
          setDashboardRefreshError(
            "Dashboard data could not be refreshed. Showing the last available values.",
          );
          setAttendanceError(
            "Unable to load your attendance and availability status.",
          );
        }
      } finally {
        requestInFlight = false;
        if (mounted) {
          setLoading(false);
          // Schedule the next refresh after the current one has finished.
          refreshTimer = window.setTimeout(() => {
            void loadDashboard();
          }, 5000);
        }
      }
    };

    void loadDashboard();

    return () => {
      mounted = false;
      if (refreshTimer !== undefined) window.clearTimeout(refreshTimer);
    };
  }, []);

  useEffect(() => {
    let active = true;
    setPerformanceReport(null);
    setPerformanceReportError(null);

    const loadPerformanceReport = async () => {
      try {
        const response = await getTechnicianPerformanceReport(reportPeriod);
        if (active) {
          setPerformanceReport(response.data);
          setPerformanceReportError(null);
        }
      } catch (error) {
        console.error("Failed to load technician performance report:", error);
        if (active) {
          setPerformanceReportError(
            "Unable to load performance metrics. Please try again later.",
          );
        }
      }
    };

    void loadPerformanceReport();
    const timer = setInterval(loadPerformanceReport, 60_000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [reportPeriod]);

  const acceptanceCountdowns = useAcceptanceCountdowns(dashboardJobs);
  const assignedOffer = dashboardJobs.find(
    (job) =>
      isAwaitingAcceptance(job) &&
      !dismissedOfferIds.current.has(Number(job.id)),
  ) ?? null;
  const assignedOfferSeconds = assignedOffer
    ? acceptanceCountdowns[String(assignedOffer.id)] ?? null
    : null;
  const legacyAssignedOfferSeconds = assignedOfferSeconds ?? 0;
  const offerCustomerCoordinates = assignedOffer
    ? parseCoordinates(
        assignedOffer.site_latitude,
        assignedOffer.site_longitude,
      )
    : null;
  const offerTechnicianFix =
    technicianGpsLocation?.technicianId === String(authUser?.id ?? "") &&
    technicianGpsLocation?.tenantId === String(authUser?.tenant_id ?? "")
      ? technicianGpsLocation.fix
      : null;
  const offerHasFreshTechnicianLocation =
    offerTechnicianFix !== null &&
    isValidTechnicianGpsFix(offerTechnicianFix, gpsFreshnessNow);
  const offerDistanceKm =
    offerCustomerCoordinates &&
    offerHasFreshTechnicianLocation &&
    offerTechnicianFix
      ? haversineDistanceKm(offerTechnicianFix, offerCustomerCoordinates)
      : null;
  const offerDistanceDisplay =
    !offerCustomerCoordinates ||
    (offerCustomerCoordinates.latitude === 0 &&
      offerCustomerCoordinates.longitude === 0)
      ? "Customer location unavailable"
      : !offerHasFreshTechnicianLocation || offerDistanceKm === null
        ? "Waiting for GPS location"
        : `${offerDistanceKm.toFixed(1)} km`;

  useEffect(() => {
    setGpsFreshnessNow(Date.now());
    if (!assignedOffer || !technicianGpsLocation) return;

    const expiresAt =
      technicianGpsLocation.fix.timestamp + TECHNICIAN_GPS_MAX_AGE_MS;
    const staleInMs = expiresAt - Date.now() + 1;
    if (staleInMs <= 0) return;

    const timer = window.setTimeout(
      () => setGpsFreshnessNow(Date.now()),
      staleInMs,
    );
    return () => window.clearTimeout(timer);
  }, [assignedOffer, technicianGpsLocation]);

  const dismissAssignedOffer = () => {
    if (assignedOffer) {
      dismissedOfferIds.current.add(Number(assignedOffer.id));
    }
    setOfferError(null);
    setRejectingOffer(false);
  };

  const refreshDashboardJobs = async () => {
    // Refresh both the job list and summary cards after accept/reject actions.
    // A failure in one request must not prevent the other from updating.
    const [dashboardResult, jobsResult] = await Promise.allSettled([
      getTechnicianDashboard(),
      getTechnicianJobs(),
    ]);

    let dashboardUpdated = false;
    let jobsUpdated = false;

    if (dashboardResult.status === "fulfilled") {
      const dashboardData = extractDashboardPayload(dashboardResult.value.data);
      if (dashboardData) {
        setStats(dashboardData);
        dashboardUpdated = true;
      } else {
        console.error(
          "Technician dashboard API returned an unexpected payload:",
          dashboardResult.value.data,
        );
      }
    } else {
      console.error(
        "Failed to refresh technician dashboard statistics:",
        dashboardResult.reason,
      );
    }

    if (jobsResult.status === "fulfilled") {
      const jobs = extractJobsPayload(jobsResult.value.data);
      if (jobs !== null) {
        setDashboardJobs(jobs);
        setRecentJobs(jobs.slice(0, 5));
        jobsUpdated = true;
      } else {
        console.error(
          "Technician jobs API returned an unexpected payload:",
          jobsResult.value.data,
        );
      }
    } else {
      console.error("Failed to refresh technician jobs:", jobsResult.reason);
    }

    setDashboardRefreshError(
      dashboardUpdated && jobsUpdated
        ? null
        : "Some dashboard data could not be refreshed. Showing the last available values.",
    );
  };

  const handleAssignedOfferAccept = async () => {
    if (!assignedOffer || offerActionLoading) return;
    if (assignedOfferSeconds !== null && assignedOfferSeconds <= 0) {
      setOfferError("The acceptance deadline has passed.");
      return;
    }

    setOfferActionLoading(true);
    setOfferError(null);
    try {
      await acceptTechnicianJob(Number(assignedOffer.id));
      dismissAssignedOffer();
      await refreshDashboardJobs();
    } catch (error) {
      console.error("Failed to accept assigned dashboard job:", error);
      setOfferError("Unable to accept this job. Please try again.");
    } finally {
      setOfferActionLoading(false);
    }
  };

  const handleAssignedOfferReject = async () => {
    if (!assignedOffer || offerActionLoading || rejectReason.trim().length < 10) {
      return;
    }

    setOfferActionLoading(true);
    setOfferError(null);
    try {
      await rejectTechnicianJob(
        Number(assignedOffer.id),
        rejectReason.trim(),
      );
      dismissAssignedOffer();
      setRejectReason("");
      await refreshDashboardJobs();
    } catch (error) {
      console.error("Failed to reject assigned dashboard job:", error);
      setOfferError("Unable to reject this job. Please try again.");
    } finally {
      setOfferActionLoading(false);
    }
  };

  const handleAvailabilityChange = async () => {
    if (transitionInFlight.current) return;
    const goingOnline = technicianStatus.toLowerCase() !== "available";
    transitionInFlight.current = true;
    try {
      setSavingStatus(true);
      setAttendanceError(null);
      setGpsError(null);

      if (goingOnline) {
        if (!tenantId) throw new Error("Your account is missing its organization context.");
        try {
          const position = await getTechnicianLocation({
            timeoutMs: 30_000,
            maximumAgeMs: 15_000,
            maxAccuracyMeters: GPS_AVAILABILITY_MAX_ACCURACY_METERS,
          });
          await sendTechnicianAvailabilityLocation(tenantId, {
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            accuracy: position.coords.accuracy,
            timestamp: new Date(position.timestamp).toISOString(),
          });
        } catch (error) {
          if (error instanceof GeolocationAcquisitionError) {
            setGpsError(error.message);
          } else {
            const detail = (error as any)?.response?.data?.detail;
            setGpsError(typeof detail === "string"
              ? `Location was not accepted: ${detail}`
              : "Could not send your location. Check your connection and retry.");
          }
          return;
        }
      }

      const response =
        await updateTechnicianStatus(
          goingOnline ? "Available" : "Offline",
        );

      const authoritativeStatus =
        normalizeTechnicianStatus(
          response.data?.technician_status,
        );

      if (!authoritativeStatus) {
        throw new Error(
          "Backend returned an invalid technician status.",
        );
      }

      // Update only after backend confirmation.
      setTechnicianStatus(
        authoritativeStatus,
      );
      onAvailabilityChange?.(
      authoritativeStatus,);

      setStats((previous: any) =>
        previous
          ? {
              ...previous,
              technician_status:
                authoritativeStatus,
            }
          : previous,
      );

      setLastAttendanceSync(new Date());
    } catch (error) {
      console.error(
        "Failed to update technician attendance status:",
        error,
      );

      setAttendanceError(
        "Unable to update your availability. Please check your connection and try again.",
      );
    } finally {
      setSavingStatus(false);
      transitionInFlight.current = false;
    }
  };

  const cards = [
    {
      label: "Total Jobs",
      value: stats?.total_jobs ?? stats?.total_assigned ?? 0,
      icon: "📄",
      watermark: "📄",
      theme: {
        background: "linear-gradient(145deg, #F0FFF9 0%, #D9FFF1 68%, #B8F7E2 100%)",
        border: "#45E7BC",
        iconBg: "linear-gradient(145deg, #B8F7E2, #8DEFD0)",
        accent: "#00B98A",
        value: "#086B53",
        shadow: "0 12px 24px rgba(0, 185, 138, 0.14)",
      },
    },
    {
      label: "Active Jobs",
      value: stats?.active_jobs ?? 0,
      icon: "👥",
      watermark: "👥",
      theme: {
        background: "linear-gradient(145deg, #F2F8FF 0%, #DFEEFF 68%, #C7E1FF 100%)",
        border: "#85BCFF",
        iconBg: "linear-gradient(145deg, #C7E1FF, #A5CEFF)",
        accent: "#3186E8",
        value: "#1D5FB8",
        shadow: "0 10px 20px rgba(49, 134, 232, 0.14)",
      },
    },

    {
      label: "Pending Acceptance",
      value: stats?.pending_acceptance ?? 0,
      icon: "🔔",
      watermark: "🔔",
      theme: {
        background: "linear-gradient(145deg, #FFFCF0 0%, #FFF1C7 68%, #FFE7A1 100%)",
        border: "#FFC94C",
        iconBg: "linear-gradient(145deg, #FFE9A5, #FFD566)",
        accent: "#F3A000",
        value: "#A85A00",
        shadow: "0 12px 24px rgba(243, 160, 0, 0.14)",
      },
    },

    {
      label: "Rejected Jobs",
      value: stats?.rejected_jobs ?? 0,
      icon: "❌",
      watermark: "❌",
      theme: {
        background: "linear-gradient(145deg, #FFF5F5 0%, #FFE1E5 68%, #FFC9D1 100%)",
        border: "#FF9CA9",
        iconBg: "linear-gradient(145deg, #FFD6DC, #FFB6C1)",
        accent: "#F0445B",
        value: "#B42336",
        shadow: "0 12px 24px rgba(240, 68, 91, 0.14)",
      },
    },

    {
      label: "Completed",
      value: stats?.total_completed ?? 0,
      icon: "✅",
      watermark: "✅",
      theme: {
        background: "linear-gradient(145deg, #F4F1FF 0%, #E8DCFF 68%, #D9C5FF 100%)",
        border: "#C4A2FF",
        iconBg: "linear-gradient(145deg, #E1D0FF, #C8A9FF)",
        accent: "#8B45E8",
        value: "#5425A8",
        shadow: "0 10px 20px rgba(139, 69, 232, 0.14)",
      },
    },
  ];

  const priorityColor: Record<string, string> = {
    HIGH: "#E53E3E",
    CRITICAL: "#E53E3E",
    MEDIUM: "#DD6B20",
    LOW: "#38A169",
  };

  const getStatusLabel = (status: string) => {
    const normalizedStatus =
      (status || "").toUpperCase();

    switch (normalizedStatus) {
      case "ASSIGNED":
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
        return status || "UNKNOWN";
    }
  };

  const getStatusColor = (status: string) => {
    const normalizedStatus =
      (status || "").toUpperCase();

    switch (normalizedStatus) {
      case "ASSIGNED":
        return "#DD6B20";

      case "ACCEPTED":
        return "#16A34A";

      case "EN_ROUTE":
        return "#5B21B6";

      case "ON_SITE":
      case "IN_PROGRESS":
      case "PAUSED":
        return "#EA580C";

      case "COMPLETED":
      case "CLOSED":
        return "#059669";

      default:
        return "#6B7280";
    }
  };

  const availabilityStale =
    profileCompleted &&
    (!lastAttendanceSync ||
      Date.now() -
        lastAttendanceSync.getTime() >
        AVAILABILITY_STALE_AFTER_MS);

  const activeStatuses = new Set([
    "ACCEPTED",
    "EN_ROUTE",
    "ON_SITE",
    "IN_PROGRESS",
    "PAUSED",
  ]);
  const currentJob =
    recentJobs.find((job) =>
      activeStatuses.has(String(job.status || "").toUpperCase()),
    ) || recentJobs[0] || null;
  const renderAcceptanceCountdown = (job: any) => {
    const seconds = acceptanceCountdowns[String(job.id)];
    if (seconds === null || seconds === undefined) return null;

    const color =
      seconds <= 30 ? "#DC2626" : seconds <= 120 ? "#D97706" : "#078A4D";
    return (
      <span
        data-testid="dashboard-acceptance-countdown"
        data-job-id={job.id}
        aria-live="off"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 5,
          color,
          fontSize: 12,
          fontWeight: 700,
          textAlign: "right",
        }}
      >
        <Clock3 size={14} />
        {seconds === 0
          ? "Acceptance deadline reached"
          : `Time left to accept: ${formatAcceptanceCountdown(seconds)}`}
      </span>
    );
  };
  const formatJobDate = (value?: string | null) => {
    if (!value) return "Not recorded";
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? "Not recorded"
      : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  const currentHour = new Date().getHours();
  const welcomeGreeting =
    currentHour < 12
      ? "Good morning!"
      : currentHour < 18
        ? "Good afternoon!"
        : "Good evening!";
  const welcomeName =
    authUser?.first_name?.trim() ||
    [authUser?.first_name, authUser?.last_name].filter(Boolean).join(" ") ||
    "Technician";
  const welcomeBanner = (
    <section
      aria-label="Technician welcome"
      style={{
        position: "relative",
        isolation: "isolate",
        minHeight: 184,
        marginBottom: 24,
        padding: "30px 40px",
        display: "flex",
        alignItems: "center",
        overflow: "hidden",
        borderRadius: 14,
        boxSizing: "border-box",
        backgroundImage: "url('/services/technician_banner.jpeg')",
        backgroundSize: "cover",
        backgroundPosition: "center 48%",
        boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
      }}
    >
      <div
        aria-hidden="true"
        style={{
          position: "absolute",
          inset: 0,
          zIndex: -1,
          background: "linear-gradient(90deg, rgba(5, 28, 20, 0.78) 0%, rgba(5, 28, 20, 0.48) 46%, rgba(5, 28, 20, 0.04) 100%)",
        }}
      />
      <div style={{ color: "#FFFFFF", textShadow: "0 1px 3px rgba(0,0,0,0.3)" }}>
        <p style={{ margin: "0 0 8px", fontSize: 16, fontWeight: 600 }}>
          {welcomeGreeting}
        </p>
        <h1 style={{ margin: 0, fontSize: "clamp(26px, 3vw, 36px)", lineHeight: 1.15, fontWeight: 750 }}>
          Welcome {welcomeName}
        </h1>
      </div>
    </section>
  );

  if (loading)
    return (
      <div style={s.page}>
        {welcomeBanner}
        <div style={s.empty}>
          Loading dashboard...
        </div>
      </div>
    );

  return (
    <div style={s.page}>
      {welcomeBanner}
      {dashboardRefreshError && (
        <div
          role="alert"
          style={{
            marginBottom: 16,
            padding: "10px 14px",
            border: "1px solid #F3D19C",
            borderRadius: 10,
            background: "#FFF8E8",
            color: "#8A4B08",
            fontSize: 13,
          }}
        >
          {dashboardRefreshError}
        </div>
      )}
      <div
        style={{
          ...s.header,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
        }}
      >
        <div>
          <h1 style={s.title}>
            Technician Dashboard
          </h1>

          <p style={s.subtitle}>
            Your work overview at a glance
          </p>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "10px",
          }}
        >
          <span
            style={{
              fontSize: "13px",
              fontWeight: 600,
              color: "#6B7280",
            }}
          >
            Availability
          </span>
          <button
            type="button"
            aria-label={technicianStatus.toLowerCase() === "available" ? "Go Offline" : "Go Online"}
            data-testid="technician-availability-toggle"
            disabled={savingStatus || !profileCompleted}
            onClick={() => {
              if (!profileCompleted) { setShowProfileMessage(true); return; }
              void handleAvailabilityChange();
            }}
            style={{
              minWidth: "130px",
              height: "40px",
              padding: "0 12px",
              border: "0",
              borderRadius: "8px",
              background: technicianStatus.toLowerCase() === "available" ? "#B91C1C" : "#15803D",
              color: "#FFFFFF",
              fontSize: "14px",
              fontWeight: 600,
              cursor: savingStatus ? "wait" : "pointer",
              opacity: savingStatus ? 0.7 : 1,
            }}
          >
            {savingStatus ? "Updating…" : technicianStatus.toLowerCase() === "available" ? "Go Offline" : "Go Online"}
          </button>

          <div
            style={{
              display: "flex",
              flexDirection:
                "column",
              gap: "2px",
              minWidth: "235px",
            }}
          >
            {gpsError && (
              <span role="alert" style={{ fontSize: "12px", color: "#B91C1C" }}>
                {gpsError}{" "}
                <button
                  type="button"
                  onClick={() => void handleAvailabilityChange()}
                  disabled={savingStatus}
                  style={{ border: 0, background: "transparent", color: "#1D4ED8", textDecoration: "underline", cursor: savingStatus ? "wait" : "pointer", padding: 0, font: "inherit" }}
                >
                  Retry
                </button>
              </span>
            )}
            {attendanceError ? (
              <span
                role="alert"
                style={{
                  fontSize: "12px",
                  color: "#B91C1C",
                }}
              >
                {attendanceError}
              </span>
            ) : availabilityStale ? (
              <>
                <span
                  data-testid="technician-availability-state"
                  aria-live="polite"
                  style={{
                    fontSize: "12px",
                    color: "#B45309",
                    fontWeight: 600,
                  }}
                >
                  Availability data is stale
                </span>

                {lastAttendanceSync && (
                  <span
                    style={{
                      fontSize: "11px",
                      color: "#6B7280",
                    }}
                  >
                    Last synced{" "}
                    {lastAttendanceSync.toLocaleTimeString()}
                  </span>
                )}
              </>
            ) : lastAttendanceSync ? (
              <>
                <span
                  data-testid="technician-availability-state"
                  aria-live="polite"
                  style={{
                    fontSize: "12px",
                    color: "#4B5563",
                    fontWeight: 600,
                  }}
                >
                  Current availability:{" "}
                  {technicianStatus}
                </span>

                <span
                  style={{
                    fontSize: "11px",
                    color: "#6B7280",
                  }}
                >
                  Last synced{" "}
                  {lastAttendanceSync.toLocaleTimeString()}
                </span>
              </>
            ) : profileCompleted ? (
              <span
                data-testid="technician-availability-state"
                aria-live="polite"
                style={{
                  fontSize: "11px",
                  color: "#6B7280",
                }}
              >
                Waiting for availability status...
              </span>
            ) : null}
          </div>

          {showProfileMessage &&
            !profileCompleted && (
              <div
                style={{
                  marginTop: "8px",
                  fontSize: "13px",
                  color: "#B45309",
                }}
              >
                Please complete your profile
                to change technician status.

                <button
                  type="button"
                  onClick={() =>
                    onNavigate(
                      "/technician/profile",
                    )
                  }
                  style={{
                    marginLeft: "8px",
                    border: "none",
                    background: "none",
                    textDecoration:
                      "underline",
                    cursor: "pointer",
                    fontWeight: 600,
                  }}
                >
                  Complete Profile
                </button>
              </div>
            )}
        </div>
      </div>

      <div style={s.grid}>
        {[...cards]
          .sort((a, b) => {
            const order = ["Total Jobs", "Pending Acceptance", "Active Jobs", "Completed", "Rejected Jobs"];
            return order.indexOf(a.label) - order.indexOf(b.label);
          })
          .map((c, i) => (
          <div
            key={i}
            style={{
              ...s.card,
              background: c.theme.background,
              borderColor: c.theme.border,
              boxShadow: c.theme.shadow,
              transition: "transform 200ms ease, box-shadow 200ms ease, filter 200ms ease, border-color 200ms ease",
            }}
            onMouseEnter={(event) => {
              event.currentTarget.style.transform = "translateY(-3px)";
              event.currentTarget.style.boxShadow = `0 16px 28px ${c.theme.accent}38`;
              event.currentTarget.style.borderColor = c.theme.accent;
            }}
            onMouseLeave={(event) => {
              event.currentTarget.style.transform = "translateY(0)";
              event.currentTarget.style.boxShadow = c.theme.shadow;
              event.currentTarget.style.borderColor = c.theme.border;
            }}
          >
            <div aria-hidden="true" style={{ position: "absolute", top: 18, right: 18, width: 14, height: 14, borderRadius: "50%", background: c.theme.accent, opacity: 0.2 }} />
            <div aria-hidden="true" style={{ position: "absolute", top: 38, right: 38, width: 9, height: 9, borderRadius: "50%", background: c.theme.accent, opacity: 0.16 }} />
            <div aria-hidden="true" style={{ position: "absolute", right: -18, bottom: -20, width: 112, height: 112, borderRadius: "50%", background: c.theme.accent, opacity: 0.13 }} />
            <div aria-hidden="true" style={{ position: "absolute", left: -18, bottom: -44, width: "78%", height: 88, borderRadius: "50% 55% 0 0", background: `linear-gradient(145deg, transparent, ${c.theme.accent}45)`, transform: "rotate(-8deg)" }} />
            <div className="technician-stat-card-watermark" aria-hidden="true" onMouseEnter={(event) => {
              event.currentTarget.style.transform = "translateY(-14px) scale(1.2) rotate(0deg)";
              event.currentTarget.style.boxShadow = `0 14px 24px ${c.theme.accent}55`;
              event.currentTarget.style.zIndex = "3";
            }} onMouseLeave={(event) => {
              event.currentTarget.style.transform = "rotate(-8deg)";
              event.currentTarget.style.boxShadow = `0 8px 14px ${c.theme.accent}30`;
              event.currentTarget.style.zIndex = "2";
            }} style={{ position: "absolute", zIndex: 2, right: 10, bottom: 8, width: 54, height: 54, borderRadius: 15, display: "grid", placeItems: "center", fontSize: 44, fontFamily: "'Segoe UI Emoji', 'Apple Color Emoji', sans-serif", opacity: 0.96, background: `radial-gradient(circle at 35% 25%, #FFFFFFD9, ${c.theme.accent}25)`, boxShadow: `0 8px 14px ${c.theme.accent}30`, transform: "rotate(-8deg)", transition: "transform 260ms cubic-bezier(.2,.8,.2,1), box-shadow 260ms ease", transformOrigin: "center bottom", cursor: "pointer", pointerEvents: "auto" }}>
              <span>{c.watermark}</span>
            </div>
            <div style={{ position: "relative", zIndex: 1, display: "flex", flexDirection: "column", alignItems: "flex-start", minHeight: "100%" }}>
            <div
              style={{
                ...s.cardIcon,
                background: c.theme.iconBg,
                color: c.theme.accent,
                boxShadow: `0 8px 16px ${c.theme.accent}26`,
              }}
            >
              <span style={{ fontSize: 21, lineHeight: 1, fontFamily: "'Segoe UI Emoji', 'Apple Color Emoji', sans-serif" }}>{c.icon}</span>
            </div>

            <span style={{ ...s.cardLabel, marginTop: 8, fontSize: 12, color: "#253047", fontWeight: 600 }}>
              {c.label}
            </span>

            <span aria-hidden="true" style={{ width: 20, height: 3, borderRadius: 4, background: c.theme.accent, marginTop: 6 }} />

            <span style={{ ...s.cardValue, marginTop: 7, fontSize: 24, lineHeight: 1, color: c.theme.value }}>
              {c.value}
            </span>
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: 14, marginBottom: 14 }}>
        <section style={{ ...s.section, minWidth: 0, background: "linear-gradient(145deg, #FFFFFF 0%, #F0F8FF 100%)", borderColor: "#CFE4FA" }}>
          <div style={{ ...s.sectionTitle, justifyContent: "space-between" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 9 }}>
              <Briefcase size={18} color="#1682F8" /> Current Job
            </span>
            {currentJob && (
              <span style={{ display: "grid", justifyItems: "end", gap: 6, minWidth: 0, maxWidth: "60%" }}>
                <span style={s.badge(getStatusColor(currentJob.status))}>{getStatusLabel(currentJob.status)}</span>
                {renderAcceptanceCountdown(currentJob)}
              </span>
            )}
          </div>
          {currentJob ? (
            <>
              <h2 style={{ margin: "2px 0 14px", fontSize: 19, color: "#14213D" }}>
                #{currentJob.id} — {currentJob.service_type || "Service"}
                {currentJob.priority && <span style={{ ...s.badge(priorityColor[currentJob.priority] || "#6B7280"), marginLeft: 10, verticalAlign: "middle" }}>{currentJob.priority}</span>}
              </h2>
              <div style={{ display: "grid", gap: 12, color: "#52627E", fontSize: 14 }}>
                <span style={{ display: "flex", alignItems: "center", gap: 9 }}><UserRound size={17} />{currentJob.customer_name || "Customer"}</span>
                <span style={{ display: "flex", alignItems: "flex-start", gap: 9, lineHeight: 1.55 }}><MapPin size={17} style={{ flex: "0 0 auto", marginTop: 2 }} />{currentJob.location || currentJob.site_address || "Service location not provided"}</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginTop: 22 }}>
                <div style={{ color: "#52627E", display: "flex", alignItems: "center", gap: 8 }}><Clock3 size={18} /><span>Assigned<br /><strong style={{ color: "#14213D" }}>{formatJobDate(currentJob.assigned_at || currentJob.created_at)}</strong></span></div>
                <button type="button" onClick={() => onNavigate("tech_jobs")} style={{ border: 0, borderRadius: 9, padding: "11px 18px", background: "#078A4D", color: "white", fontWeight: 700, cursor: "pointer" }}>Open Job <ArrowRight size={15} style={{ verticalAlign: "middle", marginLeft: 5 }} /></button>
              </div>
            </>
          ) : <div style={s.empty}>No current job assigned.</div>}
        </section>

      </div>

      <TechnicianPerformanceReport
        data={performanceReport}
        period={reportPeriod}
        onPeriodChange={setReportPeriod}
        error={performanceReportError}
      />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 420px), 1fr))", gap: 14, alignItems: "stretch", marginTop: 14 }}>
        <section style={{ ...s.section, background: "linear-gradient(145deg, #FFFFFF 0%, #F0FFF8 100%)", borderColor: "#CDEFE0" }}>
          <div style={s.sectionTitle}><Activity size={18} color="#1682F8" /> Today's Activity</div>
          {currentJob ? (
            <div style={{ display: "grid", gridTemplateColumns: "62px 14px 1fr", gap: "12px 10px", alignItems: "start", fontSize: 12 }}>
              <span style={{ color: "#52627E" }}>{formatJobDate(currentJob.created_at)}</span><span style={{ width: 10, height: 10, borderRadius: "50%", background: "#0AA66A", marginTop: 3 }} /><span><strong>Job created</strong><div style={{ color: "#71809B", marginTop: 3 }}>#{currentJob.id} — {currentJob.service_type || "Service"}</div></span>
              <span style={{ color: "#52627E" }}>{formatJobDate(currentJob.assigned_at || currentJob.updated_at)}</span><span style={{ width: 10, height: 10, borderRadius: "50%", background: "#1682F8", marginTop: 3 }} /><span><strong>Current status: {getStatusLabel(currentJob.status)}</strong><div style={{ color: "#71809B", marginTop: 3 }}>Last updated {formatJobDate(currentJob.updated_at)}</div></span>
            </div>
          ) : <div style={s.empty}>Job activity will appear here when a job is assigned.</div>}
        </section>

        <section style={{ ...s.section, background: "linear-gradient(145deg, #FFFFFF 0%, #FFF8EB 100%)", borderColor: "#F4E2BD" }}>
          <div style={{ ...s.sectionTitle, justifyContent: "space-between" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 9 }}><BarChart3 size={18} color="#1682F8" /> Recent Assigned Jobs</span>
            <button type="button" onClick={() => onNavigate("tech_jobs")} style={{ border: 0, background: "transparent", color: "#1682F8", fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap" }}>View All Jobs</button>
          </div>
          {recentJobs.length === 0 ? <div style={s.empty}>No assigned jobs yet.</div> : recentJobs.slice(0, 4).map((job: any) => (
            <button key={job.id} type="button" onClick={() => onNavigate("tech_jobs")} style={{ ...s.jobRow, width: "100%", textAlign: "left", background: "transparent", cursor: "pointer", gap: 10 }}>
              <span style={{ ...s.jobInfo, minWidth: 0 }}><span style={s.jobTitle}>#{job.id} — {job.service_type || "Service"}</span><span style={{ ...s.jobMeta, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 260 }}>{job.location || job.customer_name || "Service location"}</span></span>
              <span style={{ display: "grid", justifyItems: "end", gap: 6, minWidth: 0, maxWidth: "60%" }}>
                <span style={{ ...s.badge(getStatusColor(job.status)), whiteSpace: "nowrap" }}>{getStatusLabel(job.status)}</span>
                {renderAcceptanceCountdown(job)}
              </span>
            </button>
          ))}
        </section>
      </div>
      {assignedOffer && (
        <TechnicianJobAssignmentPopup
          job={assignedOffer}
          countdownSeconds={assignedOfferSeconds}
          distanceDisplay={offerDistanceDisplay}
          loading={offerActionLoading}
          rejecting={rejectingOffer}
          rejectReason={rejectReason}
          onClose={dismissAssignedOffer}
          onAccept={() => void handleAssignedOfferAccept()}
          onReject={() => setRejectingOffer(true)}
          onRejectReasonChange={setRejectReason}
          onCancelReject={() => {
            setRejectingOffer(false);
            setRejectReason("");
            setOfferError(null);
          }}
          onConfirmReject={() => void handleAssignedOfferReject()}
        />
      )}
      {false && assignedOffer && (
        <div
          data-testid="dashboard-assignment-popup-backdrop"
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 1000,
            display: "grid",
            placeItems: "center",
            padding: 16,
            background: "rgba(15, 23, 42, 0.56)",
            backdropFilter: "blur(4px)",
          }}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="dashboard-assignment-popup-title"
            style={{
              width: "min(100%, 520px)",
              maxHeight: "min(90vh, 680px)",
              overflowY: "auto",
              boxSizing: "border-box",
              padding: 28,
              borderRadius: 20,
              background: "#FFFFFF",
              boxShadow: "0 24px 70px rgba(15, 23, 42, 0.3)",
              color: "#14213D",
            }}
          >
            <header style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
              <div>
                <span style={{ color: "#078A4D", fontSize: 12, fontWeight: 700 }}>
                  JOB #{assignedOffer.id}
                </span>
                <h2
                  id="dashboard-assignment-popup-title"
                  style={{ margin: "5px 0", fontSize: 25 }}
                >
                  Job Assigned
                </h2>
                <p style={{ margin: 0, color: "#64748B", fontSize: 14 }}>
                  Review the service request and respond before the deadline.
                </p>
              </div>
              <button
                type="button"
                aria-label="Close assigned job popup"
                onClick={dismissAssignedOffer}
                style={{
                  width: 36,
                  height: 36,
                  border: "1px solid #E2E8F0",
                  borderRadius: 10,
                  background: "#FFFFFF",
                  color: "#475569",
                  cursor: "pointer",
                  flex: "0 0 auto",
                }}
              >
                <X size={18} />
              </button>
            </header>

            {rejectingOffer ? (
              <div style={{ marginTop: 24 }}>
                <label
                  htmlFor="dashboard-reject-reason"
                  style={{ display: "block", marginBottom: 8, fontWeight: 700 }}
                >
                  Why are you rejecting this job?
                </label>
                <textarea
                  id="dashboard-reject-reason"
                  value={rejectReason}
                  onChange={(event) => setRejectReason(event.target.value)}
                  placeholder="Explain why you're rejecting this job..."
                  rows={4}
                  style={{
                    boxSizing: "border-box",
                    width: "100%",
                    resize: "vertical",
                    padding: 12,
                    border: "1px solid #CBD5E1",
                    borderRadius: 10,
                    font: "inherit",
                  }}
                />
              </div>
            ) : (
              <>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                    gap: 12,
                    marginTop: 22,
                    padding: 16,
                    border: "1px solid #BBF7D0",
                    borderRadius: 14,
                    background: "#F0FDF4",
                  }}
                >
                  <div>
                    <span style={{ color: "#64748B", fontSize: 11, fontWeight: 700 }}>
                      TIME TO ACCEPT
                    </span>
                    <strong
                      data-testid="dashboard-popup-acceptance-countdown"
                      style={{
                        display: "block",
                        marginTop: 5,
                        color:
                          legacyAssignedOfferSeconds <= 30
                            ? "#DC2626"
                            : legacyAssignedOfferSeconds <= 120
                              ? "#D97706"
                              : "#078A4D",
                        fontSize: 22,
                      }}
                    >
                      {legacyAssignedOfferSeconds === 0
                        ? "Deadline reached"
                        : formatAcceptanceCountdown(legacyAssignedOfferSeconds)}
                    </strong>
                  </div>
                  <div>
                    <span style={{ color: "#64748B", fontSize: 11, fontWeight: 700 }}>
                      SERVICE TYPE
                    </span>
                    <strong style={{ display: "block", marginTop: 5, fontSize: 16 }}>
                      {assignedOffer.service_type || "Service"}
                    </strong>
                  </div>
                </div>
                <div style={{ display: "grid", gap: 13, marginTop: 20 }}>
                  <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                    <UserRound size={18} color="#078A4D" />
                    <strong>{assignedOffer.customer_name || "Customer"}</strong>
                  </div>
                  {assignedOffer.contact_number && (
                    <a
                      href={`tel:${String(assignedOffer.contact_number).replace(/[^+\d]/g, "")}`}
                      style={{ display: "flex", gap: 10, color: "#1769E8", textDecoration: "none" }}
                    >
                      <Phone size={18} />
                      {assignedOffer.contact_number}
                    </a>
                  )}
                  <div style={{ display: "flex", gap: 10, alignItems: "flex-start", color: "#475569" }}>
                    <MapPin size={18} color="#078A4D" style={{ flex: "0 0 auto" }} />
                    <span>{assignedOffer.location || assignedOffer.site_address || "Service location unavailable"}</span>
                  </div>
                  <p style={{ margin: 0, padding: 13, borderRadius: 10, background: "#F8FAFC", color: "#475569", lineHeight: 1.5 }}>
                    {assignedOffer.issue_description || "No additional service details provided."}
                  </p>
                </div>
              </>
            )}

            {offerError && (
              <p role="alert" style={{ margin: "14px 0 0", color: "#B91C1C" }}>
                {offerError}
              </p>
            )}
            <div style={{ display: "flex", gap: 10, marginTop: 24 }}>
              {rejectingOffer ? (
                <>
                  <button
                    type="button"
                    onClick={() => {
                      setRejectingOffer(false);
                      setRejectReason("");
                      setOfferError(null);
                    }}
                    disabled={offerActionLoading}
                    style={{
                      flex: 1,
                      minHeight: 44,
                      border: "1px solid #CBD5E1",
                      borderRadius: 10,
                      background: "#FFFFFF",
                      color: "#334155",
                      fontWeight: 700,
                      cursor: "pointer",
                    }}
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleAssignedOfferReject()}
                    disabled={offerActionLoading || rejectReason.trim().length < 10}
                    style={{
                      flex: 1,
                      minHeight: 44,
                      border: 0,
                      borderRadius: 10,
                      background: "#DC2626",
                      color: "#FFFFFF",
                      fontWeight: 700,
                      cursor: "pointer",
                      opacity: offerActionLoading || rejectReason.trim().length < 10 ? 0.6 : 1,
                    }}
                  >
                    {offerActionLoading ? "Rejecting..." : "Confirm Reject"}
                  </button>
                </>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => setRejectingOffer(true)}
                    disabled={offerActionLoading}
                    style={{
                      flex: 1,
                      minHeight: 46,
                      border: "1px solid #FECACA",
                      borderRadius: 10,
                      background: "#FEF2F2",
                      color: "#B91C1C",
                      fontWeight: 700,
                      cursor: "pointer",
                    }}
                  >
                    Reject
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleAssignedOfferAccept()}
                    disabled={offerActionLoading || legacyAssignedOfferSeconds <= 0}
                    style={{
                      flex: 1,
                      minHeight: 46,
                      border: 0,
                      borderRadius: 10,
                      background: "#078A4D",
                      color: "#FFFFFF",
                      fontWeight: 700,
                      cursor: "pointer",
                      opacity: offerActionLoading || legacyAssignedOfferSeconds <= 0 ? 0.6 : 1,
                    }}
                  >
                    <CheckCircle size={16} style={{ verticalAlign: "middle", marginRight: 6 }} />
                    {offerActionLoading ? "Accepting..." : "Accept Job"}
                  </button>
                </>
              )}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
