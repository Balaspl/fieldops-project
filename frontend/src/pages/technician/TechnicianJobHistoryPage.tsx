import { useState, useEffect } from "react";
import { History, MapPin, Clock, CheckCircle, MessageSquare } from "lucide-react";
import { getTechnicianJobHistory } from "../../services/technicianPortalService";
import JobMessagePanel from "../../components/customer-tracking/JobMessagePanel";

export default function TechnicianJobHistoryPage() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [messageJobId, setMessageJobId] = useState<number | null>(null);

  useEffect(() => {
    getTechnicianJobHistory()
      .then(r => setJobs(r.data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

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
      <h2
        style={{
          fontSize: "22px",
          fontWeight: 700,
          color: "#1F2933",
          marginBottom: "20px",
          display: "flex",
          alignItems: "center",
          gap: "8px",
        }}
      >
        <History size={22} color="#7AAE8A" />
        Job History
      </h2>

      {loading ? (
        <div
          style={{
            textAlign: "center",
            padding: "48px",
            color: "#9CA3AF",
          }}
        >
          Loading...
        </div>
      ) : jobs.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: "48px",
            color: "#9CA3AF",
          }}
        >
          No completed jobs yet
        </div>
      ) : (
        jobs.map(job => (
          <div
            key={job.id}
            style={{
              background: "#fff",
              borderRadius: "14px",
              padding: "18px",
              marginBottom: "12px",
              boxShadow: "0 2px 8px rgba(0,0,0,0.05)",
              border: "1px solid #E3ECE7",
            }}
          >
            {/* Job Header */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "8px",
              }}
            >
              <div>
                <span
                  style={{
                    fontSize: "11px",
                    color: "#9CA3AF",
                  }}
                >
                  JOB #{job.id}
                </span>

                <div
                  style={{
                    fontSize: "15px",
                    fontWeight: 700,
                    color: "#1F2933",
                  }}
                >
                  {job.service_type || "Service"}
                </div>
              </div>

              {/* Completed Status */}
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "6px",
                  background: String(job.status).toUpperCase() === "CANCELLED" ? "#B91C1C" : "#059669",
                  color: "#FFFFFF",
                  border: "1px solid #047857",
                  borderRadius: "8px",
                  padding: "9px 18px",
                  minWidth: "110px",
                  height: "38px",
                  fontSize: "12px",
                  fontWeight: 700,
                  cursor: "default",
                  boxShadow: "0 2px 5px rgba(0,0,0,0.15)",
                  boxSizing: "border-box",
                }}
              >
                <CheckCircle size={15} />
                {String(job.status || "COMPLETED").toUpperCase()}
              </span>
            </div>

            {/* Location and Completion Date */}
            <div
              style={{
                display: "flex",
                gap: "16px",
                fontSize: "13px",
                color: "#6B7280",
              }}
            >
              <span
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "4px",
                }}
              >
                <MapPin size={13} />
                {job.location || "N/A"}
              </span>

              <span
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "4px",
                }}
              >
                <Clock size={13} />
                {job.completed_at
                  ? new Date(job.completed_at).toLocaleDateString()
                  : "N/A"}
              </span>
            </div>

            {/* Customer */}
            {job.customer_name && (
              <div
                style={{
                  fontSize: "13px",
                  color: "#6B7280",
                  marginTop: "4px",
                }}
              >
                Customer: {job.customer_name}
              </div>
            )}
            <button type="button" onClick={() => setMessageJobId(Number(job.id))} style={{ marginTop: "12px", padding: "9px 12px", border: 0, borderRadius: "8px", background: "#156B5B", color: "#FFFFFF", fontSize: "12px", fontWeight: 700, display: "inline-flex", alignItems: "center", gap: "7px", cursor: "pointer" }}>
              <MessageSquare size={15} /> View Messages
            </button>
          </div>
        ))
      )}
      {messageJobId !== null && <JobMessagePanel jobId={messageJobId} onClose={() => setMessageJobId(null)} />}
    </div>
  );
}
