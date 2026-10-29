import { useCallback, useEffect, useState } from "react";
import { getJobs, getTechnicians } from "../../services/planningService";
import type { PlanningJobFilterValues } from "./PlanningJobFilters";
import { Eye } from "lucide-react";
const PAGE_SIZE = 10;

interface InProgressJob {
  id: string | number;
  customer_name?: string;
  issue_description?: string;
  location?: string;
  priority?: string;
  status?: string;
  assigned_technician_id?: string | number | null;
  assigned_technician_name?: string;
}

interface Technician {
  technician_id: string | number;
  technician_name: string;
}

interface Props {
  onCountChange?: (count: number) => void;
  onViewJob?: (job: InProgressJob) => void;
  filters: PlanningJobFilterValues;
}

const normalizeStatus = (status?: string) =>
  (status || "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

const priorityStyle = (priority?: string) => {
  const p = (priority || "").toUpperCase();

  const colors: Record<string, { bg: string; color: string }> = {
    CRITICAL: { bg: "#FEE2E2", color: "#991B1B" },
    HIGH: { bg: "#FEF3C7", color: "#92400E" },
    MEDIUM: { bg: "#FEF9C3", color: "#854D0E" },
    LOW: { bg: "#DCFCE7", color: "#166534" },
  };

  const theme = colors[p] || {
    bg: "#F3F4F6",
    color: "#4B5563",
  };

  return {
    background: theme.bg,
    color: theme.color,
    borderRadius: "20px",
    padding: "4px 9px",
    fontSize: "10px",
    fontWeight: 700,
    whiteSpace: "nowrap" as const,
  };
};

export default function InProgressJobsTable({
  onCountChange,
  onViewJob,
  filters,
}: Props) {
  const [jobs, setJobs] = useState<InProgressJob[]>([]);
  const [technicians, setTechnicians] = useState<Technician[]>([]);
  const [page, setPage] = useState(1);
  const [totalJobs, setTotalJobs] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const fetchJobs = useCallback(async () => {
    try {
      setError("");
            if (
  filters.status !== "ALL" &&
  filters.status !== "IN_PROGRESS"
) {
  setJobs([]);
  setTotalJobs(0);
  onCountChange?.(0);
  setLoading(false);
  return;
}

      const [jobResponse, technicianResponse] = await Promise.all([
        getJobs({
  status: "IN_PROGRESS",
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

      const rows: InProgressJob[] = Array.isArray(jobResponse?.data)
        ? jobResponse.data.filter(
            (job: InProgressJob) =>
              ["IN_PROGRESS", "ON_SITE"].includes(
                normalizeStatus(job.status),
              ),
          )
        : [];

      const techRows: Technician[] = Array.isArray(
        technicianResponse?.data,
      )
        ? technicianResponse.data
        : [];

      const totalHeader =
        jobResponse?.headers?.["x-total-count"] ??
        jobResponse?.headers?.["X-Total-Count"];

      const parsedTotal = Number.parseInt(
        String(totalHeader ?? ""),
        10,
      );

      const count = Number.isFinite(parsedTotal)
        ? Math.max(parsedTotal, rows.length)
        : rows.length;

      setJobs(rows);
      setTechnicians(techRows);
      setTotalJobs(count);
      onCountChange?.(count);
    } catch (err) {
      console.error("Failed to load in-progress jobs:", err);
      setError("Unable to load in-progress jobs. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [page, onCountChange, filters]);

  useEffect(() => {
    setLoading(true);
    void fetchJobs();

    const timer = window.setInterval(() => {
      void fetchJobs();
    }, 15000);

    return () => window.clearInterval(timer);
  }, [fetchJobs]);

  const totalPages = Math.max(
    1,
    Math.ceil(totalJobs / PAGE_SIZE),
  );

  return (
    <section
      style={{
        display: "flex",
        flexDirection: "column",
        flex: 1,
        minHeight: "420px",
        height: "auto",
        overflow: "hidden",
        background: "#FFFFFF",
        border: "1px solid #E3ECE7",
        borderRadius: "12px",
      }}
    >
      <div
        style={{
          padding: "12px 16px",
          borderBottom: "1px solid #E3ECE7",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexShrink: 0,
        }}
      >
        <div>
          <strong style={{ fontSize: "14px", color: "#1F2937" }}>
            In Progress Jobs
          </strong>
          <div style={{ fontSize: "11px", color: "#64748B", marginTop: 3 }}>
            Jobs where technicians have arrived and started work
          </div>
        </div>

        <button
          type="button"
          onClick={() => {
            setLoading(true);
            void fetchJobs();
          }}
          style={{
            padding: "7px 12px",
            border: "1px solid #E3ECE7",
            borderRadius: "7px",
            background: "#FFFFFF",
            color: "#2F4F3E",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Refresh
        </button>
      </div>

      <div
        style={{
          flex: 1,
          minHeight: 0,
          overflow: "auto",
        }}
      >
        <table
          style={{
            width: "100%",
            minWidth: "720px",
            borderCollapse: "collapse",
          }}
        >
          <thead>
            <tr style={{ background: "#F6FAF8" }}>
              {[
                "Job ID",
                "Customer",
                "Technician",
                "In Progress",
                "Priority",
                "Actions",
              ].map((heading) => (
                <th
                  key={heading}
                  style={{
                    padding: "12px",
                    borderBottom: "1px solid #E3ECE7",
                    textAlign: "left",
                    whiteSpace: "nowrap",
                    fontSize: "10px",
                    color: "#6B7280",
                  }}
                >
                  {heading}
                </th>
              ))}
            </tr>
          </thead>

          <tbody>
            {error && (
              <tr>
                <td
                  colSpan={6}
                  style={{
                    padding: "24px",
                    color: "#B91C1C",
                    textAlign: "center",
                  }}
                >
                  {error}
                </td>
              </tr>
            )}

            {!error && loading && jobs.length === 0 && (
              <tr>
                <td
                  colSpan={6}
                  style={{ padding: "24px", textAlign: "center" }}
                >
                  Loading in-progress jobs...
                </td>
              </tr>
            )}

            {!error && !loading && jobs.length === 0 && (
              <tr>
                <td
                  colSpan={6}
                  style={{
                    padding: "40px 20px",
                    textAlign: "center",
                    color: "#64748B",
                  }}
                >
                  No in-progress jobs found.
                </td>
              </tr>
            )}

            {jobs.map((job) => {
              const technician = technicians.find(
                (tech) =>
                  String(tech.technician_id) ===
                  String(job.assigned_technician_id),
              );

              return (
                <tr
                  key={job.id}
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

                  <td style={{ padding: "12px", minWidth: "180px" }}>
                    <strong
                      style={{ color: "#2F4F3E", fontSize: "12px" }}
                    >
                      {job.customer_name || "Unknown customer"}
                    </strong>

                    {job.issue_description && (
                      <div
                        style={{
                          marginTop: "4px",
                          color: "#6B7280",
                          fontSize: "11px",
                        }}
                      >
                        {job.issue_description}
                      </div>
                    )}
                  </td>

                  <td
                    style={{
                      padding: "12px",
                      fontSize: "12px",
                      fontWeight: 600,
                    }}
                  >
                    {technician?.technician_name ||
                      job.assigned_technician_name ||
                      "Technician not found"}
                  </td>

                  <td style={{ padding: "12px" }}>
                    <span
                      style={{
                        background: "#FFEDD5",
                        color: "#C2410C",
                        borderRadius: "20px",
                        padding: "5px 10px",
                        fontSize: "10px",
                        fontWeight: 700,
                        whiteSpace: "nowrap",
                      }}
                    >
                      IN PROGRESS
                    </span>
                  </td>

                  <td style={{ padding: "12px" }}>
                    <span style={priorityStyle(job.priority)}>
                      {job.priority || "—"}
                    </span>
                  </td>
                  <td style={{ padding: "12px", textAlign: "center" }}>
  <button
    type="button"
    title="View job details and status history"
    aria-label={`View job ${job.id} details`}
    onClick={(event) => {
      event.stopPropagation();
      onViewJob?.({
        ...job,
        status: job.status || "IN_PROGRESS",
      });
    }}
    style={{
      width: "32px",
      height: "32px",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      border: "1px solid #A7D9BF",
      borderRadius: "8px",
      background: "#FFFFFF",
      color: "#059669",
      cursor: "pointer",
    }}
  >
    <Eye size={16} />
  </button>
</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div
        style={{
          padding: "10px 14px",
          borderTop: "1px solid #E3ECE7",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexShrink: 0,
          fontSize: "11px",
          color: "#64748B",
        }}
      >
        <span>
          Page {page} of {totalPages} · {totalJobs} jobs
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