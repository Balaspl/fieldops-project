import { useCallback, useEffect, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  deleteOfflineRecord,
  getOfflineRecord,
  setOfflineRecord
} from "../../src/offline/offlineStore";
import {
  ActivityIndicator,
  Image,
  ImageBackground,
  Pressable,
  RefreshControl,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { useAuthStore } from "../../src/auth/authStore";
import { getTechnicianDashboard } from "../../src/api/dashboard";
import { getApiErrorMessage } from "../../src/api/apiError";

type DashboardData = Record<string, unknown>;

const DASHBOARD_CACHE_PREFIX = "fieldops:dashboard:cache:v1";

interface DashboardCacheEntry {
  version: 1;
  tenantId: string;
  technicianId: string;
  savedAt: string;
  data: DashboardData;
}

type DashboardIcon = keyof typeof Ionicons.glyphMap;

interface Metric {
  label: string;
  value: string;
  icon: DashboardIcon;
  color: string;
  backgroundColor: string;
}

interface QuickAccessItem {
  title: string;
  description: string;
  icon: DashboardIcon;
  route: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  );
}

function getDashboardCacheKey(
  tenantId: string | null,
  technicianId: string | null
): string | null {
  if (!tenantId || !technicianId) {
    return null;
  }

  return `${DASHBOARD_CACHE_PREFIX}:${encodeURIComponent(
    tenantId
  )}:${encodeURIComponent(technicianId)}`;
}

function isDashboardCacheEntry(
  value: unknown,
  tenantId: string,
  technicianId: string
): value is DashboardCacheEntry {
  if (!isRecord(value)) {
    return false;
  }

  return (
    value.version === 1 &&
    value.tenantId === tenantId &&
    value.technicianId === technicianId &&
    typeof value.savedAt === "string" &&
    Number.isFinite(Date.parse(value.savedAt)) &&
    isRecord(value.data)
  );
}

function getSavedAtLabel(value: string | null): string | null {
  if (!value) {
    return null;
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return null;
  }

  return date.toLocaleString();
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
      label: "Total Jobs",
      value: getMetricValue(sources, [
        "total_jobs",
        "totalJobs",
        "total_count",
        "job_count",
        "total_assigned",
        "assigned_jobs",
        "assignedJobs",
        "assigned_count",
      ]),
      icon: "briefcase",
      color: "#079653",
      backgroundColor: "#EFFAF4",
    },
    {
      label: "Pending Acceptance",
      value: getMetricValue(sources, [
        "pending_acceptance",
        "pendingAcceptance",
        "pending_acceptance_jobs",
        "awaiting_acceptance",
        "pending_jobs",
        "pendingJobs",
        "pending_count",
      ]),
      icon: "time-outline",
      color: "#F58212",
      backgroundColor: "#FFF7ED",
    },
    {
      label: "Active Jobs",
      value: getMetricValue(sources, [
        "active_jobs",
        "activeJobs",
        "in_progress_jobs",
        "inProgressJobs",
      ]),
      icon: "pulse",
      color: "#147DF5",
      backgroundColor: "#F0F7FF",
    },
    {
      label: "Completed Jobs",
      value: getMetricValue(sources, [
        "total_completed",
        "completed_jobs",
        "completedJobs",
        "completed_count",
      ]),
      icon: "checkmark-circle-outline",
      color: "#079653",
      backgroundColor: "#EFFAF4",
    },
  ];
}

const quickAccessItems: QuickAccessItem[] = [
  {
    title: "My Jobs",
    description: "View assignments and open individual job details.",
    icon: "document-text-outline",
    route: "/(app)/jobs",
  },
  {
    title: "Job History",
    description: "Review previously completed service jobs.",
    icon: "time-outline",
    route: "/(app)/history",
  },
  {
    title: "Notifications",
    description: "View important updates and alerts.",
    icon: "notifications-outline",
    route: "/(app)/notifications",
  },
  {
    title: "My Profile",
    description: "View and manage your profile information.",
    icon: "person-outline",
    route: "/(app)/profile",
  },
];

