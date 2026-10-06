import React, { useState, useEffect } from "react";
import { X, Briefcase, Clock, RefreshCw, Info, CheckCheck } from "lucide-react";
import { motion, AnimatePresence, type Variants } from "framer-motion";
import { NotificationDrawerProps } from "../../types/notifications.ts";

const formatAgo = (ts: string) => {
  if (!ts) return "";
  try {
    const diff = Math.round((Date.now() - new Date(ts).getTime()) / 60000);
    if (diff < 1) return "just now";
    if (diff < 60) return `${diff}m ago`;
    const h = Math.round(diff / 60);
    if (h < 24) return `${h}h ago`;
    return new Date(ts).toLocaleDateString();
  } catch {
    return String(ts);
  }
};

const getTypeIcon = (type: string) => {
  switch (type) {
    case "JOB_ASSIGNED":
      return <Briefcase size={18} />;
    case "SLA_WARNING":
      return <Clock size={18} />;
    case "JOB_UPDATED":
      return <RefreshCw size={18} />;
    case "SYSTEM":
    default:
      return <Info size={18} />;
  }
};

const styles = {
  container: {
    position: "fixed",
    inset: 0,
    zindex: 999,
  } as React.CSSProperties,

  backdrop: {
    position: "fixed",
    top: 0,
    left: 0,
    width: "100%",
    height: "100%",
    backgroundColor: "rgba(15, 23, 42, 0.4)",
    backdropFilter: "blur(4px)",
    zIndex: 999,
  } as React.CSSProperties,

  drawer: {
    position: "fixed",
    top: 0,
    right: 0,
    height: "100%",
    backgroundColor: "#ffffff",
    boxShadow: "-4px 0 24px rgba(15, 23, 42, 0.15)",
    zIndex: 1000,
    display: "flex",
    flexDirection: "column",
    boxSizing: "border-box",
  } as React.CSSProperties,

  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "16px 20px",
    borderBottom: "1px solid #e2e8f0",
  } as React.CSSProperties,

  h2: {
    fontSize: "18px",
    fontWeight: "600",
    margin: 0,
    color: "#0f172a",
    fontFamily: "'Inter', sans-serif",
  } as React.CSSProperties,

  closeBtn: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: "32px",
    height: "32px",
    borderRadius: "50%",
    border: "none",
    background: "transparent",
    cursor: "pointer",
    color: "#64748b",
    transition: "background-color 0.2s",
  } as React.CSSProperties,

  content: {
    flex: 1,
    overflowY: "auto",
    padding: "16px 20px",
  } as React.CSSProperties,

  empty: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    height: "100%",
    textAlign: "center",
    color: "#64748b",
    padding: "40px 20px",
    fontFamily: "'Inter', sans-serif",
  } as React.CSSProperties,

  emptyIcon: {
    marginBottom: "12px",
    color: "#cbd5e1",
  } as React.CSSProperties,

  emptyTitle: {
    margin: "0 0 4px 0",
    fontSize: "15px",
    fontWeight: 500,
    color: "#334155",
  } as React.CSSProperties,

  emptySpan: {
    fontSize: "13px",
  } as React.CSSProperties,

  item: {
    display: "flex",
    gap: "12px",
    padding: "14px",
    borderRadius: "8px",
    backgroundColor: "#ffffff",
    border: "1px solid #e2e8f0",
    marginBottom: "12px",
    cursor: "pointer",
    transition: "all 0.2s",
    textAlign: "left",
    fontFamily: "'Inter', sans-serif",
  } as React.CSSProperties,

  iconWrapper: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: "40px",
    height: "40px",
    borderRadius: "8px",
    flexShrink: 0,
  } as React.CSSProperties,

  details: {
    flex: 1,
    minWidth: 0,
  } as React.CSSProperties,

  title: {
    fontSize: "14px",
    fontWeight: 600,
    color: "#1e293b",
    margin: "0 0 4px 0",
  } as React.CSSProperties,

  message: {
    fontSize: "13px",
    color: "#64748b",
    margin: "0 0 6px 0",
    lineHeight: 1.4,
    display: "-webkit-box",
    WebkitLineClamp: 2,
    WebkitBoxOrient: "vertical",
    overflow: "hidden",
  } as React.CSSProperties,

  time: {
    fontSize: "11px",
    color: "#94a3b8",
  } as React.CSSProperties,
};

const iconColors: Record<string, { bg: string; color: string }> = {
  JOB_ASSIGNED: { bg: "#eff6ff", color: "#3b82f6" },
  SLA_WARNING: { bg: "#fffbeb", color: "#f59e0b" },
  JOB_UPDATED: { bg: "#f0fdf4", color: "#10b981" },
  SYSTEM: { bg: "#f8fafc", color: "#64748b" },
};

