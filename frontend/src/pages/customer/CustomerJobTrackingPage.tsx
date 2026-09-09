import { useState, useEffect } from "react";
import {
  Navigation,
  User,
  Phone,
  MapPin,
  Clock,
  ShieldCheck,
} from "lucide-react";
import { getCustomerJobs } from "../../services/customerPortalService";

const statusStyle: Record<string, { bg: string; fg: string }> = {
  ASSIGNED: { bg: "#DBEAFE", fg: "#1E40AF" },
  ACCEPTED: { bg: "#D1FAE5", fg: "#065F46" },
  IN_PROGRESS: { bg: "#FEF3C7", fg: "#92400E" },
  EN_ROUTE: { bg: "#EDE9FE", fg: "#5B21B6" },
  COMPLETED: { bg: "#D1FAE5", fg: "#065F46" },
  CLOSED: { bg: "#E5E7EB", fg: "#374151" },
};

export default function CustomerJobTrackingPage() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getCustomerJobs()
      .then((r) => setJobs(r.data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div
        style={{
          padding: "24px",
          background: "#EEF4F1",
          height: "100%",
          textAlign: "center",
          paddingTop: "80px",
          color: "#9CA3AF",
        }}
      >
        Loading job tracking...
      </div>
    );
  }

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
      <div style={{ marginBottom: "20px" }}>
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
          <Navigation size={22} color="#7AAE8A" />
          Real-Time Job Tracking
        </h2>

        <p
          style={{
            fontSize: "13px",
            color: "#6B7280",
            marginTop: "4px",
          }}
        >
          Track technician assignment and service status for your requests
        </p>
      </div>

      {jobs.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: "48px",
            color: "#9CA3AF",
            background: "#fff",
            borderRadius: "14px",
            border: "1px solid #E3ECE7",
          }}
        >
          No active or tracked jobs found.
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: "12px",
          }}
        >
          {jobs.map((job) => (
            <div
              key={job.id}
              style={{
                background: "#fff",
                borderRadius: "14px",
                padding: "20px",
                boxShadow: "0 2px 8px rgba(0,0,0,0.05)",
                border: "1px solid #E3ECE7",
              }}
            >
              {/* Top Row */}
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "flex-start",
                  marginBottom: "12px",
                  gap: "10px",
                }}
              >
                <div style={{ minWidth: 0 }}>
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
                      marginTop: "2px",
                    }}
                  >
                    {job.service_type || "Service Request"}
                  </div>
                </div>

                <span
                  style={{
                    flexShrink: 0,
                    fontSize: "11px",
                    fontWeight: 600,
                    padding: "4px 12px",
                    borderRadius: "20px",
                    background:
                      statusStyle[job.status]?.bg || "#E5E7EB",
                    color:
                      statusStyle[job.status]?.fg || "#374151",
                  }}
                >
                  {job.status}
                </span>
              </div>

              {/* Job Details */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr",
                  gap: "10px",
                  marginBottom: "16px",
                  fontSize: "13px",
                  color: "#4B5563",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                  }}
                >
                  <MapPin size={14} color="#6B7280" />
                  {job.location || "N/A"}
                </div>

                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                  }}
                >
                  <Clock size={14} color="#6B7280" />
                  Created:{" "}
                  {new Date(job.created_at).toLocaleDateString()}
                </div>
              </div>

              {/* Technician Card Section */}
              <div
                style={{
                  background: "#F8FAFC",
                  borderRadius: "10px",
                  padding: "14px",
                  border: "1px solid #E2E8F0",
                }}
              >
                <div
                  style={{
                    fontSize: "12px",
                    fontWeight: 700,
                    color: "#64748B",
                    textTransform: "uppercase",
                    letterSpacing: "0.5px",
                    marginBottom: "8px",
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                  }}
                >
                  <ShieldCheck size={14} color="#7AAE8A" />
                  Assigned Field Technician
                </div>

                {job.assigned_technician_name ? (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "12px",
                    }}
                  >
                    {job.assigned_technician_photo ? (
                      <img
                        src={job.assigned_technician_photo}
                        alt={job.assigned_technician_name}
                        style={{
                          width: "44px",
                          height: "44px",
                          borderRadius: "50%",
                          objectFit: "cover",
                        }}
                      />
                    ) : (
                      <div
                        style={{
                          width: "44px",
                          height: "44px",
                          borderRadius: "50%",
                          background: "#CBD5E1",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          color: "#475569",
                        }}
                      >
                        <User size={22} />
                      </div>
                    )}

                    <div style={{ minWidth: 0 }}>
                      <div
                        style={{
                          fontSize: "14px",
                          fontWeight: 700,
                          color: "#1E293B",
                        }}
                      >
                        {job.assigned_technician_name}
                      </div>

                      {job.assigned_technician_phone && (
                        <div
                          style={{
                            fontSize: "12px",
                            color: "#64748B",
                            display: "flex",
                            alignItems: "center",
                            gap: "4px",
                            marginTop: "2px",
                          }}
                        >
                          <Phone size={12} />
                          {job.assigned_technician_phone}
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <div
                    style={{
                      fontSize: "13px",
                      color: "#94A3B8",
                      fontStyle: "italic",
                    }}
                  >
                    Waiting for dispatcher to assign a technician...
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}