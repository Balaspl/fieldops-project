import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  deleteOfflineRecord,
  getOfflineRecord,
  setOfflineRecord,
  type OfflineScope
} from "../../src/offline/offlineStore";
import { FlatList, Image, Modal, Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View, type ImageSourcePropType } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { LinearGradient } from "expo-linear-gradient";
import {
  getTechnicianJobs,
  getTechnicianJobHistory,
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

function normalizeJobs(
  data: TechnicianJobCollection
): TechnicianJob[] {
  return Array.isArray(data) ? data : data.items;
}

interface CachedTechnicianJobs {
  jobs: TechnicianJob[];
  cachedAt: string;
}

type JobStatusFilter = "ALL" | "ASSIGNED" | "ACCEPTED" | "STARTED" | "EN_ROUTE" | "IN_PROGRESS" | "COMPLETED";
type JobDateFilter = "ANY" | "TODAY" | "THIS_WEEK" | "THIS_MONTH" | "OVERDUE";

const jobStatusFilters: { label: string; value: JobStatusFilter }[] = [
  { label: "All statuses", value: "ALL" },
  { label: "Assigned", value: "ASSIGNED" },
  { label: "Accepted", value: "ACCEPTED" },
  { label: "Started", value: "STARTED" },
  { label: "En Route", value: "EN_ROUTE" },
  { label: "In Progress", value: "IN_PROGRESS" },
  { label: "Completed", value: "COMPLETED" }
];

const jobDateFilters: { label: string; value: JobDateFilter }[] = [
  { label: "Any date", value: "ANY" },
  { label: "Today", value: "TODAY" },
  { label: "This week", value: "THIS_WEEK" },
  { label: "This month", value: "THIS_MONTH" },
  { label: "Past due", value: "OVERDUE" }
];

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
      // Avoid storing photo data in secure offline list storage.
      jobs: jobs.map((job) => ({ ...job, images: [] })),
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

function isActiveAssignment(job: TechnicianJob): boolean {
  const status = normalizeStatus(job.status).replace(/[ -]+/g, "_");
  return ![
    "COMPLETED",
    "CLOSED",
    "CANCELLED",
    "CANCELED",
    "REJECTED",
    "REJECTED_BY_TECHNICIAN"
  ].includes(status);
}

function formatSchedule(date?: string | null, time?: string | null): string {
  return [date, time].filter(Boolean).join(" ") || "N/A";
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Unable to load jobs. Please try again.";
}

function getAcceptanceSeconds(job: TechnicianJob, now: number): number | null {
  const status = normalizeStatus(job.status).replace(/ /g, "_");
  if (!["ASSIGNED", "ACTIVE", "PENDING", "AWAITING_ACCEPTANCE"].includes(status)) return null;
  const explicitDeadline = job.acceptance_expires_at;
  const explicitTimestamp = typeof explicitDeadline === "string" ? Date.parse(explicitDeadline) : Number.NaN;
  const deadline = Number.isFinite(explicitTimestamp)
    ? explicitTimestamp
    : job.assigned_at
      ? Date.parse(job.assigned_at) + 5 * 60 * 1000
      : Number.NaN;
  return Number.isFinite(deadline) ? Math.max(0, Math.floor((deadline - now) / 1000)) : null;
}

function formatAcceptanceTime(seconds: number): string {
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function getJobStatusFilter(job: TechnicianJob): JobStatusFilter | "OTHER" {
  const status = normalizeStatus(job.status).replace(/[ -]+/g, "_");
  if (["ASSIGNED", "PENDING", "AWAITING_ACCEPTANCE", "ACTIVE"].includes(status)) return "ASSIGNED";
  if (["ACCEPTED", "ACCEPTED_BY_TECHNICIAN"].includes(status)) return "ACCEPTED";
  if (["COMPLETED", "COMPLETE", "CLOSED"].includes(status)) return "COMPLETED";
  if (["EN_ROUTE", "ENROUTE"].includes(status)) return "EN_ROUTE";
  if (["STARTED", "WORK_STARTED"].includes(status)) return "STARTED";
  if (["ON_SITE", "ONSITE", "IN_PROGRESS", "PAUSED"].includes(status)) return "IN_PROGRESS";
  if (job.work_started_at) return "STARTED";
  return "OTHER";
}

function getScheduledDay(job: TechnicianJob): Date | null {
  const value = job.preferred_service_date?.trim() || job.scheduled_at?.trim();
  if (!value) return null;
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const date = dateOnly
    ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]))
    : new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  date.setHours(0, 0, 0, 0);
  return date;
}

