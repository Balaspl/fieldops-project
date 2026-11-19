import {
  FormEvent,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock3,
  Headphones,
  RefreshCw,
  Send,
  UserRound,
  BriefcaseBusiness,
} from "lucide-react";

import useAuthStore from "../../store/authStore";
import {
  createCustomerSupportRequest,
  CustomerSupportAdminRequest,
  CustomerSupportAdminUpdate,
  CustomerSupportRequestResponse,
  getAdminCustomerSupportRequest,
  getAdminCustomerSupportRequests,
  getCustomerJobs,
  getCustomerSupportRequests,
  getServiceHistory,
  updateAdminCustomerSupportRequest,
} from "../../services/customerPortalService";

interface CustomerSupportPageProps {
  initialRequestId?: number | null;
}

type RelatedJobOption = {
  id: number;
  serviceType: string;
  status: string;
  title: string;
};

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

  twoColumn: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 0.9fr) minmax(0, 1.1fr)",
    gap: "22px",
    alignItems: "start",
  } as React.CSSProperties,

  secondaryButton: {
    minHeight: "38px",
    border: "1px solid #D7E4DC",
    borderRadius: "8px",
    padding: "8px 12px",
    background: "#FFFFFF",
    color: "#2F4F3E",
    fontSize: "13px",
    fontWeight: 700,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "7px",
    cursor: "pointer",
  } as React.CSSProperties,

  requestCardSelected: {
    border: "1px solid #7AA58B",
    boxShadow: "0 0 0 2px rgba(47, 79, 62, 0.08)",
  } as React.CSSProperties,

  select: {
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

  summaryGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
    gap: "12px",
    marginBottom: "18px",
  } as React.CSSProperties,

  summaryCard: {
    border: "1px solid #E5E7EB",
    borderRadius: "10px",
    padding: "14px",
    background: "#FFFFFF",
  } as React.CSSProperties,

  summaryLabel: {
    fontSize: "11px",
    fontWeight: 700,
    color: "#64748B",
    textTransform: "uppercase",
    marginBottom: "6px",
  } as React.CSSProperties,

  summaryValue: {
    fontSize: "24px",
    lineHeight: 1,
    fontWeight: 800,
    color: "#1F2937",
  } as React.CSSProperties,

  staffLayout: {
    display: "grid",
    gridTemplateColumns: "minmax(280px, 0.75fr) minmax(0, 1.35fr)",
    gap: "18px",
    alignItems: "start",
  } as React.CSSProperties,

  detailSection: {
    border: "1px solid #E5E7EB",
    borderRadius: "10px",
    padding: "15px",
    marginBottom: "14px",
  } as React.CSSProperties,

  detailTitle: {
    margin: "0 0 12px",
    fontSize: "14px",
    fontWeight: 800,
    color: "#1F2937",
    display: "flex",
    alignItems: "center",
    gap: "7px",
  } as React.CSSProperties,

  detailRow: {
    display: "grid",
    gridTemplateColumns: "150px minmax(0, 1fr)",
    gap: "12px",
    padding: "6px 0",
    borderBottom: "1px solid #F1F5F9",
  } as React.CSSProperties,

  detailLabel: {
    fontSize: "12px",
    color: "#64748B",
  } as React.CSSProperties,

  detailValue: {
    fontSize: "13px",
    color: "#1F2937",
    overflowWrap: "anywhere",
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

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

function valueOrDash(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  return String(value);
}

function DetailRow({
  label,
  value,
}: {
  label: string;
  value: unknown;
}) {
  return (
    <div style={styles.detailRow}>
      <span style={styles.detailLabel}>
        {label}
      </span>
      <span style={styles.detailValue}>
        {valueOrDash(value)}
      </span>
    </div>
  );
}

function CustomerSupportView() {
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [relatedJobId, setRelatedJobId] =
    useState<number | "">("");

  const [requests, setRequests] =
    useState<CustomerSupportRequestResponse[]>(
      [],
    );

  const [jobs, setJobs] =
    useState<RelatedJobOption[]>([]);

  const [loading, setLoading] =
    useState(true);

  const [refreshing, setRefreshing] =
    useState(false);

  const [jobsLoading, setJobsLoading] =
    useState(true);

  const [submitting, setSubmitting] =
    useState(false);

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

    let cancelled = false;

    const loadRelatedJobs = async () => {
      setJobsLoading(true);

      try {
        const [
          activeResponse,
          historyResponse,
        ] = await Promise.all([
          getCustomerJobs(),
          getServiceHistory(),
        ]);

        const jobMap =
          new Map<number, RelatedJobOption>();

        for (
          const job of
          activeResponse.data || []
        ) {
          jobMap.set(job.id, {
            id: job.id,
            serviceType:
              job.service_type ||
              "Service",
            status:
              job.status ||
              "UNKNOWN",
            title:
              `Job #${job.id}`,
          });
        }

        for (
          const item of
          historyResponse.data || []
        ) {
          if (
            item.linked_job_id == null ||
            jobMap.has(
              item.linked_job_id,
            )
          ) {
            continue;
          }

          jobMap.set(
            item.linked_job_id,
            {
              id: item.linked_job_id,
              serviceType:
                item.service_type ||
                "Service",
              status:
                item.status ||
                "UNKNOWN",
              title:
                item.title ||
                `Job #${item.linked_job_id}`,
            },
          );
        }

        if (!cancelled) {
          setJobs(
            Array.from(
              jobMap.values(),
            ),
          );
        }
      } catch {
        if (!cancelled) {
          setJobs([]);
        }
      } finally {
        if (!cancelled) {
          setJobsLoading(false);
        }
      }
    };

    void loadRelatedJobs();

    return () => {
      cancelled = true;
    };
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
          description:
            trimmedDescription,
          related_job_id:
            relatedJobId === ""
              ? null
              : relatedJobId,
        });

      const createdRequest =
        response.data;

      setRequests((current) => [
        createdRequest,
        ...current.filter(
          (item) =>
            item.id !==
            createdRequest.id,
        ),
      ]);

      setSubject("");
      setDescription("");
      setRelatedJobId("");

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
          Raise a support issue and track how
          FieldOps is handling it.
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
            style={{
              flexShrink: 0,
            }}
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
            style={{
              flexShrink: 0,
            }}
          />

          <span>
            {errorMessage}
          </span>
        </div>
      )}

      <div
        className="customer-support-layout"
        style={styles.twoColumn}
      >
        <section style={styles.card}>
          <h2 style={styles.cardTitle}>
            Submit a Support Request
          </h2>

          <p style={styles.cardSubtitle}>
            Use Support when you need FieldOps
            to investigate or help with an issue.
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
                htmlFor="support-related-job"
                style={styles.label}
              >
                Related Job{" "}
                <span
                  style={{
                    color: "#94A3B8",
                    fontWeight: 500,
                  }}
                >
                  (optional)
                </span>
              </label>

              <select
                id="support-related-job"
                value={relatedJobId}
                onChange={(event) =>
                  setRelatedJobId(
                    event.target.value
                      ? Number(
                          event.target.value,
                        )
                      : "",
                  )
                }
                disabled={
                  submitting ||
                  jobsLoading
                }
                style={styles.select}
              >
                <option value="">
                  No related job
                </option>

                {jobs.map((job) => (
                  <option
                    key={job.id}
                    value={job.id}
                  >
                    {job.title} ·{" "}
                    {job.serviceType} ·{" "}
                    {job.status}
                  </option>
                ))}
              </select>
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
          <div
            style={styles.requestsHeader}
          >
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
                Track support requests and
                staff resolution updates.
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
                ...styles.secondaryButton,
                ...(refreshing
                  ? styles.disabledButton
                  : {}),
              }}
            >
              <RefreshCw
                size={15}
                style={{
                  animation:
                    refreshing
                      ? "customer-support-spin 1s linear infinite"
                      : undefined,
                }}
              />

              Refresh
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
                  <div
                    style={styles.requestTop}
                  >
                    <div>
                      <div
                        style={
                          styles.requestNumber
                        }
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

                  {item.related_job_id !=
                    null && (
                    <div
                      style={{
                        fontSize: "12px",
                        color: "#475569",
                        marginBottom: "9px",
                      }}
                    >
                      Related Job:{" "}
                      <strong>
                        #{item.related_job_id}
                      </strong>
                    </div>
                  )}

                  {item.resolution_note && (
                    <div
                      style={{
                        padding: "10px 11px",
                        borderRadius: "8px",
                        background: "#F8FAFC",
                        border: "1px solid #E2E8F0",
                        fontSize: "12px",
                        lineHeight: 1.5,
                        color: "#334155",
                        marginBottom: "10px",
                      }}
                    >
                      <strong>
                        Resolution:
                      </strong>{" "}
                      {item.resolution_note}
                    </div>
                  )}

                  <div
                    style={styles.requestMeta}
                  >
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

          @media (max-width: 950px) {
            .customer-support-layout {
              grid-template-columns: 1fr !important;
            }
          }
        `}
      </style>
    </div>
  );
}

const STAFF_STATUSES:
  CustomerSupportAdminUpdate["status"][] = [
    "OPEN",
    "IN_PROGRESS",
    "RESOLVED",
    "CLOSED",
  ];

function StaffCustomerSupportView({
  initialRequestId,
}: CustomerSupportPageProps) {
  const [requests, setRequests] =
    useState<
      CustomerSupportAdminRequest[]
    >([]);

  const [
    selectedRequestId,
    setSelectedRequestId,
  ] = useState<number | null>(
    initialRequestId ?? null,
  );

  const [
    statusFilter,
    setStatusFilter,
  ] = useState<
    "ALL" |
    CustomerSupportAdminUpdate["status"]
  >("ALL");

  const [
    selectedRequest,
    setSelectedRequest,
  ] =
    useState<CustomerSupportAdminRequest | null>(
      null,
    );

  const [
    selectedStatus,
    setSelectedStatus,
  ] =
    useState<
      CustomerSupportAdminUpdate["status"]
    >("OPEN");

  const [
    resolutionNote,
    setResolutionNote,
  ] = useState("");

  const [loading, setLoading] =
    useState(true);

  const [detailLoading, setDetailLoading] =
    useState(false);

  const [saving, setSaving] =
    useState(false);

  const [
    errorMessage,
    setErrorMessage,
  ] = useState("");

  const [
    successMessage,
    setSuccessMessage,
  ] = useState("");

  const loadRequests = async () => {
    setLoading(true);

    try {
      const response =
        await getAdminCustomerSupportRequests(
          statusFilter === "ALL"
            ? undefined
            : statusFilter,
        );

      const nextRequests =
        response.data || [];

      setRequests(nextRequests);
      setErrorMessage("");

      if (
        selectedRequestId != null &&
        nextRequests.some(
          (item) =>
            item.id ===
            selectedRequestId,
        )
      ) {
        return;
      }

      if (nextRequests.length > 0) {
        setSelectedRequestId(
          nextRequests[0].id,
        );
      } else {
        setSelectedRequestId(null);
        setSelectedRequest(null);
      }
    } catch (error) {
      setErrorMessage(
        getErrorMessage(error),
      );
      setRequests([]);
      setSelectedRequest(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadRequests();
  }, [statusFilter]);

  useEffect(() => {
    if (
      initialRequestId != null
    ) {
      setSelectedRequestId(
        initialRequestId,
      );
    }
  }, [initialRequestId]);

  useEffect(() => {
    if (
      selectedRequestId == null
    ) {
      setSelectedRequest(null);
      return;
    }

    const listMatch =
      requests.find(
        (item) =>
          item.id ===
          selectedRequestId,
      );

    if (listMatch) {
      setSelectedRequest(
        listMatch,
      );

      setSelectedStatus(
        listMatch.status as CustomerSupportAdminUpdate["status"],
      );

      setResolutionNote(
        listMatch.resolution_note ||
          "",
      );

      return;
    }

    let cancelled = false;

    const loadDetail = async () => {
      setDetailLoading(true);

      try {
        const response =
          await getAdminCustomerSupportRequest(
            selectedRequestId,
          );

        if (!cancelled) {
          setSelectedRequest(
            response.data,
          );

          setSelectedStatus(
            response.data.status as CustomerSupportAdminUpdate["status"],
          );

          setResolutionNote(
            response.data
              .resolution_note ||
              "",
          );

          setErrorMessage("");
        }
      } catch (error) {
        if (!cancelled) {
          setErrorMessage(
            getErrorMessage(error),
          );

          setSelectedRequest(null);
        }
      } finally {
        if (!cancelled) {
          setDetailLoading(false);
        }
      }
    };

    void loadDetail();

    return () => {
      cancelled = true;
    };
  }, [
    selectedRequestId,
    requests,
  ]);

  const counts = useMemo(() => {
    return {
      open: requests.filter(
        (item) =>
          item.status === "OPEN",
      ).length,

      inProgress: requests.filter(
        (item) =>
          item.status ===
          "IN_PROGRESS",
      ).length,

      resolved: requests.filter(
        (item) =>
          item.status ===
          "RESOLVED",
      ).length,

      closed: requests.filter(
        (item) =>
          item.status === "CLOSED",
      ).length,
    };
  }, [requests]);

  const handleSave = async () => {
    if (!selectedRequest) {
      return;
    }

    const trimmedNote =
      resolutionNote.trim();

    if (
      (
        selectedStatus === "RESOLVED" ||
        selectedStatus === "CLOSED"
      ) &&
      !trimmedNote
    ) {
      setErrorMessage(
        "A resolution note is required before resolving or closing a support request.",
      );
      return;
    }

    setSaving(true);
    setErrorMessage("");
    setSuccessMessage("");

    try {
      const response =
        await updateAdminCustomerSupportRequest(
          selectedRequest.id,
          {
            status: selectedStatus,
            resolution_note:
              trimmedNote || null,
          },
        );

      setSelectedRequest(
        response.data,
      );

      setSelectedStatus(
        response.data.status as CustomerSupportAdminUpdate["status"],
      );

      setResolutionNote(
        response.data
          .resolution_note || "",
      );

      setRequests((current) =>
        current.map((item) =>
          item.id ===
          response.data.id
            ? response.data
            : item,
        ),
      );

      setSuccessMessage(
        `Support request ${response.data.request_number} updated and the customer was notified.`,
      );
    } catch (error) {
      setErrorMessage(
        getErrorMessage(error),
      );
    } finally {
      setSaving(false);
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
          Review customer support cases,
          inspect related job information,
          and send resolution updates.
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
            style={{
              flexShrink: 0,
            }}
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
            style={{
              flexShrink: 0,
            }}
          />

          <span>
            {errorMessage}
          </span>
        </div>
      )}

      <div style={styles.summaryGrid}>
        <div style={styles.summaryCard}>
          <div style={styles.summaryLabel}>
            Open
          </div>

          <div style={styles.summaryValue}>
            {counts.open}
          </div>
        </div>

        <div style={styles.summaryCard}>
          <div style={styles.summaryLabel}>
            In Progress
          </div>

          <div style={styles.summaryValue}>
            {counts.inProgress}
          </div>
        </div>

        <div style={styles.summaryCard}>
          <div style={styles.summaryLabel}>
            Resolved
          </div>

          <div style={styles.summaryValue}>
            {counts.resolved}
          </div>
        </div>

        <div style={styles.summaryCard}>
          <div style={styles.summaryLabel}>
            Closed
          </div>

          <div style={styles.summaryValue}>
            {counts.closed}
          </div>
        </div>
      </div>

      <div
        className="customer-support-staff-layout"
        style={styles.staffLayout}
      >
        <section style={styles.card}>
          <div
            style={styles.requestsHeader}
          >
            <div>
              <h2 style={styles.cardTitle}>
                Support Queue
              </h2>

              <p
                style={{
                  ...styles.cardSubtitle,
                  marginBottom: 0,
                }}
              >
                Click a case to inspect
                the full request.
              </p>
            </div>

            <button
              type="button"
              onClick={() =>
                void loadRequests()
              }
              style={
                styles.secondaryButton
              }
              disabled={loading}
            >
              <RefreshCw size={15} />
              Refresh
            </button>
          </div>

          <div
            style={{
              marginBottom: "14px",
            }}
          >
            <label
              htmlFor="support-status-filter"
              style={styles.label}
            >
              Filter
            </label>

            <select
              id="support-status-filter"
              value={statusFilter}
              onChange={(event) =>
                setStatusFilter(
                  event.target.value as
                    | "ALL"
                    | CustomerSupportAdminUpdate["status"],
                )
              }
              style={styles.select}
            >
              <option value="ALL">
                All support requests
              </option>

              {STAFF_STATUSES.map(
                (statusValue) => (
                  <option
                    key={statusValue}
                    value={statusValue}
                  >
                    {statusValue}
                  </option>
                ),
              )}
            </select>
          </div>

          {loading ? (
            <div
              style={styles.loading}
            >
              Loading support queue...
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
                No support requests
              </div>

              <div
                style={{
                  fontSize: "12px",
                }}
              >
                New customer support cases
                will appear here.
              </div>
            </div>
          ) : (
            requests.map((item) => (
              <button
                type="button"
                key={item.id}
                onClick={() =>
                  setSelectedRequestId(
                    item.id,
                  )
                }
                style={{
                  ...styles.requestCard,
                  ...(selectedRequestId ===
                  item.id
                    ? styles.requestCardSelected
                    : {}),
                  display: "block",
                  width: "100%",
                  textAlign: "left",
                  cursor: "pointer",
                }}
              >
                <div
                  style={styles.requestTop}
                >
                  <div>
                    <div
                      style={
                        styles.requestNumber
                      }
                    >
                      {
                        item.request_number
                      }
                    </div>

                    <div
                      style={
                        styles.requestSubject
                      }
                    >
                      {item.subject}
                    </div>
                  </div>

                  <span
                    style={getStatusStyle(
                      item.status,
                    )}
                  >
                    {item.status}
                  </span>
                </div>

                <div
                  style={{
                    fontSize: "12px",
                    color: "#475569",
                    marginBottom: "8px",
                  }}
                >
                  Customer:{" "}
                  <strong>
                    {item.customer.name}
                  </strong>
                </div>

                <div
                  style={{
                    fontSize: "12px",
                    color: "#64748B",
                    lineHeight: 1.5,
                  }}
                >
                  {item.description.length >
                  130
                    ? `${item.description.slice(
                        0,
                        130,
                      )}…`
                    : item.description}
                </div>

                <div
                  style={{
                    ...styles.requestMeta,
                    marginTop: "10px",
                  }}
                >
                  <span
                    style={styles.date}
                  >
                    {formatDate(
                      item.created_at,
                    )}
                  </span>

                  {item.job ? (
                    <span
                      style={{
                        ...styles.date,
                        display:
                          "inline-flex",
                        alignItems:
                          "center",
                        gap: "4px",
                      }}
                    >
                      <BriefcaseBusiness
                        size={11}
                      />

                      Job #
                      {item.job.id}
                    </span>
                  ) : (
                    <span
                      style={styles.date}
                    >
                      No related job
                    </span>
                  )}
                </div>
              </button>
            ))
          )}
        </section>

        <section style={styles.card}>
          {detailLoading ? (
            <div style={styles.loading}>
              Loading support request details...
            </div>
          ) : !selectedRequest ? (
            <div style={styles.empty}>
              <Headphones
                size={34}
                style={{
                  marginBottom: "10px",
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
                Select a support request
              </div>

              <div
                style={{
                  fontSize: "12px",
                }}
              >
                Full customer and job
                details will appear here.
              </div>
            </div>
          ) : (
            <>
              <div
                style={styles.requestsHeader}
              >
                <div>
                  <div
                    style={
                      styles.requestNumber
                    }
                  >
                    {
                      selectedRequest.request_number
                    }
                  </div>

                  <h2
                    style={styles.cardTitle}
                  >
                    {
                      selectedRequest.subject
                    }
                  </h2>
                </div>

                <span
                  style={getStatusStyle(
                    selectedRequest.status,
                  )}
                >
                  {
                    selectedRequest.status
                  }
                </span>
              </div>

              <div
                style={styles.detailSection}
              >
                <h3
                  style={styles.detailTitle}
                >
                  <Headphones size={15} />
                  Support Request
                </h3>

                <DetailRow
                  label="Request #"
                  value={
                    selectedRequest.request_number
                  }
                />

                <DetailRow
                  label="Subject"
                  value={
                    selectedRequest.subject
                  }
                />

                <DetailRow
                  label="Description"
                  value={
                    selectedRequest.description
                  }
                />

                <DetailRow
                  label="Created"
                  value={formatDate(
                    selectedRequest.created_at,
                  )}
                />

                <DetailRow
                  label="Last updated"
                  value={formatDate(
                    selectedRequest.updated_at,
                  )}
                />

                <DetailRow
                  label="Resolution"
                  value={
                    selectedRequest.resolution_note
                  }
                />

                <DetailRow
                  label="Resolved at"
                  value={formatDate(
                    selectedRequest.resolved_at,
                  )}
                />
              </div>

              <div
                style={styles.detailSection}
              >
                <h3
                  style={styles.detailTitle}
                >
                  <UserRound size={15} />
                  Customer
                </h3>

                <DetailRow
                  label="Name"
                  value={
                    selectedRequest.customer
                      .name
                  }
                />

                <DetailRow
                  label="Email"
                  value={
                    selectedRequest.customer
                      .email
                  }
                />

                <DetailRow
                  label="Phone"
                  value={
                    selectedRequest.customer
                      .phone_number
                  }
                />
              </div>

              <div
                style={styles.detailSection}
              >
                <h3
                  style={styles.detailTitle}
                >
                  <BriefcaseBusiness
                    size={15}
                  />
                  Related Job
                </h3>

                {selectedRequest.job ? (
                  <>
                    <DetailRow
                      label="Job ID"
                      value={`#${selectedRequest.job.id}`}
                    />

                    <DetailRow
                      label="Customer"
                      value={
                        selectedRequest.job
                          .customer_name
                      }
                    />

                    <DetailRow
                      label="Service"
                      value={
                        selectedRequest.job
                          .service_type
                      }
                    />

                    <DetailRow
                      label="Issue"
                      value={
                        selectedRequest.job
                          .issue_description
                      }
                    />

                    <DetailRow
                      label="Priority"
                      value={
                        selectedRequest.job
                          .priority
                      }
                    />

                    <DetailRow
                      label="Job status"
                      value={
                        selectedRequest.job
                          .status
                      }
                    />

                    <DetailRow
                      label="Location"
                      value={
                        selectedRequest.job
                          .location ||
                        selectedRequest.job
                          .site_address
                      }
                    />

                    <DetailRow
                      label="Contact"
                      value={
                        selectedRequest.job
                          .contact_number
                      }
                    />

                    <DetailRow
                      label="Technician"
                      value={
                        selectedRequest.job
                          .assigned_technician_name
                      }
                    />

                    <DetailRow
                      label="Technician phone"
                      value={
                        selectedRequest.job
                          .assigned_technician_phone
                      }
                    />

                    <DetailRow
                      label="Preferred date"
                      value={
                        selectedRequest.job
                          .preferred_service_date
                      }
                    />

                    <DetailRow
                      label="Assigned at"
                      value={formatDate(
                        selectedRequest.job
                          .assigned_at,
                      )}
                    />

                    <DetailRow
                      label="En route at"
                      value={formatDate(
                        selectedRequest.job
                          .en_route_at,
                      )}
                    />

                    <DetailRow
                      label="On site at"
                      value={formatDate(
                        selectedRequest.job
                          .on_site_at,
                      )}
                    />

                    <DetailRow
                      label="Completed at"
                      value={formatDate(
                        selectedRequest.job
                          .completed_at,
                      )}
                    />
                  </>
                ) : (
                  <div
                    style={{
                      fontSize: "13px",
                      color: "#64748B",
                    }}
                  >
                    This support request is
                    not linked to a service job.
                  </div>
                )}
              </div>

              <div
                style={styles.detailSection}
              >
                <h3
                  style={styles.detailTitle}
                >
                  Handle Support Case
                </h3>

                <div style={styles.field}>
                  <label
                    htmlFor="support-update-status"
                    style={styles.label}
                  >
                    Status
                  </label>

                  <select
                    id="support-update-status"
                    value={selectedStatus}
                    onChange={(event) =>
                      setSelectedStatus(
                        event.target.value as CustomerSupportAdminUpdate["status"],
                      )
                    }
                    disabled={saving}
                    style={styles.select}
                  >
                    {STAFF_STATUSES.map(
                      (statusValue) => (
                        <option
                          key={statusValue}
                          value={statusValue}
                        >
                          {statusValue}
                        </option>
                      ),
                    )}
                  </select>
                </div>

                <div style={styles.field}>
                  <label
                    htmlFor="support-resolution"
                    style={styles.label}
                  >
                    Resolution / response
                  </label>

                  <textarea
                    id="support-resolution"
                    value={resolutionNote}
                    onChange={(event) =>
                      setResolutionNote(
                        event.target.value,
                      )
                    }
                    placeholder="Tell the customer what was fixed, checked, or decided. Required for RESOLVED/CLOSED."
                    maxLength={5000}
                    disabled={saving}
                    style={{
                      ...styles.textarea,
                      minHeight: "130px",
                    }}
                  />
                </div>

                <button
                  type="button"
                  onClick={() =>
                    void handleSave()
                  }
                  disabled={saving}
                  style={{
                    ...styles.button,
                    ...(saving
                      ? styles.disabledButton
                      : {}),
                  }}
                >
                  {saving ? (
                    <>
                      <RefreshCw
                        size={16}
                        style={{
                          animation:
                            "customer-support-spin 1s linear infinite",
                        }}
                      />

                      Saving and notifying...
                    </>
                  ) : (
                    <>
                      <CheckCircle2
                        size={16}
                      />
                      Save & Notify Customer
                    </>
                  )}
                </button>
              </div>
            </>
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

          @media (max-width: 1050px) {
            .customer-support-staff-layout {
              grid-template-columns: 1fr !important;
            }
          }
        `}
      </style>
    </div>
  );
}

export default function CustomerSupportPage(
  props: CustomerSupportPageProps,
) {
  const user = useAuthStore(
    (state) => state.user,
  );

  const role = String(
    user?.role || "",
  ).toLowerCase();

  const isStaff =
    role === "super_admin" ||
    role === "dispatcher";

  return isStaff ? (
    <StaffCustomerSupportView
      {...props}
    />
  ) : (
    <CustomerSupportView />
  );
}