import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bell,
  BellRing,
  CheckCircle2,
  Clock3,
  Mail,
  MessageSquareText,
  RefreshCw,
  Search,
  Send,
  Smartphone,
  TriangleAlert,
} from "lucide-react";
import type {
  CommunicationActivity,
  CommunicationCenterResponse,
} from "../services/communicationCenterService";
import { getCommunicationActivity } from "../services/communicationCenterService";
import "./CommunicationCenterPage.css";

const CHANNELS = [
  { value: "all", label: "All channels" },
  { value: "in_app", label: "In-app" },
  { value: "sms", label: "SMS" },
  { value: "email", label: "Email" },
  { value: "push", label: "Push" },
];

const MESSAGE_STATUSES = [
  { value: "all", label: "All delivery states" },
  { value: "unread", label: "Unread" },
  { value: "read", label: "Read" },
  { value: "pending", label: "Pending" },
  { value: "queued", label: "Queued" },
  { value: "sending", label: "Sending" },
  { value: "accepted", label: "Accepted by provider" },
  { value: "sent", label: "Sent" },
  { value: "delivered", label: "Delivered" },
  { value: "failed", label: "Failed" },
  { value: "permanent_failure", label: "Permanent failure" },
];

const IN_APP_STATUSES = [
  { value: "all", label: "All delivery states" },
  { value: "unread", label: "Unread" },
  { value: "read", label: "Read" },
];

const EXTERNAL_STATUSES = [
  { value: "all", label: "All delivery states" },
  { value: "pending", label: "Pending" },
  { value: "queued", label: "Queued" },
  { value: "sending", label: "Sending" },
  { value: "accepted", label: "Accepted by provider" },
  { value: "sent", label: "Sent" },
  { value: "delivered", label: "Delivered" },
  { value: "failed", label: "Failed" },
  { value: "permanent_failure", label: "Permanent failure" },
];

const channelIcon = (channel: string) => {
  if (channel === "sms") return <Smartphone size={14} />;
  if (channel === "email") return <Mail size={14} />;
  if (channel === "push") return <BellRing size={14} />;
  return <Bell size={14} />;
};

const pretty = (value: string) =>
  value.replace(/_/g, " ").replace(/\b\w/g, (letter: string) => letter.toUpperCase());

const formatDate = (value: string | null) => {
  if (!value) return "Time unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Time unavailable";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
};

function summaryIcon(status: string) {
  if (status === "delivered" || status === "accepted" || status === "sent" || status === "read") {
    return <CheckCircle2 size={14} />;
  }
  if (status === "failed" || status === "permanent_failure") return <TriangleAlert size={14} />;
  return <Clock3 size={14} />;
}

function DeliveryBadge({ delivery }: { delivery: CommunicationActivity["channels"][number] }) {
  const state = delivery.status.toLowerCase();
  return (
    <span className={`communication-center__delivery communication-center__delivery--${state}`}>
      {channelIcon(delivery.channel)}
      <span>{pretty(delivery.channel)}</span>
      <span className="communication-center__delivery-state">
        {summaryIcon(state)}
        {pretty(state)}
      </span>
      {delivery.attempts > 0 && (
        <span className="communication-center__attempts">
          {delivery.attempts} {delivery.attempts === 1 ? "attempt" : "attempts"}
        </span>
      )}
    </span>
  );
}

function ActivityCard({ item }: { item: CommunicationActivity }) {
  return (
    <article className="communication-center__message">
      <div className="communication-center__message-heading">
        <div className="communication-center__message-title-wrap">
          <span className="communication-center__message-icon"><Send size={16} /></span>
          <div>
            <h2>{item.title || pretty(item.type)}</h2>
            <p>
              {pretty(item.recipient_role)}
              {item.job_id ? ` · Job #${item.job_id}` : " · Service update"}
              {item.type ? ` · ${pretty(item.type)}` : ""}
            </p>
          </div>
        </div>
        <time>{formatDate(item.updated_at || item.created_at)}</time>
      </div>

      <p className="communication-center__message-body">
        {item.message || "This automatic update has no message body."}
      </p>

      <div className="communication-center__delivery-list" aria-label="Delivery status">
        {item.channels.map((delivery) => (
          <DeliveryBadge key={`${item.id}-${delivery.channel}`} delivery={delivery} />
        ))}
      </div>
    </article>
  );
}

