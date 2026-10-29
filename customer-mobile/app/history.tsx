import { useCallback, useState } from "react";
import { Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { customerApi } from "../src/api/customer";
import { getApiErrorMessage } from "../src/api/client";
import { Card, EmptyState, ErrorState, Header, LoadingView, Screen, StatusBadge, sharedStyles } from "../src/components/ui";
import type { CustomerJob, ServiceHistoryItem, ServiceRequest } from "../src/types/api";
import { formatDate, formatDateTime } from "../src/utils/format";
import { colors } from "../src/theme";

export default function CustomerHistoryScreen() {
  const [history, setHistory] = useState<ServiceHistoryItem[]>([]);
  const [requests, setRequests] = useState<ServiceRequest[]>([]);
  const [jobs, setJobs] = useState<CustomerJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState("ALL");
  const [error, setError] = useState("");
  const load = useCallback(async (pull = false) => {
    if (pull) setRefreshing(true); else setLoading(true);
    setError("");
    try {
      const [h, r, j] = await Promise.all([customerApi.history(), customerApi.requests(), customerApi.jobs()]);
      setHistory(h); setRequests(r); setJobs(j);
    } catch (e) { setError(getApiErrorMessage(e, "Could not load service history.")); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useFocusEffect(useCallback(() => { void load(); }, [load]));
  const completedJobs = jobs.filter((job) => ["COMPLETED", "CLOSED"].includes(String(job.status ?? "").toUpperCase()));
  const cancelledRequests = requests.filter((request) => ["CANCELLED", "REJECTED_BY_TECHNICIAN", "QUEUED"].includes(String(request.status).toUpperCase()));
  const source = history.length ? history : requests.map((request) => ({ linked_job_id: request.linked_job_id ?? null, title: request.title, service_type: request.service_type, status: request.status, created_at: request.created_at }));
  const visible = source.filter((item) => {
    const s = String(item.status ?? "").toUpperCase();
    if (filter === "COMPLETED") return ["COMPLETED", "CLOSED"].includes(s);
    if (filter === "CANCELLED") return ["CANCELLED", "REJECTED_BY_TECHNICIAN", "QUEUED"].includes(s);
    return true;
  });
  return <Screen scroll={false} contentStyle={{ paddingHorizontal: 0, paddingTop: 0, paddingBottom: 0 }}>
    <ScrollView contentContainerStyle={{ padding: 18, gap: 18, paddingBottom: 32 }} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load(true)} tintColor={colors.brand} />} showsVerticalScrollIndicator={false}>
      <Header title="Service history" subtitle="A record of your service requests and completed visits" />
      <View style={{ flexDirection: "row", gap: 10 }}><Card style={{ flex: 1, gap: 5 }}><Text style={{ color: colors.muted, fontSize: 11, fontWeight: "700" }}>COMPLETED JOBS</Text><Text style={{ color: colors.brand, fontSize: 27, fontWeight: "900" }}>{completedJobs.length}</Text></Card><Card style={{ flex: 1, gap: 5 }}><Text style={{ color: colors.muted, fontSize: 11, fontWeight: "700" }}>CANCELLED</Text><Text style={{ color: colors.brand, fontSize: 27, fontWeight: "900" }}>{cancelledRequests.length}</Text></Card></View>
      <View style={{ flexDirection: "row", gap: 8 }}>{["ALL", "COMPLETED", "CANCELLED"].map((value) => <Pressable key={value} onPress={() => setFilter(value)} style={{ borderRadius: 99, paddingHorizontal: 13, paddingVertical: 10, backgroundColor: filter === value ? colors.brand : "white", borderWidth: 1, borderColor: filter === value ? colors.brand : colors.border }}><Text style={{ color: filter === value ? "white" : colors.muted, fontSize: 12, fontWeight: "800" }}>{value.charAt(0) + value.slice(1).toLowerCase()}</Text></Pressable>)}</View>
      {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}
      {loading ? <LoadingView message="Loading service history…" /> : visible.length === 0 ? <Card><EmptyState title="No history to show" message="Completed and cancelled service records will appear here." icon="time-outline" /></Card> : visible.map((item, index) => {
        const jobId = item.linked_job_id ?? null;
        const linkedJob = jobs.find((job) => job.id === jobId);
        const request = requests.find((candidate) => candidate.linked_job_id === jobId);
        return <Pressable key={`${jobId ?? "request"}-${index}`} onPress={() => jobId ? router.push({ pathname: "/jobs/[jobId]", params: { jobId: String(jobId) } }) : request ? router.push({ pathname: "/requests/[requestId]", params: { requestId: String(request.id) } }) : undefined}>
          <Card><View style={sharedStyles.spaceBetween}><Text style={{ flex: 1, color: colors.text, fontSize: 15, fontWeight: "800" }}>{item.title || item.service_type || `Service #${index + 1}`}</Text><StatusBadge status={item.status} /></View><Text style={{ color: colors.muted, fontSize: 12 }}>{item.service_type || linkedJob?.service_type || "Service visit"}</Text><View style={sharedStyles.spaceBetween}><Text style={{ color: colors.muted, fontSize: 11 }}>{linkedJob ? `Job #${linkedJob.id}` : request?.request_number || "Service request"}</Text><Text style={{ color: colors.muted, fontSize: 11 }}>{formatDate(item.created_at || linkedJob?.completed_at || linkedJob?.created_at || request?.created_at)}</Text></View>{["COMPLETED", "CLOSED"].includes(String(item.status ?? "").toUpperCase()) && jobId ? <Text style={{ color: colors.brandMid, fontSize: 12, fontWeight: "800" }}>Open job details to leave feedback ›</Text> : null}</Card>
        </Pressable>;
      })}
      <Text style={{ color: colors.muted, fontSize: 11, lineHeight: 17 }}>Feedback is available only for eligible completed jobs and is saved by the FieldOps backend.</Text>
    </ScrollView>
  </Screen>;
}
