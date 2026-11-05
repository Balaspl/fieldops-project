import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  Activity,
  AlertCircle,
  CalendarDays,
  Check,
  ChevronDown,
  CircleDashed,
  Clock3,
  LockKeyhole,
  MapPin,
  MessageCircle,
  RefreshCw,
  Search,
  UserRound,
  Wrench,
  Workflow,
} from "lucide-react";
import {
  getAgentTracking,
  getAgentTrackingJob,
  type AgentTrackedJob,
  type AgentTrackingJobDetail,
  type AgentTrackingStage,
  type AgentTrackingResponse,
} from "../services/agentTrackingService";
import "./AgentTrackingPage.css";

type FilterKey = "all" | "active" | "waiting" | "complete";

const FILTERS: Array<{ key: FilterKey; label: string }> = [
  { key: "all", label: "All workflows" },
  { key: "active", label: "In progress" },
  { key: "waiting", label: "Awaiting acceptance" },
  { key: "complete", label: "Completed or cancelled" },
];

function formatTimestamp(value: string | null): string {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not recorded";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function isTerminal(job: AgentTrackedJob): boolean {
  return ["COMPLETED", "CLOSED", "CANCELLED", "CANCELED"].includes(
    job.status.toUpperCase(),
  );
}

function stageIcon(stage: AgentTrackingStage) {
  if (stage.state === "complete") return <Check size={15} />;
  if (stage.state === "active") return <Activity size={15} />;
  if (stage.state === "waiting") return <Clock3 size={15} />;
  if (stage.state === "locked") return <LockKeyhole size={14} />;
  return <CircleDashed size={15} />;
}

function stageStateLabel(state: AgentTrackingStage["state"]): string {
  switch (state) {
    case "complete": return "Complete";
    case "active": return "Active";
    case "waiting": return "Waiting";
    case "locked": return "After acceptance";
    case "event_driven": return "On event";
  }
}

function JobWorkflowCard({ job, onOpen }: { job: AgentTrackedJob; onOpen: () => void }) {
  const terminal = isTerminal(job);
  const visibleStages = job.accepted ? job.stages : job.stages.slice(0, 3);
  return (
    <article className="agent-track-card" role="button" tabIndex={0} onClick={onOpen} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onOpen(); } }} aria-label={`View job ${job.job_number} progress`}>
      <div className="agent-track-card-head">
        <div className="agent-track-job-heading">
          <span className="agent-track-job-id">JOB #{job.job_number}</span>
          <h2>{job.service_type || "Service job"}</h2>
          <span className="agent-track-job-meta">
            Updated {formatTimestamp(job.updated_at)}
          </span>
        </div>
        <div className="agent-track-job-badges">
          <span className={`agent-track-status ${terminal ? "is-terminal" : ""}`}>
            {job.status.replace(/_/g, " ")}
          </span>
          {job.priority ? <span className="agent-track-priority">{job.priority}</span> : null}
        </div>
      </div>

      <div className={`agent-track-current ${terminal ? "is-terminal" : job.accepted ? "is-working" : "is-waiting"}`}>
        <div className="agent-track-current-icon"><Workflow size={19} /></div>
        <div className="agent-track-current-copy">
          <span className="agent-track-eyebrow">CURRENT WORKFLOW STAGE</span>
          <strong>{job.current_agent}</strong>
          <span>{job.current_detail}</span>
        </div>
        <div className="agent-track-current-technician">
          <span>TECHNICIAN</span>
          <strong>{job.technician_name || "Not assigned"}</strong>
          <small>{job.accepted ? "Accepted" : job.assigned_at ? "Awaiting acceptance" : "Not assigned"}</small>
        </div>
      </div>

      <div className="agent-track-stages" role="list" aria-label={`Agent workflow for job ${job.job_number}`}>
        {visibleStages.map((stage, index) => (
          <div
            className={`agent-track-stage state-${stage.state}`}
            role="listitem"
            key={stage.key}
          >
            <div className="agent-track-stage-top">
              <span className="agent-track-stage-icon">{stageIcon(stage)}</span>
              {index < visibleStages.length - 1 ? <span className="agent-track-stage-connector" /> : null}
            </div>
            <strong>{stage.label}</strong>
            <span className="agent-track-stage-state">{stageStateLabel(stage.state)}</span>
            <p>{stage.detail}</p>
          </div>
        ))}
      </div>
      <div className="agent-track-open-hint">Open job progress <span>→</span></div>
    </article>
  );
}

