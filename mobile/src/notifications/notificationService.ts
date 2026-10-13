
import Constants, { ExecutionEnvironment } from "expo-constants";
import { Platform } from "react-native";
import { logError, logEvent } from "../observability/logger";

export async function configureNotifications(): Promise<void> {
  if (Platform.OS !== "android" && Platform.OS !== "ios") {
    return;
  }

  // Remote push notifications are not supported in Expo Go.
  // Avoid importing expo-notifications in that environment.
  if (
    Constants.executionEnvironment === ExecutionEnvironment.StoreClient
  ) {
    logEvent("notifications.skipped", {
      reason: "expo_go"
    });
    return;
  }

  try {
    const Notifications = await import("expo-notifications");

    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowBanner: true,
        shouldShowList: true,
        shouldPlaySound: false,
        shouldSetBadge: false
      })
    });

    logEvent("notifications.configured");
  } catch (error: unknown) {
    logError("notifications.configure_failed", error);
  }
}
