import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import {
  dismissTechnicianNotification,
  getTechnicianNotifications,
  markAllTechnicianNotificationsRead,
  markTechnicianNotificationRead,
  type NotificationCollection,
  type TechnicianNotification
} from "../../src/api/notifications";
import {
  EmptyState,
  ErrorState,
  LoadingState
} from "../../src/components/ScreenState";

type NotificationFilter = "all" | "unread" | "read";

function normalizeNotifications(
  response: NotificationCollection
): TechnicianNotification[] {
  if (Array.isArray(response)) return response;
  return response && typeof response === "object" && Array.isArray(response.items)
    ? response.items
    : [];
}

function isNotificationRead(notification: TechnicianNotification): boolean {
  return notification.read ?? notification.is_read ?? false;
}

function formatDate(value?: string): string {
  if (!value) return "Date unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date unavailable";
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit"
  });
}

export default function NotificationsScreen() {
  const router = useRouter();
  const [notifications, setNotifications] = useState<TechnicianNotification[]>([]);
  const [filter, setFilter] = useState<NotificationFilter>("all");
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isMarkingAllRead, setIsMarkingAllRead] = useState(false);
  const [busyIds, setBusyIds] = useState<Set<string>>(new Set());
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isBulkDeleting, setIsBulkDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const unreadCount = notifications.filter((item) => !isNotificationRead(item)).length;

  const loadNotifications = useCallback(async (refresh = false) => {
    if (refresh) setIsRefreshing(true);
    else setIsLoading(true);
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

  const markNotificationRead = useCallback(async (notification: TechnicianNotification) => {
    if (isNotificationRead(notification)) return;
    try {
      await markTechnicianNotificationRead(notification.id);
      setNotifications((current) => current.map((item) =>
        String(item.id) === String(notification.id)
          ? { ...item, read: true, is_read: true }
          : item
      ));
    } catch {
      Alert.alert("Unable to update notification", "Please check your connection and try again.");
    }
  }, []);

  const dismissNotification = useCallback((notification: TechnicianNotification) => {
    Alert.alert(
      "Delete notification?",
      "This update will be removed from your notifications.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete",
          style: "destructive",
          onPress: async () => {
            const id = String(notification.id);
            setBusyIds((current) => new Set(current).add(id));
            try {
              await dismissTechnicianNotification(notification.id);
              setNotifications((current) => current.filter((item) => String(item.id) !== id));
            } catch {
              Alert.alert("Unable to delete notification", "Please check your connection and try again.");
            } finally {
              setBusyIds((current) => {
                const next = new Set(current);
                next.delete(id);
                return next;
              });
            }
          }
        }
      ]
    );
  }, []);

  const markAllRead = useCallback(async () => {
    if (unreadCount === 0 || isMarkingAllRead) return;
    setIsMarkingAllRead(true);
    try {
      await markAllTechnicianNotificationsRead();
      setNotifications((current) => current.map((item) => ({ ...item, read: true, is_read: true })));
    } catch {
      Alert.alert("Unable to update notifications", "Please check your connection and try again.");
    } finally {
      setIsMarkingAllRead(false);
    }
  }, [isMarkingAllRead, unreadCount]);

  useEffect(() => {
    void loadNotifications();
  }, [loadNotifications]);

  const filteredNotifications = useMemo(() => notifications.filter((item) => {
    if (filter === "unread") return !isNotificationRead(item);
    if (filter === "read") return isNotificationRead(item);
    return true;
  }), [filter, notifications]);
  const allVisibleSelected = filteredNotifications.length > 0 &&
    filteredNotifications.every((item) => selectedIds.has(String(item.id)));

  const toggleSelection = useCallback((notificationId: string | number) => {
    const id = String(notificationId);
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (allVisibleSelected) filteredNotifications.forEach((item) => next.delete(String(item.id)));
      else filteredNotifications.forEach((item) => next.add(String(item.id)));
      return next;
    });
  }, [allVisibleSelected, filteredNotifications]);

  const deleteSelected = useCallback(() => {
    const selected = notifications.filter((item) => selectedIds.has(String(item.id)));
    if (selected.length === 0 || isBulkDeleting) return;
    Alert.alert(
      "Delete selected notifications?",
      `${selected.length} ${selected.length === 1 ? "notification" : "notifications"} will be removed.`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete",
          style: "destructive",
          onPress: async () => {
            setIsBulkDeleting(true);
            const results = await Promise.allSettled(
              selected.map((item) => dismissTechnicianNotification(item.id))
            );
            const deletedIds = new Set(
              selected
                .filter((_item, index) => results[index]?.status === "fulfilled")
                .map((item) => String(item.id))
            );
            setNotifications((current) => current.filter((item) => !deletedIds.has(String(item.id))));
            setSelectedIds((current) => {
              const next = new Set(current);
              deletedIds.forEach((id) => next.delete(id));
              return next;
            });
            setIsBulkDeleting(false);
            if (deletedIds.size !== selected.length) {
              Alert.alert("Some notifications could not be deleted", "Please check your connection and try again.");
            }
          }
        }
      ]
    );
  }, [isBulkDeleting, notifications, selectedIds]);

  if (isLoading) return <LoadingState label="Loading notifications..." variant="list" />;
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
        <View style={styles.headerTop}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Back to dashboard"
            onPress={() => router.replace("/(app)/dashboard")}
            hitSlop={8}
            style={({ pressed }) => [styles.backButton, pressed && styles.pressed]}
          >
            <Ionicons name="arrow-back" size={20} color="#FFFFFF" />
          </Pressable>
          <View style={styles.headingCopy}>
            <Text style={styles.eyebrow}>FIELDOPS UPDATES</Text>
            <Text style={styles.title}>Notifications</Text>
          </View>
          <View style={styles.headerIcon}>
            <Ionicons name="notifications" size={22} color="#FFFFFF" />
          </View>
        </View>
        <Text style={styles.subtitle}>Stay on top of your latest job updates.</Text>
        <View style={styles.summaryRow}>
          <View style={styles.summaryDot} />
          <Text style={styles.summaryText}>
            {unreadCount === 0 ? "You're all caught up" : `${unreadCount} unread ${unreadCount === 1 ? "update" : "updates"}`}
          </Text>
          {unreadCount > 0 ? (
            <Pressable
              accessibilityRole="button"
              disabled={isMarkingAllRead}
              onPress={() => void markAllRead()}
              style={({ pressed }) => [styles.markAllButton, pressed && styles.pressed, isMarkingAllRead && styles.disabled]}
            >
              <Ionicons name="checkmark-done" size={15} color="#DDF5E8" />
              <Text style={styles.markAllText}>{isMarkingAllRead ? "Updating…" : "Mark all read"}</Text>
            </Pressable>
          ) : null}
        </View>
      </View>

      {error ? <Text style={styles.warning}>Refresh failed. Pull down to try again.</Text> : null}

      <View style={styles.selectionToolbar}>
        <Pressable
          accessibilityRole="button"
          accessibilityState={{ selected: allVisibleSelected }}
          onPress={toggleSelectAll}
          disabled={filteredNotifications.length === 0 || isBulkDeleting}
          style={({ pressed }) => [styles.selectAllButton, pressed && styles.pressed, filteredNotifications.length === 0 && styles.disabled]}
        >
          <Ionicons name={allVisibleSelected ? "checkbox" : "square-outline"} size={19} color="#087447" />
          <Text style={styles.selectAllText}>{allVisibleSelected ? "Deselect all" : "Select all"}</Text>
        </Pressable>
        {selectedIds.size > 0 ? (
          <View style={styles.selectionActions}>
            <Text style={styles.selectedCount}>{selectedIds.size} selected</Text>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Delete selected notifications"
              disabled={isBulkDeleting}
              onPress={deleteSelected}
              style={({ pressed }) => [styles.deleteSelectedButton, pressed && styles.pressed, isBulkDeleting && styles.disabled]}
            >
              <Ionicons name="trash-outline" size={16} color="#FFFFFF" />
              <Text style={styles.deleteSelectedText}>{isBulkDeleting ? "Deleting…" : "Delete"}</Text>
            </Pressable>
          </View>
        ) : null}
      </View>

      <View style={styles.filterBar}>
        {(["all", "unread", "read"] as const).map((value) => {
          const selected = filter === value;
          const label = value === "all" ? "All" : value === "unread" ? "Unread" : "Read";
          const count = value === "all"
            ? notifications.length
            : value === "unread"
              ? unreadCount
              : notifications.length - unreadCount;
          return (
            <Pressable
              key={value}
              accessibilityRole="button"
              accessibilityState={{ selected }}
              onPress={() => setFilter(value)}
              style={[styles.filterChip, selected && styles.filterChipSelected]}
            >
              <Text style={[styles.filterText, selected && styles.filterTextSelected]}>{label}</Text>
              <Text style={[styles.filterCount, selected && styles.filterCountSelected]}>{count}</Text>
            </Pressable>
          );
        })}
      </View>

      <FlatList
        data={filteredNotifications}
        keyExtractor={(item) => String(item.id)}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={() => void loadNotifications(true)}
            tintColor="#078A4D"
          />
        }
        contentContainerStyle={filteredNotifications.length === 0 ? styles.emptyList : styles.list}
        ListEmptyComponent={
          <EmptyState
            title={filter === "unread" ? "No unread updates" : filter === "read" ? "No read updates yet" : "No notifications"}
            message={filter === "all" ? "New updates will appear here." : "Try another filter to see your updates."}
            onRetry={() => void loadNotifications(true)}
          />
        }
        renderItem={({ item }) => {
          const isRead = isNotificationRead(item);
          const message = item.message ?? item.body;
          const isBusy = busyIds.has(String(item.id));
          const isSelected = selectedIds.has(String(item.id));
          return (
            <View style={[styles.card, !isRead && styles.unreadCard, isBusy && styles.disabled]}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`${isSelected ? "Deselect" : "Select"} notification ${item.title || "FieldOps update"}`}
                accessibilityState={{ selected: isSelected }}
                onPress={() => toggleSelection(item.id)}
                hitSlop={6}
                style={styles.selectionCheckbox}
              >
                <Ionicons
                  name={isSelected ? "checkbox" : "square-outline"}
                  size={19}
                  color={isSelected ? "#078A4D" : "#9AA99F"}
                />
              </Pressable>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={isRead ? `Notification: ${item.title || "FieldOps update"}` : `Mark notification ${item.title || "FieldOps update"} as read`}
                disabled={isRead}
                onPress={() => void markNotificationRead(item)}
                style={({ pressed }) => [styles.cardBody, pressed && !isRead && styles.cardPressed]}
              >
                <View style={styles.cardHeading}>
                  <View style={[styles.statusIcon, isRead ? styles.readStatusIcon : styles.unreadStatusIcon]}>
                    <Ionicons
                      name={isRead ? "checkmark" : "notifications"}
                      size={15}
                      color={isRead ? "#647A6C" : "#078A4D"}
                    />
                  </View>
                  <Text style={[styles.notificationTitle, isRead && styles.readTitle]} numberOfLines={2}>
                    {item.title || "FieldOps update"}
                  </Text>
                  {!isRead ? <View style={styles.unreadPill}><Text style={styles.unreadPillText}>NEW</Text></View> : null}
                </View>
                {message ? <Text style={styles.message}>{message}</Text> : null}
                <View style={styles.cardFooter}>
                  <Ionicons name="time-outline" size={14} color="#789083" />
                  <Text style={styles.date}>{formatDate(item.created_at)}</Text>
                  {!isRead ? <Text style={styles.tapHint}>Tap to mark read</Text> : null}
                </View>
              </Pressable>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`Delete notification ${item.title || "FieldOps update"}`}
                disabled={isBusy}
                onPress={() => dismissNotification(item)}
                hitSlop={8}
                style={({ pressed }) => [styles.deleteButton, pressed && styles.deletePressed]}
              >
                <Ionicons name="close" size={19} color="#718579" />
              </Pressable>
            </View>
          );
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#F3F8F4", paddingTop: 18 },
  header: {
    marginHorizontal: 16,
    padding: 20,
    borderRadius: 22,
    backgroundColor: "#075B3C",
    shadowColor: "#06452F",
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.16,
    shadowRadius: 15,
    elevation: 5
  },
  headerTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  backButton: { width: 36, height: 36, borderRadius: 12, alignItems: "center", justifyContent: "center", backgroundColor: "rgba(255,255,255,0.14)", marginRight: 11 },
  headingCopy: { flex: 1 },
  eyebrow: { color: "#A9E2C1", fontSize: 10, fontWeight: "900", letterSpacing: 1.5 },
  title: { color: "#FFFFFF", fontSize: 27, fontWeight: "900", marginTop: 4 },
  headerIcon: { width: 46, height: 46, borderRadius: 16, backgroundColor: "rgba(255,255,255,0.14)", alignItems: "center", justifyContent: "center" },
  subtitle: { color: "#D8F0E1", fontSize: 13, lineHeight: 19, marginTop: 8 },
  summaryRow: { flexDirection: "row", alignItems: "center", marginTop: 18, minHeight: 34 },
  summaryDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: "#79E2A6", marginRight: 8 },
  summaryText: { color: "#FFFFFF", fontSize: 13, fontWeight: "700", flex: 1 },
  markAllButton: { flexDirection: "row", alignItems: "center", gap: 5, borderRadius: 20, paddingHorizontal: 11, paddingVertical: 8, backgroundColor: "rgba(255,255,255,0.14)" },
  markAllText: { color: "#E8F7EE", fontSize: 11, fontWeight: "800" },
  selectionToolbar: { minHeight: 48, flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 19, paddingTop: 12 },
  selectAllButton: { flexDirection: "row", alignItems: "center", gap: 7, paddingVertical: 6 },
  selectAllText: { color: "#176342", fontSize: 12, fontWeight: "800" },
  selectionActions: { flexDirection: "row", alignItems: "center", gap: 10 },
  selectedCount: { color: "#6B7D72", fontSize: 11, fontWeight: "700" },
  deleteSelectedButton: { flexDirection: "row", alignItems: "center", gap: 5, borderRadius: 16, paddingHorizontal: 12, paddingVertical: 8, backgroundColor: "#B83D45" },
  deleteSelectedText: { color: "#FFFFFF", fontSize: 11, fontWeight: "800" },
  filterBar: { flexDirection: "row", gap: 9, paddingHorizontal: 18, paddingVertical: 17 },
  filterChip: { flexDirection: "row", alignItems: "center", gap: 7, paddingHorizontal: 14, paddingVertical: 9, borderRadius: 22, backgroundColor: "#E7EFE9", borderWidth: 1, borderColor: "#E7EFE9" },
  filterChipSelected: { backgroundColor: "#FFFFFF", borderColor: "#078A4D", shadowColor: "#078A4D", shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.1, shadowRadius: 4, elevation: 2 },
  filterText: { color: "#687B70", fontSize: 12, fontWeight: "700" },
  filterTextSelected: { color: "#075B3C" },
  filterCount: { minWidth: 18, color: "#819187", fontSize: 11, textAlign: "center", fontWeight: "700" },
  filterCountSelected: { color: "#078A4D" },
  list: { paddingHorizontal: 16, paddingBottom: 28 },
  emptyList: { flexGrow: 1, paddingHorizontal: 16, paddingBottom: 28 },
  card: { position: "relative", flexDirection: "row", backgroundColor: "#FFFFFF", borderColor: "#E0EAE3", borderWidth: 1, borderRadius: 18, marginBottom: 11, shadowColor: "#16432E", shadowOffset: { width: 0, height: 3 }, shadowOpacity: 0.05, shadowRadius: 8, elevation: 2 },
  unreadCard: { borderColor: "#A8D9BA", backgroundColor: "#FCFFFD", borderLeftWidth: 4, borderLeftColor: "#078A4D" },
  cardBody: { flex: 1, padding: 15, paddingLeft: 4, paddingRight: 4 },
  selectionCheckbox: { width: 38, alignItems: "center", justifyContent: "flex-start", paddingTop: 19 },
  cardPressed: { opacity: 0.78 },
  cardHeading: { flexDirection: "row", alignItems: "center", gap: 10 },
  statusIcon: { width: 30, height: 30, borderRadius: 11, alignItems: "center", justifyContent: "center" },
  unreadStatusIcon: { backgroundColor: "#E5F6EB" },
  readStatusIcon: { backgroundColor: "#EEF2EF" },
  notificationTitle: { color: "#173B29", flex: 1, fontSize: 14, lineHeight: 19, fontWeight: "800" },
  readTitle: { color: "#65766B", fontWeight: "700" },
  unreadPill: { backgroundColor: "#E6F6EC", borderRadius: 10, paddingHorizontal: 8, paddingVertical: 4 },
  unreadPillText: { color: "#078A4D", fontSize: 9, fontWeight: "900", letterSpacing: 0.5 },
  message: { color: "#5E7065", fontSize: 13, lineHeight: 19, marginTop: 10, marginLeft: 40 },
  cardFooter: { flexDirection: "row", alignItems: "center", gap: 5, marginTop: 12, marginLeft: 40 },
  date: { color: "#789083", fontSize: 11, flex: 1 },
  tapHint: { color: "#078A4D", fontSize: 10, fontWeight: "700" },
  deleteButton: { width: 38, alignItems: "center", justifyContent: "flex-start", paddingTop: 13, marginRight: 5, borderRadius: 12 },
  deletePressed: { backgroundColor: "#F0F5F1" },
  disabled: { opacity: 0.55 },
  pressed: { opacity: 0.8 },
  warning: { color: "#8A5A09", backgroundColor: "#FFF5D9", marginHorizontal: 16, marginTop: 12, padding: 12, borderRadius: 10 }
});
