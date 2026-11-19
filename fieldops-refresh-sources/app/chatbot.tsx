
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { customerApi } from "../src/api/customer";
import type {
  CustomerChatComponent,
  CustomerChatMessage,
} from "../src/api/customer";
import { getApiErrorMessage } from "../src/api/client";

const GREEN = "#156B5B";
const DARK_GREEN = "#156B5B";
const MINT = "#E1F1ED";
const BG = "#F7FAF9";
const TEXT = "#1A2E2A";
const MUTED = "#62726E";

const QUICK_QUESTIONS = [
  "What is FieldOps used for?",
  "What services does FieldOps offer?",
  "How do I create a service request?",
  "How can I check my job status?",
  "When will my technician arrive?",
  "How do I track my technician?",
  "How do appointments work?",
  "Will I receive job notifications?",
  "What is a closure report?",
  "How do I contact support?",
];

type DisplayMessage = CustomerChatMessage;

export default function CustomerChatbotScreen() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef<ScrollView>(null);

  const loadConversation = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const conversations = await customerApi.listChatConversations();

      if (conversations.length > 0) {
        const latest = conversations[0];
        const conversation =
          await customerApi.getChatConversation(latest.id);

        setConversationId(conversation.id);
        setMessages(
          Array.isArray(conversation.messages)
            ? conversation.messages
            : [],
        );
      } else {
        setConversationId(null);
        setMessages([]);
      }
    } catch (err) {
      setError(
        getApiErrorMessage(
          err,
          "Couldn't load your conversations. Please try again.",
        ),
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadConversation();
  }, [loadConversation]);

  useEffect(() => {
    const timeout = setTimeout(() => {
      scrollRef.current?.scrollToEnd({ animated: true });
    }, 100);

    return () => clearTimeout(timeout);
  }, [messages]);

  const sendMessage = useCallback(
    async (overrideText?: string) => {
      const message = (overrideText ?? draft).trim();

      if (!message || sending) return;

      setSending(true);
      setError("");
      setDraft("");

      const clientMessageId =
        "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(
          /[xy]/g,
          (character) => {
            const random = Math.floor(Math.random() * 16);
            const value =
              character === "x" ? random : (random & 0x3) | 0x8;

            return value.toString(16);
          },
        );

      const optimisticMessage: DisplayMessage = {
        id: Date.now(),
        sender: "customer",
        content: message,
        created_at: new Date().toISOString(),
      };

      setMessages((current) => [...current, optimisticMessage]);

      try {
        const response = await customerApi.sendChatMessage(
          conversationId,
          message,
          clientMessageId,
        );

        setConversationId(response.conversation_id);

        const assistantMessage: DisplayMessage = {
          id: Date.now() + 1,
          sender: "assistant",
          content: response.answer,
          created_at: new Date().toISOString(),
          intent: response.intent,
          components: response.components,
          follow_up_suggestions: response.follow_up_suggestions,
        };

        setMessages((current) => [
          ...current,
          assistantMessage,
        ]);
      } catch (err) {
        setError(
          getApiErrorMessage(
            err,
            "Your message couldn't be sent. Please try again.",
          ),
        );
        setDraft(message);
      } finally {
        setSending(false);
      }
    },
    [conversationId, draft, sending],
  );

  const openAction = (action: CustomerChatComponent["action"]) => {
    switch (action) {
      case "service_requests":
        router.push("/(tabs)/requests");
        break;
      case "tracking":
        router.push("/(tabs)/tracking");
        break;
      case "support":
        router.push("/support");
        break;
      default:
        break;
    }
  };

  const renderComponent = (component: CustomerChatComponent, index: number) => (
    <View
      key={`${component.type}-${component.job_id ?? "general"}-${index}`}
      style={styles.responseCard}
    >
      <View style={styles.responseCardHeading}>
        <Ionicons
          name={
            component.type === "job_status"
              ? "construct-outline"
              : component.type === "service_catalog"
                ? "grid-outline"
                : "headset-outline"
          }
          size={20}
          color={GREEN}
        />
        <Text style={styles.responseCardTitle}>
          {component.title}
        </Text>
      </View>

      {component.status ? (
        <Text style={styles.responseDetail}>
          Status: {component.status.replace(/_/g, " ")}
        </Text>
      ) : null}

      {component.preferred_service_date ? (
        <Text style={styles.responseDetail}>
          Scheduled: {component.preferred_service_date}
        </Text>
      ) : null}

      {component.arrival_estimate ? (
        <Text style={styles.responseDetail}>
          Arrival estimate: {component.arrival_estimate}
        </Text>
      ) : null}

      {component.completed_at ? (
        <Text style={styles.responseDetail}>
          Completed: {component.completed_at}
        </Text>
      ) : null}

      {component.items?.map((item, itemIndex) => (
        <Text key={`${item}-${itemIndex}`} style={styles.responseDetail}>
          • {item}
        </Text>
      ))}

      {component.action && component.action !== "download_report" ? (
        <Pressable
          accessibilityRole="button"
          onPress={() => openAction(component.action)}
          style={styles.actionButton}
        >
          <Text style={styles.actionButtonText}>
            {component.action === "service_requests"
              ? "View my requests"
              : component.action === "tracking"
                ? "Open tracking"
                : "Contact support"}
          </Text>
          <Ionicons name="arrow-forward" size={16} color={GREEN} />
        </Pressable>
      ) : null}

      {component.action === "download_report" ? (
        <Text style={styles.responseDetail}>
          Your report action is available on the web portal.
        </Text>
      ) : null}
    </View>
  );

  return (
    <SafeAreaView style={styles.safeArea} edges={["top", "bottom"]}>
      <StatusBar barStyle="light-content" backgroundColor={DARK_GREEN} />

      <View style={styles.header}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Go back"
          onPress={() => router.back()}
          style={styles.backButton}
        >
          <Ionicons name="arrow-back" size={23} color="#FFFFFF" />
        </Pressable>

        <View style={styles.robotIcon}>
          <Ionicons name="hardware-chip" size={26} color="#FFFFFF" />
          <View style={styles.onlineDot} />
        </View>

        <View style={styles.headerText}>
          <Text style={styles.headerTitle}>FieldOps Assistant</Text>
          <Text style={styles.headerSubtitle}>
            Your service support chatbot
          </Text>
        </View>

        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Refresh conversation"
          onPress={() => void loadConversation()}
          style={styles.refreshButton}
        >
          <Ionicons name="refresh-outline" size={21} color="#FFFFFF" />
        </Pressable>
      </View>

      <KeyboardAvoidingView
        style={styles.content}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={Platform.OS === "ios" ? 8 : 0}
      >
        {loading ? (
          <View style={styles.centerState}>
            <ActivityIndicator size="large" color={GREEN} />
            <Text style={styles.stateText}>
              Loading your conversation...
            </Text>
          </View>
        ) : (
          <ScrollView
            ref={scrollRef}
            style={styles.messageScroll}
            contentContainerStyle={styles.messageContent}
            keyboardShouldPersistTaps="handled"
          >
            {messages.length === 0 ? (
              <View style={styles.welcomeCard}>
                <View style={styles.welcomeRobot}>
                  <Ionicons
                    name="hardware-chip"
                    size={34}
                    color={GREEN}
                  />
                </View>
                <Text style={styles.welcomeTitle}>
                  Hi, how can we help?
                </Text>
                <Text style={styles.welcomeText}>
                  Ask a question about FieldOps or your service requests.
                </Text>

                <Text style={styles.quickHeading}>
                  SUGGESTED QUESTIONS
                </Text>

                {QUICK_QUESTIONS.map((question) => (
                  <Pressable
                    key={question}
                    onPress={() => void sendMessage(question)}
                    disabled={sending}
                    style={styles.quickQuestion}
                  >
                    <Text style={styles.quickQuestionText}>
                      {question}
                    </Text>
                    <Ionicons
                      name="arrow-up-circle-outline"
                      size={21}
                      color={GREEN}
                    />
                  </Pressable>
                ))}
              </View>
            ) : (
              messages.map((message, index) => (
                <View key={`${message.id}-${index}`}>
                  <View
                    style={[
                      styles.messageRow,
                      message.sender === "customer"
                        ? styles.customerMessageRow
                        : styles.assistantMessageRow,
                    ]}
                  >
                    {message.sender === "assistant" ? (
                      <View style={styles.smallRobot}>
                        <Ionicons
                          name="hardware-chip"
                          size={17}
                          color={GREEN}
                        />
                      </View>
                    ) : null}

                    <View
                      style={[
                        styles.bubble,
                        message.sender === "customer"
                          ? styles.customerBubble
                          : styles.assistantBubble,
                      ]}
                    >
                      <Text
                        style={[
                          styles.messageText,
                          message.sender === "customer" &&
                            styles.customerMessageText,
                        ]}
                      >
                        {message.content}
                      </Text>
                      <Text
                        style={[
                          styles.messageTime,
                          message.sender === "customer" &&
                            styles.customerMessageTime,
                        ]}
                      >
                        {new Date(message.created_at).toLocaleTimeString(
                          [],
                          { hour: "numeric", minute: "2-digit" },
                        )}
                      </Text>
                    </View>
                  </View>

                  {message.sender === "assistant"
                    ? message.components?.map(renderComponent)
                    : null}

                  {message.sender === "assistant" &&
                  message.follow_up_suggestions?.length ? (
                    <View style={styles.followUps}>
                      {message.follow_up_suggestions.map((suggestion) => (
                        <Pressable
                          key={suggestion}
                          onPress={() => void sendMessage(suggestion)}
                          disabled={sending}
                          style={styles.followUp}
                        >
                          <Text style={styles.followUpText}>
                            {suggestion}
                          </Text>
                          <Ionicons
                            name="arrow-up-outline"
                            size={15}
                            color={GREEN}
                          />
                        </Pressable>
                      ))}
                    </View>
                  ) : null}
                </View>
              ))
            )}

            {sending ? (
              <View style={styles.typingRow}>
                <ActivityIndicator size="small" color={GREEN} />
                <Text style={styles.stateText}>
                  FieldOps Assistant is replying...
                </Text>
              </View>
            ) : null}
          </ScrollView>
        )}

        {error ? (
          <View style={styles.errorBox}>
            <Text style={styles.errorText}>{error}</Text>
            <Pressable onPress={() => void loadConversation()}>
              <Text style={styles.retryText}>Retry</Text>
            </Pressable>
          </View>
        ) : null}

        <View style={styles.composer}>
          <TextInput
            value={draft}
            onChangeText={setDraft}
            placeholder="Ask FieldOps anything..."
            placeholderTextColor="#84948B"
            style={styles.input}
            multiline
            maxLength={2000}
            editable={!loading && !sending}
            onSubmitEditing={() => void sendMessage()}
            returnKeyType="send"
            accessibilityLabel="Message FieldOps Assistant"
          />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Send message"
            disabled={!draft.trim() || loading || sending}
            onPress={() => void sendMessage()}
            style={[
              styles.sendButton,
              (!draft.trim() || loading || sending) &&
                styles.sendButtonDisabled,
            ]}
          >
            <Ionicons name="send" size={20} color="#FFFFFF" />
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: BG },
  header: {
    minHeight: 76,
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 12,
    gap: 10,
    backgroundColor: DARK_GREEN,
  },
  backButton: {
    width: 34,
    height: 42,
    alignItems: "center",
    justifyContent: "center",
  },
  robotIcon: {
    width: 46,
    height: 46,
    borderRadius: 23,
    backgroundColor: "#11966C",
    alignItems: "center",
    justifyContent: "center",
  },
  onlineDot: {
    position: "absolute",
    right: 0,
    top: 0,
    width: 11,
    height: 11,
    borderRadius: 6,
    backgroundColor: "#6EE7A8",
    borderWidth: 2,
    borderColor: DARK_GREEN,
  },
  headerText: { flex: 1 },
  headerTitle: { color: "#FFFFFF", fontSize: 16, fontWeight: "800" },
  headerSubtitle: { color: "#B9D9C9", fontSize: 11, marginTop: 3 },
  refreshButton: {
    width: 36,
    height: 42,
    alignItems: "center",
    justifyContent: "center",
  },
  content: { flex: 1, backgroundColor: BG },
  messageScroll: { flex: 1 },
  messageContent: { padding: 16, paddingBottom: 24, flexGrow: 1 },
  centerState: { flex: 1, alignItems: "center", justifyContent: "center", gap: 12 },
  stateText: { color: MUTED, fontSize: 12 },
  welcomeCard: {
    marginTop: 8,
    backgroundColor: "#FFFFFF",
    padding: 16,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "#DBE5E2",
  },
  welcomeRobot: {
    width: 62,
    height: 62,
    borderRadius: 20,
    backgroundColor: MINT,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 16,
  },
  welcomeTitle: { color: TEXT, fontSize: 21, fontWeight: "800" },
  welcomeText: {
    color: MUTED,
    fontSize: 14,
    lineHeight: 21,
    marginTop: 8,
    marginBottom: 24,
  },
  quickHeading: {
    color: "#60726C",
    fontSize: 11,
    fontWeight: "700",
    marginBottom: 6,
  },
  quickQuestion: {
    minHeight: 38,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: "#D7E4E0",
    backgroundColor: "#FFFFFF",
    paddingHorizontal: 10,
    paddingVertical: 6,
    marginTop: 5,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 8,
  },
  quickQuestionText: {
    color: "#205C50",
    fontSize: 11,
    fontWeight: "700",
    flex: 1,
  },
  messageRow: { flexDirection: "row", alignItems: "flex-end", marginBottom: 14, gap: 7 },
  customerMessageRow: { justifyContent: "flex-end" },
  assistantMessageRow: { justifyContent: "flex-start" },
  smallRobot: {
    width: 29,
    height: 29,
    borderRadius: 15,
    backgroundColor: MINT,
    alignItems: "center",
    justifyContent: "center",
  },
  bubble: { maxWidth: "82%", paddingHorizontal: 13, paddingTop: 11, paddingBottom: 8, borderRadius: 17 },
  assistantBubble: {
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#E3EBE8",
    borderTopLeftRadius: 4,
  },

  customerBubble: {
    backgroundColor: GREEN,
    borderTopRightRadius: 4,
  },
  messageText: { color: TEXT, fontSize: 14, lineHeight: 20 },
  customerMessageText: { color: "#FFFFFF" },
  messageTime: { color: MUTED, fontSize: 9, textAlign: "right", marginTop: 5 },
  customerMessageTime: { color: "#D6F5E5" },
  responseCard: {
    marginLeft: 36,
    marginBottom: 14,
    padding: 13,
    borderRadius: 15,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#DCEAE2",
  },
  responseCardHeading: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 8 },
  responseCardTitle: { color: TEXT, fontSize: 13, fontWeight: "800", flex: 1 },
  responseDetail: { color: MUTED, fontSize: 12, lineHeight: 19, marginTop: 3 },
  actionButton: {
    marginTop: 12,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: "#E7EFEA",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  actionButtonText: { color: GREEN, fontSize: 12, fontWeight: "800" },
  followUps: { marginLeft: 36, marginBottom: 14, gap: 7 },
  followUp: {
    alignSelf: "flex-start",
    maxWidth: "100%",
    borderWidth: 1,
    borderColor: "#B7DDC8",
    backgroundColor: "#F7FCF8",
    paddingHorizontal: 12,
    paddingVertical: 9,
    borderRadius: 15,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  followUpText: { color: GREEN, fontSize: 12, fontWeight: "600", flexShrink: 1 },
  typingRow: { flexDirection: "row", alignItems: "center", gap: 8, marginLeft: 36, marginBottom: 12 },
  errorBox: {
    paddingHorizontal: 14,
    paddingVertical: 10,
    backgroundColor: "#FFF1F0",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
  },
  errorText: { color: "#A42A25", fontSize: 12, flex: 1 },
  retryText: { color: "#A42A25", fontSize: 12, fontWeight: "800" },
  composer: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: 9,
    padding: 12,
    backgroundColor: "#FFFFFF",
    borderTopWidth: 1,
    borderTopColor: "#DFEAE3",
  },
  input: {
    flex: 1,
    maxHeight: 110,
    minHeight: 46,
    backgroundColor: "#F5F9F6",
    borderWidth: 1,
    borderColor: "#DCE8E0",
    borderRadius: 15,
    paddingHorizontal: 13,
    paddingVertical: 12,
    color: TEXT,
    fontSize: 14,
  },
  sendButton: {
    width: 46,
    height: 46,
    borderRadius: 15,
    backgroundColor: GREEN,
    alignItems: "center",
    justifyContent: "center",
  },
  sendButtonDisabled: { opacity: 0.4 },
});
