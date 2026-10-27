import { useCallback, useEffect, useState } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import {
  deleteOfflineRecord,
  getOfflineRecord,
  setOfflineRecord,
  type OfflineScope
} from "../../../src/offline/offlineStore";
import { isAxiosError } from "axios";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useAuthStore } from "../../../src/auth/authStore";
import { isNetworkUnavailableError } from "../../../src/api/client";
import { setActiveGpsJob } from "../../../src/gps/backgroundLocationService";
import {
  getTechnicianJob,
  type TechnicianJob
} from "../../../src/api/technician";
import {
  performTechnicianJobAction,
  type TechnicianJobAction
} from "../../../src/api/jobActions";
import {
  enqueueJobAction,
  getJobActionQueue,
  type QueueableTechnicianJobAction,
  type QueuedJobAction
} from "../../../src/offline/jobActionQueue";
import { useNetworkStatus } from "../../../src/hooks/useNetworkStatus";
import {
  ErrorState,
  LoadingState
} from "../../../src/components/ScreenState";
import {
  getJobActionOptions,
  getJobStatusLabel,
  normalizeJobStatus
} from "../../../src/utils/jobStatus";

type IconName = keyof typeof Ionicons.glyphMap;

type CacheIdentifier = string | number | null | undefined;

interface CachedTechnicianJob {
  job: TechnicianJob;
  cachedAt: string;
}

function getJobCacheKey(
  tenantId: CacheIdentifier,
  userId: CacheIdentifier,
  jobId: string
): string | null {
  if (tenantId == null || userId == null || !jobId.trim()) {
    return null;
  }

  const tenantKey = String(tenantId).trim();
  const technicianKey = String(userId).trim();

  if (!tenantKey || !technicianKey) {
    return null;
  }

  return [
    "fieldops:offline:job-detail:v1",
    encodeURIComponent(tenantKey),
    encodeURIComponent(technicianKey),
    encodeURIComponent(jobId)
  ].join(":");
}

function getJobCacheScope(
  tenantId: CacheIdentifier,
  userId: CacheIdentifier
): OfflineScope | null {
  if (tenantId == null || userId == null) {
    return null;
  }

  const tenantKey = String(tenantId).trim();
  const technicianKey = String(userId).trim();

  if (!tenantKey || !technicianKey) {
    return null;
  }

  return {
    tenantId: tenantKey,
    technicianId: technicianKey
  };
}

function isValidCachedTechnicianJob(
  value: unknown,
  expectedJobId: string
): value is CachedTechnicianJob {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as {
    job?: unknown;
    cachedAt?: unknown;
  };

  if (
    typeof candidate.job !== "object" ||
    candidate.job === null ||
    typeof candidate.cachedAt !== "string"
  ) {
    return false;
  }

  const cachedJob = candidate.job as Partial<TechnicianJob>;

  return String(cachedJob.id) === expectedJobId;
}

async function readCachedTechnicianJob(
  scope: OfflineScope | null,
  legacyCacheKey: string | null,
  expectedJobId: string
): Promise<CachedTechnicianJob | null> {
  if (!scope) {
    return null;
  }

  try {
    let parsedValue = await getOfflineRecord<unknown>(
      scope,
      "job-detail",
      expectedJobId
    );

    if (parsedValue === null && legacyCacheKey) {
      const rawValue = await AsyncStorage.getItem(legacyCacheKey);

      if (rawValue) {
        const legacyValue: unknown = JSON.parse(rawValue);

        if (isValidCachedTechnicianJob(legacyValue, expectedJobId)) {
          // Migration succeeds only if encrypted storage accepts the record.
          await setOfflineRecord(
            scope,
            "job-detail",
            expectedJobId,
            legacyValue
          );

          parsedValue = legacyValue;
        }

        // Remove the old plaintext copy after attempting migration.
        await AsyncStorage.removeItem(legacyCacheKey);
      }
    } else if (legacyCacheKey) {
      // The encrypted copy already exists; discard the plaintext copy.
      await AsyncStorage.removeItem(legacyCacheKey);
    }

    if (!isValidCachedTechnicianJob(parsedValue, expectedJobId)) {
      if (parsedValue !== null) {
        await deleteOfflineRecord(
          scope,
          "job-detail",
          expectedJobId
        );
      }

      return null;
    }

    return parsedValue;
  } catch {
    // Do not use legacy plaintext data if encrypted storage fails.
    if (legacyCacheKey) {
      try {
        await AsyncStorage.removeItem(legacyCacheKey);
      } catch {
        // Cache cleanup must not block the authoritative API request.
      }
    }

    return null;
  }
}

