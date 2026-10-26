import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { Bot, Cog, X, Minus, Send, RotateCw, MessageCircle, Headphones } from "lucide-react";
import {
  ChatMessage,
  createCustomerChatConversation,
  deleteCustomerChatConversation,
  downloadCustomerJobReport,
  getCustomerChatConversation,
  sendCustomerChatMessage,
} from "../../services/customerChatService";
import "./CustomerSupportWidget.css";

const suggestions = [
  "What is FieldOps used for?",
  "What services does FieldOps offer?",
  "How do I create a service request?",
  "How can I check my job status?",
  "When will my technician arrive?",
  "How do I track my technician?",
  "How do appointments work?",
  "Will I receive job notifications?",
  "What is a closure report?",
  "How do I contact support?",
];

function FieldOpsMascot() {
  return <svg className="fieldops-mascot" viewBox="0 0 64 64" role="img" aria-label="FieldOps support robot mascot">
    <defs>
      <linearGradient id="mascot-green" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#a8f0ce" /><stop offset="1" stopColor="#19a675" /></linearGradient>
      <linearGradient id="mascot-teal" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#31a895" /><stop offset="1" stopColor="#0c554b" /></linearGradient>
    </defs>
    <g className="fieldops-mascot-dance">
      <path d="M32 7v5" stroke="#c9fff4" strokeWidth="3" strokeLinecap="round" />
      <circle cx="32" cy="6" r="3" fill="#ffd36e" stroke="#fff" strokeWidth="1.5" />
      <g className="fieldops-mascot-left-arm"><path d="M19 34 12 41l2 7" fill="none" stroke="#55c594" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" /><circle cx="14" cy="49" r="4" fill="url(#mascot-green)" /></g>
      <g className="fieldops-mascot-wave"><path d="m45 34 7-7 1-8" fill="none" stroke="#55c594" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" /><circle cx="54" cy="16" r="4" fill="url(#mascot-green)" stroke="#b6f1d7" strokeWidth="1.5" /></g>
      <rect x="20" y="33" width="24" height="22" rx="8" fill="url(#mascot-green)" stroke="#d0ffe9" strokeWidth="1.5" />
      <rect x="24" y="37" width="16" height="14" rx="6" fill="url(#mascot-teal)" />
      <circle cx="32" cy="44" r="5.6" fill="#eafffa" />
      <Cog x="27.5" y="39.5" size={9} stroke="#147568" strokeWidth={2.4} />
      <g className="fieldops-mascot-feet"><path d="m26 54-2 4" stroke="#55c594" strokeWidth="5" strokeLinecap="round" /><path d="m38 54 2 4" stroke="#55c594" strokeWidth="5" strokeLinecap="round" /><ellipse cx="23" cy="59" rx="5" ry="2.5" fill="#49b985" /><ellipse cx="41" cy="59" rx="5" ry="2.5" fill="#49b985" /></g>
      <rect x="15" y="12" width="34" height="24" rx="10" fill="url(#mascot-green)" stroke="#d0ffe9" strokeWidth="1.5" />
      <path d="M20 24a12 12 0 0 1 24 0" fill="#c8f6df" />
      <rect x="21" y="20" width="22" height="10" rx="5" fill="#145b53" />
      <circle cx="27" cy="25" r="2" fill="#94fff0" /><circle cx="37" cy="25" r="2" fill="#94fff0" />
      <path d="M28 30q4 3 8 0" fill="none" stroke="#369b8a" strokeWidth="1.6" strokeLinecap="round" />
      <rect x="12" y="21" width="4" height="9" rx="2" fill="#66c8b6" /><rect x="48" y="21" width="4" height="9" rx="2" fill="#66c8b6" />
    </g>
  </svg>;
}

export default function CustomerSupportWidget({ customerId, onSupportClick, onServiceRequestsClick, onTrackingClick }: { customerId: string; onSupportClick?: () => void; onServiceRequestsClick?: () => void; onTrackingClick?: () => void }) {
  const [open, setOpen] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reportError, setReportError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const composeRef = useRef<HTMLTextAreaElement>(null);
  const retryMessageId = useRef<string | null>(null);
  const chatSessionRef = useRef(0);
  const conversationCreateRef = useRef<Promise<{ id: string }> | null>(null);
  const messageSendRef = useRef<Promise<{ conversation_id: string; answer: string; intent: string | null; escalation: boolean; components?: ChatMessage["components"]; follow_up_suggestions?: string[] }> | null>(null);

  useEffect(() => {
    let active = true;
    chatSessionRef.current += 1;
    const sessionId = chatSessionRef.current;
    const key = `fieldops-chat:${customerId}`;
    async function restore() {
      const saved = localStorage.getItem(key);
      if (saved) {
        try {
          const conversation = await getCustomerChatConversation(saved);
          if (active && sessionId === chatSessionRef.current) { setConversationId(conversation.id); setMessages(conversation.messages); }
          return;
        } catch { if (active && sessionId === chatSessionRef.current) localStorage.removeItem(key); }
      }
      // A cleared session starts fresh. Older server-side conversations are
      // intentionally not reopened unless this browser still has its ID.
    }
    void restore();
    return () => { active = false; chatSessionRef.current += 1; };
  }, [customerId]);

  useEffect(() => { if (open && !minimized) endRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" }); }, [messages, open, minimized, busy]);
  useEffect(() => { if (open && !minimized) composeRef.current?.focus(); }, [open, minimized]);

  async function submit(value = draft) {
    const content = value.trim();
    if (!content || busy) return;
    setError(""); setBusy(true); setDraft("");
    const now = new Date().toISOString();
    const localMessage: ChatMessage = { id: Date.now(), sender: "customer", content, created_at: now };
    retryMessageId.current ??= crypto.randomUUID();
    const clientMessageId = retryMessageId.current;
    const sessionId = chatSessionRef.current;
    let createPromise: Promise<{ id: string }> | null = null;
    let sendPromise: ReturnType<typeof sendCustomerChatMessage> | null = null;
    setMessages((items) => [...items, localMessage]);
    try {
      let id = conversationId;
      if (!id) {
        createPromise = createCustomerChatConversation();
        conversationCreateRef.current = createPromise;
        const created = await createPromise;
        if (conversationCreateRef.current === createPromise) conversationCreateRef.current = null;
        if (sessionId !== chatSessionRef.current) return;
        id = created.id;
        setConversationId(id);
        localStorage.setItem(`fieldops-chat:${customerId}`, id);
      }
      sendPromise = sendCustomerChatMessage(id, content, clientMessageId);
      messageSendRef.current = sendPromise;
      const result = await sendPromise;
      if (messageSendRef.current === sendPromise) messageSendRef.current = null;
      if (sessionId !== chatSessionRef.current) return;
      const response: ChatMessage = { id: Date.now() + 1, sender: "assistant", content: result.answer, created_at: new Date().toISOString(), intent: result.intent, components: result.components, follow_up_suggestions: result.follow_up_suggestions };
      setMessages((items) => [...items, response]);
      retryMessageId.current = null;
    } catch {
      if (sessionId !== chatSessionRef.current) return;
      setError("Your message couldnÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢t be sent. Please retry.");
      setDraft(content);
      setMessages((items) => items.filter((item) => item.id !== localMessage.id));
    } finally {
      if (createPromise && conversationCreateRef.current === createPromise) conversationCreateRef.current = null;
      if (sendPromise && messageSendRef.current === sendPromise) messageSendRef.current = null;
      if (sessionId === chatSessionRef.current) setBusy(false);
    }
  }

  function closeChat() {
    const key = `fieldops-chat:${customerId}`;
    let id = conversationId ?? localStorage.getItem(key);
    const createPromise = conversationCreateRef.current;
    const sendPromise = messageSendRef.current;
    chatSessionRef.current += 1;
    localStorage.removeItem(key);
    setConversationId(null); setMessages([]); setDraft(""); setError(""); setReportError("");
    setBusy(false); setMinimized(false); setOpen(false); retryMessageId.current = null;
    void (async () => {
      try { if (!id && createPromise) id = (await createPromise).id; } catch { /* No session was created. */ }
      try { if (sendPromise) id = (await sendPromise).conversation_id; } catch { /* The known session can still be removed. */ }
      if (id) { try { await deleteCustomerChatConversation(id); } catch { /* Local session is cleared even when offline. */ } }
    })();
  }

  async function downloadReport(jobId?: number | null) {
    if (!jobId) return;
    setReportError("");
    try { await downloadCustomerJobReport(jobId); }
    catch { setReportError("The completion report could not be downloaded. Please contact FieldOps Support."); }
  }

  function onSubmit(event: FormEvent) { event.preventDefault(); void submit(); }
  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void submit(); } }
  return <>
    {open && !minimized && <section className="customer-chat-panel" role="dialog" aria-modal="false" aria-labelledby="customer-chat-title">
      <header className="customer-chat-header">
        <div className="customer-chat-brand"><span className="customer-chat-mark"><Bot size={20} /></span><div><strong id="customer-chat-title">FieldOps Support</strong><small>Ask about your service requests</small></div></div>
        <div className="customer-chat-controls"><button type="button" aria-label="Minimize chat" onClick={() => setMinimized(true)}><Minus size={18} /></button><button type="button" aria-label="Close chat" onClick={closeChat}><X size={18} /></button></div>
      </header>
      <div className="customer-chat-messages" aria-live="polite">
        {!messages.length && <div className="customer-chat-welcome"><span className="customer-chat-mark"><Headphones size={22} /></span><h2>Hi, how can we help?</h2><p>Ask a question about FieldOps or your service requests.</p></div>}
        {messages.map((message) => <article className={`customer-chat-message ${message.sender}`} key={message.id}><p>{message.content}</p>{message.components?.map((component, index) => <div className="customer-chat-card" key={`${component.type}-${index}`}>
          <strong>{component.title}</strong>
          {component.type === "job_status" && <div className="customer-chat-card-details"><span>Status: {component.status ?? "Unavailable"}</span>{component.preferred_service_date && <span>Preferred date: {component.preferred_service_date}</span>}{component.arrival_estimate && <span>Estimated arrival: {component.arrival_estimate}</span>}{component.completed_at && <span>Completed: {component.completed_at}</span>}</div>}
          {component.type === "service_catalog" && <ul>{(component.items ?? []).map((item) => <li key={item}>{item}</li>)}</ul>}
          {component.action === "service_requests" && <button className="customer-chat-support-link" type="button" onClick={onServiceRequestsClick}>View service requests</button>}
          {component.action === "tracking" && <button className="customer-chat-support-link" type="button" onClick={onTrackingClick}>Open technician tracking</button>}
          {component.action === "download_report" && <button className="customer-chat-support-link" type="button" onClick={() => void downloadReport(component.job_id)}>Download completion report</button>}
          {component.action === "support" && <button className="customer-chat-support-link" type="button" onClick={onSupportClick}>Open Support page</button>}
        </div>)}{message.sender === "assistant" && !message.components?.some((component) => component.action === "support") && /support page/i.test(message.content) && <button className="customer-chat-support-link" type="button" onClick={onSupportClick}>Open Support page</button>}{message.sender === "assistant" && Boolean(message.follow_up_suggestions?.length) && <div className="customer-chat-followups" aria-label="Related questions">{message.follow_up_suggestions?.map((prompt) => <button key={prompt} type="button" disabled={busy} onClick={() => void submit(prompt)}>{prompt}</button>)}</div>}<time dateTime={message.created_at}>{new Date(message.created_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</time></article>)}
        {busy && <div className="customer-chat-loading" role="status"><span /> Finding the right informationÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦</div>}
        {error && <div className="customer-chat-error" role="alert">{error}<button type="button" disabled={busy} onClick={() => void submit(draft)}> <RotateCw size={14} /> Retry</button></div>}
        {reportError && <div className="customer-chat-error" role="alert">{reportError}<button type="button" onClick={onSupportClick}>Open Support page</button></div>}
        <div ref={endRef} />
      </div>
      <section className="customer-chat-suggestions" aria-label="Suggested questions">
        <h3>Suggested questions</h3>
        <div className="customer-chat-suggestion-list">{suggestions.map((prompt) => <button type="button" key={prompt} disabled={busy} onClick={() => void submit(prompt)}>{prompt}</button>)}</div>
      </section>
      <form className="customer-chat-compose" onSubmit={onSubmit}><textarea ref={composeRef} aria-label="Message FieldOps Support" placeholder="Write a message..." value={draft} maxLength={4000} onChange={(event) => setDraft(event.target.value)} onKeyDown={onKeyDown} disabled={busy} rows={1} /><button aria-label="Send message" type="submit" disabled={busy || !draft.trim()}><Send size={18} /></button></form>
      <footer className="customer-chat-footer">For booking changes, use the Support page.</footer>
    </section>}
    {open && minimized && <button className="customer-chat-reopen" type="button" onClick={() => setMinimized(false)} aria-label="Reopen support chat"><MessageCircle size={18} /> Support chat</button>}
    <button className="customer-chat-launcher" type="button" aria-label="Open FieldOps Support Chat" aria-expanded={open && !minimized} title="Chat with FieldOps Support" onClick={() => { setOpen(true); setMinimized(false); }}><FieldOpsMascot /><span className="customer-chat-tooltip">Chat with FieldOps Support</span></button>
  </>;
}
