import { useCallback, useEffect, useState } from "react";
import { Eye, ExternalLink } from "lucide-react";
import type { PlanningJobFilterValues } from "./PlanningJobFilters";
import { getJobs } from "../../services/planningService";

interface CompletedJob {
  id: string | number;
  customer_name?: string;
  issue_description?: string;
  location?: string;
  priority?: string;
  service_type?: string;
  preferred_service_date?: string | null;
  completed_at?: string | null;
  status?: string;
}
interface CompletedJobsTableProps {
  onCountChange?: (count: number) => void;
  onViewJob?: (job: CompletedJob) => void;
  filters: PlanningJobFilterValues;
}
interface CompletedJobsTableProps {
  onCountChange?: (count: number) => void;
  onViewJob?: (job: CompletedJob) => void;
}

const PAGE_SIZE = 10;

const normalizeStatus = (status?: string) =>
  (status || "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

const getPriorityStyle = (priority?: string) => {
  const colors: Record<string, { bg: string; color: string }> = {
    CRITICAL: { bg: "#FEE2E2", color: "#991B1B" },
    HIGH: { bg: "#FEF3C7", color: "#92400E" },
    MEDIUM: { bg: "#FEF9C3", color: "#854D0E" },
    LOW: { bg: "#DCFCE7", color: "#166534" },
  };

  const theme = colors[(priority || "").toUpperCase()] || {
    bg: "#F3F4F6",
    color: "#4B5563",
  };

  return {
    background: theme.bg,
    color: theme.color,
    padding: "4px 9px",
    borderRadius: "20px",
    fontSize: "10px",
    fontWeight: 700,
    whiteSpace: "nowrap" as const,
  };
};

export default function CompletedJobsTable({
  onCountChange,
  onViewJob,
  filters,
}: CompletedJobsTableProps) {
  const [jobs, setJobs] = useState<CompletedJob[]>([]);
  const [page, setPage] = useState(1);
  const [totalJobs, setTotalJobs] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [expandedJobId, setExpandedJobId] = useState<string | null>(
    null,
  );

  const fetchCompletedJobs = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      if (
  filters.status !== "ALL" &&
  filters.status !== "COMPLETED"
) {
  setJobs([]);
  setTotalJobs(0);
  onCountChange?.(0);
  setLoading(false);
  return;
}
      const response = await getJobs({
  status: "COMPLETED",
  search: filters.search.trim() || undefined,
  location: filters.location.trim() || undefined,
  priority:
    filters.priority !== "ALL" ? filters.priority : undefined,
  service_type:
    filters.serviceType !== "ALL"
      ? filters.serviceType
      : undefined,
  sla: filters.sla !== "ALL" ? filters.sla : undefined,
  technician_id:
    filters.technician !== "ALL"
      ? Number(filters.technician)
      : undefined,
  page,
  limit: PAGE_SIZE,
});

      const rows: CompletedJob[] = Array.isArray(response?.data)
        ? response.data.filter(
            (job: CompletedJob) =>
              normalizeStatus(job.status) === "COMPLETED",
          )
        : [];

      const totalHeader =
        response?.headers?.["x-total-count"] ??
        response?.headers?.["X-Total-Count"];

      const parsedTotal = Number.parseInt(
        String(totalHeader ?? ""),
        10,
      );

      const total = Number.isFinite(parsedTotal)
        ? parsedTotal
        : rows.length;

      setJobs(rows);
      setTotalJobs(total);
      onCountChange?.(total);
    } catch (err) {
      console.error("Failed to load completed jobs:", err);
      setError("Unable to load completed jobs. Please try again.");
      setJobs([]);
      setTotalJobs(0);
      onCountChange?.(0);
    } finally {
      setLoading(false);
    }
  }, [page, onCountChange, filters]);
  useEffect(() => {
  setPage(1);
}, [filters]);

  useEffect(() => {
    void fetchCompletedJobs();

    const timer = window.setInterval(() => {
      void fetchCompletedJobs();
    }, 30000);

    return () => window.clearInterval(timer);
  }, [fetchCompletedJobs]);

  const totalPages = Math.max(
    1,
    Math.ceil(totalJobs / PAGE_SIZE),
  );

  return (
    <section
  style={{
    background: "#FFFFFF",
    border: "1px solid #E3ECE7",
    borderRadius: "12px",
    overflow: "hidden",
    fontFamily: "'Inter', sans-serif",

    display: "flex",
    flexDirection: "column",
    flex: 1,
    minHeight: "420px",
    height: "auto",
    boxSizing: "border-box",
  }}
>
      <div
        style={{
          padding: "14px 16px",
          borderBottom: "1px solid #E3ECE7",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "10px",
          flexShrink: 0,
        }}
      >
        <div>
          <h3 style={{ margin: 0, fontSize: "15px", color: "#1F2933" }}>
            Completed Jobs
          </h3>
          <p
            style={{
              margin: "4px 0 0",
              color: "#6B7280",
              fontSize: "11px",
            }}
          >
            Jobs completed by technicians
          </p>
        </div>

        <button
          type="button"
          onClick={() => void fetchCompletedJobs()}
          disabled={loading}
          style={{
            padding: "7px 12px",
            border: "1px solid #E3ECE7",
            borderRadius: "7px",
            background: "#FFFFFF",
            cursor: loading ? "wait" : "pointer",
            fontWeight: 600,
          }}
        >
          {loading ? "Loading..." : "Refresh"}
        </button>
      </div>

      {error && (
        <div
          role="alert"
          style={{ padding: "16px", color: "#B91C1C" }}
        >
          {error}
        </div>
      )}

      {!error && (
        <div
  style={{
    flex: 1,
    minHeight: 0,
    overflowY: "auto",
    overflowX: "auto",
  }}
>
    
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              minWidth: "900px",
            }}
          >
            <thead>
              <tr style={{ background: "#F6FAF8" }}>
                {[
                  "ID",
                  "Customer",
                  "Location",
                  "Priority",
                  "Service Type",
                  "Preferred Date",
                  "Status",
                  "Actions",
                ].map((heading) => (
                  <th
                    key={heading}
                    style={{
                      padding: "12px",
                      textAlign: "left",
                      fontSize: "10px",
                      color: "#6B7280",
                      borderBottom: "1px solid #E3ECE7",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>

            <tbody>
              {!loading && jobs.length === 0 && (
                <tr>
                  <td
                    colSpan={8}
                    style={{
                      padding: "30px",
                      textAlign: "center",
                      color: "#6B7280",
                    }}
                  >
                    No completed jobs found.
                  </td>
                </tr>
              )}

              {jobs.map((job) => {
                const jobId = String(job.id);
                const expanded = expandedJobId === jobId;

                return (
                  <>
                    <tr
                      key={jobId}
                      style={{ borderBottom: "1px solid #E3ECE7" }}
                    >
                      <td
                        style={{
                          padding: "12px",
                          color: "#5C9470",
                          fontWeight: 700,
                          fontSize: "11px",
                        }}
                      >
                        #{job.id}
                      </td>

                      <td
                        style={{
                          padding: "12px",
                          minWidth: "190px",
                        }}
                      >
                        <strong
                          style={{
                            display: "block",
                            color: "#2F4F3E",
                            fontSize: "12px",
                          }}
                        >
                          {job.customer_name || "Unknown customer"}
                        </strong>

                        <span
                          style={{
                            display: "block",
                            marginTop: "3px",
                            color: "#6B7280",
                            fontSize: "11px",
                          }}
                        >
                          {job.issue_description || "—"}
                        </span>
                      </td>

                      <td
                        style={{
                          padding: "12px",
                          fontSize: "11px",
                          minWidth: "170px",
                        }}
                      >
                        <span>{job.location || "—"}</span>

                        {job.location && (
                          <a
                            href={`https://maps.google.com/?q=${encodeURIComponent(
                              job.location,
                            )}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            title="Open location in Maps"
                            style={{
                              marginLeft: "6px",
                              color: "#94A3B8",
                            }}
                          >
                            <ExternalLink
                              size={12}
                              style={{ verticalAlign: "middle" }}
                            />
                          </a>
                        )}
                      </td>

                      <td style={{ padding: "12px" }}>
                        <span style={getPriorityStyle(job.priority)}>
                          {job.priority || "—"}
                        </span>
                      </td>

                      <td
                        style={{
                          padding: "12px",
                          fontSize: "11px",
                        }}
                      >
                        {job.service_type || "—"}
                      </td>

                      <td
                        style={{
                          padding: "12px",
                          fontSize: "11px",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {job.preferred_service_date
                          ? String(job.preferred_service_date).slice(
                              0,
                              10,
                            )
                          : "—"}
                      </td>

                      <td style={{ padding: "12px" }}>
                        <span
                          style={{
                            background: "#E5EDFF",
                            color: "#1D4ED8",
                            borderRadius: "20px",
                            padding: "5px 10px",
                            fontSize: "10px",
                            fontWeight: 700,
                          }}
                        >
                          Completed
                        </span>
                      </td>

                      <td style={{ padding: "12px" }}>
                        <button
                          type="button"
                          aria-label={`View job ${job.id} details`}
                          title="View job details"
                          onClick={() => {
  if (onViewJob) {
    onViewJob(job);
  } else {
    setExpandedJobId(
      expanded ? null : jobId,
    );
  }
}}
                          style={{
                            border: "none",
                            background: "transparent",
                            color: "#059669",
                            cursor: "pointer",
                            padding: "5px",
                          }}
                        >
                          <Eye size={16} />
                        </button>
                      </td>
                    </tr>

                    {expanded && (
                      <tr key={`${jobId}-details`}>
                        <td
                          colSpan={8}
                          style={{
                            padding: "12px 16px",
                            background: "#F8FBF9",
                            color: "#4B5563",
                            fontSize: "12px",
                          }}
                        >
                          <strong>Job #{job.id} details</strong>
                          <p>
                            Customer: {job.customer_name || "—"}
                          </p>
                          <p>
                            Issue: {job.issue_description || "—"}
                          </p>
                          <p>
                            Completed at:{" "}
                            {job.completed_at
                              ? new Date(
                                  job.completed_at,
                                ).toLocaleString()
                              : "Completion time not available"}
                          </p>
                        </td>
                      </tr>
                    )}
                  </>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div
        style={{
          padding: "10px 14px",
          borderTop: "1px solid #E3ECE7",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          fontSize: "11px",
          color: "#6B7280",
          flexShrink: 0,
        }}
      >
        <span>
          Page {page} of {totalPages} · {totalJobs} completed jobs
        </span>

        <div style={{ display: "flex", gap: "8px" }}>
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((current) => current - 1)}
          >
            ‹ Prev
          </button>

          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => setPage((current) => current + 1)}
          >
            Next ›
          </button>
        </div>
      </div>
    </section>
  );
}