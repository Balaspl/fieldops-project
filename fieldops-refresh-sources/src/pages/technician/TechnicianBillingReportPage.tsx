import { useEffect, useMemo, useState } from "react";
import {
  CalendarDays,
  CheckCircle,
  ChevronDown,
  Clock3,
  Download,
  Filter,
  FileText,
  IndianRupee,
  List,
  LayoutGrid,
  Search,
  RefreshCw,
  UserRound,
} from "lucide-react";

import api from "../../services/api";
import { getTechnicianBillingReports } from "../../services/technicianPortalService";
import { getCustomerSignature } from "../../services/planningService";

interface BillingReport {
  id: number;
  job_id: number;
  customer_name: string;
  service_type: string;
  location: string;
  work_summary: string;
  labour_cost: number;
  material_cost: number;
  subtotal: number;
  gst_rate: number;
  gst_amount: number;
  total_amount: number;
  completed_at: string;
}

interface CustomerSignatureState {
  data: string | null;
  loading: boolean;
  error: string | null;
}

const money = (value: number) =>
  `₹${Number(value || 0).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

const filterLabel: React.CSSProperties = { minHeight: 48, boxSizing: "border-box", display: "flex", alignItems: "center", gap: 12, padding: "6px 12px", border: "1px solid #DCE5EF", borderRadius: 9, color: "#315174", background: "white", fontSize: 11 };
const filterSelect: React.CSSProperties = { display: "block", border: 0, outline: 0, background: "transparent", color: "#17375D", fontSize: 13, fontWeight: 650, minWidth: 0 };
const viewButton = (active: boolean): React.CSSProperties => ({ width: 32, height: 30, display: "grid", placeItems: "center", border: "1px solid #DCE5EF", borderRadius: 6, background: active ? "#078D6A" : "white", color: active ? "white" : "#45617F", cursor: "pointer" });

export default function TechnicianBillingReportPage() {
  const [reports, setReports] = useState<BillingReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [visibleSignatureReportId, setVisibleSignatureReportId] =
    useState<number | null>(null);
  const [signatureState, setSignatureState] = useState<
    Record<number, CustomerSignatureState>
  >({});
  const [search, setSearch] = useState("");
  const [dateRange, setDateRange] = useState("30");
  const [customerFilter, setCustomerFilter] = useState("all");
  const [sortOrder, setSortOrder] = useState("newest");
  const [viewMode, setViewMode] = useState<"list" | "grid">("list");

  const loadReports = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await getTechnicianBillingReports();

      setReports(response.data?.reports || []);
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ||
          "Failed to load billing reports."
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadReports();
  }, []);

  const customers = useMemo(
    () => Array.from(new Set(reports.map((report) => report.customer_name).filter(Boolean))).sort(),
    [reports],
  );
  const visibleReports = useMemo(() => {
    const query = search.trim().toLowerCase();
    const cutoff = dateRange === "all" ? null : Date.now() - Number(dateRange) * 86400000;
    return reports
      .filter((report) => {
        const reportDate = new Date(report.completed_at || "").getTime();
        const matchesSearch = !query || [report.job_id, report.id, report.customer_name, report.location, report.service_type]
          .some((value) => String(value ?? "").toLowerCase().includes(query));
        return matchesSearch
          && (customerFilter === "all" || report.customer_name === customerFilter)
          && (!cutoff || (Number.isFinite(reportDate) && reportDate >= cutoff));
      })
      .sort((a, b) => {
        const delta = new Date(a.completed_at || "").getTime() - new Date(b.completed_at || "").getTime();
        return sortOrder === "oldest" ? delta : -delta;
      });
  }, [reports, search, dateRange, customerFilter, sortOrder]);
  const reportTotals = useMemo(() => visibleReports.reduce((totals, report) => ({
    jobs: totals.jobs + 1,
    amount: totals.amount + Number(report.total_amount || 0),
    labour: totals.labour + Number(report.labour_cost || 0),
    materials: totals.materials + Number(report.material_cost || 0),
  }), { jobs: 0, amount: 0, labour: 0, materials: 0 }), [visibleReports]);

  const handleToggleSignature = async (report: BillingReport) => {
    const current = signatureState[report.id];

    if (visibleSignatureReportId === report.id) {
      setVisibleSignatureReportId(null);
      return;
    }

    setVisibleSignatureReportId(report.id);

    if (current?.data || current?.loading || current?.error) {
      return;
    }

    setSignatureState((prev) => ({
      ...prev,
      [report.id]: {
        data: null,
        loading: true,
        error: null,
      },
    }));

    try {
      const response = await getCustomerSignature(report.job_id);

      setSignatureState((prev) => ({
        ...prev,
        [report.id]: {
          data: response.signature_data,
          loading: false,
          error: null,
        },
      }));
    } catch (err: any) {
      const status = err?.response?.status;

      setSignatureState((prev) => ({
        ...prev,
        [report.id]: {
          data: null,
          loading: false,
          error:
            status === 404
              ? "Customer signature is not available for this job."
              : status === 403
                ? "You are not authorized to view this customer signature."
                : "Failed to load the customer signature.",
        },
      }));
    }
  };

  const handleDownload = async (report: BillingReport) => {
    if (downloading !== null) {
      return;
    }

    setDownloading(report.id);
    setError(null);

    try {
      const response = await api.get(
        `/api/technician/billing-reports/${report.id}/pdf`,
        {
          responseType: "blob",
          validateStatus: () => true,
        }
      );

      /*
       * Axios returns a Blob even when the backend returns an
       * error because responseType is "blob".
       * Therefore check the HTTP status before downloading.
       */
      if (response.status < 200 || response.status >= 300) {
        let message = "Failed to download billing report.";

        try {
          const errorText = await response.data.text();

          if (errorText) {
            const parsed = JSON.parse(errorText);

            message =
              parsed?.detail ||
              message;
          }
        } catch {
          // Keep the generic message when the error body is not JSON.
        }

        if (response.status === 403) {
          message =
            "You are not authorized to download this billing report.";
        } else if (response.status === 404) {
          message =
            "Billing report PDF was not found.";
        }

        throw new Error(message);
      }

      const blob =
        response.data instanceof Blob
          ? response.data
          : new Blob(
              [response.data],
              {
                type: "application/pdf",
              }
            );

      if (blob.size === 0) {
        throw new Error(
          "Billing report PDF is empty."
        );
      }

      /*
       * Create a temporary browser URL for the PDF.
       */
      const url =
        window.URL.createObjectURL(blob);

      /*
       * Create a real download link.
       */
      const anchor =
        document.createElement("a");

      anchor.href = url;
      anchor.download =
        `billing_report_job_${report.job_id}.pdf`;

      anchor.style.display = "none";

      document.body.appendChild(anchor);

      /*
       * Trigger the browser download.
       */
      anchor.click();

      document.body.removeChild(anchor);

      /*
       * Give the browser enough time to consume
       * the Blob before releasing the object URL.
       */
      window.setTimeout(() => {
        window.URL.revokeObjectURL(url);
      }, 5000);
    } catch (err: any) {
      console.error(
        "Billing report download failed:",
        err
      );

      setError(
        err?.message ||
          "Failed to download billing report. Please try again."
      );
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div style={{ ...styles.page, background: "#F4F8FC", padding: "20px clamp(16px, 1.8vw, 30px)" }}>
      <style>{`
        .billing-filter-grid { display:grid; grid-template-columns:repeat(3,minmax(150px,.8fr)) minmax(220px,1.2fr); gap:12px; }
        .billing-stats { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:14px; margin:14px 0; }
        .billing-report-card { display:grid; grid-template-columns:minmax(0,1.35fr) minmax(230px,.75fr); gap:12px 18px; }
        @media(max-width:900px) { .billing-filter-grid { grid-template-columns:repeat(2,minmax(0,1fr)); } .billing-stats { grid-template-columns:repeat(2,minmax(0,1fr)); } .billing-report-card { grid-template-columns:1fr; } }
        @media(max-width:600px) { .billing-filter-grid,.billing-stats { grid-template-columns:1fr; } }
      `}</style>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, padding: "22px 24px", borderRadius: 14, background: "linear-gradient(105deg,#E7F7F2,#F3FAFD)", border: "1px solid #E1EFEF", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 18 }}><div style={{ width: 62, height: 62, borderRadius: 15, background: "#078D6A", display: "grid", placeItems: "center", color: "white" }}><FileText size={33} /></div><div><h1 style={{ margin: 0, color: "#122846", fontSize: 28, fontWeight: 750 }}>Billing Reports</h1><p style={{ margin: "6px 0 0", color: "#64748B", fontSize: 14 }}>View and download detailed billing reports for your completed jobs.</p></div></div>
        <button type="button" style={{ ...styles.refreshButton, borderColor: "#9ED5C8", color: "#078D6A", padding: "11px 17px" }} onClick={loadReports} disabled={loading}><RefreshCw size={15} />{loading ? "Loading..." : "Refresh"}</button>
      </header>

      <section className="billing-filter-grid" aria-label="Filter billing reports" style={{ padding: 14, border: "1px solid #E5EBF3", borderRadius: 13, background: "white", boxShadow: "0 2px 8px rgba(25,54,91,.04)" }}>
        <label style={filterLabel}><CalendarDays size={18} /><span>Date Range<select value={dateRange} onChange={(event) => setDateRange(event.target.value)} style={filterSelect}><option value="30">Last 30 Days</option><option value="7">Last 7 Days</option><option value="90">Last 90 Days</option><option value="all">All Time</option></select></span><ChevronDown size={15} /></label>
        <label style={filterLabel}><CheckCircle size={18} /><span>Job Status<select value="all" disabled style={filterSelect}><option value="all">All Completed</option></select></span><ChevronDown size={15} /></label>
        <label style={filterLabel}><UserRound size={18} /><span>Customer<select value={customerFilter} onChange={(event) => setCustomerFilter(event.target.value)} style={filterSelect}><option value="all">All Customers</option>{customers.map((customer) => <option key={customer} value={customer}>{customer}</option>)}</select></span><ChevronDown size={15} /></label>
        <label style={{ ...filterLabel, position: "relative" }}><Search size={18} /><input aria-label="Search billing reports" placeholder="Search by job ID, customer or location..." value={search} onChange={(event) => setSearch(event.target.value)} style={{ border: 0, outline: 0, width: "100%", color: "#334968", fontSize: 13 }} /></label>
      </section>

      <section className="billing-stats" aria-label="Billing totals">
        {[
          { label: "Total Jobs", value: reportTotals.jobs.toLocaleString("en-IN"), icon: <FileText size={22} />, tint: "#E9F8F4", color: "#078D6A" },
          { label: "Total Amount", value: money(reportTotals.amount), icon: <IndianRupee size={23} />, tint: "#EEF5FF", color: "#1674C8" },
          { label: "Service / Labour", value: money(reportTotals.labour), icon: <UserRound size={22} />, tint: "#F4F0FF", color: "#7650D9" },
          { label: "Materials", value: money(reportTotals.materials), icon: <Clock3 size={22} />, tint: "#FFF6E8", color: "#E99814" },
        ].map((stat) => <div key={stat.label} style={{ display: "flex", alignItems: "center", gap: 15, padding: 16, minWidth: 0, borderRadius: 12, border: `1px solid ${stat.color}22`, background: "white" }}><div style={{ width: 50, height: 50, borderRadius: 13, display: "grid", placeItems: "center", color: stat.color, background: stat.tint, flexShrink: 0 }}>{stat.icon}</div><div style={{ minWidth: 0 }}><div style={{ color: "#60718E", fontSize: 12 }}>{stat.label}</div><strong style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", color: "#16365D", fontSize: 19, marginTop: 4 }}>{stat.value}</strong></div></div>)}
      </section>

      {error && (
        <div
          role="alert"
          style={styles.error}
        >
          {error}
        </div>
      )}

      {loading ? (
        <div style={styles.empty}>
          Loading billing reports...
        </div>
      ) : reports.length === 0 ? (
        <div style={styles.empty}>
          <FileText
            size={36}
            color="#9CA3AF"
          />

          <div>
            No billing reports submitted yet.
          </div>

          <span>
            Reports will appear here after you submit the billing form.
          </span>
        </div>
      ) : visibleReports.length === 0 ? (
        <div style={styles.empty}>No reports match these filters.</div>
      ) : (
        <section style={{ borderRadius: 13, background: "white", border: "1px solid #E5EBF3", boxShadow: "0 2px 8px rgba(25,54,91,.04)", padding: "0 14px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, minHeight: 48, borderBottom: "1px solid #E7EDF5", padding: "0 8px", color: "#405675", fontSize: 12 }}>
          <span>Showing {visibleReports.length} of {reports.length} reports</span>
          <div style={{ display: "flex", alignItems: "center", gap: 9 }}><label>Sort by: <select value={sortOrder} onChange={(event) => setSortOrder(event.target.value)} style={{ border: 0, background: "transparent", color: "#304968", fontWeight: 650 }}><option value="newest">Date (Newest)</option><option value="oldest">Date (Oldest)</option></select></label><button aria-label="List view" type="button" onClick={() => setViewMode("list")} style={viewButton(viewMode === "list")}><List size={16} /></button><button aria-label="Grid view" type="button" onClick={() => setViewMode("grid")} style={viewButton(viewMode === "grid")}><LayoutGrid size={16} /></button></div>
        </div>
        <div style={{ ...styles.list, ...(viewMode === "grid" ? { gridTemplateColumns: "repeat(auto-fit,minmax(330px,1fr))" } : {}) }}>
          {visibleReports.map((report) => {
            const signature = signatureState[report.id];

            return (
            <div
              key={report.id}
              className="billing-report-card"
              style={styles.card}
            >
              <div style={styles.cardHeader}>
                <div>
                  <div style={styles.reportId}>
                    REPORT #{report.id}
                  </div>

                  <div style={styles.jobTitle}>
                    Job #{report.job_id} ·{" "}
                    {report.service_type}
                  </div>

                  <div style={styles.customer}>
                    {report.customer_name} ·{" "}
                    {report.location}
                  </div>
                </div>

                <div style={styles.completedBadge}>
                  COMPLETED
                </div>
              </div>

              <div style={styles.summary}>
                {report.work_summary}
              </div>

              <div style={styles.costGrid}>
                <div style={styles.costItem}>
                  <span>
                    Service / Labour :
                  </span>

                  <strong>
                    {money(report.labour_cost)}
                  </strong>
                </div>

                <div style={styles.costItem}>
                  <span>
                    Material :
                  </span>

                  <strong>
                    {money(report.material_cost)}
                  </strong>
                </div>

                <div style={styles.costItem}>
                  <span>
                    Subtotal :
                  </span>

                  <strong>
                    {money(report.subtotal)}
                  </strong>
                </div>

                <div style={styles.costItem}>
                  <span>
                    GST ({report.gst_rate}%) :
                  </span>

                  <strong>
                    {money(report.gst_amount)}
                  </strong>
                </div>

                <div
                  style={{
                    ...styles.costItem,
                    ...styles.total,
                  }}
                >
                  <span>
                    Total :
                  </span>

                  <strong>
                    {money(report.total_amount)}
                  </strong>
                </div>
              </div>

              <div style={styles.signatureSection}>
                <div style={styles.signatureHeader}>
                  <div>
                    <div style={styles.signatureTitle}>
                      Customer Signature
                    </div>
                    <div style={styles.signatureSubtitle}>
                      Captured during job completion
                    </div>
                  </div>

                  <button
                    type="button"
                    style={styles.signatureButton}
                    onClick={() =>
                      void handleToggleSignature(report)
                    }
                  >
                    {visibleSignatureReportId === report.id
                      ? "Hide Signature"
                      : "View Signature"}
                  </button>
                </div>

                {visibleSignatureReportId === report.id && (
                  <div style={styles.signatureContent}>
                    {signature?.loading ? (
                      <span style={styles.signatureMessage}>
                        Loading customer signature...
                      </span>
                    ) : signature?.error ? (
                      <span style={styles.signatureError}>
                        {signature.error}
                      </span>
                    ) : signature?.data ? (
                      <div style={styles.signatureImageWrap}>
                        <img
                          src={signature.data}
                          alt={`Customer signature for job #${report.job_id}`}
                          style={styles.signatureImage}
                        />
                      </div>
                    ) : (
                      <span style={styles.signatureMessage}>
                        Customer signature is not available.
                      </span>
                    )}
                  </div>
                )}
              </div>

              <div style={styles.footer}>
                <span>
                  Submitted:{" "}
                  {report.completed_at
                    ? new Date(
                        report.completed_at
                      ).toLocaleString("en-IN")
                    : "N/A"}
                </span>

                <button
                  type="button"
                  style={{
                    ...styles.downloadButton,
                    ...(downloading === report.id
                      ? styles.downloadButtonDisabled
                      : {}),
                  }}
                  onClick={() =>
                    void handleDownload(report)
                  }
                  disabled={
                    downloading !== null
                  }
                >
                  <Download size={15} />

                  {downloading === report.id
                    ? "Preparing..."
                    : "Download PDF"}
                </button>
              </div>
            </div>
            );
          })}
        </div>
        </section>
      )}
    </div>
  );
}