export default function CommunicationCenterPage() {
  const [data, setData] = useState<CommunicationCenterResponse | null>(null);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [channel, setChannel] = useState("all");
  const [status, setStatus] = useState("all");
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  const load = useCallback(async (append = false, offset = 0) => {
    if (append) setLoadingMore(true);
    else setLoading(true);
    setError("");
    try {
      const result = await getCommunicationActivity({
        search: debouncedSearch || undefined,
        channel,
        status,
        limit: 50,
        offset: append ? offset : 0,
      });
      setData((previous) => append && previous
        ? { ...result, messages: [...previous.messages, ...result.messages] }
        : result);
    } catch {
      setError("Automatic message activity could not be loaded. Check your access and try again.");
      if (!append) setData(null);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [channel, debouncedSearch, status]);

  useEffect(() => {
    void load();
    const refreshTimer = window.setInterval(() => void load(), 30_000);
    return () => window.clearInterval(refreshTimer);
  }, [load]);

  const visibleCount = data?.messages.length ?? 0;
  const counts = data?.delivery_counts ?? {};
  const summary = useMemo(() => ([
    { label: "Automatic updates", value: data?.total ?? 0, tone: "green" },
    { label: "Loaded delivered / sent", value: (counts.delivered ?? 0) + (counts.sent ?? 0) + (counts.accepted ?? 0), tone: "blue" },
    { label: "Loaded waiting", value: (counts.pending ?? 0) + (counts.queued ?? 0) + (counts.sending ?? 0), tone: "amber" },
    { label: "Loaded failed", value: (counts.failed ?? 0) + (counts.permanent_failure ?? 0), tone: "red" },
  ]), [counts, data?.total]);

  return (
    <main className="communication-center">
      <header className="communication-center__header">
        <div>
          <p className="communication-center__eyebrow"><MessageSquareText size={16} /> AUTOMATED COMMUNICATIONS</p>
          <h1>Communication Center</h1>
          <p className="communication-center__subtitle">
            Follow automatic customer and technician updates across in-app, push, SMS, and email.
          </p>
        </div>
        <button className="communication-center__refresh" type="button" onClick={() => void load()} disabled={loading}>
          <RefreshCw size={16} className={loading ? "communication-center__spin" : ""} />
          Refresh
        </button>
      </header>

      <section className="communication-center__summary" aria-label="Message summary">
        {summary.map((item) => (
          <article key={item.label} className={`communication-center__summary-card communication-center__summary-card--${item.tone}`}>
            <span>{item.label}</span>
            <strong>{item.value}</strong>
          </article>
        ))}
      </section>

      <section className="communication-center__panel">
        <div className="communication-center__panel-heading">
          <div>
            <h2>Recent automatic messages</h2>
            <p>Messages are generated by FieldOps workflows and refreshed automatically every 30 seconds.</p>
          </div>
          <span className="communication-center__count">{data?.total ?? 0} messages</span>
        </div>

        <div className="communication-center__filters">
          <label className="communication-center__search">
            <Search size={17} />
            <input
              aria-label="Search automatic messages"
              placeholder="Search message, event, or job number"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <label>
            <span className="communication-center__sr-only">Channel</span>
            <select aria-label="Filter by channel" value={channel} onChange={(event) => {
              setChannel(event.target.value);
              setStatus("all");
            }}>
              {CHANNELS.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </label>
          <label>
            <span className="communication-center__sr-only">Delivery state</span>
            <select aria-label="Filter by delivery state" value={status} onChange={(event) => setStatus(event.target.value)}>
              {(channel === "in_app" ? IN_APP_STATUSES : channel === "sms" || channel === "email" || channel === "push" ? EXTERNAL_STATUSES : MESSAGE_STATUSES)
                .map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </label>
        </div>

        {error && <div className="communication-center__error" role="alert">{error}</div>}
        {loading ? (
          <div className="communication-center__state" role="status">Loading automatic message activity…</div>
        ) : data?.messages.length ? (
          <div className="communication-center__messages">
            {data.messages.map((item) => <ActivityCard key={item.id} item={item} />)}
          </div>
        ) : !error ? (
          <div className="communication-center__state">
            <span><MessageSquareText size={22} /></span>
            <strong>No automatic messages found</strong>
            <p>New service updates will appear here when FieldOps sends them.</p>
          </div>
        ) : null}

        {data && visibleCount < data.total && !loading && (
          <button className="communication-center__load-more" type="button" onClick={() => void load(true, visibleCount)} disabled={loadingMore}>
            {loadingMore ? "Loading…" : "Load more messages"}
          </button>
        )}
      </section>
    </main>
  );
}
