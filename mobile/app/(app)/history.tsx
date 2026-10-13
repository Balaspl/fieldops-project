
import { useCallback, useEffect, useState } from "react";
import {
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View
} from "react-native";
import { useRouter } from "expo-router";
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

function normalizeJobs(
  response: TechnicianJobCollection
): TechnicianJob[] {
  return Array.isArray(response) ? response : response.items;
}

export default function JobHistoryScreen() {
  const router = useRouter();

  const [jobs, setJobs] = useState<TechnicianJob[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(async (refresh = false) => {
    if (refresh) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }

    setError(null);

    try {
      const response = await getTechnicianJobHistory();
      setJobs(normalizeJobs(response));
    } catch {
      setError("Unable to load job history. Check your connection and try again.");
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  if (isLoading) {
    return <LoadingState label="Loading job history..." />;
  }

  if (error && jobs.length === 0) {
    return (
      <ErrorState
        title="Job history unavailable"
        message={error}
        onRetry={() => void loadHistory()}
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
            message="Your previous jobs will appear here."
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