const localCss = `
  .close-btn-style:hover { background-color: #f1f5f9 !important; color: #0f172a !important; }
  .notif-item-style:hover { border-color: #cbd5e1 !important; background-color: #f8fafc !important; transform: translateY(-1px); }
  .notif-item-unread-style { background-color: #f0fdf4 !important; border-color: #bbf7d0 !important; }
  .notif-item-unread-style:hover { background-color: #f0fdf4 !important; border-color: #86efac !important; }
  
  .btn-sec-style {
    height: 30px;
    font-size: 12px;
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 0 10px;
    border-radius: 6px;
    border: none;
    background-color: #f1f5f9;
    color: #64748b;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
  }
  .btn-sec-style:hover {
    background-color: #e2e8f0;
    color: #1e293b;
  }
  
  .tld-refresh-spinner-local {
    width: 24px;
    height: 24px;
    border: 2px solid #e2e8f0;
    border-top-color: #3b82f6;
    border-radius: 50%;
    animation: local-spin 1s linear infinite;
  }
  @keyframes local-spin {
    to { transform: rotate(360deg); }
  }
`;

export const NotificationDrawer: React.FC<NotificationDrawerProps> = ({
  isOpen,
  onClose,
  notifications,
  onNotificationClick,
  onMarkAllAsRead,
  onDismissNotification,
  loading = false
}) => {
  const [windowWidth, setWindowWidth] = useState(window.innerWidth);

  useEffect(() => {
    const handleResize = () => setWindowWidth(window.innerWidth);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const isMobile = windowWidth <= 640;

  const drawerVariants: Variants = {
    hidden: isMobile ? { y: "100%", x: 0 } : { x: "100%", y: 0 },
    visible: { y: 0, x: 0, transition: { type: "tween", duration: 0.3 } },
    exit: isMobile
      ? { y: "100%", x: 0 }
      : { x: "100%", y: 0, transition: { type: "tween", duration: 0.25 } }
  };

  const drawerResponsive: React.CSSProperties = {
    ...styles.drawer,
    ...(isMobile ? {
      top: "auto",
      bottom: 0,
      width: "100%",
      maxWidth: "100%",
      height: "75vh",
      borderRadius: "16px 16px 0 0",
      boxShadow: "0 -4px 24px rgba(15, 23, 42, 0.15)",
    } : {
      width: "100%",
      maxWidth: "440px",
    })
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <div style={styles.container} className="noc-module">
          <style>{localCss}</style>
          {/* Backdrop */}
          <motion.div
            style={styles.backdrop}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />

          {/* Drawer container */}
          <motion.div
            style={drawerResponsive}
            role="dialog"
            aria-modal="true"
            aria-label="Notification center"
            variants={drawerVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
          >
            <div style={styles.header}>
              <h2 style={styles.h2}>Notifications</h2>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                {onMarkAllAsRead && notifications.some((n) => !n.isRead) && (
                  <button
                    type="button"
                    className="btn-sec-style"
                    onClick={onMarkAllAsRead}
                    title="Mark all as read"
                  >
                    <CheckCheck size={14} /> Mark all read
                  </button>
                )}
                <button
                  type="button"
                  className="close-btn-style"
                  style={styles.closeBtn}
                  onClick={onClose}
                  aria-label="Close notifications panel"
                >
                  <X size={20} />
                </button>
              </div>
            </div>

            <div style={styles.content}>
              {loading ? (
                <div style={styles.empty}>
                  <div className="tld-refresh-spinner-local" style={{ marginBottom: "12px" }} />
                  <span>Loading notifications…</span>
                </div>
              ) : notifications.length === 0 ? (
                <div style={styles.empty}>
                  <div style={styles.emptyIcon}>
                    <Briefcase size={36} />
                  </div>
                  <p style={styles.emptyTitle}>All caught up!</p>
                  <span style={styles.emptySpan}>You have no new notifications.</span>
                </div>
              ) : (
                <div style={{ paddingBottom: "20px" }}>
                  {notifications.map((notification) => {
                    const isUnread = !notification.isRead;
                    const itemClass = `notif-item-style ${isUnread ? "notif-item-unread-style" : ""}`;
                    const typeColor = iconColors[notification.type] || iconColors.SYSTEM;
                    
                    return (
                      <div
                        key={notification.id}
                        className={itemClass}
                        style={{
                          ...styles.item,
                          width: "100%",
                          borderStyle: "solid",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          padding: "10px 14px"
                        }}
                      >
                        <div 
                          style={{ display: "flex", gap: "12px", flex: 1, cursor: "pointer", minWidth: 0 }}
                          onClick={() => onNotificationClick(notification)}
                        >
                          <div style={{ ...styles.iconWrapper, backgroundColor: typeColor.bg, color: typeColor.color }}>
                            {getTypeIcon(notification.type)}
                          </div>
                          <div style={styles.details}>
                            <p style={styles.title}>{notification.title}</p>
                            <p style={styles.message}>{notification.message}</p>
                            <span style={styles.time}>{formatAgo(notification.createdAt)}</span>
                          </div>
                        </div>
                        {onDismissNotification && (
                          <button
                            type="button"
                            className="close-btn-style"
                            style={{
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              width: "28px",
                              height: "28px",
                              borderRadius: "50%",
                              border: "none",
                              background: "transparent",
                              cursor: "pointer",
                              color: "#94a3b8",
                              marginLeft: "8px",
                              flexShrink: 0,
                            }}
                            onClick={(e) => {
                              e.stopPropagation();
                              onDismissNotification(notification.id);
                            }}
                            title="Dismiss notification"
                          >
                            <X size={14} />
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};

export default NotificationDrawer;
