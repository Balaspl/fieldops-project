import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { LoadingState } from "../../../../src/components/ScreenState";
import {
  acknowledgeTechnicianMessageDelivered,
  getTechnicianJobConversation,
  sendTechnicianJobMessage,
  type JobConversation,
  type JobMessage
} from "../../../../src/api/jobMessaging";

function formatMessageTime(value: string | null) {
  if (!value) return "Sending…";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export default function TechnicianJobChatScreen() {
  const { jobId: rawJobId } = useLocalSearchParams<{ jobId: string }>();
  const jobId = Number(rawJobId);
  const router = useRouter();
  const listRef = useRef<FlatList<JobMessage>>(null);
  const [conversation, setConversation] = useState<JobConversation | null>(null);
  const [messages, setMessages] = useState<JobMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async (showLoader = false) => {
    if (!Number.isSafeInteger(jobId) || jobId < 1) {
      setError("This job conversation is unavailable.");
      setLoading(false);
      return;
    }
    if (showLoader) setLoading(true);
    try {
      const data = await getTechnicianJobConversation(jobId);
      setConversation(data);
      setMessages((current) => {
        // Keep messages sent moments ago if a just-sent response has not yet
        // appeared in the refreshed history.
        const known = new Set(data.messages.map((message) => message.id));
        const pending = current.filter((message) => message.id.startsWith("local-") && !known.has(message.id));
        return [...data.messages, ...pending];
      });
      setError("");
      data.messages
        .filter((message) => !message.is_mine && !message.delivered_at)
        .forEach((message) => void acknowledgeTechnicianMessageDelivered(jobId, message.id).catch(() => undefined));
    } catch {
      setError("Messages could not be loaded. Check your connection and try again.");
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    void refresh(true);
    const interval = setInterval(() => void refresh(), 6000);
    return () => clearInterval(interval);
  }, [refresh]);

  const submit = async () => {
    const body = draft.trim();
    if (!body || sending || !conversation?.can_send) return;
    setSending(true);
    setDraft("");
    setError("");
    try {
      const message = await sendTechnicianJobMessage(jobId, body);
      setMessages((current) => current.some((item) => item.id === message.id) ? current : [...current, message]);
    } catch {
      setDraft(body);
      setError("Your message could not be sent. Please try again.");
    } finally {
      setSending(false);
    }
  };

  const renderMessage = ({ item }: { item: JobMessage }) => (
    <View style={[styles.messageRow, item.is_mine ? styles.messageRowMine : styles.messageRowTheirs]}>
      {!item.is_mine ? <View style={styles.senderDot}><Ionicons name="person" size={12} color="#087653" /></View> : null}
      <View style={[styles.bubble, item.is_mine ? styles.bubbleMine : styles.bubbleTheirs]}>
        <Text style={[styles.messageText, item.is_mine && styles.messageTextMine]}>{item.body}</Text>
        <View style={styles.messageMeta}>
          <Text style={[styles.messageTime, item.is_mine && styles.messageTimeMine]}>{formatMessageTime(item.created_at)}</Text>
          {item.is_mine ? <Ionicons name={item.read_at ? "checkmark-done" : "checkmark"} size={14} color={item.read_at ? "#b5ffe4" : "#e0fff3"} /> : null}
        </View>
      </View>
    </View>
  );

  return (
    <KeyboardAvoidingView style={styles.screen} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <View style={styles.header}>
        <Pressable accessibilityRole="button" accessibilityLabel="Back to job" onPress={() => router.back()} style={styles.backButton}>
          <Ionicons name="arrow-back" size={22} color="#123b33" />
        </Pressable>
        <View style={styles.headerAvatar}><Ionicons name="person" size={19} color="#087653" /></View>
        <View style={styles.headerCopy}>
          <Text numberOfLines={1} style={styles.headerTitle}>{conversation?.participant_name || "Customer"}</Text>
          <Text style={styles.headerSubtitle}>{conversation?.job_reference || `JOB-${rawJobId}`} · Job chat</Text>
        </View>
        <View style={styles.onlineMark} />
      </View>

      <View style={styles.conversationNotice}>
        <Ionicons name="lock-closed-outline" size={14} color="#538477" />
        <Text style={styles.conversationNoticeText}>Messages are private to this service job</Text>
      </View>

      {loading ? (
        <LoadingState label="Loading messages…" variant="chat" />
      ) : (
        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={(item) => item.id}
          renderItem={renderMessage}
          contentContainerStyle={[styles.messageList, !messages.length && styles.emptyList]}
          keyboardShouldPersistTaps="handled"
          onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
          ListEmptyComponent={<View style={styles.emptyState}><View style={styles.emptyIcon}><Ionicons name="chatbubbles-outline" size={24} color="#07865b" /></View><Text style={styles.emptyTitle}>Start the conversation</Text><Text style={styles.emptyCopy}>Send the customer a message about this job.</Text></View>}
        />
      )}

      {error ? <Text accessibilityRole="alert" style={styles.errorText}>{error}</Text> : null}
      {!loading && !conversation?.can_send ? (
        <View style={styles.readOnlyNotice}><Ionicons name="information-circle-outline" size={18} color="#8b6820" /><Text style={styles.readOnlyText}>{conversation?.read_only_reason || "Messaging is unavailable for this job."}</Text></View>
      ) : (
        <View style={styles.composerWrap}>
          <TextInput
            accessibilityLabel="Write a message"
            style={styles.composerInput}
            value={draft}
            onChangeText={setDraft}
            placeholder="Write a message…"
            placeholderTextColor="#8a9b96"
            multiline
            maxLength={4000}
            editable={!sending}
          />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Send message"
            onPress={() => void submit()}
            disabled={!draft.trim() || sending}
            style={({ pressed }) => [styles.sendButton, (!draft.trim() || sending) && styles.sendButtonDisabled, pressed && styles.sendButtonPressed]}
          >
            {sending ? <ActivityIndicator size="small" color="#fff" /> : <Ionicons name="send" size={18} color="#fff" />}
          </Pressable>
        </View>
      )}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#f3f8f6" },
  header: { flexDirection: "row", alignItems: "center", backgroundColor: "#fff", paddingHorizontal: 16, paddingTop: 14, paddingBottom: 14, borderBottomWidth: 1, borderBottomColor: "#e6efeb" },
  backButton: { width: 38, height: 38, alignItems: "center", justifyContent: "center", marginRight: 8 },
  headerAvatar: { width: 42, height: 42, borderRadius: 21, backgroundColor: "#e4f5ed", alignItems: "center", justifyContent: "center", marginRight: 10 },
  headerCopy: { flex: 1 },
  headerTitle: { color: "#172b26", fontSize: 16, fontWeight: "800" },
  headerSubtitle: { color: "#71827d", fontSize: 12, marginTop: 3 },
  onlineMark: { width: 9, height: 9, borderRadius: 5, backgroundColor: "#19a76b", marginLeft: 8 },
  conversationNotice: { flexDirection: "row", alignItems: "center", justifyContent: "center", paddingVertical: 10, gap: 6 },
  conversationNoticeText: { color: "#638078", fontSize: 11, fontWeight: "600" },
  messageList: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 20, gap: 12 },
  emptyList: { flexGrow: 1, justifyContent: "center" },
  centerState: { flex: 1, alignItems: "center", justifyContent: "center", gap: 10 },
  stateText: { color: "#71827d", fontSize: 13 },
  emptyState: { alignItems: "center", paddingHorizontal: 32 },
  emptyIcon: { width: 54, height: 54, borderRadius: 27, backgroundColor: "#e2f3eb", alignItems: "center", justifyContent: "center", marginBottom: 14 },
  emptyTitle: { color: "#20362f", fontSize: 16, fontWeight: "800" },
  emptyCopy: { color: "#71827d", fontSize: 13, textAlign: "center", marginTop: 6, lineHeight: 19 },
  messageRow: { flexDirection: "row", alignItems: "flex-end", gap: 7 },
  messageRowMine: { justifyContent: "flex-end" },
  messageRowTheirs: { justifyContent: "flex-start" },
  senderDot: { width: 26, height: 26, borderRadius: 13, backgroundColor: "#e0f0e9", alignItems: "center", justifyContent: "center" },
  bubble: { maxWidth: "82%", borderRadius: 17, paddingHorizontal: 13, paddingTop: 10, paddingBottom: 7 },
  bubbleMine: { backgroundColor: "#07865b", borderBottomRightRadius: 5 },
  bubbleTheirs: { backgroundColor: "#fff", borderBottomLeftRadius: 5, borderWidth: 1, borderColor: "#e7efeb" },
  messageText: { color: "#20352f", fontSize: 14, lineHeight: 20 },
  messageTextMine: { color: "#fff" },
  messageMeta: { flexDirection: "row", alignItems: "center", justifyContent: "flex-end", gap: 4, marginTop: 4 },
  messageTime: { color: "#85948f", fontSize: 10 },
  messageTimeMine: { color: "#d4f5e8" },
  errorText: { color: "#b33636", fontSize: 12, paddingHorizontal: 16, paddingVertical: 6 },
  readOnlyNotice: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: "#fff7e4", margin: 12, padding: 12, borderRadius: 12 },
  readOnlyText: { flex: 1, color: "#795d20", fontSize: 12, lineHeight: 17 },
  composerWrap: { flexDirection: "row", alignItems: "flex-end", gap: 9, paddingHorizontal: 12, paddingVertical: 10, paddingBottom: Platform.OS === "android" ? 12 : 18, backgroundColor: "#fff", borderTopWidth: 1, borderTopColor: "#e5eeea" },
  composerInput: { flex: 1, maxHeight: 110, minHeight: 44, borderRadius: 22, backgroundColor: "#f2f7f4", paddingHorizontal: 16, paddingTop: 12, paddingBottom: 10, color: "#20352f", fontSize: 14 },
  sendButton: { width: 44, height: 44, borderRadius: 22, backgroundColor: "#07865b", alignItems: "center", justifyContent: "center" },
  sendButtonDisabled: { backgroundColor: "#a8c7b9" },
  sendButtonPressed: { opacity: 0.82 }
});
