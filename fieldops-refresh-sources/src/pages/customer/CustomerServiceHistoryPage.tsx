import {
  useCallback,
  useEffect,
  useState,
} from "react";
import {
  AlertCircle,
  Calendar,
  CheckCircle,
  History,
  Send,
  Star,
  Wrench,
  X,
  XCircle,
} from "lucide-react";
import {
  CustomerFeedbackResponse,
  getCustomerFeedback,
  getCustomerJobs,
  getServiceHistory,
  submitCustomerFeedback,
} from "../../services/customerPortalService";

interface ServiceHistoryItem {
  id: number;
  request_number: string;
  title: string;
  description?: string;
  service_type?: string | null;
  priority?: string | null;
  status: string;
  linked_job_id?: number | null;
  assigned_technician_id?: number | null;
  assigned_technician_name?: string | null;
  assigned_technician_phone?: string | null;
  created_job?: {
    id: number;
    assigned_technician_id?: number | null;
  } | null;
  preferred_visit_date?: string | null;
  created_at?: string;
  updated_at: string;
}

type FeedbackByJob = Record<
  number,
  CustomerFeedbackResponse | undefined
>;

type FeedbackLoadingByJob = Record<number, boolean>;

type FeedbackSubmittingByJob = Record<number, boolean>;

type FeedbackErrorByJob = Record<number, string | null>;

type FeedbackRatingByJob = Record<number, number>;

type FeedbackCommentByJob = Record<number, string>;

function getFeedbackErrorMessage(error: unknown) {
  const responseStatus =
    (
      error as {
        response?: {
          status?: number;
        };
      } | null
    )?.response?.status;

  if (responseStatus === 401) {
    return "Your session has expired. Please sign in again.";
  }

  if (responseStatus === 403) {
    return "You do not have permission to submit feedback.";
  }

  if (responseStatus === 404) {
    return "This completed job is no longer available for feedback.";
  }

  if (responseStatus === 409) {
    return "Feedback has already been submitted for this job.";
  }

  if (responseStatus === 422) {
    return "Please select a valid rating and try again.";
  }

  return "We couldn't process your feedback right now. Please try again.";
}

