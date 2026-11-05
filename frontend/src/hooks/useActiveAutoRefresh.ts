import { useEffect, useRef } from "react";

/**
 * Poll the currently mounted web page while its browser tab is visible.
 * Requests are serialized; this hook must only be given read-only refresh work.
 */
export function useActiveAutoRefresh(
  refresh: () => void | Promise<unknown>,
  enabled = true,
  intervalMs = 3000,
): void {
  const refreshRef = useRef(refresh);
  const inFlightRef = useRef(false);
  refreshRef.current = refresh;

  useEffect(() => {
    if (!enabled) return undefined;

    let disposed = false;
    const isVisible = () => document.visibilityState === "visible";

    const run = () => {
      if (disposed || !isVisible() || inFlightRef.current) return;
      inFlightRef.current = true;
      Promise.resolve()
        .then(() => refreshRef.current())
        .catch(() => undefined)
        .finally(() => {
          inFlightRef.current = false;
        });
    };

    const timer = window.setInterval(run, intervalMs);
    const handleVisibility = () => {
      if (isVisible()) run();
    };
    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("focus", handleVisibility);

    return () => {
      disposed = true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("focus", handleVisibility);
    };
  }, [enabled, intervalMs]);
}
