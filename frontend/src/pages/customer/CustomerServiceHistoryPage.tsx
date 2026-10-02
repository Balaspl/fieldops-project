import {
  useCallback,
  useEffect,
  useState,
} from "react";
import {
  AlertCircle,
  CheckCircle,
  Clock,
  History,
  Send,
  Star,
} from "lucide-react";
import {
  CustomerFeedbackResponse,
  getCustomerFeedback,
  getServiceHistory,
  submitCustomerFeedback,
} from "../../services/customerPortalService";

interface ServiceHistoryItem {
  id: number;
  request_number: string;
  title: string;
  description: string;
  status: string;
  linked_job_id?: number | null;
  created_job?: {
    id: number;
  } | null;
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
  const [history, setHistory] = useState<
    ServiceHistoryItem[]
  >([]);
  const [loading, setLoading] = useState(true);
  const [historyError, setHistoryError] =
    useState<string | null>(null);

  const [feedbackByJob, setFeedbackByJob] =
    useState<FeedbackByJob>({});

  const [feedbackLoadingByJob, setFeedbackLoadingByJob] =
    useState<FeedbackLoadingByJob>({});

  const [
    feedbackSubmittingByJob,
    setFeedbackSubmittingByJob,
  ] = useState<FeedbackSubmittingByJob>({});

  const [feedbackErrorByJob, setFeedbackErrorByJob] =
    useState<FeedbackErrorByJob>({});

  const [feedbackRatingByJob, setFeedbackRatingByJob] =
    useState<FeedbackRatingByJob>({});

  const [feedbackCommentByJob, setFeedbackCommentByJob] =
    useState<FeedbackCommentByJob>({});

