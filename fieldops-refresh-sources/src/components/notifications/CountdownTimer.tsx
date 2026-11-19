/**
 * CountdownTimer.tsx
 * Visual countdown badge with color-coded urgency, pulse animations,
 * ARIA live region for accessibility, and a warning toast banner.
 */
import React, { useState, useEffect, useRef } from "react";
import { Clock, AlertTriangle } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import useCountdown from "../../hooks/useCountdown";
import type { CountdownTimerProps, UrgencyLevel } from "../../types/notifications";

const pad = (n: number) => String(n).padStart(2, "0");

/** How often the ARIA live region updates (seconds) per urgency level */
const ANNOUNCE_INTERVALS: Record<UrgencyLevel, number> = {
  safe: 30,
  caution: 10,
  warning: 5,
  critical: 5,
};

const styles = {
  timer: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    padding: "10px 16px",
    borderRadius: "10px",
    fontSize: "14px",
    fontWeight: 700,
    marginBottom: "20px",
    transition: "background-color 0.4s ease, color 0.4s ease, border-color 0.4s ease",
    border: "1px solid",
  } as React.CSSProperties,

  timerCondensed: {
    padding: "6px 12px",
    marginBottom: "12px",
    borderRadius: "6px",
    fontSize: "12.5px",
  } as React.CSSProperties,

  digits: {
    fontFamily: "'Courier New', Courier, monospace",
    fontSize: "18px",
    fontWeight: 800,
    letterSpacing: "0.08em",
  } as React.CSSProperties,

  digitsCondensed: {
    fontSize: "14px",
  } as React.CSSProperties,

  label: {
    fontSize: "12px",
    fontWeight: 500,
    opacity: 0.8,
    textTransform: "uppercase",
    letterSpacing: "0.05em",
  } as React.CSSProperties,

  labelCondensed: {
    fontSize: "11px",
  } as React.CSSProperties,

  warningToast: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    padding: "10px 14px",
    borderRadius: "8px",
    backgroundColor: "#fef3c7",
    border: "1px solid #fde68a",
    color: "#92400e",
    fontSize: "13px",
    fontWeight: 600,
    marginBottom: "14px",
  } as React.CSSProperties,
};

const urgencyStyles = {
  safe: {
    backgroundColor: "#ecfdf5",
    borderColor: "#a7f3d0",
    color: "#065f46",
  },
  caution: {
    backgroundColor: "#fffbeb",
    borderColor: "#fde68a",
    color: "#92400e",
  },
  warning: {
    backgroundColor: "#fff7ed",
    borderColor: "#fdba74",
    color: "#9a3412",
  },
  critical: {
    backgroundColor: "#fef2f2",
    borderColor: "#fca5a5",
    color: "#991b1b",
  },
};

const localCss = `
  @keyframes countdownPulseSlow {
    0%, 100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(249, 115, 22, 0.3); }
    50% { transform: scale(1.02); box-shadow: 0 0 0 6px rgba(249, 115, 22, 0); }
  }
  @keyframes countdownPulseFast {
    0%, 100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
    50% { transform: scale(1.03); box-shadow: 0 0 0 8px rgba(239, 68, 68, 0); }
  }
  .countdown-pulse-slow {
    animation: countdownPulseSlow 2s ease-in-out infinite;
  }
  .countdown-pulse-fast {
    animation: countdownPulseFast 0.8s ease-in-out infinite;
  }
`;

export const CountdownTimer: React.FC<CountdownTimerProps> = ({
  expiresAt,
  onExpire,
  onWarning,
  jobId,
  hidden = false,
  condensed = false,
}) => {
  const { minutes, seconds, totalSeconds, isExpired, urgencyLevel } = useCountdown({
    expiresAt,
    onExpire,
    onWarning,
  });

  // Warning toast visibility
  const [showWarningToast, setShowWarningToast] = useState(false);
  const prevUrgencyRef = useRef<UrgencyLevel>(urgencyLevel);

  // Show warning toast when transitioning into "caution" from "safe"
  useEffect(() => {
    if (urgencyLevel === "caution" && prevUrgencyRef.current === "safe") {
      setShowWarningToast(true);
      const id = setTimeout(() => setShowWarningToast(false), 5000);
      return () => clearTimeout(id);
    }
    prevUrgencyRef.current = urgencyLevel;
  }, [urgencyLevel]);

  // ARIA live region — throttled announcements
  const [ariaText, setAriaText] = useState("");
  const lastAnnounceRef = useRef(0);

  useEffect(() => {
    const now = Date.now();
    const interval = ANNOUNCE_INTERVALS[urgencyLevel] * 1000;

    if (now - lastAnnounceRef.current >= interval) {
      lastAnnounceRef.current = now;
      if (isExpired) {
        setAriaText("Timer expired. Please respond immediately.");
      } else {
        setAriaText(`${minutes} minutes and ${seconds} seconds remaining.`);
      }
    }
  }, [totalSeconds, minutes, seconds, isExpired, urgencyLevel]);

  if (hidden || (isExpired && totalSeconds < -5)) return null;

  const pulseClass =
    urgencyLevel === "critical"
      ? "countdown-pulse-fast"
      : urgencyLevel === "warning"
        ? "countdown-pulse-slow"
        : "";

  const finalTimerStyle = {
    ...styles.timer,
    ...urgencyStyles[urgencyLevel],
    ...(condensed ? styles.timerCondensed : {}),
  };

  const finalDigitsStyle = {
    ...styles.digits,
    ...(condensed ? styles.digitsCondensed : {}),
  };

  const finalLabelStyle = {
    ...styles.label,
    ...(condensed ? styles.labelCondensed : {}),
  };

  return (
    <>
      <style>{localCss}</style>

      {/* Screen reader announcements */}
      <div style={{ position: "absolute", width: "1px", height: "1px", padding: 0, margin: "-1px", overflow: "hidden", clip: "rect(0, 0, 0, 0)", whiteSpace: "nowrap", borderWidth: 0 }} aria-live="polite" aria-atomic="true" data-testid="countdown-aria">
        {ariaText}
      </div>

      {/* Timer badge */}
      <motion.div
        className={pulseClass}
        style={finalTimerStyle}
        data-testid="countdown-timer"
        data-urgency={urgencyLevel}
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        role="timer"
        aria-label={`${pad(minutes)}:${pad(seconds)} remaining for job ${jobId}`}
      >
        <Clock size={16} aria-hidden="true" />
        <span style={finalDigitsStyle} data-testid="countdown-digits">
          {isExpired ? "00:00" : `${pad(minutes)}:${pad(seconds)}`}
        </span>
        <span style={finalLabelStyle}>
          {isExpired ? "Expired" : "remaining"}
        </span>
      </motion.div>

      {/* Warning toast banner */}
      <AnimatePresence>
        {showWarningToast && (
          <motion.div
            style={styles.warningToast}
            data-testid="countdown-warning-toast"
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            role="alert"
          >
            <AlertTriangle size={14} />
            <span>⏰ Only 2 minutes remaining to respond!</span>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
};

export default CountdownTimer;
