import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { io, Socket } from "socket.io-client";
import { Check, CheckCheck, LoaderCircle, MessageSquare, Send, X } from "lucide-react";
import {
  acknowledgeJobMessageDelivered,
  getJobConversation,
  JobConversation,
  JobMessage,
  sendJobMessage,
} from "../../services/jobMessagingService";
import "./JobMessagePanel.css";

type Props = {
  jobId: number;
  initialTechnicianName?: string | null;
  token?: string;
  onClose: () => void;
};

const SOCKET_URL = (import.meta.env.VITE_SOCKET_URL || import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/+$/, "");

function statusLabel(message: JobMessage) {
  if (!message.is_mine) return "";
  if (message.read_at) return "Read";
  if (message.delivered_at) return "Delivered";
  return "Sent";
}

export default function JobMessagePanel({ jobId, initialTechnicianName, token, onClose }: Props) {
  const [conversation, setConversation] = useState<JobConversation | null>(null);
  const [messages, setMessages] = useState<JobMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const socketRef = useRef<Socket | null>(null);

  const refresh = useCallback(async () => {
    try {
      const { data } = await getJobConversation(jobId);
      setConversation(data);
      setMessages(data.messages);
      setError("");
      // GET returns persisted history and marks messages visible to this
      // authenticated participant as read. Acknowledge delivery separately.
      data.messages.filter((message) => !message.is_mine && !message.delivered_at).forEach((message) => {
        void acknowledgeJobMessageDelivered(jobId, message.id).catch(() => undefined);
      });
    } catch (requestError: any) {
      setError(requestError?.response?.status === 404
        ? "This conversation is not available for your account."
        : "Messages could not be loaded. Reconnect and try again.");
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    void refresh();
    let auth: { token?: string } = {};
    try {
      const authMode = localStorage.getItem("auth_mode");
      if (authMode !== "sso") {
        const localToken = token || localStorage.getItem("access_token") || localStorage.getItem("token");
        if (localToken) auth = { token: localToken };
      }
    } catch { /* HttpOnly SSO cookies are sent with credentials. */ }
    const socket = io(SOCKET_URL, { auth, withCredentials: true, reconnection: true, reconnectionAttempts: Infinity });
    socketRef.current = socket;
    socket.on("connect", () => void refresh());
    socket.on("job_message", (event: { job_id: number; message: JobMessage }) => {
      if (Number(event?.job_id) !== jobId || !event?.message?.id) return;
      const incoming = { ...event.message, is_mine: false };
      setMessages((items) => items.some((item) => item.id === incoming.id) ? items : [...items, incoming]);
      void acknowledgeJobMessageDelivered(jobId, incoming.id).catch(() => undefined);
      // Re-fetch so read timestamps and any messages missed while offline are authoritative.
      void refresh();
    });
    socket.on("job_message_delivered", (event: { job_id: number; message_id: string; delivered_at: string }) => {
      if (Number(event?.job_id) !== jobId) return;
      setMessages((items) => items.map((message) => message.id === event.message_id ? { ...message, delivered_at: event.delivered_at } : message));
    });
    socket.on("job_message_read", (event: { job_id: number; read_at: string }) => {
      if (Number(event?.job_id) !== jobId) return;
      setMessages((items) => items.map((message) => message.is_mine ? { ...message, read_at: event.read_at } : message));
    });
    const fallback = window.setInterval(() => { if (!socket.connected) void refresh(); }, 12000);
    return () => { window.clearInterval(fallback); socket.removeAllListeners(); socket.disconnect(); socketRef.current = null; };
  }, [jobId, refresh, token]);

  useEffect(() => { endRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" }); }, [messages]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const body = draft.trim();
    if (!body || sending || !conversation?.can_send) return;
    setSending(true); setError(""); setDraft("");
    try {
      const { data } = await sendJobMessage(jobId, body);
      setMessages((items) => items.some((message) => message.id === data.id) ? items : [...items, data]);
    } catch (sendError: any) {
      setDraft(body);
      setError(sendError?.response?.data?.detail || "Your message could not be sent. Please try again.");
    } finally { setSending(false); }
  }

  const title = conversation?.participant_name || initialTechnicianName || "Job conversation";
  return <div role="presentation" className="job-message-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className="job-message-panel" role="dialog" aria-modal="true" aria-labelledby="job-message-title">
      <header className="job-message-header"><div className="job-message-avatar"><MessageSquare size={19} /></div><div className="job-message-heading"><strong id="job-message-title">{title}</strong><span>{conversation?.job_reference || `JOB-${jobId}`} · {conversation?.status || "Loading status"}</span></div><button type="button" className="job-message-close" aria-label="Close messages" onClick={onClose}><X size={20} /></button></header>
      <div className="job-message-list" aria-live="polite">
        {loading && <div className="job-message-state"><LoaderCircle className="job-message-spinner" size={20} /> Loading conversation…</div>}
        {!loading && messages.length === 0 && <div className="job-message-state">Messages about this job will appear here.</div>}
        {messages.map((message) => <article className={`job-message-bubble ${message.is_mine ? "mine" : "theirs"}`} key={message.id}>
          <p>{message.body}</p><div className="job-message-meta"><time dateTime={message.created_at || undefined}>{message.created_at ? new Date(message.created_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : "Sending…"}</time>{message.is_mine && <span aria-label={statusLabel(message)} title={statusLabel(message)}>{message.read_at ? <CheckCheck size={13} /> : message.delivered_at ? <CheckCheck size={13} /> : <Check size={13} />} {statusLabel(message)}</span>}</div>
        </article>)}
        <div ref={endRef} />
      </div>
      {error && <p className="job-message-error" role="alert">{error}</p>}
      {conversation?.can_send ? <form className="job-message-compose" onSubmit={submit}><textarea aria-label="Write a message" placeholder="Write a message…" value={draft} maxLength={4000} rows={1} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} disabled={sending} /><button type="submit" aria-label="Send message" disabled={sending || !draft.trim()}>{sending ? <LoaderCircle className="job-message-spinner" size={19} /> : <Send size={18} />}</button></form>
        : <div className="job-message-readonly" role="status">{conversation?.read_only_reason || (conversation?.assigned ? "This conversation is read-only." : "Chat available after technician assignment.")}</div>}
    </section>
  </div>;
}
