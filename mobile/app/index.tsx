
import { useCallback, useEffect, useRef, useState } from "react";
import { Redirect } from "expo-router";
import { useAuthStore } from "../src/auth/authStore";
import { AnimatedLaunchScreen } from "../../fo/src/components/AnimatedLaunchScreen";

export default function IndexScreen() {
  const [sessionRestored, setSessionRestored] = useState(false);
  const [launchComplete, setLaunchComplete] = useState(false);
  const restoreStarted = useRef(false);

  const restoreSession = useAuthStore(
    (state) => state.restoreSession
  );
  const isAuthenticated = useAuthStore(
    (state) => state.isAuthenticated
  );
  const user = useAuthStore((state) => state.user);

  useEffect(() => {
    if (restoreStarted.current) return;
    restoreStarted.current = true;
    let mounted = true;

    void restoreSession()
      .catch(() => undefined)
      .finally(() => {
        if (mounted) setSessionRestored(true);
      });

    return () => {
      mounted = false;
    };
  }, [restoreSession]);

  const finishLaunch = useCallback(() => setLaunchComplete(true), []);

  if (!launchComplete) {
    return (
      <AnimatedLaunchScreen
        readyToExit={sessionRestored}
        onExitComplete={finishLaunch}
      />
    );
  }

  if (
    isAuthenticated &&
    user?.role.toLowerCase() === "technician"
  ) {
    return <Redirect href="/(app)/dashboard" />;
  }

  return <Redirect href="/(auth)/login" />;
}
