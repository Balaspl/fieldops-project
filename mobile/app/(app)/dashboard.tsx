import { useCallback, useEffect, useRef, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  deleteOfflineRecord,
  getOfflineRecord,
  setOfflineRecord
} from "../../src/offline/offlineStore";
import {
  ActivityIndicator,
  Animated,
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
import * as Notifications from "expo-notifications";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect, useRouter } from "expo-router";

import { useAuthStore } from "../../src/auth/authStore";
import { getTechnicianDashboard } from "../../src/api/dashboard";
import { getTechnicianNotifications } from "../../src/api/notifications";
import { getTechnicianJobs, type TechnicianJob } from "../../src/api/technician";
import { normalizeJobStatus, getJobStatusLabel } from "../../src/utils/jobStatus";
import { apiClient } from "../../src/api/client";
import { getApiErrorMessage } from "../../src/api/apiError";
import { LoadingState } from "../../src/components/ScreenState";

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

  const pending = getMetricValue(sources, ["pending_acceptance", "pendingAcceptance", "pending_acceptance_jobs", "awaiting_acceptance", "pending_jobs", "pendingJobs", "pending_count"]);
  const active = getMetricValue(sources, ["active_jobs", "activeJobs", "in_progress_jobs", "inProgressJobs"]);
  const completed = getMetricValue(sources, ["total_completed", "completed_jobs", "completedJobs", "completed_count"]);
  const rejected = getMetricValue(sources, ["rejected_jobs", "rejectedJobs"]);
  const categoryCounts = [pending, active, completed, rejected].map((value) => Number(value));
  const calculatedTotal = categoryCounts.every(Number.isFinite)
    ? String(categoryCounts.reduce((total, count) => total + count, 0))
    : getMetricValue(sources, ["total_jobs", "totalJobs", "total_count", "job_count", "total_assigned", "assigned_jobs", "assignedJobs", "assigned_count"]);

  return [
    {
      label: "Total Jobs",
      value: calculatedTotal,
      icon: "briefcase",
      color: "#1769E0",
      backgroundColor: "#F0F6FF",
    },
    {
      label: "Pending Acceptance",
      value: pending,
      icon: "time-outline",
      color: "#E58A00",
      backgroundColor: "#FFF8E8",
    },
    {
      label: "Active Jobs",
      value: active,
      icon: "pulse",
      color: "#087EBD",
      backgroundColor: "#EAF8FF",
    },
    {
      label: "Completed Jobs",
      value: completed,
      icon: "checkmark-circle-outline",
      color: "#078A55",
      backgroundColor: "#EAFBF2",
    },
  ];
}

