import { useCallback, useState } from "react";
import { Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { customerApi } from "../../src/api/customer";
import { getApiErrorMessage } from "../../src/api/client";
import { Card, EmptyState, ErrorState, Header, LoadingView, Screen, StatusBadge, sharedStyles } from "../../src/components/ui";
import type { CustomerJob } from "../../src/types/api";
import { formatDateTime } from "../../src/utils/format";
import { colors } from "../../src/theme";

export default function CustomerTrackingScreen() {
  const [jobs, setJobs] = useState<CustomerJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async (pull = false) => {
    if (pull) setRefreshing(true); else setLoading(true);
    setError("");
    try { setJobs(await customerApi.jobs()); }
    catch (e) { setError(getApiErrorMessage(e, "Could not load job tracking.")); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useFocusEffect(useCallback(() => { void load(); }, [load]));
  const active = jobs.filter((job) => !["COMPLETED", "CLOSED", "CANCELLED"].includes(String(job.status ?? "").toUpperCase()));
  const past = jobs.filter((job) => ["COMPLETED", "CLOSED", "CANCELLED"].includes(String(job.status ?? "").toUpperCase()));
  return <Screen scroll={false} contentStyle={{ paddingHorizontal: 0, paddingTop: 0, paddingBottom: 0 }}>
    <ScrollView contentContainerStyle={{ padding: 18, gap: 18, paddingBottom: 30 }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load(true)} tintColor={colors.brand} />} showsVerticalScrollIndicator={false}>
      <Header title="Job tracking" subtitle="Follow active visits and service progress" />
      <View style={{ backgroundColor: colors.brand, borderRadius: 20, padding: 18, gap: 8 }}><View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}><Ionicons name="navigate-circle" size={22} color={colors.accent} /><Text style={{ color: colors.accent, fontSize: 12, fontWeight: "800" }}>YOUR SERVICE JOURNEY</Text></View><Text style={{ color: "white", fontSize: 20, fontWeight: "900" }}>{active.length} active {active.length === 1 ? "job" : "jobs"}</Text><Text style={{ color: "#D5E6DD", fontSize: 13, lineHeight: 19 }}>Live GPS and arrival estimates appear when the assigned technician and backend tracking service provide them. Pull down to refresh.</Text></View>
      {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}
      {loading ? <LoadingView message="Loading your jobs…" /> : <>
        <View style={{ gap: 12 }}><Text style={{ fontSize: 17, fontWeight: "800", color: colors.text }}>In progress and upcoming</Text>{active.length ? active.map((job) => <Pressable key={job.id} onPress={() => router.push({ pathname: "/jobs/[jobId]", params: { jobId: String(job.id) } })}><Card>
          <View style={sharedStyles.spaceBetween}><Text style={{ flex: 1, color: colors.text, fontSize: 15, fontWeight: "800" }}>{job.service_type || "Service job"}</Text><StatusBadge status={job.status} /></View>
          <View style={{ flexDirection: "row", gap: 8, alignItems: "center" }}><Ionicons name="location-outline" size={17} color={colors.muted} /><Text style={{ color: colors.muted, fontSize: 12, flex: 1 }}>{job.site_address || job.location || "Service address unavailable"}</Text></View>
          {job.assigned_technician_name ? <View style={{ flexDirection: "row", gap: 8, alignItems: "center" }}><Ionicons name="person-outline" size={17} color={colors.muted} /><Text style={{ color: colors.text, fontSize: 13, fontWeight: "600" }}>{job.assigned_technician_name}</Text></View> : null}
          <View style={{ backgroundColor: colors.accentLight, borderRadius: 12, padding: 12, gap: 5 }}><Text style={{ color: colors.brandMid, fontSize: 11, fontWeight: "800" }}>ARRIVAL ESTIMATE</Text><Text style={{ color: colors.brand, fontSize: 15, fontWeight: "800" }}>{job.eta_duration_minutes != null ? `${job.eta_duration_minutes} min away` : job.estimated_arrival ? formatDateTime(job.estimated_arrival) : "Not available yet"}</Text><Text style={{ color: colors.muted, fontSize: 11, lineHeight: 16 }}>{job.eta_message || "The estimate will update when the backend receives enough route and GPS information."}</Text></View>
          <View style={sharedStyles.spaceBetween}><Text style={{ fontSize: 11, color: colors.muted }}>Job #{job.id}</Text><Text style={{ color: colors.brandMid, fontWeight: "800", fontSize: 12 }}>Open tracking  ›</Text></View>
        </Card></Pressable>) : <Card><EmptyState title="Nothing to track right now" message="Once you book a service, job progress and technician details will appear here." icon="navigate-outline" /></Card>}</View>
        {past.length ? <View style={{ gap: 12 }}><Text style={{ fontSize: 17, fontWeight: "800", color: colors.text }}>Previous jobs</Text>{past.slice(0, 5).map((job) => <Pressable key={job.id} onPress={() => router.push({ pathname: "/jobs/[jobId]", params: { jobId: String(job.id) } })}><Card style={{ padding: 14 }}><View style={sharedStyles.spaceBetween}><Text style={{ flex: 1, color: colors.text, fontSize: 14, fontWeight: "700" }}>{job.service_type || `Job #${job.id}`}</Text><StatusBadge status={job.status} /></View><Text style={{ color: colors.muted, fontSize: 12 }}>Job #{job.id} · {formatDateTime(job.completed_at || job.created_at)}</Text></Card></Pressable>)}</View> : null}
      </>}
    </ScrollView>
  </Screen>;
}
