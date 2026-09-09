import React, { useState, useEffect, useRef, useCallback } from "react";
import { Clock, AlertTriangle } from "lucide-react";

interface AcceptanceTimerProps {
  /** ISO timestamp when the job was assigned */
  assignedAt: string | null;
  /** ISO timestamp when the acceptance window expires (preferred) */
  expiresAt: string | null;
  /** Current job status */
  status: string;
  /** Acceptance window in minutes (fallback when expiresAt is null) */
  windowMinutes?: number;
}

const formatTime = (totalSeconds: number): string => {
  if (totalSeconds <= 0) return "00:00";
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
};

const styles = {
  badge: {
    display: "inline-flex",
    alignItems: "center",
    gap: "5px",
    fontSize: "11px",
    fontWeight: 700,
    padding: "4px 10px",
    borderRadius: "8px",
    whiteSpace: "nowrap",
    transition: "all 0.2s",
  } as React.CSSProperties,
  
  digits: {
    fontFamily: "'SF Mono', 'Fira Code', 'Cascadia Code', monospace",
    letterSpacing: "0.04em",
  } as React.CSSProperties,
  
  themes: {
    green: { background: "#DCFCE7", color: "#166534" },
    yellow: { background: "#FEF9C3", color: "#854D0E" },
    red: { background: "#FEE2E2", color: "#991B1B", animation: "timer-pulse 1.2s ease-in-out infinite" },
    expired: { background: "#FEE2E2", color: "#991B1B", fontWeight: 800, textTransform: "uppercase", fontSize: "10px" },
    queued: { background: "#F3F4F6", color: "#9CA3AF" },
    accepted: { background: "#DCFCE7", color: "#166534" },
  },

  check: {
    fontSize: "13px",
  } as React.CSSProperties,
  
  paused: {
    fontSize: "10px",
    opacity: 0.7,
  } as React.CSSProperties,
};

const keyframes = `
  @keyframes timer-pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.85; transform: scale(1.03); }
  }
`;

const getTimerTheme = (seconds: number) => {
  if (seconds <= 0) return styles.themes.expired;
  if (seconds < 120) return styles.themes.red;
  if (seconds < 300) return styles.themes.yellow;
  return styles.themes.green;
};

const AcceptanceTimer = ({
  assignedAt,
  expiresAt,
  status,
  windowMinutes = 10,
}: AcceptanceTimerProps) => {
  const computeRemaining = useCallback((): number => {
    // Only show timer for ASSIGNED status
    if (status !== "ASSIGNED") return -1;

    let expiresDate: Date;

    if (expiresAt) {
      expiresDate = new Date(expiresAt);
    } else if (assignedAt) {
      // Fallback: simulate window from assigned_at
      expiresDate = new Date(
        new Date(assignedAt).getTime() + windowMinutes * 60 * 1000
      );
    } else {
      return -1;
    }

    const now = Date.now();
    return Math.max(0, Math.floor((expiresDate.getTime() - now) / 1000));
  }, [assignedAt, expiresAt, status, windowMinutes]);

  const [remaining, setRemaining] = useState<number>(computeRemaining);
  const [isPaused, setIsPaused] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Reset when props change
  useEffect(() => {
    setRemaining(computeRemaining());
  }, [computeRemaining]);

  // Tick every second
  useEffect(() => {
    if (status !== "ASSIGNED" || remaining <= 0 || isPaused) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }

    intervalRef.current = setInterval(() => {
      setRemaining((prev) => {
        if (prev <= 1) {
          if (intervalRef.current) clearInterval(intervalRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [status, remaining > 0, isPaused]); // eslint-disable-line react-hooks/exhaustive-deps

  // QUEUED jobs: no timer
  if (status === "QUEUED") {
    return (
      <span 
        style={{ ...styles.badge, ...styles.themes.queued }}
        className="timer-badge timer-queued" 
        title="Awaiting assignment"
      >
        <Clock size={12} />
        <span>Unassigned</span>
      </span>
    );
  }

  // EN_ROUTE / ON_SITE: accepted
  if (status === "EN_ROUTE" || status === "ON_SITE") {
    return (
      <span 
        style={{ ...styles.badge, ...styles.themes.accepted }}
        className="timer-badge timer-accepted" 
        title="Accepted"
      >
        <span className="timer-check" style={styles.check}>✓</span>
        <span>Accepted</span>
      </span>
    );
  }

  // ASSIGNED with no valid time data
  if (remaining < 0) {
    return (
      <span 
        style={{ ...styles.badge, ...styles.themes.queued }}
        className="timer-badge timer-queued"
      >
        <Clock size={12} />
        <span>—</span>
      </span>
    );
  }

  const isExpired = remaining <= 0;
  const activeTheme = getTimerTheme(remaining);

  return (
    <span
      className={`timer-badge`}
      style={{ ...styles.badge, ...activeTheme }}
      title={
        isExpired
          ? "Acceptance window expired"
          : `${formatTime(remaining)} remaining`
      }
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
    >
      <style>{keyframes}</style>
      {isExpired ? (
        <>
          <AlertTriangle size={12} />
          <span>EXPIRED</span>
        </>
      ) : (
        <>
          <Clock size={12} />
          <span className="timer-digits" style={styles.digits}>{formatTime(remaining)}</span>
          {isPaused && (
            <span className="timer-paused-indicator" style={styles.paused} title="Paused on hover">
              ⏸
            </span>
          )}
        </>
      )}
    </span>
  );
};

export default AcceptanceTimer;
