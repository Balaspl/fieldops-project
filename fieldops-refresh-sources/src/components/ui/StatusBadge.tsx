import React, { useState } from "react";
import {
  CheckCircle,
  Clock,
  UserMinus,
  Navigation,
  MapPin,
  Coffee,
  AlertTriangle,
  Briefcase,
  LucideIcon,
} from "lucide-react";

export interface StatusBadgeProps {
  status: "AVAILABLE" | "BUSY" | "ASSIGNED" | "OFFLINE" | "EN_ROUTE" | "ON_SITE" | "ON_BREAK" | "SUSPENDED";
  size?: "sm" | "md" | "lg";
  showIcon?: boolean;
  pulse?: boolean;
  className?: string;
  "data-testid"?: string;
}

interface StatusConfigItem {
  label: string;
  icon: LucideIcon;
  description: string;
  defaultPulse?: boolean;
}

const STATUS_CONFIG: Record<StatusBadgeProps["status"], StatusConfigItem> = {
  AVAILABLE: {
    label: "Available",
    icon: CheckCircle,
    description: "Technician is available for assignment",
  },
  BUSY: {
    label: "Busy",
    icon: Clock,
    description: "Technician is currently assigned or occupied",
  },
  ASSIGNED: {
    label: "Assigned",
    icon: Briefcase,
    description: "Technician is currently assigned to a job",
  },
  OFFLINE: {
    label: "Offline",
    icon: UserMinus,
    description: "Technician is not currently online",
  },
  EN_ROUTE: {
    label: "En Route",
    icon: Navigation,
    description: "Technician is travelling to job location",
    defaultPulse: true,
  },
  ON_SITE: {
    label: "On Site",
    icon: MapPin,
    description: "Technician has reached the job location",
  },
  ON_BREAK: {
    label: "On Break",
    icon: Coffee,
    description: "Technician is temporarily unavailable",
  },
  SUSPENDED: {
    label: "Suspended",
    icon: AlertTriangle,
    description: "Technician is blocked from assignment",
  },
};

export const TECHNICIAN_STATUSES = Object.keys(STATUS_CONFIG) as StatusBadgeProps["status"][];

const styleConfig = {
  badge: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "flex-start",
    gap: "5px",
    borderRadius: "20px",
    border: "1px solid transparent",
    fontFamily: "'Inter', sans-serif",
    fontWeight: 600,
    whiteSpace: "nowrap",
    cursor: "default",
    lineHeight: 1,
    position: "relative",
    userSelect: "none",
    transition: "opacity .2s",
  } as React.CSSProperties,
  
  sizes: {
    sm: { fontSize: "10px", padding: "2px 8px", gap: "4px", width: "95px" },
    md: { fontSize: "12px", padding: "4px 12px", gap: "5px", width: "115px" },
    lg: { fontSize: "14px", padding: "6px 14px", gap: "6px", width: "135px" },
  },
  
  icon: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  } as React.CSSProperties,
  
  dot: {
    borderRadius: "50%",
    flexShrink: 0,
  } as React.CSSProperties,
  
  dotSizes: {
    sm: { width: "5px", height: "5px" },
    md: { width: "6px", height: "6px" },
    lg: { width: "7px", height: "7px" },
  },

  colors: {
    AVAILABLE: { background: "#DDEEE5", color: "#1D6B3E", borderColor: "#B5D9C4", dot: "#2F9E59" },
    BUSY: { background: "#DBEAFE", color: "#1D4ED8", borderColor: "#BFDBFE", dot: "#2563EB" },
    ASSIGNED: { background: "#E0F2FE", color: "#0369A1", borderColor: "#7DD3FC", dot: "#0284C7" },
    OFFLINE: { background: "#F0F4F2", color: "#6B7280", borderColor: "#D1D5DB", dot: "#9CA3AF", opacity: 0.75 },
    EN_ROUTE: { background: "#FEF9C3", color: "#854D0E", borderColor: "#FDE68A", dot: "#CA8A04" },
    ON_SITE: { background: "#EDE9FE", color: "#6D28D9", borderColor: "#DDD6FE", dot: "#7C3AED" },
    ON_BREAK: { background: "#FEF0D6", color: "#92400E", borderColor: "#FCD29A", dot: "#D97706" },
    SUSPENDED: { background: "#FEE2E2", color: "#991B1B", borderColor: "#FECACA", dot: "#DC2626" },
  } as Record<StatusBadgeProps["status"], { background: string; color: string; borderColor: string; dot: string; opacity?: number }>,
  
  tooltip: {
    position: "absolute",
    bottom: "calc(100% + 6px)",
    left: "50%",
    transform: "translateX(-50%) translateY(4px)",
    background: "#1F2933",
    color: "#F9FAFB",
    fontSize: "11px",
    fontWeight: 500,
    padding: "5px 10px",
    borderRadius: "6px",
    whiteSpace: "nowrap",
    pointerEvents: "none",
    opacity: 0,
    transition: "opacity .15s ease, transform .15s ease",
    zIndex: 500,
    boxShadow: "0 4px 12px rgba(0,0,0,.18)",
  } as React.CSSProperties,

  tooltipVisible: {
    opacity: 1,
    transform: "translateX(-50%) translateY(0)",
    pointerEvents: "auto",
  } as React.CSSProperties,
};

