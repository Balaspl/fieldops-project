import {
  FormEvent,
  useEffect,
  useState,
} from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock3,
  Headphones,
  RefreshCw,
  Send,
} from "lucide-react";

import {
  createCustomerSupportRequest,
  CustomerSupportRequestResponse,
  getCustomerSupportRequests,
} from "../../services/customerPortalService";

const styles = {
  page: {
    minHeight: "100%",
    padding: "28px",
    background: "#F8FAF9",
    boxSizing: "border-box",
  } as React.CSSProperties,

  header: {
    marginBottom: "24px",
  } as React.CSSProperties,

  titleRow: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    marginBottom: "8px",
  } as React.CSSProperties,

  titleIcon: {
    width: "42px",
    height: "42px",
    borderRadius: "10px",
    background: "#E8F3EC",
    color: "#2F4F3E",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  } as React.CSSProperties,

  title: {
    margin: 0,
    fontSize: "26px",
    fontWeight: 700,
    color: "#1F2937",
  } as React.CSSProperties,

  subtitle: {
    margin: 0,
    fontSize: "14px",
    lineHeight: 1.6,
    color: "#64748B",
  } as React.CSSProperties,

  grid: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)",
    gap: "22px",
    alignItems: "start",
  } as React.CSSProperties,

  card: {
    background: "#FFFFFF",
    border: "1px solid #E3ECE7",
    borderRadius: "14px",
    padding: "22px",
    boxShadow: "0 4px 16px rgba(47, 79, 62, 0.05)",
  } as React.CSSProperties,

  cardTitle: {
    margin: 0,
    fontSize: "18px",
    fontWeight: 700,
    color: "#1F2937",
  } as React.CSSProperties,

  cardSubtitle: {
    margin: "6px 0 20px",
    fontSize: "13px",
    lineHeight: 1.5,
    color: "#64748B",
  } as React.CSSProperties,

  label: {
    display: "block",
    marginBottom: "7px",
    fontSize: "13px",
    fontWeight: 600,
    color: "#334155",
  } as React.CSSProperties,

  input: {
    width: "100%",
    minHeight: "44px",
    padding: "10px 12px",
    border: "1px solid #CBD5E1",
    borderRadius: "9px",
    fontSize: "14px",
    color: "#1F2937",
    background: "#FFFFFF",
    outline: "none",
    boxSizing: "border-box",
  } as React.CSSProperties,

  textarea: {
    width: "100%",
    minHeight: "150px",
    padding: "11px 12px",
    border: "1px solid #CBD5E1",
    borderRadius: "9px",
    fontSize: "14px",
    lineHeight: 1.5,
    color: "#1F2937",
    background: "#FFFFFF",
    outline: "none",
    resize: "vertical",
    boxSizing: "border-box",
    fontFamily: "inherit",
  } as React.CSSProperties,

  field: {
    marginBottom: "18px",
  } as React.CSSProperties,

  button: {
    width: "100%",
    minHeight: "45px",
    border: "none",
    borderRadius: "9px",
    padding: "10px 16px",
    background: "#2F4F3E",
    color: "#FFFFFF",
    fontSize: "14px",
    fontWeight: 700,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "8px",
    cursor: "pointer",
  } as React.CSSProperties,

  disabledButton: {
    opacity: 0.65,
    cursor: "not-allowed",
  } as React.CSSProperties,

  alert: {
    borderRadius: "9px",
    padding: "11px 12px",
    marginBottom: "18px",
    fontSize: "13px",
    lineHeight: 1.5,
    display: "flex",
    gap: "9px",
    alignItems: "flex-start",
  } as React.CSSProperties,

  successAlert: {
    background: "#ECFDF3",
    border: "1px solid #BBF7D0",
    color: "#166534",
  } as React.CSSProperties,

  errorAlert: {
    background: "#FEF2F2",
    border: "1px solid #FECACA",
    color: "#991B1B",
  } as React.CSSProperties,

  requestsHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "12px",
    marginBottom: "18px",
  } as React.CSSProperties,

  refreshButton: {
    width: "36px",
    height: "36px",
    borderRadius: "8px",
    border: "1px solid #D7E4DC",
    background: "#FFFFFF",
    color: "#2F4F3E",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    cursor: "pointer",
  } as React.CSSProperties,

  requestCard: {
    border: "1px solid #E5E7EB",
    borderRadius: "11px",
    padding: "15px",
    marginBottom: "12px",
  } as React.CSSProperties,

  requestTop: {
    display: "flex",
    justifyContent: "space-between",
    gap: "12px",
    alignItems: "flex-start",
    marginBottom: "9px",
  } as React.CSSProperties,

  requestNumber: {
    fontSize: "12px",
    fontWeight: 700,
    color: "#64748B",
    marginBottom: "4px",
  } as React.CSSProperties,

  requestSubject: {
    margin: 0,
    fontSize: "15px",
    fontWeight: 700,
    color: "#1F2937",
  } as React.CSSProperties,

  requestDescription: {
    margin: "0 0 12px",
    fontSize: "13px",
    lineHeight: 1.5,
    color: "#475569",
    whiteSpace: "pre-wrap",
  } as React.CSSProperties,

  requestMeta: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "10px",
    flexWrap: "wrap",
  } as React.CSSProperties,

  status: {
    display: "inline-flex",
    alignItems: "center",
    gap: "5px",
    padding: "5px 8px",
    borderRadius: "999px",
    fontSize: "11px",
    fontWeight: 700,
    textTransform: "uppercase",
  } as React.CSSProperties,

  date: {
    fontSize: "11px",
    color: "#94A3B8",
  } as React.CSSProperties,

  empty: {
    textAlign: "center",
    padding: "38px 20px",
    color: "#94A3B8",
  } as React.CSSProperties,

  loading: {
    textAlign: "center",
    padding: "38px 20px",
    color: "#64748B",
    fontSize: "13px",
  } as React.CSSProperties,
};

