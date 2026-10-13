
import { useEffect, useState } from "react";
import { Redirect } from "expo-router";
import { LoadingState } from "../src/components/ScreenState";
import { useAuthStore } from "../src/auth/authStore";

export default function IndexScreen() {
  const [isReady, setIsReady] = useState(false);

  const restoreSession = useAuthStore((state) => state.restoreSession);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const user = useAuthStore((state) => state.user);

  useEffect(() => {
    let mounted = true;

    void restoreSession()
      .catch(() => undefined)
      .finally(() => {
        if (mounted) {
          setIsReady(true);
        }
      });

    return () => {
      mounted = false;
    };
  }, [restoreSession]);

  if (!isReady) {
    return <LoadingState label="Preparing FieldOps..." />;
  }

  if (isAuthenticated && user?.role.toLowerCase() === "technician") {
    return <Redirect href="/(app)/dashboard" />;
  }

  return <Redirect href="/(auth)/login" />;
}
