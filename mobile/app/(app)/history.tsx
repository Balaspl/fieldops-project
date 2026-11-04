import { useCallback, useEffect, useMemo, useState } from "react";
import {
  FlatList,
  Image,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useAuthStore } from "../../src/auth/authStore";
import { deleteOfflineRecord, getOfflineRecord, setOfflineRecord } from "../../src/offline/offlineStore";
import { getTechnicianJobHistory, type TechnicianJob } from "../../src/api/technician";
import { EmptyState, ErrorState, LoadingState } from "../../src/components/ScreenState";

const JOB_HISTORY_CACHE_VERSION = 1;
const JOB_HISTORY_CACHE_PREFIX = "fieldops:offline:job-history:v1";
type HistoryTab = "COMPLETED" | "REJECTED";
type DateFilter = "ANY" | "THIS_MONTH" | "LAST_30_DAYS" | "THIS_YEAR";

const dateOptions: { label: string; value: DateFilter }[] = [
  { label: "All dates", value: "ANY" },
  { label: "This month", value: "THIS_MONTH" },
  { label: "Last 30 days", value: "LAST_30_DAYS" },
  { label: "This year", value: "THIS_YEAR" }
];

interface CachedJobHistory {
  version: number;
  tenantId: string;
  technicianId: string;
  savedAt: string;
  jobs: TechnicianJob[];
}

function isTechnicianJob(value: unknown): value is TechnicianJob {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return (typeof candidate.id === "string" || typeof candidate.id === "number") && typeof candidate.status === "string";
}

function isCachedJobHistory(value: unknown, tenantId: string, technicianId: string): value is CachedJobHistory {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return candidate.version === JOB_HISTORY_CACHE_VERSION && candidate.tenantId === tenantId && candidate.technicianId === technicianId && typeof candidate.savedAt === "string" && Number.isFinite(Date.parse(candidate.savedAt)) && Array.isArray(candidate.jobs) && candidate.jobs.every(isTechnicianJob);
}

function getHistoryCacheKey(tenantId: string, technicianId: string): string {
  return `${JOB_HISTORY_CACHE_PREFIX}:${encodeURIComponent(tenantId)}:${encodeURIComponent(technicianId)}`;
}

function normalizedStatus(job: TechnicianJob): string {
  return String(job.status ?? "UNKNOWN").replace(/[_-]+/g, " ").trim().toUpperCase();
}

function isCompleted(job: TechnicianJob): boolean {
  return ["COMPLETED", "COMPLETE", "CLOSED"].includes(normalizedStatus(job));
}

function historyDate(job: TechnicianJob): Date | null {
  const value = job.completed_at || job.rejected_at || job.cancelled_at || job.preferred_service_date || job.scheduled_at || job.created_at;
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function matchesDate(job: TechnicianJob, filter: DateFilter, now: Date): boolean {
  if (filter === "ANY") return true;
  const date = historyDate(job);
  if (!date) return false;
  if (filter === "THIS_MONTH") return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth();
  if (filter === "THIS_YEAR") return date.getFullYear() === now.getFullYear();
  const lowerBound = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 29);
  lowerBound.setHours(0, 0, 0, 0);
  return date >= lowerBound && date <= now;
}

