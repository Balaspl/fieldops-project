import Constants from "expo-constants";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";
import { customerApi } from "../api/customer";

export type CustomerNotificationAction = (jobId?: string) => void;

function getProjectId(): string | undefined {
  return (
    Constants.easConfig?.projectId ||
    Constants.expoConfig?.extra?.eas?.projectId ||
    process.env.EXPO_PUBLIC_EAS_PROJECT_ID
  );
}

export function configureCustomerNotifications(
  onOpen: CustomerNotificationAction,
): () => void {
  if (Platform.OS !== "android" && Platform.OS !== "ios") return () => undefined;

  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: false,
      shouldSetBadge: false,
    }),
  });

  const handleResponse = (response: Notifications.NotificationResponse | null) => {
    const data = response?.notification.request.content.data;
    const jobId = data?.job_id ?? data?.jobId;
    onOpen(jobId == null || String(jobId).trim() === "" ? undefined : String(jobId));
  };

  const subscription = Notifications.addNotificationResponseReceivedListener(handleResponse);
  void Notifications.getLastNotificationResponseAsync()
    .then((response) => {
      if (response) {
        handleResponse(response);
        return Notifications.clearLastNotificationResponseAsync();
      }
      return undefined;
    })
    .catch(() => undefined);

  return () => subscription.remove();
}

export async function registerCustomerPushDevice(): Promise<void> {
  if (Platform.OS !== "android" && Platform.OS !== "ios") {
    throw new Error("Push notifications are available in the iOS and Android apps.");
  }
  const projectId = getProjectId();
  if (!projectId) {
    throw new Error("Set EXPO_PUBLIC_EAS_PROJECT_ID to the customer app's EAS project before registering push notifications.");
  }

  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("fieldops_updates", {
      name: "FieldOps updates",
      importance: Notifications.AndroidImportance.HIGH,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: "#168653",
    });
  }

  let permission = await Notifications.getPermissionsAsync();
  if (permission.status !== "granted") {
    permission = await Notifications.requestPermissionsAsync();
  }
  if (permission.status !== "granted") {
    throw new Error("Allow notifications in your device settings to receive FieldOps push updates.");
  }

  const result = await Notifications.getExpoPushTokenAsync({ projectId });
  const token = String(result.data || "").trim();
  if (!token || token.length > 4096) {
    throw new Error("Your device did not provide a valid push token.");
  }
  await customerApi.registerNotificationDevice(token, Platform.OS);
}

export async function unregisterCustomerPushDevice(): Promise<void> {
  await customerApi.unregisterNotificationDevice();
}
