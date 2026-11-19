import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle,
  Clock,
  RefreshCw,
  Briefcase,
  UserCheck,
} from "lucide-react";

import { getTechnicianDashboard } from "../../services/technicianPortalService";

interface TechnicianPerformanceData {
  total_assigned?: number;
  active_jobs?: number;
  completed_today?: number;
  pending_acceptance?: number;
  total_completed?: number;
  rejected_jobs?: number;
  technician_status?: string | null;
  profile_completed?: boolean;
}

type ReportState = "loading" | "ready" | "error";

const metricValue = (
  value: number | undefined,
): number => {
  return Number.isFinite(value) ? Number(value) : 0;
};

const normalizeStatus = (
  status?: string | null,
): string => {
  if (!status) {
    return "Not Available";
  }

  const normalized = status
    .trim()
    .toLowerCase()
    .replace(/[_-]+/g, " ");

  return normalized
    .split(" ")
    .filter(Boolean)
    .map(
      (part) =>
        part.charAt(0).toUpperCase() +
        part.slice(1),
    )
    .join(" ");
};

const getPerformanceErrorMessage = (
  error: unknown,
): string => {
  const status = (error as any)?.response?.status;

  if (status === 403) {
    return "You are not authorized to view your technician performance report.";
  }

  if (status === 404) {
    return "Technician performance data is not available.";
  }

  return "Technician performance data is temporarily unavailable. Please try again.";
};

const formatLastUpdated = (
  value: Date | null,
): string => {
  if (!value) {
    return "Not available";
  }

  return value.toLocaleString();
};

const styles = {
  page: {
    padding: "24px",
    height: "100%",
    overflowY: "auto" as const,
    boxSizing: "border-box" as const,
    background: "#EEF4F1",
    fontFamily: "'Inter', sans-serif",
  },

  header: {
    background: "#FFFFFF",
    border: "1px solid #E3ECE7",
    borderRadius: "14px",
    padding: "22px",
    marginBottom: "18px",
    boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
  },

  headerRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: "16px",
    flexWrap: "wrap" as const,
  },

  title: {
    margin: 0,
    fontSize: "24px",
    fontWeight: 700,
    color: "#1F2933",
  },

  subtitle: {
    margin: "5px 0 0",
    fontSize: "13px",
    color: "#6B7280",
    lineHeight: 1.5,
  },

  refreshButton: {
    border: "1px solid #D1D5DB",
    background: "#FFFFFF",
    color: "#374151",
    borderRadius: "9px",
    minHeight: "38px",
    padding: "0 13px",
    fontSize: "12px",
    fontWeight: 700,
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
    gap: "7px",
  },

  metaRow: {
    display: "flex",
    flexWrap: "wrap" as const,
    gap: "10px 18px",
    marginTop: "15px",
    fontSize: "11px",
    color: "#6B7280",
  },

  metaItem: {
    display: "inline-flex",
    alignItems: "center",
    gap: "5px",
  },

  grid: {
    display: "grid",
    gridTemplateColumns:
      "repeat(auto-fit, minmax(190px, 1fr))",
    gap: "14px",
    marginBottom: "18px",
  },

  card: {
    background: "#FFFFFF",
    border: "1px solid #E3ECE7",
    borderRadius: "14px",
    padding: "18px",
    boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
  },

  cardTop: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "10px",
    marginBottom: "13px",
  },

  iconBox: {
    width: "38px",
    height: "38px",
    borderRadius: "10px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#ECFDF5",
    color: "#047857",
  },

  cardLabel: {
    fontSize: "12px",
    color: "#6B7280",
    fontWeight: 600,
  },

  cardValue: {
    marginTop: "4px",
    fontSize: "28px",
    lineHeight: 1,
    fontWeight: 800,
    color: "#1F2933",
  },

  section: {
    background: "#FFFFFF",
    border: "1px solid #E3ECE7",
    borderRadius: "14px",
    padding: "20px",
    boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
  },

  sectionTitle: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    margin: 0,
    fontSize: "16px",
    fontWeight: 700,
    color: "#1F2933",
  },

  description: {
    margin: "7px 0 18px",
    fontSize: "12px",
    color: "#6B7280",
    lineHeight: 1.5,
  },

  table: {
    width: "100%",
    borderCollapse: "collapse" as const,
  },

  th: {
    textAlign: "left" as const,
    padding: "11px 10px",
    borderBottom: "1px solid #E5E7EB",
    fontSize: "11px",
    fontWeight: 700,
    color: "#6B7280",
    textTransform: "uppercase" as const,
    letterSpacing: "0.04em",
  },

  td: {
    padding: "12px 10px",
    borderBottom: "1px solid #F3F4F6",
    fontSize: "13px",
    color: "#374151",
  },

  valueCell: {
    fontWeight: 800,
    textAlign: "right" as const,
    color: "#111827",
  },

  statusBadge: {
    display: "inline-flex",
    alignItems: "center",
    padding: "4px 10px",
    borderRadius: "999px",
    background: "#ECFDF5",
    color: "#047857",
    fontSize: "11px",
    fontWeight: 700,
  },

  error: {
    marginTop: "16px",
    padding: "12px 14px",
    borderRadius: "10px",
    border: "1px solid #FECACA",
    background: "#FEF2F2",
    color: "#991B1B",
    fontSize: "12px",
    lineHeight: 1.5,
  },

  loading: {
    background: "#FFFFFF",
    border: "1px solid #E3ECE7",
    borderRadius: "14px",
    padding: "46px",
    textAlign: "center" as const,
    color: "#6B7280",
    fontSize: "14px",
    boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
  },

  empty: {
    background: "#FFFFFF",
    border: "1px solid #E3ECE7",
    borderRadius: "14px",
    padding: "38px",
    textAlign: "center" as const,
    color: "#6B7280",
    fontSize: "13px",
    lineHeight: 1.5,
    boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
  },
};