function formatDate(value?: string | null): string {
  if (!value) return "Not scheduled";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString([], { month: "numeric", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" });
}

function paymentStatusLabel(value?: string | null): string {
  switch ((value ?? "UNAVAILABLE").toUpperCase()) {
    case "SUCCESSFUL": return "Paid";
    case "PENDING": return "Pending";
    case "FAILED": return "Failed";
    default: return "Unavailable";
  }
}

function formatAmount(value?: number | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "Unavailable";
  return `₹${value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function paymentMethodLabel(job: TechnicianJob): string {
  const method = String(job.payment_method ?? "").trim().toUpperCase();
  if (method === "CASH") return "Cash";
  if (method === "UPI") {
    const provider = String(job.payment_provider ?? "").trim();
    return provider ? `UPI · ${provider.replace(/_/g, " ")}` : "UPI";
  }
  if (method === "BOTH") return "Cash + UPI";
  return "Not recorded";
}

function serviceImage(job: TechnicianJob) {
  const kind = `${job.service_type ?? ""} ${job.title ?? ""} ${job.required_skill ?? ""}`.toLowerCase();
  if (kind.includes("electrical")) return require("../../assets/images/job-service-electrical.png");
  if (kind.includes("plumb")) return require("../../assets/images/job-service-plumbing.png");
  if (kind.includes("hvac") || kind.includes("air condition")) return require("../../assets/images/job-service-hvac.png");
  if (kind.includes("appliance")) return require("../../assets/images/job-service-appliances.png");
  if (kind.includes("network")) return require("../../assets/images/job-service-network.png");
  if (kind.includes("carpent")) return require("../../assets/images/job-service-carpentry.png");
  if (kind.includes("clean")) return require("../../assets/images/job-service-cleaning.png");
  if (kind.includes("security")) return require("../../assets/images/job-service-security.png");
  return require("../../assets/images/job-service-maintenance.png");
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
  const [selectedTab, setSelectedTab] = useState<HistoryTab>("COMPLETED");
  const [dateFilter, setDateFilter] = useState<DateFilter>("ANY");
  const [draftDateFilter, setDraftDateFilter] = useState<DateFilter>("ANY");
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const tenantId = user?.tenant_id == null ? "" : String(user.tenant_id).trim();
  const technicianId = user?.id == null ? "" : String(user.id).trim();
  const hasCacheScope = tenantId.length > 0 && technicianId.length > 0;

  const loadHistory = useCallback(async (refresh = false) => {
    const cacheKey = hasCacheScope ? getHistoryCacheKey(tenantId, technicianId) : null;
    const cacheScope = hasCacheScope ? { tenantId, technicianId } : null;
    if (refresh) setIsRefreshing(true);
    else {
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
          let cached: unknown = await getOfflineRecord<unknown>(cacheScope, "job-history", "history-list");
          if (cached === null) {
            const legacyValue = await AsyncStorage.getItem(cacheKey);
            if (legacyValue) {
              try {
                const parsed: unknown = JSON.parse(legacyValue);
                if (isCachedJobHistory(parsed, tenantId, technicianId)) {
                  await setOfflineRecord(cacheScope, "job-history", "history-list", parsed);
                  cached = parsed;
                }
              } finally {
                await AsyncStorage.removeItem(cacheKey);
              }
            }
          } else {
            await AsyncStorage.removeItem(cacheKey);
          }
          if (isCachedJobHistory(cached, tenantId, technicianId)) {
            setJobs(cached.jobs);
            setCachedAt(cached.savedAt);
            setIsShowingCachedData(true);
            cachedHistoryLoaded = true;
            setIsLoading(false);
          } else if (cached !== null) {
            await deleteOfflineRecord(cacheScope, "job-history", "history-list");
          }
        } catch {
          // A local-cache failure must not block the authoritative refresh.
        }
      }
      if (!hasCacheScope) throw new Error("Technician identity is unavailable. Sign in again to load job history.");
      const freshJobs = await getTechnicianJobHistory();
      const savedAt = new Date().toISOString();
      setJobs(freshJobs);
      setCachedAt(savedAt);
      setIsShowingCachedData(false);
      setError(null);
      if (cacheScope) {
        const cacheEntry: CachedJobHistory = { version: JOB_HISTORY_CACHE_VERSION, tenantId, technicianId, savedAt, jobs: freshJobs };
        try {
          await setOfflineRecord(cacheScope, "job-history", "history-list", cacheEntry);
        } catch {
          // Keep server results available when secure local storage is unavailable.
        } finally {
          try { await AsyncStorage.removeItem(cacheKey!); } catch { /* ignore legacy cache cleanup errors */ }
        }
      }
    } catch {
      setError("Unable to refresh job history. Check your connection and try again.");
      if (!cachedHistoryLoaded && !jobs.length) setJobs([]);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [hasCacheScope, tenantId, technicianId]);

  useEffect(() => { void loadHistory(); }, [loadHistory]);

  const completedJobs = useMemo(() => jobs.filter(isCompleted), [jobs]);
  const rejectedJobs = useMemo(() => jobs.filter((job) => !isCompleted(job)), [jobs]);
  const tabJobs = selectedTab === "COMPLETED" ? completedJobs : rejectedJobs;
  const visibleJobs = useMemo(() => tabJobs.filter((job) => matchesDate(job, dateFilter, new Date())), [tabJobs, dateFilter]);

  if (isLoading && jobs.length === 0) return <LoadingState label="Loading job history..." variant="list" />;
  if (error && jobs.length === 0 && !isShowingCachedData) {
    return <ErrorState title="Job history unavailable" message={error} onRetry={() => void loadHistory(true)} />;
  }

  return (
    <View style={styles.screen}>
      <LinearGradient pointerEvents="none" colors={["#E8F7EF", "#F3F8FF", "#F8FBFD"]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.screenBackground} />
      <FlatList
        data={visibleJobs}
        keyExtractor={(job) => String(job.id)}
        refreshControl={<RefreshControl refreshing={isRefreshing} onRefresh={() => void loadHistory(true)} tintColor="#087C47" />}
        contentContainerStyle={visibleJobs.length === 0 ? styles.emptyList : styles.list}
        ListHeaderComponent={(
          <>
            <LinearGradient colors={["#078349", "#00653D", "#087B4B"]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.hero}>
              <View style={styles.heroRow}>
                <View style={styles.heroMark}><Ionicons name="construct-outline" size={43} color="#FFFFFF" /></View>
                <View style={styles.heroDivider} />
                <View style={styles.heroCopy}>
                  <Text style={styles.heroTitle}>Job History</Text>
                  <Text style={styles.heroSubtitle}>Review your previous service jobs.</Text>
                </View>
                <Pressable accessibilityRole="button" accessibilityLabel="Filter job history by date" onPress={() => { setDraftDateFilter(dateFilter); setIsFilterOpen(true); }} style={styles.heroFilter}>
                  <Ionicons name="options-outline" size={31} color="#FFFFFF" />
                  {dateFilter !== "ANY" ? <View style={styles.filterDot} /> : null}
                </Pressable>
              </View>
            </LinearGradient>

            {isShowingCachedData ? <View style={styles.offlineNotice}><Text style={styles.offlineTitle}>Saved history · May be outdated</Text><Text style={styles.offlineText}>{cachedAt ? `Last saved ${new Date(cachedAt).toLocaleString()}. ` : ""}Refresh when connected to check for updates.</Text></View> : null}
            {error ? <Pressable accessibilityRole="button" onPress={() => void loadHistory(true)} style={styles.warning}><Text style={styles.warningText}>Refresh failed. Tap to retry.</Text></Pressable> : null}

            <View style={styles.statsRow}>
              <View style={styles.statCard}>
                <View style={styles.totalIcon}><Ionicons name="briefcase" size={29} color="#1764D9" /></View>
                <View><Text style={styles.statLabel}>Total Jobs</Text><Text style={styles.statNumber}>{jobs.length}</Text></View>
              </View>
              <View style={styles.statCard}>
                <View style={styles.completedIcon}><Ionicons name="checkmark" size={31} color="#FFFFFF" /></View>
                <View><Text style={styles.statLabel}>Completed</Text><Text style={styles.statNumber}>{completedJobs.length}</Text></View>
              </View>
            </View>

            <View style={styles.segmentWrap}>
              <Pressable accessibilityRole="tab" accessibilityState={{ selected: selectedTab === "COMPLETED" }} onPress={() => setSelectedTab("COMPLETED")} style={[styles.segment, selectedTab === "COMPLETED" && styles.segmentSelected]}>
                <Ionicons name="checkmark-circle" size={24} color={selectedTab === "COMPLETED" ? "#07834A" : "#FFFFFF"} />
                <Text style={[styles.segmentText, selectedTab === "COMPLETED" && styles.segmentTextSelected]}>Completed <Text style={styles.segmentCount}>{completedJobs.length}</Text></Text>
              </Pressable>
              <Pressable accessibilityRole="tab" accessibilityState={{ selected: selectedTab === "REJECTED" }} onPress={() => setSelectedTab("REJECTED")} style={[styles.segment, selectedTab === "REJECTED" && styles.segmentRejectedSelected]}>
                <Ionicons name="close-circle" size={24} color={selectedTab === "REJECTED" ? "#E31B3D" : "#E31B3D"} />
                <Text style={[styles.segmentText, selectedTab === "REJECTED" && styles.segmentRejectedText]}>Rejected <Text style={styles.segmentCount}>{rejectedJobs.length}</Text></Text>
              </Pressable>
            </View>
            {dateFilter !== "ANY" ? <Pressable onPress={() => setDateFilter("ANY")} style={styles.activeFilter}><Text style={styles.activeFilterText}>{dateOptions.find((option) => option.value === dateFilter)?.label} · Clear</Text><Ionicons name="close-circle" size={16} color="#087B4B" /></Pressable> : null}
          </>
        )}
        ListEmptyComponent={<EmptyState title={dateFilter === "ANY" ? `No ${selectedTab.toLowerCase()} jobs` : "No matching jobs"} message={dateFilter === "ANY" ? "Your previous jobs will appear here." : "Try another date range or clear the date filter."} onRetry={() => void loadHistory(true)} />}
        renderItem={({ item }) => {
          const rejected = !isCompleted(item);
          const service = item.service_type || item.title || "Service job";
          const status = rejected ? (normalizedStatus(item).replace(/\b\w/g, (letter) => letter.toUpperCase())) : "Completed";
          const hasPayment = !rejected;
          return (
            <View style={[styles.jobCard, rejected ? styles.rejectedCard : styles.completedCard]}>
              <LinearGradient colors={rejected ? ["#FFF1F3", "#FFFFFF"] : ["#E9FAF0", "#FFFFFF"]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={[styles.cardTop, rejected ? styles.cardTopRejected : styles.cardTopCompleted]}>
                <Image source={serviceImage(item)} style={[styles.serviceImage, rejected && styles.serviceImageRejected]} resizeMode="cover" />
                <View style={styles.jobTitleWrap}>
                  <Text style={[styles.jobNumber, rejected && styles.rejectedText]} numberOfLines={1}>Job #{item.job_number ?? item.id}</Text>
                  <Text style={styles.serviceTitle} numberOfLines={1}>{service}</Text>
                </View>
                <View style={[styles.statusPill, rejected ? styles.rejectedPill : styles.completedPill]}>
                  <Ionicons name={rejected ? "close-circle" : "checkmark-circle"} size={23} color={rejected ? "#DC1837" : "#07834A"} />
                  <Text style={[styles.statusPillText, rejected && styles.rejectedText]} numberOfLines={1}>{status}</Text>
                </View>
              </LinearGradient>

              <View style={styles.detailsRow}>
                <Ionicons name="person" size={22} color="#526987" />
                <View style={styles.customerBlock}><Text style={styles.detailLabel}>Customer</Text><Text style={styles.detailValue} numberOfLines={1}>{item.customer_name || "Customer"}</Text></View>
                <View style={styles.verticalRule} />
                <Ionicons name="calendar" size={22} color="#526987" />
                <View style={styles.scheduleBlock}><Text style={styles.detailLabel}>Scheduled</Text><Text style={styles.detailValue} numberOfLines={2}>{formatDate(item.preferred_service_date || item.scheduled_at)}</Text></View>
              </View>

              {hasPayment ? <LinearGradient colors={["#E4F9EC", "#F3FCF7"]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={styles.paymentPanel}>
                <View style={styles.paymentHeading}><Ionicons name="wallet" size={22} color="#07834A" /><Text style={styles.paymentTitle}>Payment Details</Text><View style={[styles.paymentBadge, item.payment_status === "SUCCESSFUL" ? styles.paymentPaid : styles.paymentOther]}><Text style={styles.paymentBadgeText}>{paymentStatusLabel(item.payment_status)}</Text></View></View>
                <View style={styles.paymentGrid}>
                  <View style={styles.paymentCell}><Text style={styles.detailLabel}>Amount</Text><Text style={styles.amountValue}>{formatAmount(item.payment_amount)}</Text></View>
                  <View style={styles.paymentDivider} />
                  <View style={styles.paymentCell}><Text style={styles.detailLabel}>Payment Mode</Text><Text style={styles.detailValue} numberOfLines={2}>{paymentMethodLabel(item)}</Text></View>
                  <View style={styles.paymentDivider} />
                  <View style={styles.paymentCell}><Text style={styles.detailLabel}>{item.payment_status === "SUCCESSFUL" ? "Paid On" : "Updated On"}</Text><Text style={styles.detailValue} numberOfLines={2}>{item.payment_updated_at ? formatDate(item.payment_updated_at) : "—"}</Text></View>
                </View>
              </LinearGradient> : null}

              <Pressable accessibilityRole="button" accessibilityLabel={`View details for job ${item.job_number ?? item.id}`} onPress={() => router.push({ pathname: "/(app)/jobs/[jobId]", params: { jobId: String(item.id), source: "history" } })} style={({ pressed }) => [styles.detailsButton, rejected ? styles.detailsButtonRejected : styles.detailsButtonCompleted, pressed && styles.pressed]}>
                <Ionicons name="document-text" size={21} color={rejected ? "#D71938" : "#087B4B"} />
                <Text style={[styles.detailsButtonText, rejected && styles.rejectedText]}>{rejected ? "View Details" : "View Job Details"}</Text>
                <Ionicons name="chevron-forward" size={24} color={rejected ? "#D71938" : "#087B4B"} />
              </Pressable>
            </View>
          );
        }}
      />

      <Modal visible={isFilterOpen} transparent animationType="slide" statusBarTranslucent onRequestClose={() => setIsFilterOpen(false)}>
        <View style={styles.modalRoot}>
          <Pressable style={styles.backdrop} onPress={() => setIsFilterOpen(false)} />
          <View style={styles.filterSheet}>
            <View style={styles.sheetHandle} />
            <View style={styles.sheetHeading}><View><Text style={styles.sheetTitle}>Filter job history</Text><Text style={styles.sheetSubtitle}>Choose when the job was scheduled</Text></View><Pressable accessibilityRole="button" accessibilityLabel="Close filters" onPress={() => setIsFilterOpen(false)} style={styles.closeButton}><Ionicons name="close" size={22} color="#31463B" /></Pressable></View>
            <ScrollView style={styles.filterOptions} contentContainerStyle={styles.filterOptionsContent}>
              {dateOptions.map((option) => <Pressable key={option.value} accessibilityRole="radio" accessibilityState={{ selected: draftDateFilter === option.value }} onPress={() => setDraftDateFilter(option.value)} style={[styles.dateOption, draftDateFilter === option.value && styles.dateOptionSelected]}><Text style={[styles.dateOptionText, draftDateFilter === option.value && styles.dateOptionTextSelected]}>{option.label}</Text>{draftDateFilter === option.value ? <Ionicons name="checkmark-circle" size={21} color="#087B4B" /> : null}</Pressable>)}
            </ScrollView>
            <View style={styles.sheetActions}><Pressable onPress={() => { setDateFilter("ANY"); setDraftDateFilter("ANY"); setIsFilterOpen(false); }} style={styles.clearButton}><Text style={styles.clearText}>Clear</Text></Pressable><Pressable onPress={() => { setDateFilter(draftDateFilter); setIsFilterOpen(false); }} style={styles.applyButton}><Text style={styles.applyText}>Apply filter</Text></Pressable></View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "transparent" },
  screenBackground: { ...StyleSheet.absoluteFill, opacity: 0.96 },
  list: { paddingBottom: 20 },
  emptyList: { flexGrow: 1, paddingBottom: 20 },
  hero: { minHeight: 158, paddingTop: 30, paddingBottom: 24, paddingHorizontal: 26, borderBottomLeftRadius: 30, borderBottomRightRadius: 30, justifyContent: "flex-end" },
  heroRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  heroMark: { width: 82, height: 76, alignItems: "center", justifyContent: "center" },
  heroDivider: { width: 2, height: 74, backgroundColor: "rgba(255,255,255,0.85)" },
  heroCopy: { flex: 1, minWidth: 0 },
  heroTitle: { color: "#FFFFFF", fontSize: 27, fontWeight: "900", letterSpacing: -0.4 },
  heroSubtitle: { color: "#E2F7E9", fontSize: 14, lineHeight: 20, marginTop: 5 },
  heroFilter: { width: 60, height: 60, borderRadius: 32, alignItems: "center", justifyContent: "center", backgroundColor: "rgba(255,255,255,0.16)" },
  filterDot: { position: "absolute", right: 10, top: 10, width: 8, height: 8, borderRadius: 4, backgroundColor: "#B8F5D0" },
  statsRow: { flexDirection: "row", gap: 12, marginHorizontal: 18, marginTop: 17, marginBottom: 15 },
  statCard: { flex: 1, minHeight: 92, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 12, paddingHorizontal: 10, backgroundColor: "#FFFFFF", borderWidth: 1.5, borderColor: "#D8EFE6", borderRadius: 23 },
  totalIcon: { width: 59, height: 59, borderRadius: 31, alignItems: "center", justifyContent: "center", backgroundColor: "#E1EEFF" },
  completedIcon: { width: 59, height: 59, borderRadius: 31, alignItems: "center", justifyContent: "center", backgroundColor: "#0A9B5D", borderWidth: 9, borderColor: "#D5F7E7" },
  statLabel: { color: "#315B65", fontSize: 15, fontWeight: "800" },
  statNumber: { color: "#0D2540", fontSize: 25, fontWeight: "900", marginTop: 1 },
  segmentWrap: { minHeight: 55, marginHorizontal: 36, marginBottom: 15, borderWidth: 1.5, borderColor: "#D8E0F1", borderRadius: 30, padding: 3, flexDirection: "row", backgroundColor: "#F0F3FB" },
  segment: { flex: 1, borderRadius: 27, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 7 },
  segmentSelected: { backgroundColor: "#078C4A" },
  segmentRejectedSelected: { backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#F3C5CC" },
  segmentText: { color: "#142A4E", fontSize: 14, fontWeight: "800" },
  segmentTextSelected: { color: "#FFFFFF" },
  segmentRejectedText: { color: "#D71938" },
  segmentCount: { fontWeight: "700" },
  activeFilter: { alignSelf: "flex-start", marginHorizontal: 24, marginBottom: 10, paddingHorizontal: 11, paddingVertical: 6, borderRadius: 16, backgroundColor: "#E3F8EC", flexDirection: "row", alignItems: "center", gap: 5 },
  activeFilterText: { color: "#087B4B", fontSize: 12, fontWeight: "700" },
  jobCard: { marginHorizontal: 16, marginBottom: 17, padding: 10, backgroundColor: "#FFFFFF", borderRadius: 24, borderWidth: 1.5, overflow: "hidden", shadowColor: "#153B2F", shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.11, shadowRadius: 12, elevation: 4 },
  completedCard: { borderColor: "#79D6A1" },
  rejectedCard: { borderColor: "#E6C8CF" },
  cardTop: { minHeight: 91, flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 8, paddingBottom: 9, borderBottomWidth: 1, borderTopLeftRadius: 15, borderTopRightRadius: 15 },
  cardTopCompleted: { borderBottomColor: "#D8F0E0" },
  cardTopRejected: { borderBottomColor: "#F1DDE1" },
  serviceImage: { width: 68, height: 68, borderRadius: 19, backgroundColor: "#D9F7E5" },
  serviceImageRejected: { backgroundColor: "#FDE8EC" },
  jobTitleWrap: { flex: 1, minWidth: 0 },
  jobNumber: { color: "#087B35", fontSize: 15, fontWeight: "900" },
  rejectedText: { color: "#D71938" },
  serviceTitle: { color: "#0E2746", fontSize: 20, fontWeight: "900", marginTop: 3 },
  statusPill: { maxWidth: "47%", minHeight: 43, paddingHorizontal: 10, borderRadius: 24, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6 },
  completedPill: { backgroundColor: "#D9F8E6" },
  rejectedPill: { backgroundColor: "#FFE7EB" },
  statusPillText: { color: "#087B35", fontSize: 12, fontWeight: "800", flexShrink: 1 },
  detailsRow: { minHeight: 79, paddingHorizontal: 9, paddingVertical: 12, flexDirection: "row", alignItems: "center", gap: 9 },
  customerBlock: { flex: 1, minWidth: 0 },
  scheduleBlock: { flex: 1.2, minWidth: 0 },
  verticalRule: { width: 1.5, height: 54, backgroundColor: "#D7DFE8", marginHorizontal: 2 },
  detailLabel: { color: "#536A87", fontSize: 12, fontWeight: "600" },
  detailValue: { color: "#102A4D", fontSize: 14, lineHeight: 19, fontWeight: "600", marginTop: 2 },
  paymentPanel: { marginHorizontal: 2, marginTop: 3, marginBottom: 10, padding: 12, borderRadius: 21, borderWidth: 1, borderColor: "#D0F0DD" },
  paymentHeading: { minHeight: 34, flexDirection: "row", alignItems: "center", gap: 8 },
  paymentTitle: { color: "#087B43", fontSize: 15, fontWeight: "900", flex: 1 },
  paymentBadge: { paddingHorizontal: 13, paddingVertical: 7, borderRadius: 18 },
  paymentPaid: { backgroundColor: "#C3F5D7" },
  paymentOther: { backgroundColor: "#FFF0CC" },
  paymentBadgeText: { color: "#087B43", fontSize: 12, fontWeight: "800" },
  paymentGrid: { flexDirection: "row", alignItems: "stretch", marginTop: 12 },
  paymentCell: { flex: 1, minWidth: 0, paddingHorizontal: 5 },
  paymentDivider: { width: 1, backgroundColor: "#CFEBDD", marginHorizontal: 3 },
  amountValue: { color: "#087B35", fontSize: 17, fontWeight: "900", marginTop: 5 },
  detailsButton: { minHeight: 52, borderRadius: 25, paddingHorizontal: 15, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 9 },
  detailsButtonCompleted: { backgroundColor: "#DDF7E8" },
  detailsButtonRejected: { backgroundColor: "#FFE8EC" },
  detailsButtonText: { flex: 1, textAlign: "center", color: "#087B43", fontSize: 15, fontWeight: "900" },
  pressed: { opacity: 0.78, transform: [{ scale: 0.99 }] },
  offlineNotice: { backgroundColor: "#FFF7DB", borderColor: "#F1D48A", borderWidth: 1, padding: 12, marginHorizontal: 16, marginTop: 12, borderRadius: 12 },
  offlineTitle: { color: "#854D0E", fontSize: 13, fontWeight: "800" },
  offlineText: { color: "#854D0E", fontSize: 12, lineHeight: 18, marginTop: 4 },
  warning: { backgroundColor: "#FEF3C7", padding: 12, marginHorizontal: 16, marginTop: 12, borderRadius: 10 },
  warningText: { color: "#92400E", fontSize: 13 },
  modalRoot: { flex: 1, justifyContent: "flex-end" },
  backdrop: { ...StyleSheet.absoluteFill, backgroundColor: "rgba(12,25,18,0.45)" },
  filterSheet: { maxHeight: "70%", paddingHorizontal: 22, paddingTop: 10, paddingBottom: 24, backgroundColor: "#FFFFFF", borderTopLeftRadius: 26, borderTopRightRadius: 26 },
  sheetHandle: { width: 42, height: 4, alignSelf: "center", borderRadius: 3, backgroundColor: "#CBD5CE", marginBottom: 15 },
  sheetHeading: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 17 },
  sheetTitle: { color: "#17211B", fontSize: 20, fontWeight: "900" },
  sheetSubtitle: { color: "#6B7A70", fontSize: 12, marginTop: 4 },
  closeButton: { width: 38, height: 38, borderRadius: 19, alignItems: "center", justifyContent: "center", backgroundColor: "#F0F5F1" },
  filterOptions: { flexShrink: 1 },
  filterOptionsContent: { gap: 8 },
  dateOption: { minHeight: 48, borderWidth: 1, borderColor: "#DCE7DF", borderRadius: 14, paddingHorizontal: 14, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  dateOptionSelected: { borderColor: "#087B4B", backgroundColor: "#F0FBF4" },
  dateOptionText: { color: "#42534A", fontSize: 14, fontWeight: "700" },
  dateOptionTextSelected: { color: "#087B4B" },
  sheetActions: { flexDirection: "row", gap: 10, marginTop: 19 },
  clearButton: { minHeight: 49, minWidth: 95, borderWidth: 1, borderColor: "#DCE7DF", borderRadius: 14, alignItems: "center", justifyContent: "center" },
  clearText: { color: "#395144", fontSize: 14, fontWeight: "800" },
  applyButton: { flex: 1, minHeight: 49, borderRadius: 14, backgroundColor: "#087B4B", alignItems: "center", justifyContent: "center" },
  applyText: { color: "#FFFFFF", fontSize: 14, fontWeight: "800" }
});
