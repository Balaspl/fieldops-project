
import { useEffect } from "react";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { configureNotifications } from "../src/notifications/notificationService";
import { logError } from "../src/observability/logger";

export default function RootLayout() {
  useEffect(() => {
    void configureNotifications().catch((error: unknown) => {
      logError("notifications.configure_failed", error);
    });
  }, []);

  return (
    <>
      <StatusBar style="auto" />
      <Stack
        screenOptions={{
          headerShown: false
        }}
      >
        <Stack.Screen name="index" />
        <Stack.Screen name="(auth)" />
        <Stack.Screen name="(app)" />
      </Stack>
    </>
  );
}
