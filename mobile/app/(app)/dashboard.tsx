
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View
} from "react-native";
import { useRouter } from "expo-router";
import { useAuthStore } from "../../src/auth/authStore";
import { getTechnicianDashboard } from "../../src/api/dashboard";
import { getApiErrorMessage } from "../../src/api/apiError";

type DashboardData = Record<string, unknown>;

interface Metric {
  label: string;
  value: string;
  color: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getMetricValue(
  sources: Record<string, unknown>[],
  keys: string[]
): string {
  for (const source of sources) {
    for (const key of keys) {
      const value = source[key];

      if (typeof value === "number" && Number.isFinite(value)) {
        return String(value);
      }

      if (
        typeof value === "string" &&
        value.trim() !== "" &&
        Number.isFinite(Number(value))
      ) {
        return value;
      }
    }
  }

  return "--";
}

function buildMetrics(data: DashboardData): Metric[] {
  const sources: Record<string, unknown>[] = [data];

  for (const key of ["summary", "kpis", "metrics", "counts"]) {
    const value = data[key];

    if (isRecord(value)) {
      sources.push(value);
    }
  }

  return [
    {
      label: "Assigned jobs",
      value: getMetricValue(sources, [
        "assigned_jobs",
        "assignedJobs",
        "assigned_count"
      ]),
      color: "#1D4ED8"
    },
    {
      label: "Active jobs",
      value: getMetricValue(sources, [
        "active_jobs",
        "activeJobs",
        "in_progress_jobs",
        "inProgressJobs"
      ]),
      color: "#0F766E"
    },
    {
      label: "Completed jobs",
      value: getMetricValue(sources, [
        "completed_jobs",
        "completedJobs",
        "completed_count"
      ]),
      color: "#15803D"
    },
    {
      label: "Pending jobs",
      value: getMetricValue(sources, [
        "pending_jobs",
        "pendingJobs",
        "pending_count"
      ]),
      color: "#B45309"
    }
  ];
}

export default function DashboardScreen() {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  const [data, setData] = useState<DashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  const loadDashboard = useCallback(async (refresh = false) => {
    if (refresh) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }

    setError(null);

    try {
      const result = await getTechnicianDashboard();
      setData(result);
    } catch (loadError: unknown) {
      setError(
        getApiErrorMessage(
          loadError,
          "Unable to load dashboard data. Please try again."
        )
      );
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  async function handleLogout() {
    if (isLoggingOut) {
      return;
    }

    setIsLoggingOut(true);

    try {
      await logout();
      router.replace("/(auth)/login");
    } catch {
      setError("Sign out could not be completed. Please try again.");
    } finally {
      setIsLoggingOut(false);
    }
  }

  const displayName =
    user?.full_name?.trim() || user?.email || "Technician";

  const metrics = data ? buildMetrics(data) : [];

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={isRefreshing}
          onRefresh={() => void loadDashboard(true)}
        />
      }
    >
      <View style={styles.header}>
        <View>
          <Text style={styles.brand}>FieldOps</Text>
          <Text style={styles.headerSubtitle}>
            Technician workspace
          </Text>
        </View>

        <View style={styles.avatar}>
          <Text style={styles.avatarText}>
            {displayName.charAt(0).toUpperCase()}
          </Text>
        </View>
      </View>

      <View style={styles.welcomeCard}>
        <Text style={styles.eyebrow}>YOUR DASHBOARD</Text>
        <Text style={styles.welcomeTitle}>
          Hello, {displayName}
        </Text>
        <Text style={styles.welcomeMessage}>
          Here is your FieldOps workspace overview.
        </Text>
      </View>

      <View style={styles.sectionHeader}>
        <Text style={styles.sectionTitle}>Job overview</Text>

        <Pressable
          accessibilityRole="button"
          onPress={() => router.push("/(app)/jobs")}
        >
          <Text style={styles.link}>View jobs</Text>
        </Pressable>
      </View>

      {isLoading ? (
        <View style={styles.loadingBox}>
          <ActivityIndicator size="large" color="#1D4ED8" />
          <Text style={styles.muted}>Loading dashboard...</Text>
        </View>
      ) : null}

      {error ? (
        <View style={styles.errorCard}>
          <Text accessibilityRole="alert" style={styles.errorText}>
            {error}
          </Text>

          <Pressable
            accessibilityRole="button"
            onPress={() => void loadDashboard()}
            style={styles.retryButton}
          >
            <Text style={styles.retryText}>Try again</Text>
          </Pressable>
        </View>
      ) : null}

      {!isLoading && data ? (
        <>
          <View style={styles.metricsGrid}>
            {metrics.map((metric) => (
              <View key={metric.label} style={styles.metricCard}>
                <View
                  style={[
                    styles.metricAccent,
                    { backgroundColor: metric.color }
                  ]}
                />

                <Text style={styles.metricValue}>
                  {metric.value}
                </Text>

                <Text style={styles.metricLabel}>
                  {metric.label}
                </Text>
              </View>
            ))}
          </View>

          {metrics.every((metric) => metric.value === "--") ? (
            <Text style={styles.muted}>
              Dashboard data was received, but the expected job-count
              fields were not found. The metrics must be mapped to the
              actual backend response contract.
            </Text>
          ) : null}
        </>
      ) : null}

      <Text style={styles.sectionTitle}>Quick access</Text>

      <Pressable
        accessibilityRole="button"
        onPress={() => router.push("/(app)/jobs")}
        style={styles.navigationCard}
      >
        <Text style={styles.navigationTitle}>My Jobs</Text>
        <Text style={styles.navigationDescription}>
          View assignments and open individual job details.
        </Text>
      </Pressable>

      <Pressable
        accessibilityRole="button"
        onPress={() => router.push("/(app)/history")}
        style={styles.navigationCard}
      >
        <Text style={styles.navigationTitle}>Job History</Text>
        <Text style={styles.navigationDescription}>
          Review previously completed service jobs.
        </Text>
      </Pressable>

      <Pressable
        accessibilityRole="button"
        onPress={() => router.push("/(app)/notifications")}
        style={styles.navigationCard}
      >
        <Text style={styles.navigationTitle}>Notifications</Text>
        <Text style={styles.navigationDescription}>
          Check updates from your FieldOps workspace.
        </Text>
      </Pressable>

      <Pressable
        accessibilityRole="button"
        disabled={isLoggingOut}
        onPress={() => void handleLogout()}
        style={[styles.logoutButton, isLoggingOut && styles.disabled]}
      >
        {isLoggingOut ? (
          <ActivityIndicator color="#FFFFFF" />
        ) : (
          <Text style={styles.logoutText}>Sign out</Text>
        )}
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#F8FAFC"
  },
  content: {
    padding: 20,
    paddingTop: 42,
    paddingBottom: 36
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 26
  },
  brand: {
    color: "#1D4ED8",
    fontSize: 25,
    fontWeight: "800"
  },
  headerSubtitle: {
    color: "#64748B",
    fontSize: 13,
    marginTop: 4
  },
  avatar: {
    width: 46,
    height: 46,
    borderRadius: 23,
    backgroundColor: "#DBEAFE",
    alignItems: "center",
    justifyContent: "center"
  },
  avatarText: {
    color: "#1D4ED8",
    fontSize: 20,
    fontWeight: "700"
  },
  welcomeCard: {
    backgroundColor: "#1D4ED8",
    padding: 22,
    borderRadius: 16,
    marginBottom: 26
  },
  eyebrow: {
    color: "#DBEAFE",
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 1.2,
    marginBottom: 12
  },
  welcomeTitle: {
    color: "#FFFFFF",
    fontSize: 25,
    fontWeight: "800",
    marginBottom: 8
  },
  welcomeMessage: {
    color: "#E2E8F0",
    fontSize: 14,
    lineHeight: 21
  },
  sectionHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: 12
  },
  sectionTitle: {
    color: "#0F172A",
    fontSize: 18,
    fontWeight: "700",
    marginBottom: 12
  },
  link: {
    color: "#1D4ED8",
    fontSize: 13,
    fontWeight: "700"
  },
  metricsGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 12,
    marginBottom: 28
  },
  metricCard: {
    flexGrow: 1,
    flexBasis: "45%",
    minHeight: 112,
    backgroundColor: "#FFFFFF",
    borderRadius: 12,
    borderColor: "#E2E8F0",
    borderWidth: 1,
    padding: 15
  },
  metricAccent: {
    width: 28,
    height: 4,
    borderRadius: 2,
    marginBottom: 13
  },
  metricValue: {
    color: "#0F172A",
    fontSize: 27,
    fontWeight: "800"
  },
  metricLabel: {
    color: "#64748B",
    fontSize: 12,
    marginTop: 5
  },
  loadingBox: {
    alignItems: "center",
    padding: 24
  },
  muted: {
    color: "#64748B",
    fontSize: 13,
    lineHeight: 20,
    marginBottom: 24
  },
  errorCard: {
    backgroundColor: "#FEF2F2",
    borderColor: "#FECACA",
    borderWidth: 1,
    borderRadius: 10,
    padding: 14,
    marginBottom: 24
  },
  errorText: {
    color: "#B91C1C",
    fontSize: 14,
    lineHeight: 21
  },
  retryButton: {
    alignSelf: "flex-start",
    paddingVertical: 10
  },
  retryText: {
    color: "#1D4ED8",
    fontWeight: "700"
  },
  navigationCard: {
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#E2E8F0",
    borderRadius: 12,
    padding: 17,
    marginBottom: 12
  },
  navigationTitle: {
    color: "#0F172A",
    fontSize: 16,
    fontWeight: "700",
    marginBottom: 6
  },
  navigationDescription: {
    color: "#64748B",
    fontSize: 13,
    lineHeight: 20
  },
  logoutButton: {
    minHeight: 50,
    backgroundColor: "#DC2626",
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 20
  },
  logoutText: {
    color: "#FFFFFF",
    fontSize: 15,
    fontWeight: "700"
  },
  disabled: {
    opacity: 0.6
  }
});
