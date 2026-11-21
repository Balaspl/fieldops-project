import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, ClipboardCheck, RefreshCw, Wrench, XCircle } from "lucide-react";
import { getClosureAgentResults, type ClosureAgentResult } from "../services/planningService";

export default function ClosureAgentResultsPage() {
  const [results, setResults] = useState<ClosureAgentResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadResults = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setResults(await getClosureAgentResults());
    } catch (loadError: any) {
      setError(loadError?.response?.data?.detail || "Could not load closure recommendations.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadResults();
  }, [loadResults]);

  return (
    <div style={{ padding: "24px", maxWidth: 1400, margin: "0 auto", color: "#142238" }}>
      <header style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, marginBottom: 22 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ width: 48, height: 48, borderRadius: 14, background: "#DDF5E8", color: "#07884E", display: "grid", placeItems: "center" }}>
            <ClipboardCheck size={25} />
          </div>
          <div>
            <h1 style={{ margin: 0, fontSize: 25 }}>Closure Agent</h1>
            <p style={{ margin: "5px 0 0", color: "#64748B", fontSize: 14 }}>
              Technician completion notes and follow-up recommendations
            </p>
          </div>
        </div>
        <button type="button" onClick={() => void loadResults()} disabled={loading} style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "10px 14px", background: "#FFFFFF", border: "1px solid #DCE7E1", borderRadius: 9, color: "#315541", fontWeight: 700, cursor: loading ? "wait" : "pointer" }}>
          <RefreshCw size={16} /> Refresh
        </button>
      </header>

      {error && <div role="alert" style={{ padding: 14, marginBottom: 16, color: "#991B1B", background: "#FEF2F2", border: "1px solid #FECACA", borderRadius: 10 }}>{error}</div>}
      {loading && results.length === 0 ? (
        <div role="status" style={{ padding: 42, textAlign: "center", color: "#64748B", background: "#FFFFFF", border: "1px solid #E3ECE7", borderRadius: 14 }}>Loading closure results…</div>
      ) : results.length === 0 ? (
        <div style={{ padding: 50, textAlign: "center", color: "#64748B", background: "#FFFFFF", border: "1px solid #E3ECE7", borderRadius: 14 }}>
          <ClipboardCheck size={34} style={{ color: "#94A3B8", marginBottom: 10 }} />
          <h2 style={{ margin: "0 0 6px", fontSize: 18, color: "#334155" }}>No closure recommendations yet</h2>
          <p style={{ margin: 0, fontSize: 14 }}>Recommendations will appear here after a technician completes a job and submits payment.</p>
        </div>
      ) : (
        <div style={{ display: "grid", gap: 14 }}>
          {results.map((result) => {
            const needsFollowUp = result.follow_up_required;
            const tone = needsFollowUp
              ? { bg: "#FEF2F2", border: "#FCA5A5", text: "#B91C1C", label: "Follow-up Required", Icon: XCircle }
              : { bg: "#ECFDF5", border: "#86EFAC", text: "#047857", label: "Follow-up Not Required", Icon: CheckCircle2 };
            const StatusIcon = tone.Icon;

            return (
              <article key={result.closure_id} style={{ overflow: "hidden", background: "#FFFFFF", border: "1px solid #E3ECE7", borderRadius: 14, boxShadow: "0 2px 8px rgba(47, 79, 62, 0.05)" }}>
                <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: 10, padding: "14px 18px", borderBottom: "1px solid #E8EFEB" }}>
                  <div>
                    <strong style={{ fontSize: 16 }}>Job #{result.job_id}</strong>
                    <span style={{ marginLeft: 12, color: "#475569", fontSize: 14 }}>{result.customer_name || "Customer not listed"}</span>
                  </div>
                  <span style={{ color: "#64748B", fontSize: 12 }}>{result.completed_at ? new Date(result.completed_at).toLocaleString("en-GB", { day: "2-digit", month: "2-digit", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true }) : "Completion time unavailable"}</span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 12, padding: "14px 18px" }}>
                  <div style={{ display: "flex", alignItems: "flex-start", gap: 9 }}>
                    <Wrench size={16} style={{ flexShrink: 0, marginTop: 2, color: "#07884E" }} />
                    <div><div style={{ color: "#64748B", fontSize: 11, fontWeight: 700, textTransform: "uppercase" }}>Service</div><div style={{ marginTop: 4, fontSize: 13 }}>{result.service_type || "—"}</div></div>
                  </div>
                  <div><div style={{ color: "#64748B", fontSize: 11, fontWeight: 700, textTransform: "uppercase" }}>Technician</div><div style={{ marginTop: 4, fontSize: 13 }}>{result.technician_name || "—"}</div></div>
                  <div style={{ gridColumn: "1 / -1" }}><div style={{ color: "#64748B", fontSize: 11, fontWeight: 700, textTransform: "uppercase" }}>Technician Work Summary</div><div style={{ marginTop: 5, color: "#334155", fontSize: 13, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>{result.work_summary}</div></div>
                </div>
                <div style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "12px 18px", background: tone.bg, borderTop: `1px solid ${tone.border}`, color: tone.text }}>
                  <StatusIcon size={18} style={{ flexShrink: 0, marginTop: 1 }} />
                  <div><strong style={{ fontSize: 14 }}>{tone.label}</strong>{needsFollowUp && result.follow_up_reason && <div style={{ marginTop: 4, fontSize: 13, lineHeight: 1.5 }}>{result.follow_up_reason}</div>}</div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
