import { useCallback, useState } from "react";
import { Alert, Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { customerApi, readNotificationFeed } from "../src/api/customer";
import { getApiErrorMessage } from "../src/api/client";
import { AppButton, Card, EmptyState, ErrorState, Header, LoadingView, Screen, sharedStyles } from "../src/components/ui";
import type { CustomerNotification, NotificationFeed } from "../src/types/api";
import { formatDateTime } from "../src/utils/format";
import { colors } from "../src/theme";

const emptyFeed: NotificationFeed = { notifications: [], unread_count: 0 };

export default function CustomerNotificationsScreen() {
  const [feed, setFeed] = useState<NotificationFeed>(emptyFeed);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(async (pull = false) => {
    if (pull) setRefreshing(true); else setLoading(true);
    setError("");
    try { setFeed(readNotificationFeed(await customerApi.notificationFeed())); }
    catch (e) { setError(getApiErrorMessage(e, "Could not load customer notifications.")); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useFocusEffect(useCallback(() => { void load(); }, [load]));
  const open = async (item: CustomerNotification) => {
    if (!item.isRead && item.status?.toUpperCase() === "UNREAD") {
      setBusyId(item.id);
      try { await customerApi.markNotificationRead(item.id); setFeed((old) => ({ ...old, unread_count: Math.max(0, old.unread_count - 1), notifications: old.notifications.map((n) => n.id === item.id ? { ...n, isRead: true, status: "READ" } : n) })); }
      catch (e) { Alert.alert("Could not update notification", getApiErrorMessage(e)); }
      finally { setBusyId(""); }
    }
    if (item.jobId) router.push({ pathname: "/jobs/[jobId]", params: { jobId: String(item.jobId) } });
  };
  const markAll = async () => {
    if (feed.unread_count === 0) return;
    setBusyId("all");
    try { await customerApi.markAllNotificationsRead(); setFeed((old) => ({ notifications: old.notifications.map((item) => ({ ...item, isRead: true, status: "READ" })), unread_count: 0 })); }
    catch (e) { Alert.alert("Could not mark all read", getApiErrorMessage(e)); }
    finally { setBusyId(""); }
  };

  return <Screen scroll={false} contentStyle={{ paddingHorizontal: 0, paddingTop: 0, paddingBottom: 0 }}>
    <ScrollView contentContainerStyle={{ padding: 18, gap: 18, paddingBottom: 30 }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load(true)} tintColor={colors.brand} />} showsVerticalScrollIndicator={false}>
      <Header title="Notifications" subtitle={`${feed.unread_count} unread ${feed.unread_count === 1 ? "message" : "messages"}`} right={<Pressable onPress={() => router.back()} style={{ padding: 8 }}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>} />
      {feed.unread_count > 0 ? <AppButton title="Mark all as read" icon="checkmark-done-outline" kind="secondary" onPress={() => void markAll()} loading={busyId === "all"} /> : null}
      {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}
      {loading ? <LoadingView message="Loading your notifications…" /> : feed.notifications.length === 0 ? <Card><EmptyState title="You’re all caught up" message="Service status updates and other customer messages will appear here." icon="notifications-outline" /></Card> : feed.notifications.map((item) => {
        const unread = !item.isRead && item.status?.toUpperCase() === "UNREAD";
        return <Pressable key={item.id} disabled={busyId === item.id} onPress={() => void open(item)}><Card style={{ backgroundColor: unread ? "#F3F8F4" : "#FFFFFF", borderColor: unread ? "#C9DFD0" : colors.border, opacity: busyId === item.id ? 0.6 : 1 }}>
          <View style={{ flexDirection: "row", gap: 12, alignItems: "flex-start" }}><View style={{ width: 42, height: 42, borderRadius: 14, backgroundColor: unread ? colors.brand : "#EEF2EF", alignItems: "center", justifyContent: "center" }}><Ionicons name={unread ? "notifications" : "notifications-outline"} size={20} color={unread ? "white" : colors.muted} /></View><View style={{ flex: 1, gap: 6 }}><View style={sharedStyles.spaceBetween}><Text style={{ flex: 1, color: colors.text, fontSize: 14, fontWeight: unread ? "900" : "700" }}>{item.title || "FieldOps update"}</Text>{unread ? <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: colors.brandMid }} /> : null}</View><Text style={{ color: colors.muted, fontSize: 13, lineHeight: 20 }}>{item.message || "You have a new service update."}</Text><Text style={{ color: colors.muted, fontSize: 11 }}>{formatDateTime(item.createdAt)}</Text>{item.jobId ? <Text style={{ color: colors.brandMid, fontSize: 12, fontWeight: "800" }}>Open job #{item.jobId} ›</Text> : null}</View></View>
        </Card></Pressable>;
      })}
      <Text style={{ fontSize: 11, color: colors.muted, lineHeight: 17 }}>This screen uses the existing authenticated in-app notification feed. Native push delivery is not enabled until a customer device-registration endpoint is available.</Text>
    </ScrollView>
  </Screen>;
}
