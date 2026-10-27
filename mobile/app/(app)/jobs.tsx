import { useCallback, useMemo, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  deleteOfflineRecord,
  getOfflineRecord,
  setOfflineRecord,
  type OfflineScope
} from "../../src/offline/offlineStore";
import {
  FlatList,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import {
  getTechnicianJobs,
  type TechnicianJob,
  type TechnicianJobCollection
} from "../../src/api/technician";
import { isNetworkUnavailableError } from "../../src/api/client";
import { useAuthStore } from "../../src/auth/authStore";
import {
  EmptyState,
  ErrorState,
  LoadingState
} from "../../src/components/ScreenState";

type JobFilter = "ALL" | "EN_ROUTE" | "IN_PROGRESS" | "COMPLETED";

function normalizeJobs(
  data: TechnicianJobCollection
): TechnicianJob[] {
  return Array.isArray(data) ? data : data.items;
}

interface CachedTechnicianJobs {
  jobs: TechnicianJob[];
  cachedAt: string;
}

function getJobsCacheScope(user: unknown): OfflineScope | null {
  if (typeof user !== "object" || user === null) {
    return null;
  }

  const record = user as Record<string, unknown>;

  const tenantId =
    record.tenant_id ??
    record.tenantId ??
    record.organization_id ??
    record.organizationId ??
    record.org_id;

  const technicianId =
    record.technician_id ??
    record.technicianId ??
    record.user_id ??
    record.userId ??
    record.id;

  if (
    tenantId === undefined ||
    tenantId === null ||
    technicianId === undefined ||
    technicianId === null ||
    !String(tenantId).trim() ||
    !String(technicianId).trim()
  ) {
    return null;
  }

  return {
    tenantId: String(tenantId).trim(),
    technicianId: String(technicianId).trim()
  };
}

function getLegacyJobsCacheKey(scope: OfflineScope): string {
  return [
    "fieldops:technician-jobs:v1",
    encodeURIComponent(scope.tenantId),
    encodeURIComponent(scope.technicianId)
  ].join(":");
}

function isCachedTechnicianJobs(
  value: unknown
): value is CachedTechnicianJobs {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const record = value as Record<string, unknown>;

  return (
    Array.isArray(record.jobs) &&
    typeof record.cachedAt === "string"
  );
}

async function readCachedJobs(
  scope: OfflineScope
): Promise<CachedTechnicianJobs | null> {
  const legacyCacheKey = getLegacyJobsCacheKey(scope);

  try {
    const encryptedValue = await getOfflineRecord<unknown>(
      scope,
      "jobs",
      "assigned-list"
    );

    if (encryptedValue !== null) {
      if (isCachedTechnicianJobs(encryptedValue)) {
        await AsyncStorage.removeItem(legacyCacheKey).catch(
          () => undefined
        );

        return encryptedValue;
      }

      await deleteOfflineRecord(
        scope,
        "jobs",
        "assigned-list"
      );
    }

    // Migrate a legacy cache only after encrypted storage is accessible.
    const legacyValue = await AsyncStorage.getItem(legacyCacheKey);

    if (!legacyValue) {
      return null;
    }

    let parsedValue: unknown;

    try {
      parsedValue = JSON.parse(legacyValue);
    } catch {
      await AsyncStorage.removeItem(legacyCacheKey);
      return null;
    }

    if (!isCachedTechnicianJobs(parsedValue)) {
      await AsyncStorage.removeItem(legacyCacheKey);
      return null;
    }

    await setOfflineRecord(
      scope,
      "jobs",
      "assigned-list",
      parsedValue
    );

    // Delete the old copy only after migration succeeds.
    await AsyncStorage.removeItem(legacyCacheKey).catch(
      () => undefined
    );

    return parsedValue;
  } catch {
    // Never use plaintext cache as a fallback if encrypted storage fails.
    return null;
  }
}

async function saveCachedJobs(
  scope: OfflineScope,
  jobs: TechnicianJob[]
): Promise<void> {
  try {
    const cachedValue: CachedTechnicianJobs = {
      jobs,
      cachedAt: new Date().toISOString()
    };

    await setOfflineRecord(
      scope,
      "jobs",
      "assigned-list",
      cachedValue
    );
  } catch {
    // Job loading should continue if secure local caching is unavailable.
  }
}


function normalizeStatus(status: string): string {
  return status
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toUpperCase();
}

function getStatusGroup(status: string): JobFilter | "OTHER" {
  const normalized = normalizeStatus(status);

  if (normalized === "EN ROUTE" || normalized === "ENROUTE") {
    return "EN_ROUTE";
  }

  if (normalized === "IN PROGRESS") {
    return "IN_PROGRESS";
  }

  if (
    normalized === "COMPLETED" ||
    normalized === "COMPLETE"
  ) {
    return "COMPLETED";
  }

  return "OTHER";
}

function formatStatus(status: string): string {
  return normalizeStatus(status) || "UNKNOWN";
}

function formatSchedule(value?: string): string {
  if (!value?.trim()) {
    return "Not scheduled";
  }

  const trimmedValue = value.trim();
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(trimmedValue);

  if (dateOnly) {
    const year = Number(dateOnly[1]);
    const month = Number(dateOnly[2]);
    const day = Number(dateOnly[3]);
    const date = new Date(year, month - 1, day);

    if (
      date.getFullYear() !== year ||
      date.getMonth() !== month - 1 ||
      date.getDate() !== day
    ) {
      return trimmedValue;
    }

    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric"
    });
  }

  const date = new Date(trimmedValue);

  if (Number.isNaN(date.getTime())) {
    return trimmedValue;
  }

  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric"
  });
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Unable to load jobs. Please try again.";
}

