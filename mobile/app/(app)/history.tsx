import { useCallback, useEffect, useState } from "react";
import {
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  deleteOfflineRecord,
  getOfflineRecord,
  setOfflineRecord
} from "../../src/offline/offlineStore";
import { useRouter } from "expo-router";
import { useAuthStore } from "../../src/auth/authStore";
import {
  getTechnicianJobHistory,
  type TechnicianJob,
  type TechnicianJobCollection
} from "../../src/api/technician";
import {
  EmptyState,
  ErrorState,
  LoadingState
} from "../../src/components/ScreenState";

const JOB_HISTORY_CACHE_VERSION = 1;
const JOB_HISTORY_CACHE_PREFIX = "fieldops:offline:job-history:v1";

interface CachedJobHistory {
  version: number;
  tenantId: string;
  technicianId: string;
  savedAt: string;
  jobs: TechnicianJob[];
}

function normalizeJobs(
  response: TechnicianJobCollection
): TechnicianJob[] {
  return Array.isArray(response) ? response : response.items;
}

function isTechnicianJob(value: unknown): value is TechnicianJob {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Record<string, unknown>;

  return (
    (typeof candidate.id === "string" || typeof candidate.id === "number") &&
    typeof candidate.status === "string"
  );
}

function isCachedJobHistory(
  value: unknown,
  tenantId: string,
  technicianId: string
): value is CachedJobHistory {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Record<string, unknown>;

  return (
    candidate.version === JOB_HISTORY_CACHE_VERSION &&
    candidate.tenantId === tenantId &&
    candidate.technicianId === technicianId &&
    typeof candidate.savedAt === "string" &&
    Number.isFinite(Date.parse(candidate.savedAt)) &&
    Array.isArray(candidate.jobs) &&
    candidate.jobs.every(isTechnicianJob)
  );
}

function getHistoryCacheKey(
  tenantId: string,
  technicianId: string
): string {
  return `${JOB_HISTORY_CACHE_PREFIX}:${encodeURIComponent(tenantId)}:${encodeURIComponent(technicianId)}`;
}

function formatCacheTime(value: string | null): string {
  if (!value) {
    return "Last saved locally";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Last saved locally";
  }

  return `Last saved ${date.toLocaleString()}`;
}

