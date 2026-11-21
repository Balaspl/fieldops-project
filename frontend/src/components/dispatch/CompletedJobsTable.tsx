import { useCallback, useEffect, useState } from "react";
import { Eye } from "lucide-react";
import type { PlanningJobFilterValues } from "./PlanningJobFilters";
import { getJobs, getTechnicians } from "../../services/planningService";

interface CompletedJob {
  id: string | number;
  customer_name?: string;
  technician_name?: string | null;
  issue_description?: string;
  assigned_technician_id?: string | number | null;
  location?: string;
  priority?: string;
  service_type?: string;
  preferred_service_date?: string | null;
  completed_at?: string | null;
  closed_at?: string | null;
  status?: string;
}
interface CompletedJobsTableProps {
  onCountChange?: (count: number) => void;
  onViewJob?: (job: CompletedJob) => void;
  filters: PlanningJobFilterValues;
}
interface Technician {
  technician_id: string | number;
  technician_name: string;
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
  const [technicians, setTechnicians] = useState<Technician[]>([]);
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
      const [response, technicianResponse] = await Promise.all([
        getJobs({
          status: "COMPLETED_OR_CLOSED",
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
        }),
        getTechnicians(),
      ]);

      const rows: CompletedJob[] = Array.isArray(response?.data)
        ? response.data.filter(
            (job: CompletedJob) =>
              ["COMPLETED", "CLOSED"].includes(normalizeStatus(job.status)),
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
      setTechnicians(
        Array.isArray(technicianResponse?.data)
          ? technicianResponse.data
          : [],
      );
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
    boxShadow: "0 1px 4px rgba(47, 79, 62, 0.07)",
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
              minWidth: "760px",
            }}
          >
            <thead>
              <tr style={{ background: "#F6FAF8" }}>
                {[
                  "Job ID",
                  "Customer Name",
                  "Service Name",
                  "Technician Name",
                  "Priority",
                  "Status",
                  "Action",
                ].map((heading) => (
                  <th
                    key={heading}
                    style={{
                      padding: "4px 8px",
                      textAlign: "left",
                      fontSize: "9.5px",
                      fontWeight: 700,
                      color: "#6B7280",
                      borderBottom: "1px solid #E3ECE7",
                      whiteSpace: "nowrap",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                    }}
                  >
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>

            <tbody>
              {error && (
                <tr><td colSpan={7} role="alert" style={{ padding: "8px", color: "#B91C1C", fontSize: "11.5px" }}>{error}</td></tr>
              )}
              {!error && loading && jobs.length === 0 && (
                <tr><td colSpan={7} style={{ padding: "8px", color: "#64748B", fontSize: "11.5px" }}>Loading jobs...</td></tr>
              )}
              {!error && !loading && jobs.length === 0 && (
                <tr>
                  <td
                    colSpan={7}
                    style={{
                      padding: "8px",
                      textAlign: "center",
                      color: "#6B7280",
                      fontSize: "11.5px",
                    }}
                  >
                    No completed jobs found.
                  </td>
                </tr>
              )}

              {jobs.map((job) => {
                const jobId = String(job.id);
                const expanded = expandedJobId === jobId;
                const technician = technicians.find(
                  (row) =>
                    String(row.technician_id) ===
                    String(job.assigned_technician_id),
                );

                return (
                  <>
                    <tr
                      key={jobId}
                      style={{ borderBottom: "1px solid #E3ECE7" }}
                    >
                      <td style={{ padding: "4px 8px", color: "#5C9470", fontWeight: 700, fontSize: "11.5px" }}>
                        #{job.id}
                      </td>

                      <td style={{ padding: "4px 8px", minWidth: "190px" }}>
                        <strong style={{ color: "#2F4F3E", fontSize: "11.5px" }}>
                          {job.customer_name || "Unknown customer"}
                        </strong>
                      </td>

                      <td style={{ padding: "4px 8px", fontSize: "11.5px" }}>
                        {job.service_type || "—"}
                      </td>

                      <td style={{ padding: "4px 8px", fontSize: "11.5px" }}>
                        {technician?.technician_name || "Not Assigned"}
                      </td>

                      <td style={{ padding: "4px 8px" }}>
                        <span style={getPriorityStyle(job.priority)}>
                          {job.priority || "—"}
                        </span>
                      </td>

                      <td style={{ padding: "4px 8px", fontSize: "11.5px" }}>
                        <span style={{ fontWeight: 600 }}>
                          {(job.status || "COMPLETED").replace(/[\s_-]+/g, " ").toUpperCase()}
                        </span>
                      </td>

                      <td style={{ padding: "4px 8px" }}>
                        <button
                          type="button"
                          className="icon-action-btn-style"
                          aria-label={`View job ${job.id} details`}
                          title="View job details"
                          onClick={() => {
                            if (onViewJob) {
                              onViewJob({
                                ...job,
                                technician_name: technician?.technician_name || null,
                              });
                            } else {
                              setExpandedJobId(expanded ? null : jobId);
                            }
                          }}
                        >
                          <Eye size={16} />
                        </button>
                      </td>
                    </tr>

                    {expanded && (
                      <tr key={`${jobId}-details`}>
                        <td
                          colSpan={7}
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
                            {job.completed_at || job.closed_at
                              ? new Date(
                                  job.completed_at || job.closed_at || "",
                                ).toLocaleString("en-GB", { day: "2-digit", month: "2-digit", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true })
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

      <div
        style={{
          padding: "8px",
          borderTop: "1px solid #E3ECE7",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          fontSize: "11.5px",
          color: "#6B7280",
          flexShrink: 0,
        }}
      >
        <span>
          Page {page} of {totalPages} · {totalJobs} results
        </span>

        <div style={{ display: "flex", gap: "8px" }}>
          <button
            type="button"
            className="planning-page-btn-style"
            disabled={page <= 1}
            onClick={() => setPage((current) => current - 1)}
          >
            ‹ Prev
          </button>

          <button
            type="button"
            className="planning-page-btn-style"
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
