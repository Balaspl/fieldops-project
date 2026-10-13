
import { useCallback, useEffect, useState } from "react";
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
import { useLocalSearchParams, useRouter } from "expo-router";
import {
  getTechnicianJob,
  type TechnicianJob
} from "../../../src/api/technician";

import {
  performTechnicianJobAction,
  type TechnicianJobAction
} from "../../../src/api/jobActions";

import {
  ErrorState,
  LoadingState
} from "../../../src/components/ScreenState";

import {
  getJobActionOptions,
  getJobStatusLabel,
  normalizeJobStatus
} from "../../../src/utils/jobStatus";

export default function JobDetailScreen() {
  const router = useRouter();
  const { jobId } = useLocalSearchParams<{ jobId: string }>();

  const [job, setJob] = useState<TechnicianJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeAction, setActiveAction] =
    useState<TechnicianJobAction | null>(null);
  const [error, setError] = useState<string | null>(null);
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

    setLoading(true);
    setError(null);

    try {
      const result = await getTechnicianJob(jobId);
      setJob(result);
    } catch {
      setError(
        "Unable to load this job. Check your connection and try again."
      );
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    void loadJob();
  }, [loadJob]);

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

  async function handleAction(action: TechnicianJobAction) {
    if (!job || activeAction) {
      return;
    }

    if (action === "reject") {
      setRejectionReason("");
      setIsRejectModalVisible(true);
      setError(null);
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

    setActiveAction(action);
    setError(null);

    try {
      const response = await performTechnicianJobAction(
        job.id,
        action,
        payload
      );

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

      Alert.alert("Job updated", "The action was submitted to FieldOps.");
    } catch {
      setError(
        "The job action could not be completed. Refresh the job and try again."
      );
    } finally {
      setActiveAction(null);
    }
  }

  function openExpenses() {
    if (!job) {
      return;
    }

    router.push({
      pathname: "/(app)/jobs/[jobId]/expenses",
      params: { jobId: String(job.id) }
    });
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

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
    >
      <Pressable
        accessibilityRole="button"
        onPress={() => router.back()}
        style={styles.backButton}
      >
        <Text style={styles.backText}>‹  Back</Text>
      </Pressable>

      <Text style={styles.eyebrow}>
        JOB #{job.job_number ?? String(job.id)}
      </Text>

      <Text style={styles.title}>
        {job.title || "Service job"}
      </Text>

      <View style={styles.statusCard}>
        <Text style={styles.label}>Current status</Text>
        <Text style={styles.status}>
          {getJobStatusLabel(job.status)}
        </Text>
      </View>

      <View style={styles.detailsCard}>
        <Text style={styles.sectionTitle}>Job information</Text>

        {job.description ? (
          <DetailRow label="Description" value={job.description} />
        ) : null}

        {job.priority ? (
          <DetailRow label="Priority" value={job.priority} />
        ) : null}

        {job.customer_name ? (
          <DetailRow label="Customer" value={job.customer_name} />
        ) : null}

        {job.address ? (
          <DetailRow label="Address" value={job.address} />
        ) : null}

        {job.scheduled_at ? (
          <DetailRow
            label="Scheduled at"
            value={new Date(job.scheduled_at).toLocaleString()}
          />
        ) : null}
      </View>

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Submit an expense for this job"
        onPress={openExpenses}
        style={({ pressed }) => [
          styles.expenseButton,
          pressed && styles.buttonPressed
        ]}
      >
        <Text style={styles.expenseButtonText}>
          Submit Job Expense
        </Text>
      </Pressable>

      {error ? (
        <Text accessibilityRole="alert" style={styles.error}>
          {error}
        </Text>
      ) : null}

      {isRejectModalVisible ? (
        <View style={styles.rejectForm}>
          <Text style={styles.sectionTitle}>Reject this job</Text>

          <Text style={styles.label}>
            Please explain why you cannot accept this job.
          </Text>

          <TextInput
            accessibilityLabel="Job rejection reason"
            value={rejectionReason}
            onChangeText={setRejectionReason}
            placeholder="Enter your reason (at least 10 characters)"
            placeholderTextColor="#94A3B8"
            multiline
            maxLength={1000}
            textAlignVertical="top"
            style={styles.rejectionInput}
          />

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
            style={styles.actionButton}
          >
            <Text style={styles.actionButtonText}>Confirm Rejection</Text>
          </Pressable>

          <Pressable
            accessibilityRole="button"
            onPress={() => setIsRejectModalVisible(false)}
            style={styles.cancelButton}
          >
            <Text style={styles.cancelButtonText}>Cancel</Text>
          </Pressable>
        </View>
      ) : null}

      {assignedStatus === "ASSIGNED" ? (
        <View
          style={{
            marginTop: 20,
            padding: 16,
            borderRadius: 12,
            backgroundColor: acceptanceExpired ? "#FEE2E2" : "#ECFDF5",
            borderWidth: 1,
            borderColor: acceptanceExpired ? "#FCA5A5" : "#A7F3D0"
          }}
        >
          <Text
            style={{
              fontSize: 12,
              fontWeight: "700",
              color: acceptanceExpired ? "#991B1B" : "#047857"
            }}
          >
            TIME TO ACCEPT
          </Text>

          <Text
            style={{
              marginTop: 6,
              fontSize: 28,
              fontWeight: "800",
              fontVariant: ["tabular-nums"],
              color: acceptanceExpired ? "#991B1B" : "#065F46"
            }}
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
            style={{
              marginTop: 4,
              fontSize: 12,
              color: acceptanceExpired ? "#991B1B" : "#047857"
            }}
          >
            {acceptanceRemainingSeconds === null
              ? "Assignment time unavailable. Refresh the job."
              : acceptanceExpired
                ? "The acceptance window has expired."
                : "Please accept the job before time runs out."}
          </Text>
        </View>
      ) : null}

      {availableActions.length > 0 ? (
        <View style={styles.actionsSection}>
          <Text style={styles.sectionTitle}>Job actions</Text>

          {availableActions.map(({ action, label }) => (
            <Pressable
              key={action}
              accessibilityRole="button"
              disabled={
                activeAction !== null ||
                (action === "accept" && acceptanceExpired)
              }
              onPress={() => void handleAction(action)}
              style={({ pressed }) => [
                styles.actionButton,
                action === "reject" && styles.rejectButton,
                pressed && styles.buttonPressed,
                activeAction !== null && styles.buttonDisabled
              ]}
            >
              {activeAction === action ? (
                <ActivityIndicator color="#FFFFFF" />
              ) : (
                <Text style={styles.actionButtonText}>{label}</Text>
              )}
            </Pressable>
          ))}
        </View>
      ) : (
        <Text style={styles.noActions}>
          No actions are available for this job status.
        </Text>
      )}
    </ScrollView>
  );
}

