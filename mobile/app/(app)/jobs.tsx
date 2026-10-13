
import { useCallback, useState } from "react";
import {
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import {
  getTechnicianJobs,
  type TechnicianJob,
  type TechnicianJobCollection
} from "../../src/api/technician";
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

function getErrorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Unable to load jobs. Please try again.";
}

export default function JobsScreen() {
  const router = useRouter();

  const [jobs, setJobs] = useState<TechnicianJob[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadJobs = useCallback(async (refresh = false) => {
    if (refresh) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }

    setError(null);

    try {
      const response = await getTechnicianJobs();
      setJobs(normalizeJobs(response));
    } catch (loadError: unknown) {
      setError(getErrorMessage(loadError));
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void loadJobs();
    }, [loadJobs])
  );

  if (isLoading) {
    return <LoadingState label="Loading your jobs..." />;
  }

  if (error && jobs.length === 0) {
    return (
      <ErrorState
        title="Couldn't load jobs"
        message={error}
        onRetry={() => void loadJobs()}
      />
    );
  }

  return (
    <View style={styles.screen}>
      <View style={styles.header}>
        <Text style={styles.title}>My Jobs</Text>
        <Text style={styles.subtitle}>
          Jobs assigned to your technician account
        </Text>
      </View>

      {error ? (
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

      <FlatList
        data={jobs}
        keyExtractor={(job) => String(job.id)}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={() => void loadJobs(true)}
          />
        }
        contentContainerStyle={
          jobs.length === 0 ? styles.emptyList : styles.list
        }
        ListEmptyComponent={
          <EmptyState
            title="No jobs assigned"
            message="Newly assigned jobs will appear here."
            onRetry={() => void loadJobs(true)}
          />
        }
        renderItem={({ item }) => (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`Open job ${item.job_number ?? item.id}`}
            onPress={() =>
              router.push({
                pathname: "/(app)/jobs/[jobId]",
                params: { jobId: String(item.id) }
              })
            }
            style={({ pressed }) => [
              styles.jobCard,
              pressed && styles.jobCardPressed
            ]}
          >
            <View style={styles.jobTopRow}>
              <Text style={styles.jobNumber}>
                Job #{item.job_number ?? String(item.id)}
              </Text>

              <View style={styles.statusBadge}>
                <Text style={styles.statusText}>
                  {item.status.replace(/_/g, " ")}
                </Text>
              </View>
            </View>

            <Text style={styles.jobTitle}>
              {item.title || "Service job"}
            </Text>

            {item.customer_name ? (
              <Text style={styles.detail}>
                Customer: {item.customer_name}
              </Text>
            ) : null}

            {item.address ? (
              <Text style={styles.detail}>
                Location: {item.address}
              </Text>
            ) : null}

            {item.priority ? (
              <Text style={styles.priority}>
                Priority: {item.priority}
              </Text>
            ) : null}

            <Text style={styles.openHint}>
              Tap to view job details →
            </Text>
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
  jobCard: {
    backgroundColor: "#FFFFFF",
    borderColor: "#E2E8F0",
    borderWidth: 1,
    borderRadius: 12,
    padding: 16,
    marginBottom: 12
  },
  jobCardPressed: {
    backgroundColor: "#EFF6FF",
    borderColor: "#93C5FD"
  },
  jobTopRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    flexWrap: "wrap",
    gap: 8
  },
  jobNumber: {
    color: "#1D4ED8",
    fontSize: 13,
    fontWeight: "700"
  },
  statusBadge: {
    backgroundColor: "#DBEAFE",
    borderRadius: 6,
    paddingHorizontal: 9,
    paddingVertical: 5
  },
  statusText: {
    color: "#1E40AF",
    fontSize: 11,
    fontWeight: "700",
    textTransform: "capitalize"
  },
  jobTitle: {
    color: "#0F172A",
    fontSize: 17,
    fontWeight: "700",
    marginTop: 12
  },
  detail: {
    color: "#475569",
    fontSize: 13,
    lineHeight: 20,
    marginTop: 7
  },
  priority: {
    color: "#92400E",
    fontSize: 13,
    fontWeight: "600",
    marginTop: 9
  },
  openHint: {
    color: "#2563EB",
    fontSize: 13,
    fontWeight: "600",
    marginTop: 14
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
