import { useEffect, useMemo, useState } from "react";
import {
  Navigation,
  User,
  Phone,
  MapPin,
  Clock,
  ShieldCheck,
  X,
} from "lucide-react";

import { getCustomerJobs } from "../../services/customerPortalService";
import JobLiveTrackingMap from "../../components/customer-tracking/JobLiveTrackingMap";

type CustomerJob = {
  id: string | number;

  status?: string | null;
  service_type?: string | null;

  location?: string | null;
  address?: string | null;
  site_address?: string | null;

  site_latitude?: number | string | null;
  site_longitude?: number | string | null;

  created_at?: string | null;
  completed_at?: string | null;

  assigned_technician_id?: number | null;
  assigned_technician_name?: string | null;
  assigned_technician_phone?: string | null;
  assigned_technician_photo?: string | null;
  assigned_technician_skills?: string[] | null;
  assigned_technician_experience?: string | null;
  assigned_technician_certifications?: string[] | null;

  estimated_arrival?: string | null;
  eta_status?: string | null;
  eta_source?: string | null;
  eta_confidence?: string | null;
  eta_duration_minutes?: number | null;
  eta_distance_km?: number | null;
  eta_traffic_delay_minutes?: number | null;
  eta_message?: string | null;
  eta_updated_at?: string | null;

  technician_latitude?: number | string | null;
  technician_longitude?: number | string | null;

  tracking_tenant_id?: string | null;
};

type StatusStyle = {
  bg: string;
  fg: string;
};

const statusStyle: Record<string, StatusStyle> = {
  UNASSIGNED: {
    bg: "#FEF3C7",
    fg: "#DD6B20",
  },

  "AWAITING ACCEPTANCE": {
    bg: "#DBEAFE",
    fg: "#1E40AF",
  },

  ASSIGNED: {
    bg: "#DBEAFE",
    fg: "#1E40AF",
  },

  "EN ROUTE": {
    bg: "#EDE9FE",
    fg: "#5B21B6",
  },

  IN_PROGRESS: {
    bg: "#FEF3C7",
    fg: "#92400E",
  },

  COMPLETED: {
    bg: "#D1FAE5",
    fg: "#065F46",
  },

  CLOSED: {
    bg: "#E5E7EB",
    fg: "#374151",
  },

  CANCELLED: {
    bg: "#FEE2E2",
    fg: "#991B1B",
  },
};

const TERMINAL_STATUSES = new Set([
  "COMPLETED",
  "CLOSED",
  "CANCELLED",
]);

function normalizeJobStatus(status: unknown): string {
  return String(status ?? "")
    .trim()
    .toUpperCase();
}

function displayJobStatus(status: unknown): string {
  const normalized = normalizeJobStatus(status);

  switch (normalized) {
    case "CREATED":
      return "UNASSIGNED";

    case "ASSIGNED":
      return "AWAITING ACCEPTANCE";

    case "ACCEPTED":
      return "ASSIGNED";

    case "EN_ROUTE":
      return "EN ROUTE";

    case "IN_PROGRESS":
      return "IN_PROGRESS";

    default:
      return normalized || "UNKNOWN";
  }
}

function toFiniteNumber(
  value: unknown
): number | null {
  if (value === null || value === undefined || (typeof value === "string" && !value.trim())) {
    return null;
  }
  const numberValue = Number(value);

  return Number.isFinite(numberValue)
    ? numberValue
    : null;
}

function getJobAddress(
  job: CustomerJob
): string {
  return (
    job.location ||
    job.address ||
    job.site_address ||
    "Service location"
  );
}

function hasValidCoordinates(
  latitude: unknown,
  longitude: unknown
): boolean {
  const lat = toFiniteNumber(latitude);
  const lng = toFiniteNumber(longitude);

  return (
    lat !== null &&
    lng !== null &&
    lat >= -90 &&
    lat <= 90 &&
    lng >= -180 &&
    lng <= 180
  );
}