function JobProgressDetail({
  job,
  detailed,
  onToggleDetail,
  onClose,
}: {
  job: AgentTrackingJobDetail;
  detailed: boolean;
  onToggleDetail: () => void;
  onClose: () => void;
}) {
  const terminal = isTerminal(job);
  const [expandedEvents, setExpandedEvents] = useState<number[]>([]);
  useEffect(() => {
    const firstCommunication = job.events.findIndex((event) => event.kind === "communication");
    setExpandedEvents(firstCommunication >= 0 ? [firstCommunication] : []);
  }, [job.job_id, job.events]);

  const toggleEvent = (index: number) => {
    setExpandedEvents((current) => current.includes(index)
      ? current.filter((value) => value !== index)
      : [...current, index]);
  };

  return (
      <section className="agent-track-detail" aria-labelledby="agent-track-detail-title">
        <header className="agent-track-detail-header">
          <button className="agent-track-back" onClick={onClose} aria-label="Back to job workflows"><ArrowLeft size={19} /></button>
          <div><h1 id="agent-track-detail-title">Job Progress</h1><p>See how the agents worked together on this job</p></div>
          <span className="agent-track-live"><i /> Live</span>
        </header>

        <div className="agent-track-detail-summary">
          <div className="agent-track-detail-summary-icon"><Wrench size={23} /></div>
          <div><span>Job ID</span><strong>JOB-{job.job_number}</strong></div>
          <div><UserRound size={21} /><span>Customer</span><strong>{job.customer_name || "Customer"}</strong></div>
          <div><Wrench size={21} /><span>Service</span><strong>{job.service_type || "Service"}</strong></div>
          <div><CalendarDays size={21} /><span>Preferred Visit</span><strong>{[job.preferred_service_date, job.preferred_service_time].filter(Boolean).join(", ") || "Not recorded"}</strong></div>
          <span className={`agent-track-detail-status ${terminal ? "is-terminal" : ""}`}>{job.status.replace(/_/g, " ")}</span>
        </div>
        {job.location ? <div className="agent-track-detail-location"><MapPin size={16} />{job.location}</div> : null}

        <div className="agent-track-progress-rail" role="list" aria-label="Job workflow stages">
          {job.stages.map((stage) => <div key={stage.key} className={`agent-track-progress-step state-${stage.state}`} role="listitem"><span className="agent-track-progress-icon">{stageIcon(stage)}</span><strong>{stage.label}</strong></div>)}
        </div>

        <section className="agent-track-event-panel">
          <div className="agent-track-event-panel-head">
            <h2>What Happened in This Job</h2>
            <div className="agent-track-log-toggle" role="group" aria-label="Event log detail level">
              <button className={!detailed ? "is-active" : ""} onClick={() => detailed && onToggleDetail()}>Simple View</button>
              <button className={detailed ? "is-active" : ""} onClick={() => !detailed && onToggleDetail()}>Detailed Log</button>
            </div>
          </div>
          {job.events.length ? <ol className="agent-track-event-list">
            {job.events.map((event, index) => (
              <li className={`agent-track-event kind-${event.kind} ${expandedEvents.includes(index) ? "is-expanded" : ""}`} key={`${event.kind}-${event.timestamp}-${index}`}>
                <button className="agent-track-event-trigger" onClick={() => toggleEvent(index)} aria-expanded={expandedEvents.includes(index)}>
                  <span className="agent-track-event-dot" />
                  <time>{formatTimestamp(event.timestamp)}</time>
                  <span className="agent-track-event-icon">{event.kind === "communication" ? <MessageCircle size={18} /> : event.kind === "work" ? <Activity size={18} /> : <CircleDashed size={18} />}</span>
                  <span className="agent-track-event-agent">{event.agent}</span>
                  <span className="agent-track-event-copy"><strong>{event.title}</strong>{!detailed ? <small>{event.detail}</small> : null}</span>
                  <span className="agent-track-event-state"><Check size={14} /> {event.kind === "communication" ? "Action Taken" : "Done"}</span>
                  <ChevronDown className={expandedEvents.includes(index) ? "is-open" : ""} size={17} />
                </button>
                {expandedEvents.includes(index) ? (
                  <div className="agent-track-event-expanded">
                    {event.kind === "communication" ? (
                      <>
                        <div className="agent-track-message-card"><MessageCircle size={18} /><strong>{event.sender_role ? `${event.sender_role.toLowerCase() === "customer" ? "Customer" : event.sender_role.toLowerCase() === "technician" ? "Technician" : event.sender_role} Message` : "Message"}</strong><p>{event.detail}</p></div>
                        <span className="agent-track-event-arrow">→</span>
                        <div className="agent-track-message-card mood-card"><Activity size={18} /><strong>Customer Mood</strong><p>{(event.message_id ? job.events.find((item) => item.kind === "sentiment" && item.source_message_id === event.message_id) : undefined)?.detail || "No sentiment analysis has been recorded for this message."}</p></div>
                        <span className="agent-track-event-arrow">→</span>
                        <div className="agent-track-message-card response-card"><MessageCircle size={18} /><strong>Agent Response</strong><p>{job.events.find((item) => item.kind === "communication" && item !== event && item.sender_role && ["assistant", "agent", "communication_agent"].includes(item.sender_role.toLowerCase()))?.detail || "No agent response message has been recorded for this event."}</p></div>
                      </>
                    ) : <div className="agent-track-event-detail"><strong>{event.agent} details</strong><p>{event.detail}</p></div>}
                  </div>
                ) : null}
              </li>
            ))}
          </ol> : <div className="agent-track-empty agent-track-no-events"><Workflow size={25} /><strong>No workflow events recorded yet</strong><span>Events will appear here as this job moves through its stages.</span></div>}
        </section>
      </section>
  );
}

