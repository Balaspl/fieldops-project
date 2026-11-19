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
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = async () => {
    setLoading(true);
    setError(null);

    try {
      // Both values come from the backend's authenticated customer scope.
      // The client does not supply or calculate tenant/object ownership.
      const [dRes, srRes] = await Promise.all([
        getCustomerDashboard(),
        getServiceRequests(),
      ]);

      setStats(dRes.data);
      setRecent(
        Array.isArray(srRes.data)
          ? srRes.data.slice(0, 5)
          : [],
      );
    } catch (err: any) {
      const status = err?.response?.status;

      if (status === 401) {
        setError(
          "Your session has expired. Please sign in again.",
        );
      } else if (status === 403) {
        setError(
          "You do not have permission to access the customer portal.",
        );
      } else {
        setError(
          "We couldn't load your customer dashboard. Please try again.",
        );
      }

      // Avoid displaying stale data after an unsuccessful refresh.
      setStats(null);
      setRecent([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadDashboard();
  }, []);

  const cards = [
    {
      label: "TOTAL REQUESTS",
      value: stats?.total_requests ?? 0,
      icon: <FileText size={20} />,
      bg: "#E8F8F2",
      color: "#059669",
    },
    {
      label: "UNASSIGNED",
      value: stats?.pending_requests ?? 0,
      icon: <Clock size={20} />,
      bg: "#FFFBEB",
      color: "#D97706",
    },
    {
      label: "ACTIVE JOBS",
      value: stats?.active_jobs ?? 0,
      icon: <PlusCircle size={20} />,
      bg: "#EFF6FF",
      color: "#2563EB",
    },
    {
      label: "COMPLETED",
      value: stats?.completed_jobs ?? 0,
      icon: <CheckCircle size={20} />,
      bg: "#F5F3FF",
      color: "#7C3AED",
    },
  ];

  const statusColor: Record<string, string> = {
    UNASSIGNED: "#DD6B20",
    "AWAITING ACCEPTANCE": "#1E40AF",
    ASSIGNED: "#1E40AF",
    "EN ROUTE": "#7C3AED",
    "IN_PROGRESS": "#92400E",
    COMPLETED: "#065F46",
    CANCELLED: "#991B1B",
  };

  if (loading)
    return (
      <div
        style={{
          padding: "24px",
          background: "#F8FAFC",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#9CA3AF",
        }}
        role="status"
        aria-live="polite"
      >
        Loading dashboard...
      </div>
    );

  if (error)
    return (
      <div
        style={{
          padding: "24px",
          height: "100%",
          overflowY: "auto",
          background: "#F8FAFC",
          fontFamily: "'Inter', sans-serif",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div
          style={{
            width: "100%",
            maxWidth: "520px",
            background: "#fff",
            borderRadius: "14px",
            padding: "28px",
            border: "1px solid #E3ECE7",
            boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
            textAlign: "center",
          }}
          role="alert"
        >
          <div
            style={{
              fontSize: "16px",
              fontWeight: 700,
              color: "#1F2933",
              marginBottom: "8px",
            }}
          >
            Unable to load customer dashboard
          </div>

          <div
            style={{
              fontSize: "14px",
              lineHeight: 1.5,
              color: "#6B7280",
              marginBottom: "18px",
            }}
          >
            {error}
          </div>

          <button
            type="button"
            onClick={() => void loadDashboard()}
            style={{
              padding: "10px 18px",
              border: "none",
              borderRadius: "10px",
              background: "#7AB38A",
              color: "#fff",
              fontSize: "14px",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            Try Again
          </button>
        </div>
      </div>
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
            background: "#1E6B52",
            color: "#fff",
            fontSize: "14px",
            fontWeight: 700,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
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
              borderRadius: "16px",
              padding: "22px 24px",
              boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
              border: "1px solid #F1F5F9",
            }}
          >
            <div
              style={{
                width: "42px",
                height: "42px",
                borderRadius: "12px",
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
              style={{
                fontSize: "11px",
                color: "#64748B",
                fontWeight: 700,
                letterSpacing: "0.06em",
                marginTop: "12px",
                marginBottom: "4px",
              }}
            >
              {c.label}
            </div>
            <div
              style={{ fontSize: "32px", fontWeight: 700, color: "#0F172A" }}
            >
              {c.value}
            </div>
          </div>
        ))}
      </div>

      <div
        style={{
          background: "#fff",
          borderRadius: "16px",
          padding: "24px",
          boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
          border: "1px solid #F1F5F9",
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
          <FileText size={20} color="#059669" /> Recent Requests
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
                  background:
                    (statusColor[
                      sr.status === "CREATED"
                        ? "UNASSIGNED"
                        : sr.status === "ASSIGNED"
                        ? "AWAITING ACCEPTANCE"
                        : sr.status === "ACCEPTED"
                        ? "ASSIGNED"
                        : sr.status === "EN_ROUTE"
                        ? "EN ROUTE"
                        : sr.status === "IN_PROGRESS"
                        ? "IN_PROGRESS"
                        : sr.status
                    ] || "#6B7280") + "18",
                  color:
                    statusColor[
                      sr.status === "CREATED"
                        ? "UNASSIGNED"
                        : sr.status === "ASSIGNED"
                        ? "AWAITING ACCEPTANCE"
                        : sr.status === "ACCEPTED"
                        ? "ASSIGNED"
                        : sr.status === "EN_ROUTE"
                        ? "EN ROUTE"
                        : sr.status === "IN_PROGRESS"
                        ? "IN_PROGRESS"
                        : sr.status
                    ] || "#6B7280",
                }}
              >
                {sr.status === "CREATED"
                  ? "UNASSIGNED"
                  : sr.status === "ASSIGNED"
                  ? "AWAITING ACCEPTANCE"
                  : sr.status === "ACCEPTED"
                  ? "ASSIGNED"
                  : sr.status === "EN_ROUTE"
                  ? "EN ROUTE"
                  : sr.status === "IN_PROGRESS"
                  ? "IN_PROGRESS"
                  : sr.status}
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
              color: "#059669",
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