  const loadFeedbackForHistory =
    useCallback(
      async (items: ServiceHistoryItem[]) => {
        const completedItems = items.filter(
          (item) =>
            String(item.status || "")
              .trim()
              .toUpperCase() === "COMPLETED" &&
            item.linked_job_id != null,
        );

        if (completedItems.length === 0) {
          return;
        }

        const feedbackResults = await Promise.all(
          completedItems.map(async (item) => {
            const jobId = Number(item.linked_job_id);

            setFeedbackLoadingByJob((prev) => ({
              ...prev,
              [jobId]: true,
            }));

            setFeedbackErrorByJob((prev) => ({
              ...prev,
              [jobId]: null,
            }));

            try {
              const response =
                await getCustomerFeedback(jobId);

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
          const next = {
            ...prev,
          };

          feedbackResults.forEach(
            ({ jobId, response }) => {
              next[jobId] = response;
            },
          );

          return next;
        });

        setFeedbackErrorByJob((prev) => {
          const next = {
            ...prev,
          };

          feedbackResults.forEach(
            ({ jobId, error }) => {
              next[jobId] = error;
            },
          );

          return next;
        });
      },
      [],
    );

  const loadHistory = useCallback(async () => {
    setLoading(true);
    setHistoryError(null);

    try {
      const response = await getServiceHistory();

      const nextHistory = Array.isArray(response.data)
        ? (response.data as ServiceHistoryItem[])
        : [];

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
      setHistoryError(
        getFeedbackErrorMessage(error),
      );
    } finally {
      setLoading(false);
    }
  }, [loadFeedbackForHistory]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  const handleSubmitFeedback = async (
    jobId: number,
  ) => {
    const rating = feedbackRatingByJob[jobId] || 0;

    if (rating < 1 || rating > 5) {
      setFeedbackErrorByJob((prev) => ({
        ...prev,
        [jobId]: "Please select a rating from 1 to 5.",
      }));
      return;
    }

    const commentValue =
      feedbackCommentByJob[jobId]?.trim() || null;

    setFeedbackSubmittingByJob((prev) => ({
      ...prev,
      [jobId]: true,
    }));

    setFeedbackErrorByJob((prev) => ({
      ...prev,
      [jobId]: null,
    }));

    try {
      const response =
        await submitCustomerFeedback(jobId, {
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
        (
          error as {
            response?: {
              status?: number;
            };
          } | null
        )?.response?.status === 409
      ) {
        try {
          const refreshed =
            await getCustomerFeedback(jobId);

          setFeedbackByJob((prev) => ({
            ...prev,
            [jobId]: refreshed.data,
          }));
        } catch {
          // Keep the authoritative conflict message visible.
        }
      }
    } finally {
      setFeedbackSubmittingByJob((prev) => ({
        ...prev,
        [jobId]: false,
      }));
    }
  };

  return (
    <div
      style={{
        padding: "24px",
        height: "100%",
        overflowY: "auto",
        background: "#EEF4F1",
        fontFamily: "'Inter', sans-serif",
      }}
    >
      {/* Page Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "16px",
          marginBottom: "18px",
          flexWrap: "wrap",
        }}
      >
        <h2
          style={{
            fontSize: "22px",
            fontWeight: 700,
            color: "#1F2933",
            margin: 0,
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <History
            size={22}
            color="#7AAE8A"
          />
          Service History
        </h2>

        {!loading && (
          <button
            type="button"
            onClick={() => void loadHistory()}
            style={{
              border: "1px solid #D7E5DC",
              background: "#FFFFFF",
              color: "#315C43",
              borderRadius: "9px",
              padding: "8px 12px",
              fontSize: "12px",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            Refresh
          </button>
        )}
      </div>

      {/* Loading */}
      {loading ? (
        <div
          role="status"
          style={{
            textAlign: "center",
            padding: "40px",
            color: "#6B7280",
            fontSize: "14px",
            background: "#FFFFFF",
            borderRadius: "14px",
            border: "1px solid #E3ECE7",
          }}
        >
          Loading service history...
        </div>
      ) : historyError ? (
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
          <AlertCircle
            size={28}
            style={{
              marginBottom: "8px",
            }}
          />

          <div
            style={{
              fontWeight: 700,
              marginBottom: "6px",
            }}
          >
            Unable to load service history
          </div>

          <div>{historyError}</div>

          <button
            type="button"
            onClick={() => void loadHistory()}
            style={{
              marginTop: "14px",
              border: "none",
              background: "#7AAE8A",
              color: "#FFFFFF",
              borderRadius: "9px",
              padding: "9px 14px",
              fontSize: "12px",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            Try Again
          </button>
        </div>
      ) : history.length === 0 ? (
        /* Empty State */
        <div
          style={{
            textAlign: "center",
            padding: "40px",
            color: "#6B7280",
            background: "#FFFFFF",
            borderRadius: "14px",
            border: "1px solid #E3ECE7",
            fontSize: "14px",
          }}
        >
          No completed or cancelled service requests yet.
        </div>
      ) : (
        /* History Cards */
        <div
          data-testid="customer-service-history-list"
          style={{
            display: "grid",
            gridTemplateColumns:
              "repeat(auto-fit, minmax(320px, 1fr))",
            gap: "12px",
          }}
        >
          {history.map((sr) => {
            const isCompleted =
              String(sr.status || "")
                .trim()
                .toUpperCase() === "COMPLETED";

            const jobId =
              sr.linked_job_id != null
                ? Number(sr.linked_job_id)
                : sr.created_job?.id != null
                  ? Number(sr.created_job.id)
                  : null;

            const feedback =
              jobId != null
                ? feedbackByJob[jobId]
                : undefined;

            const feedbackLoading =
              jobId != null
                ? Boolean(
                    feedbackLoadingByJob[jobId],
                  )
                : false;

            const feedbackSubmitting =
              jobId != null
                ? Boolean(
                    feedbackSubmittingByJob[jobId],
                  )
                : false;

            const feedbackError =
              jobId != null
                ? feedbackErrorByJob[jobId]
                : null;

            const selectedRating =
              jobId != null
                ? feedbackRatingByJob[jobId] || 0
                : 0;

            const commentValue =
              jobId != null
                ? feedbackCommentByJob[jobId] || ""
                : "";

            return (
              <div
                key={sr.id}
                data-testid={`customer-service-history-${sr.id}`}
                style={{
                  background: "#FFFFFF",
                  borderRadius: "14px",
                  padding: "14px 18px",
                  boxShadow:
                    "0 2px 8px rgba(0,0,0,0.05)",
                  border: "1px solid #E3ECE7",
                }}
              >
                {/* Top Row */}
                <div
                  style={{
                    display: "flex",
                    justifyContent:
                      "space-between",
                    alignItems:
                      "flex-start",
                    gap: "16px",
                  }}
                >
                  {/* Request Details */}
                  <div
                    style={{
                      minWidth: 0,
                      flex: 1,
                    }}
                  >
                    {/* Request Number */}
                    <div
                      style={{
                        fontSize: "11px",
                        fontWeight: 500,
                        color: "#64748B",
                        lineHeight: "16px",
                        marginBottom: "2px",
                      }}
                    >
                      {sr.request_number}
                    </div>

                    {/* Title */}
                    <div
                      style={{
                        fontSize: "16px",
                        fontWeight: 700,
                        color: "#17212B",
                        lineHeight: "21px",
                        marginBottom: "5px",
                      }}
                    >
                      {sr.title}
                    </div>

                    {/* Description */}
                    <div
                      style={{
                        fontSize: "13px",
                        fontWeight: 400,
                        color: "#4B5563",
                        lineHeight: "19px",
                      }}
                    >
                      {sr.description}
                    </div>
                  </div>

                  {/* Status */}
                  <span
                    style={{
                      flexShrink: 0,
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent:
                        "center",
                      fontSize: "11px",
                      fontWeight: 700,
                      lineHeight: "16px",
                      padding: "4px 11px",
                      borderRadius: "20px",
                      background: isCompleted
                        ? "#D1FAE5"
                        : "#FEE2E2",
                      color: isCompleted
                        ? "#065F46"
                        : "#991B1B",
                      whiteSpace:
                        "nowrap",
                    }}
                  >
                    {isCompleted && (
                      <CheckCircle
                        size={12}
                        style={{
                          marginRight: "4px",
                        }}
                      />
                    )}

                    {sr.status}
                  </span>
                </div>

                {/* Updated Date */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "5px",
                    marginTop: "8px",
                    fontSize: "12px",
                    fontWeight: 500,
                    color: "#6B7280",
                    lineHeight: "16px",
                  }}
                >
                  <Clock
                    size={13}
                    color="#7C8794"
                  />

                  <span>
                    Updated:{" "}
                    {sr.updated_at
                      ? new Date(
                          sr.updated_at,
                        ).toLocaleDateString()
                      : "—"}
                  </span>
                </div>

                {/* Customer Feedback */}
                {isCompleted && jobId != null && (
                  <div
                    data-testid={`customer-feedback-${jobId}`}
                    style={{
                      marginTop: "16px",
                      paddingTop: "14px",
                      borderTop:
                        "1px solid #E8EFEA",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "7px",
                        fontSize: "14px",
                        fontWeight: 700,
                        color: "#1F2933",
                        marginBottom: "8px",
                      }}
                    >
                      <Star
                        size={16}
                        color="#7AAE8A"
                      />
                      Service Feedback
                    </div>

                    {feedbackLoading ? (
                      <div
                        role="status"
                        style={{
                          fontSize: "12px",
                          color: "#6B7280",
                          padding: "8px 0",
                        }}
                      >
                        Checking feedback status...
                      </div>
                    ) : feedback?.has_feedback &&
                      feedback.feedback ? (
                      <div
                        data-testid={`customer-feedback-submitted-${jobId}`}
                        style={{
                          padding: "12px",
                          borderRadius: "10px",
                          background:
                            "#F0FDF4",
                          border:
                            "1px solid #BBF7D0",
                        }}
                      >
                        <div
                          style={{
                            display:
                              "flex",
                            alignItems:
                              "center",
                            gap: "5px",
                            marginBottom:
                              "7px",
                          }}
                        >
                          {Array.from({
                            length: 5,
                          }).map(
                            (_, index) => (
                              <Star
                                key={
                                  index
                                }
                                size={15}
                                fill={
                                  index <
                                  feedback
                                    .feedback!
                                    .rating
                                    ? "#EAB308"
                                    : "none"
                                }
                                color={
                                  index <
                                  feedback
                                    .feedback!
                                    .rating
                                    ? "#EAB308"
                                    : "#CBD5E1"
                                }
                              />
                            ),
                          )}
                        </div>

                        {feedback
                          .feedback
                          .comment && (
                          <div
                            style={{
                              fontSize:
                                "12px",
                              lineHeight:
                                1.5,
                              color:
                                "#374151",
                            }}
                          >
                            {
                              feedback
                                .feedback
                                .comment
                            }
                          </div>
                        )}

                        <div
                          style={{
                            marginTop:
                              "8px",
                            fontSize:
                              "11px",
                            fontWeight:
                              600,
                            color:
                              "#166534",
                          }}
                        >
                          Feedback submitted
                        </div>
                      </div>
                    ) : feedbackError ? (
                      <div
                        role="alert"
                        style={{
                          display:
                            "flex",
                          alignItems:
                            "flex-start",
                          gap: "7px",
                          padding: "10px",
                          borderRadius:
                            "9px",
                          background:
                            "#FFF7ED",
                          border:
                            "1px solid #FED7AA",
                          color:
                            "#9A3412",
                          fontSize:
                            "12px",
                          lineHeight:
                            1.45,
                        }}
                      >
                        <AlertCircle
                          size={15}
                          style={{
                            flexShrink: 0,
                            marginTop: "1px",
                          }}
                        />
                        <span>
                          {
                            feedbackError
                          }
                        </span>
                      </div>
                    ) : (
                      <div>
                        <div
                          style={{
                            fontSize:
                              "12px",
                            color:
                              "#64748B",
                            marginBottom:
                              "7px",
                          }}
                        >
                          How was your service?
                        </div>

                        <div
                          role="radiogroup"
                          aria-label={`Rate completed job ${jobId}`}
                          style={{
                            display:
                              "flex",
                            gap: "4px",
                            marginBottom:
                              "10px",
                          }}
                        >
                          {[
                            1, 2, 3, 4, 5,
                          ].map(
                            (rating) => (
                              <button
                                key={
                                  rating
                                }
                                type="button"
                                role="radio"
                                aria-label={`${rating} star${rating === 1 ? "" : "s"}`}
                                aria-checked={
                                  selectedRating ===
                                  rating
                                }
                                onClick={() =>
                                  setFeedbackRatingByJob(
                                    (
                                      prev,
                                    ) => ({
                                      ...prev,
                                      [jobId]:
                                        rating,
                                    }),
                                  )
                                }
                                disabled={
                                  feedbackSubmitting
                                }
                                style={{
                                  border:
                                    "none",
                                  background:
                                    "transparent",
                                  padding:
                                    "2px",
                                  cursor:
                                    feedbackSubmitting
                                      ? "not-allowed"
                                      : "pointer",
                                  opacity:
                                    feedbackSubmitting
                                      ? 0.6
                                      : 1,
                                }}
                              >
                                <Star
                                  size={
                                    22
                                  }
                                  fill={
                                    rating <=
                                    selectedRating
                                      ? "#EAB308"
                                      : "none"
                                  }
                                  color={
                                    rating <=
                                    selectedRating
                                      ? "#EAB308"
                                      : "#CBD5E1"
                                  }
                                />
                              </button>
                            ),
                          )}
                        </div>

                        <textarea
                          value={
                            commentValue
                          }
                          onChange={(
                            event,
                          ) =>
                            setFeedbackCommentByJob(
                              (prev) => ({
                                ...prev,
                                [jobId]:
                                  event
                                    .target
                                    .value,
                              }),
                            )
                          }
                          disabled={
                            feedbackSubmitting
                          }
                          placeholder="Add an optional comment"
                          rows={3}
                          aria-label={`Feedback comment for job ${jobId}`}
                          style={{
                            width:
                              "100%",
                            boxSizing:
                              "border-box",
                            resize:
                              "vertical",
                            border:
                              "1px solid #D7E5DC",
                            borderRadius:
                              "9px",
                            padding:
                              "9px 10px",
                            fontFamily:
                              "inherit",
                            fontSize:
                              "12px",
                            color:
                              "#1F2933",
                            outline:
                              "none",
                            marginBottom:
                              "9px",
                          }}
                        />

                        {feedbackError && (
                          <div
                            role="alert"
                            style={{
                              display:
                                "flex",
                              alignItems:
                                "flex-start",
                              gap: "7px",
                              padding:
                                "8px 9px",
                              borderRadius:
                                "8px",
                              background:
                                "#FEF2F2",
                              border:
                                "1px solid #FECACA",
                              color:
                                "#991B1B",
                              fontSize:
                                "11px",
                              lineHeight:
                                1.4,
                              marginBottom:
                                "9px",
                            }}
                          >
                            <AlertCircle
                              size={
                                14
                              }
                              style={{
                                flexShrink: 0,
                                marginTop:
                                  "1px",
                              }}
                            />

                            <span>
                              {
                                feedbackError
                              }
                            </span>
                          </div>
                        )}

                        <button
                          type="button"
                          onClick={() =>
                            void handleSubmitFeedback(
                              jobId,
                            )
                          }
                          disabled={
                            feedbackSubmitting ||
                            selectedRating <
                              1
                          }
                          style={{
                            display:
                              "inline-flex",
                            alignItems:
                              "center",
                            justifyContent:
                              "center",
                            gap: "6px",
                            border:
                              "none",
                            borderRadius:
                              "9px",
                            padding:
                              "9px 13px",
                            background:
                              feedbackSubmitting ||
                              selectedRating <
                                1
                                ? "#CBD5E1"
                                : "#7AAE8A",
                            color:
                              "#FFFFFF",
                            fontSize:
                              "12px",
                            fontWeight:
                              700,
                            cursor:
                              feedbackSubmitting ||
                              selectedRating <
                                1
                                ? "not-allowed"
                                : "pointer",
                          }}
                        >
                          <Send
                            size={13}
                          />

                          {feedbackSubmitting
                            ? "Submitting..."
                            : "Submit Feedback"}
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {/* No linked job available */}
                {isCompleted &&
                  jobId == null && (
                    <div
                      style={{
                        marginTop:
                          "14px",
                        paddingTop:
                          "12px",
                        borderTop:
                          "1px solid #E8EFEA",
                        fontSize:
                          "11px",
                        color:
                          "#6B7280",
                      }}
                    >
                      Feedback is currently unavailable
                      because this history entry has no linked
                      completed job.
                    </div>
                  )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}