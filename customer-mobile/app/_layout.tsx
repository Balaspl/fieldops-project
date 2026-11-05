
import { useEffect } from "react";
import { Stack, router } from "expo-router";
import { Platform } from "react-native";
import { StatusBar } from "expo-status-bar";
import { colors } from "../src/theme";
import { configureCustomerNotifications } from "../src/notifications/notificationService";
import { useAuthStore } from "../src/auth/authStore";
import { customerApi } from "../src/api/customer";
import { registerCustomerPushDevice } from "../src/notifications/notificationService";

export default function RootLayout() {
  const user = useAuthStore((state) => state.user);

  useEffect(() => configureCustomerNotifications((jobId) => {
    if (jobId) router.push({ pathname: "/jobs/[jobId]", params: { jobId } });
    else router.push("/notifications");
  }), []);

  useEffect(() => {
    if (!user) return;
    let active = true;
    void customerApi.notificationPreferences()
      .then((preferences) => {
        if (active && preferences.push_enabled) {
          return registerCustomerPushDevice();
        }
        return undefined;
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [user?.id]);

  return (
    <>
      <StatusBar
        style={Platform.OS === "android" ? "light" : "dark"}
      />

      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: colors.background },
          animation: "slide_from_right",
        }}
      >
        <Stack.Screen name="index" />
        <Stack.Screen name="(auth)" />
        <Stack.Screen name="(tabs)" />
        <Stack.Screen
          name="chatbot"
          options={{
            headerShown: false,
            presentation: "card",
            animation: "slide_from_right",
          }}
        />
        <Stack.Screen name="requests/new" />
        <Stack.Screen name="requests/[requestId]" />
        <Stack.Screen name="requests/edit/[requestId]" />
        <Stack.Screen name="jobs/[jobId]" />
        <Stack.Screen name="job-chat/[jobId]" />
        <Stack.Screen name="notifications" />
        <Stack.Screen name="history" />
        <Stack.Screen name="invoices" />
        <Stack.Screen name="support" />
        <Stack.Screen name="settings" />
        <Stack.Screen name="profile" />
      </Stack>
    </>
  );
}