function getErrorMessage(error: unknown): string {
  const apiError = error as {
    response?: {
      data?: {
        detail?: string;
      };
    };
    message?: string;
  };

  return (
    apiError.response?.data?.detail ||
    apiError.message ||
    "Unable to complete the support request."
  );
}

function getStatusStyle(status: string): React.CSSProperties {
  const normalized = status.toUpperCase();

  if (
    normalized === "COMPLETED" ||
    normalized === "RESOLVED" ||
    normalized === "CLOSED"
  ) {
    return {
      ...styles.status,
      background: "#ECFDF3",
      color: "#166534",
    };
  }

  if (
    normalized === "IN_PROGRESS" ||
    normalized === "PROCESSING"
  ) {
    return {
      ...styles.status,
      background: "#EFF6FF",
      color: "#1D4ED8",
    };
  }

  return {
    ...styles.status,
    background: "#FFF7ED",
    color: "#C2410C",
  };
}

function formatDate(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

export default function CustomerSupportPage() {
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");

  const [
    requests,
    setRequests,
  ] = useState<CustomerSupportRequestResponse[]>([]);

  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const [successMessage, setSuccessMessage] =
    useState("");

  const [errorMessage, setErrorMessage] =
    useState("");

  const loadRequests = async (
    showRefreshState = false,
  ) => {
    if (showRefreshState) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      const response =
        await getCustomerSupportRequests();

      setRequests(
        response.data || [],
      );

      setErrorMessage("");
    } catch (error) {
      setErrorMessage(
        getErrorMessage(error),
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    void loadRequests();
  }, []);

  const handleSubmit = async (
    event: FormEvent<HTMLFormElement>,
  ) => {
    event.preventDefault();

    setSuccessMessage("");
    setErrorMessage("");

    const trimmedSubject =
      subject.trim();

    const trimmedDescription =
      description.trim();

    if (trimmedSubject.length < 3) {
      setErrorMessage(
        "Subject must contain at least 3 characters.",
      );
      return;
    }

    if (trimmedDescription.length < 10) {
      setErrorMessage(
        "Description must contain at least 10 characters.",
      );
      return;
    }

    try {
      setSubmitting(true);

      const response =
        await createCustomerSupportRequest({
          subject: trimmedSubject,
          description: trimmedDescription,
        });

      const createdRequest =
        response.data;

      setRequests((current) => [
        createdRequest,
        ...current.filter(
          (item) =>
            item.id !== createdRequest.id,
        ),
      ]);

      setSubject("");
      setDescription("");

      setSuccessMessage(
        `Support request ${createdRequest.request_number} was submitted successfully.`,
      );
    } catch (error) {
      setErrorMessage(
        getErrorMessage(error),
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={styles.page}>
      <div style={styles.header}>
        <div style={styles.titleRow}>
          <div style={styles.titleIcon}>
            <Headphones size={22} />
          </div>

          <h1 style={styles.title}>
            Customer Support
          </h1>
        </div>

        <p style={styles.subtitle}>
          Submit a support request and view
          the requests you have already submitted.
        </p>
      </div>

      {successMessage && (
        <div
          style={{
            ...styles.alert,
            ...styles.successAlert,
          }}
          role="status"
        >
          <CheckCircle2
            size={17}
            style={{ flexShrink: 0 }}
          />

          <span>
            {successMessage}
          </span>
        </div>
      )}

      {errorMessage && (
        <div
          style={{
            ...styles.alert,
            ...styles.errorAlert,
          }}
          role="alert"
        >
          <AlertCircle
            size={17}
            style={{ flexShrink: 0 }}
          />

          <span>
            {errorMessage}
          </span>
        </div>
      )}

      <div style={styles.grid}>
        <section style={styles.card}>
          <h2 style={styles.cardTitle}>
            Submit a Support Request
          </h2>

          <p style={styles.cardSubtitle}>
            Tell our support team what you
            need help with.
          </p>

          <form
            onSubmit={handleSubmit}
            noValidate
          >
            <div style={styles.field}>
              <label
                htmlFor="support-subject"
                style={styles.label}
              >
                Subject
              </label>

              <input
                id="support-subject"
                type="text"
                value={subject}
                onChange={(event) =>
                  setSubject(
                    event.target.value,
                  )
                }
                placeholder="What do you need help with?"
                maxLength={200}
                disabled={submitting}
                style={styles.input}
              />
            </div>

            <div style={styles.field}>
              <label
                htmlFor="support-description"
                style={styles.label}
              >
                Description
              </label>

              <textarea
                id="support-description"
                value={description}
                onChange={(event) =>
                  setDescription(
                    event.target.value,
                  )
                }
                placeholder="Describe the issue or request in detail..."
                maxLength={5000}
                disabled={submitting}
                style={styles.textarea}
              />

              <div
                style={{
                  marginTop: "6px",
                  textAlign: "right",
                  fontSize: "11px",
                  color: "#94A3B8",
                }}
              >
                {description.length}/5000
              </div>
            </div>

            <button
              type="submit"
              disabled={submitting}
              style={{
                ...styles.button,
                ...(submitting
                  ? styles.disabledButton
                  : {}),
              }}
            >
              {submitting ? (
                <>
                  <RefreshCw
                    size={17}
                    style={{
                      animation:
                        "customer-support-spin 1s linear infinite",
                    }}
                  />

                  Submitting...
                </>
              ) : (
                <>
                  <Send size={17} />
                  Submit Support Request
                </>
              )}
            </button>
          </form>
        </section>

        <section style={styles.card}>
          <div style={styles.requestsHeader}>
            <div>
              <h2 style={styles.cardTitle}>
                My Support Requests
              </h2>

              <p
                style={{
                  ...styles.cardSubtitle,
                  marginBottom: 0,
                }}
              >
                Your support history for the
                authenticated account.
              </p>
            </div>

            <button
              type="button"
              aria-label="Refresh support requests"
              title="Refresh"
              onClick={() =>
                void loadRequests(true)
              }
              disabled={refreshing}
              style={{
                ...styles.refreshButton,
                opacity: refreshing ? 0.6 : 1,
                cursor: refreshing
                  ? "not-allowed"
                  : "pointer",
              }}
            >
              <RefreshCw
                size={16}
                style={{
                  animation: refreshing
                    ? "customer-support-spin 1s linear infinite"
                    : undefined,
                }}
              />
            </button>
          </div>

          {loading ? (
            <div style={styles.loading}>
              Loading your support requests...
            </div>
          ) : requests.length === 0 ? (
            <div style={styles.empty}>
              <Headphones
                size={30}
                style={{
                  marginBottom: "9px",
                  opacity: 0.65,
                }}
              />

              <div
                style={{
                  fontSize: "14px",
                  fontWeight: 600,
                  marginBottom: "5px",
                }}
              >
                No support requests yet
              </div>

              <div
                style={{
                  fontSize: "12px",
                }}
              >
                Submitted requests will appear here.
              </div>
            </div>
          ) : (
            <div>
              {requests.map((item) => (
                <article
                  key={item.id}
                  style={styles.requestCard}
                >
                  <div style={styles.requestTop}>
                    <div>
                      <div
                        style={styles.requestNumber}
                      >
                        {item.request_number}
                      </div>

                      <h3
                        style={
                          styles.requestSubject
                        }
                      >
                        {item.subject}
                      </h3>
                    </div>

                    <span
                      style={getStatusStyle(
                        item.status,
                      )}
                    >
                      {item.status ===
                        "OPEN" && (
                        <Clock3 size={11} />
                      )}

                      {item.status}
                    </span>
                  </div>

                  <p
                    style={
                      styles.requestDescription
                    }
                  >
                    {item.description}
                  </p>

                  <div style={styles.requestMeta}>
                    <span
                      style={styles.date}
                    >
                      Submitted{" "}
                      {formatDate(
                        item.created_at,
                      )}
                    </span>

                    {item.updated_at !==
                      item.created_at && (
                      <span
                        style={styles.date}
                      >
                        Updated{" "}
                        {formatDate(
                          item.updated_at,
                        )}
                      </span>
                    )}
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      </div>

      <style>
        {`
          @keyframes customer-support-spin {
            from {
              transform: rotate(0deg);
            }
            to {
              transform: rotate(360deg);
            }
          }

          @media (max-width: 900px) {
            .customer-support-grid {
              grid-template-columns: 1fr !important;
            }
          }
        `}
      </style>
    </div>
  );
}