export default function DashboardScreen() {
  const router = useRouter();

  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  const [data, setData] = useState<DashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [isCached, setIsCached] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);

  const technicianId =
    user?.id == null ? null : String(user.id).trim() || null;
  const tenantId =
    user?.tenant_id == null
      ? null
      : String(user.tenant_id).trim() || null;

  const loadDashboard = useCallback(async (refresh = false) => {
    if (refresh) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }

    setError(null);

    const cacheKey = getDashboardCacheKey(tenantId, technicianId);

    const cacheScope =
      tenantId && technicianId
        ? { tenantId, technicianId }
        : null;

    // Read encrypted cache first, then migrate a valid legacy cache.
    if (!refresh && cacheScope && tenantId && technicianId) {
      try {
        let parsedValue = await getOfflineRecord<unknown>(
          cacheScope,
          "dashboard",
          "summary"
        );

        if (!parsedValue && cacheKey) {
          const storedValue = await AsyncStorage.getItem(cacheKey);

          if (storedValue) {
            const legacyValue: unknown = JSON.parse(storedValue);

            if (
              isDashboardCacheEntry(
                legacyValue,
                tenantId,
                technicianId
              )
            ) {
              await setOfflineRecord(
                cacheScope,
                "dashboard",
                "summary",
                legacyValue
              );

              parsedValue = legacyValue;
            }

            // Remove legacy data after attempting migration.
            await AsyncStorage.removeItem(cacheKey);
          }
        } else if (cacheKey) {
          // Encrypted copy exists, so discard the old plaintext copy.
          await AsyncStorage.removeItem(cacheKey);
        }

        if (parsedValue) {
          if (
            isDashboardCacheEntry(
              parsedValue,
              tenantId,
              technicianId
            )
          ) {
            setData(parsedValue.data);
            setIsCached(true);
            setLastUpdatedAt(parsedValue.savedAt);
          } else {
            await deleteOfflineRecord(
              cacheScope,
              "dashboard",
              "summary"
            );
          }
        }
      } catch {
        // Cache failures must never prevent a request to the backend.
      }
    }

    try {
      const result = await getTechnicianDashboard();
      const savedAt = new Date().toISOString();

      setData(result);
      setIsCached(false);
      setLastUpdatedAt(savedAt);
      setError(null);

      if (cacheKey && tenantId && technicianId) {
        const cacheEntry: DashboardCacheEntry = {
          version: 1,
          tenantId,
          technicianId,
          savedAt,
          data: result
        };

        try {
          await setOfflineRecord(
            { tenantId, technicianId },
            "dashboard",
            "summary",
            cacheEntry
          );
        } catch {
          // The live dashboard remains usable if secure caching fails.
        }
      }
    } catch (loadError: unknown) {
      // Any data already on screen is now a stale snapshot until the
      // backend can confirm a newer response.
      setIsCached(true);
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
  }, [tenantId, technicianId]);

  useEffect(() => {
    // Avoid showing the previous account's information during a session
    // change. The next request can then restore only the matching cache.
    setData(null);
    setIsCached(false);
    setLastUpdatedAt(null);
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

  const fullName = String(user?.full_name ?? "").trim();
  const emailName = String(user?.email ?? "").split("@")[0]?.trim() ?? "";

  const displayName = fullName || emailName || "Technician";
  const firstName = displayName.split(/\s+/)[0];

  const metrics = data ? buildMetrics(data) : [];

  return (
    <View style={styles.screen}>
      <StatusBar barStyle="light-content" backgroundColor="#00432E" />

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={() => void loadDashboard(true)}
            tintColor="#078A4D"
          />
        }
        showsVerticalScrollIndicator={false}
      >
        {/* Branded header */}
        <View style={styles.header}>
          <Image
            source={require("../../assets/images/fieldops-logo.png")}
            style={styles.logo}
            resizeMode="contain"
            accessibilityLabel="FieldOps Commander"
          />

          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Notifications"
            onPress={() => router.push("/(app)/notifications")}
            style={styles.notificationButton}
          >
            <Ionicons
              name="notifications-outline"
              size={28}
              color="#FFFFFF"
            />

            <View style={styles.notificationBadge}>
              <Text style={styles.notificationBadgeText}>3</Text>
            </View>
          </Pressable>
        </View>

        {/* Hero banner */}
        <ImageBackground
          source={require("../../assets/images/fieldops-hero.png")}
          style={styles.hero}
          imageStyle={styles.heroImage}
          resizeMode="cover"
        >
          <View style={styles.heroOverlay}>
            <Text style={styles.greeting}>Good Morning,</Text>

            <Text style={styles.greetingName}>
              {firstName}!
            </Text>

            <Text style={styles.heroMessage}>
              Your field operations are running smoothly.
            </Text>
          </View>
        </ImageBackground>

        {/* Job overview */}
        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Job Overview</Text>

          <Pressable
            accessibilityRole="button"
            onPress={() => router.push("/(app)/jobs")}
          >
            <Text style={styles.viewJobs}>View jobs →</Text>
          </Pressable>
        </View>

        {isLoading ? (
          <View style={styles.loadingBox}>
            <ActivityIndicator size="large" color="#079653" />
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

        {isCached && data ? (
          <View style={styles.cachedNotice}>
            <Ionicons
              name="cloud-offline-outline"
              size={21}
              color="#8A5A09"
              style={styles.cachedNoticeIcon}
            />
            <View style={styles.cachedNoticeContent}>
              <Text style={styles.cachedNoticeTitle}>
                Showing saved dashboard data
              </Text>
              <Text style={styles.cachedNoticeMessage}>
                This information may be outdated.
                {getSavedAtLabel(lastUpdatedAt)
                  ? ` Last saved ${getSavedAtLabel(lastUpdatedAt)}.`
                  : ""}
              </Text>
            </View>
          </View>
        ) : null}

        {data ? (
          <View style={styles.metricsGrid}>
            {metrics.map((metric) => (
              <View
                key={metric.label}
                style={[
                  styles.metricCard,
                  { backgroundColor: metric.backgroundColor },
                ]}
              >
                <View
                  style={[
                    styles.metricIcon,
                    { backgroundColor: metric.color },
                  ]}
                >
                  <Ionicons
                    name={metric.icon}
                    size={29}
                    color="#FFFFFF"
                  />
                </View>

                <View style={styles.metricDetails}>
                  <Text style={styles.metricLabel}>
                    {metric.label}
                  </Text>

                  <Text style={styles.metricValue}>
                    {metric.value}
                  </Text>
                </View>
              </View>
            ))}
          </View>
        ) : null}

        {!isLoading &&
        data &&
        metrics.every((metric) => metric.value === "--") ? (
          <Text style={styles.muted}>
            Dashboard data was received, but the expected job-count
            fields were not found. The metrics need to match the
            backend response fields.
          </Text>
        ) : null}

        {/* Quick access */}
        <Text style={styles.quickTitle}>Quick access</Text>

        {quickAccessItems.map((item) => (
          <Pressable
            key={item.title}
            accessibilityRole="button"
            onPress={() => router.push(item.route as never)}
            style={styles.navigationCard}
          >
            <View style={styles.navigationIcon}>
              <Ionicons
                name={item.icon}
                size={28}
                color="#075B3C"
              />
            </View>

            <View style={styles.navigationText}>
              <Text style={styles.navigationTitle}>
                {item.title}
              </Text>

              <Text style={styles.navigationDescription}>
                {item.description}
              </Text>
            </View>

            <Ionicons
              name="chevron-forward"
              size={24}
              color="#718096"
            />
          </Pressable>
        ))}

        <Pressable
          accessibilityRole="button"
          disabled={isLoggingOut}
          onPress={() => void handleLogout()}
          style={[
            styles.logoutButton,
            isLoggingOut && styles.disabled,
          ]}
        >
          {isLoggingOut ? (
            <ActivityIndicator color="#FFFFFF" />
          ) : (
            <Text style={styles.logoutText}>Sign Out</Text>
          )}
        </Pressable>
      </ScrollView>


    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#FFFFFF",
  },

  scroll: {
    flex: 1,
  },

  content: {
    paddingBottom: 24,
  },

  header: {
    minHeight: 145,
    backgroundColor: "#00432E",
    paddingHorizontal: 20,
    paddingTop: 28,
    paddingBottom: 20,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },

  logo: {
    width: 235,
    height: 76,
  },

  notificationButton: {
    width: 48,
    height: 48,
    alignItems: "center",
    justifyContent: "center",
    marginLeft: 8,
  },

  notificationBadge: {
    position: "absolute",
    top: 0,
    right: 0,
    minWidth: 21,
    height: 21,
    borderRadius: 11,
    backgroundColor: "#F04444",
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 4,
  },

  notificationBadgeText: {
    color: "#FFFFFF",
    fontSize: 11,
    fontWeight: "800",
  },

  hero: {
    height: 220,
    marginHorizontal: 10,
    marginTop: 0,
    marginBottom: 25,
    justifyContent: "center",
    overflow: "hidden",
    backgroundColor: "#06452F",
  },

  heroImage: {
    borderRadius: 20,
  },

  heroOverlay: {
    width: "68%",
    minHeight: 164,
    justifyContent: "center",
    backgroundColor: "rgba(0, 55, 37, 0.78)",
    paddingHorizontal: 18,
    paddingVertical: 16,
    borderTopRightRadius: 18,
    borderBottomRightRadius: 18,
  },

  greeting: {
    color: "#FFFFFF",
    fontSize: 23,
    fontWeight: "800",
  },

  greetingName: {
    color: "#70E7B0",
    fontSize: 28,
    fontWeight: "900",
    marginTop: 2,
  },

  heroMessage: {
    color: "#FFFFFF",
    fontSize: 14,
    lineHeight: 20,
    marginTop: 9,
  },

  sectionHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginHorizontal: 18,
    marginBottom: 15,
  },

  sectionTitle: {
    color: "#16241D",
    fontSize: 20,
    fontWeight: "800",
  },

  viewJobs: {
    color: "#078A4D",
    fontSize: 13,
    fontWeight: "700",
  },

  loadingBox: {
    alignItems: "center",
    padding: 24,
  },

  muted: {
    color: "#64786D",
    fontSize: 13,
    lineHeight: 20,
    marginHorizontal: 18,
    marginVertical: 12,
  },

  cachedNotice: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10,
    marginHorizontal: 18,
    marginBottom: 18,
    padding: 13,
    borderRadius: 14,
    backgroundColor: "#FFF7E6",
    borderColor: "#F6D89B",
    borderWidth: 1,
  },

  cachedNoticeIcon: {
    marginTop: 1,
  },

  cachedNoticeContent: {
    flex: 1,
  },

  cachedNoticeTitle: {
    color: "#7C4A03",
    fontSize: 13,
    fontWeight: "800",
  },

  cachedNoticeMessage: {
    color: "#855F20",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 4,
  },

  errorCard: {
    marginHorizontal: 18,
    marginBottom: 20,
    padding: 15,
    borderRadius: 14,
    backgroundColor: "#FFF1F0",
    borderColor: "#FECACA",
    borderWidth: 1,
    gap: 12,
  },

  errorText: {
    color: "#C73737",
    fontSize: 14,
    lineHeight: 21,
  },

  retryButton: {
    alignSelf: "flex-start",
    paddingVertical: 4,
  },

  retryText: {
    color: "#078A4D",
    fontWeight: "800",
  },

  metricsGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    marginBottom: 29,
    rowGap: 12,
  },

  metricCard: {
    width: "48%",
    minHeight: 164,
    borderRadius: 21,
    padding: 14,
    borderWidth: 1,
    borderColor: "#EEF2EF",
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 11,
  },

  metricIcon: {
    width: 49,
    height: 49,
    borderRadius: 15,
    alignItems: "center",
    justifyContent: "center",
  },

  metricDetails: {
    flex: 1,
    paddingTop: 3,
  },

  metricLabel: {
    color: "#172554",
    fontSize: 13,
    lineHeight: 18,
    fontWeight: "600",
  },

  metricValue: {
    color: "#0F172A",
    fontSize: 30,
    fontWeight: "900",
    marginTop: 7,
  },

  quickTitle: {
    color: "#111827",
    fontSize: 22,
    fontWeight: "800",
    marginHorizontal: 18,
    marginBottom: 15,
  },

  navigationCard: {
    minHeight: 92,
    marginHorizontal: 16,
    marginBottom: 12,
    paddingHorizontal: 14,
    paddingVertical: 13,
    borderRadius: 18,
    borderWidth: 1.2,
    borderColor: "#DCE5EF",
    backgroundColor: "#FFFFFF",
    flexDirection: "row",
    alignItems: "center",
  },

  navigationIcon: {
    width: 54,
    height: 54,
    borderRadius: 16,
    backgroundColor: "#F0FAF5",
    alignItems: "center",
    justifyContent: "center",
    marginRight: 13,
  },

  navigationText: {
    flex: 1,
    paddingRight: 8,
  },

  navigationTitle: {
    color: "#111827",
    fontSize: 16,
    fontWeight: "800",
    marginBottom: 5,
  },

  navigationDescription: {
    color: "#718096",
    fontSize: 12,
    lineHeight: 19,
  },

  logoutButton: {
    minHeight: 50,
    marginHorizontal: 18,
    marginTop: 12,
    borderRadius: 14,
    backgroundColor: "#B91C1C",
    alignItems: "center",
    justifyContent: "center",
  },

  logoutText: {
    color: "#FFFFFF",
    fontSize: 15,
    fontWeight: "800",
  },

  disabled: {
    opacity: 0.6,
  },

  bottomNavigation: {
    minHeight: 72,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-around",
    backgroundColor: "#FFFFFF",
    borderTopWidth: 1,
    borderTopColor: "#E7ECE9",
    paddingHorizontal: 8,
    paddingVertical: 7,
  },

  tabItem: {
    flex: 1,
    minHeight: 58,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
    gap: 3,
  },

  activeTab: {
    backgroundColor: "#E7F8EF",
  },

  tabLabel: {
    color: "#475569",
    fontSize: 12,
  },

  activeTabLabel: {
    color: "#078A4D",
    fontSize: 12,
    fontWeight: "800",
  },
});