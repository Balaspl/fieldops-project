import { useState, useEffect } from "react";
import {
  FileText,
  CheckCircle,
  Clock,
  PlusCircle,
  ArrowRight,
} from "lucide-react";
import {
  getCustomerDashboard,
  getServiceRequests,
} from "../../services/customerPortalService";

export default function CustomerPortalDashboard({
  onNavigate,
}: {
  onNavigate: (tab: string) => void;
}) {
  const [stats, setStats] = useState<any>(null);
  const [recent, setRecent] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getCustomerDashboard(), getServiceRequests()])
      .then(([dRes, srRes]) => {
        setStats(dRes.data);
        setRecent((srRes.data || []).slice(0, 5));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const cards = [
    {
      label: "Total Requests",
      value: stats?.total_requests ?? 0,
      icon: <FileText size={20} />,
      bg: "#E8F5E9",
      color: "#2E7D32",
    },
    {
      label: "Unassigned",
      value: stats?.pending_requests ?? 0,
      icon: <Clock size={20} />,
      bg: "#FFF8E1",
      color: "#F57F17",
    },
    {
      label: "Active Jobs",
      value: stats?.active_jobs ?? 0,
      icon: <PlusCircle size={20} />,
      bg: "#E3F2FD",
      color: "#1565C0",
    },
    {
      label: "Completed",
      value: stats?.completed_jobs ?? 0,
      icon: <CheckCircle size={20} />,
      bg: "#F3E5F5",
      color: "#7B1FA2",
    },
  ];

  const statusColor: Record<string, string> = {
    UNASSIGNED: "#DD6B20",
    ASSIGNED: "#1E40AF",
    EN_ROUTE: "#7C3AED",
    IN_PROGRESS: "#92400E",
    COMPLETED: "#065F46",
    CANCELLED: "#991B1B",
  };

  if (loading)
    return (
      <div
        style={{
          padding: "24px",
          background: "#EEF4F1",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#9CA3AF",
        }}
      >
        Loading dashboard...
      </div>
    );

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
      <div
        style={{
          marginBottom: "24px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <div>
          <h1
            style={{
              fontSize: "24px",
              fontWeight: 700,
              color: "#1F2933",
              margin: 0,
            }}
          >
            Customer Dashboard
          </h1>

          <p
            style={{
              fontSize: "14px",
              color: "#6B7280",
              marginTop: "4px",
            }}
          >
            Track your service requests and jobs
          </p>
        </div>

        <button
          onClick={() => onNavigate("cust_create_request")}
          style={{
            padding: "12px 20px",
            border: "none",
            borderRadius: "10px",
            background: "#7AB38A",
            color: "#fff",
            fontSize: "14px",
            fontWeight: 700,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <PlusCircle size={18} />
          New Request
        </button>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          gap: "16px",
          marginBottom: "28px",
        }}
      >
        {cards.map((c, i) => (
          <div
            key={i}
            style={{
              background: "#fff",
              borderRadius: "14px",
              padding: "20px",
              boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
              border: "1px solid #E3ECE7",
            }}
          >
            <div
              style={{
                width: "40px",
                height: "40px",
                borderRadius: "10px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: c.bg,
                color: c.color,
                marginBottom: "8px",
              }}
            >
              {c.icon}
            </div>
            <div
              style={{ fontSize: "12px", color: "#6B7280", fontWeight: 500 }}
            >
              {c.label}
            </div>
            <div
              style={{ fontSize: "28px", fontWeight: 700, color: "#1F2933" }}
            >
              {c.value}
            </div>
          </div>
        ))}
      </div>

      {/* <div style={{ display: "flex", gap: "16px", marginBottom: "28px" }}>
        <button onClick={() => onNavigate("cust_create_request")} style={{ padding: "14px 28px", border: "none", borderRadius: "12px", background: "#7AAE8A", color: "#fff", fontSize: "14px", fontWeight: 700, cursor: "pointer", display: "flex", alignItems: "center", gap: "8px", boxShadow: "0 4px 12px rgba(122,174,138,0.3)" }}>
          <PlusCircle size={18} /> Create Service Request
        </button>
      </div> */}

      <div
        style={{
          background: "#fff",
          borderRadius: "14px",
          padding: "20px",
          boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
          border: "1px solid #E3ECE7",
        }}
      >
        <div
          style={{
            fontSize: "16px",
            fontWeight: 700,
            color: "#1F2933",
            marginBottom: "16px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <FileText size={18} color="#7AAE8A" /> Recent Requests
        </div>
        {recent.length === 0 ? (
          <div
            style={{
              textAlign: "center",
              color: "#9CA3AF",
              padding: "32px",
              fontSize: "14px",
            }}
          >
            No service requests yet
          </div>
        ) : (
          recent.map((sr: any) => (
            <div
              key={sr.id}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "12px 0",
                borderBottom: "1px solid #f0f0f0",
              }}
            >
              <div>
                <div
                  style={{
                    fontSize: "14px",
                    fontWeight: 600,
                    color: "#1F2933",
                  }}
                >
                  {sr.title}
                </div>
                <div style={{ fontSize: "12px", color: "#6B7280" }}>
                  {sr.request_number} •{" "}
                  {new Date(sr.created_at).toLocaleDateString()}
                </div>
              </div>
              <span
                style={{
                  fontSize: "11px",
                  fontWeight: 600,
                  padding: "3px 10px",
                  borderRadius: "20px",
                  background: (statusColor[sr.status] || "#6B7280") + "18",
                  color: statusColor[sr.status] || "#6B7280",
                }}
              >
                {sr.status}
              </span>
            </div>
          ))
        )}
        {recent.length > 0 && (
          <button
            onClick={() => onNavigate("cust_requests")}
            style={{
              marginTop: "12px",
              background: "none",
              border: "none",
              color: "#7AAE8A",
              fontSize: "13px",
              fontWeight: 600,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "4px",
            }}
          >
            View All <ArrowRight size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
