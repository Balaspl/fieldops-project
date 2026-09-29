import { useEffect, useState } from "react";
import {
  Download,
  FileText,
  RefreshCw,
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
    <div style={styles.page}>
      <div style={styles.header}>
        <div>
          <h2 style={styles.title}>
            Billing Reports
          </h2>

          <p style={styles.subtitle}>
            Submitted billing details for your completed jobs
          </p>
        </div>

        <button
          type="button"
          style={styles.refreshButton}
          onClick={loadReports}
          disabled={loading}
        >
          <RefreshCw size={15} />

          {loading
            ? "Loading..."
            : "Refresh"}
        </button>
      </div>

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
      ) : (
        <div style={styles.list}>
          {reports.map((report) => {
            const signature = signatureState[report.id];

            return (
            <div
              key={report.id}
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
    background: "#fff",
    border: "1px solid #E3ECE7",
    borderRadius: "14px",
    padding: "20px",
    boxShadow:
      "0 2px 8px rgba(0,0,0,0.05)",
  },

  cardHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: "12px",
    marginBottom: "14px",
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
    background: "#F9FAFB",
    border: "1px solid #F3F4F6",
    borderRadius: "9px",
    padding: "11px 13px",
    fontSize: "13px",
    color: "#4B5563",
    lineHeight: 1.5,
    marginBottom: "14px",
  },

  costGrid: {
    display: "grid",
    gridTemplateColumns:
      "repeat(5, minmax(150px, 1fr))",
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

  total: {
    background: "#ECFDF5",
    borderRadius: "9px",
    padding: "10px 12px",
  },

  signatureSection: {
    marginTop: "16px",
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
    marginTop: "16px",
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