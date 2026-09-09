import { useState, useEffect } from "react";
import { History, Clock, CheckCircle } from "lucide-react";
import { getServiceHistory } from "../../services/customerPortalService";

export default function CustomerServiceHistoryPage() {
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getServiceHistory()
      .then((r) => setHistory(r.data || []))
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
      {/* Page Header */}
      <h2
        style={{
          fontSize: "22px",
          fontWeight: 700,
          color: "#1F2933",
          marginBottom: "18px",
          display: "flex",
          alignItems: "center",
          gap: "8px",
        }}
      >
        <History size={22} color="#7AAE8A" />
        Service History
      </h2>

      {/* Loading */}
      {loading ? (
        <div
          style={{
            textAlign: "center",
            padding: "40px",
            color: "#6B7280",
            fontSize: "14px",
          }}
        >
          Loading...
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
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            gap: "12px",
          }}
        >
          {history.map((sr) => {
            const isCompleted = sr.status === "COMPLETED";

            return (
              <div
                key={sr.id}
                style={{
                  background: "#FFFFFF",
                  borderRadius: "14px",
                  padding: "14px 18px",
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
                      justifyContent: "center",
                      fontSize: "11px",
                      fontWeight: 700,
                      lineHeight: "16px",
                      padding: "4px 11px",
                      borderRadius: "20px",
                      background: isCompleted ? "#D1FAE5" : "#FEE2E2",
                      color: isCompleted ? "#065F46" : "#991B1B",
                      whiteSpace: "nowrap",
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
                  <Clock size={13} color="#7C8794" />

                  <span>
                    Updated:{" "}
                    {new Date(sr.updated_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}