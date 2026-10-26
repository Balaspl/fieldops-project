
import Constants, {
  ExecutionEnvironment
} from "expo-constants";
import { Platform } from "react-native";
import * as Notifications from "expo-notifications";
import type {
  NotificationResponse
} from "expo-notifications";
import {
  registerTechnicianPushToken
} from "../api/notifications";
import {
  logError,
  logEvent
} from "../observability/logger";

interface TechnicianPushIdentity {
  id: string | number;
  tenant_id?: string | number;
}

export async function configureNotifications(): Promise<void> {
  if (
    Platform.OS !== "android" &&
    Platform.OS !== "ios"
  ) {
    return;
  }

  // Remote push notifications are not supported in Expo Go.
  if (
    Constants.executionEnvironment ===
    ExecutionEnvironment.StoreClient
  ) {
    logEvent("notifications.skipped", {
      reason: "expo_go"
    });
    return;
  }

  try {
    

    if (typeof Notifications.setNotificationHandler !== "function") {
      logError(
        "notifications.handler_api_unavailable",
        new Error(
          `setNotificationHandler type: ${typeof Notifications.setNotificationHandler}; exports: ${Object.keys(Notifications).join(", ")}`
        )
      );
      return;
    }

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
    console.error(
      "[FieldOps] Full notification configuration error:",
      error
    );
    if (error instanceof Error) {
      console.error("[FieldOps] Error stack:", error.stack);
    }
    logError("notifications.configure_failed", error);
  }
}

/**
 * Request notification permission and register the native
 * Android/iOS device token with the existing backend.
 *
 * The backend remains authoritative for identity and tenant
 * authorization. Device tokens are never written to logs.
 */
export async function registerPushTokenForTechnician(
  user: TechnicianPushIdentity
): Promise<void> {
  const deviceType = Platform.OS;

  if (
    deviceType !== "android" &&
    deviceType !== "ios"
  ) {
    logEvent("notifications.registration_skipped", {
      reason: "unsupported_platform"
    });
    return;
  }

  if (
    Constants.executionEnvironment ===
    ExecutionEnvironment.StoreClient
  ) {
    logEvent("notifications.registration_skipped", {
      reason: "expo_go"
    });
    return;
  }

  const userId = String(user.id ?? "").trim();
  const tenantId = String(
    user.tenant_id ?? ""
  ).trim();

  if (!userId || !tenantId) {
    logEvent("notifications.registration_skipped", {
      reason: "missing_authenticated_identity"
    });
    return;
  }

  

  // Create the Android notification channel before registration.
  if (deviceType === "android") {
    await Notifications.setNotificationChannelAsync(
      "job_assignments",
      {
        name: "FieldOps job assignments",
        importance: Notifications.AndroidImportance.HIGH,
        vibrationPattern: [0, 250, 250, 250],
        lightColor: "#0F766E"
      }
    );
  }

  let permission =
    await Notifications.getPermissionsAsync();

  if (permission.status !== "granted") {
    permission =
      await Notifications.requestPermissionsAsync();
  }

  if (permission.status !== "granted") {
    logEvent("notifications.permission_not_granted", {
      platform: deviceType
    });
    return;
  }

  // This is the native FCM/APNs token expected by the
  // existing backend, not an Expo push-service token.
  const nativeToken =
    await Notifications.getDevicePushTokenAsync();

  const token = String(nativeToken.data ?? "").trim();

  if (!token || token.length > 4096) {
    throw new Error(
      "The device did not return a valid push token."
    );
  }

  await registerTechnicianPushToken({
    userId,
    tenantId,
    token,
    deviceType
  });

  logEvent("notifications.token_registered", {
    platform: deviceType
  });
}


export async function subscribeToNotificationEvents(
  onResponse: (data: Record<string, unknown>) => void
): Promise<() => void> {
  if (
    Platform.OS !== "android" &&
    Platform.OS !== "ios"
  ) {
    return () => undefined;
  }

  if (
    Constants.executionEnvironment ===
    ExecutionEnvironment.StoreClient
  ) {
    return () => undefined;
  }

  try {
    

    let lastResponseKey: string | null = null;

    const handleResponse = (
      response: NotificationResponse | null
    ) => {
      if (!response) {
        return;
      }

      // Prevent handling the same tap twice.
      const responseKey =
        `${response.notification.request.identifier}:` +
        response.actionIdentifier;

      if (responseKey === lastResponseKey) {
        return;
      }

      lastResponseKey = responseKey;

      const rawData =
        response.notification.request.content.data;

      const data: Record<string, unknown> =
        rawData && typeof rawData === "object"
          ? rawData as Record<string, unknown>
          : {};

      const jobId = data.job_id;

      logEvent("notifications.opened", {
        platform: Platform.OS,
        hasJobId:
          (typeof jobId === "string" && jobId.length > 0) ||
          typeof jobId === "number"
      });

      try {
        onResponse(data);
      } catch (error: unknown) {
        logError(
          "notifications.response_handler_failed",
          error
        );
      }
    };

    const receivedSubscription =
      Notifications.addNotificationReceivedListener(() => {
        // Do not log notification content or device tokens.
        logEvent("notifications.received", {
          platform: Platform.OS
        });
      });

    const responseSubscription =
      Notifications.addNotificationResponseReceivedListener(
        handleResponse
      );

    // Also handle a notification that opened the app from a
    // terminated state, after the authenticated layout mounts.
    try {
      const lastResponse =
        await Notifications.getLastNotificationResponseAsync();

      if (lastResponse) {
        handleResponse(lastResponse);
        await Notifications.clearLastNotificationResponseAsync();
      }
    } catch (error: unknown) {
      logError(
        "notifications.last_response_restore_failed",
        error
      );
    }

    logEvent("notifications.listeners_registered", {
      platform: Platform.OS
    });

    return () => {
      receivedSubscription.remove();
      responseSubscription.remove();
    };
  } catch (error: unknown) {
    logError(
      "notifications.listeners_setup_failed",
      error
    );

    return () => undefined;
  }
}
