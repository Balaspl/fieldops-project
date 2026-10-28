import {
  BarChart3,
  CheckCircle2,
  Clock3,
  MapPin,
  Star,
} from "lucide-react";
import type { TechnicianPerformanceReportResponse } from "../../services/technicianPortalService";
import "./TechnicianPerformanceReport.css";

type ReportPeriod = "week" | "month";

interface TechnicianPerformanceReportProps {
  data: TechnicianPerformanceReportResponse | null;
  period: ReportPeriod;
  onPeriodChange: (period: ReportPeriod) => void;
  error?: string | null;
}

const statusColors: Record<string, string> = {
  completed: "#16A36A",
  active: "#2F80ED",
  pending: "#F2A900",
  cancelled: "#E46767",
  other: "#8793A5",
};

const statusLabels: Record<string, string> = {
  completed: "Completed",
  active: "In progress",
  pending: "Pending",
  cancelled: "Cancelled",
  other: "Other",
};

const formatDuration = (minutes?: number | null) => {
  if (minutes == null || !Number.isFinite(minutes)) return "—";
  const totalMinutes = Math.round(minutes);
  const hours = Math.floor(totalMinutes / 60);
  const remainder = totalMinutes % 60;
  return hours > 0
    ? `${hours}h ${String(remainder).padStart(2, "0")}m`
    : `${remainder}m`;
};

export default function TechnicianPerformanceReport({
  data,
  period,
  onPeriodChange,
  error,
}: TechnicianPerformanceReportProps) {
  const trend = data?.completion_trend ?? [];
  const distribution = data?.status_distribution ?? [];
  const maxCompletions = Math.max(1, ...trend.map((item) => item.count));
  const totalStatusJobs = distribution.reduce(
    (total, item) => total + item.count,
    0,
  );
  let chartOffset = 0;
  const chartStops = distribution.map((item) => {
    const start = chartOffset;
    chartOffset += totalStatusJobs
      ? (item.count / totalStatusJobs) * 100
      : 0;
    return `${statusColors[item.status] ?? statusColors.other} ${start}% ${chartOffset}%`;
  });

  return (
    <section className="technician-performance" aria-labelledby="performance-title">
      <header className="technician-performance__header">
        <div>
          <div className="technician-performance__eyebrow">
            <BarChart3 size={16} aria-hidden="true" />
            PERFORMANCE OVERVIEW
          </div>
          <h2 id="performance-title">Performance Report</h2>
          <p>Track completed work, customer feedback, and job activity.</p>
        </div>
        <label className="technician-performance__period">
          <span>Reporting period</span>
          <select
            aria-label="Performance report period"
            value={period}
            onChange={(event) =>
              onPeriodChange(event.target.value as ReportPeriod)
            }
          >
            <option value="week">This week</option>
            <option value="month">This month</option>
          </select>
        </label>
      </header>

      {error && (
        <p className="technician-performance__error" role="alert">
          {error}
        </p>
      )}

      <div className="technician-performance__metrics">
        <article className="technician-performance__metric">
          <span className="technician-performance__metric-icon technician-performance__metric-icon--green">
            <CheckCircle2 size={20} aria-hidden="true" />
          </span>
          <span className="technician-performance__metric-label">
            Jobs completed
          </span>
          <strong>{data?.period_completed_jobs ?? "—"}</strong>
          <span className="technician-performance__metric-caption">
            {period === "week" ? "This week" : "This month"}
          </span>
        </article>
        <article className="technician-performance__metric">
          <span className="technician-performance__metric-icon technician-performance__metric-icon--blue">
            <Clock3 size={20} aria-hidden="true" />
          </span>
          <span className="technician-performance__metric-label">
            Avg. completion time
          </span>
          <strong>{formatDuration(data?.average_completion_minutes)}</strong>
          <span className="technician-performance__metric-caption">
            From job start to completion
          </span>
        </article>
        <article className="technician-performance__metric">
          <span className="technician-performance__metric-icon technician-performance__metric-icon--gold">
            <Star size={20} aria-hidden="true" />
          </span>
          <span className="technician-performance__metric-label">
            Customer rating
          </span>
          <strong>
            {data?.customer_rating == null
              ? "—"
              : `${data.customer_rating.toFixed(1)}/5`}
          </strong>
          <span className="technician-performance__metric-caption">
            Based on submitted feedback
          </span>
        </article>
        <article className="technician-performance__metric">
          <span className="technician-performance__metric-icon technician-performance__metric-icon--violet">
            <MapPin size={20} aria-hidden="true" />
          </span>
          <span className="technician-performance__metric-label">
            Distance tracked
          </span>
          <strong>
            {data?.total_distance_km == null
              ? "—"
              : `${data.total_distance_km.toFixed(1)} km`}
          </strong>
          <span className="technician-performance__metric-caption">
            From recorded job GPS
          </span>
        </article>
      </div>

      <div className="technician-performance__charts">
        <article className="technician-performance__chart-card">
          <div className="technician-performance__chart-heading">
            <div>
              <h3>Completed jobs</h3>
              <p>{period === "week" ? "Daily this week" : "Weekly this month"}</p>
            </div>
            <span className="technician-performance__chart-icon">
              <BarChart3 size={18} aria-hidden="true" />
            </span>
          </div>
          {trend.length ? (
            <div
              className="technician-performance__bar-chart"
              role="img"
              aria-label={`Completed jobs trend for this ${period}`}
            >
              {trend.map((item) => (
                <div
                  className="technician-performance__bar-item"
                  key={item.label}
                  title={`${item.count} completed`}
                >
                  <span className="technician-performance__bar-count">
                    {item.count || ""}
                  </span>
                  <div className="technician-performance__bar-track">
                    <span
                      className="technician-performance__bar"
                      style={{
                        height: `${Math.max(
                          item.count > 0 ? 8 : 0,
                          (item.count / maxCompletions) * 100,
                        )}%`,
                      }}
                    />
                  </div>
                  <span className="technician-performance__bar-label">
                    {item.label}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="technician-performance__empty">
              No completion trend data available.
            </p>
          )}
        </article>

        <article className="technician-performance__chart-card">
          <div className="technician-performance__chart-heading">
            <div>
              <h3>Job status</h3>
              <p>Jobs assigned during this period</p>
            </div>
            <span className="technician-performance__chart-icon">
              <CheckCircle2 size={18} aria-hidden="true" />
            </span>
          </div>
          <div className="technician-performance__status-content">
            <div
              className={`technician-performance__donut${totalStatusJobs ? "" : " technician-performance__donut--empty"}`}
              style={
                totalStatusJobs
                  ? { background: `conic-gradient(${chartStops.join(", ")})` }
                  : undefined
              }
              role="img"
              aria-label={
                totalStatusJobs
                  ? `Job status distribution for ${totalStatusJobs} jobs`
                  : "No job status data available"
              }
            >
              <span>
                <strong>{totalStatusJobs}</strong>
                <small>jobs</small>
              </span>
            </div>
            <ul className="technician-performance__legend">
              {distribution.length ? (
                distribution.map((item) => (
                  <li key={item.status}>
                    <span
                      className="technician-performance__legend-dot"
                      style={{
                        background:
                          statusColors[item.status] ?? statusColors.other,
                      }}
                    />
                    <span>{statusLabels[item.status] ?? "Other"}</span>
                    <strong>{item.count}</strong>
                  </li>
                ))
              ) : (
                <li className="technician-performance__legend-empty">
                  No job status data available.
                </li>
              )}
            </ul>
          </div>
        </article>
      </div>
    </section>
  );
}
