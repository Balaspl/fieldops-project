import { useEffect, useMemo, useState } from "react";
import {
  CalendarDays,
  CheckCircle,
  Clock3,
  Eye,
  History,
  MapPin,
  MessageSquare,
  Search,
  UserRound,
  XCircle,
} from "lucide-react";
import { getTechnicianJobHistory } from "../../services/technicianPortalService";
import JobMessagePanel from "../../components/customer-tracking/JobMessagePanel";

type HistoryJob = {
  id: number;
  status?: string | null;
  service_type?: string | null;
  location?: string | null;
  site_address?: string | null;
  customer_name?: string | null;
  assigned_at?: string | null;
  completed_at?: string | null;
  rejected_at?: string | null;
  rejection_reason?: string | null;
  issue_description?: string | null;
};

type HistoryStatusFilter = "completed" | "rejected";

function isRejectedJob(job: HistoryJob) {
  const status = String(job.status || "").toLowerCase();
  if (status === "completed" || status === "closed") return false;
  return Boolean(job.rejected_at || job.rejection_reason) || status.includes("rejected");
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  height: 48,
  boxSizing: "border-box",
  border: "1px solid #D7E0EC",
  borderRadius: 9,
  background: "#FFFFFF",
  color: "#425675",
  fontSize: 14,
  outlineColor: "#0A9874",
};

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "-"
    : date.toLocaleString([], { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatDuration(start?: string | null, end?: string | null) {
  if (!start || !end) return "Duration unavailable";
  const minutes = Math.max(0, Math.round((new Date(end).getTime() - new Date(start).getTime()) / 60000));
  if (!Number.isFinite(minutes)) return "Duration unavailable";
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return hours ? `${hours}h ${remainder}m` : `${remainder}m`;
}

export default function TechnicianJobHistoryPage() {
  const [jobs, setJobs] = useState<HistoryJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [messageJobId, setMessageJobId] = useState<number | null>(null);
  const [expandedJobId, setExpandedJobId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [dateRange, setDateRange] = useState("all");
  const [statusFilter, setStatusFilter] =
    useState<HistoryStatusFilter>("completed");

  useEffect(() => {
    getTechnicianJobHistory()
      .then((response) => setJobs(Array.isArray(response.data) ? response.data : []))
      .catch(() => setJobs([]))
      .finally(() => setLoading(false));
  }, []);

  const filteredJobs = useMemo(() => {
    const query = search.trim().toLowerCase();
    const cutoff = dateRange === "all" ? null : Date.now() - Number(dateRange) * 24 * 60 * 60 * 1000;
    return jobs.filter((job) => {
      const rejected = isRejectedJob(job);
      const status = String(job.status || "").toLowerCase();
      const date = new Date(
        rejected
          ? job.rejected_at || job.assigned_at || ""
          : job.completed_at || job.assigned_at || "",
      ).getTime();
      const matchesSearch = !query || [job.id, job.location, job.site_address, job.customer_name, job.service_type]
        .some((value) => String(value || "").toLowerCase().includes(query));
      return matchesSearch
        && (statusFilter === "rejected"
          ? rejected
          : !rejected && (status === "completed" || status === "closed"))
        && (!cutoff || (Number.isFinite(date) && date >= cutoff));
    });
  }, [jobs, search, dateRange, statusFilter]);
  const completedJobCount = jobs.filter((job) => {
    const status = String(job.status || "").toLowerCase();
    return !isRejectedJob(job) && (status === "completed" || status === "closed");
  }).length;
  const rejectedJobCount = jobs.filter(isRejectedJob).length;

  return (
    <div style={{ height: "100%", overflowY: "auto", boxSizing: "border-box", padding: "28px clamp(18px, 2.2vw, 38px)", background: "#F5F8FC", fontFamily: "'Inter', sans-serif", color: "#10213D" }}>
      <style>{`
        .tech-history-filters { display:grid; grid-template-columns:minmax(240px, 1.6fr) minmax(190px,.65fr) minmax(250px,1fr); gap:16px; }
        .tech-history-card { display:grid; grid-template-columns:minmax(0,1.7fr) minmax(190px,.72fr) minmax(145px,.55fr) 24px; gap:22px; align-items:center; }
        .tech-history-meta { border-left:2px solid #E0E7F0; padding-left:24px; display:grid; gap:12px; }
        .tech-history-status-toggle { display:grid; grid-template-columns:1fr 1fr; gap:4px; height:48px; padding:4px; box-sizing:border-box; border:1px solid #D7E0EC; border-radius:9px; background:#F8FAFC; }
        .tech-history-status-button { border:0; border-radius:6px; background:transparent; color:#52627E; font-size:14px; font-weight:600; cursor:pointer; }
        .tech-history-status-button[aria-pressed="true"] { background:#078C69; color:#FFFFFF; box-shadow:0 1px 3px rgba(15, 23, 42, .16); }
        @media (max-width:900px) { .tech-history-filters { grid-template-columns:1fr 1fr; } .tech-history-search { grid-column:1 / -1; } .tech-history-card { grid-template-columns:minmax(0,1fr) minmax(180px,.8fr); } .tech-history-actions { grid-column:2; grid-row:2; } .tech-history-meta { grid-column:1; grid-row:2; } .tech-history-chevron { display:none; } }
        @media (max-width:600px) { .tech-history-filters { grid-template-columns:1fr; } .tech-history-search { grid-column:auto; } .tech-history-card { grid-template-columns:1fr; gap:16px; } .tech-history-meta { grid-column:auto; grid-row:auto; border-left:0; border-top:1px solid #E0E7F0; padding:14px 0 0; } .tech-history-actions { grid-column:auto; grid-row:auto; display:flex; gap:10px; flex-wrap:wrap; } }
      `}</style>

      <header style={{ display: "flex", alignItems: "center", gap: 18, margin: "2px 0 26px" }}>
        <div style={{ width: 58, height: 58, borderRadius: "50%", background: "#078C69", color: "white", display: "grid", placeItems: "center", flexShrink: 0 }}><History size={33} /></div>
        <div>
          <h1 style={{ margin: 0, fontSize: 34, lineHeight: 1.15, fontWeight: 750, letterSpacing: "-.6px" }}>Job History</h1>
          <p style={{ margin: "5px 0 0", color: "#60718E", fontSize: 17 }}>View your completed and rejected jobs</p>
        </div>
      </header>

      <section className="tech-history-filters" aria-label="Filter job history" style={{ padding: 15, background: "#FFFFFF", border: "1px solid #E5EBF3", borderRadius: 13, boxShadow: "0 3px 12px rgba(25,54,91,.06)", marginBottom: 20 }}>
        <label className="tech-history-search" style={{ position: "relative" }}>
          <Search size={20} color="#405675" style={{ position: "absolute", left: 16, top: 14 }} />
          <input aria-label="Search job history" placeholder="Search by job ID, location or customer..." value={search} onChange={(event) => setSearch(event.target.value)} style={{ ...inputStyle, padding: "0 14px 0 54px" }} />
        </label>
        <div style={{ position: "relative" }}>
          <CalendarDays size={19} color="#405675" style={{ position: "absolute", left: 15, top: 14, pointerEvents: "none" }} />
          <select aria-label="Date range" value={dateRange} onChange={(event) => setDateRange(event.target.value)} style={{ ...inputStyle, appearance: "none", padding: "0 34px 0 48px" }}>
            <option value="all">Date Range</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option>
          </select>
          <span style={{ position: "absolute", right: 14, top: 15, pointerEvents: "none", color: "#334968" }}>v</span>
        </div>
        <div role="group" aria-label="Filter jobs by status" className="tech-history-status-toggle">
          <button
            type="button"
            className="tech-history-status-button"
            aria-pressed={statusFilter === "completed"}
            onClick={() => setStatusFilter("completed")}
          >
            Completed ({completedJobCount})
          </button>
          <button
            type="button"
            className="tech-history-status-button"
            aria-pressed={statusFilter === "rejected"}
            onClick={() => setStatusFilter("rejected")}
          >
            Rejected ({rejectedJobCount})
          </button>
        </div>
      </section>

      {loading ? <div style={{ textAlign: "center", padding: 56, color: "#71819A" }}>Loading job history...</div> : filteredJobs.length === 0 ? (
        <div style={{ textAlign: "center", padding: 56, color: "#71819A", background: "white", borderRadius: 14, border: "1px solid #E5EBF3" }}>{jobs.length ? "No jobs match these filters." : "No job history yet."}</div>
      ) : filteredJobs.map((job) => {
        const isRejected = isRejectedJob(job);
        const status = isRejected ? "REJECTED" : String(job.status || "COMPLETED").replaceAll("_", " ").toUpperCase();
        const eventDate = isRejected ? job.rejected_at : job.completed_at;
        const danger = isRejected || status === "CANCELLED";
        const expanded = expandedJobId === job.id;
        return (
          <article key={job.id} className="tech-history-card" style={{ background: "#FFFFFF", border: "1px solid #E7EDF5", borderRadius: 15, padding: "22px 24px", marginBottom: 16, boxShadow: "0 3px 12px rgba(25,54,91,.055)" }}>
            <div style={{ display: "flex", alignItems: "flex-start", gap: 22, minWidth: 0 }}>
              <div style={{ width: 68, height: 68, flexShrink: 0, borderRadius: 11, background: danger ? "#FDEBEC" : "#E2F5EF", color: danger ? "#C44048" : "#078C69", display: "grid", placeItems: "center" }}>{isRejected ? <XCircle size={31} /> : <CheckCircle size={31} />}</div>
              <div style={{ minWidth: 0 }}>
                <div style={{ color: "#72819A", fontWeight: 600, fontSize: 13, margin: "2px 0 5px" }}>JOB #{job.id}</div>
                <div style={{ color: "#10213D", fontWeight: 720, fontSize: 20, marginBottom: 10 }}>{job.service_type || "Service"}</div>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 10, color: "#60718E", fontSize: 13, lineHeight: 1.5 }}><MapPin size={16} style={{ flexShrink: 0, marginTop: 1 }} /><span>{job.site_address || job.location || "Location not provided"}</span></div>
                {job.customer_name && <div style={{ display: "flex", alignItems: "center", gap: 10, color: "#60718E", fontSize: 13, marginTop: 13 }}><UserRound size={16} />Customer: {job.customer_name}</div>}
                {isRejected && job.rejection_reason && <div style={{ color: "#A64047", fontSize: 13, marginTop: 9 }}>Reason: {job.rejection_reason}</div>}
              </div>
            </div>

            <div className="tech-history-meta">
              <div style={{ display: "flex", gap: 12, color: "#60718E", fontSize: 13, lineHeight: 1.4 }}><CalendarDays size={17} color="#233C5E" style={{ flexShrink: 0 }} /><div><div>Assigned</div><strong style={{ display: "block", color: "#4E6280", fontWeight: 500, marginTop: 3 }}>{formatDate(job.assigned_at)}</strong></div></div>
              <div style={{ display: "flex", gap: 12, color: "#60718E", fontSize: 13, lineHeight: 1.4 }}>{isRejected ? <XCircle size={17} color="#B9434B" style={{ flexShrink: 0 }} /> : <CheckCircle size={17} color="#233C5E" style={{ flexShrink: 0 }} />}<div>{isRejected ? "Rejected" : "Completed"}<strong style={{ display: "block", color: "#4E6280", fontWeight: 500, marginTop: 3 }}>{formatDate(eventDate)}</strong></div></div>
              <div style={{ display: "flex", gap: 12, color: "#60718E", fontSize: 13 }}><Clock3 size={17} color="#233C5E" /><div><div>Duration</div><strong style={{ display: "block", color: "#4E6280", fontWeight: 500, marginTop: 3 }}>{isRejected ? "Not started" : formatDuration(job.assigned_at, eventDate)}</strong></div></div>
            </div>

            <div className="tech-history-actions" style={{ display: "grid", justifyItems: "start", gap: 12 }}>
              <span style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8, borderRadius: 8, padding: "11px 16px", minWidth: 148, color: "white", background: danger ? "#C33F49" : "#078D6A", fontSize: 12, fontWeight: 750, boxShadow: "0 2px 5px rgba(0,0,0,.13)" }}>{isRejected ? <XCircle size={15} /> : <CheckCircle size={15} />}{status}</span>
              <button type="button" onClick={() => setExpandedJobId(expanded ? null : job.id)} style={{ height: 44, minWidth: 148, padding: "0 15px", border: "1px solid #0A9A76", borderRadius: 8, background: "white", color: "#078D6A", fontSize: 14, fontWeight: 650, display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 9, cursor: "pointer" }}><Eye size={18} />{expanded ? "Hide Details" : "View Details"}</button>
              <button type="button" onClick={() => setMessageJobId(job.id)} style={{ border: 0, background: "transparent", color: "#60718E", fontSize: 12, display: "inline-flex", alignItems: "center", gap: 7, cursor: "pointer" }}><MessageSquare size={15} />View Messages</button>
            </div>
            <span className="tech-history-chevron" style={{ fontSize: 25, color: "#10213D", textAlign: "right" }}>&gt;</span>
            {expanded && <div style={{ gridColumn: "1 / -1", borderTop: "1px solid #E5EBF3", paddingTop: 15, color: "#60718E", fontSize: 14 }}><strong style={{ color: "#10213D" }}>Job details</strong><p style={{ margin: "8px 0 0" }}>{job.issue_description || "No additional job description is available."}</p></div>}
          </article>
        );
      })}
      {messageJobId !== null && <JobMessagePanel jobId={messageJobId} onClose={() => setMessageJobId(null)} />}
    </div>
  );
}
