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

  assigned_technician_id?: string | null;
  assigned_technician_name?: string | null;
  assigned_technician_phone?: string | null;
  assigned_technician_photo?: string | null;

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
};

const TERMINAL_STATUSES = new Set([
  "COMPLETED",
  "CLOSED",
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

interface CustomerTrackingPageProps {
  token: string;
}

export default function CustomerTrackingPage({
  token,
}: CustomerTrackingPageProps)  {
  const [jobs, setJobs] = useState<CustomerJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const [liveJob, setLiveJob] =
    useState<CustomerJob | null>(null);

  /**
   * Load customer jobs.
   *
   * The polling is intentionally kept here because it also
   * detects when the technician completes the job.
   */
  useEffect(() => {
    let stopped = false;

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

        setJobs(nextJobs);
      } catch (error) {
        /*
         * Keep the previous successful data on transient
         * network/backend failures.
         */
        console.error(
          "Failed to load customer jobs:",
          error
        );
      } finally {
        if (!stopped) {
          setLoading(false);
          setRefreshing(false);
        }
      }
    };

    void loadJobs();

    const timer = window.setInterval(
      loadJobs,
      5000
    );

    return () => {
      stopped = true;
      window.clearInterval(timer);
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

                {/* CREATED DATE */}
                <div
                  style={{
                    display: "flex",
                    alignItems:
                      "center",
                    gap: "7px",
                    marginBottom: "16px",
                    fontSize: "12px",
                    color: "#64748B",
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
                          <div
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
                            }}
                          >
                            <Phone
                              size={12}
                            />

                            {
                              job.assigned_technician_phone
                            }
                          </div>
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
                </div>

                {/* COMPLETED */}
                {isTerminal && (
                  <div
                    style={{
                      marginTop: "12px",
                      padding:
                        "11px 14px",
                      borderRadius: "9px",
                      background:
                        "#ECFDF5",
                      border:
                        "1px solid #A7F3D0",
                      color: "#065F46",
                      fontSize: "13px",
                      fontWeight: 700,
                      textAlign:
                        "center",
                    }}
                  >
                    ✓ Service Completed
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