function matchesDateFilter(job: TechnicianJob, filter: JobDateFilter, now: Date): boolean {
  if (filter === "ANY") return true;
  const scheduled = getScheduledDay(job);
  if (!scheduled) return false;
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  if (filter === "TODAY") return scheduled.getTime() === today.getTime();
  if (filter === "OVERDUE") return scheduled < today;
  if (filter === "THIS_MONTH") return scheduled.getFullYear() === today.getFullYear() && scheduled.getMonth() === today.getMonth();
  const weekStart = new Date(today);
  weekStart.setDate(today.getDate() - ((today.getDay() + 6) % 7));
  const nextWeek = new Date(weekStart);
  nextWeek.setDate(weekStart.getDate() + 7);
  return scheduled >= weekStart && scheduled < nextWeek;
}

const jobCategoryImages: Record<string, ImageSourcePropType> = {
  electrical: require("../../assets/images/job-service-electrical.png"),
  plumbing: require("../../assets/images/job-service-plumbing.png"),
  hvac: require("../../assets/images/job-service-hvac.png"),
  network: require("../../assets/images/job-service-network.png"),
  appliance: require("../../assets/images/job-service-appliances.png"),
  carpentry: require("../../assets/images/job-service-carpentry.png"),
  cleaning: require("../../assets/images/job-service-cleaning.png"),
  security: require("../../assets/images/job-service-security.png"),
  maintenance: require("../../assets/images/job-service-maintenance.png"),
  default: require("../../assets/images/jobs-toolbox.png")
};

