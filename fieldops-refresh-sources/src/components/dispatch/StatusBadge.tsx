import React from "react";

/**
 * StatusBadge.tsx
 * Color-coded status badge for dispatch queue rows.
 *
 * QUEUED   → gray
 * ASSIGNED → blue (subtle pulse)
 * EN_ROUTE → yellow
 * ON_SITE  → orange
 */

interface StatusBadgeProps {
  status: string;
}

const statusConfig: Record<
  string,
  { label: string; background: string; color: string; dotColor: string; pulse?: boolean }
> = {
  QUEUED: { label: "Queued", background: "#F3F4F6", color: "#6B7280", dotColor: "#9CA3AF" },
  ASSIGNED: { label: "Assigned", background: "#DBEAFE", color: "#1D4ED8", dotColor: "#3B82F6", pulse: true },
  EN_ROUTE: { label: "En Route", background: "#FEF3C7", color: "#92400E", dotColor: "#F59E0B" },
  ON_SITE: { label: "On Site", background: "#FFEDD5", color: "#9A3412", dotColor: "#F97316" },
};

const styles = {
  badge: {
    display: "inline-flex",
    alignItems: "center",
    gap: "5px",
    fontSize: "10px",
    fontWeight: 700,
    padding: "3px 10px",
    borderRadius: "20px",
    textTransform: "uppercase",
    letterSpacing: "0.03em",
    whiteSpace: "nowrap",
  } as React.CSSProperties,
  
  dot: {
    width: "6px",
    height: "6px",
    borderRadius: "50%",
    flexShrink: 0,
  } as React.CSSProperties,
};

const keyframes = `
  @keyframes dq-subtle-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.85; }
  }
`;

const StatusBadge = ({ status }: StatusBadgeProps) => {
  const normalizedStatus = (status || "").toUpperCase();
  const config = statusConfig[normalizedStatus] || {
    label: status,
    background: "#F3F4F6",
    color: "#6B7280",
    dotColor: "#9CA3AF",
  };

  const badgeStyle: React.CSSProperties = {
    ...styles.badge,
    background: config.background,
    color: config.color,
    animation: config.pulse ? "dq-subtle-pulse 2.5s ease-in-out infinite" : undefined,
  };

  const dotStyle: React.CSSProperties = {
    ...styles.dot,
    background: config.dotColor,
  };

  return (
    <span 
      className={`dq-status-badge dq-status-${normalizedStatus.toLowerCase()}`}
      style={badgeStyle}
    >
      <style>{keyframes}</style>
      <span className="dq-status-dot" style={dotStyle} />
      {config.label}
    </span>
  );
};

export default StatusBadge;