const metrics = [
  {
    key: "total_assigned",
    label: "Total Assigned",
    icon: Briefcase,
  },
  {
    key: "active_jobs",
    label: "Active Jobs",
    icon: Activity,
  },
  {
    key: "completed_today",
    label: "Completed Today",
    icon: CheckCircle,
  },
  {
    key: "total_completed",
    label: "Total Completed",
    icon: UserCheck,
  },
  {
    key: "pending_acceptance",
    label: "Pending Acceptance",
    icon: Clock,
  },
  {
    key: "rejected_jobs",
    label: "Rejected Jobs",
    icon: AlertTriangle,
  },
] as const;

export default function TechnicianPerformanceReportPage() {
  const [report, setReport] =
    useState<TechnicianPerformanceData | null>(null);

  const [state, setState] =
    useState<ReportState>("loading");

  const [error, setError] =
    useState<string | null>(null);

  const [lastUpdated, setLastUpdated] =
    useState<Date | null>(null);

  const loadReport = useCallback(async () => {
    setState("loading");
    setError(null);

    try {
      const response =
        await getTechnicianDashboard();

      const data =
        (response?.data || null) as
          | TechnicianPerformanceData
          | null;

      if (!data) {
        setReport(null);
        setState("ready");
        setLastUpdated(new Date());
        return;
      }

      setReport(data);
      setState("ready");
      setLastUpdated(new Date());
    } catch (requestError) {
      console.error(
        "Failed to load technician performance report:",
        requestError,
      );

      setReport(null);
      setState("error");
      setError(
        getPerformanceErrorMessage(
          requestError,
        ),
      );
    }
  }, []);

  useEffect(() => {
    void loadReport();
  }, [loadReport]);

  const handleRefresh = () => {
    if (state === "loading") {
      return;
    }

    void loadReport();
  };

  const hasActivity =
    report !== null &&
    [
      report.total_assigned,
      report.active_jobs,
      report.completed_today,
      report.total_completed,
      report.pending_acceptance,
      report.rejected_jobs,
    ].some((value) =>
      metricValue(value) > 0,
    );

  if (state === "loading" && !report) {
    return (
      <div style={styles.page}>
        <div style={styles.loading}>
          Loading technician performance report...
        </div>
      </div>
    );
  }

  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <div style={styles.headerRow}>
          <div>
            <h1 style={styles.title}>
              Technician Performance Report
            </h1>

            <p style={styles.subtitle}>
              Backend-authoritative performance metrics for
              the authenticated technician.
            </p>
          </div>

          <button
            type="button"
            onClick={handleRefresh}
            disabled={state === "loading"}
            style={{
              ...styles.refreshButton,
              opacity:
                state === "loading" ? 0.6 : 1,
              cursor:
                state === "loading"
                  ? "not-allowed"
                  : "pointer",
            }}
            aria-label="Refresh technician performance report"
          >
            <RefreshCw
              size={14}
              style={{
                transform:
                  state === "loading"
                    ? "rotate(180deg)"
                    : undefined,
              }}
            />
            {state === "loading"
              ? "Refreshing..."
              : "Refresh"}
          </button>
        </div>

        <div style={styles.metaRow}>
          <span style={styles.metaItem}>
            <Activity size={13} />
            Source: Backend dashboard contract
          </span>

          <span style={styles.metaItem}>
            Last updated:{" "}
            {formatLastUpdated(lastUpdated)}
          </span>

          <span style={styles.metaItem}>
            Technician status:{" "}
            {normalizeStatus(
              report?.technician_status,
            )}
          </span>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          style={styles.error}
        >
          {error}
        </div>
      )}

      {state === "ready" && !report ? (
        <div
          role="status"
          style={styles.empty}
        >
          No technician performance data is currently
          available.
        </div>
      ) : (
        <>
          <div style={styles.grid}>
            {metrics.map(
              ({
                key,
                label,
                icon: Icon,
              }) => (
                <div
                  key={key}
                  style={styles.card}
                >
                  <div style={styles.cardTop}>
                    <span style={styles.cardLabel}>
                      {label}
                    </span>

                    <div style={styles.iconBox}>
                      <Icon size={18} />
                    </div>
                  </div>

                  <div style={styles.cardValue}>
                    {metricValue(report?.[key])}
                  </div>
                </div>
              ),
            )}
          </div>

          <section style={styles.section}>
            <h2 style={styles.sectionTitle}>
              <Activity size={17} />
              Performance Details
            </h2>

            <p style={styles.description}>
              These values are presented directly from the
              technician dashboard API. No authoritative KPI
              is recomputed in the client.
            </p>

            <div
              style={{
                overflowX: "auto",
              }}
            >
              <table
                style={styles.table}
              >
                <thead>
                  <tr>
                    <th style={styles.th}>
                      Metric
                    </th>
                    <th
                      style={{
                        ...styles.th,
                        textAlign: "right",
                      }}
                    >
                      Backend Value
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {metrics.map(
                    ({
                      key,
                      label,
                    }) => (
                      <tr key={key}>
                        <td style={styles.td}>
                          {label}
                        </td>

                        <td
                          style={{
                            ...styles.td,
                            ...styles.valueCell,
                          }}
                        >
                          {metricValue(
                            report?.[key],
                          )}
                        </td>
                      </tr>
                    ),
                  )}

                  <tr>
                    <td style={styles.td}>
                      Technician Status
                    </td>

                    <td
                      style={{
                        ...styles.td,
                        ...styles.valueCell,
                      }}
                    >
                      <span
                        style={
                          styles.statusBadge
                        }
                      >
                        {normalizeStatus(
                          report?.technician_status,
                        )}
                      </span>
                    </td>
                  </tr>

                  <tr>
                    <td
                      style={{
                        ...styles.td,
                        borderBottom:
                          "none",
                      }}
                    >
                      Profile Completed
                    </td>

                    <td
                      style={{
                        ...styles.td,
                        ...styles.valueCell,
                        borderBottom:
                          "none",
                      }}
                    >
                      {report?.profile_completed
                        ? "Yes"
                        : "No"}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            {!hasActivity && (
              <div
                role="status"
                style={{
                  marginTop: "16px",
                  padding: "12px 14px",
                  borderRadius: "10px",
                  background: "#F9FAFB",
                  border:
                    "1px solid #E5E7EB",
                  color: "#6B7280",
                  fontSize: "12px",
                }}
              >
                The backend currently reports no recorded
                job activity for this technician.
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
