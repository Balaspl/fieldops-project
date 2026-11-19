import { useCallback, useEffect, useState } from "react";
import { Alert, Pressable, ScrollView, Text, View } from "react-native";
import { router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { customerApi } from "../src/api/customer";
import { getApiErrorMessage } from "../src/api/client";
import { AppButton, Card, EmptyState, ErrorState, Field, Header, LoadingView, Screen, StatusBadge, sharedStyles } from "../src/components/ui";
import type { CustomerJob, SupportRequest } from "../src/types/api";
import { formatDateTime } from "../src/utils/format";
import { colors } from "../src/theme";

export default function CustomerSupportScreen() {
  const [requests, setRequests] = useState<SupportRequest[]>([]);
  const [jobs, setJobs] = useState<CustomerJob[]>([]);
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [relatedJobId, setRelatedJobId] = useState<number | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [submittingError, setSubmittingError] = useState("");
  const load = useCallback(async (pull = false) => {
    if (pull) setRefreshing(true); else setLoading(true);
    setError("");
    try { const [s, j] = await Promise.all([customerApi.supportRequests(), customerApi.jobs()]); setRequests(s); setJobs(j); }
    catch (e) { setError(getApiErrorMessage(e, "Could not load support requests.")); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useFocusEffect(useCallback(() => { void load(); }, [load]));
  const create = async () => {
    setSubmittingError("");
    if (subject.trim().length < 3) { setSubmittingError("Enter a subject with at least 3 characters."); return; }
    if (description.trim().length < 10) { setSubmittingError("Describe the issue in at least 10 characters."); return; }
    setSaving(true);
    try {
      const created = await customerApi.createSupportRequest({ subject: subject.trim(), description: description.trim(), related_job_id: relatedJobId });
      setRequests((old) => [created, ...old]); setSubject(""); setDescription(""); setRelatedJobId(null); setShowForm(false);
      Alert.alert("Support request created", `Your reference number is ${created.request_number}.`);
    } catch (e) { setSubmittingError(getApiErrorMessage(e, "Could not create the support request.")); }
    finally { setSaving(false); }
  };

  return <Screen scroll={false} contentStyle={{ paddingHorizontal: 0, paddingTop: 0, paddingBottom: 0 }}>
    <ScrollView contentContainerStyle={{ padding: 18, gap: 18, paddingBottom: 30 }} refreshControl={undefined} showsVerticalScrollIndicator={false}>
      <Header title="Customer support" subtitle="Raise a question and track its status" right={<Pressable onPress={() => router.back()} style={{ padding: 8 }}><Ionicons name="close" color={colors.muted} size={22} /></Pressable>} />
      <Card style={{ backgroundColor: colors.brand, borderColor: colors.brand }}><View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}><View style={{ width: 48, height: 48, borderRadius: 16, backgroundColor: "#164B3C", alignItems: "center", justifyContent: "center" }}><Ionicons name="chatbubbles-outline" color={colors.accent} size={25} /></View><View style={{ flex: 1, gap: 4 }}><Text style={{ color: "white", fontSize: 17, fontWeight: "900" }}>We’re here to help</Text><Text style={{ color: "#D5E6DD", fontSize: 12, lineHeight: 18 }}>Include the job number and a clear description so the support team can assist.</Text></View></View><AppButton title={showForm ? "Hide support form" : "Create support request"} icon={showForm ? "chevron-up" : "add-circle-outline"} kind="secondary" onPress={() => { setShowForm((v) => !v); setSubmittingError(""); }} /></Card>
      {showForm ? <Card>
        <Text style={{ color: colors.text, fontSize: 17, fontWeight: "800" }}>New support request</Text>
        {submittingError ? <Text style={{ color: colors.danger, fontSize: 13, lineHeight: 19 }}>{submittingError}</Text> : null}
        <Field label="Subject" value={subject} onChangeText={setSubject} placeholder="What do you need help with?" maxLength={200} />
        <Field label="Description" value={description} onChangeText={setDescription} multiline placeholder="Describe the issue and any steps you have tried" maxLength={3000} />
        <Text style={{ color: colors.text, fontSize: 13, fontWeight: "700" }}>Related job (optional)</Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}><Pressable onPress={() => setRelatedJobId(null)} style={{ paddingHorizontal: 12, paddingVertical: 9, borderRadius: 99, backgroundColor: relatedJobId === null ? colors.brand : "white", borderWidth: 1, borderColor: relatedJobId === null ? colors.brand : colors.border }}><Text style={{ color: relatedJobId === null ? "white" : colors.muted, fontSize: 12, fontWeight: "700" }}>No job</Text></Pressable>{jobs.slice(0, 10).map((job) => <Pressable key={job.id} onPress={() => setRelatedJobId(job.id)} style={{ paddingHorizontal: 12, paddingVertical: 9, borderRadius: 99, backgroundColor: relatedJobId === job.id ? colors.brand : "white", borderWidth: 1, borderColor: relatedJobId === job.id ? colors.brand : colors.border }}><Text style={{ color: relatedJobId === job.id ? "white" : colors.muted, fontSize: 12, fontWeight: "700" }}>Job #{job.id}</Text></Pressable>)}</View>
        <AppButton title="Submit support request" onPress={() => void create()} loading={saving} icon="send-outline" />
      </Card> : null}
      {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}
      {loading ? <LoadingView message="Loading your support requests…" /> : requests.length === 0 ? <Card><EmptyState title="No support requests yet" message="Your submitted questions and their latest status will appear here." icon="chatbubbles-outline" /></Card> : <View style={{ gap: 12 }}><Text style={{ color: colors.text, fontWeight: "800", fontSize: 17 }}>Your support requests</Text>{requests.map((item) => <Card key={item.id}>
        <View style={sharedStyles.spaceBetween}><Text style={{ flex: 1, color: colors.text, fontSize: 14, fontWeight: "800" }}>{item.subject}</Text><StatusBadge status={item.status} /></View>
        <Text style={{ color: colors.muted, fontSize: 11 }}>{item.request_number} · {formatDateTime(item.created_at)}</Text>
        <Text style={{ color: colors.text, fontSize: 13, lineHeight: 20 }}>{item.description}</Text>
        {item.related_job_id ? <Text style={{ color: colors.muted, fontSize: 12 }}>Related job #{item.related_job_id}</Text> : null}
        {item.resolution_note ? <View style={{ backgroundColor: colors.accentLight, padding: 11, borderRadius: 11, gap: 4 }}><Text style={{ color: colors.brand, fontSize: 11, fontWeight: "800" }}>SUPPORT RESPONSE</Text><Text style={{ color: colors.text, fontSize: 12, lineHeight: 18 }}>{item.resolution_note}</Text></View> : null}
      </Card>)}</View>}
    </ScrollView>
  </Screen>;
}