function formatEtaTime(value: unknown): string | null {
  if (!value) {
    return null;
  }

  const timestamp = new Date(String(value));
  if (Number.isNaN(timestamp.getTime())) {
    return null;
  }

  return timestamp.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatEtaDuration(value: unknown): string | null {
  const minutes = toFiniteNumber(value);
  if (minutes === null || minutes < 0) {
    return null;
  }

  const rounded = Math.round(minutes);
  if (rounded < 1) {
    return "Arriving now";
  }

  if (rounded >= 60) {
    const hours = Math.floor(rounded / 60);
    const remainder = rounded % 60;
    return remainder > 0
      ? `${hours}h ${remainder}m`
      : `${hours}h`;
  }

  return `${rounded} min`;
}

interface CustomerTrackingPageProps {
  token: string;
}

export default function CustomerTrackingPage({
  token,
}: CustomerTrackingPageProps)  {
  const [jobs, setJobs] = useState<CustomerJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasActiveJobs, setHasActiveJobs] =
    useState(false);

  const [liveJob, setLiveJob] =
    useState<CustomerJob | null>(null);

  /**
   * Load customer jobs.
   *
   * Poll only while at least one non-terminal job exists.
   * Historical terminal jobs do not need continuous refreshes.
   */
  useEffect(() => {
    let stopped = false;
    let timer: number | undefined;

    const loadJobs = async () => {
      try {
        setRefreshing(true);

        const response = await getCustomerJobs();

        if (stopped) {
          return;
        }

        const nextJobs = Array.isArray(response?.data)
          ? response.data
          : [];

        const activeJobsExist =
          nextJobs.some(
            (job) =>
              !TERMINAL_STATUSES.has(
                normalizeJobStatus(job.status)
              )
          );

        setJobs(nextJobs);
        setHasActiveJobs(activeJobsExist);
        setError(null);

        if (
          !stopped &&
          activeJobsExist
        ) {
          timer = window.setTimeout(
            loadJobs,
            5000
          );
        }
      } catch (requestError: any) {
        if (stopped) {
          return;
        }

        const status =
          requestError?.response?.status;

        if (status === 401) {
          setError(
            "Your session has expired. Please sign in again."
          );
        } else if (status === 403) {
          setError(
            "You do not have permission to view these jobs."
          );
        } else {
          setError(
            "We couldn't refresh your job tracking data."
          );
        }

        console.error(
          "Failed to load customer jobs:",
          requestError
        );

        timer = window.setTimeout(
          loadJobs,
          5000
        );
      } finally {
        if (!stopped) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    };

    void loadJobs();

    return () => {
      stopped = true;

      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
    };
  }, []);

  /**
   * Keep the live tracking modal synchronized
   * with the latest customer job response.
   *
   * EN_ROUTE / IN_PROGRESS
   *          ↓
   * technician completes
   *          ↓
   * jobs refreshed
   *          ↓
   * COMPLETED / CLOSED
   *          ↓
   * liveJob cleared
   *          ↓
   * map unmounts
   */
  useEffect(() => {
    if (!liveJob) {
      return;
    }

    const currentJob = jobs.find(
      (job) =>
        String(job.id) ===
        String(liveJob.id)
    );

    if (!currentJob) {
      setLiveJob(null);
      return;
    }

    const currentStatus =
      normalizeJobStatus(
        currentJob.status
      );

    if (
      TERMINAL_STATUSES.has(
        currentStatus
      )
    ) {
      setLiveJob(null);
      return;
    }

    setLiveJob(currentJob);
  }, [jobs, liveJob]);

  /**
   * Close tracking immediately if the selected job
   * becomes terminal.
   */
  const liveJobStatus = useMemo(() => {
    return liveJob
      ? normalizeJobStatus(liveJob.status)
      : null;
  }, [liveJob]);

  const shouldShowLiveMap =
    liveJob !== null &&
    !TERMINAL_STATUSES.has(
      liveJobStatus || ""
    );

  const activeJobs = useMemo(
    () =>
      jobs.filter(
        (job) =>
          !TERMINAL_STATUSES.has(
            normalizeJobStatus(job.status)
          )
      ),
    [jobs]
  );

  if (loading) {
    return (
      <div
        style={{
          minHeight: "100%",
          padding: "24px",
          background: "#EEF4F1",
          fontFamily: "'Inter', sans-serif",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
        role="status"
        aria-live="polite"
      >
        <div
          style={{
            background: "#FFFFFF",
            border: "1px solid #E3ECE7",
            borderRadius: "14px",
            padding: "28px 36px",
            color: "#64748B",
            fontSize: "14px",
            fontWeight: 600,
            boxShadow:
              "0 4px 14px rgba(15, 23, 42, 0.06)",
          }}
        >
          Loading job tracking...
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        minHeight: "100%",
        padding: "24px",
        overflowY: "auto",
        background: "#EEF4F1",
        fontFamily: "'Inter', sans-serif",
        boxSizing: "border-box",
      }}
    >
      {/* PAGE HEADER */}
      <div
        style={{
          marginBottom: "20px",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "12px",
            flexWrap: "wrap",
          }}
        >
          <div>
            <h2
              style={{
                fontSize: "22px",
                fontWeight: 700,
                color: "#1F2933",
                display: "flex",
                alignItems: "center",
                gap: "8px",
                margin: 0,
              }}
            >
              <Navigation
                size={22}
                color="#7AAE8A"
              />

              Real-Time Job Tracking
            </h2>

            <p
              style={{
                fontSize: "13px",
                color: "#6B7280",
                marginTop: "6px",
                marginBottom: 0,
              }}
            >
              Track technician assignment,
              location and service status.
            </p>
          </div>

          {refreshing && (
            <div
              style={{
                fontSize: "12px",
                color: "#64748B",
                display: "flex",
                alignItems: "center",
                gap: "6px",
              }}
            >
              Updating...
            </div>
          )}
        </div>
      </div>

      {error && (
        <div
          role="alert"
          style={{
            marginBottom: "14px",
            padding: "12px 14px",
            borderRadius: "10px",
            border: "1px solid #FCD34D",
            background: "#FFFBEB",
            color: "#92400E",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "12px",
            flexWrap: "wrap",
            fontSize: "13px",
          }}
        >
          <span>{error}</span>

          <button
            type="button"
            onClick={() => setError(null)}
            style={{
              border: "1px solid #D97706",
              borderRadius: "8px",
              background: "#FFFFFF",
              color: "#92400E",
              padding: "7px 12px",
              fontSize: "12px",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* NO JOBS */}
      {jobs.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: "48px",
            color: "#9CA3AF",
            background: "#FFFFFF",
            borderRadius: "14px",
            border: "1px solid #E3ECE7",
            boxShadow:
              "0 2px 8px rgba(0,0,0,0.04)",
          }}
        >
          No active or tracked jobs found.
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns:
              "repeat(auto-fit, minmax(280px, 1fr))",
            gap: "14px",
          }}
        >
          {jobs.map((job) => {
            const rawStatus =
              normalizeJobStatus(job.status);

            const shownStatus =
              displayJobStatus(job.status);

            const style =
              statusStyle[shownStatus] || {
                bg: "#E5E7EB",
                fg: "#374151",
              };

            const isTerminal =
              TERMINAL_STATUSES.has(
                rawStatus
              );

            const customerLat =
              toFiniteNumber(
                job.site_latitude
              );

            const customerLng =
              toFiniteNumber(
                job.site_longitude
              );

            const canTrackLive =
              rawStatus === "EN_ROUTE" &&
              customerLat !== null &&
              customerLng !== null &&
              !isTerminal;

            const address =
              getJobAddress(job);

            return (
              <div
                key={String(job.id)}
                style={{
                  background: "#FFFFFF",
                  borderRadius: "14px",
                  padding: "20px",
                  boxShadow:
                    "0 2px 8px rgba(0,0,0,0.05)",
                  border:
                    "1px solid #E3ECE7",
                  boxSizing: "border-box",
                }}
              >
                {/* TOP ROW */}
                <div
                  style={{
                    display: "flex",
                    justifyContent:
                      "space-between",
                    alignItems:
                      "flex-start",
                    marginBottom: "14px",
                    gap: "10px",
                  }}
                >
                  <div
                    style={{
                      minWidth: 0,
                    }}
                  >
                    <span
                      style={{
                        fontSize: "11px",
                        color: "#9CA3AF",
                        fontWeight: 600,
                      }}
                    >
                      JOB #{job.id}
                    </span>

                    <div
                      style={{
                        fontSize: "16px",
                        fontWeight: 700,
                        color: "#1F2933",
                        marginTop: "3px",
                      }}
                    >
                      {job.service_type ||
                        "Service Request"}
                    </div>
                  </div>

                  <span
                    style={{
                      flexShrink: 0,
                      fontSize: "11px",
                      fontWeight: 600,
                      padding: "5px 11px",
                      borderRadius: "20px",
                      background: style.bg,
                      color: style.fg,
                    }}
                  >
                    {shownStatus}
                  </span>
                </div>

                {/* LOCATION */}
                <div
                  style={{
                    display: "flex",
                    alignItems:
                      "flex-start",
                    gap: "8px",
                    marginBottom: "12px",
                    fontSize: "13px",
                    color: "#4B5563",
                    lineHeight: 1.45,
                  }}
                >
                  <MapPin
                    size={15}
                    color="#6B7280"
                    style={{
                      flexShrink: 0,
                      marginTop: "2px",
                    }}
                  />

                  <div>
                    <div
                      style={{
                        fontWeight: 600,
                        color: "#374151",
                      }}
                    >
                      Service location
                    </div>

                    <div
                      style={{
                        color: "#64748B",
                        marginTop: "2px",
                        wordBreak:
                          "break-word",
                      }}
                    >
                      {address}
                    </div>
                  </div>
                </div>

                {/* JOB DATES */}
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "7px",
                    marginBottom: "16px",
                    fontSize: "12px",
                    color: "#64748B",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "7px",
                    }}
                  >
                    <Clock size={14} />

                    Created:{" "}
                    {job.created_at
                      ? new Date(
                          job.created_at
                        ).toLocaleDateString()
                      : "N/A"}
                  </div>

                  {job.completed_at && (
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "7px",
                      }}
                    >
                      <Clock size={14} />

                      Completed:{" "}
                      {new Date(
                        job.completed_at
                      ).toLocaleDateString()}
                    </div>
                  )}
                </div>

                {/* TECHNICIAN */}
                <div
                  style={{
                    background: "#F8FAFC",
                    borderRadius: "10px",
                    padding: "14px",
                    border:
                      "1px solid #E2E8F0",
                  }}
                >
                  <div
                    style={{
                      fontSize: "12px",
                      fontWeight: 700,
                      color: "#64748B",
                      textTransform:
                        "uppercase",
                      letterSpacing:
                        "0.5px",
                      marginBottom: "9px",
                      display: "flex",
                      alignItems:
                        "center",
                      gap: "6px",
                    }}
                  >
                    <ShieldCheck
                      size={14}
                      color="#7AAE8A"
                    />

                    Assigned Field Technician
                  </div>

                  {job.assigned_technician_name ? (
                    <div
                      style={{
                        display: "flex",
                        alignItems:
                          "center",
                        gap: "12px",
                      }}
                    >
                      {job.assigned_technician_photo ? (
                        <img
                          src={
                            job.assigned_technician_photo
                          }
                          alt={
                            job.assigned_technician_name
                          }
                          style={{
                            width: "44px",
                            height: "44px",
                            borderRadius:
                              "50%",
                            objectFit:
                              "cover",
                            flexShrink: 0,
                          }}
                        />
                      ) : (
                        <div
                          style={{
                            width: "44px",
                            height: "44px",
                            borderRadius:
                              "50%",
                            background:
                              "#CBD5E1",
                            display:
                              "flex",
                            alignItems:
                              "center",
                            justifyContent:
                              "center",
                            color:
                              "#475569",
                            flexShrink: 0,
                          }}
                        >
                          <User size={22} />
                        </div>
                      )}

                      <div
                        style={{
                          minWidth: 0,
                        }}
                      >
                        <div
                          style={{
                            fontSize: "14px",
                            fontWeight: 700,
                            color: "#1E293B",
                          }}
                        >
                          {
                            job.assigned_technician_name
                          }
                        </div>

                        {job.assigned_technician_phone && (
                          <a
                            href={`tel:${job.assigned_technician_phone}`}
                            aria-label={`Call ${job.assigned_technician_name}`}
                            style={{
                              fontSize: "12px",
                              color: "#64748B",
                              display:
                                "flex",
                              alignItems:
                                "center",
                              gap: "4px",
                              marginTop:
                                "3px",
                              textDecoration:
                                "none",
                            }}
                          >
                            <Phone
                              size={12}
                            />

                            {
                              job.assigned_technician_phone
                            }
                          </a>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div
                      style={{
                        fontSize: "13px",
                        color: "#94A3B8",
                        fontStyle:
                          "italic",
                      }}
                    >
                      Waiting for dispatcher
                      to assign a technician...
                    </div>
                  )}

                  {job.assigned_technician_name && (
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns:
                          "repeat(auto-fit, minmax(150px, 1fr))",
                        gap: "10px",
                        marginTop: "14px",
                      }}
                    >
                      {job.assigned_technician_skills &&
                        job.assigned_technician_skills.length > 0 && (
                          <div
                            style={{
                              padding: "10px",
                              borderRadius: "8px",
                              background: "#FFFFFF",
                              border: "1px solid #E2E8F0",
                            }}
                          >
                            <div
                              style={{
                                fontSize: "11px",
                                fontWeight: 700,
                                color: "#64748B",
                                textTransform: "uppercase",
                                letterSpacing: "0.4px",
                                marginBottom: "5px",
                              }}
                            >
                              Skills
                            </div>

                            <div
                              style={{
                                fontSize: "12px",
                                color: "#334155",
                                lineHeight: 1.45,
                              }}
                            >
                              {job.assigned_technician_skills.join(", ")}
                            </div>
                          </div>
                        )}

                      {job.assigned_technician_experience && (
                        <div
                          style={{
                            padding: "10px",
                            borderRadius: "8px",
                            background: "#FFFFFF",
                            border: "1px solid #E2E8F0",
                          }}
                        >
                          <div
                            style={{
                              fontSize: "11px",
                              fontWeight: 700,
                              color: "#64748B",
                              textTransform: "uppercase",
                              letterSpacing: "0.4px",
                              marginBottom: "5px",
                            }}
                          >
                            Experience
                          </div>

                          <div
                            style={{
                              fontSize: "12px",
                              color: "#334155",
                              lineHeight: 1.45,
                            }}
                          >
                            {job.assigned_technician_experience}
                          </div>
                        </div>
                      )}

                      {job.assigned_technician_certifications &&
                        job.assigned_technician_certifications.length > 0 && (
                          <div
                            style={{
                              padding: "10px",
                              borderRadius: "8px",
                              background: "#FFFFFF",
                              border: "1px solid #E2E8F0",
                            }}
                          >
                            <div
                              style={{
                                fontSize: "11px",
                                fontWeight: 700,
                                color: "#64748B",
                                textTransform: "uppercase",
                                letterSpacing: "0.4px",
                                marginBottom: "5px",
                              }}
                            >
                              Certifications
                            </div>

                            <div
                              style={{
                                fontSize: "12px",
                                color: "#334155",
                                lineHeight: 1.45,
                              }}
                            >
                              {job.assigned_technician_certifications.join(", ")}
                            </div>
                          </div>
                        )}
                    </div>
                  )}

                  {job.assigned_technician_name &&
                    !job.assigned_technician_phone &&
                    !job.assigned_technician_skills?.length &&
                    !job.assigned_technician_experience &&
                    !job.assigned_technician_certifications?.length && (
                      <div
                        style={{
                          marginTop: "10px",
                          fontSize: "12px",
                          color: "#94A3B8",
                          fontStyle: "italic",
                        }}
                      >
                        Additional technician details are currently unavailable.
                      </div>
                    )}
                </div>

                {/* ETA */}
                {job.assigned_technician_id != null && (
                  <div
                    data-testid={`eta-card-${job.id}`}
                    style={{
                      marginTop: "12px",
                      padding: "14px",
                      borderRadius: "10px",
                      background:
                        job.eta_status === "calculated"
                          ? "#F0FDF4"
                          : job.eta_status === "estimated"
                            ? "#FFFBEB"
                            : "#F8FAFC",
                      border:
                        job.eta_status === "calculated"
                          ? "1px solid #BBF7D0"
                          : job.eta_status === "estimated"
                            ? "1px solid #FDE68A"
                            : "1px solid #E2E8F0",
                    }}
                  >
                    {job.estimated_arrival ? (
                      <>
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: "10px",
                            flexWrap: "wrap",
                          }}
                        >
                          <div>
                            <div
                              style={{
                                fontSize: "11px",
                                fontWeight: 700,
                                color: "#64748B",
                                textTransform: "uppercase",
                                letterSpacing: "0.5px",
                              }}
                            >
                              Estimated Arrival
                            </div>

                            <div
                              style={{
                                fontSize: "20px",
                                fontWeight: 800,
                                color:
                                  job.eta_status === "calculated"
                                    ? "#166534"
                                    : "#92400E",
                                marginTop: "4px",
                              }}
                            >
                              {formatEtaTime(job.estimated_arrival) ||
                                "ETA unavailable"}
                            </div>
                          </div>

                          <span
                            style={{
                              fontSize: "11px",
                              fontWeight: 700,
                              padding: "5px 9px",
                              borderRadius: "999px",
                              background:
                                job.eta_status === "calculated"
                                  ? "#DCFCE7"
                                  : "#FEF3C7",
                              color:
                                job.eta_status === "calculated"
                                  ? "#166534"
                                  : "#92400E",
                            }}
                          >
                            {job.eta_status === "calculated"
                              ? "LIVE ETA"
                              : job.eta_status === "estimated"
                                ? "ESTIMATED"
                                : "ETA"}
                          </span>
                        </div>

                        {formatEtaDuration(job.eta_duration_minutes) && (
                          <div
                            style={{
                              marginTop: "6px",
                              fontSize: "12px",
                              color: "#475569",
                              fontWeight: 600,
                            }}
                          >
                            Approximate travel time: {formatEtaDuration(job.eta_duration_minutes)}
                          </div>
                        )}

                        {job.eta_distance_km != null && (
                          <div
                            style={{
                              marginTop: "4px",
                              fontSize: "12px",
                              color: "#64748B",
                            }}
                          >
                            Route distance: {Number(job.eta_distance_km).toFixed(1)} km
                          </div>
                        )}

                        {job.eta_traffic_delay_minutes != null &&
                          Number(job.eta_traffic_delay_minutes) > 0 && (
                            <div
                              style={{
                                marginTop: "4px",
                                fontSize: "12px",
                                color: "#92400E",
                              }}
                            >
                              Traffic delay: +{Math.round(Number(job.eta_traffic_delay_minutes))} min
                            </div>
                          )}

                        {job.eta_message && (
                          <div
                            style={{
                              marginTop: "7px",
                              fontSize: "12px",
                              color: "#64748B",
                              lineHeight: 1.45,
                            }}
                          >
                            {job.eta_message}
                          </div>
                        )}

                        {job.eta_updated_at && (
                          <div
                            style={{
                              marginTop: "7px",
                              fontSize: "11px",
                              color: "#94A3B8",
                            }}
                          >
                            Updated {new Date(job.eta_updated_at).toLocaleTimeString([], {
                              hour: "numeric",
                              minute: "2-digit",
                              second: "2-digit",
                            })}
                          </div>
                        )}
                      </>
                    ) : (
                      <div>
                        <div
                          style={{
                            fontSize: "12px",
                            fontWeight: 700,
                            color: "#64748B",
                            textTransform: "uppercase",
                            letterSpacing: "0.5px",
                          }}
                        >
                          Estimated Arrival
                        </div>

                        <div
                          style={{
                            marginTop: "5px",
                            fontSize: "13px",
                            color: "#64748B",
                          }}
                        >
                          {job.eta_message ||
                            "ETA is currently unavailable. The latest route data could not be provided."}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* TERMINAL STATUS */}
                {isTerminal && (
                  <div
                    style={{
                      marginTop: "12px",
                      padding:
                        "11px 14px",
                      borderRadius: "9px",
                      background:
                        rawStatus === "CANCELLED"
                          ? "#FEF2F2"
                          : "#ECFDF5",
                      border:
                        rawStatus === "CANCELLED"
                          ? "1px solid #FECACA"
                          : "1px solid #A7F3D0",
                      color:
                        rawStatus === "CANCELLED"
                          ? "#991B1B"
                          : "#065F46",
                      fontSize: "13px",
                      fontWeight: 700,
                      textAlign:
                        "center",
                    }}
                  >
                    {rawStatus === "CANCELLED"
                      ? "✕ Service Cancelled"
                      : "✓ Service Completed"}
                  </div>
                )}

                {/* LIVE MAP */}
                {canTrackLive && (
                  <button
                    type="button"
                    onClick={() =>
                      setLiveJob(job)
                    }
                    style={{
                      width: "100%",
                      marginTop: "12px",
                      padding:
                        "11px 14px",
                      border: 0,
                      borderRadius: "9px",
                      background:
                        "#2563EB",
                      color: "#FFFFFF",
                      fontWeight: 700,
                      cursor: "pointer",
                      display:
                        "flex",
                      alignItems:
                        "center",
                      justifyContent:
                        "center",
                      gap: "7px",
                      transition:
                        "opacity 0.2s ease",
                    }}
                    onMouseEnter={(event) => {
                      event.currentTarget.style.opacity =
                        "0.9";
                    }}
                    onMouseLeave={(event) => {
                      event.currentTarget.style.opacity =
                        "1";
                    }}
                  >
                    <Navigation size={15} />

                    LIVE MAP
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* LIVE TRACKING MODAL */}
      {shouldShowLiveMap && liveJob && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 10000,
            background:
              "rgba(15,23,42,0.65)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "20px",
            boxSizing: "border-box",
          }}
        >
          <div
            style={{
              width:
                "min(1100px, 96vw)",
              height:
                "min(760px, 92vh)",
              background:
                "#FFFFFF",
              borderRadius: "16px",
              overflow: "hidden",
              boxShadow:
                "0 25px 60px rgba(0,0,0,0.25)",
              display: "flex",
              flexDirection:
                "column",
            }}
          >
            {/* MAP HEADER */}
            <div
              style={{
                padding:
                  "14px 18px",
                display: "flex",
                justifyContent:
                  "space-between",
                alignItems:
                  "center",
                gap: "12px",
                borderBottom:
                  "1px solid #E5E7EB",
                background:
                  "#FFFFFF",
                flexShrink: 0,
              }}
            >
              <div
                style={{
                  minWidth: 0,
                }}
              >
                <strong
                  style={{
                    display: "block",
                    fontSize: "15px",
                    color: "#111827",
                  }}
                >
                  Live Technician Tracking
                </strong>

                <div
                  style={{
                    fontSize: "12px",
                    color: "#64748B",
                    marginTop: "3px",
                    whiteSpace:
                      "nowrap",
                    overflow:
                      "hidden",
                    textOverflow:
                      "ellipsis",
                  }}
                >
                  Job #{liveJob.id} •{" "}
                  {getJobAddress(
                    liveJob
                  )}
                </div>
              </div>

              <button
                type="button"
                aria-label="Close live tracking"
                onClick={() =>
                  setLiveJob(null)
                }
                style={{
                  width: "36px",
                  height: "36px",
                  border: 0,
                  borderRadius:
                    "9px",
                  background:
                    "#F1F5F9",
                  color: "#475569",
                  cursor: "pointer",
                  display:
                    "flex",
                  alignItems:
                    "center",
                  justifyContent:
                    "center",
                  flexShrink: 0,
                }}
              >
                <X size={19} />
              </button>
            </div>

            {/* MAP */}
            <div
              style={{
                flex: 1,
                minHeight: 0,
                position:
                  "relative",
              }}
            >
             <JobLiveTrackingMap 
                jobId={liveJob.id}
                customerLatitude={
                  toFiniteNumber(
                    liveJob.site_latitude
                  )
                }
                customerLongitude={
                  toFiniteNumber(
                    liveJob.site_longitude
                  )
                }
                technicianLatitude={
                  toFiniteNumber(
                    liveJob.technician_latitude
                  )
                }
                technicianLongitude={
                  toFiniteNumber(
                    liveJob.technician_longitude
                  )
                }
                technicianId={
                  liveJob.assigned_technician_id
                }
                mode="customer"
                tenantId={
                  localStorage.getItem(
                    "tenant_id"
                  ) || ""
                }
                trackingTenantId={
                  liveJob.tracking_tenant_id
                }
                buildingAddress={getJobAddress(
                  liveJob
                )}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
