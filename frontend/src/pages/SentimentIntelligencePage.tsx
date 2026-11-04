import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, FileText, Layers, RefreshCw, Search, Sparkles } from "lucide-react";
import api from "../services/api";
import useAuthStore from "../store/authStore";

type SentimentAnalysis = {
  id: number;
  job_id: number | null;
  source_type?: string | null;
  channel: string;
  message?: string | null;
  sentiment: string;
  emotion: string | null;
  urgency: string | null;
  severity: string | null;
  confidence: number;
  issue_categories: string[];
  requires_human: boolean;
  summary: string | null;
  recommended_action: string | null;
  created_at: string | null;
};

type SentimentAlert = {
  escalation_id: number;
  job_id: number | null;
  customer_name: string;
  sentiment_label: string;
  trigger_reason: string;
  suggested_action: string | null;
  status: string;
  sla_breach: string | null;
  created_at: string;
};

const palette: Record<string, { bg: string; fg: string }> = {
  NEGATIVE: { bg: "#FEE2E2", fg: "#991B1B" },
  MIXED: { bg: "#FEF3C7", fg: "#92400E" },
  POSITIVE: { bg: "#DCFCE7", fg: "#166534" },
  NEUTRAL: { bg: "#E5E7EB", fg: "#374151" },
};