const inlineAnimationStyles = `
  @keyframes sb-pulse-avail {
    0%, 100% { box-shadow: 0 0 0 0 rgba(47,158,89,.5); }
    50%       { box-shadow: 0 0 0 5px rgba(47,158,89,0); }
  }
  @keyframes sb-pulse-busy {
    0%, 100% { box-shadow: 0 0 0 0 rgba(37,99,235,.5); }
    50%       { box-shadow: 0 0 0 5px rgba(37,99,235,0); }
  }
  @keyframes sb-pulse-assigned {
    0%, 100% { box-shadow: 0 0 0 0 rgba(2,132,199,.5); }
    50%       { box-shadow: 0 0 0 5px rgba(2,132,199,0); }
  }
  @keyframes sb-pulse-enroute {
    0%, 100% { box-shadow: 0 0 0 0 rgba(202,138,4,.5); }
    50%       { box-shadow: 0 0 0 5px rgba(202,138,4,0); }
  }
  @keyframes sb-pulse-onsite {
    0%, 100% { box-shadow: 0 0 0 0 rgba(124,58,237,.5); }
    50%       { box-shadow: 0 0 0 5px rgba(124,58,237,0); }
  }
  @keyframes sb-pulse-onbreak {
    0%, 100% { box-shadow: 0 0 0 0 rgba(217,119,6,.5); }
    50%       { box-shadow: 0 0 0 5px rgba(217,119,6,0); }
  }
  @keyframes sb-pulse-suspended {
    0%, 100% { box-shadow: 0 0 0 0 rgba(220,38,38,0.5); }
    50%       { box-shadow: 0 0 0 5px rgba(220,38,38,0); }
  }
  
  .sb-tooltip-arrow::after {
    content: "";
    position: absolute;
    top: 100%;
    left: 50%;
    transform: translateX(-50%);
    border: 5px solid transparent;
    border-top-color: #1F2933;
  }
  
  @media (prefers-color-scheme: dark) {
    .sb-AVAILABLE-dark { background: rgba(47,158,89,.2) !important; color: #86efac !important; border-color: rgba(47,158,89,.35) !important; }
    .sb-BUSY-dark      { background: rgba(37,99,235,.2) !important; color: #93c5fd !important; border-color: rgba(37,99,235,.35) !important; }
    .sb-OFFLINE-dark   { background: rgba(107,114,128,.15) !important; color: #9CA3AF !important; border-color: rgba(107,114,128,.3) !important; }
    .sb-EN_ROUTE-dark  { background: rgba(202,138,4,.18) !important; color: #fde68a !important; border-color: rgba(202,138,4,.35) !important; }
    .sb-ON_SITE-dark   { background: rgba(124,58,237,.2) !important; color: #c4b5fd !important; border-color: rgba(124,58,237,.35) !important; }
    .sb-ON_BREAK-dark  { background: rgba(217,119,6,.18) !important; color: #fcd29a !important; border-color: rgba(217,119,6,.35) !important; }
    .sb-SUSPENDED-dark { background: rgba(220,38,38,.18) !important; color: #fca5a5 !important; border-color: rgba(220,38,38,.35) !important; }
    
    .sb-tooltip-arrow-dark::after {
      border-top-color: #374151 !important;
    }
  }
`;

