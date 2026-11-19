/**
 * useInterval.ts
 * A declarative setInterval hook that:
 * - Avoids stale closure issues by always reading the latest callback via ref
 * - Clears the interval on unmount automatically
 * - Skips creating the interval when delay is null (paused state)
 *
 * Usage:
 *   useInterval(callback, isActive ? 30000 : null)
 */
import { useEffect, useRef } from "react";

export default function useInterval(callback: () => void, delay: number | null | undefined): void {
  const savedCallback = useRef<() => void>(callback);

  // Always store the latest callback without re-creating the interval
  useEffect(() => {
    savedCallback.current = callback;
  }, [callback]);

  useEffect(() => {
    // null delay = paused
    if (delay === null || delay === undefined) return;

    const id = setInterval(() => savedCallback.current(), delay);
    return () => clearInterval(id);
  }, [delay]);
}