export default function DashboardScreen() {
  const router = useRouter();
  const notificationShake = useRef(new Animated.Value(0)).current;

  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  const [data, setData] = useState<DashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [isCached, setIsCached] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<string | null>(null);
  const [jobs, setJobs] = useState<TechnicianJob[]>([]);
  const [performance, setPerformance] = useState<Record<string, unknown> | null>(null);
  const [performancePeriod, setPerformancePeriod] = useState<"week" | "month">("week");
  const [unreadNotificationCount, setUnreadNotificationCount] = useState(0);

  useFocusEffect(
    useCallback(() => {
      let active = true;
      const refreshUnreadCount = async () => {
        try {
          const response = await getTechnicianNotifications();
          if (!active) return;
          const unreadCount = response.unread_count ?? response.items.filter(
            (notification) => !(notification.read ?? notification.is_read ?? false)
          ).length;
          setUnreadNotificationCount(unreadCount);
        } catch {
          // Keep the last known unread count when the notification service is unavailable.
        }
      };

      void refreshUnreadCount();
      const subscription = Notifications.addNotificationReceivedListener(() => {
        void refreshUnreadCount();
      });

      return () => {
        active = false;
        subscription.remove();
      };
    }, [])
  );

  useEffect(() => {
    notificationShake.stopAnimation();
    notificationShake.setValue(0);
    if (unreadNotificationCount === 0) return;

    const shake = Animated.sequence([
      Animated.timing(notificationShake, { toValue: 1, duration: 75, useNativeDriver: true }),
      Animated.timing(notificationShake, { toValue: -1, duration: 75, useNativeDriver: true }),
      Animated.timing(notificationShake, { toValue: 1, duration: 75, useNativeDriver: true }),
      Animated.timing(notificationShake, { toValue: -1, duration: 75, useNativeDriver: true }),
      Animated.timing(notificationShake, { toValue: 0, duration: 75, useNativeDriver: true }),
      Animated.delay(900),
    ]);
    const ringing = Animated.loop(shake);
    ringing.start();

    return () => ringing.stop();
  }, [notificationShake, unreadNotificationCount]);

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
      const [dashboardResult, jobResult] = await Promise.allSettled([
        getTechnicianDashboard(),
        getTechnicianJobs(),
      ]);
      if (jobResult.status === "fulfilled") {
        setJobs(Array.isArray(jobResult.value) ? jobResult.value : []);
      }
      if (dashboardResult.status === "rejected") throw dashboardResult.reason;
      const result = dashboardResult.value;
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
    let active = true;
    apiClient.get<Record<string, unknown>>("/api/technician/performance-report", {
      params: { period: performancePeriod },
    }).then(({ data: report }) => {
      if (active) setPerformance(report);
    }).catch(() => {
      if (active) setPerformance(null);
    });
    return () => { active = false; };
  }, [performancePeriod]);

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
  const metricValues = [
    metrics.find((metric) => metric.label === "Total Jobs"),
    metrics.find((metric) => metric.label === "Pending Acceptance"),
    metrics.find((metric) => metric.label === "Active Jobs"),
    metrics.find((metric) => metric.label === "Completed Jobs"),
    { label: "Rejected Jobs", value: getMetricValue([data ?? {}], ["rejected_jobs", "rejectedJobs"]), icon: "close-circle-outline" as DashboardIcon, color: "#F0445B", backgroundColor: "#FFF5F5" },
  ].filter(Boolean) as Metric[];
  const currentJob = jobs.find((job) => ["ACTIVE", "ACCEPTED", "EN_ROUTE", "ON_SITE", "IN_PROGRESS", "PAUSED", "AWAITING_ACCEPTANCE"].includes(normalizeJobStatus(job.status))) ?? jobs[0];
  const recentJobs = jobs.slice(0, 4);
  const formatTime = (value?: string | null) => value && !Number.isNaN(Date.parse(value)) ? new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "Not recorded";

  if (isLoading) {
    return <LoadingState label="Loading dashboard..." variant="dashboard" />;
  }

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

          <Animated.View
            style={{
              transform: [
                {
                  rotate: notificationShake.interpolate({
                    inputRange: [-1, 1],
                    outputRange: ["-18deg", "18deg"],
                  }),
                },
              ],
            }}
          >
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Notifications"
            onPress={() => router.push("/(app)/notifications")}
            style={styles.notificationButton}
          >
            <Ionicons
              name="notifications-outline"
              size={28}
              color={unreadNotificationCount > 0 ? "#F04444" : "#FFFFFF"}
            />

            {unreadNotificationCount > 0 ? (
              <View style={styles.notificationBadge}>
                <Text style={styles.notificationBadgeText}>
                  {unreadNotificationCount > 99 ? "99+" : unreadNotificationCount}
                </Text>
              </View>
            ) : null}
          </Pressable>
          </Animated.View>
        </View>

        <ImageBackground source={require("../../assets/images/technician-banner.png")} style={styles.hero} imageStyle={styles.heroImage} resizeMode="cover">
          <View style={styles.heroOverlay}><Text style={styles.greeting}>{new Date().getHours() < 12 ? "Good morning!" : new Date().getHours() < 18 ? "Good afternoon!" : "Good evening!"}</Text><Text style={styles.greetingName}>Welcome {firstName}</Text></View>
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
            {metricValues.map((metric) => (
              <LinearGradient
                key={metric.label}
                colors={[metric.backgroundColor, "#FFFFFF", `${metric.color}1C`]}
                locations={[0, 0.52, 1]}
                start={{ x: 0, y: 0 }}
                end={{ x: 1, y: 1 }}
                style={[
                  styles.metricCard,
                  { borderColor: `${metric.color}55` },
                ]}
              >
                <LinearGradient colors={[metric.color, `${metric.color}D9`]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.metricCover}>
                  <View style={styles.metricCoverIcon}><Ionicons name={metric.icon} size={21} color={metric.color} /></View>
                  <View style={styles.metricCoverCopy}><Text style={styles.metricCoverEyebrow}>TECHNICIAN OVERVIEW</Text><Text style={styles.metricCoverTitle}>{metric.label}</Text></View>
                  <View pointerEvents="none" style={styles.metricCoverOrb} />
                  <View pointerEvents="none" style={styles.metricCoverOrbSmall} />
                  <Ionicons name="sparkles-outline" size={18} color="rgba(255,255,255,0.9)" />
                </LinearGradient>
                <View style={styles.metricBody}>
                  <Ionicons name={metric.icon} size={86} color={metric.color} style={styles.metricWatermark} />
                  <View style={styles.metricLabelRow}>
                    <Text style={styles.metricLabel} numberOfLines={2}>Current total</Text>
                    <View style={[styles.metricTag, { backgroundColor: `${metric.color}20` }]}>
                      <View style={[styles.metricFooterDot, { backgroundColor: metric.color }]} />
                      <Text style={[styles.metricTagText, { color: metric.color }]}>LIVE</Text>
                    </View>
                  </View>
                  <Text style={styles.metricValue}>{metric.value}</Text>
                  <View style={styles.metricFooter}>
                    <Text style={styles.metricFooterText}>Updated from your jobs</Text>
                    <View style={[styles.metricFooterLine, { backgroundColor: metric.color }]} />
                  </View>
                </View>
              </LinearGradient>
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

        <View style={[styles.panel, styles.currentPanel]}>
          <View style={styles.panelHeading}><Text style={styles.panelTitle}>▣  Current Job</Text>{currentJob ? <Text style={styles.statusPill}>{getJobStatusLabel(currentJob.status)}</Text> : null}</View>
          {currentJob ? <>
            <Text style={styles.currentTitle}>#{currentJob.id} — {currentJob.service_type || "Service"}</Text>
            <Text style={styles.detailLine}>♙  {currentJob.customer_name || "Customer"}</Text>
            <Text style={styles.detailLine}>⌖  {currentJob.location || currentJob.site_address || currentJob.address || "Service location not provided"}</Text>
            <View style={styles.currentFooter}><Text style={styles.detailLine}>◷  Assigned  {formatTime(currentJob.assigned_at)}</Text><Pressable onPress={() => router.push("/(app)/jobs" as never)} style={styles.openJob}><Text style={styles.openJobText}>Open Job  →</Text></Pressable></View>
          </> : <Text style={styles.emptyText}>No current job assigned.</Text>}
        </View>

        <View style={styles.panel}>
          <View style={styles.panelHeading}><Text style={styles.panelTitle}>▥  Performance</Text><View style={styles.periodSwitch}>{(["week", "month"] as const).map((period) => <Pressable key={period} onPress={() => setPerformancePeriod(period)} style={[styles.periodButton, performancePeriod === period && styles.periodButtonActive]}><Text style={[styles.periodText, performancePeriod === period && styles.periodTextActive]}>{period === "week" ? "Week" : "Month"}</Text></Pressable>)}</View></View>
          <View style={styles.performanceRow}><View><Text style={styles.performanceValue}>{String(performance?.period_completed_jobs ?? "—")}</Text><Text style={styles.performanceLabel}>Completed jobs</Text></View><View><Text style={styles.performanceValue}>{performance?.average_completion_minutes == null ? "—" : `${Math.round(Number(performance.average_completion_minutes))}m`}</Text><Text style={styles.performanceLabel}>Avg. completion</Text></View><View><Text style={styles.performanceValue}>{performance?.customer_rating == null ? "—" : Number(performance.customer_rating).toFixed(1)}</Text><Text style={styles.performanceLabel}>Rating</Text></View></View>
        </View>

        <View style={[styles.panel, styles.activityPanel]}>
          <Text style={styles.panelTitle}>◉  Today's Activity</Text>
          {currentJob ? <><Text style={styles.detailLine}>●  {formatTime(currentJob.created_at as string)}   Job created · #{currentJob.id} — {currentJob.service_type || "Service"}</Text><Text style={styles.detailLine}>●  {formatTime(currentJob.updated_at as string)}   Current status: {getJobStatusLabel(currentJob.status)}</Text></> : <Text style={styles.emptyText}>Job activity will appear here when a job is assigned.</Text>}
        </View>

        <View style={[styles.panel, styles.recentPanel]}>
          <View style={styles.panelHeading}><Text style={styles.panelTitle}>▤  Recent Assigned Jobs</Text><Pressable onPress={() => router.push("/(app)/jobs")}><Text style={styles.viewJobs}>View All Jobs</Text></Pressable></View>
          {recentJobs.length ? recentJobs.map((job) => <Pressable key={String(job.id)} onPress={() => router.push("/(app)/jobs")} style={styles.recentRow}><View style={{ flex: 1 }}><Text style={styles.navigationTitle}>#{job.id} — {job.service_type || "Service"}</Text><Text style={styles.jobSub}>{job.location || job.customer_name || "Service location"}</Text></View><Text style={styles.recentStatus}>{getJobStatusLabel(job.status)}  ›</Text></Pressable>) : <Text style={styles.emptyText}>No assigned jobs yet.</Text>}
        </View>


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
    height: 184,
    marginHorizontal: 0,
    marginTop: 0,
    marginBottom: 20,
    justifyContent: "center",
    overflow: "hidden",
    backgroundColor: "#05241A",
  },

  heroImage: {
    borderRadius: 20,
  },

  heroOverlay: {
    width: "100%",
    minHeight: 184,
    justifyContent: "center",
    backgroundColor: "rgba(5, 28, 20, 0.62)",
    paddingHorizontal: 24,
    paddingVertical: 16,
    borderTopRightRadius: 18,
    borderBottomRightRadius: 18,
  },

  greeting: {
    color: "#FFFFFF",
    fontSize: 16,
    fontWeight: "800",
  },

  greetingName: {
    color: "#FFFFFF",
    fontSize: 29,
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
    overflow: "hidden",
    width: "48.5%",
    minHeight: 196,
    borderRadius: 22,
    borderWidth: 1.2,
    shadowColor: "#123B32",
    shadowOffset: { width: 0, height: 7 },
    shadowOpacity: 0.14,
    shadowRadius: 13,
    elevation: 5,
  },
  metricCover: {
    minHeight: 70,
    paddingHorizontal: 12,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
    overflow: "hidden",
  },
  metricCoverIcon: {
    width: 39,
    height: 39,
    borderRadius: 13,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.75)",
    zIndex: 2,
  },
  metricCoverCopy: { flex: 1, zIndex: 2 },
  metricCoverEyebrow: { color: "rgba(255,255,255,0.82)", fontSize: 7, fontWeight: "800", letterSpacing: 0.8 },
  metricCoverTitle: { color: "#FFFFFF", fontSize: 12, fontWeight: "900", marginTop: 2 },
  metricCoverOrb: { position: "absolute", width: 88, height: 88, borderRadius: 44, right: -20, top: -42, backgroundColor: "rgba(255,255,255,0.14)" },
  metricCoverOrbSmall: { position: "absolute", width: 42, height: 42, borderRadius: 22, right: 30, bottom: -28, backgroundColor: "rgba(255,255,255,0.12)" },
  metricWatermark: { position: "absolute", right: -10, bottom: -8, opacity: 0.09, transform: [{ rotate: "-13deg" }] },
  metricFooterLine: { width: 20, height: 3, borderRadius: 2 },
  metricBody: {
    flex: 1,
    minHeight: 126,
    paddingHorizontal: 13,
    paddingTop: 10,
    paddingBottom: 10,
    overflow: "hidden",
    position: "relative",
  },
  metricLabelRow: {
    minHeight: 28,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 5,
  },
  metricTag: {
    minHeight: 21,
    paddingHorizontal: 6,
    borderRadius: 7,
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  metricTagText: { fontSize: 8, fontWeight: "900", letterSpacing: 0.5 },
  metricFooter: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginTop: 6,
  },
  metricFooterDot: { width: 6, height: 6, borderRadius: 3 },
  metricFooterText: { color: "#64758A", fontSize: 9, fontWeight: "600" },
  metricLabel: {
    color: "#43566F",
    flex: 1,
    fontSize: 11,
    lineHeight: 15,
    fontWeight: "700",
  },

  metricValue: {
    color: "#142B45",
    fontSize: 29,
    lineHeight: 34,
    fontWeight: "900",
    marginTop: 4,
  },

  panel: {
    marginHorizontal: 16,
    marginBottom: 14,
    padding: 17,
    borderRadius: 15,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#E3ECE7",
    shadowColor: "#0F172A",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 8,
    elevation: 2,
  },
  currentPanel: { backgroundColor: "#F4F9FF", borderColor: "#CFE4FA" },
  activityPanel: { backgroundColor: "#F4FFF9", borderColor: "#CDEFE0" },
  recentPanel: { backgroundColor: "#FFFBF3", borderColor: "#F4E2BD" },
  panelHeading: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8, marginBottom: 12 },
  panelTitle: { color: "#1F2933", fontSize: 16, fontWeight: "800" },
  currentTitle: { color: "#14213D", fontSize: 18, lineHeight: 24, fontWeight: "800", marginBottom: 12 },
  detailLine: { color: "#52627E", fontSize: 13, lineHeight: 21, marginBottom: 7 },
  statusPill: { color: "#087447", backgroundColor: "#DFF7EA", borderRadius: 20, paddingHorizontal: 10, paddingVertical: 5, overflow: "hidden", fontSize: 11, fontWeight: "800" },
  currentFooter: { marginTop: 13, flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" },
  openJob: { backgroundColor: "#078A4D", paddingHorizontal: 14, paddingVertical: 10, borderRadius: 9 },
  openJobText: { color: "#FFFFFF", fontWeight: "800", fontSize: 13 },
  emptyText: { color: "#718096", fontSize: 13, paddingVertical: 9 },
  periodSwitch: { flexDirection: "row", padding: 3, borderRadius: 9, backgroundColor: "#EDF3F0" },
  periodButton: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 7 },
  periodButtonActive: { backgroundColor: "#078A4D" },
  periodText: { color: "#52627E", fontSize: 11, fontWeight: "700" },
  periodTextActive: { color: "#FFFFFF" },
  performanceRow: { flexDirection: "row", justifyContent: "space-between", paddingTop: 8 },
  performanceValue: { color: "#14213D", fontSize: 20, fontWeight: "900" },
  performanceLabel: { color: "#718096", fontSize: 10, marginTop: 4 },
  recentRow: { flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 12, borderTopWidth: 1, borderTopColor: "#F0E9DB" },
  jobSub: { color: "#718096", fontSize: 12, marginTop: 4 },
  recentStatus: { color: "#1682F8", fontWeight: "700", fontSize: 11, maxWidth: 100, textAlign: "right" },

  navigationTitle: {
    color: "#111827",
    fontSize: 16,
    fontWeight: "800",
    marginBottom: 5,
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
