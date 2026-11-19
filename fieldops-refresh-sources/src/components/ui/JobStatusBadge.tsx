import React, { useState, useRef, useEffect } from "react";
import { Clock, UserCheck, Truck, MapPin, CheckCircle, XOctagon, Archive, LucideIcon } from "lucide-react";
import { useThemeStore } from "../../store/themeStore";

export interface StatusConfigItem {
  label: string;
  icon: LucideIcon;
  description: string;
  colors: {
    bg: string;
    text: string;
    border: string;
    dot: string;
    darkBg: string;
    darkText: string;
    darkBorder: string;
    darkDot: string;
  };
  pulse?: boolean;
}

export const STATUS_CONFIG: Record<string, StatusConfigItem> = {
  CREATED: {
    label: "Created",
    icon: Clock,
    description: "Job has been created and is in queue",
    colors: {
      bg: "bg-slate-100",
      text: "text-slate-700",
      border: "border-slate-200",
      dot: "bg-slate-400",
      darkBg: "dark:bg-slate-800/80",
      darkText: "dark:text-slate-350",
      darkBorder: "dark:border-slate-700",
      darkDot: "dark:bg-slate-500",
    },
    pulse: false,
  },
  ASSIGNED: {
    label: "Assigned",
    icon: UserCheck,
    description: "Job has been assigned to a technician",
    colors: {
      bg: "bg-blue-100",
      text: "text-blue-700",
      border: "border-blue-200",
      dot: "bg-blue-500",
      darkBg: "dark:bg-blue-950/40",
      darkText: "dark:text-blue-300",
      darkBorder: "dark:border-blue-900/50",
      darkDot: "dark:bg-blue-400",
    },
    pulse: true,
  },
  EN_ROUTE: {
    label: "En Route",
    icon: Truck,
    description: "Technician is on the way to the job site",
    colors: {
      bg: "bg-green-100",
      text: "text-green-700",
      border: "border-green-200",
      dot: "bg-green-500",
      darkBg: "dark:bg-green-950/40",
      darkText: "dark:text-green-300",
      darkBorder: "dark:border-green-900/50",
      darkDot: "dark:bg-green-400",
    },
    pulse: true,
  },
  ON_SITE: {
    label: "On Site",
    icon: MapPin,
    description: "Technician is on-site performing the job",
    colors: {
      bg: "bg-amber-100",
      text: "text-amber-700",
      border: "border-amber-200",
      dot: "bg-amber-500",
      darkBg: "dark:bg-amber-950/40",
      darkText: "dark:text-amber-300",
      darkBorder: "dark:border-amber-900/50",
      darkDot: "dark:bg-amber-400",
    },
    pulse: true,
  },
  COMPLETED: {
    label: "Completed",
    icon: CheckCircle,
    description: "Job has been completed successfully",
    colors: {
      bg: "bg-emerald-100",
      text: "text-emerald-700",
      border: "border-emerald-200",
      dot: "bg-emerald-500",
      darkBg: "dark:bg-emerald-950/40",
      darkText: "dark:text-emerald-300",
      darkBorder: "dark:border-emerald-900/50",
      darkDot: "dark:bg-emerald-400",
    },
    pulse: false,
  },
  CANCELLED: {
    label: "Cancelled",
    icon: XOctagon,
    description: "Job has been cancelled",
    colors: {
      bg: "bg-red-100",
      text: "text-red-700",
      border: "border-red-200",
      dot: "bg-red-500",
      darkBg: "dark:bg-red-950/40",
      darkText: "dark:text-red-300",
      darkBorder: "dark:border-red-900/50",
      darkDot: "dark:bg-red-400",
    },
    pulse: false,
  },
  CLOSED: {
    label: "Closed",
    icon: Archive,
    description: "Job has been closed",
    colors: {
      bg: "bg-slate-100",
      text: "text-slate-700",
      border: "border-slate-200",
      dot: "bg-slate-500",
      darkBg: "dark:bg-slate-800/80",
      darkText: "dark:text-slate-350",
      darkBorder: "dark:border-slate-700",
      darkDot: "dark:bg-slate-400",
    },
    pulse: false,
  },
  NO_ACTIVE_JOBS: {
    label: "No Active Jobs",
    icon: Clock,
    description: "This technician has no active jobs assigned",
    colors: {
      bg: "bg-slate-100",
      text: "text-slate-500",
      border: "border-slate-200",
      dot: "bg-slate-300",
      darkBg: "dark:bg-slate-800/60",
      darkText: "dark:text-slate-400",
      darkBorder: "dark:border-slate-700/50",
      darkDot: "dark:bg-slate-550",
    },
    pulse: false,
  },
};