export default function SentimentIntelligencePage() {
  const user = useAuthStore((state) => state.user);
  const [items, setItems] = useState<SentimentAnalysis[]>([]);
  const [alerts, setAlerts] = useState<SentimentAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("ALL");

  const load = useCallback(async () => {
    if (!user?.tenant_id) return;
    setLoading(true);
    setError("");
    try {
      const [response, dashboard] = await Promise.all([
        api.get("/admin/sentiment/dashboard/analyses", {
          params: { tenant_id: user.tenant_id, limit: 100 },
        }),
        api.get("/admin/sentiment/dashboard", {
          params: { tenant_id: user.tenant_id },
        }),
      ]);
      setItems(response.data?.items ?? []);
      setAlerts(dashboard.data?.alert_feed ?? []);
    } catch {
      setError("Sentiment activity could not be loaded. Check your access and try again.");
    } finally {
      setLoading(false);
    }
  }, [user?.tenant_id]);

  useEffect(() => { void load(); }, [load]);

  const visibleItems = filter === "ALL"
    ? items
    : items.filter((item) => filter === "REVIEW" ? item.requires_human : item.sentiment === filter);
  const reviewCount = items.filter((item) => item.requires_human).length;

  const sourceLabel = (item: SentimentAnalysis) => {
    if (item.source_type === "JOB_FEEDBACK") return "JOB FEEDBACK";
    if (item.source_type === "SUPPORT_CASE") return "SUPPORT REQUEST";
    if (item.source_type === "SUPPORT_CASE_UPDATE") return "SUPPORT REQUEST UPDATE";
    return item.channel.replaceAll("_", " ");
  };

  const subjectLabel = (item: SentimentAnalysis) => {
    if (item.job_id) return `Job #${item.job_id}`;
    if (item.source_type === "JOB_FEEDBACK") return "Customer feedback";
    if (item.source_type?.startsWith("SUPPORT_CASE")) return "Support request";
    if (item.channel === "SUPPORT_CHAT") return "Customer support conversation";
    if (item.channel === "SMS") return "Customer SMS";
    return "Customer message";
  };

  return (
    <main className="sentiment-intel-page">
      <style>{`
        .sentiment-intel-page{--si-ink:#172033;--si-muted:#63748b;--si-line:#dce5ec;--si-green:#14855e;min-height:100%;padding:26px;background:#f5f8fb;color:var(--si-ink);font-family:Inter,system-ui,sans-serif}
        .si-header{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;margin-bottom:24px}
        .si-eyebrow{display:flex;align-items:center;gap:9px;color:#168052;font-size:13px;font-weight:800;letter-spacing:.04em}
        .si-title{margin:8px 0 5px;font-size:30px;line-height:1.15;letter-spacing:-.03em;font-weight:750}
        .si-subtitle{margin:0;color:var(--si-muted);font-size:15px}
        .si-refresh{display:inline-flex;align-items:center;gap:9px;border:1px solid #cbd8e3;border-radius:10px;padding:11px 16px;background:#fff;color:#142236;font-weight:700;font-size:14px;cursor:pointer;box-shadow:0 1px 2px #0f172a0a}
        .si-refresh:hover{border-color:#80b9a0;background:#fbfefc}
        .si-metrics{display:grid;grid-template-columns:repeat(3,minmax(210px,1fr));gap:16px;margin-bottom:22px;max-width:1180px}
        .si-metric{display:flex;align-items:center;gap:16px;min-height:88px;padding:16px 19px;background:#fff;border:1px solid var(--si-line);border-radius:13px;box-shadow:0 2px 8px #0f172a08}
        .si-metric-review{border-color:#fecaca}
        .si-metric-icon{display:grid;place-items:center;flex:0 0 46px;height:46px;border-radius:13px;background:#e6f5ee;color:#168052}
        .si-metric-review .si-metric-icon{background:#fff0ef;color:#c92727}
        .si-metric-label{display:block;color:var(--si-muted);font-size:13px;font-weight:600}
        .si-metric-review .si-metric-label{color:#a91e1e}
        .si-metric-value{display:block;margin-top:4px;font-size:26px;line-height:1.1;font-weight:800;letter-spacing:-.02em}
        .si-metric-sources{font-size:16px;letter-spacing:0;white-space:nowrap}
        .si-panel{overflow:hidden;background:#fff;border:1px solid var(--si-line);border-radius:14px;box-shadow:0 3px 12px #0f172a08}
        .si-panel-head{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:17px 20px;background:linear-gradient(90deg,#f0f8f4,#f8fbfc);border-bottom:1px solid var(--si-line)}
        .si-panel-title{margin:0;font-size:20px;letter-spacing:-.02em}
        .si-filter{display:flex;align-items:center;gap:9px;color:#5f7287}
        .si-filter select{min-width:185px;padding:9px 12px;border:1px solid #cbd8e3;border-radius:9px;background:#fff;color:#25354a;font:inherit;font-size:14px;outline:none}
        .si-filter select:focus{border-color:#168052;box-shadow:0 0 0 3px #1680521c}
        .si-analysis-list{display:grid;gap:10px;padding:10px}
        .si-analysis-row{display:grid;grid-template-columns:minmax(190px,.9fr) minmax(320px,2.1fr) minmax(280px,1.35fr);gap:18px;align-items:stretch;padding:16px;border:1px solid #e4ebf0;border-radius:12px;background:#fff;box-shadow:0 1px 4px #0f172a08}
        .si-meta{padding-right:16px;border-right:1px solid #e5ebf0}
        .si-sentiment{display:inline-flex;padding:5px 10px;border-radius:99px;font-size:12px;font-weight:800;letter-spacing:.025em}
        .si-subject{margin-top:9px;font-size:16px;font-weight:800}
        .si-source{margin-top:5px;color:#65778d;font-size:12px;font-weight:650;letter-spacing:.025em}
        .si-time{margin-top:7px;color:#75859a;font-size:12px}
        .si-review-flag{display:flex;align-items:center;gap:6px;margin-top:9px;color:#bd2929;font-size:12px;font-weight:800}
        .si-content{min-width:0;padding:3px 0}
        .si-summary{font-size:15px;line-height:1.45;font-weight:750}
        .si-quote{margin:9px 0 0;padding:10px 13px;border-radius:10px;background:#f1f5f8;color:#52647a;font-size:13px;line-height:1.5;font-style:italic;overflow-wrap:anywhere}
        .si-issues{margin-top:9px;color:#60728a;font-size:13px;line-height:1.45}
        .si-issues strong{color:#35475e}
        .si-action{align-self:center;padding:14px 15px;border:1px solid #e6f0e9;border-radius:11px;background:#f3f8f5}
        .si-action-label{color:#13784f;font-size:12px;font-weight:850;letter-spacing:.055em;text-transform:uppercase}
        .si-action-text{margin:6px 0 11px;font-size:13px;line-height:1.5}
        .si-action-meta{display:flex;flex-wrap:wrap;gap:7px}
        .si-meta-pill{padding:5px 9px;border-radius:99px;background:#e2f3e9;color:#176b4b;font-size:11px;font-weight:750;white-space:nowrap}
        .si-meta-confidence{background:#e9eef3;color:#405168}
        .si-state{padding:28px 22px;color:var(--si-muted);font-size:14px}
        .si-state-error{color:#b42323}
        .si-escalations{margin-top:22px}
        .si-escalation-row{display:flex;justify-content:space-between;gap:16px;padding:16px 20px;border-bottom:1px solid #edf1f4;flex-wrap:wrap}
        .si-escalation-row:last-child{border-bottom:0}
        .si-disclaimer{margin:12px 2px 0;color:#718197;font-size:12px}
        @media(max-width:1100px){.sentiment-intel-page{padding:21px}.si-analysis-row{grid-template-columns:minmax(180px,.8fr) minmax(280px,1.5fr)}.si-meta{border-right:0;border-bottom:1px solid #e5ebf0;padding:0 0 12px}.si-action{grid-column:2;align-self:stretch}}
        @media(max-width:720px){.sentiment-intel-page{padding:15px}.si-header{display:block}.si-title{font-size:26px}.si-subtitle{font-size:14px;line-height:1.45}.si-refresh{margin-top:14px}.si-metrics{grid-template-columns:1fr;gap:10px}.si-metric{min-height:72px}.si-metric-sources{white-space:normal}.si-panel-head{align-items:flex-start;flex-direction:column;padding:15px}.si-panel-title{font-size:18px}.si-filter{width:100%}.si-filter select{flex:1}.si-analysis-list{padding:8px}.si-analysis-row{grid-template-columns:1fr;gap:12px;padding:14px}.si-meta{padding:0 0 11px}.si-action{grid-column:auto}.si-escalation-row{padding:15px}}
      `}</style>
      <header className="si-header">
        <div>
          <div className="si-eyebrow"><Sparkles size={18} /> CUSTOMER EXPERIENCE</div>
          <h1 className="si-title">Sentiment intelligence</h1>
          <p className="si-subtitle">Customer message and feedback tone, reported issues, and suggested staff follow-up.</p>
        </div>
        <button className="si-refresh" onClick={() => void load()}><RefreshCw size={17} /> Refresh</button>
      </header>

      <section className="si-metrics" aria-label="Sentiment summary">
        <div className="si-metric">
          <span className="si-metric-icon"><FileText size={22} /></span>
          <span><span className="si-metric-label">Recent analyses</span><strong className="si-metric-value">{items.length}</strong></span>
        </div>
        <div className="si-metric si-metric-review">
          <span className="si-metric-icon"><AlertTriangle size={22} /></span>
          <span><span className="si-metric-label">Needs human review</span><strong className="si-metric-value">{reviewCount}</strong></span>
        </div>
        <div className="si-metric">
          <span className="si-metric-icon"><Layers size={22} /></span>
          <span><span className="si-metric-label">Sources</span><strong className="si-metric-value si-metric-sources">Job chat · Support · Feedback · SMS</strong></span>
        </div>
      </section>

      <section className="si-panel">
        <div className="si-panel-head">
          <h2 className="si-panel-title">Customer sentiment activity</h2>
          <label className="si-filter"><Search size={17} /><select aria-label="Filter sentiment analyses" value={filter} onChange={(event) => setFilter(event.target.value)}>
            <option value="ALL">All messages</option><option value="REVIEW">Needs human review</option><option value="NEGATIVE">Negative</option><option value="MIXED">Mixed</option><option value="POSITIVE">Positive</option><option value="NEUTRAL">Neutral</option>
          </select></label>
        </div>
        {loading ? <p className="si-state">Loading sentiment activity…</p> : error ? <p role="alert" className="si-state si-state-error">{error}</p> : visibleItems.length === 0 ? <p className="si-state">No analyzed customer messages or feedback yet. New job chat, support chat, support requests, and written job feedback will appear here after background analysis completes.</p> : (
          <div className="si-analysis-list">
            {visibleItems.map((item) => {
              const colors = palette[item.sentiment] ?? palette.NEUTRAL;
              return <article className="si-analysis-row" key={item.id}>
                <div className="si-meta">
                  <span className="si-sentiment" style={{ background: colors.bg, color: colors.fg }}>{item.sentiment}</span>
                  <div className="si-subject">{subjectLabel(item)}</div>
                  <div className="si-source">{item.emotion || "Emotion not recorded"} · {sourceLabel(item)}</div>
                  <div className="si-time">{item.created_at ? new Date(item.created_at).toLocaleString() : ""}</div>
                  {item.requires_human && <div className="si-review-flag"><AlertTriangle size={15} /> Human review</div>}
                </div>
                <div className="si-content">
                  <div className="si-summary">{item.summary || "No summary provided."}</div>
                  {item.message && <blockquote className="si-quote">“{item.message}”</blockquote>}
                  <div className="si-issues"><strong>Issues:</strong> {item.issue_categories?.length ? item.issue_categories.map((label) => label.replaceAll("_", " ").toLowerCase()).join(", ") : "None identified"}</div>
                </div>
                <aside className="si-action">
                  <div className="si-action-label">Suggested staff action</div>
                  <p className="si-action-text">{item.recommended_action || "Review the message and use your judgment."}</p>
                  <div className="si-action-meta">
                    <span className="si-meta-pill">Urgency {item.urgency || "—"}</span>
                    <span className="si-meta-pill">Severity {item.severity || "—"}</span>
                    <span className="si-meta-pill si-meta-confidence">Confidence {Math.round(item.confidence * 100)}%</span>
                  </div>
                </aside>
              </article>;
            })}
          </div>
        )}
      </section>

      <section className="si-panel si-escalations">
        <div className="si-panel-head"><h2 className="si-panel-title">Open sentiment escalations</h2></div>
        {alerts.length === 0 ? <p className="si-state">No open sentiment escalations.</p> : alerts.map((alert) => <div className="si-escalation-row" key={alert.escalation_id}>
          <div><strong>{alert.customer_name}</strong><span style={{ color: "#63748b" }}> · {alert.job_id ? `Job #${alert.job_id}` : "Customer support conversation"}</span><div style={{ marginTop: 5, color: "#63748b", fontSize: 13 }}>{alert.trigger_reason.replaceAll("_", " ").toLowerCase()} · {new Date(alert.created_at).toLocaleString()}</div>{alert.suggested_action && <div style={{ marginTop: 8, color: "#334155", fontSize: 13 }}>Suggested action: {alert.suggested_action}</div>}</div>
          <div style={{ textAlign: "right" }}><strong style={{ color: alert.sla_breach ? "#B91C1C" : "#92400E" }}>{alert.sla_breach ? alert.sla_breach.replaceAll("_", " ") : alert.status}</strong><div style={{ color: "#63748b", fontSize: 12, marginTop: 4 }}>{alert.sentiment_label}</div></div>
        </div>)}
      </section>
      <p className="si-disclaimer">AI suggestions support staff review. They do not change job or support request status.</p>
    </main>
  );
}
