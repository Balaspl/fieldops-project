
import { useCallback, useEffect, useState } from "react";
import {
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  View
} from "react-native";
import {
  getTechnicianNotifications,
  type NotificationCollection,
  type TechnicianNotification
} from "../../src/api/notifications";
import {
  EmptyState,
  ErrorState,
  LoadingState
} from "../../src/components/ScreenState";

function normalizeNotifications(
  response: NotificationCollection
): TechnicianNotification[] {
  if (Array.isArray(response)) {
    return response;
  }

  if (
    response &&
    typeof response === "object" &&
    Array.isArray(response.items)
  ) {
    return response.items;
  }

  return [];
}

function formatDate(value?: string): string {
  if (!value) {
    return "Date unavailable";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Date unavailable";
  }

  return date.toLocaleString();
}

export default function NotificationsScreen() {
  const [notifications, setNotifications] = useState<
    TechnicianNotification[]
  >([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadNotifications = useCallback(async (refresh = false) => {
    if (refresh) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }

    setError(null);

    try {
      const response = await getTechnicianNotifications();
      setNotifications(normalizeNotifications(response));
    } catch {
      setError("Unable to load notifications. Check your connection and try again.");
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadNotifications();
  }, [loadNotifications]);

  if (isLoading) {
    return <LoadingState label="Loading notifications..." />;
  }

  if (error && notifications.length === 0) {
    return (
      <ErrorState
        title="Notifications unavailable"
        message={error}
        onRetry={() => void loadNotifications()}
      />
    );
  }

  return (
    <View style={styles.screen}>
      <View style={styles.header}>
        <Text style={styles.title}>Notifications</Text>
        <Text style={styles.subtitle}>
          Updates from your FieldOps workspace
        </Text>
      </View>

      {error ? (
        <Text style={styles.warning}>
          Refresh failed. Pull down to try again.
        </Text>
      ) : null}

      <FlatList
        data={notifications}
        keyExtractor={(item) => String(item.id)}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={() => void loadNotifications(true)}
          />
        }
        contentContainerStyle={
          notifications.length === 0 ? styles.emptyList : styles.list
        }
        ListEmptyComponent={
          <EmptyState
            title="No notifications"
            message="New updates will appear here."
            onRetry={() => void loadNotifications(true)}
          />
        }
        renderItem={({ item }) => {
          const isRead = item.read ?? item.is_read ?? false;
          const message = item.message ?? item.body;

          return (
            <View
              style={[
                styles.card,
                !isRead && styles.unreadCard
              ]}
            >
              <View style={styles.row}>
                <View
                  style={[
                    styles.dot,
                    isRead && styles.readDot
                  ]}
                />
                <Text style={styles.notificationTitle}>
                  {item.title || "FieldOps update"}
                </Text>
              </View>

              {message ? (
                <Text style={styles.message}>{message}</Text>
              ) : null}

              <Text style={styles.date}>
                {formatDate(item.created_at)}
              </Text>
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
  unreadCard: {
    borderColor: "#93C5FD",
    backgroundColor: "#EFF6FF"
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 9
  },
  dot: {
    width: 9,
    height: 9,
    borderRadius: 5,
    backgroundColor: "#2563EB"
  },
  readDot: {
    backgroundColor: "#CBD5E1"
  },
  notificationTitle: {
    color: "#0F172A",
    fontSize: 16,
    fontWeight: "700",
    flex: 1
  },
  message: {
    color: "#475569",
    fontSize: 14,
    lineHeight: 21,
    marginTop: 10
  },
  date: {
    color: "#64748B",
    fontSize: 12,
    marginTop: 12
  },
  warning: {
    color: "#92400E",
    backgroundColor: "#FEF3C7",
    marginHorizontal: 16,
    marginBottom: 12,
    padding: 12,
    borderRadius: 8
  }
});