interface DetailRowProps {
  label: string;
  value: string;
}

function DetailRow({ label, value }: DetailRowProps) {
  return (
    <View style={styles.detailRow}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.value}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#F8FAFC"
  },
  content: {
    padding: 20,
    paddingTop: 40,
    paddingBottom: 36
  },
  backButton: {
    alignSelf: "flex-start",
    paddingVertical: 10,
    marginBottom: 20
  },
  backText: {
    color: "#217346",
    fontSize: 15,
    fontWeight: "700"
  },
  eyebrow: {
    color: "#64748B",
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 1,
    marginBottom: 8
  },
  title: {
    color: "#0F172A",
    fontSize: 26,
    fontWeight: "800",
    marginBottom: 22
  },
  statusCard: {
    backgroundColor: "#E5F4E9",
    padding: 20,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: "#CDE8D4",
    marginBottom: 20
  },
  label: {
    color: "#64748B",
    fontSize: 13,
    marginBottom: 6
  },
  status: {
    color: "#217346",
    fontSize: 18,
    fontWeight: "800"
  },
  detailsCard: {
    backgroundColor: "#FFFFFF",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#E2E8F0",
    padding: 18
  },
  sectionTitle: {
    color: "#0F172A",
    fontSize: 18,
    fontWeight: "700",
    marginBottom: 12
  },
  detailRow: {
    borderTopWidth: 1,
    borderTopColor: "#F1F5F9",
    paddingVertical: 13
  },
  value: {
    color: "#0F172A",
    fontSize: 15,
    lineHeight: 22
  },
  expenseButton: {
    minHeight: 54,
    justifyContent: "center",
    alignItems: "center",
    backgroundColor: "#217346",
    borderRadius: 16,
    paddingHorizontal: 18,
    marginTop: 20
  },
  expenseButtonText: {
    color: "#FFFFFF",
    fontSize: 15,
    fontWeight: "700"
  },
  actionsSection: {
    marginTop: 26
  },
  actionButton: {
    minHeight: 54,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#217346",
    borderRadius: 16,
    paddingHorizontal: 18,
    marginBottom: 12
  },
  rejectButton: {
    backgroundColor: "#B91C1C"
  },
  rejectForm: {
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#FECACA",
    borderRadius: 16,
    padding: 18,
    marginTop: 20
  },
  rejectionInput: {
    minHeight: 120,
    borderWidth: 1,
    borderColor: "#CBD5E1",
    borderRadius: 12,
    padding: 12,
    color: "#0F172A",
    fontSize: 15,
    marginTop: 8,
    marginBottom: 16
  },
  cancelButton: {
    minHeight: 48,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#CBD5E1",
    marginTop: 4
  },
  cancelButtonText: {
    color: "#475569",
    fontSize: 15,
    fontWeight: "700"
  },
  buttonPressed: {
    opacity: 0.85
  },
  buttonDisabled: {
    opacity: 0.55
  },
  actionButtonText: {
    color: "#FFFFFF",
    fontSize: 15,
    fontWeight: "700"
  },
  error: {
    color: "#B91C1C",
    fontSize: 14,
    lineHeight: 21,
    marginTop: 18
  },
  noActions: {
    color: "#64748B",
    fontSize: 14,
    lineHeight: 21,
    marginTop: 24,
    textAlign: "center"
  }
});
