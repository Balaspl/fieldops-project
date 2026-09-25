import { useState, useEffect } from "react";
import { Bell, Check, CheckCheck } from "lucide-react";
import { getCustomerNotifications, markCustomerNotificationRead, markAllCustomerNotificationsRead } from "../../services/customerPortalService";

export default function CustomerNotificationsPage() {
  const [notifications, setNotifications] = useState<any[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(true);

  const load = () => {
    getCustomerNotifications()
      .then((r) => {
        setNotifications(r.data.notifications || []);
        setUnread(r.data.unread_count || 0);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const markRead = async (id: string) => {
    await markCustomerNotificationRead(id);
    setNotifications((ns) => ns.map((n) => (n.id === id ? { ...n, isRead: true } : n)));
    setUnread((u) => Math.max(0, u - 1));
  };

  const markAllRead = async () => {
    await markAllCustomerNotificationsRead();
    setNotifications((ns) => ns.map((n) => ({ ...n, isRead: true })));
    setUnread(0);
  };

  return (
    <div style={{ padding: "24px", height: "100%", overflowY: "auto", background: "#EEF4F1", fontFamily: "'Inter', sans-serif" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
        <h2 style={{ fontSize: "22px", fontWeight: 700, color: "#1F2933", display: "flex", alignItems: "center", gap: "8px" }}>
          <Bell size={22} color="#7AAE8A" /> Notifications
          {unread > 0 && <span style={{ fontSize: "12px", background: "#E53E3E", color: "#fff", borderRadius: "20px", padding: "2px 8px", fontWeight: 700 }}>{unread}</span>}
        </h2>
        {unread > 0 && (
          <button onClick={markAllRead} style={{ background: "none", border: "1px solid #D1D5DB", borderRadius: "8px", padding: "6px 14px", fontSize: "12px", fontWeight: 600, color: "#374151", cursor: "pointer", display: "flex", alignItems: "center", gap: "5px" }}>
            <CheckCheck size={14} /> Mark All Read
          </button>
        )}
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: "48px", color: "#9CA3AF" }}>Loading...</div>
      ) : notifications.length === 0 ? (
        <div style={{ textAlign: "center", padding: "48px", color: "#9CA3AF", background: "#fff", borderRadius: "14px", border: "1px solid #E3ECE7" }}>No notifications yet</div>
      ) : (
        notifications.map((n) => (
          <div
            key={n.id}
            style={{
              background: n.isRead ? "#fff" : "#F0FFF4",
              borderRadius: "12px",
              padding: "14px 18px",
              marginBottom: "10px",
              boxShadow: "0 1px 4px rgba(0,0,0,0.04)",
              border: `1px solid ${n.isRead ? "#E3ECE7" : "#C6F6D5"}`,
              cursor: "pointer",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-start",
            }}
            onClick={() => !n.isRead && markRead(n.id)}
          >
            <div>
              <div style={{ fontSize: "14px", fontWeight: 600, color: "#1F2933" }}>{n.title}</div>
              <div style={{ fontSize: "13px", color: "#6B7280", marginTop: "2px" }}>{n.message}</div>
              <div style={{ fontSize: "11px", color: "#9CA3AF", marginTop: "4px" }}>{n.createdAt ? new Date(n.createdAt).toLocaleString() : ""}</div>
            </div>
            {!n.isRead && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  markRead(n.id);
                }}
                style={{ background: "none", border: "none", cursor: "pointer", color: "#7AAE8A", padding: "4px" }}
                title="Mark as read"
              >
                <Check size={16} />
              </button>
            )}
          </div>
        ))
      )}
    </div>
  );
}