export interface StatusTooltipProps {
  description: string;
  visible: boolean;
  targetRef: React.RefObject<HTMLElement | null>;
}

export const StatusTooltip: React.FC<StatusTooltipProps> = ({ description, visible, targetRef }) => {
  const [coords, setCoords] = useState({ top: 0, left: 0 });

  useEffect(() => {
    if (visible && targetRef.current) {
      const rect = targetRef.current.getBoundingClientRect();
      setCoords({
        top: rect.top + window.scrollY - 36, // Position above the badge
        left: rect.left + window.scrollX + rect.width / 2,
      });
    }
  }, [visible, targetRef]);

  if (!visible) return null;

  return (
    <div
      role="tooltip"
      data-testid="status-tooltip"
      className="fixed z-50 -translate-x-1/2 bg-slate-900 dark:bg-slate-850 text-white text-xs px-2.5 py-1.5 rounded-lg shadow-xl border border-slate-750/50 pointer-events-none select-none animate-fade-in animate-scale-up"
      style={{
        top: `${coords.top}px`,
        left: `${coords.left}px`,
      }}
    >
      <span>{description}</span>
      {/* Caret / Arrow */}
      <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-900 dark:border-t-slate-850" />
    </div>
  );
};

export interface JobStatusBadgeProps {
  status: "CREATED" | "ASSIGNED" | "EN_ROUTE" | "ON_SITE" | "COMPLETED" | "CANCELLED" | "CLOSED" | "NO_ACTIVE_JOBS" | string;
  size?: "sm" | "md" | "lg";
  variant?: "pill" | "rounded-square";
  className?: string;
}

export const JobStatusBadge: React.FC<JobStatusBadgeProps> = ({
  status,
  size = "md",
  variant = "pill",
  className = "",
}) => {
  const [isHovered, setIsHovered] = useState(false);
  const hoverTimerRef = useRef<NodeJS.Timeout | null>(null);
  const badgeRef = useRef<HTMLDivElement | null>(null);

  // Sync with Zustand theme store
  const isDarkMode = useThemeStore((state) => state.isDarkMode);

  const lookupKey = (status || "").toUpperCase();
  const config = STATUS_CONFIG[lookupKey] || STATUS_CONFIG.CREATED;
  const IconComponent = config.icon;

  const handleMouseEnter = () => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    hoverTimerRef.current = setTimeout(() => {
      setIsHovered(true);
    }, 200); // 200ms delay
  };

  const handleMouseLeave = () => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    setIsHovered(false);
  };

  useEffect(() => {
    return () => {
      if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    };
  }, []);

  // Size mapping styles
  const sizeClasses = {
    sm: "text-[10px] px-2 py-0.5 gap-1 font-bold",
    md: "text-xs px-2.5 py-1 gap-1.5 font-bold",
    lg: "text-sm px-3 py-1.5 gap-2 font-bold",
  };

  const iconSizes = {
    sm: 12,
    md: 14,
    lg: 16,
  };

  // Shape mapping styles
  const shapeClasses = {
    pill: "rounded-full",
    "rounded-square": "rounded-md",
  };

  const colorStyles = config.colors;
  const shouldPulse = config.pulse;

  return (
    <>
      <div
        ref={badgeRef}
        role="status"
        aria-label={`${config.label} — ${config.description}`}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        onFocus={handleMouseEnter}
        onBlur={handleMouseLeave}
        tabIndex={0}
        data-testid="job-status-badge"
        className={`inline-flex items-center justify-center border select-none transition cursor-default leading-none ${
          sizeClasses[size]
        } ${shapeClasses[variant]} ${colorStyles.bg} ${colorStyles.text} ${colorStyles.border} ${
          colorStyles.darkBg
        } ${colorStyles.darkText} ${colorStyles.darkBorder} ${className} ${
          isDarkMode ? "dark" : ""
        }`}
      >
        {/* Pulsing dot for active statuses */}
        {shouldPulse && (
          <span
            data-testid="status-pulse-dot"
            className={`w-1.5 h-1.5 rounded-full shrink-0 animate-pulse ${colorStyles.dot} ${colorStyles.darkDot}`}
          />
        )}

        {/* Icon Component */}
        {IconComponent && (
          <IconComponent
            size={iconSizes[size]}
            className="shrink-0"
            data-testid="status-badge-icon"
            aria-hidden="true"
          />
        )}

        {/* Status label */}
        <span>{config.label}</span>
      </div>

      <StatusTooltip
        description={config.description}
        visible={isHovered}
        targetRef={badgeRef}
      />
    </>
  );
};

export default JobStatusBadge;
