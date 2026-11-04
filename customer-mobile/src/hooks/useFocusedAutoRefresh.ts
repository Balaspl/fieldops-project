import { useCallback, useRef } from "react";
import { AppState, type AppStateStatus } from "react-native";
import { useFocusEffect } from "expo-router";

/**
 * Refresh data for the screen that is currently focused, every three seconds.
 * Polling pauses while the app is backgrounded and never overlaps requests.
 * The callback should contain GET/read-only work and should update existing
 * screen state without resetting forms or navigation.
 */
export function useFocusedAutoRefresh(
  refresh: () => void | Promise<unknown>,
  enabled = true,
  intervalMs = 3000,
): void {
  const refreshRef = useRef(refresh);
  const inFlightRef = useRef(false);
  refreshRef.current = refresh;

  useFocusEffect(
    useCallback(() => {
      if (!enabled) return undefined;

      let appState: AppStateStatus = AppState.currentState;
      let disposed = false;

      const run = () => {
        if (disposed || appState !== "active" || inFlightRef.current) return;
        inFlightRef.current = true;
        Promise.resolve()
          .then(() => refreshRef.current())
          .catch(() => undefined)
          .finally(() => {
            inFlightRef.current = false;
          });
      };

      const timer = setInterval(run, intervalMs);
      const subscription = AppState.addEventListener("change", (nextState) => {
        appState = nextState;
      });

      return () => {
        disposed = true;
        clearInterval(timer);
        subscription.remove();
      };
    }, [enabled, intervalMs]),
  );
}