export default function JobHistoryScreen() {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);

  const [jobs, setJobs] = useState<TechnicianJob[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isShowingCachedData, setIsShowingCachedData] = useState(false);
  const [cachedAt, setCachedAt] = useState<string | null>(null);

  const tenantId =
    user?.tenant_id == null ? "" : String(user.tenant_id).trim();
  const technicianId = user?.id == null ? "" : String(user.id).trim();
  const hasCacheScope = tenantId.length > 0 && technicianId.length > 0;

  const loadHistory = useCallback(async (refresh = false) => {
    const cacheKey = hasCacheScope
      ? getHistoryCacheKey(tenantId, technicianId)
      : null;

    const cacheScope = hasCacheScope
      ? { tenantId, technicianId }
      : null;

    if (refresh) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
      setJobs([]);
      setIsShowingCachedData(false);
      setCachedAt(null);
    }

    setError(null);

    let cachedHistoryLoaded = false;

    try {
      if (!refresh && cacheKey && cacheScope) {
        try {
          let parsedValue = await getOfflineRecord<unknown>(
            cacheScope,
            "job-history",
            "history-list"
          );

          if (parsedValue === null) {
            const cachedValue = await AsyncStorage.getItem(cacheKey);

            if (cachedValue) {
              try {
                const legacyValue: unknown = JSON.parse(cachedValue);

                if (
                  isCachedJobHistory(
                    legacyValue,
                    tenantId,
                    technicianId
                  )
                ) {
                  await setOfflineRecord(
                    cacheScope,
                    "job-history",
                    "history-list",
                    legacyValue
                  );

                  parsedValue = legacyValue;
                }
              } finally {
                // Remove the legacy plaintext cache after migration is attempted.
                await AsyncStorage.removeItem(cacheKey);
              }
            }
          } else {
            // An encrypted copy exists, so remove its legacy plaintext copy.
            await AsyncStorage.removeItem(cacheKey);
          }

          if (
            isCachedJobHistory(
              parsedValue,
              tenantId,
              technicianId
            )
          ) {
            setJobs(parsedValue.jobs);
            setCachedAt(parsedValue.savedAt);
            setIsShowingCachedData(true);
            cachedHistoryLoaded = true;
            setIsLoading(false);
          } else if (parsedValue !== null) {
            await deleteOfflineRecord(
              cacheScope,
              "job-history",
              "history-list"
            );
          }
        } catch {
          // Cache failures must not prevent a request to the backend.
        }
      }

      if (!hasCacheScope) {
        throw new Error(
          "Your technician or organization identity is unavailable. Sign in again to load job history."
        );
      }

      const response = await getTechnicianJobHistory();
      const freshJobs = normalizeJobs(response);
      const savedAt = new Date().toISOString();

      setJobs(freshJobs);
      setCachedAt(savedAt);
      setIsShowingCachedData(false);
      setError(null);

      if (cacheKey && cacheScope) {
        const cacheEntry: CachedJobHistory = {
          version: JOB_HISTORY_CACHE_VERSION,
          tenantId,
          technicianId,
          savedAt,
          jobs: freshJobs
        };

        try {
          await setOfflineRecord(
            cacheScope,
            "job-history",
            "history-list",
            cacheEntry
          );
        } catch {
          // The server result remains usable if secure caching fails.
        } finally {
          try {
            await AsyncStorage.removeItem(cacheKey);
          } catch {
            // Legacy-cache cleanup must not block the server result.
          }
        }
      }
    } catch {
      setError(
        "Unable to refresh job history. Check your connection and try again."
      );

      if (!cachedHistoryLoaded) {
        setIsShowingCachedData((current) => current);
      }
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [hasCacheScope, tenantId, technicianId]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  if (isLoading && jobs.length === 0) {
    return <LoadingState label="Loading job history..." />;
  }

  if (error && jobs.length === 0 && !isShowingCachedData) {
    return (
      <ErrorState
        title="Job history unavailable"
        message={error}
        onRetry={() => void loadHistory(true)}
      />
    );
  }

  return (
    <View style={styles.screen}>
      <View style={styles.header}>
        <Text style={styles.title}>Job History</Text>
        <Text style={styles.subtitle}>
          Review your previous service jobs.
        </Text>
      </View>

      {isShowingCachedData ? (
        <View style={styles.offlineNotice}>
          <Text style={styles.offlineTitle}>
            Saved job history · May be outdated
          </Text>
          <Text style={styles.offlineText}>
            {formatCacheTime(cachedAt)}. Reconnect and refresh to check for updates.
          </Text>
        </View>
      ) : null}

      {error ? (
        <Pressable
          accessibilityRole="button"
          onPress={() => void loadHistory(true)}
          style={styles.warning}
        >
          <Text style={styles.warningText}>
            Refresh failed. Tap to retry.
          </Text>
        </Pressable>
      ) : null}

      <FlatList
        data={jobs}
        keyExtractor={(job) => String(job.id)}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={() => void loadHistory(true)}
          />
        }
        contentContainerStyle={
          jobs.length === 0 ? styles.emptyList : styles.list
        }
        ListEmptyComponent={
          <EmptyState
            title="No job history"
            message={
              isShowingCachedData
                ? "No jobs were present in the last saved history. Refresh when connected to check for updates."
                : "Your previous jobs will appear here."
            }
            onRetry={() => void loadHistory(true)}
          />
        }
        renderItem={({ item }) => (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`View job ${item.job_number ?? item.id}`}
            onPress={() =>
              router.push({
                pathname: "/(app)/jobs/[jobId]",
                params: { jobId: String(item.id) }
              })
            }
            style={({ pressed }) => [
              styles.card,
              pressed && styles.cardPressed
            ]}
          >
            <Text style={styles.jobNumber}>
              Job #{item.job_number ?? String(item.id)}
            </Text>

            <Text style={styles.jobTitle}>
              {item.title || "Service job"}
            </Text>

            <View style={styles.statusBadge}>
              <Text style={styles.statusText}>
                {item.status.replace(/_/g, " ")}
              </Text>
            </View>

            {item.customer_name ? (
              <Text style={styles.detail}>
                Customer: {item.customer_name}
              </Text>
            ) : null}

            {item.scheduled_at ? (
              <Text style={styles.detail}>
                Scheduled: {new Date(item.scheduled_at).toLocaleString()}
              </Text>
            ) : null}

            <Text style={styles.openHint}>View details →</Text>
          </Pressable>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#F8FAFC",
    paddingTop: 28
  },
  header: {
    paddingHorizontal: 20,
    paddingBottom: 20
  },
  title: {
    color: "#0F172A",
    fontSize: 28,
    fontWeight: "800"
  },
  subtitle: {
    color: "#64748B",
    fontSize: 14,
    lineHeight: 21,
    marginTop: 6
  },
  list: {
    paddingHorizontal: 16,
    paddingBottom: 28
  },
  emptyList: {
    flexGrow: 1,
    paddingHorizontal: 16,
    paddingBottom: 28
  },
  card: {
    backgroundColor: "#FFFFFF",
    borderColor: "#E2E8F0",
    borderWidth: 1,
    borderRadius: 12,
    padding: 16,
    marginBottom: 12
  },
  cardPressed: {
    backgroundColor: "#EFF6FF",
    borderColor: "#93C5FD"
  },
  jobNumber: {
    color: "#1D4ED8",
    fontSize: 13,
    fontWeight: "700"
  },
  jobTitle: {
    color: "#0F172A",
    fontSize: 17,
    fontWeight: "700",
    marginTop: 10,
    marginBottom: 12
  },
  statusBadge: {
    alignSelf: "flex-start",
    backgroundColor: "#DBEAFE",
    borderRadius: 6,
    paddingHorizontal: 9,
    paddingVertical: 5,
    marginBottom: 6
  },
  statusText: {
    color: "#1E40AF",
    fontSize: 11,
    fontWeight: "700",
    textTransform: "capitalize"
  },
  detail: {
    color: "#475569",
    fontSize: 13,
    lineHeight: 20,
    marginTop: 7
  },
  openHint: {
    color: "#2563EB",
    fontSize: 13,
    fontWeight: "600",
    marginTop: 12
  },
  offlineNotice: {
    backgroundColor: "#FFF7DB",
    borderColor: "#F1D48A",
    borderWidth: 1,
    padding: 12,
    marginHorizontal: 16,
    marginBottom: 12,
    borderRadius: 10
  },
  offlineTitle: {
    color: "#854D0E",
    fontSize: 13,
    fontWeight: "800"
  },
  offlineText: {
    color: "#854D0E",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 4
  },
  warning: {
    backgroundColor: "#FEF3C7",
    padding: 12,
    marginHorizontal: 16,
    marginBottom: 12,
    borderRadius: 8
  },
  warningText: {
    color: "#92400E",
    fontSize: 13
  }
});