export default function AgentTrackingPage() {
  const [data, setData] = useState<AgentTrackingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [search, setSearch] = useState("");
  const [selectedJob, setSelectedJob] = useState<AgentTrackingJobDetail | null>(null);
  const [detailError, setDetailError] = useState("");
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailedLog, setDetailedLog] = useState(false);

  const openJob = useCallback(async (job: AgentTrackedJob) => {
    setSelectedJob(null);
    setDetailError("");
    setDetailLoading(true);
    try {
      setSelectedJob(await getAgentTrackingJob(job.job_id));
    } catch (requestError) {
      const response = (requestError as { response?: { status?: number; data?: { detail?: string } } }).response;
      const status = response?.status;
      if (status === 404) {
        const detail = response?.data?.detail;
        setDetailError(detail === "Job not found."
          ? "This job is no longer available in your organization. Refresh the workflow list and try again."
          : "The running backend does not have the job detail route loaded. Restart it with the latest code, then try again.");
      } else if (status === 401) {
        setDetailError("Your session has expired. Sign in again to view this job's progress.");
      } else if (status === 403) {
        setDetailError("Your account does not have permission to view this job.");
      } else if (status && status >= 500) {
        setDetailError("The backend failed while loading this job's details. Check the backend logs for the API error.");
      } else {
        setDetailError("Could not connect to the job detail API. Check the backend connection and try again.");
      }
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const load = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);
    try {
      const result = await getAgentTracking();
      setData(result);
      setError("");
    } catch (requestError) {
      const status = (requestError as { response?: { status?: number } })
        .response?.status;
      if (status === 404) {
        setError("Agent Tracking API was not found. Restart the backend so it loads the Agent Tracking route.");
      } else if (status === 401) {
        setError("Your session has expired. Sign in again to load agent tracking.");
      } else if (status === 403) {
        setError("Your account does not have access to Agent Tracking.");
      } else if (status && status >= 500) {
        setError("The Agent Tracking API returned a server error. Check the backend logs for the request failure.");
      } else {
        setError("Agent tracking could not connect to the API. Check the backend connection and try again.");
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(true), 20_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const filteredJobs = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (data?.jobs ?? []).filter((job) => {
      const matchesFilter =
        filter === "all" ||
        (filter === "active" && !isTerminal(job)) ||
        (filter === "waiting" && job.current_agent === "Dispatcher") ||
        (filter === "complete" && isTerminal(job));
      const matchesSearch = !query || [
        String(job.job_number),
        job.service_type,
        job.status,
        job.technician_name ?? "",
        job.current_agent,
      ].some((value) => value.toLowerCase().includes(query));
      return matchesFilter && matchesSearch;
    });
  }, [data?.jobs, filter, search]);

  return (
    <main className="agent-tracking-page">
      {selectedJob ? (
        <JobProgressDetail job={selectedJob} detailed={detailedLog} onToggleDetail={() => setDetailedLog((value) => !value)} onClose={() => setSelectedJob(null)} />
      ) : detailLoading ? (
        <div className="agent-track-page-message"><span className="agent-track-loader" />Loading job progress…</div>
      ) : detailError ? (
        <div className="agent-track-page-message is-error"><AlertCircle size={20} />{detailError}<button onClick={() => setDetailError("")}>Back to workflows</button></div>
      ) : (
      <>
      <header className="agent-track-hero">
        <div className="agent-track-hero-mark"><Workflow size={24} /></div>
        <div>
          <div className="agent-track-kicker">OPERATIONS CONTROL</div>
          <h1>Agent Tracking</h1>
          <p>Follow each job from intake through dispatch, service, and closure.</p>
        </div>
        <button className="agent-track-refresh" onClick={() => void load(true)} disabled={refreshing}>
          <RefreshCw size={16} className={refreshing ? "is-spinning" : ""} />
          <span>{refreshing ? "Updating" : "Refresh"}</span>
        </button>
      </header>

      <section className="agent-track-summary" aria-label="Workflow totals">
        <div className="agent-track-summary-card">
          <span>Tracked jobs</span><strong>{data?.total ?? "—"}</strong>
          <small>Latest tracked jobs</small>
        </div>
        <div className="agent-track-summary-card summary-active">
          <span>In progress</span><strong>{data?.active ?? "—"}</strong>
          <small>Not yet completed or cancelled</small>
        </div>
        <div className="agent-track-summary-card summary-waiting">
          <span>Awaiting technician</span><strong>{data?.waiting_acceptance ?? "—"}</strong>
          <small>Dispatcher is waiting for acceptance</small>
        </div>
        <div className="agent-track-summary-card summary-live">
          <span>Auto refresh</span><strong>20s</strong>
          <small>Last sync {formatTimestamp(data?.generated_at ?? null)}</small>
        </div>
      </section>

      <section className="agent-track-board">
        <div className="agent-track-board-head">
          <div>
            <h2>Job workflows</h2>
            <p>Open any job to see its progress timeline and recorded agent activity. Communication and Sentiment appear after technician acceptance.</p>
          </div>
          <label className="agent-track-search">
            <Search size={17} />
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search job, service, technician" />
          </label>
        </div>

        <div className="agent-track-filters" role="tablist" aria-label="Filter workflows">
          {FILTERS.map((option) => (
            <button
              key={option.key}
              role="tab"
              aria-selected={filter === option.key}
              className={filter === option.key ? "is-selected" : ""}
              onClick={() => setFilter(option.key)}
            >
              {option.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="agent-track-message"><span className="agent-track-loader" />Loading job workflows…</div>
        ) : error ? (
          <div className="agent-track-message is-error"><AlertCircle size={20} />{error}<button onClick={() => void load()}>Try again</button></div>
        ) : filteredJobs.length ? (
          <div className="agent-track-list">
            {filteredJobs.map((job) => <JobWorkflowCard key={job.job_id} job={job} onOpen={() => void openJob(job)} />)}
          </div>
        ) : (
          <div className="agent-track-empty">
            <Workflow size={28} />
            <strong>No matching workflows</strong>
            <span>Try another filter or search term.</span>
          </div>
        )}
      </section>
      </>
      )}
    </main>
  );
}