const getPulseAnimationName = (status: string): string => {
  const s = (status || "").toUpperCase();
  if (s === "AVAILABLE") return "sb-pulse-avail 1.6s ease-in-out infinite";
  if (s === "BUSY") return "sb-pulse-busy 1.6s ease-in-out infinite";
  if (s === "ASSIGNED") return "sb-pulse-assigned 1.6s ease-in-out infinite";
  if (s === "EN_ROUTE") return "sb-pulse-enroute 1.6s ease-in-out infinite";
  if (s === "ON_SITE") return "sb-pulse-onsite 1.6s ease-in-out infinite";
  if (s === "ON_BREAK") return "sb-pulse-onbreak 1.6s ease-in-out infinite";
  if (s === "SUSPENDED") return "sb-pulse-suspended 1.6s ease-in-out infinite";
  return "";
};

export default function StatusBadge({
  status,
  size = "md",
  showIcon = true,
  pulse,
  className = "",
  "data-testid": dataTestId,
}: StatusBadgeProps) {
  const [isHovered, setIsHovered] = useState(false);
  
  const lookupStatus = (status || "").toUpperCase() as StatusBadgeProps["status"];
  const config = STATUS_CONFIG[lookupStatus] ?? STATUS_CONFIG["OFFLINE"];
  const label = config.label;
  const desc = config.description;
  const IconComponent = config.icon;

  const shouldPulse = pulse !== undefined ? pulse : (config.defaultPulse ?? false);

  const iconSize = size === "sm" ? 11 : size === "lg" ? 15 : 13;

  const colorStyles = styleConfig.colors[lookupStatus] ?? styleConfig.colors["OFFLINE"];
  
  const badgeStyle: React.CSSProperties = {
    ...styleConfig.badge,
    ...styleConfig.sizes[size],
    background: colorStyles.background,
    color: colorStyles.color,
    borderColor: colorStyles.borderColor,
    opacity: colorStyles.opacity ?? 1,
  };

  const dotStyle: React.CSSProperties = {
    ...styleConfig.dot,
    ...styleConfig.dotSizes[size],
    background: colorStyles.dot,
    animation: shouldPulse ? getPulseAnimationName(lookupStatus) : undefined,
  };

  const tooltipStyle: React.CSSProperties = {
    ...styleConfig.tooltip,
    ...(isHovered ? styleConfig.tooltipVisible : {}),
  };

  return (
    <span
      className={`sb-badge sb-${size} sb-${lookupStatus} ${shouldPulse ? "sb-pulse" : ""} ${className} sb-${lookupStatus}-dark`}
      role="status"
      aria-label={`${label} — ${desc}`}
      tabIndex={0}
      data-testid={dataTestId}
      style={badgeStyle}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onFocus={() => setIsHovered(true)}
      onBlur={() => setIsHovered(false)}
    >
      <style>{inlineAnimationStyles}</style>

      {/* Colored dot — always rendered for a11y (not color-only) */}
      <span 
        className="sb-dot" 
        aria-hidden="true" 
        data-testid="status-badge-dot" 
        style={dotStyle}
      />

      {/* Optional icon */}
      {showIcon && IconComponent && (
        <span 
          className="sb-icon" 
          aria-hidden="true" 
          data-testid="status-badge-icon" 
          style={styleConfig.icon}
        >
          <IconComponent size={iconSize} />
        </span>
      )}

      {/* Label text */}
      <span>{label}</span>

      {/* Tooltip */}
      <span 
        className={`sb-tooltip sb-tooltip-arrow ${isHovered ? "sb-tooltip-arrow-dark" : ""}`}
        role="tooltip" 
        style={tooltipStyle}
      >
        {desc}
      </span>
    </span>
  );
}