export default function CustomerServiceHistoryPage() {
  const [history, setHistory] = useState<ServiceHistoryItem[]>([]);
  const [jobsById, setJobsById] = useState<Record<number, any>>({});
  const [jobsBySrId, setJobsBySrId] = useState<Record<number, any>>({});
  const [loading, setLoading] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);

  // 2 Tabs: "COMPLETED" | "CANCELLED"
  const [activeTab, setActiveTab] = useState<"COMPLETED" | "CANCELLED">("COMPLETED");

  const [feedbackByJob, setFeedbackByJob] = useState<FeedbackByJob>({});
  const [feedbackLoadingByJob, setFeedbackLoadingByJob] = useState<FeedbackLoadingByJob>({});
  const [feedbackSubmittingByJob, setFeedbackSubmittingByJob] = useState<FeedbackSubmittingByJob>({});
  const [feedbackErrorByJob, setFeedbackErrorByJob] = useState<FeedbackErrorByJob>({});
  const [feedbackRatingByJob, setFeedbackRatingByJob] = useState<FeedbackRatingByJob>({});
  const [feedbackCommentByJob, setFeedbackCommentByJob] = useState<FeedbackCommentByJob>({});

  // Active Job ID for Feedback Popup Modal
  const [activeFeedbackModalJobId, setActiveFeedbackModalJobId] = useState<number | null>(null);

  const loadFeedbackForHistory = useCallback(
    async (items: ServiceHistoryItem[]) => {
      const completedItems = items.filter(
        (item) =>
          String(item.status || "").trim().toUpperCase() === "COMPLETED" &&
          (item.linked_job_id != null || item.created_job?.id != null || item.id != null),
      );

      if (completedItems.length === 0) {
        return;
      }

      const feedbackResults = await Promise.all(
        completedItems.map(async (item) => {
          const jobId = Number(item.linked_job_id || item.created_job?.id || item.id);

          setFeedbackLoadingByJob((prev) => ({
            ...prev,
            [jobId]: true,
          }));

          setFeedbackErrorByJob((prev) => ({
            ...prev,
            [jobId]: null,
          }));

          try {
            const response = await getCustomerFeedback(jobId);
            return {
              jobId,
              response: response.data,
              error: null,
            };
          } catch (error) {
            return {
              jobId,
              response: undefined,
              error: getFeedbackErrorMessage(error),
            };
          } finally {
            setFeedbackLoadingByJob((prev) => ({
              ...prev,
              [jobId]: false,
            }));
          }
        }),
      );

      setFeedbackByJob((prev) => {
        const next = { ...prev };
        feedbackResults.forEach(({ jobId, response }) => {
          next[jobId] = response;
        });
        return next;
      });

      setFeedbackErrorByJob((prev) => {
        const next = { ...prev };
        feedbackResults.forEach(({ jobId, error }) => {
          next[jobId] = error;
        });
        return next;
      });
    },
    [],
  );

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setHistoryError(null);

    try {
      const [historyRes, jobsRes] = await Promise.allSettled([
        getServiceHistory(),
        getCustomerJobs(),
      ]);

      let nextHistory: ServiceHistoryItem[] = [];
      if (historyRes.status === "fulfilled" && Array.isArray(historyRes.value.data)) {
        nextHistory = historyRes.value.data as ServiceHistoryItem[];
      }

      const jMap: Record<number, any> = {};
      const srMap: Record<number, any> = {};
      if (jobsRes.status === "fulfilled" && Array.isArray(jobsRes.value.data)) {
        jobsRes.value.data.forEach((j: any) => {
          if (j.id != null) jMap[j.id] = j;
          if (j.service_request_id != null) srMap[j.service_request_id] = j;
        });
      }

      setJobsById(jMap);
      setJobsBySrId(srMap);
      setHistory(nextHistory);
      setFeedbackByJob({});
      setFeedbackErrorByJob({});
      setFeedbackRatingByJob({});
      setFeedbackCommentByJob({});

      await loadFeedbackForHistory(nextHistory);
    } catch (error) {
      setHistory([]);
      setFeedbackByJob({});
      setFeedbackErrorByJob({});
      setHistoryError(getFeedbackErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [loadFeedbackForHistory]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  const handleSubmitFeedback = async (jobId: number) => {
    const rawRating = feedbackRatingByJob[jobId] || 0;
    const rating = rawRating >= 1 ? rawRating : 5;
    const commentValue = feedbackCommentByJob[jobId]?.trim() || null;

    setFeedbackSubmittingByJob((prev) => ({
      ...prev,
      [jobId]: true,
    }));

    setFeedbackErrorByJob((prev) => ({
      ...prev,
      [jobId]: null,
    }));

    try {
      const response = await submitCustomerFeedback(jobId, {
        rating,
        comment: commentValue,
      });

      setFeedbackByJob((prev) => ({
        ...prev,
        [jobId]: response.data,
      }));

      setFeedbackRatingByJob((prev) => ({
        ...prev,
        [jobId]: 0,
      }));

      setFeedbackCommentByJob((prev) => ({
        ...prev,
        [jobId]: "",
      }));
    } catch (error) {
      setFeedbackErrorByJob((prev) => ({
        ...prev,
        [jobId]: getFeedbackErrorMessage(error),
      }));

      if (
        (error as { response?: { status?: number } } | null)?.response?.status === 409
      ) {
        try {
          const refreshed = await getCustomerFeedback(jobId);
          setFeedbackByJob((prev) => ({
            ...prev,
            [jobId]: refreshed.data,
          }));
        } catch {
          // Keep conflict message visible
        }
      }
    } finally {
      setFeedbackSubmittingByJob((prev) => ({
        ...prev,
        [jobId]: false,
      }));
    }
  };

  const completedList = history.filter(
    (item) => String(item.status || "").trim().toUpperCase() === "COMPLETED",
  );

  const cancelledList = history.filter(
    (item) => String(item.status || "").trim().toUpperCase() === "CANCELLED",
  );

  const currentList = activeTab === "COMPLETED" ? completedList : cancelledList;

  const activeModalItem = history.find(
    (h) =>
      Number(h.linked_job_id || h.created_job?.id || h.id) === activeFeedbackModalJobId,
  );

  return (
    <div
      style={{
        padding: "24px",
        height: "100%",
        overflowY: "auto",
        background: "#F8FAFC",
        fontFamily: "'Inter', sans-serif",
      }}
    >
      <style>{`
        .service-history-grid {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 16px;
        }
        @media (max-width: 1080px) {
          .service-history-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
          }
        }
        @media (max-width: 680px) {
          .service-history-grid {
            grid-template-columns: 1fr !important;
          }
        }
      `}</style>

      {/* Page Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "16px",
          marginBottom: "16px",
          flexWrap: "wrap",
        }}
      >
        <div>
          <h2
            style={{
              fontSize: "22px",
              fontWeight: 700,
              color: "#0F172A",
              margin: 0,
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <History size={22} color="#059669" />
            Service History
          </h2>
          <p style={{ margin: "4px 0 0 0", fontSize: "13px", color: "#64748B" }}>
            Track completed and cancelled service records
          </p>
        </div>

        {!loading && (
          <button
            type="button"
            onClick={() => void loadHistory()}
            style={{
              border: "1px solid #E2E8F0",
              background: "#FFFFFF",
              color: "#0F172A",
              borderRadius: "8px",
              padding: "7px 14px",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
              transition: "all 0.15s ease",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "#F1F5F9")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "#FFFFFF")}
          >
            Refresh
          </button>
        )}
      </div>

      {/* 2 Tabs: Completed Jobs vs Cancelled Jobs */}
      <div
        style={{
          display: "flex",
          gap: "8px",
          marginBottom: "20px",
          background: "#F1F5F9",
          padding: "4px",
          borderRadius: "10px",
          width: "fit-content",
        }}
      >
        {/* Completed Jobs Tab */}
        <button
          type="button"
          onClick={() => setActiveTab("COMPLETED")}
          style={{
            padding: "8px 18px",
            borderRadius: "8px",
            border: "none",
            background: activeTab === "COMPLETED" ? "#FFFFFF" : "transparent",
            color: activeTab === "COMPLETED" ? "#0F172A" : "#64748B",
            fontWeight: 700,
            fontSize: "13px",
            cursor: "pointer",
            boxShadow:
              activeTab === "COMPLETED"
                ? "0 1px 3px rgba(0,0,0,0.08)"
                : "none",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            transition: "all 0.15s ease",
          }}
        >
          <CheckCircle
            size={15}
            color={activeTab === "COMPLETED" ? "#059669" : "#64748B"}
          />
          <span>Completed Jobs</span>
          <span
            style={{
              background:
                activeTab === "COMPLETED" ? "#ECFDF5" : "#E2E8F0",
              color:
                activeTab === "COMPLETED" ? "#059669" : "#64748B",
              fontSize: "11px",
              fontWeight: 700,
              padding: "1px 7px",
              borderRadius: "10px",
            }}
          >
            {completedList.length}
          </span>
        </button>

        {/* Cancelled Jobs Tab */}
        <button
          type="button"
          onClick={() => setActiveTab("CANCELLED")}
          style={{
            padding: "8px 18px",
            borderRadius: "8px",
            border: "none",
            background: activeTab === "CANCELLED" ? "#FFFFFF" : "transparent",
            color: activeTab === "CANCELLED" ? "#0F172A" : "#64748B",
            fontWeight: 700,
            fontSize: "13px",
            cursor: "pointer",
            boxShadow:
              activeTab === "CANCELLED"
                ? "0 1px 3px rgba(0,0,0,0.08)"
                : "none",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            transition: "all 0.15s ease",
          }}
        >
          <XCircle
            size={15}
            color={activeTab === "CANCELLED" ? "#DC2626" : "#64748B"}
          />
          <span>Cancelled Jobs</span>
          <span
            style={{
              background:
                activeTab === "CANCELLED" ? "#FEF2F2" : "#E2E8F0",
              color:
                activeTab === "CANCELLED" ? "#DC2626" : "#64748B",
              fontSize: "11px",
              fontWeight: 700,
              padding: "1px 7px",
              borderRadius: "10px",
            }}
          >
            {cancelledList.length}
          </span>
        </button>
      </div>

      {/* Loading State */}
      {loading ? (
        <div
          role="status"
          style={{
            textAlign: "center",
            padding: "48px",
            color: "#64748B",
            fontSize: "14px",
            background: "#FFFFFF",
            borderRadius: "14px",
            border: "1px solid #E2E8F0",
          }}
        >
          Loading service history...
        </div>
      ) : historyError ? (
        /* Error State */
        <div
          role="alert"
          style={{
            textAlign: "center",
            padding: "40px",
            color: "#991B1B",
            background: "#FEF2F2",
            borderRadius: "14px",
            border: "1px solid #FECACA",
            fontSize: "14px",
          }}
        >
          <AlertCircle size={28} style={{ marginBottom: "8px" }} />
          <div style={{ fontWeight: 700, marginBottom: "6px" }}>
            Unable to load service history
          </div>
          <div>{historyError}</div>
          <button
            type="button"
            onClick={() => void loadHistory()}
            style={{
              marginTop: "14px",
              border: "none",
              background: "#059669",
              color: "#FFFFFF",
              borderRadius: "8px",
              padding: "8px 16px",
              fontSize: "12px",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            Try Again
          </button>
        </div>
      ) : currentList.length === 0 ? (
        /* Empty State */
        <div
          style={{
            textAlign: "center",
            padding: "48px",
            color: "#64748B",
            background: "#FFFFFF",
            borderRadius: "14px",
            border: "1px solid #E2E8F0",
            fontSize: "14px",
          }}
        >
          {activeTab === "COMPLETED"
            ? "No completed jobs found."
            : "No cancelled jobs found."}
        </div>
      ) : (
        /* Cards Grid - 3 per row on desktop */
        <div
          className="service-history-grid"
          data-testid="customer-service-history-list"
        >
          {currentList.map((sr) => {
            const isCompleted =
              String(sr.status || "").trim().toUpperCase() === "COMPLETED";

            const jobId =
              sr.linked_job_id != null
                ? Number(sr.linked_job_id)
                : sr.created_job?.id != null
                  ? Number(sr.created_job.id)
                  : sr.id != null
                    ? Number(sr.id)
                    : null;

            // Resolve linked job details
            const jobData =
              (jobId != null ? jobsById[jobId] : null) ||
              (sr.id != null ? jobsBySrId[sr.id] : null);

            // Service Type
            const serviceType =
              sr.service_type || jobData?.service_type || "General Service";

            // Date
            const dateObj = sr.updated_at
              ? new Date(sr.updated_at)
              : sr.created_at
                ? new Date(sr.created_at)
                : null;
            const displayDate = dateObj
              ? dateObj.toLocaleDateString("en-IN", {
                  day: "numeric",
                  month: "short",
                  year: "numeric",
                })
              : "—";

            // Feedback status
            const feedback = jobId != null ? feedbackByJob[jobId] : undefined;
            const hasSubmittedFeedback = Boolean(feedback?.has_feedback && feedback.feedback);

            return (
              <div
                key={sr.id}
                data-testid={`customer-service-history-${sr.id}`}
                style={{
                  background: "#FFFFFF",
                  borderRadius: "14px",
                  padding: "16px 18px",
                  boxShadow:
                    "0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02)",
                  border: "1px solid #E2E8F0",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                  boxSizing: "border-box",
                  minHeight: "155px",
                  transition: "transform 0.15s ease, box-shadow 0.15s ease",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = "translateY(-2px)";
                  e.currentTarget.style.boxShadow =
                    "0 6px 16px rgba(0,0,0,0.06)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = "translateY(0)";
                  e.currentTarget.style.boxShadow =
                    "0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02)";
                }}
              >
                {/* Top Section */}
                <div>
                  {/* Row 1: Job ID + Status */}
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      gap: "8px",
                      marginBottom: "8px",
                    }}
                  >
                    {/* Job ID Tag */}
                    <span
                      style={{
                        fontSize: "11px",
                        fontWeight: 700,
                        padding: "2px 8px",
                        borderRadius: "6px",
                        background: "#F1F5F9",
                        color: "#334155",
                        letterSpacing: "0.02em",
                      }}
                    >
                      Job #{jobId || sr.id}
                    </span>

                    {/* Status Badge */}
                    <span
                      style={{
                        flexShrink: 0,
                        display: "inline-flex",
                        alignItems: "center",
                        fontSize: "11px",
                        fontWeight: 700,
                        padding: "3px 9px",
                        borderRadius: "20px",
                        background: isCompleted ? "#D1FAE5" : "#FEE2E2",
                        color: isCompleted ? "#065F46" : "#991B1B",
                        whiteSpace: "nowrap",
                        gap: "4px",
                      }}
                    >
                      {isCompleted ? (
                        <CheckCircle size={12} />
                      ) : (
                        <XCircle size={12} />
                      )}
                      {isCompleted ? "Completed" : "Cancelled"}
                    </span>
                  </div>

                  {/* Row 2: Service Type Tag (Below Job ID) */}
                  <div style={{ marginBottom: "8px" }}>
                    <span
                      style={{
                        fontSize: "11px",
                        fontWeight: 600,
                        padding: "2px 8px",
                        borderRadius: "6px",
                        background: "#ECFDF5",
                        color: "#059669",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "4px",
                      }}
                    >
                      <Wrench size={11} />
                      {serviceType}
                    </span>
                  </div>

                  {/* Row 3: Title (Below Service Type) */}
                  <div
                    style={{
                      fontSize: "15px",
                      fontWeight: 700,
                      color: "#0F172A",
                      lineHeight: "20px",
                    }}
                  >
                    {sr.title}
                  </div>
                </div>

                {/* Bottom Footer Section: Date + Feedback */}
                <div
                  style={{
                    marginTop: "16px",
                    paddingTop: "10px",
                    borderTop: "1px solid #F1F5F9",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: "10px",
                  }}
                >
                  {/* Date */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "5px",
                      fontSize: "11px",
                      fontWeight: 500,
                      color: "#64748B",
                    }}
                  >
                    <Calendar size={13} color="#94A3B8" />
                    <span>{displayDate}</span>
                  </div>

                  {/* Feedback Action for Completed */}
                  <div>
                    {isCompleted && jobId != null ? (
                      hasSubmittedFeedback ? (
                        <button
                          type="button"
                          onClick={() => setActiveFeedbackModalJobId(jobId)}
                          title="Click to view submitted feedback"
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "4px",
                            background: "#F0FDF4",
                            border: "1px solid #BBF7D0",
                            color: "#166534",
                            borderRadius: "6px",
                            padding: "5px 10px",
                            fontSize: "11px",
                            fontWeight: 600,
                            cursor: "pointer",
                          }}
                        >
                          <Star size={12} fill="#EAB308" color="#EAB308" />
                          <span>Rated {feedback!.feedback!.rating}/5</span>
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setActiveFeedbackModalJobId(jobId)}
                          title="Leave feedback for this completed service"
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "4px",
                            background: "#059669",
                            border: "none",
                            color: "#FFFFFF",
                            borderRadius: "6px",
                            padding: "5px 12px",
                            fontSize: "11px",
                            fontWeight: 600,
                            cursor: "pointer",
                            boxShadow: "0 1px 2px rgba(0,0,0,0.06)",
                          }}
                          onMouseEnter={(e) =>
                            (e.currentTarget.style.background = "#047857")
                          }
                          onMouseLeave={(e) =>
                            (e.currentTarget.style.background = "#059669")
                          }
                        >
                          <Star size={12} fill="#FFFFFF" color="#FFFFFF" />
                          <span>Feedback</span>
                        </button>
                      )
                    ) : null}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Feedback Modal Popup */}
      {activeFeedbackModalJobId !== null && (
        <div
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setActiveFeedbackModalJobId(null);
            }
          }}
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(15, 23, 42, 0.45)",
            backdropFilter: "blur(3px)",
            zIndex: 1000,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "16px",
          }}
        >
          <div
            style={{
              background: "#FFFFFF",
              borderRadius: "16px",
              maxWidth: "480px",
              width: "100%",
              padding: "24px",
              boxShadow:
                "0 20px 25px -5px rgba(0,0,0,0.1), 0 10px 10px -5px rgba(0,0,0,0.04)",
              position: "relative",
              boxSizing: "border-box",
            }}
          >
            {/* Modal Header */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                marginBottom: "16px",
              }}
            >
              <div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                    fontSize: "18px",
                    fontWeight: 700,
                    color: "#0F172A",
                  }}
                >
                  <Star size={20} color="#EAB308" fill="#EAB308" />
                  <span>Service Feedback</span>
                </div>
                {activeModalItem && (
                  <div
                    style={{
                      fontSize: "12px",
                      color: "#64748B",
                      marginTop: "3px",
                    }}
                  >
                    Job #{activeFeedbackModalJobId} &bull; {activeModalItem.title}
                  </div>
                )}
              </div>

              {/* Close Button */}
              <button
                type="button"
                onClick={() => setActiveFeedbackModalJobId(null)}
                style={{
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  color: "#94A3B8",
                  padding: "4px",
                  borderRadius: "6px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.color = "#1E293B")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "#94A3B8")}
              >
                <X size={20} />
              </button>
            </div>

            {/* Modal Content */}
            {(() => {
              const jobId = activeFeedbackModalJobId;
              const feedback = feedbackByJob[jobId];
              const feedbackLoading = Boolean(feedbackLoadingByJob[jobId]);
              const feedbackSubmitting = Boolean(feedbackSubmittingByJob[jobId]);
              const feedbackError = feedbackErrorByJob[jobId];
              const selectedRating = feedbackRatingByJob[jobId] || 0;
              const commentValue = feedbackCommentByJob[jobId] || "";

              const hasEnteredFeedback =
                selectedRating > 0 || commentValue.trim().length > 0;
              const isSubmitDisabled = feedbackSubmitting || !hasEnteredFeedback;

              if (feedbackLoading) {
                return (
                  <div
                    style={{
                      textAlign: "center",
                      padding: "32px",
                      color: "#64748B",
                      fontSize: "13px",
                    }}
                  >
                    Loading feedback details...
                  </div>
                );
              }

              if (feedback?.has_feedback && feedback.feedback) {
                return (
                  <div>
                    <div
                      style={{
                        padding: "16px",
                        borderRadius: "12px",
                        background: "#F0FDF4",
                        border: "1px solid #BBF7D0",
                        marginBottom: "20px",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "6px",
                          marginBottom: "10px",
                        }}
                      >
                        {Array.from({ length: 5 }).map((_, idx) => (
                          <Star
                            key={idx}
                            size={18}
                            fill={
                              idx < feedback.feedback!.rating
                                ? "#EAB308"
                                : "none"
                            }
                            color={
                              idx < feedback.feedback!.rating
                                ? "#EAB308"
                                : "#CBD5E1"
                            }
                          />
                        ))}
                        <span
                          style={{
                            fontSize: "13px",
                            fontWeight: 700,
                            color: "#166534",
                            marginLeft: "6px",
                          }}
                        >
                          {feedback.feedback.rating} out of 5
                        </span>
                      </div>

                      {feedback.feedback.comment && (
                        <div
                          style={{
                            fontSize: "13px",
                            lineHeight: 1.5,
                            color: "#374151",
                            background: "#FFFFFF",
                            padding: "10px 12px",
                            borderRadius: "8px",
                            border: "1px solid #DCFCE7",
                            marginBottom: "10px",
                          }}
                        >
                          &ldquo;{feedback.feedback.comment}&rdquo;
                        </div>
                      )}

                      <div
                        style={{
                          fontSize: "11px",
                          fontWeight: 600,
                          color: "#166534",
                          display: "flex",
                          alignItems: "center",
                          gap: "4px",
                        }}
                      >
                        <CheckCircle size={13} color="#166534" />
                        Feedback submitted
                        {feedback.feedback.created_at && (
                          <span style={{ color: "#4B5563", fontWeight: 400 }}>
                            &bull;{" "}
                            {new Date(
                              feedback.feedback.created_at,
                            ).toLocaleDateString()}
                          </span>
                        )}
                      </div>
                    </div>

                    <div style={{ display: "flex", justifyContent: "flex-end" }}>
                      <button
                        type="button"
                        onClick={() => setActiveFeedbackModalJobId(null)}
                        style={{
                          padding: "8px 18px",
                          border: "none",
                          borderRadius: "8px",
                          background: "#059669",
                          color: "#FFFFFF",
                          fontSize: "13px",
                          fontWeight: 700,
                          cursor: "pointer",
                        }}
                      >
                        Done
                      </button>
                    </div>
                  </div>
                );
              }

              // Give Feedback Form
              return (
                <div>
                  <div
                    style={{
                      fontSize: "13px",
                      color: "#475569",
                      marginBottom: "12px",
                    }}
                  >
                    How was the service provided? Rate your experience:
                  </div>

                  {/* Star Rating Selection */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      marginBottom: "16px",
                    }}
                  >
                    {[1, 2, 3, 4, 5].map((starVal) => {
                      const isFilled = starVal <= selectedRating;
                      return (
                        <button
                          key={starVal}
                          type="button"
                          onClick={() =>
                            setFeedbackRatingByJob((prev) => ({
                              ...prev,
                              [jobId]: starVal,
                            }))
                          }
                          disabled={feedbackSubmitting}
                          style={{
                            border: "none",
                            background: "transparent",
                            cursor: feedbackSubmitting
                              ? "not-allowed"
                              : "pointer",
                            padding: "4px",
                            borderRadius: "6px",
                            transition: "transform 0.15s ease",
                          }}
                          onMouseEnter={(e) =>
                            (e.currentTarget.style.transform = "scale(1.15)")
                          }
                          onMouseLeave={(e) =>
                            (e.currentTarget.style.transform = "scale(1)")
                          }
                          title={`${starVal} Star${starVal > 1 ? "s" : ""}`}
                        >
                          <Star
                            size={28}
                            fill={isFilled ? "#EAB308" : "none"}
                            color={isFilled ? "#EAB308" : "#CBD5E1"}
                          />
                        </button>
                      );
                    })}

                    {selectedRating > 0 && (
                      <span
                        style={{
                          fontSize: "13px",
                          fontWeight: 700,
                          color: "#0F172A",
                          marginLeft: "6px",
                        }}
                      >
                        {selectedRating === 1
                          ? "1 - Poor"
                          : selectedRating === 2
                            ? "2 - Fair"
                            : selectedRating === 3
                              ? "3 - Good"
                              : selectedRating === 4
                                ? "4 - Very Good"
                                : "5 - Excellent"}
                      </span>
                    )}
                  </div>

                  {/* Comment Input */}
                  <div style={{ marginBottom: "16px" }}>
                    <div
                      style={{
                        fontSize: "12px",
                        fontWeight: 600,
                        color: "#334155",
                        marginBottom: "6px",
                      }}
                    >
                      Comments / Feedback
                    </div>
                    <textarea
                      value={commentValue}
                      onChange={(e) =>
                        setFeedbackCommentByJob((prev) => ({
                          ...prev,
                          [jobId]: e.target.value,
                        }))
                      }
                      placeholder="Write your feedback here (e.g. service quality, punctuality)..."
                      rows={4}
                      disabled={feedbackSubmitting}
                      style={{
                        width: "100%",
                        boxSizing: "border-box",
                        borderRadius: "10px",
                        border: "1px solid #D1D5DB",
                        padding: "10px 12px",
                        fontSize: "13px",
                        fontFamily: "inherit",
                        outline: "none",
                        resize: "vertical",
                        lineHeight: 1.5,
                      }}
                      onFocus={(e) =>
                        (e.currentTarget.style.borderColor = "#059669")
                      }
                      onBlur={(e) =>
                        (e.currentTarget.style.borderColor = "#D1D5DB")
                      }
                    />
                  </div>

                  {/* Feedback Error Message */}
                  {feedbackError && (
                    <div
                      role="alert"
                      style={{
                        display: "flex",
                        alignItems: "flex-start",
                        gap: "7px",
                        padding: "10px 12px",
                        borderRadius: "8px",
                        background: "#FEF2F2",
                        border: "1px solid #FECACA",
                        color: "#991B1B",
                        fontSize: "12px",
                        lineHeight: 1.45,
                        marginBottom: "16px",
                      }}
                    >
                      <AlertCircle
                        size={15}
                        style={{ flexShrink: 0, marginTop: "1px" }}
                      />
                      <span>{feedbackError}</span>
                    </div>
                  )}

                  {/* Action Buttons */}
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "flex-end",
                      gap: "10px",
                    }}
                  >
                    <button
                      type="button"
                      onClick={() => setActiveFeedbackModalJobId(null)}
                      style={{
                        padding: "8px 16px",
                        border: "1px solid #D1D5DB",
                        borderRadius: "8px",
                        background: "#FFFFFF",
                        color: "#475569",
                        fontSize: "13px",
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                    >
                      Cancel
                    </button>

                    <button
                      type="button"
                      onClick={() => void handleSubmitFeedback(jobId)}
                      disabled={isSubmitDisabled}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                        gap: "6px",
                        border: "none",
                        borderRadius: "8px",
                        padding: "8px 18px",
                        background: isSubmitDisabled ? "#E2E8F0" : "#059669",
                        color: isSubmitDisabled ? "#94A3B8" : "#FFFFFF",
                        fontSize: "13px",
                        fontWeight: 700,
                        cursor: isSubmitDisabled ? "not-allowed" : "pointer",
                        transition: "all 0.15s ease",
                      }}
                    >
                      <Send size={13} />
                      {feedbackSubmitting ? "Submitting..." : "Submit Feedback"}
                    </button>
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      )}
    </div>
  );
}