function getJobThumbnailSource(job: TechnicianJob): ImageSourcePropType {
  const firstPhoto = Array.isArray(job.images)
    ? job.images.find((image) => typeof image === "string" && image.trim())
    : undefined;
  if (typeof firstPhoto === "string" && (/^data:image\//i.test(firstPhoto) || /^https?:\/\//i.test(firstPhoto))) {
    return { uri: firstPhoto };
  }

  const category = `${job.service_type ?? ""} ${job.title ?? ""} ${job.required_skill ?? ""}`.toLowerCase();
  const categoryKey = Object.keys(jobCategoryImages).find((key) => key !== "default" && category.includes(key));
  return (categoryKey ? jobCategoryImages[categoryKey] : undefined) ?? jobCategoryImages.default!;
}

export default function JobsScreen() {
  const router = useRouter();
  const jobsListRef = useRef<FlatList<TechnicianJob>>(null);
  const user = useAuthStore((state) => state.user);
  const cacheScope = useMemo(() => getJobsCacheScope(user), [user]);

  const [jobs, setJobs] = useState<TechnicianJob[]>([]);
  const [completedJobs, setCompletedJobs] = useState<TechnicianJob[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [offlineMessage, setOfflineMessage] = useState<string | null>(null);
  const [dataSource, setDataSource] = useState<"server" | "cache" | null>(
    null
  );
  const [lastSyncedAt, setLastSyncedAt] = useState<Date | null>(null);
  const [now, setNow] = useState(Date.now());
  const [searchQuery, setSearchQuery] = useState("");
  const [completedCount, setCompletedCount] = useState(0);
  const [isFilterModalVisible, setIsFilterModalVisible] = useState(false);
  const [statusFilter, setStatusFilter] = useState<JobStatusFilter>("ALL");
  const [dateFilter, setDateFilter] = useState<JobDateFilter>("ANY");
  const [draftStatusFilter, setDraftStatusFilter] = useState<JobStatusFilter>("ALL");
  const [draftDateFilter, setDraftDateFilter] = useState<JobDateFilter>("ANY");

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
        setJobs(cachedJobs.jobs.filter(isActiveAssignment));
        setDataSource("cache");
        setOfflineMessage(
          "Showing saved jobs while checking for updates. These details may be outdated."
        );
        setIsLoading(false);
      }
    }

    try {
      const serverJobs = normalizeJobs(await getTechnicianJobs())
        .filter(isActiveAssignment)
        .sort((first, second) => {
        const firstTimestamp = Date.parse(String(first.assigned_at || first.created_at || "")) || 0;
        const secondTimestamp = Date.parse(String(second.assigned_at || second.created_at || "")) || 0;
        return secondTimestamp - firstTimestamp;
      });

      setJobs(serverJobs);
      setDataSource("server");
      setLastSyncedAt(new Date());
      void getTechnicianJobHistory().then((history) => {
        const completed = history.filter((job) => ["COMPLETED", "COMPLETE", "CLOSED"].includes(normalizeStatus(job.status).replace(/[ -]+/g, "_")));
        setCompletedJobs(completed);
        setCompletedCount(completed.length);
      }).catch(() => undefined);
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
      jobsListRef.current?.scrollToOffset({ offset: 0, animated: false });
      void loadJobs();
    }, [loadJobs])
  );

  const getStatusCount = (filter: JobStatusFilter) => jobs.filter((job) => getJobStatusFilter(job) === filter).length;
  const assignedCount = getStatusCount("ASSIGNED");
  const acceptedCount = getStatusCount("ACCEPTED");
  const startedCount = getStatusCount("STARTED");
  const enRouteCount = getStatusCount("EN_ROUTE");
  const inProgressCount = getStatusCount("IN_PROGRESS");
  const visibleJobs = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    const sourceJobs = statusFilter === "COMPLETED" ? completedJobs : jobs;
    return sourceJobs.filter((job) => {
      const matchesQuery = !query || [job.job_number, job.id, job.service_type, job.title, job.customer_name, job.location, job.site_address, job.address].filter(Boolean).join(" ").toLowerCase().includes(query);
      const matchesStatus = statusFilter === "ALL" || getJobStatusFilter(job) === statusFilter;
      return matchesQuery && matchesStatus && matchesDateFilter(job, dateFilter, new Date());
    });
  }, [jobs, completedJobs, searchQuery, statusFilter, dateFilter]);

  useEffect(() => {
    if (!jobs.some((job) => getAcceptanceSeconds(job, Date.now()) !== null)) return;
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [jobs]);

  if (isLoading) {
    return <LoadingState label="Loading your jobs..." variant="list" />;
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

  return (
    <View style={styles.screen}>
      <FlatList
        ref={jobsListRef}
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
            <LinearGradient
              colors={["#00533F", "#087653", "#0B8B61"]}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
              style={styles.jobsHero}
            >
              <View style={styles.heroTitleRow}>
                <View style={styles.heroIcon}><Ionicons name="briefcase-outline" size={25} color="#FFFFFF" /></View>
                <View style={styles.heroTitleText}>
                  <Text style={styles.heroTitle}>Assigned Jobs</Text>
                  <Text style={styles.heroSubtitle}>Jobs assigned to you</Text>
                </View>
              </View>
              <Image source={require("../../assets/images/jobs-toolbox.png")} style={styles.heroArtwork} resizeMode="contain" accessibilityLabel="Green toolbox with technician tools" />
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.jobStatsRow} style={styles.jobStatsViewport}>
                <View style={[styles.jobStatCard, styles.assignedStat]}><View style={styles.statIcon}><Ionicons name="briefcase-outline" size={20} color="#075C40" /></View><View><Text style={styles.jobStatNumber}>{assignedCount}</Text><Text style={styles.jobStatLabel}>Assigned</Text></View></View>
                <View style={[styles.jobStatCard, styles.acceptedStat]}><View style={styles.statIcon}><Ionicons name="checkmark-done-outline" size={20} color="#087653" /></View><View><Text style={styles.jobStatNumber}>{acceptedCount}</Text><Text style={styles.jobStatLabel}>Accepted</Text></View></View>
                <View style={[styles.jobStatCard, styles.startedStat]}><View style={styles.statIcon}><Ionicons name="play-outline" size={20} color="#966500" /></View><View><Text style={styles.jobStatNumber}>{startedCount}</Text><Text style={styles.jobStatLabel}>Started</Text></View></View>
                <View style={[styles.jobStatCard, styles.enRouteStat]}><View style={styles.statIcon}><Ionicons name="navigate-outline" size={20} color="#175CD3" /></View><View><Text style={styles.jobStatNumber}>{enRouteCount}</Text><Text style={styles.jobStatLabel}>En Route</Text></View></View>
                <View style={[styles.jobStatCard, styles.progressStat]}><View style={styles.statIcon}><Ionicons name="time-outline" size={20} color="#966500" /></View><View><Text style={styles.jobStatNumber}>{inProgressCount}</Text><Text style={styles.jobStatLabel}>In Progress</Text></View></View>
                <View style={[styles.jobStatCard, styles.completedStat]}><View style={styles.statIcon}><Ionicons name="checkmark-circle-outline" size={20} color="#087C80" /></View><View><Text style={styles.jobStatNumber}>{completedCount}</Text><Text style={styles.jobStatLabel}>Completed</Text></View></View>
              </ScrollView>
            </LinearGradient>

            <View style={styles.searchRow}>
              <View style={styles.searchBox}>
                <Ionicons name="search-outline" size={22} color="#1F2937" />
                <TextInput value={searchQuery} onChangeText={setSearchQuery} placeholder="Search by job ID, customer or location" placeholderTextColor="#78828C" style={styles.searchInput} returnKeyType="search" />
              </View>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Filter jobs by status and date"
                onPress={() => {
                  setDraftStatusFilter(statusFilter);
                  setDraftDateFilter(dateFilter);
                  setIsFilterModalVisible(true);
                }}
                style={styles.filterButton}
              >
                <Ionicons name="options-outline" size={22} color="#075C40" />
                {statusFilter !== "ALL" || dateFilter !== "ANY" ? <View style={styles.filterActiveDot} /> : null}
              </Pressable>
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
            ) : dataSource === "server" && lastSyncedAt ? (
              <Text style={styles.lastSynced}>Last synced {lastSyncedAt.toLocaleTimeString()}</Text>
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

          </View>
        }
        ListEmptyComponent={
          <EmptyState
            title={statusFilter !== "ALL" || dateFilter !== "ANY" || searchQuery ? "No matching jobs" : "No jobs assigned"}
            message={statusFilter !== "ALL" || dateFilter !== "ANY" || searchQuery ? "Try changing or clearing your filters." : "Newly assigned jobs will appear here."}
            onRetry={() => void loadJobs(true)}
          />
        }
        renderItem={({ item }) => {
          const acceptanceSeconds = getAcceptanceSeconds(item, now);
          const acceptanceColor = acceptanceSeconds !== null && acceptanceSeconds <= 30 ? "#DC2626" : acceptanceSeconds !== null && acceptanceSeconds <= 120 ? "#D97706" : "#078A4D";
          const statusLabel = normalizeStatus(item.status).toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());

          return (
            <View style={styles.compactJobCard}>
              <View style={styles.compactJobBody}>
                <View style={styles.jobCardHeading}>
                  <View style={styles.compactTitleIcon}><Ionicons name="flash" size={21} color="#087653" /></View>
                  <View style={styles.compactTitleGroup}>
                    <Text style={styles.compactTitle} numberOfLines={1}>{item.service_type || item.title || "Service Request"}</Text>
                    <Text style={styles.compactJobNumber} numberOfLines={1}>#{item.job_number || item.id}</Text>
                  </View>
                  <View style={styles.statusPill}><Text style={styles.statusPillText}>{statusLabel || "Assigned"}</Text></View>
                </View>
                <View style={styles.jobSummaryRow}>
                  <View style={styles.compactInfoRows}>
                    <View style={styles.compactInfoRow}><View style={styles.compactInfoIcon}><Ionicons name="location-outline" size={16} color="#087653" /></View><Text style={styles.compactInfoText} numberOfLines={2}>{item.location || item.site_address || item.address || "Location not provided"}</Text></View>
                    <View style={styles.compactInfoRow}><View style={styles.compactInfoIcon}><Ionicons name="call-outline" size={16} color="#087653" /></View><Text style={styles.compactInfoText} numberOfLines={1}>{item.contact_number || "Phone not provided"}</Text></View>
                    <View style={styles.compactInfoRow}><View style={styles.compactInfoIcon}><Ionicons name="calendar-outline" size={16} color="#087653" /></View><Text style={styles.compactInfoText} numberOfLines={1}>{formatSchedule(item.preferred_service_date, item.preferred_service_time)}</Text></View>
                  </View>
                  <Image source={getJobThumbnailSource(item)} style={styles.jobThumbnail} resizeMode="cover" accessibilityLabel={`Photo for ${item.service_type || item.title || "service job"}`} />
                </View>
                {acceptanceSeconds !== null ? <Text style={[styles.acceptanceCountdown, { color: acceptanceColor }]}>Respond within {formatAcceptanceTime(acceptanceSeconds)}</Text> : null}
              </View>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`Job info for job ${item.job_number ?? item.id}`}
                onPress={() => router.push({ pathname: "/(app)/jobs/[jobId]", params: { jobId: String(item.id), source: "jobs" } })}
                style={({ pressed }) => [styles.jobInfoButton, pressed && styles.liveRoutePressed]}
              >
                <LinearGradient colors={["#07553F", "#07805A"]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={styles.jobInfoGradient}>
                  <Ionicons name="information-circle-outline" size={18} color="#FFFFFF" />
                  <Text style={styles.liveRouteText}>Job Info</Text>
                  <Ionicons name="arrow-forward" size={16} color="#FFFFFF" />
                </LinearGradient>
              </Pressable>
            </View>
          );
        }}
      />
      <Modal
        visible={isFilterModalVisible}
        transparent
        animationType="slide"
        statusBarTranslucent
        onRequestClose={() => setIsFilterModalVisible(false)}
      >
        <View style={styles.filterModalRoot}>
          <Pressable style={styles.filterBackdrop} onPress={() => setIsFilterModalVisible(false)} />
          <View style={styles.filterSheet}>
            <View style={styles.filterSheetHandle} />
            <View style={styles.filterSheetHeader}>
              <View>
                <Text style={styles.filterSheetTitle}>Filter jobs</Text>
                <Text style={styles.filterSheetSubtitle}>Choose a status and scheduled date</Text>
              </View>
              <Pressable accessibilityRole="button" accessibilityLabel="Close filters" onPress={() => setIsFilterModalVisible(false)} style={styles.filterCloseButton}>
                <Ionicons name="close" size={22} color="#42534A" />
              </Pressable>
            </View>

            <ScrollView style={styles.filterOptionsScroll} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
              <Text style={styles.filterSectionTitle}>Status</Text>
              <View style={styles.filterChoices}>
                {jobStatusFilters.map((option) => (
                  <Pressable
                    key={option.value}
                    accessibilityRole="button"
                    accessibilityState={{ selected: draftStatusFilter === option.value }}
                    onPress={() => setDraftStatusFilter(option.value)}
                    style={[styles.filterChoice, draftStatusFilter === option.value && styles.filterChoiceSelected]}
                  >
                    <Text style={[styles.filterChoiceText, draftStatusFilter === option.value && styles.filterChoiceTextSelected]}>{option.label}</Text>
                  </Pressable>
                ))}
              </View>

              <Text style={[styles.filterSectionTitle, styles.dateFilterTitle]}>Scheduled date</Text>
              <View style={styles.filterChoices}>
                {jobDateFilters.map((option) => (
                  <Pressable
                    key={option.value}
                    accessibilityRole="button"
                    accessibilityState={{ selected: draftDateFilter === option.value }}
                    onPress={() => setDraftDateFilter(option.value)}
                    style={[styles.filterChoice, draftDateFilter === option.value && styles.filterChoiceSelected]}
                  >
                    <Text style={[styles.filterChoiceText, draftDateFilter === option.value && styles.filterChoiceTextSelected]}>{option.label}</Text>
                  </Pressable>
                ))}
              </View>
            </ScrollView>

            <View style={styles.filterSheetActions}>
              <Pressable
                accessibilityRole="button"
                onPress={() => {
                  setDraftStatusFilter("ALL");
                  setDraftDateFilter("ANY");
                  setStatusFilter("ALL");
                  setDateFilter("ANY");
                  setIsFilterModalVisible(false);
                }}
                style={styles.clearFiltersButton}
              >
                <Text style={styles.clearFiltersText}>Clear</Text>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                onPress={() => {
                  setStatusFilter(draftStatusFilter);
                  setDateFilter(draftDateFilter);
                  setIsFilterModalVisible(false);
                }}
                style={styles.applyFiltersButton}
              >
                <Text style={styles.applyFiltersText}>Apply filters</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#EEF4F1"
  },

  jobsHero: { position: "relative", paddingHorizontal: 18, paddingTop: 17, paddingBottom: 20, borderBottomLeftRadius: 28, borderBottomRightRadius: 28 },
  heroTitleRow: { minHeight: 68, flexDirection: "row", alignItems: "center", gap: 12, marginBottom: 16, zIndex: 1 },
  heroIcon: { width: 46, height: 46, borderRadius: 14, alignItems: "center", justifyContent: "center", backgroundColor: "rgba(255,255,255,0.14)" },
  heroTitleText: { flex: 1, maxWidth: "55%" },
  heroTitle: { color: "#FFFFFF", fontSize: 21, fontWeight: "800", letterSpacing: -0.3 },
  heroSubtitle: { color: "#D7F2E5", fontSize: 13, marginTop: 3 },
  heroArtwork: { position: "absolute", width: 88, height: 80, right: 10, top: 47, zIndex: 0 },
  jobStatsViewport: { marginTop: 38, marginHorizontal: -18, flexGrow: 0 },
  jobStatsRow: { flexDirection: "row", gap: 8, paddingHorizontal: 18, paddingRight: 22 },
  jobStatCard: { width: 100, minHeight: 67, flexShrink: 0, borderRadius: 18, paddingHorizontal: 7, paddingVertical: 8, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6 },
  assignedStat: { backgroundColor: "#DDF9DE" },
  acceptedStat: { backgroundColor: "#E3F7E9" },
  startedStat: { backgroundColor: "#FFF3D7" },
  enRouteStat: { backgroundColor: "#E2F0FF" },
  progressStat: { backgroundColor: "#FFF3D7" },
  completedStat: { backgroundColor: "#DDF7F7" },
  statIcon: { width: 31, height: 31, borderRadius: 16, alignItems: "center", justifyContent: "center", backgroundColor: "rgba(255,255,255,0.65)" },
  jobStatNumber: { color: "#111827", fontSize: 17, lineHeight: 19, fontWeight: "900" },
  jobStatLabel: { color: "#17211B", fontSize: 9, fontWeight: "700", marginTop: 1 },
  searchRow: { flexDirection: "row", alignItems: "center", gap: 9, marginHorizontal: 15, marginTop: 14, marginBottom: 15 },
  searchBox: { flex: 1, minHeight: 52, paddingHorizontal: 13, flexDirection: "row", alignItems: "center", gap: 10, backgroundColor: "#FFFFFF", borderRadius: 16, borderWidth: 1, borderColor: "#DDE7E1", shadowColor: "#164E3B", shadowOffset: { width: 0, height: 3 }, shadowOpacity: 0.08, shadowRadius: 6, elevation: 2 },
  searchInput: { flex: 1, minWidth: 0, color: "#17211B", fontSize: 13, paddingVertical: 8 },
  filterButton: { width: 52, height: 52, borderRadius: 16, alignItems: "center", justifyContent: "center", backgroundColor: "#DDF9DE", borderWidth: 1, borderColor: "#C8E9CF" },
  filterActiveDot: { position: "absolute", width: 8, height: 8, borderRadius: 4, top: 8, right: 8, backgroundColor: "#087653" },
  filterModalRoot: { flex: 1, justifyContent: "flex-end" },
  filterBackdrop: { ...StyleSheet.absoluteFill, backgroundColor: "rgba(12, 25, 18, 0.45)" },
  filterSheet: { maxHeight: "85%", paddingHorizontal: 20, paddingTop: 10, paddingBottom: 24, backgroundColor: "#FFFFFF", borderTopLeftRadius: 26, borderTopRightRadius: 26 },
  filterOptionsScroll: { flexShrink: 1 },
  filterSheetHandle: { width: 42, height: 4, alignSelf: "center", borderRadius: 2, backgroundColor: "#CBD5CE", marginBottom: 15 },
  filterSheetHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 20 },
  filterSheetTitle: { color: "#17211B", fontSize: 20, fontWeight: "800" },
  filterSheetSubtitle: { color: "#6B7A70", fontSize: 12, marginTop: 4 },
  filterCloseButton: { width: 38, height: 38, borderRadius: 19, alignItems: "center", justifyContent: "center", backgroundColor: "#F0F5F1" },
  filterSectionTitle: { color: "#24352B", fontSize: 14, fontWeight: "800", marginBottom: 10 },
  dateFilterTitle: { marginTop: 19 },
  filterChoices: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  filterChoice: { minHeight: 38, paddingHorizontal: 13, borderRadius: 20, borderWidth: 1, borderColor: "#DCE7DF", backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center" },
  filterChoiceSelected: { backgroundColor: "#087653", borderColor: "#087653" },
  filterChoiceText: { color: "#526257", fontSize: 12, fontWeight: "700" },
  filterChoiceTextSelected: { color: "#FFFFFF" },
  filterSheetActions: { flexDirection: "row", gap: 10, marginTop: 25 },
  clearFiltersButton: { minHeight: 49, minWidth: 96, paddingHorizontal: 18, borderRadius: 14, borderWidth: 1, borderColor: "#DCE7DF", alignItems: "center", justifyContent: "center" },
  clearFiltersText: { color: "#395144", fontSize: 14, fontWeight: "800" },
  applyFiltersButton: { flex: 1, minHeight: 49, paddingHorizontal: 18, borderRadius: 14, backgroundColor: "#087653", alignItems: "center", justifyContent: "center" },
  applyFiltersText: { color: "#FFFFFF", fontSize: 14, fontWeight: "800" },
  lastSynced: { marginHorizontal: 20, marginBottom: 12, color: "#6B7280", fontSize: 11, textAlign: "right" },

  compactJobCard: { marginHorizontal: 14, marginBottom: 14, borderRadius: 19, overflow: "hidden", backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#D8E7DF", borderLeftWidth: 4, borderLeftColor: "#48C944", shadowColor: "#164E3B", shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.10, shadowRadius: 8, elevation: 3 },
  compactJobBody: { paddingHorizontal: 12, paddingTop: 12, backgroundColor: "#FFFFFF" },
  jobCardHeading: { minHeight: 54, flexDirection: "row", alignItems: "center", gap: 10, paddingBottom: 8 },
  compactTitleIcon: { width: 48, height: 48, borderRadius: 14, alignItems: "center", justifyContent: "center", backgroundColor: "#E1F8E0" },
  compactTitleGroup: { flex: 1, minWidth: 0 },
  compactTitle: { color: "#111827", fontSize: 16, fontWeight: "800" },
  compactJobNumber: { color: "#374151", fontSize: 12, marginTop: 2 },
  statusPill: { paddingHorizontal: 10, paddingVertical: 7, borderRadius: 16, backgroundColor: "#D8F7D6" },
  statusPillText: { color: "#075C28", fontSize: 11, fontWeight: "800" },
  compactInfoRows: { flex: 1, minWidth: 0, paddingVertical: 4, backgroundColor: "#FFFFFF" },
  jobSummaryRow: { width: "100%", flexDirection: "row", alignItems: "center", gap: 9 },
  jobThumbnail: { width: 89, height: 76, flexShrink: 0, borderRadius: 13, backgroundColor: "#E7E2DA" },
  compactInfoRow: { minHeight: 35, flexDirection: "row", alignItems: "center", gap: 9, paddingVertical: 4 },
  compactInfoIcon: { width: 30, height: 30, borderRadius: 15, alignItems: "center", justifyContent: "center", backgroundColor: "#EEF9F0" },
  compactInfoText: { flex: 1, color: "#111827", fontSize: 13, lineHeight: 18, fontWeight: "500" },
  acceptanceCountdown: { fontSize: 11, fontWeight: "800", marginBottom: 8, textAlign: "right" },
  jobInfoButton: { minHeight: 48, marginHorizontal: 10, marginBottom: 10, overflow: "hidden", borderRadius: 13, borderWidth: 1, borderColor: "#0A7654", shadowColor: "#164E3B", shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.10, shadowRadius: 4, elevation: 1 },
  jobInfoGradient: { minHeight: 48, paddingHorizontal: 13, borderRadius: 12, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8 },
  liveRoutePressed: { opacity: 0.88, transform: [{ scale: 0.99 }] },
  liveRouteText: { color: "#FFFFFF", fontSize: 13, fontWeight: "800" },

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

  searchIcon: {
    color: "#536779",
    fontSize: 30,
    lineHeight: 34,
    marginRight: 10
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
    paddingHorizontal: 0,
    paddingBottom: 24
  },
  emptyList: {
    flexGrow: 1,
    paddingHorizontal: 16,
    paddingBottom: 24
  },

  jobCard: {
    backgroundColor: "#FBFEFD",
    borderRadius: 15,
    borderWidth: 1,
    borderColor: "#E3ECE7",
    borderLeftWidth: 4,
    borderLeftColor: "#0AA66A",
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 12,
    marginBottom: 14,
    shadowColor: "#154434",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08,
    shadowRadius: 9,
    elevation: 2
  },
  urgentCard: {
    borderLeftWidth: 4,
    borderLeftColor: "#0AA66A"
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
    borderTopWidth: 1,
    borderTopColor: "#E9EEF2",
    marginTop: 12,
    paddingTop: 12,
    backgroundColor: "transparent",
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    flexWrap: "wrap",
    gap: 10
  },
  detailsButtonPressed: {
    opacity: 0.85
  },
  detailsButtonText: {
    color: "#156B5B",
    fontSize: 12,
    fontWeight: "700"
  },
  detailsButtonArrow: {
    color: "#156B5B",
    fontSize: 20,
    lineHeight: 22,
    fontWeight: "700"
  },

  cardHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 8, marginBottom: 12 },
  jobHeading: { flex: 1, minWidth: 0 },
  jobId: { fontSize: 11, color: "#9CA3AF", fontWeight: "700", marginBottom: 3 },
  badgeGroup: { flexDirection: "row", justifyContent: "flex-end", flexWrap: "wrap", gap: 6, maxWidth: "55%" },
  webBadge: { fontSize: 10, fontWeight: "700", paddingHorizontal: 9, paddingVertical: 5, borderRadius: 16, overflow: "hidden" },
  webDetails: { borderTopWidth: 1, borderBottomWidth: 1, borderColor: "#E9EEF2", paddingVertical: 4 },
  webDetail: { minHeight: 54, flexDirection: "row", alignItems: "flex-start", gap: 11, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: "#E7EDF2" },
  webDetailText: { flex: 1, minWidth: 0 },
  webDetailStrong: { color: "#172033", fontSize: 13, lineHeight: 19, fontWeight: "700" },
  webDetailSub: { color: "#64748B", fontSize: 12, lineHeight: 18, marginTop: 2 },
  callCustomer: { color: "#1769E8", fontSize: 12, marginTop: 3 },
  serviceDetails: { flexDirection: "row", alignItems: "flex-start", gap: 11, paddingHorizontal: 3, paddingVertical: 12 },
  footerStatus: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 8, flex: 1, minWidth: 190 },
  checkCircle: { width: 27, height: 27, borderRadius: 14, alignItems: "center", justifyContent: "center", backgroundColor: "#D1FAE5" },
  assignedDate: { color: "#718096", fontSize: 10, lineHeight: 15, flexShrink: 1 },
  acceptanceTimer: { fontSize: 11, fontWeight: "800" },
  detailsAction: { minHeight: 36, paddingHorizontal: 10, borderWidth: 1, borderColor: "#156B5B", borderRadius: 8, flexDirection: "row", alignItems: "center", gap: 6 },

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
