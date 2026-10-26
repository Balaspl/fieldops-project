import { useEffect } from "react";
import { Redirect, Tabs, useRouter } from "expo-router";
import { AppState, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { useAuthStore } from "../../src/auth/authStore";
import { LoadingState } from "../../src/components/ScreenState";
import { useNetworkStatus } from "../../src/hooks/useNetworkStatus";
import { syncPendingJobActions } from "../../src/offline/jobActionSync";
import {
  registerPushTokenForTechnician,
  subscribeToNotificationEvents
} from "../../src/notifications/notificationService";
import {
  logError,
  logEvent
} from "../../src/observability/logger";

import {
  flushPendingGpsPings,
  startTechnicianLocationTracking,
  stopTechnicianLocationTracking
} from "../../src/gps/backgroundLocationService";

export default function AppLayout() {
  const isLoading = useAuthStore((state) => state.isLoading);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const user = useAuthStore((state) => state.user);
  const router = useRouter();
  const networkStatus = useNetworkStatus();

  // Synchronize persisted job actions when the technician is online
  // and when the app returns to the foreground. The synchronizer
  // reconciles each action against authoritative backend state.
  useEffect(() => {
    if (
      isLoading ||
      !isAuthenticated ||
      !user ||
      user.role.toLowerCase() !== "technician" ||
      user.id == null ||
      user.tenant_id == null ||
      String(user.id).trim() === "" ||
      String(user.tenant_id).trim() === "" ||
      networkStatus.isLoading ||
      networkStatus.isOffline
    ) {
      return;
    }

    let active = true;

    const syncScope = {
      technicianId: String(user.id).trim(),
      tenantId: String(user.tenant_id).trim()
    };

    const synchronize = async () => {
      try {
        const result = await syncPendingJobActions(syncScope);

        if (!active) {
          return;
        }

        logEvent("offline.job_actions.sync_finished", {
          result: result.result,
          processed: result.processed,
          synced: result.synced,
          conflicts: result.conflicts,
          failed: result.failed
        });

        if (
          result.result !== "synced" &&
          result.result !== "empty" &&
          result.result !== "already-syncing"
        ) {
          logEvent("offline.job_actions.sync_not_complete", {
            result: result.result,
            message: result.message ?? "No additional details"
          });
        }
      } catch (error: unknown) {
        if (active) {
          logError("offline.job_actions.sync_failed", error);
        }
      }
    };

    void synchronize();

    const appStateSubscription = AppState.addEventListener(
      "change",
      (nextState) => {
        if (nextState === "active") {
          void synchronize();
        }
      }
    );

    return () => {
      active = false;
      appStateSubscription.remove();
    };
  }, [
    isLoading,
    isAuthenticated,
    user?.id,
    user?.tenant_id,
    user?.role,
    networkStatus.isLoading,
    networkStatus.isOffline,
    networkStatus.isConnected,
    networkStatus.isInternetReachable
  ]);

  // Register the native push token for the authenticated technician.
  useEffect(() => {
    if (
      !isAuthenticated ||
      !user ||
      user.role.toLowerCase() !== "technician"
    ) {
      return;
    }

    void registerPushTokenForTechnician({
      id: user.id,
      tenant_id: user.tenant_id
    }).catch((error: unknown) => {
      // Push registration failures must not block app access.
      logError(
        "notifications.registration_failed",
        error
      );
    });
  }, [
    isAuthenticated,
    user?.id,
    user?.tenant_id,
    user?.role
  ]);

  // Track GPS only for an authenticated technician.
  // Permission and network failures must not block app access.
  useEffect(() => {
    if (
      !isAuthenticated ||
      !user ||
      user.tenant_id == null ||
      String(user.tenant_id).trim() === "" ||
      user.role.toLowerCase() !== "technician"
    ) {
      return;
    }

    let active = true;

    const startPromise = startTechnicianLocationTracking({
      technicianId: user.id,
      tenantId: user.tenant_id
    }).catch((error: unknown) => {
      if (active) {
        logError("gps.tracking_start_failed", error);
      }
    });

    const appStateSubscription = AppState.addEventListener(
      "change",
      (nextState) => {
        if (nextState !== "active") {
          return;
        }

        void startPromise
          .then(async () => {
            if (!active) {
              return;
            }

            await flushPendingGpsPings();
          })
          .catch((error: unknown) => {
            if (active) {
              logError(
                "gps.foreground_queue_flush_failed",
                error
              );
            }
          });
      }
    );

    return () => {
      active = false;
      appStateSubscription.remove();

      logEvent("gps.tracking_effect_cleanup", {
        previousTechnicianId: user.id
      });

      void startPromise.then(async () => {
        try {
          const currentAuth = useAuthStore.getState();
          const currentUser = currentAuth.user;

          const activeTechnicianSession =
            currentAuth.isAuthenticated &&
            currentUser != null &&
            currentUser.role.toLowerCase() === "technician" &&
            currentUser.tenant_id != null &&
            String(currentUser.tenant_id).trim() !== "";

          if (activeTechnicianSession) {
            logEvent(
              "gps.tracking_cleanup_skipped_active_technician",
              {
                currentTechnicianId: currentUser.id,
                currentTenantId: currentUser.tenant_id
              }
            );

            return;
          }

          await stopTechnicianLocationTracking({
            preservePendingQueues: true
          });
        } catch (error: unknown) {
          logError("gps.tracking_stop_failed", error);
        }
      });
    };
  }, [
    isAuthenticated,
    user?.id,
    user?.tenant_id,
    user?.role
  ]);

  // Handle notification taps after the technician session is ready.
  useEffect(() => {
    if (
      isLoading ||
      !isAuthenticated ||
      !user ||
      user.role.toLowerCase() !== "technician"
    ) {
      return;
    }

    let active = true;
    let unsubscribe: (() => void) | undefined;

    void subscribeToNotificationEvents((data) => {
      if (!active) {
        return;
      }

      const rawJobId = data.job_id ?? data.jobId;

      const jobId =
        typeof rawJobId === "number" &&
        Number.isFinite(rawJobId)
          ? String(rawJobId)
          : typeof rawJobId === "string"
            ? rawJobId.trim()
            : "";

      if (jobId && !/[\\/]/.test(jobId)) {
        router.push({
          pathname: "/(app)/jobs/[jobId]",
          params: { jobId }
        });
      } else {
        router.push("/(app)/notifications");
      }
    })
      .then((cleanup) => {
        if (active) {
          unsubscribe = cleanup;
        } else {
          cleanup();
        }
      })
      .catch((error: unknown) => {
        logError(
          "notifications.navigation_setup_failed",
          error
        );
      });

    return () => {
      active = false;
      unsubscribe?.();
    };
  }, [
    isLoading,
    isAuthenticated,
    user?.id,
    user?.tenant_id,
    user?.role,
    router
  ]);

  if (isLoading) {
    return <LoadingState label="Checking your session..." />;
  }

  if (!isAuthenticated || !user) {
    return <Redirect href="/(auth)/login" />;
  }

  if (user.role.toLowerCase() !== "technician") {
    return (
      <View style={styles.container}>
        <Text style={styles.title}>Access restricted</Text>
        <Text style={styles.message}>
          This mobile workspace is for technician accounts.
          Contact your FieldOps administrator if you need access.
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.appContainer}>
      {networkStatus.isOffline ? (
        <View
          accessibilityRole="alert"
          style={styles.offlineBanner}
        >
          <Ionicons
            name="cloud-offline-outline"
            size={23}
            color="#8A4B08"
          />
          <View style={styles.offlineBannerContent}>
            <Text style={styles.offlineBannerTitle}>
              No internet connection
            </Text>
            <Text style={styles.offlineBannerMessage}>
              Saved information may be outdated. Job actions need a connection.
            </Text>
          </View>
        </View>
      ) : null}

      <View style={styles.tabsContainer}>
        <Tabs
          screenOptions={{
            headerShown: false,
            tabBarActiveTintColor: "#007F5F",
            tabBarInactiveTintColor: "#91A39B",
            tabBarLabelStyle: styles.tabLabel,
            tabBarStyle: styles.tabBar
          }}
        >
          <Tabs.Screen
            name="dashboard"
            options={{
              title: "Home",
              tabBarLabel: "Home",
              tabBarIcon: ({ color, size, focused }) => (
                <Ionicons
                  name={focused ? "home" : "home-outline"}
                  size={size}
                  color={color}
                />
              )
            }}
          />

          <Tabs.Screen
            name="jobs"
            options={{
              title: "My Jobs",
              tabBarLabel: "My Jobs",
              tabBarIcon: ({ color, size, focused }) => (
                <Ionicons
                  name={focused ? "briefcase" : "briefcase-outline"}
                  size={size}
                  color={color}
                />
              )
            }}
          />

          <Tabs.Screen
            name="history"
            options={{
              title: "Job History",
              tabBarLabel: "History",
              tabBarIcon: ({ color, size, focused }) => (
                <Ionicons
                  name={focused ? "time" : "time-outline"}
                  size={size}
                  color={color}
                />
              )
            }}
          />

          <Tabs.Screen
            name="notifications"
            options={{
              title: "Notifications",
              tabBarLabel: "Alerts",
              tabBarIcon: ({ color, size, focused }) => (
                <Ionicons
                  name={focused ? "notifications" : "notifications-outline"}
                  size={size}
                  color={color}
                />
              )
            }}
          />

          <Tabs.Screen
            name="profile"
            options={{
              title: "My Profile",
              tabBarLabel: "Profile",
              tabBarIcon: ({ color, size, focused }) => (
                <Ionicons
                  name={focused ? "person-circle" : "person-circle-outline"}
                  size={size}
                  color={color}
                />
              )
            }}
          />

          <Tabs.Screen
            name="jobs/[jobId]"
            options={{
              href: null,
              title: "Job Details"
            }}
          />

          <Tabs.Screen
            name="jobs/[jobId]/expenses"
            options={{
              href: null,
              title: "Submit Expense"
            }}
          />

          <Tabs.Screen
            name="jobs/[jobId]/completion"
            options={{
              href: null,
              title: "Complete Job"
            }}
          />

          <Tabs.Screen
            name="jobs/[jobId]/customer-signature"
            options={{
              href: null,
              title: "Customer Signature"
            }}
          />

          <Tabs.Screen
            name="jobs/[jobId]/live-map"
            options={{
              href: null,
              title: "Live Route"
            }}
          />
        </Tabs>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  appContainer: {
    flex: 1,
    backgroundColor: "#F8FAFC"
  },
  tabsContainer: {
    flex: 1
  },
  offlineBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingHorizontal: 16,
    paddingVertical: 11,
    backgroundColor: "#FFF4D7",
    borderBottomWidth: 1,
    borderBottomColor: "#F3D28B"
  },
  offlineBannerContent: {
    flex: 1,
    gap: 2
  },
  offlineBannerTitle: {
    color: "#7C3F0A",
    fontSize: 13,
    fontWeight: "800"
  },
  offlineBannerMessage: {
    color: "#7C3F0A",
    fontSize: 12,
    lineHeight: 17
  },
  container: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#F8FAFC",
    padding: 24
  },
  title: {
    color: "#0F172A",
    fontSize: 23,
    fontWeight: "700",
    marginBottom: 12
  },
  message: {
    color: "#64748B",
    fontSize: 15,
    lineHeight: 23,
    textAlign: "center"
  },
  tabBar: {
    backgroundColor: "#FFFFFF",
    borderTopColor: "#E2E8F0",
    height: 62,
    paddingTop: 6,
    paddingBottom: 5
  },
  tabLabel: {
    fontSize: 12,
    fontWeight: "600"
  }
});