const styles = {
  page: {
    padding: "24px",
    height: "100%",
    overflowY: "auto" as const,
    background: "#EEF4F1",
    fontFamily: "'Inter', sans-serif",
  },

  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "22px",
    gap: "16px",
  },

  title: {
    margin: 0,
    fontSize: "22px",
    fontWeight: 700,
    color: "#1F2933",
  },

  subtitle: {
    margin: "5px 0 0",
    fontSize: "13px",
    color: "#6B7280",
  },

  refreshButton: {
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    padding: "9px 14px",
    border: "1px solid #D1D5DB",
    borderRadius: "8px",
    background: "#fff",
    color: "#374151",
    fontWeight: 600,
    cursor: "pointer",
  },

  error: {
    background: "#FEE2E2",
    color: "#991B1B",
    border: "1px solid #FECACA",
    padding: "12px 14px",
    borderRadius: "10px",
    marginBottom: "14px",
    fontSize: "13px",
  },

  empty: {
    minHeight: "260px",
    background: "#fff",
    border: "1px solid #E3ECE7",
    borderRadius: "14px",
    display: "flex",
    flexDirection: "column" as const,
    alignItems: "center",
    justifyContent: "center",
    gap: "8px",
    color: "#6B7280",
    fontSize: "14px",
  },

  list: {
    display: "grid",
    gap: "14px",
  },

  card: {
    gap: "12px 18px",
    background: "#fff",
    border: "1px solid #E3ECE7",
    borderRadius: "14px",
    padding: "20px",
    boxShadow:
      "0 2px 8px rgba(0,0,0,0.05)",
  },

  cardHeader: {
    gridColumn: "1 / -1",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: "12px",
    marginBottom: "0",
  },

  reportId: {
    fontSize: "10px",
    fontWeight: 700,
    color: "#9CA3AF",
    letterSpacing: "0.06em",
  },

  jobTitle: {
    marginTop: "4px",
    fontSize: "16px",
    fontWeight: 700,
    color: "#1F2933",
  },

  customer: {
    marginTop: "4px",
    fontSize: "12px",
    color: "#6B7280",
  },

  completedBadge: {
    background: "#D1FAE5",
    color: "#065F46",
    padding: "5px 10px",
    borderRadius: "20px",
    fontSize: "10px",
    fontWeight: 700,
  },

  summary: {
    alignSelf: "start",
    background: "#F9FAFB",
    border: "1px solid #F3F4F6",
    borderRadius: "9px",
    padding: "11px 13px",
    fontSize: "13px",
    color: "#4B5563",
    lineHeight: 1.5,
    marginBottom: "0",
  },

  costGrid: {
    display: "grid",
    gridTemplateColumns: "1fr",
    gap: "4px",
    alignContent: "start",
    borderLeft: "1px solid #E3EAF2",
    paddingLeft: "17px",
  },

  costItem: {
    minWidth: "0",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: "10px",
    whiteSpace: "normal" as const,
    fontSize: "12px",
    color: "#536987",
  },

  total: {
    background: "#ECFDF5",
    borderRadius: "9px",
    padding: "10px 12px",
  },

  signatureSection: {
    gridColumn: "1 / -1",
    marginTop: "0",
    paddingTop: "14px",
    borderTop: "1px solid #F0F0F0",
    background: "#FAFCFB",
    borderRadius: "10px",
    padding: "14px",
  },

  signatureHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: "12px",
  },

  signatureTitle: {
    fontSize: "13px",
    fontWeight: 700,
    color: "#1F2933",
  },

  signatureSubtitle: {
    marginTop: "3px",
    fontSize: "11px",
    color: "#9CA3AF",
  },

  signatureButton: {
    border: "1px solid #D1D5DB",
    borderRadius: "8px",
    background: "#fff",
    color: "#166534",
    padding: "8px 12px",
    fontSize: "12px",
    fontWeight: 700,
    cursor: "pointer",
    whiteSpace: "nowrap" as const,
  },

  signatureContent: {
    marginTop: "12px",
    minHeight: "120px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    border: "1px dashed #D1D5DB",
    borderRadius: "9px",
    background: "#fff",
    padding: "12px",
  },

  signatureImageWrap: {
    width: "100%",
    maxWidth: "520px",
    background: "#fff",
    borderRadius: "8px",
    padding: "8px",
  },

  signatureImage: {
    display: "block",
    width: "100%",
    maxHeight: "180px",
    objectFit: "contain" as const,
  },

  signatureMessage: {
    fontSize: "12px",
    color: "#6B7280",
  },

  signatureError: {
    fontSize: "12px",
    color: "#991B1B",
    textAlign: "center" as const,
  },

  footer: {
    gridColumn: "1 / -1",
    marginTop: "0",
    paddingTop: "14px",
    borderTop: "1px solid #F0F0F0",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: "12px",
    flexWrap: "wrap" as const,
    fontSize: "11px",
    color: "#9CA3AF",
  },

  downloadButton: {
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    padding: "9px 14px",
    border: "none",
    borderRadius: "8px",
    background: "#166534",
    color: "#fff",
    fontSize: "12px",
    fontWeight: 700,
    cursor: "pointer",
  },

  downloadButtonDisabled: {
    background: "#9CA3AF",
    cursor: "not-allowed",
  },
};