async function saveCachedTechnicianJob(
  scope: OfflineScope | null,
  jobId: string,
  job: TechnicianJob
): Promise<string> {
  const cachedAt = new Date().toISOString();

  if (!scope) {
    return cachedAt;
  }

  try {
    const cachedValue: CachedTechnicianJob = {
      job,
      cachedAt
    };

    await setOfflineRecord(
      scope,
      "job-detail",
      jobId,
      cachedValue
    );
  } catch {
    // A cache write failure must not turn a successful API request into a failure.
  }

  return cachedAt;
}

function canUseCachedJobAfterError(error: unknown): boolean {
  if (isNetworkUnavailableError(error)) {
    return true;
  }

  if (!isAxiosError(error) || !error.response) {
    return false;
  }

  const status = error.response.status;

  return (
    status === 408 ||
    status === 425 ||
    status === 429 ||
    status >= 500
  );
}

function formatCachedTimestamp(value: string | null): string {
  if (!value) {
    return "Last saved time unavailable.";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Last saved time unavailable.";
  }

  return `Last saved ${date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  })}.`;
}

export default function JobDetailScreen() {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);
  const { jobId } = useLocalSearchParams<{ jobId: string }>();
  const { isOffline } = useNetworkStatus();

  const [job, setJob] = useState<TechnicianJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [dataSource, setDataSource] =
    useState<"server" | "cache" | null>(null);
  const [cachedAt, setCachedAt] = useState<string | null>(null);
  const [activeAction, setActiveAction] =
    useState<TechnicianJobAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [queuedActions, setQueuedActions] = useState<QueuedJobAction[]>([]);
  const [isRejectModalVisible, setIsRejectModalVisible] = useState(false);
  const [rejectionReason, setRejectionReason] = useState("");
  const [currentTimeMs, setCurrentTimeMs] = useState(() => Date.now());

  const assignedStatus = job
    ? normalizeJobStatus(job.status)
    : "UNKNOWN";

  const assignedAtMs = job?.assigned_at
    ? Date.parse(job.assigned_at)
    : Number.NaN;

  const acceptanceRemainingSeconds =
    assignedStatus === "ASSIGNED" && Number.isFinite(assignedAtMs)
      ? Math.max(
          0,
          Math.floor(
            (assignedAtMs + 10 * 60 * 1000 - currentTimeMs) / 1000
          )
        )
      : null;

  const acceptanceExpired = acceptanceRemainingSeconds === 0;

  const loadJob = useCallback(async () => {
    if (!jobId) {
      setError("The job ID is missing.");
      setLoading(false);
      return;
    }

    const requestedJobId = String(jobId);
    const cacheKey = getJobCacheKey(
      user?.tenant_id,
      user?.id,
      requestedJobId
    );
    const cacheScope = getJobCacheScope(
      user?.tenant_id,
      user?.id
    );

    setLoading(true);
    setError(null);

    let cachedDetails = await readCachedTechnicianJob(
      cacheScope,
      cacheKey,
      requestedJobId
    );

    if (cachedDetails) {
      setJob(cachedDetails.job);
      setDataSource("cache");
      setCachedAt(cachedDetails.cachedAt);
      setLoading(false);
    }

    try {
      const result = await getTechnicianJob(requestedJobId);
      const savedAt = await saveCachedTechnicianJob(
        cacheScope,
        requestedJobId,
        result
      );

      setJob(result);
      setDataSource("server");
      setCachedAt(savedAt);
      setError(null);
    } catch (loadError: unknown) {
      if (canUseCachedJobAfterError(loadError)) {
        if (!cachedDetails) {
          cachedDetails = await readCachedTechnicianJob(
            cacheScope,
            cacheKey,
            requestedJobId
          );
        }

        if (cachedDetails) {
          setJob(cachedDetails.job);
          setDataSource("cache");
          setCachedAt(cachedDetails.cachedAt);
          setError(null);
        } else {
          setJob(null);
          setDataSource(null);
          setCachedAt(null);
          setError(
            "You're offline or FieldOps is temporarily unavailable, and this job has no saved offline details. Reconnect and try again."
          );
        }
      } else {
        setJob(null);
        setDataSource(null);
        setCachedAt(null);
        setError(
          "Unable to load this job. Your access may have changed, or the job may no longer be available."
        );

        if (
          isAxiosError(loadError) &&
          [401, 403, 404].includes(loadError.response?.status ?? 0)
        ) {
          try {
            if (cacheScope) {
              await deleteOfflineRecord(
                cacheScope,
                "job-detail",
                requestedJobId
              );
            }

            if (cacheKey) {
              await AsyncStorage.removeItem(cacheKey);
            }
          } catch {
            // A cache cleanup failure must not hide the API error.
          }
        }
      }
    } finally {
      setLoading(false);
    }
  }, [jobId, user?.id, user?.tenant_id]);

  const refreshQueuedActions = useCallback(async () => {
    if (
      !jobId ||
      user?.id == null ||
      user.tenant_id == null
    ) {
      setQueuedActions([]);
      return;
    }

    try {
      const items = await getJobActionQueue({
        tenantId: String(user.tenant_id),
        technicianId: String(user.id)
      });

      setQueuedActions(
        items.filter(
          (item) =>
            item.jobId === String(jobId) &&
            item.status !== "synced"
        )
      );
    } catch {
      setQueuedActions([]);
    }
  }, [jobId, user?.id, user?.tenant_id]);

  useEffect(() => {
    void loadJob();
  }, [loadJob]);

  useEffect(() => {
    void refreshQueuedActions();
  }, [refreshQueuedActions]);

  useEffect(() => {
    if (
      assignedStatus !== "ASSIGNED" ||
      !Number.isFinite(assignedAtMs)
    ) {
      return;
    }

    const deadlineMs = assignedAtMs + 10 * 60 * 1000;

    setCurrentTimeMs(Date.now());

    if (Date.now() >= deadlineMs) {
      return;
    }

    const interval = setInterval(() => {
      const now = Date.now();
      setCurrentTimeMs(now);

      if (now >= deadlineMs) {
        clearInterval(interval);
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [assignedStatus, assignedAtMs]);


  async function queueOfflineJobAction(
    action: QueueableTechnicianJobAction
  ) {
    if (
      !job ||
      activeAction ||
      user?.id == null ||
      user.tenant_id == null
    ) {
      Alert.alert(
        "Cannot save action",
        "A valid technician session and job are required."
      );
      return;
    }

    setActiveAction(action);
    setError(null);

    try {
      await enqueueJobAction({
        tenantId: String(user.tenant_id),
        technicianId: String(user.id),
        jobId: job.id,
        action
      });

      await refreshQueuedActions();

      Alert.alert(
        "Action saved offline",
        `Your ${action.replace(/-/g, " ")} action is saved on this device and is pending synchronization. The server has not yet confirmed a status change.`
      );
    } catch (queueError: unknown) {
      setError(
        queueError instanceof Error
          ? queueError.message
          : "Unable to save the job action offline."
      );
    } finally {
      setActiveAction(null);
    }
  }

  async function handleAction(action: TechnicianJobAction) {
    if (!job || activeAction) {
      return;
    }

    if (action === "reject") {
      if (isOffline || dataSource !== "server") {
        Alert.alert(
          "Connection required",
          "Reconnect and refresh the job before rejecting it."
        );
        return;
      }

      setRejectionReason("");
      setIsRejectModalVisible(true);
      setError(null);
      return;
    }

    if (action === "complete") {
      if (isOffline || dataSource !== "server") {
        Alert.alert(
          "Connection required",
          "Reconnect and refresh the job before completing it."
        );
        return;
      }

      router.push({
        pathname: "/(app)/jobs/[jobId]/completion",
        params: { jobId: String(job.id) }
      });
      return;
    }

    if (isOffline) {
      await queueOfflineJobAction(action);
      return;
    }

    if (dataSource !== "server") {
      Alert.alert(
        "Reconnect to update this job",
        "These saved details may be outdated. Reconnect and refresh the job before submitting an action."
      );
      return;
    }

    await submitJobAction(action);
  }

  async function submitJobAction(
    action: TechnicianJobAction,
    payload: { reason?: string } = {}
  ) {
    if (!job || activeAction) {
      return;
    }

    if (
      isOffline &&
      (action === "reject" || action === "complete")
    ) {
      Alert.alert(
        "Connection required",
        "Reconnect and refresh the job before submitting this action."
      );
      return;
    }

    if (dataSource !== "server") {
      Alert.alert(
        "Reconnect to update this job",
        "These are saved offline details and may be outdated. Reconnect and refresh the job before submitting an action."
      );
      return;
    }

    setActiveAction(action);
    setError(null);

    let gpsWarning = false;

    try {
      const response = await performTechnicianJobAction(
        job.id,
        action,
        payload
      );

      if (action === "start" || action === "on-site") {
        if (user?.id == null || user.tenant_id == null) {
          gpsWarning = true;
        } else {
          try {
            await setActiveGpsJob(job.id);
          } catch {
            gpsWarning = true;
          }
        }
      }

      if (action === "reject") {
        setIsRejectModalVisible(false);
        setJob(null);
        router.replace("/(app)/jobs");

        Alert.alert(
          "Job rejected",
          "This job has been removed from your active jobs."
        );
        return;
      }

      if (response.status) {
        setJob((currentJob) =>
          currentJob
            ? { ...currentJob, status: response.status! }
            : currentJob
        );
      }

      await loadJob();

      if (
        ["start", "en-route", "en_route", "enroute"].includes(action)
      ) {
        router.push({
          pathname: "/(app)/jobs/[jobId]/live-map",
          params: { jobId: String(job.id) }
        });
        return;
      }

      Alert.alert(
        "Job updated",
        gpsWarning
          ? "Your status was updated, but your location could not be sent. Check location permission and connection."
          : "The action was submitted to FieldOps."
      );
    } catch (actionError: unknown) {
      if (canUseCachedJobAfterError(actionError)) {
        setDataSource("cache");
      }

      setError(
        "The job action could not be confirmed by the server. Refresh the job before trying again."
      );
    } finally {
      setActiveAction(null);
    }
  }

 

  if (loading) {
    return <LoadingState label="Loading job details..." />;
  }

  if (error && !job) {
    return (
      <ErrorState
        title="Job details unavailable"
        message={error}
        onRetry={() => void loadJob()}
      />
    );
  }

  if (!job) {
    return (
      <ErrorState
        title="Job not found"
        message="This job is unavailable to your account."
        onRetry={() => void loadJob()}
      />
    );
  }

  const canRejectJob =
    assignedStatus === "AWAITING_ACCEPTANCE" ||
    assignedStatus === "ASSIGNED" ||
    assignedStatus === "ACTIVE";

  const availableActions = getJobActionOptions(job.status).filter(
    ({ action }) => action !== "reject" || canRejectJob
  );

  const isUrgent = job.priority?.toUpperCase() === "URGENT";

  const statusStyle =
    assignedStatus === "COMPLETED"
      ? styles.statusCompleted
      : assignedStatus === "ASSIGNED" ||
          assignedStatus === "AWAITING_ACCEPTANCE"
        ? styles.statusWaiting
        : styles.statusActive;

  const priorityStyle = isUrgent
    ? styles.priorityUrgent
    : styles.priorityNormal;

  return (
    <View style={styles.screen}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        {/* Green branded job header */}
        <View style={styles.hero}>
          <View style={styles.headerRow}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Go back"
              onPress={() => router.back()}
              style={({ pressed }) => [
                styles.backButton,
                pressed && styles.pressed
              ]}
            >
              <Ionicons
                name="arrow-back"
                size={23}
                color="#FFFFFF"
              />
            </Pressable>

            <View style={styles.headerReference}>
              <Text style={styles.headerEyebrow}>
                FIELD SERVICE
              </Text>

              <Text style={styles.headerJobNumber}>
                JOB #{job.job_number ?? String(job.id)}
              </Text>
            </View>

            <View style={styles.headerDecoration}>
              <Ionicons
                name="construct-outline"
                size={25}
                color="#A8E6C8"
              />
            </View>
          </View>

          <Text style={styles.jobTitle}>
            {job.title || "Service job"}
          </Text>

          <View style={styles.headerBottomRow}>
            <View style={[styles.statusBadge, statusStyle]}>
              <View style={styles.statusDot} />

              <Text style={styles.statusText}>
                {getJobStatusLabel(job.status)}
              </Text>
            </View>

            {job.priority ? (
              <View
                style={[
                  styles.priorityBadge,
                  priorityStyle
                ]}
              >
                <Ionicons
                  name="alert-circle"
                  size={15}
                  color={isUrgent ? "#C62836" : "#087653"}
                />

                <Text
                  style={[
                    styles.priorityText,
                    isUrgent
                      ? styles.priorityTextUrgent
                      : styles.priorityTextNormal
                  ]}
                >
                  {job.priority.toUpperCase()}
                </Text>
              </View>
            ) : null}
          </View>
        </View>
        {queuedActions.length > 0 ? (
          <View style={styles.pendingActionBanner}>
            <Text style={styles.pendingActionTitle}>
              Pending job actions
            </Text>

            <Text style={styles.pendingActionText}>
              These actions are saved locally and have not all been
              confirmed by the server.
            </Text>

            {queuedActions.map((item) => (
              <Text
                key={item.id}
                style={styles.pendingActionDetail}
              >
                {item.action.replace(/-/g, " ")} —{" "}
                {item.status.toUpperCase()}
                {item.lastError ? `: ${item.lastError}` : ""}
              </Text>
            ))}
          </View>
        ) : null}
        {dataSource === "cache" ? (
          <View style={styles.offlineBanner}>
            <Ionicons
              name="cloud-offline-outline"
              size={23}
              color="#92400E"
            />

            <View style={styles.offlineBannerContent}>
              <Text style={styles.offlineBannerTitle}>
                Saved offline details — may be outdated
              </Text>

              <Text style={styles.offlineBannerText}>
                {formatCachedTimestamp(cachedAt)} Reconnect and refresh to confirm the current job status. Job actions are disabled until the server confirms this job.
              </Text>
            </View>
          </View>
        ) : null}

        {/* Job information */}
        <View style={styles.sectionHeading}>
          <View>
            <Text style={styles.sectionTitle}>
              Job details
            </Text>

            <Text style={styles.sectionSubtitle}>
              Information about this assignment
            </Text>
          </View>

          <View style={styles.sectionIcon}>
            <Ionicons
              name="document-text-outline"
              size={22}
              color="#087653"
            />
          </View>
        </View>

        <View style={styles.detailsCard}>
          {job.customer_name ? (
            <DetailRow
              icon="person-outline"
              label="Customer"
              value={job.customer_name}
            />
          ) : null}

          {job.address ? (
            <DetailRow
              icon="location-outline"
              label="Service location"
              value={job.address}
            />
          ) : null}

          {job.scheduled_at ? (
            <DetailRow
              icon="calendar-outline"
              label="Scheduled date"
              value={formatSchedule(job.scheduled_at)}
            />
          ) : null}

          {job.description ? (
            <View style={styles.descriptionSection}>
              <View style={styles.descriptionHeading}>
                <Ionicons
                  name="reader-outline"
                  size={19}
                  color="#087653"
                />

                <Text style={styles.detailLabel}>
                  Description
                </Text>
              </View>

              <Text style={styles.descriptionText}>
                {job.description}
              </Text>
            </View>
          ) : null}

          {!job.customer_name &&
          !job.address &&
          !job.scheduled_at &&
          !job.description ? (
            <Text style={styles.emptyDetails}>
              No additional job information is available.
            </Text>
          ) : null}
        </View>

        {/* Acceptance timer */}
        {assignedStatus === "ASSIGNED" ? (
          <View
            style={[
              styles.timerCard,
              acceptanceExpired && styles.timerCardExpired
            ]}
          >
            <View style={styles.timerIcon}>
              <Ionicons
                name="time-outline"
                size={25}
                color={acceptanceExpired ? "#B42332" : "#087653"}
              />
            </View>

            <View style={styles.timerContent}>
              <Text
                style={[
                  styles.timerTitle,
                  acceptanceExpired && styles.expiredText
                ]}
              >
                TIME TO ACCEPT
              </Text>

              <Text
                style={[
                  styles.timerValue,
                  acceptanceExpired && styles.expiredText
                ]}
              >
                {acceptanceRemainingSeconds === null
                  ? "--:--"
                  : acceptanceExpired
                    ? "EXPIRED"
                    : `${String(
                        Math.floor(acceptanceRemainingSeconds / 60)
                      ).padStart(2, "0")}:${String(
                        acceptanceRemainingSeconds % 60
                      ).padStart(2, "0")}`}
              </Text>

              <Text
                style={[
                  styles.timerMessage,
                  acceptanceExpired && styles.expiredText
                ]}
              >
                {acceptanceRemainingSeconds === null
                  ? "Assignment time unavailable. Refresh the job."
                  : acceptanceExpired
                    ? "The acceptance window has expired."
                    : "Accept the job before time runs out."}
              </Text>
            </View>
          </View>
        ) : null}


        {/* Error message */}
        {error ? (
          <View style={styles.errorCard}>
            <Ionicons
              name="alert-circle-outline"
              size={22}
              color="#B42332"
            />

            <View style={styles.errorContent}>
              <Text
                accessibilityRole="alert"
                style={styles.errorText}
              >
                {error}
              </Text>

              <Pressable
                accessibilityRole="button"
                onPress={() => void loadJob()}
              >
                <Text style={styles.retryText}>
                  Refresh job details
                </Text>
              </Pressable>
            </View>
          </View>
        ) : null}

        {/* Rejection form */}
        {isRejectModalVisible ? (
          <View style={styles.rejectForm}>
            <View style={styles.rejectHeading}>
              <View style={styles.rejectIcon}>
                <Ionicons
                  name="close-circle-outline"
                  size={23}
                  color="#B42332"
                />
              </View>

              <View style={styles.rejectHeadingText}>
                <Text style={styles.rejectTitle}>
                  Reject this job
                </Text>

                <Text style={styles.rejectSubtitle}>
                  Explain why you cannot accept this assignment.
                </Text>
              </View>
            </View>

            <TextInput
              accessibilityLabel="Job rejection reason"
              value={rejectionReason}
              onChangeText={setRejectionReason}
              placeholder="Enter your reason (at least 10 characters)"
              placeholderTextColor="#91A09A"
              multiline
              maxLength={1000}
              textAlignVertical="top"
              style={styles.rejectionInput}
            />

            <Text style={styles.characterHint}>
              {rejectionReason.trim().length}/1000 characters
            </Text>

            <Pressable
              accessibilityRole="button"
              disabled={activeAction !== null}
              onPress={() => {
                const reason = rejectionReason.trim();

                if (reason.length < 10) {
                  Alert.alert(
                    "Reason required",
                    "Please enter at least 10 characters."
                  );
                  return;
                }

                setIsRejectModalVisible(false);
                void submitJobAction("reject", { reason });
              }}
              style={({ pressed }) => [
                styles.confirmRejectButton,
                pressed && styles.pressed,
                activeAction !== null && styles.buttonDisabled
              ]}
            >
              {activeAction === "reject" ? (
                <ActivityIndicator color="#FFFFFF" />
              ) : (
                <Text style={styles.actionButtonText}>
                  Confirm Rejection
                </Text>
              )}
            </Pressable>

            <Pressable
              accessibilityRole="button"
              onPress={() => setIsRejectModalVisible(false)}
              style={styles.cancelButton}
            >
              <Text style={styles.cancelButtonText}>
                Cancel
              </Text>
            </Pressable>
          </View>
        ) : null}

        {/* Job actions */}
        <View style={styles.actionsSection}>
          <Text style={styles.sectionTitle}>
            Available actions
          </Text>

          <Text style={styles.sectionSubtitle}>
            Update the job as you complete each stage.
          </Text>

          {[
            "EN_ROUTE",
            "ON_SITE",
            "IN_PROGRESS",
            "PAUSED"
          ].includes(assignedStatus) ? (
            <Pressable
              key="live-map"
              accessibilityRole="button"
              accessibilityLabel="Open live route map"
              disabled={activeAction !== null || dataSource !== "server"}
              onPress={() => {
                router.push({
                  pathname: "/(app)/jobs/[jobId]/live-map",
                  params: { jobId: String(job.id) }
                });
              }}
              style={({ pressed }) => [
                styles.actionButton,
                pressed && styles.pressed,
                (activeAction !== null || dataSource !== "server") &&
                  styles.buttonDisabled
              ]}
            >
              <Ionicons
                name="map-outline"
                size={22}
                color="#FFFFFF"
              />

              <Text style={styles.actionButtonText}>
                Live Map
              </Text>

              <Ionicons
                name="arrow-forward"
                size={19}
                color="#FFFFFF"
              />
            </Pressable>
          ) : null}

          {availableActions.length > 0 ? (
            availableActions.map(({ action, label }) => {
              const actionIcons: Record<string, IconName> = {
                accept: "checkmark-circle-outline",
                reject: "close-circle-outline",
                "en-route": "navigate-outline",
                en_route: "navigate-outline",
                enroute: "navigate-outline",
                "on-site": "location-outline",
                on_site: "location-outline",
                complete: "checkmark-done-circle-outline"
              };

              const isReject = action === "reject";
              const canQueueOfflineAction =
                isOffline &&
                action !== "reject" &&
                action !== "complete";
              const offlineBlockedAction =
                isOffline &&
                (action === "reject" || action === "complete");
              const cannotUseCachedData =
                dataSource !== "server" &&
                !canQueueOfflineAction;

              return (
                <Pressable
                  key={action}
                  accessibilityRole="button"
                  disabled={
                    activeAction !== null ||
                    cannotUseCachedData ||
                    offlineBlockedAction ||
                    (action === "accept" && acceptanceExpired)
                  }
                  onPress={() => void handleAction(action)}
                  style={({ pressed }) => [
                    styles.actionButton,
                    isReject && styles.rejectButton,
                    action === "complete" && styles.completeButton,
                    pressed && styles.pressed,
                    (activeAction !== null ||
                      cannotUseCachedData ||
                      offlineBlockedAction) &&
                      styles.buttonDisabled,
                    action === "accept" &&
                      acceptanceExpired &&
                      styles.buttonDisabled
                  ]}
                >
                  {activeAction === action ? (
                    <ActivityIndicator color="#FFFFFF" />
                  ) : (
                    <>
                      <Ionicons
                        name={actionIcons[action] ?? "construct-outline"}
                        size={22}
                        color="#FFFFFF"
                      />

                      <Text style={styles.actionButtonText}>
                        {label}
                      </Text>

                      <Ionicons
                        name="arrow-forward"
                        size={19}
                        color="#FFFFFF"
                      />
                    </>
                  )}
                </Pressable>
              );
            })
          ) : (
            <View style={styles.noActionsCard}>
              <Ionicons
                name="checkmark-circle-outline"
                size={25}
                color="#087653"
              />

              <Text style={styles.noActions}>
                No actions are available for this job status.
              </Text>
            </View>
          )}
        </View>

        <Text style={styles.footerText}>
          FieldOps Commander · Technician workspace
        </Text>
      </ScrollView>
    </View>
  );
}

function formatSchedule(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  });
}

interface DetailRowProps {
  icon: IconName;
  label: string;
  value: string;
}

function DetailRow({
  icon,
  label,
  value
}: DetailRowProps) {
  return (
    <View style={styles.detailRow}>
      <View style={styles.detailIcon}>
        <Ionicons
          name={icon}
          size={21}
          color="#087653"
        />
      </View>

      <View style={styles.detailContent}>
        <Text style={styles.detailLabel}>
          {label}
        </Text>

        <Text style={styles.detailValue}>
          {value}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#F3F8F6"
  },

  scroll: {
    flex: 1
  },

  content: {
    paddingBottom: 30
  },

  /* Header */

  hero: {
    backgroundColor: "#00513D",
    paddingHorizontal: 20,
    paddingTop: 22,
    paddingBottom: 25,
    borderBottomLeftRadius: 27,
    borderBottomRightRadius: 27
  },

  headerRow: {
    flexDirection: "row",
    alignItems: "center",
    marginBottom: 24
  },

  backButton: {
    width: 43,
    height: 43,
    borderRadius: 15,
    backgroundColor: "rgba(255,255,255,0.13)",
    alignItems: "center",
    justifyContent: "center"
  },

  headerReference: {
    flex: 1,
    marginLeft: 12
  },

  headerEyebrow: {
    color: "#A8DCC5",
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 1.5
  },

  headerJobNumber: {
    color: "#FFFFFF",
    fontSize: 16,
    fontWeight: "800",
    marginTop: 3
  },

  headerDecoration: {
    width: 43,
    height: 43,
    borderRadius: 15,
    backgroundColor: "rgba(255,255,255,0.10)",
    alignItems: "center",
    justifyContent: "center"
  },

  jobTitle: {
    color: "#FFFFFF",
    fontSize: 29,
    lineHeight: 36,
    fontWeight: "800",
    letterSpacing: -0.5
  },

  headerBottomRow: {
    flexDirection: "row",
    alignItems: "center",
    flexWrap: "wrap",
    gap: 9,
    marginTop: 16
  },

  statusBadge: {
    alignSelf: "flex-start",
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    borderRadius: 20,
    paddingHorizontal: 12,
    paddingVertical: 9
  },

  statusActive: {
    backgroundColor: "#D9F5E6"
  },

  statusWaiting: {
    backgroundColor: "#FFF0CB"
  },

  statusCompleted: {
    backgroundColor: "#CFF4DF"
  },

  statusDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: "#087653"
  },

  statusText: {
    color: "#075C40",
    fontSize: 11,
    fontWeight: "800"
  },

  priorityBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    borderRadius: 20,
    paddingHorizontal: 11,
    paddingVertical: 9
  },

  priorityUrgent: {
    backgroundColor: "#FFE5E8"
  },

  priorityNormal: {
    backgroundColor: "#E4F4EB"
  },

  priorityText: {
    fontSize: 11,
    fontWeight: "800"
  },

  priorityTextUrgent: {
    color: "#B42332"
  },

  priorityTextNormal: {
    color: "#087653"
  },

  pendingActionBanner: {
    marginHorizontal: 15,
    marginTop: 16,
    padding: 14,
    borderRadius: 16,
    backgroundColor: "#E5F6EC",
    borderWidth: 1,
    borderColor: "#BDE8CF"
  },

  pendingActionTitle: {
    color: "#075C40",
    fontSize: 14,
    fontWeight: "800"
  },

  pendingActionText: {
    color: "#426C57",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 5
  },

  pendingActionDetail: {
    color: "#075C40",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 7,
    textTransform: "capitalize"
  },

  offlineBanner: {
    marginHorizontal: 15,
    marginTop: 16,
    padding: 14,
    borderRadius: 16,
    backgroundColor: "#FFF4D7",
    borderWidth: 1,
    borderColor: "#F2D790",
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10
  },

  offlineBannerContent: {
    flex: 1
  },

  offlineBannerTitle: {
    color: "#92400E",
    fontSize: 13,
    lineHeight: 19,
    fontWeight: "800"
  },

  offlineBannerText: {
    color: "#854D0E",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 4
  },

  /* Section headings */

  sectionHeading: {
    marginTop: 25,
    marginBottom: 13,
    paddingHorizontal: 19,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between"
  },

  sectionTitle: {
    color: "#16372A",
    fontSize: 19,
    fontWeight: "800"
  },

  sectionSubtitle: {
    color: "#7B8C84",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 4
  },

  sectionIcon: {
    width: 43,
    height: 43,
    borderRadius: 14,
    backgroundColor: "#E2F4EA",
    alignItems: "center",
    justifyContent: "center"
  },

  /* Details card */

  detailsCard: {
    marginHorizontal: 15,
    paddingHorizontal: 15,
    paddingVertical: 5,
    backgroundColor: "#FFFFFF",
    borderRadius: 21,
    borderWidth: 1,
    borderColor: "#E4EEE9",
    shadowColor: "#164E3B",
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.055,
    shadowRadius: 10,
    elevation: 2
  },

  detailRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    paddingVertical: 15,
    gap: 12,
    borderBottomWidth: 1,
    borderBottomColor: "#EEF3F0"
  },

  detailIcon: {
    width: 42,
    height: 42,
    borderRadius: 14,
    backgroundColor: "#EAF6F0",
    alignItems: "center",
    justifyContent: "center"
  },

  detailContent: {
    flex: 1,
    paddingTop: 2
  },

  detailLabel: {
    color: "#7A8B82",
    fontSize: 12,
    lineHeight: 17,
    marginBottom: 4
  },

  detailValue: {
    color: "#18372B",
    fontSize: 14,
    lineHeight: 21,
    fontWeight: "600"
  },

  descriptionSection: {
    paddingVertical: 16
  },

  descriptionHeading: {
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
    marginBottom: 9
  },

  descriptionText: {
    color: "#42584D",
    fontSize: 14,
    lineHeight: 22
  },

  emptyDetails: {
    color: "#7A8B82",
    fontSize: 13,
    lineHeight: 20,
    paddingVertical: 17
  },

  /* Acceptance timer */

  timerCard: {
    marginHorizontal: 15,
    marginTop: 17,
    backgroundColor: "#E5F6EC",
    borderWidth: 1,
    borderColor: "#BDE8CF",
    borderRadius: 20,
    padding: 17,
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 13
  },

  timerCardExpired: {
    backgroundColor: "#FFF0F0",
    borderColor: "#F4C5C9"
  },

  timerIcon: {
    width: 46,
    height: 46,
    borderRadius: 15,
    backgroundColor: "#FFFFFF",
    alignItems: "center",
    justifyContent: "center"
  },

  timerContent: {
    flex: 1
  },

  timerTitle: {
    color: "#087653",
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 1.2
  },

  timerValue: {
    color: "#075C40",
    fontSize: 29,
    fontWeight: "900",
    fontVariant: ["tabular-nums"],
    marginTop: 5
  },

  timerMessage: {
    color: "#426C57",
    fontSize: 12,
    lineHeight: 19,
    marginTop: 3
  },

  expiredText: {
    color: "#B42332"
  },


  /* Error card */

  errorCard: {
    marginHorizontal: 15,
    marginTop: 16,
    padding: 14,
    borderRadius: 16,
    backgroundColor: "#FFF0F0",
    borderWidth: 1,
    borderColor: "#F4C5C9",
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10
  },

  errorContent: {
    flex: 1
  },

  errorText: {
    color: "#A61B2B",
    fontSize: 13,
    lineHeight: 20
  },

  retryText: {
    color: "#087653",
    fontSize: 13,
    fontWeight: "800",
    marginTop: 9
  },

  /* Rejection form */

  rejectForm: {
    marginHorizontal: 15,
    marginTop: 20,
    padding: 17,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#F2D1D4",
    borderRadius: 20
  },

  rejectHeading: {
    flexDirection: "row",
    alignItems: "center",
    gap: 11,
    marginBottom: 15
  },

  rejectIcon: {
    width: 43,
    height: 43,
    borderRadius: 14,
    backgroundColor: "#FFE9EB",
    alignItems: "center",
    justifyContent: "center"
  },

  rejectHeadingText: {
    flex: 1
  },

  rejectTitle: {
    color: "#92212B",
    fontSize: 17,
    fontWeight: "800"
  },

  rejectSubtitle: {
    color: "#8E7779",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 3
  },

  rejectionInput: {
    minHeight: 115,
    borderWidth: 1,
    borderColor: "#E2E8E4",
    borderRadius: 14,
    padding: 13,
    color: "#18372B",
    fontSize: 14,
    lineHeight: 21,
    backgroundColor: "#FAFCFB"
  },

  characterHint: {
    color: "#87968D",
    fontSize: 11,
    textAlign: "right",
    marginTop: 7,
    marginBottom: 12
  },

  confirmRejectButton: {
    minHeight: 52,
    backgroundColor: "#B42332",
    borderRadius: 15,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 15
  },

  cancelButton: {
    minHeight: 47,
    marginTop: 9,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#E0E7E2",
    alignItems: "center",
    justifyContent: "center"
  },

  cancelButtonText: {
    color: "#53675B",
    fontSize: 14,
    fontWeight: "700"
  },

  /* Job actions */

  actionsSection: {
    marginTop: 25,
    paddingHorizontal: 15
  },

  actionButton: {
    minHeight: 59,
    marginTop: 12,
    paddingHorizontal: 17,
    borderRadius: 17,
    backgroundColor: "#087653",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 11
  },

  rejectButton: {
    backgroundColor: "#B42332"
  },

  completeButton: {
    backgroundColor: "#064E3B"
  },

  actionButtonText: {
    flex: 1,
    color: "#FFFFFF",
    fontSize: 14,
    fontWeight: "800"
  },

  noActionsCard: {
    marginTop: 13,
    borderRadius: 17,
    padding: 17,
    backgroundColor: "#E5F6EC",
    flexDirection: "row",
    alignItems: "center",
    gap: 11
  },

  noActions: {
    flex: 1,
    color: "#426C57",
    fontSize: 13,
    lineHeight: 20
  },

  /* Shared */

  pressed: {
    opacity: 0.8
  },

  buttonDisabled: {
    opacity: 0.5
  },

  footerText: {
    color: "#91A098",
    fontSize: 11,
    textAlign: "center",
    marginTop: 27,
    marginBottom: 10
  }
});