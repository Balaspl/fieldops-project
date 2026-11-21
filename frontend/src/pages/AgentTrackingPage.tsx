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
  Mail,
  Bell,
  Smartphone,
  LockKeyhole,
  MapPin,
  Play,
  CircleCheck,
  CircleX,
  FileText,
  Send,
  Smile,
  MessageSquare,
  Bot,
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
import { getJobClosure } from "../services/planningService";
import "./AgentTrackingPage.css";

type FilterKey = "all" | "active" | "complete" | "failed";

const FILTERS: Array<{ key: FilterKey; label: string }> = [
  { key: "all", label: "All Jobs" },
  { key: "active", label: "Running" },
  { key: "complete", label: "Completed" },
  { key: "failed", label: "Failed" },
];

function isFailed(job: AgentTrackedJob): boolean { return ["FAILED", "CANCELLED", "CANCELED"].includes(job.status.toUpperCase()); }
function progressFor(job: AgentTrackedJob): number {
  if (isTerminal(job) && !isFailed(job)) return 100;
  const done = job.stages.filter((stage) => stage.state === "complete").length;
  const active = job.stages.some((stage) => stage.state === "active") ? 1 : 0;
  return Math.min(99, Math.round(((done + active * 0.45) / job.stages.length) * 100));
}

function formatTimestamp(value: string | null): string {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not recorded";
  return date.toLocaleString("en-GB", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

function isTerminal(job: AgentTrackedJob): boolean {
  return ["COMPLETED", "CLOSED", "CANCELLED", "CANCELED"].includes(
    job.status.toUpperCase(),
  );
}

function isJobCompleted(job: AgentTrackedJob): boolean {
  return ["COMPLETED", "CLOSED"].includes(job.status.trim().toUpperCase());
}

function workIsIncomplete(...values: unknown[]): boolean {
  const text = values.map((value) => String(value || "")).join(" ").toLowerCase();
  return [
    "not finished",
    "unfinished",
    "not completed",
    "not complete",
    "incomplete",
    "not done",
    "not resolved",
    "issue remains unresolved",
    "work remains",
    "needs further work",
    "need more work",
    "waiting for spare parts",
    "waiting for parts",
    "temporary repair",
    "additional visit required",
  ].some((signal) => text.includes(signal));
}

function normalizeClosureStage<T extends AgentTrackedJob>(job: T): T {
  const stages = (job.stages || []).filter((stage) => stage.key !== "closure");
  if (isJobCompleted(job)) {
    stages.push({
      key: "closure",
      label: "Close Job",
      state: job.status.trim().toUpperCase() === "CLOSED" ? "complete" : "active",
      detail: job.status.trim().toUpperCase() === "CLOSED"
        ? "Closure Agent recorded the final job closure."
        : "Closure requirements are ready for review.",
      timestamp: job.updated_at,
    });
  }
  return { ...job, stages };
}

function makeClosureEvent(
  job: AgentTrackingJobDetail,
  closureRecord: any,
  existingEvent?: AgentTrackingJobDetail["events"][number],
): AgentTrackingJobDetail["events"][number] {
  const workReport = closureRecord?.work_report ?? {};
  const closureAgent = workReport.closure_agent ?? existingEvent?.output?.closure_agent ?? null;
  const decision = closureAgent && typeof closureAgent === "object"
    ? closureAgent as Record<string, unknown>
    : null;
  const followUpReason = String(decision?.follow_up_reason || "").trim();
  const workSummary = closureRecord?.work_summary
    || workReport.summary
    || decision?.work_summary
    || existingEvent?.input?.work_summary;
  const workIncomplete = existingEvent?.output?.work_incomplete === true
    || workIsIncomplete(workSummary, followUpReason);
  const checklist = closureRecord?.checklist?.items ?? existingEvent?.input?.completion_checklist ?? [];
  const requiredItems: Array<Record<string, unknown>> = Array.isArray(checklist)
    ? checklist.filter((item: any) => item?.required === true)
    : [];
  if (workIncomplete && !requiredItems.some((item) => item.id === "closure-follow-up")) {
    requiredItems.push({
      id: "closure-follow-up",
      label: followUpReason || "Complete the unfinished work.",
      required: true,
      status: "REQUIRED",
    });
  }
  const requirementsMet = requiredItems.every(
    (item: any) => String(item.status || "").toUpperCase() === "COMPLETED",
  ) && !workIncomplete;
  const detail = workIncomplete
    ? followUpReason
      ? `Work is unfinished. Required follow-up: ${followUpReason}`
      : "Work is unfinished and must be completed before closure."
    : requiredItems.length
    ? requirementsMet
      ? "All required completion checklist items were completed."
      : "Some required completion checklist items need attention."
    : "No additional required checklist items were recorded for this job.";

  return {
    ...(existingEvent || {}),
    timestamp: closureRecord?.completed_at || existingEvent?.timestamp || job.updated_at,
    agent: "Closure Agent",
    title: "Closure requirements check",
    detail,
    kind: "closure",
    delivery_status: requirementsMet ? "passed" : "review",
    input: {
      ...(existingEvent?.input || {}),
      completion_checklist: checklist,
      work_summary: workSummary || null,
      after_image_count: closureRecord?.after_images?.length ?? existingEvent?.input?.after_image_count ?? 0,
    },
    output: {
      ...(existingEvent?.output || {}),
      requirements_met: requirementsMet,
      work_incomplete: workIncomplete,
      checklist_recorded: Boolean(closureRecord?.checklist || existingEvent?.output?.checklist_recorded),
      required_checklist_items: requiredItems,
      closure_agent: closureAgent,
    },
  };
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

function eventIcon(event: AgentTrackingJobDetail["events"][number]) {
  if (event.kind === "sentiment") return <Activity size={18} />;
  if (event.kind === "escalation") return <AlertCircle size={18} />;
  if (event.channel === "email") return <Mail size={18} />;
  if (event.channel === "push" || event.channel === "in_app") return <Bell size={18} />;
  if (event.channel === "sms") return <Smartphone size={18} />;
  if (event.kind === "communication") return <MessageCircle size={18} />;
  if (event.kind === "work") return <Activity size={18} />;
  return <CircleDashed size={18} />;
}

function eventStateLabel(event: AgentTrackingJobDetail["events"][number]) {
  if (event.delivery_status) return event.delivery_status.replace(/_/g, " ");
  return event.kind === "communication" ? "Chat" : "Recorded";
}

function JobWorkflowCard({ job, onOpen }: { job: AgentTrackedJob; onOpen: () => void }) {
  const terminal = isTerminal(job);
  const visibleStages = job.stages;
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
  const jobCompleted = job.stages.some((stage) => stage.key === "closure");
  const [expandedEvents, setExpandedEvents] = useState<number[]>([]);
  useEffect(() => {
    const firstCommunication = job.events.findIndex((event) =>
      ["communication", "notification", "delivery"].includes(event.kind),
    );
    setExpandedEvents(firstCommunication >= 0 ? [firstCommunication] : []);
  }, [job.job_id]);

  const toggleEvent = (index: number) => {
    setExpandedEvents((current) => current.includes(index)
      ? current.filter((value) => value !== index)
      : [...current, index]);
  };
  const toggleDetailedLog = () => {
    onToggleDetail();
    setExpandedEvents(detailed ? [] : job.events.map((_, index) => index));
  };
  const agentCards = [
    { name: "Intake Agent", icon: <FileText size={21}/>, active: true, running: false },
    { name: "Planning Agent", icon: <CalendarDays size={21}/>, active: Boolean(job.assigned_at), running: false },
    { name: "Dispatcher Agent", icon: <Send size={21}/>, active: Boolean(job.assigned_at), running: job.current_agent === "Dispatcher" },
    { name: "Communication Agent", icon: <MessageSquare size={21}/>, active: job.accepted, running: false },
    { name: "Sentiment Agent", icon: <Smile size={21}/>, active: job.events.some((event) => event.kind === "sentiment"), running: false },
    ...(jobCompleted ? [{ name: "Closure Agent", icon: <CircleCheck size={21}/>, active: true, running: job.status.toUpperCase() === "COMPLETED" }] : []),
  ];

  return (
      <section className="agent-track-detail-page" aria-labelledby="agent-track-detail-title">
        <header className="agent-track-detail-topbar"><div className="agent-track-topbar-mark"><Workflow size={29}/></div><div><h1 id="agent-track-detail-title">Agent Tracking</h1><p>Monitor AI agents, their executions, and outcomes in real time.</p></div><span className="agent-track-date"><CalendarDays size={17}/>Today, {new Date().toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}<ChevronDown size={15}/></span></header>
        <div className="agent-track-agent-strip" aria-label="Agent status overview">{agentCards.map((agent) => <div key={agent.name} className={`agent-track-agent-card ${agent.running ? "is-running" : ""}`}><span className="agent-track-agent-card-icon">{agent.icon}</span><span className="agent-track-agent-card-copy"><strong>{agent.name}</strong><small className={agent.active ? "is-active" : "is-idle"}><i/>{agent.running ? "Running" : agent.active ? "Active" : "Idle"}</small></span></div>)}</div>
        <div className="agent-track-detail-banner"><span className="agent-track-banner-chip"><Bot size={15}/> AI Agents</span><strong>Agent Tracking</strong><i/><p>Track and monitor all FieldOps AI agents in real time —<br/> from planning to communication and resolution.</p><span className="agent-track-banner-graphic"><img src="/ai-agent-chip.png" alt="AI processor with connected workflow icons" /></span></div>
        <div className="agent-track-detail">
        <header className="agent-track-detail-header">
          <button className="agent-track-back" onClick={onClose} aria-label="Back to job workflows"><ArrowLeft size={19} /></button>
          <div><h2>Job Progress</h2><p>See how the agents worked together on this job</p></div>
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

        <div className="agent-track-progress-rail" role="list" aria-label="Job workflow stages" style={{ gridTemplateColumns: `repeat(${job.stages.length}, minmax(100px, 1fr))` }}>
          {job.stages.map((stage) => <div key={stage.key} className={`agent-track-progress-step state-${stage.state}`} role="listitem"><span className="agent-track-progress-icon">{stageIcon(stage)}</span><strong>{({intake:"Request Received",planning:"Plan Job",dispatch:"Assign Technician",communication:"Communicate",technician_work:"Track Work",sentiment:"Check Customer Mood",closure:"Close Job"} as Record<string,string>)[stage.key] || stage.label}</strong></div>)}
        </div>

        <section className="agent-track-event-panel">
          <div className="agent-track-event-panel-head">
            <h2>What Happened in This Job</h2>
            <div className="agent-track-log-toggle" role="group" aria-label="Event log detail level">
              <button className={!detailed ? "is-active" : ""} onClick={() => detailed && toggleDetailedLog()}>Simple View</button>
              <button className={detailed ? "is-active" : ""} onClick={() => !detailed && toggleDetailedLog()}>Detailed Log</button>
            </div>
          </div>
          {job.events.length ? <ol className="agent-track-event-list">
            {job.events.map((event, index) => (
              <li className={`agent-track-event kind-${event.kind} ${expandedEvents.includes(index) ? "is-expanded" : ""}`} key={`${event.kind}-${event.timestamp}-${index}`}>
                <button className="agent-track-event-trigger" onClick={() => toggleEvent(index)} aria-expanded={expandedEvents.includes(index)}>
                  <span className="agent-track-event-dot" />
                  <time>{formatTimestamp(event.timestamp)}</time>
                  <span className="agent-track-event-icon">{eventIcon(event)}</span>
                  <span className="agent-track-event-agent">{event.agent}</span>
                  <span className="agent-track-event-copy"><strong>{event.title}</strong>{!detailed ? <small>{event.channel ? `${event.channel.replace(/_/g, " ")} · ` : ""}{event.detail}</small> : null}</span>
                  <span className={`agent-track-event-state status-${(event.delivery_status || "recorded").toLowerCase().replace(/[^a-z0-9_-]/g, "-")}`}>
                    {event.delivery_status === "failed" || event.delivery_status === "permanent_failure" || event.delivery_status === "review" ? <AlertCircle size={14} /> : <Check size={14} />}
                    {eventStateLabel(event)}
                  </span>
                  <ChevronDown className={expandedEvents.includes(index) ? "is-open" : ""} size={17} />
                </button>
                {expandedEvents.includes(index) ? (
                  <div className="agent-track-event-expanded">
                    {event.kind === "delivery" || event.kind === "notification" ? (
                      <div className="agent-track-event-detail agent-track-delivery-detail">
                        <strong>{event.agent} · {event.channel?.replace(/_/g, " ") || "notification"}</strong>
                        <p>{event.detail}</p>
                        <dl>
                          <div><dt>Delivery state</dt><dd>{eventStateLabel(event)}</dd></div>
                          <div><dt>Recipient</dt><dd>{event.recipient_name ? `${event.recipient_name} · ` : ""}{event.recipient_role || "Not recorded"}</dd></div>
                          {event.attempts != null ? <div><dt>Attempts</dt><dd>{event.attempts}</dd></div> : null}
                          {event.event_version != null ? <div><dt>Event version</dt><dd>{event.event_version}</dd></div> : null}
                          {event.smtp_status != null ? <div><dt>Mail server status</dt><dd>{event.smtp_status}</dd></div> : null}
                          {event.error ? <div className="is-error"><dt>Delivery detail</dt><dd>{event.error}</dd></div> : null}
                        </dl>
                      </div>
                    ) : event.kind === "communication" ? (
                      <>
                        <div className="agent-track-message-card"><MessageCircle size={18} /><strong>{event.sender_role ? `${event.sender_role.toLowerCase() === "customer" ? "Customer" : event.sender_role.toLowerCase() === "technician" ? "Technician" : event.sender_role} Message` : "Message"}</strong><p>{event.detail}</p></div>
                        <span className="agent-track-event-arrow">→</span>
                        <div className="agent-track-message-card mood-card"><Activity size={18} /><strong>Customer Mood</strong><p>{(event.message_id ? job.events.find((item) => item.kind === "sentiment" && item.source_message_id === event.message_id) : undefined)?.detail || "No sentiment analysis has been recorded for this message."}</p></div>
                      </>
                    ) : event.kind === "sentiment" ? (
                      <div className="agent-track-event-detail">
                        <strong>Sentiment analysis</strong>
                        <p>{event.detail}</p>
                        <dl>
                          <div><dt>Emotion</dt><dd>{event.emotion || "Not recorded"}</dd></div>
                          <div><dt>Urgency</dt><dd>{event.urgency || "Not recorded"}</dd></div>
                          <div><dt>Severity</dt><dd>{event.severity || "Not recorded"}</dd></div>
                          <div><dt>Issue type</dt><dd>{event.issue_categories?.length ? event.issue_categories.join(", ").replace(/_/g, " ") : "General"}</dd></div>
                          <div><dt>Confidence</dt><dd>{event.confidence == null ? "Not recorded" : `${Math.round(event.confidence * 100)}%`}</dd></div>
                          <div><dt>Analysis path</dt><dd>{event.analysis_source === "KEYWORD_FALLBACK" ? "Safe keyword fallback" : "AI analysis"}{event.language ? ` · ${event.language.toUpperCase()}` : ""}</dd></div>
                          <div><dt>Human review</dt><dd>{event.requires_human ? "Requested" : "Not required"}</dd></div>
                          {event.escalation_id != null ? <div><dt>Escalation</dt><dd>#{event.escalation_id} · {event.escalation_status || "Open"}{event.escalation_owner_id ? ` · Owner ${event.escalation_owner_id}` : " · Unassigned tenant queue"}</dd></div> : null}
                        </dl>
                      </div>
                    ) : event.kind === "closure" ? (() => {
                      const input = event.input || {};
                      const output = event.output || {};
                      const decision = output.closure_agent && typeof output.closure_agent === "object"
                        ? output.closure_agent as Record<string, unknown>
                        : null;
                      const checklist = Array.isArray(input.completion_checklist)
                        ? input.completion_checklist as Array<Record<string, unknown>>
                        : [];
                      const requirementsMet = output.requirements_met === true;
                      const checklistRecorded = output.checklist_recorded === true;
                      return (
                        <div className="agent-track-closure-detail">
                          <div className="agent-track-closure-summary">
                            <div className="agent-track-closure-mark"><CircleCheck size={34} /></div>
                            <div className="agent-track-closure-result">
                              <h3>Closure requirements check</h3>
                              <strong className={requirementsMet ? "is-passed" : "is-review"}>
                                {requirementsMet ? "Requirements met — ready to close" : "Requirements need attention"}
                              </strong>
                              <p>{event.detail}</p>
                              <span className={`agent-track-closure-badge ${requirementsMet ? "is-passed" : "is-review"}`}>
                                {requirementsMet ? "PASSED" : "REVIEW REQUIRED"}
                              </span>
                            </div>
                          </div>
                          <div className="agent-track-closure-checks">
                            <h4>{checklistRecorded ? "Required completion items" : "Completion requirements"}</h4>
                            {checklist.filter((item) => item.required === true).length ? checklist.filter((item) => item.required === true).map((item, itemIndex) => {
                              const complete = String(item.status || "").toUpperCase() === "COMPLETED";
                              return <div className={`agent-track-closure-check ${complete ? "is-complete" : "is-incomplete"}`} key={`${String(item.id || "item")}-${itemIndex}`}>
                                <span>{complete ? <Check size={14} /> : <AlertCircle size={14} />}</span>
                                <strong>{String(item.label || "Required item")}</strong>
                                <small>{complete ? "Completed" : "Incomplete"}</small>
                              </div>;
                            }) : <p className="agent-track-closure-no-items">{checklistRecorded ? "No additional required checklist items for this job." : "No additional checklist requirements were recorded."}</p>}
                          </div>
                          <dl className="agent-track-closure-facts">
                            <div><dt>Work summary</dt><dd>{String(input.work_summary || decision?.work_summary || "Not recorded")}</dd></div>
                            <div><dt>Evidence attached</dt><dd>{Number(input.after_image_count || 0)} completion photo{Number(input.after_image_count || 0) === 1 ? "" : "s"}</dd></div>
                            <div><dt>Follow-up</dt><dd>{decision ? decision.follow_up_required ? `Recommended${decision.follow_up_reason ? `: ${String(decision.follow_up_reason)}` : ""}` : "Not recommended" : "No Closure Agent decision recorded"}</dd></div>
                            {decision?.confidence != null ? <div><dt>Agent confidence</dt><dd>{Math.round(Number(decision.confidence) * 100)}%</dd></div> : null}
                            {output.closure_reason ? <div><dt>Closure note</dt><dd>{String(output.closure_reason)}</dd></div> : null}
                          </dl>
                        </div>
                      );
                    })() : event.kind === "escalation" ? (
                      <div className="agent-track-event-detail">
                        <strong>Escalation #{event.escalation_id ?? "—"}</strong>
                        <p>{event.detail}</p>
                        <dl>
                          <div><dt>Priority</dt><dd>{event.severity || "HIGH"}</dd></div>
                          <div><dt>Owner</dt><dd>{event.recipient_id || "Tenant escalation queue"}</dd></div>
                          <div><dt>Status</dt><dd>{eventStateLabel(event)}</dd></div>
                        </dl>
                      </div>
                    ) : <div className="agent-track-event-detail"><strong>{event.agent} details</strong><p>{event.detail}</p></div>}
                  </div>
                ) : null}
              </li>
            ))}
          </ol> : <div className="agent-track-empty agent-track-no-events"><Workflow size={25} /><strong>No workflow events recorded yet</strong><span>Events will appear here as this job moves through its stages.</span></div>}
        </section>
        </div>
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

  useEffect(() => {
    if (!selectedJob) return;
    let active = true;
    const refreshSelectedJob = async () => {
      try {
        const latest = await getAgentTrackingJob(selectedJob.job_id);
        if (active) setSelectedJob(latest);
      } catch {
        // Keep the last successful timeline visible during brief refresh failures.
      }
    };
    const timer = window.setInterval(() => void refreshSelectedJob(), 20_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [selectedJob?.job_id]);

  const openJob = useCallback(async (job: AgentTrackedJob) => {
    setSelectedJob(null);
    setDetailError("");
    setDetailLoading(true);
    try {
      const detail = normalizeClosureStage(await getAgentTrackingJob(job.job_id));
      if (isJobCompleted(detail)) {
        let closureRecord: any = null;
        try {
          closureRecord = await getJobClosure(detail.job_id);
        } catch {
          // Older or partially migrated jobs can be completed without a closure record.
        }
        const existingClosureEvent = detail.events.find((event) => event.kind === "closure");
        detail.events = [
          ...detail.events.filter((event) => event.kind !== "closure"),
          makeClosureEvent(detail, closureRecord, existingClosureEvent),
        ];
      } else {
        detail.events = detail.events.filter((event) => event.kind !== "closure");
      }
      setSelectedJob(detail);
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
      setData({
        ...result,
        jobs: result.jobs.map(normalizeClosureStage),
      });
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
        (filter === "active" && !isTerminal(job) && !isFailed(job)) ||
        (filter === "complete" && isTerminal(job) && !isFailed(job)) ||
        (filter === "failed" && isFailed(job));
      const matchesSearch = !query || [
        String(job.job_number),
        job.service_type,
        job.status,
        job.technician_name ?? "",
        job.customer_name ?? "",
        job.location ?? "",
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
          <h1>Agent Tracking</h1>
          <p>Track AI agent execution for all jobs and view real-time progress.</p>
        </div>
        <div className="agent-track-date"><CalendarDays size={17}/>Today, {new Date().toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</div>
        <button className="agent-track-refresh" onClick={() => void load(true)} disabled={refreshing} aria-label="Refresh tracking"><RefreshCw size={17} className={refreshing ? "is-spinning" : ""} /></button>
      </header>

      <section className="agent-track-board">
        <div className="agent-track-board-head">
          <div>
            <h2>Job workflows</h2>
            <p>Open any job to see its agent stages, recipient chats, notifications, emails, and delivery results.</p>
          </div>
        </div>
        <div className="agent-track-toolbar">
        <div className="agent-track-filters" role="tablist" aria-label="Filter jobs">
          {FILTERS.map((option) => <button key={option.key} role="tab" aria-selected={filter === option.key} className={filter === option.key ? "is-selected" : ""} onClick={() => setFilter(option.key)}>
            {option.key === "all" ? <Workflow size={19}/> : option.key === "active" ? <Play size={19}/> : option.key === "complete" ? <CircleCheck size={19}/> : <CircleX size={19}/>}{option.label}{option.key === "all" ? ` (${data?.total ?? 0})` : option.key === "active" ? ` (${(data?.jobs ?? []).filter((job) => !isTerminal(job) && !isFailed(job)).length})` : option.key === "complete" ? ` (${(data?.jobs ?? []).filter((job) => isTerminal(job) && !isFailed(job)).length})` : ` (${(data?.jobs ?? []).filter(isFailed).length})`}
          </button>)}
        </div>
          <label className="agent-track-search">
            <Search size={17} />
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search by Job ID, customer, or location..." />
          </label>
        </div>

        {loading ? (
          <div className="agent-track-message"><span className="agent-track-loader" />Loading job workflows…</div>
        ) : error ? (
          <div className="agent-track-message is-error"><AlertCircle size={20} />{error}<button onClick={() => void load()}>Try again</button></div>
        ) : filteredJobs.length ? (
          <div className="agent-track-table-wrap"><table className="agent-track-table"><thead><tr><th>Job ID</th><th>Customer</th><th>Job Type</th><th>Agent Pipeline</th><th>Progress</th><th>Status</th><th>Last Update</th><th>Action</th></tr></thead><tbody>
            {filteredJobs.map((job) => { const progress = progressFor(job); return <tr key={job.job_id}>
              <td><strong className="agent-track-table-id">#{job.job_number}</strong></td>
              <td><div className="agent-track-customer"><span className="agent-track-customer-avatar"><UserRound size={17}/></span><span><strong>{job.customer_name || "Customer"}</strong><small>{job.location || "Location not recorded"}</small></span></div></td>
              <td><span className="agent-track-service"><Wrench size={14}/><span>{job.service_type || "Service"}</span></span></td>
              <td><div className="agent-track-pipeline">{job.stages.filter((stage) => stage.key !== "technician_work").slice(0, 6).map((stage, index, stages) => <div className={`agent-track-pipeline-step state-${stage.state}`} key={stage.key}><span>{stageIcon(stage)}</span><small>{({intake:"Intake",planning:"Planning",dispatch:"Dispatcher",communication:"Comm.",sentiment:"Sentiment",closure:"Closure"} as Record<string,string>)[stage.key] || stage.label}</small>{index < stages.length - 1 ? <i/> : null}</div>)}</div></td>
              <td><div className="agent-track-progress"><strong>{progress}%</strong><span><i style={{width: `${progress}%`}}/></span></div></td>
              <td><span className={`agent-track-table-status ${isFailed(job) ? "failed" : isTerminal(job) ? "completed" : "running"}`}>{isFailed(job) ? "Failed" : isTerminal(job) ? "Completed" : "Running"}</span></td>
              <td className="agent-track-update">{formatTimestamp(job.updated_at)}</td><td><button className="agent-track-view" onClick={() => void openJob(job)}>View Tracking <span>→</span></button></td>
            </tr>; })}
          </tbody></table></div>
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