export default function JobsScreen() {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const cacheScope = useMemo(() => getJobsCacheScope(user), [user]);

  const [jobs, setJobs] = useState<TechnicianJob[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offlineMessage, setOfflineMessage] = useState<string | null>(null);
  const [dataSource, setDataSource] = useState<"server" | "cache" | null>(
    null
  );
  const [activeFilter, setActiveFilter] = useState<JobFilter>("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  const loadJobs = useCallback(async (refresh = false) => {
    if (refresh) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }

    setError(null);

    let hasCachedJobs = false;

    if (cacheScope) {
      const cachedJobs = await readCachedJobs(cacheScope);

      if (cachedJobs) {
        hasCachedJobs = true;
        setJobs(cachedJobs.jobs);
        setDataSource("cache");
        setOfflineMessage(
          "Showing saved jobs while checking for updates. These details may be outdated."
        );
        setIsLoading(false);
      }
    }

    try {
      const response = await getTechnicianJobs();
      const serverJobs = normalizeJobs(response);

      setJobs(serverJobs);
      setDataSource("server");
      setOfflineMessage(null);
      setError(null);

      if (cacheScope) {
        await saveCachedJobs(cacheScope, serverJobs);
      }
    } catch (loadError: unknown) {
      const message = getErrorMessage(loadError);

      setError(message);

      if (hasCachedJobs) {
        setDataSource("cache");
        setOfflineMessage(
          isNetworkUnavailableError(loadError)
            ? "Offline — showing saved jobs. These details may be outdated."
            : "Couldn't refresh jobs. Showing saved jobs, which may be outdated."
        );
      } else if (isNetworkUnavailableError(loadError)) {
        setOfflineMessage(
          "You're offline and no saved job list is available yet."
        );
      } else {
        setOfflineMessage(null);
      }
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [cacheScope]);

  useFocusEffect(
    useCallback(() => {
      void loadJobs();
    }, [loadJobs])
  );

  const counts = useMemo(() => {
    return {
      ALL: jobs.length,
      EN_ROUTE: jobs.filter(
        (job) => getStatusGroup(job.status) === "EN_ROUTE"
      ).length,
      IN_PROGRESS: jobs.filter(
        (job) => getStatusGroup(job.status) === "IN_PROGRESS"
      ).length,
      COMPLETED: jobs.filter(
        (job) => getStatusGroup(job.status) === "COMPLETED"
      ).length
    };
  }, [jobs]);

  const visibleJobs = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();

    return jobs.filter((job) => {
      const matchesFilter =
        activeFilter === "ALL" ||
        getStatusGroup(job.status) === activeFilter;

      const searchableText = [
        job.job_number,
        job.id,
        job.title,
        job.customer_name,
        job.address,
        job.priority,
        job.status
      ]
        .filter((value) => value !== undefined && value !== null)
        .join(" ")
        .toLowerCase();

      return matchesFilter && (!query || searchableText.includes(query));
    });
  }, [jobs, activeFilter, searchQuery]);

  if (isLoading) {
    return <LoadingState label="Loading your jobs..." />;
  }

  if (error && jobs.length === 0) {
    return (
      <ErrorState
        title="Couldn't load jobs"
        message={offlineMessage ?? error}
        onRetry={() => void loadJobs()}
      />
    );
  }

  const filters: {
    key: JobFilter;
    label: string;
    icon: string;
  }[] = [
    { key: "ALL", label: "All Jobs", icon: "▤" },
    { key: "EN_ROUTE", label: "En Route", icon: "➜" },
    { key: "IN_PROGRESS", label: "In Progress", icon: "◷" },
    { key: "COMPLETED", label: "Completed", icon: "✓" }
  ];

  return (
    <View style={styles.screen}>
      <FlatList
        data={visibleJobs}
        keyExtractor={(job) => String(job.id)}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={() => void loadJobs(true)}
            tintColor="#087653"
            colors={["#087653"]}
          />
        }
        contentContainerStyle={
          visibleJobs.length === 0 ? styles.emptyList : styles.list
        }
        ListHeaderComponent={
          <View>
            <View style={styles.header}>
              <View style={styles.brandRow}>
                <View style={styles.brandMark}>
                  <Text style={styles.brandMarkText}>FC</Text>
                </View>

                <View style={styles.brandTextGroup}>
                  <Text style={styles.brandName}>
                    <Text style={styles.brandField}>Field</Text>
                    <Text style={styles.brandOps}>Ops</Text>
                  </Text>

                  <Text style={styles.brandSubtitle}>
                    C O M M A N D E R
                  </Text>
                </View>
              </View>

              <Text style={styles.pageTitle}>My Jobs</Text>

              <Text style={styles.pageSubtitle}>
                Jobs assigned to your technician account
              </Text>

              <View style={styles.headerAccent} />
            </View>

            {dataSource === "cache" ? (
              <Pressable
                accessibilityRole="button"
                onPress={() => void loadJobs(true)}
                style={styles.warning}
              >
                <Text style={styles.warningText}>
                  {offlineMessage ??
                    "Showing saved jobs. These details may be outdated."} Tap to refresh.
                </Text>
              </Pressable>
            ) : dataSource === "server" ? (
              <View style={styles.serverNotice}>
                <Text style={styles.serverNoticeText}>
                  ✓ Jobs refreshed from server
                </Text>
              </View>
            ) : error && jobs.length > 0 ? (
              <Pressable
                accessibilityRole="button"
                onPress={() => void loadJobs(true)}
                style={styles.warning}
              >
                <Text style={styles.warningText}>
                  Refresh failed. Tap to try again.
                </Text>
              </Pressable>
            ) : null}

            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              style={styles.filterScroll}
              contentContainerStyle={styles.filterContainer}
            >
              {filters.map((filter) => {
                const selected = activeFilter === filter.key;

                return (
                  <Pressable
                    key={filter.key}
                    accessibilityRole="button"
                    accessibilityState={{ selected }}
                    onPress={() => setActiveFilter(filter.key)}
                    style={[
                      styles.filterChip,
                      selected && styles.filterChipActive
                    ]}
                  >
                    <Text
                      style={[
                        styles.filterIcon,
                        selected && styles.filterTextActive
                      ]}
                    >
                      {filter.icon}
                    </Text>

                    <Text
                      style={[
                        styles.filterLabel,
                        selected && styles.filterTextActive
                      ]}
                      numberOfLines={1}
                    >
                      {filter.label}
                    </Text>

                    <View
                      style={[
                        styles.countBadge,
                        selected && styles.countBadgeActive
                      ]}
                    >
                      <Text
                        style={[
                          styles.countText,
                          selected && styles.countTextActive
                        ]}
                      >
                        {counts[filter.key]}
                      </Text>
                    </View>
                  </Pressable>
                );
              })}
            </ScrollView>

            <View style={styles.searchRow}>
              <View style={styles.searchBox}>
                <Text style={styles.searchIcon}>⌕</Text>

                <TextInput
                  accessibilityLabel="Search jobs"
                  value={searchQuery}
                  onChangeText={setSearchQuery}
                  placeholder="Search jobs by ID, customer or location..."
                  placeholderTextColor="#829096"
                  style={styles.searchInput}
                  returnKeyType="search"
                  autoCapitalize="none"
                  clearButtonMode="while-editing"
                />
              </View>
            </View>

            <View style={styles.sectionHeading}>
              <Text style={styles.sectionTitle}>
                {activeFilter === "ALL"
                  ? "Your assigned jobs"
                  : filters.find((filter) => filter.key === activeFilter)
                      ?.label}
              </Text>

              <Text style={styles.sectionCount}>
                {visibleJobs.length}{" "}
                {visibleJobs.length === 1 ? "job" : "jobs"}
              </Text>
            </View>
          </View>
        }
        ListEmptyComponent={
          jobs.length === 0 ? (
            <EmptyState
              title="No jobs assigned"
              message="Newly assigned jobs will appear here."
              onRetry={() => void loadJobs(true)}
            />
          ) : (
            <View style={styles.noResults}>
              <View style={styles.noResultsIcon}>
                <Text style={styles.noResultsIconText}>⌕</Text>
              </View>

              <Text style={styles.noResultsTitle}>
                No matching jobs
              </Text>

              <Text style={styles.noResultsMessage}>
                Try another search or select a different status.
              </Text>

              <Pressable
                accessibilityRole="button"
                onPress={() => {
                  setSearchQuery("");
                  setActiveFilter("ALL");
                }}
                style={styles.clearButton}
              >
                <Text style={styles.clearButtonText}>
                  Clear search and filters
                </Text>
              </Pressable>
            </View>
          )
        }
        renderItem={({ item }) => {
          const isUrgent =
            item.priority?.toUpperCase() === "URGENT";

          return (
            <View
              style={[
                styles.jobCard,
                isUrgent && styles.urgentCard
              ]}
            >
              <View style={styles.cardTopRow}>
                <View style={styles.jobIdentity}>
                  <View
                    style={[
                      styles.serviceIconBox,
                      isUrgent && styles.urgentIconBox
                    ]}
                  >
                    <Text
                      style={[
                        styles.serviceIcon,
                        isUrgent && styles.urgentServiceIcon
                      ]}
                    >
                      ⚒
                    </Text>
                  </View>

                  <View style={styles.jobNumberGroup}>
                    <Text style={styles.jobNumber}>
                      Job #{item.job_number ?? String(item.id)}
                    </Text>

                    <Text style={styles.jobReference}>
                      Service assignment
                    </Text>
                  </View>
                </View>

                <View style={styles.statusBadge}>
                  <Text style={styles.statusArrow}>➜</Text>
                  <Text style={styles.statusText}>
                    {formatStatus(item.status)}
                  </Text>
                </View>
              </View>

              <Text style={styles.jobTitle}>
                {item.title || "Service job"}
              </Text>

              {item.priority ? (
                <View
                  style={[
                    styles.priorityBadge,
                    isUrgent
                      ? styles.priorityBadgeUrgent
                      : styles.priorityBadgeNormal
                  ]}
                >
                  <View
                    style={[
                      styles.prioritySymbol,
                      isUrgent
                        ? styles.prioritySymbolUrgent
                        : styles.prioritySymbolNormal
                    ]}
                  >
                    <Text
                      style={[
                        styles.prioritySymbolText,
                        isUrgent
                          ? styles.prioritySymbolTextUrgent
                          : styles.prioritySymbolTextNormal
                      ]}
                    >
                      !
                    </Text>
                  </View>

                  <View>
                    <Text
                      style={[
                        styles.priorityLabel,
                        isUrgent && styles.urgentText
                      ]}
                    >
                      Priority
                    </Text>

                    <Text
                      style={[
                        styles.priorityValue,
                        isUrgent && styles.urgentText
                      ]}
                    >
                      {item.priority.toUpperCase()}
                    </Text>
                  </View>
                </View>
              ) : null}

              {item.customer_name ? (
                <View style={styles.detailRow}>
                  <View style={styles.detailIconCircle}>
                    <Text style={styles.detailIcon}>♙</Text>
                  </View>

                  <View style={styles.detailContent}>
                    <Text style={styles.detailLabel}>Customer</Text>

                    <Text style={styles.detailValue}>
                      {item.customer_name}
                    </Text>
                  </View>
                </View>
              ) : null}

              {item.address ? (
                <View style={styles.detailRow}>
                  <View style={styles.detailIconCircle}>
                    <Text style={styles.detailIcon}>⌖</Text>
                  </View>

                  <View style={styles.detailContent}>
                    <Text style={styles.detailLabel}>Location</Text>

                    <Text style={styles.locationValue}>
                      {item.address}
                    </Text>
                  </View>
                </View>
              ) : null}

              <View style={styles.scheduleRow}>
                <View style={styles.scheduleIconCircle}>
                  <Text style={styles.scheduleIcon}>▦</Text>
                </View>

                <View style={styles.scheduleContent}>
                  <Text style={styles.detailLabel}>
                    Scheduled Date
                  </Text>

                  <Text style={styles.detailValue}>
                    {formatSchedule(item.scheduled_at)}
                  </Text>
                </View>
              </View>

              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`View details for job ${item.job_number ?? item.id}`}
                onPress={() =>
                  router.push({
                    pathname: "/(app)/jobs/[jobId]",
                    params: { jobId: String(item.id) }
                  })
                }
                style={({ pressed }) => [
                  styles.detailsButton,
                  pressed && styles.detailsButtonPressed
                ]}
              >
                <Text style={styles.detailsButtonText}>
                  View Job Details
                </Text>

                <Text style={styles.detailsButtonArrow}>→</Text>
              </Pressable>
            </View>
          );
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#F3F8F6"
  },

  header: {
    backgroundColor: "#00513D",
    paddingHorizontal: 22,
    paddingTop: 24,
    paddingBottom: 28,
    overflow: "hidden"
  },
  brandRow: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 25
  },
  brandMark: {
    width: 48,
    height: 46,
    borderRadius: 12,
    backgroundColor: "#E8F5EE",
    justifyContent: "center",
    alignItems: "center",
    transform: [{ skewX: "-8deg" }]
  },
  brandMarkText: {
    color: "#006747",
    fontSize: 21,
    fontWeight: "900",
    letterSpacing: -2
  },
  brandTextGroup: {
    marginLeft: 10
  },
  brandName: {
    fontSize: 23,
    fontWeight: "700",
    letterSpacing: -0.7
  },
  brandField: {
    color: "#FFFFFF"
  },
  brandOps: {
    color: "#79D7A8"
  },
  brandSubtitle: {
    color: "#D7E8E1",
    fontSize: 9,
    marginTop: 1,
    letterSpacing: 1.5
  },
  pageTitle: {
    color: "#FFFFFF",
    fontSize: 35,
    lineHeight: 42,
    fontWeight: "800",
    letterSpacing: -0.7
  },
  pageSubtitle: {
    color: "#D7E8E1",
    fontSize: 14,
    lineHeight: 21,
    marginTop: 7
  },
  headerAccent: {
    position: "absolute",
    width: 180,
    height: 180,
    right: -95,
    top: 115,
    borderRadius: 90,
    borderWidth: 26,
    borderColor: "rgba(120, 213, 169, 0.08)"
  },

  filterScroll: {
    flexGrow: 0,
    marginTop: 17
  },
  filterContainer: {
    paddingHorizontal: 14,
    paddingBottom: 4,
    gap: 8
  },
  filterChip: {
    minHeight: 48,
    paddingHorizontal: 12,
    borderRadius: 15,
    borderWidth: 1,
    borderColor: "#E0E9E6",
    backgroundColor: "#FFFFFF",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6
  },
  filterChipActive: {
    backgroundColor: "#006747",
    borderColor: "#006747"
  },
  filterIcon: {
    color: "#536779",
    fontSize: 17,
    fontWeight: "700"
  },
  filterLabel: {
    color: "#526174",
    fontSize: 12,
    fontWeight: "700"
  },
  filterTextActive: {
    color: "#FFFFFF"
  },
  countBadge: {
    minWidth: 23,
    height: 23,
    paddingHorizontal: 5,
    borderRadius: 12,
    backgroundColor: "#EDF1F3",
    alignItems: "center",
    justifyContent: "center"
  },
  countBadgeActive: {
    backgroundColor: "rgba(255,255,255,0.22)"
  },
  countText: {
    color: "#64748B",
    fontSize: 11,
    fontWeight: "700"
  },
  countTextActive: {
    color: "#FFFFFF"
  },

  searchRow: {
    paddingHorizontal: 16,
    marginTop: 12
  },
  searchBox: {
    minHeight: 54,
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#E4ECE9",
    borderRadius: 16,
    paddingHorizontal: 13
  },
  searchIcon: {
    color: "#536779",
    fontSize: 30,
    lineHeight: 34,
    marginRight: 10
  },
  searchInput: {
    flex: 1,
    minWidth: 0,
    color: "#132D40",
    fontSize: 13,
    paddingVertical: 12
  },

  sectionHeading: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 20,
    marginTop: 22,
    marginBottom: 11
  },
  sectionTitle: {
    color: "#173348",
    fontSize: 15,
    fontWeight: "800"
  },
  sectionCount: {
    color: "#64748B",
    fontSize: 12,
    fontWeight: "600"
  },

  list: {
    paddingHorizontal: 14,
    paddingBottom: 24
  },
  emptyList: {
    flexGrow: 1,
    paddingHorizontal: 16,
    paddingBottom: 24
  },

  jobCard: {
    backgroundColor: "#FFFFFF",
    borderRadius: 22,
    borderWidth: 1,
    borderColor: "#E5EEEA",
    padding: 16,
    marginBottom: 15,
    shadowColor: "#164E3B",
    shadowOffset: { width: 0, height: 5 },
    shadowOpacity: 0.07,
    shadowRadius: 12,
    elevation: 3
  },
  urgentCard: {
    borderLeftWidth: 4,
    borderLeftColor: "#F04455"
  },
  cardTopRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    flexWrap: "wrap",
    gap: 10
  },
  jobIdentity: {
    flex: 1,
    minWidth: 120,
    flexDirection: "row",
    alignItems: "center",
    gap: 11
  },
  serviceIconBox: {
    width: 55,
    height: 55,
    borderRadius: 17,
    backgroundColor: "#DDF4E9",
    justifyContent: "center",
    alignItems: "center"
  },
  urgentIconBox: {
    backgroundColor: "#FFE8EB"
  },
  serviceIcon: {
    color: "#087653",
    fontSize: 29,
    fontWeight: "700"
  },
  urgentServiceIcon: {
    color: "#EF394B"
  },
  jobNumberGroup: {
    flexShrink: 1
  },
  jobNumber: {
    color: "#087653",
    fontSize: 19,
    fontWeight: "800"
  },
  jobReference: {
    color: "#718096",
    fontSize: 11,
    marginTop: 4
  },
  statusBadge: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 5,
    backgroundColor: "#E1EEFF",
    paddingHorizontal: 11,
    paddingVertical: 10,
    borderRadius: 22,
    maxWidth: "100%"
  },
  statusArrow: {
    color: "#1261C2",
    fontSize: 16,
    fontWeight: "800"
  },
  statusText: {
    color: "#1256AE",
    fontSize: 11,
    fontWeight: "800"
  },
  jobTitle: {
    color: "#122D43",
    fontSize: 24,
    lineHeight: 31,
    fontWeight: "800",
    marginTop: 15,
    marginBottom: 14
  },

  priorityBadge: {
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
    borderRadius: 15,
    paddingHorizontal: 11,
    paddingVertical: 8,
    marginBottom: 13
  },
  priorityBadgeUrgent: {
    backgroundColor: "#FFE9EB"
  },
  priorityBadgeNormal: {
    backgroundColor: "#E9F5EF"
  },
  prioritySymbol: {
    width: 29,
    height: 29,
    borderRadius: 15,
    justifyContent: "center",
    alignItems: "center",
    borderWidth: 2
  },
  prioritySymbolUrgent: {
    borderColor: "#CF2525"
  },
  prioritySymbolNormal: {
    borderColor: "#087653"
  },
  prioritySymbolText: {
    fontSize: 19,
    fontWeight: "900",
    lineHeight: 22
  },
  prioritySymbolTextUrgent: {
    color: "#CF2525"
  },
  prioritySymbolTextNormal: {
    color: "#087653"
  },
  priorityLabel: {
    color: "#718096",
    fontSize: 11
  },
  priorityValue: {
    color: "#087653",
    fontSize: 13,
    fontWeight: "900",
    marginTop: 1
  },
  urgentText: {
    color: "#BF2222"
  },

  detailRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 11,
    marginTop: 13
  },
  detailIconCircle: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: "#EAF5F0",
    alignItems: "center",
    justifyContent: "center"
  },
  detailIcon: {
    color: "#526477",
    fontSize: 24,
    fontWeight: "500"
  },
  detailContent: {
    flex: 1,
    paddingTop: 2
  },
  detailLabel: {
    color: "#718096",
    fontSize: 12,
    lineHeight: 18,
    marginBottom: 3
  },
  detailValue: {
    color: "#183149",
    fontSize: 14,
    lineHeight: 21,
    fontWeight: "500"
  },
  locationValue: {
    color: "#183149",
    fontSize: 13,
    lineHeight: 20,
    fontWeight: "500"
  },

  scheduleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 11,
    marginTop: 17,
    marginBottom: 18
  },
  scheduleIconCircle: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: "#EAF5F0",
    alignItems: "center",
    justifyContent: "center"
  },
  scheduleIcon: {
    color: "#087653",
    fontSize: 23,
    fontWeight: "700"
  },
  scheduleContent: {
    flex: 1
  },

  detailsButton: {
    minHeight: 58,
    borderRadius: 16,
    backgroundColor: "#006747",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 16,
    gap: 13
  },
  detailsButtonPressed: {
    backgroundColor: "#004D39",
    transform: [{ scale: 0.99 }]
  },
  detailsButtonText: {
    color: "#FFFFFF",
    fontSize: 15,
    fontWeight: "800"
  },
  detailsButtonArrow: {
    color: "#FFFFFF",
    fontSize: 25,
    lineHeight: 28,
    fontWeight: "500"
  },

  noResults: {
    alignItems: "center",
    paddingHorizontal: 24,
    paddingVertical: 38,
    backgroundColor: "#FFFFFF",
    borderRadius: 20,
    borderWidth: 1,
    borderColor: "#E5EEEA"
  },
  noResultsIcon: {
    width: 54,
    height: 54,
    borderRadius: 27,
    backgroundColor: "#EAF5F0",
    alignItems: "center",
    justifyContent: "center"
  },
  noResultsIconText: {
    color: "#087653",
    fontSize: 32
  },
  noResultsTitle: {
    color: "#173348",
    fontSize: 17,
    fontWeight: "800",
    marginTop: 15
  },
  noResultsMessage: {
    color: "#718096",
    fontSize: 13,
    lineHeight: 20,
    textAlign: "center",
    marginTop: 7
  },
  clearButton: {
    marginTop: 17,
    paddingHorizontal: 17,
    paddingVertical: 11,
    borderRadius: 12,
    backgroundColor: "#E5F3EC"
  },
  clearButtonText: {
    color: "#006747",
    fontSize: 13,
    fontWeight: "800"
  },

  warning: {
    backgroundColor: "#FFF4D7",
    padding: 12,
    marginHorizontal: 16,
    marginTop: 10,
    borderRadius: 10
  },
  warningText: {
    color: "#92400E",
    fontSize: 13
  },
  serverNotice: {
    backgroundColor: "#E5F3EC",
    padding: 10,
    marginHorizontal: 16,
    marginTop: 10,
    borderRadius: 10
  },
  serverNoticeText: {
    color: "#006747",
    fontSize: 12,
    fontWeight: "700"
  }
});