/**
 * useCountdown.ts
 * Countdown hook that tracks remaining time until an ISO 8601 deadline.
 * Uses Date.now() for accuracy even when the tab is inactive.
 * Fires onExpire at 0 and onWarning when crossing the 2-minute boundary.
 */
import { useState, useEffect, useRef, useCallback } from "react";
import type { UrgencyLevel, UseCountdownReturn } from "../types/notifications";

function getUrgencyLevel(totalSeconds: number): UrgencyLevel {
  if (totalSeconds > 300) return "safe";        // > 5 min
  if (totalSeconds > 120) return "caution";      // 2–5 min
  if (totalSeconds > 60) return "warning";       // 1–2 min
  return "critical";                             // < 1 min
}

interface UseCountdownOptions {
  expiresAt: string;
  onExpire: () => void;
  onWarning: () => void;
}

export default function useCountdown({
  expiresAt,
  onExpire,
  onWarning,
}: UseCountdownOptions): UseCountdownReturn {
  const calcRemaining = useCallback(() => {
    const diff = new Date(expiresAt).getTime() - Date.now();
    return Math.max(0, Math.floor(diff / 1000));
  }, [expiresAt]);

  const [totalSeconds, setTotalSeconds] = useState(calcRemaining);

  // Refs to avoid stale closure issues with callbacks
  const onExpireRef = useRef(onExpire);
  const onWarningRef = useRef(onWarning);
  const hasFiredExpire = useRef(false);
  const hasFiredWarning = useRef(false);

  useEffect(() => { onExpireRef.current = onExpire; }, [onExpire]);
  useEffect(() => { onWarningRef.current = onWarning; }, [onWarning]);

  // Reset when expiresAt changes
  useEffect(() => {
    hasFiredExpire.current = false;
    hasFiredWarning.current = false;
    setTotalSeconds(calcRemaining());
  }, [expiresAt, calcRemaining]);

  // Tick every second
  useEffect(() => {
    const id = setInterval(() => {
      const remaining = calcRemaining();
      setTotalSeconds(remaining);

      // Fire warning once when crossing 120s boundary
      if (remaining <= 120 && remaining > 0 && !hasFiredWarning.current) {
        hasFiredWarning.current = true;
        onWarningRef.current();
      }

      // Fire expire once when hitting 0
      if (remaining <= 0 && !hasFiredExpire.current) {
        hasFiredExpire.current = true;
        onExpireRef.current();
        clearInterval(id);
      }
    }, 1000);

    return () => clearInterval(id);
  }, [calcRemaining]);

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  const isExpired = totalSeconds <= 0;
  const urgencyLevel = getUrgencyLevel(totalSeconds);

  return { minutes, seconds, totalSeconds, isExpired, urgencyLevel };
}
