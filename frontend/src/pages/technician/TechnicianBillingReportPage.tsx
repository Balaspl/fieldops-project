import { useEffect, useState } from "react";
import { Download, FileText, RefreshCw } from "lucide-react";
import { getTechnicianBillingReports, downloadTechnicianBillingReport } from "../../services/technicianPortalService";

interface BillingReport {
  id: number; job_id: number; customer_name: string; service_type: string; location: string;
  work_summary: string; labour_cost: number; material_cost: number; subtotal: number;
  gst_rate: number; gst_amount: number; total_amount: number; completed_at: string;
}

const money = (value: number) => `₹${Number(value || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export default function TechnicianBillingReportPage() {
  const [reports, setReports] = useState<BillingReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadReports = async () => {
    setLoading(true); setError(null);
    try {
      const response = await getTechnicianBillingReports();
      setReports(response.data?.reports || []);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Failed to load billing reports.");
    } finally { setLoading(false); }
  };

  useEffect(() => { loadReports(); }, []);

  const handleDownload = async (report: BillingReport) => {
    setDownloading(report.id);
    try {
      const response = await downloadTechnicianBillingReport(report.id);
      const blob = new Blob([response.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = `billing_report_job_${report.job_id}.pdf`;
      document.body.appendChild(anchor); anchor.click(); anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      alert(err?.response?.data?.detail || "Failed to download billing report.");
    } finally { setDownloading(null); }
  };

  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <div><h2 style={styles.title}>Billing Reports</h2><p style={styles.subtitle}>Submitted billing details for your completed jobs</p></div>
        <button style={styles.refreshButton} onClick={loadReports} disabled={loading}><RefreshCw size={15} /> Refresh</button>
      </div>
      {error && <div style={styles.error}>{error}</div>}
      {loading ? <div style={styles.empty}>Loading billing reports...</div> : reports.length === 0 ? (
        <div style={styles.empty}><FileText size={36} color="#9CA3AF" /><div>No billing reports submitted yet.</div><span>Reports will appear here after you submit the billing form.</span></div>
      ) : (
        <div style={styles.list}>{reports.map((report) => (
          <div key={report.id} style={styles.card}>
            <div style={styles.cardHeader}>
              <div><div style={styles.reportId}>REPORT #{report.id}</div><div style={styles.jobTitle}>Job #{report.job_id} · {report.service_type}</div><div style={styles.customer}>{report.customer_name} · {report.location}</div></div>
              <div style={styles.completedBadge}>COMPLETED</div>
            </div>
            <div style={styles.summary}>{report.work_summary}</div>
            <div style={styles.costGrid}>
              <div style={styles.costItem}>
                <span>Service / Labour :</span>
                <strong>{money(report.labour_cost)}</strong>
              </div>
              <div style={styles.costItem}>
                <span>Material :</span>
                <strong>{money(report.material_cost)}</strong>
              </div>
              <div style={styles.costItem}>
                <span>Subtotal :</span>
                <strong>{money(report.subtotal)}</strong>
              </div>
              <div style={styles.costItem}>
                <span>GST ({report.gst_rate}%) :</span>
                <strong>{money(report.gst_amount)}</strong>
              </div>
              <div style={{ ...styles.costItem, ...styles.total }}>
                <span>Total :</span>
                <strong>{money(report.total_amount)}</strong>
              </div>
            </div>
            <div style={styles.footer}><span>Submitted: {new Date(report.completed_at).toLocaleString("en-IN")}</span><button style={styles.downloadButton} onClick={() => handleDownload(report)} disabled={downloading === report.id}><Download size={15} />{downloading === report.id ? "Preparing..." : "Download PDF"}</button></div>
          </div>
        ))}</div>
      )}
    </div>
  );
}

const styles = {
  page: { padding: "24px", height: "100%", overflowY: "auto" as const, background: "#EEF4F1", fontFamily: "'Inter', sans-serif" },
  header: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "22px", gap: "16px" },
  title: { margin: 0, fontSize: "22px", fontWeight: 700, color: "#1F2933" },
  subtitle: { margin: "5px 0 0", fontSize: "13px", color: "#6B7280" },
  refreshButton: { display: "inline-flex", alignItems: "center", gap: "6px", padding: "9px 14px", border: "1px solid #D1D5DB", borderRadius: "8px", background: "#fff", color: "#374151", fontWeight: 600, cursor: "pointer" },
  error: { background: "#FEE2E2", color: "#991B1B", border: "1px solid #FECACA", padding: "12px 14px", borderRadius: "10px", marginBottom: "14px" },
  empty: { minHeight: "260px", background: "#fff", border: "1px solid #E3ECE7", borderRadius: "14px", display: "flex", flexDirection: "column" as const, alignItems: "center", justifyContent: "center", gap: "8px", color: "#6B7280", fontSize: "14px" },
  list: { display: "grid", gap: "14px" },
  card: { background: "#fff", border: "1px solid #E3ECE7", borderRadius: "14px", padding: "20px", boxShadow: "0 2px 8px rgba(0,0,0,0.05)" },
  cardHeader: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "12px", marginBottom: "14px" },
  reportId: { fontSize: "10px", fontWeight: 700, color: "#9CA3AF", letterSpacing: "0.06em" },
  jobTitle: { marginTop: "4px", fontSize: "16px", fontWeight: 700, color: "#1F2933" },
  customer: { marginTop: "4px", fontSize: "12px", color: "#6B7280" },
  completedBadge: { background: "#D1FAE5", color: "#065F46", padding: "5px 10px", borderRadius: "20px", fontSize: "10px", fontWeight: 700 },
  summary: { background: "#F9FAFB", border: "1px solid #F3F4F6", borderRadius: "9px", padding: "11px 13px", fontSize: "13px", color: "#4B5563", lineHeight: 1.5, marginBottom: "14px" },
  costGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(5, minmax(150px, 1fr))",
    gap: "10px",
    overflowX: "auto" as const,
  },
  costItem: {
    minWidth: "150px",
    display: "flex",
    alignItems: "center",
    gap: "5px",
    whiteSpace: "nowrap" as const,
    fontSize: "15px",
    color: "#111827",
  },
  total: { background: "#ECFDF5", borderRadius: "9px", padding: "10px 12px" },
  footer: { marginTop: "16px", paddingTop: "14px", borderTop: "1px solid #F0F0F0", display: "flex", justifyContent: "space-between", alignItems: "center", gap: "12px", flexWrap: "wrap" as const, fontSize: "11px", color: "#9CA3AF" },
  downloadButton: { display: "inline-flex", alignItems: "center", gap: "6px", padding: "9px 14px", border: "none", borderRadius: "8px", background: "#166534", color: "#fff", fontSize: "12px", fontWeight: 700, cursor: "pointer" },
};
