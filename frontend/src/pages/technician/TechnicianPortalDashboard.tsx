import { useState, useEffect } from "react";
import {
  Briefcase,
  CheckCircle,
  Clock,
  AlertTriangle,
  Activity,
  ArrowRight,
} from "lucide-react";
import {
  getTechnicianDashboard,
  getTechnicianJobs,
  updateTechnicianStatus,
} from "../../services/technicianPortalService";

const TECHNICIAN_STATUSES = [
  "Available",
  "Busy",
  "Assigned",
  "Offline",
  "En Route",
  "On Site",
  "On Break",
  "Suspended",
];

const normalizeTechnicianStatus = (status?: string) => {
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

  return map[value] || "Available";
};

const s = {
  page: {
    padding: "24px",
    height: "100%",
    overflowY: "auto" as const,
    background: "#EEF4F1",
    fontFamily: "'Inter', sans-serif",
  },
  header: { marginBottom: "24px" },
  title: { fontSize: "24px", fontWeight: 700, color: "#1F2933", margin: 0 },
  subtitle: { fontSize: "14px", color: "#6B7280", marginTop: "4px" },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
    gap: "16px",
    marginBottom: "28px",
  },
  card: {
    background: "#fff",
    borderRadius: "14px",
    padding: "20px",
    boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
    border: "1px solid #E3ECE7",
    display: "flex",
    flexDirection: "column" as const,
    gap: "8px",
  },
  cardIcon: {
    width: "40px",
    height: "40px",
    borderRadius: "10px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  },
  cardLabel: { fontSize: "12px", color: "#6B7280", fontWeight: 500 },
  cardValue: { fontSize: "28px", fontWeight: 700, color: "#1F2933" },
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
}: {
  onNavigate: (tab: string) => void;
}) {
  const [stats, setStats] = useState<any>(null);
  const [recentJobs, setRecentJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [technicianStatus, setTechnicianStatus] = useState("Not Available");
  const [savingStatus, setSavingStatus] = useState(false);
  const [profileCompleted, setProfileCompleted] = useState(false);
  const [showProfileMessage, setShowProfileMessage] = useState(false);

  const loadDashboard = async () => {
    try {
      const [dashRes, jobsRes] = await Promise.all([
        getTechnicianDashboard(),
        getTechnicianJobs(),
      ]);

      setStats(dashRes.data);
      setRecentJobs((jobsRes.data || []).slice(0, 5));
    } catch {
      // Keep existing dashboard behaviour on API failure.
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const loadDashboard = async () => {
      try {
        const [dashRes, jobsRes] = await Promise.all([
          getTechnicianDashboard(),
          getTechnicianJobs(),
        ]);

        setStats(dashRes.data);

        const isProfileCompleted = Boolean(dashRes.data?.profile_completed);

        setProfileCompleted(isProfileCompleted);

        setTechnicianStatus(
          isProfileCompleted
            ? normalizeTechnicianStatus(dashRes.data?.technician_status)
            : "Not Available",
        );

        setRecentJobs((jobsRes.data || []).slice(0, 5));
      } catch (error) {
        console.error("Failed to load dashboard:", error);
      } finally {
        setLoading(false);
      }
    };

    loadDashboard();

    const timer = setInterval(loadDashboard, 5000);

    return () => clearInterval(timer);
  }, []);
  const handleStatusChange = async (newStatus: string) => {
    const previousStatus = technicianStatus;

    setTechnicianStatus(newStatus);

    try {
      setSavingStatus(true);

      const response = await updateTechnicianStatus(newStatus);

      setTechnicianStatus(
        normalizeTechnicianStatus(
          response.data?.technician_status || newStatus,
        ),
      );
    } catch (error) {
      console.error("Failed to update technician status:", error);

      setTechnicianStatus(previousStatus);
    } finally {
      setSavingStatus(false);
    }
  };

  const cards = [
    {
      label: "Active Jobs",
      value: stats?.active_jobs ?? 0,
      icon: <Activity size={20} />,
      bg: "#E8F5E9",
      color: "#2E7D32",
    },
    {
      label: "Pending Acceptance",
      value: stats?.pending_acceptance ?? 0,
      icon: <Clock size={20} />,
      bg: "#FFF8E1",
      color: "#F57F17",
    },
    {
      label: "Rejected Jobs",
      value: stats?.rejected_jobs ?? 0,
      icon: <AlertTriangle size={20} />,
      bg: "#FDECEC",
      color: "#D32F2F",
    },
    {
      label: "Total Completed",
      value: stats?.total_completed ?? 0,
      icon: <Briefcase size={20} />,
      bg: "#F3E5F5",
      color: "#7B1FA2",
    },
  ];

  const priorityColor: Record<string, string> = {
    HIGH: "#E53E3E",
    CRITICAL: "#E53E3E",
    MEDIUM: "#DD6B20",
    LOW: "#38A169",
  };

  const getStatusLabel = (status: string) => {
    const normalizedStatus = (status || "").toUpperCase();

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
    const normalizedStatus = (status || "").toUpperCase();

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

  if (loading)
    return (
      <div style={s.page}>
        <div style={s.empty}>Loading dashboard...</div>
      </div>
    );

  return (
    <div style={s.page}>
      <div
        style={{
          ...s.header,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
        }}
      >
        <div>
          <h1 style={s.title}>Technician Dashboard</h1>
          <p style={s.subtitle}>Your work overview at a glance</p>
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
            Status
          </span>

          <select
            value={profileCompleted ? technicianStatus : "Not Available"}
            disabled={savingStatus || !profileCompleted}
            onChange={(e) => {
              if (!profileCompleted) {
                setShowProfileMessage(true);
                return;
              }

              handleStatusChange(e.target.value);
            }}
            style={{
              minWidth: "185px",
              height: "40px",
              padding: "0 12px",
              border: "1px solid #D7E5DE",
              borderRadius: "8px",
              background: "#FFFFFF",
              color: "#1F2933",
              fontSize: "14px",
              fontWeight: 600,
              cursor: savingStatus ? "wait" : "pointer",
              opacity: savingStatus ? 0.7 : 1,
            }}
          >
            <option value="" disabled>
              Select Status
            </option>
            {TECHNICIAN_STATUSES.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>

          {showProfileMessage && !profileCompleted && (
            <div
              style={{
                marginTop: "8px",
                fontSize: "13px",
                color: "#B45309",
              }}
            >
              Please complete your profile to change technician status.
              <button
                type="button"
                onClick={() => onNavigate("/technician/profile")}
                style={{
                  marginLeft: "8px",
                  border: "none",
                  background: "none",
                  textDecoration: "underline",
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
        {cards.map((c, i) => (
          <div key={i} style={s.card}>
            <div style={{ ...s.cardIcon, background: c.bg, color: c.color }}>
              {c.icon}
            </div>

            <span style={s.cardLabel}>{c.label}</span>

            <span style={s.cardValue}>{c.value}</span>
          </div>
        ))}
      </div>

      <div style={s.section}>
        <div style={s.sectionTitle}>
          <Briefcase size={18} color="#7AAE8A" /> Recent Assigned Jobs
        </div>

        {recentJobs.length === 0 ? (
          <div style={s.empty}>No active jobs at the moment</div>
        ) : (
          recentJobs.map((job: any) => (
            <div key={job.id} style={s.jobRow}>
              <div style={s.jobInfo}>
                <span style={s.jobTitle}>
                  #{job.id} — {job.service_type || "Service"}
                </span>

                <span style={s.jobMeta}>
                  {job.customer_name} • {job.location}
                </span>
              </div>

              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                }}
              >
                <span style={s.badge(priorityColor[job.priority] || "#6B7280")}>
                  {job.priority}
                </span>

                <span style={s.badge(getStatusColor(job.status))}>
                  {getStatusLabel(job.status)}
                </span>
              </div>
            </div>
          ))
        )}

        {recentJobs.length > 0 && (
          <button
            onClick={() => onNavigate("tech_jobs")}
            style={{
              marginTop: "12px",
              background: "none",
              border: "none",
              color: "#7AAE8A",
              fontSize: "13px",
              fontWeight: 600,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "4px",
            }}
          >
            View All Jobs <ArrowRight size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
