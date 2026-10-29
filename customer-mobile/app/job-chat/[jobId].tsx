import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import {
  router,
  useFocusEffect,
  useLocalSearchParams,
} from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { SafeAreaView } from "react-native-safe-area-context";

import { customerApi } from "../../src/api/customer";
import { getApiErrorMessage } from "../../src/api/client";
import type {
  JobConversation,
  JobMessage,
} from "../../src/types/api";
import { colors } from "../../src/theme";

const REFRESH_INTERVAL_MS = 10000;

function messageTime(value: string | null): string {
  if (!value) return "Sending…";

  const parsed = new Date(value);

  if (Number.isNaN(parsed.getTime())) {
    return "";
  }

  return parsed.toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

function deliveryLabel(message: JobMessage): string {
  if (message.read_at) return "Read";
  if (message.delivered_at) return "Delivered";
  return "Sent";
}

export default function CustomerJobChatScreen() {
  const params = useLocalSearchParams<{ jobId: string }>();
  const jobId = Number(params.jobId);

  const [conversation, setConversation] =
    useState<JobConversation | null>(null);

  const [messages, setMessages] = useState<JobMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  const messageListRef = useRef<ScrollView>(null);

  const loadConversation = useCallback(
    async (showLoading = false) => {
      if (!Number.isSafeInteger(jobId) || jobId <= 0) {
        setError("This job ID is invalid.");
        setLoading(false);
        return;
      }

      if (showLoading) {
        setLoading(true);
      }

      try {
        const result = await customerApi.jobConversation(jobId);

        setConversation(result);
        setMessages(
          Array.isArray(result.messages) ? result.messages : [],
        );
        setError("");

        // Acknowledge delivery of incoming messages.
        for (const message of result.messages ?? []) {
          if (!message.is_mine && !message.delivered_at) {
            void customerApi
              .acknowledgeJobMessageDelivered(jobId, message.id)
              .catch(() => undefined);
          }
        }
      } catch (requestError) {
        const status = (
          requestError as {
            response?: { status?: number };
          }
        )?.response?.status;

        setError(
          status === 404
            ? "This conversation is not available for your account."
            : getApiErrorMessage(
                requestError,
                "Messages could not be loaded. Reconnect and try again.",
              ),
        );
      } finally {
        if (showLoading) {
          setLoading(false);
        }
      }
    },
    [jobId],
  );

  // Load messages whenever this screen becomes active.
  // Refresh the conversation while the screen remains focused.
  useFocusEffect(
    useCallback(() => {
      void loadConversation(true);

      const interval = setInterval(() => {
        void loadConversation(false);
      }, REFRESH_INTERVAL_MS);

      return () => {
        clearInterval(interval);
      };
    }, [loadConversation]),
  );

  useEffect(() => {
    messageListRef.current?.scrollToEnd({
      animated: true,
    });
  }, [messages]);

  const send = useCallback(async () => {
    const body = draft.trim();

    if (
      !body ||
      sending ||
      !conversation?.can_send
    ) {
      return;
    }

    setSending(true);
    setError("");
    setDraft("");

    try {
      const sent = await customerApi.sendJobMessage(
        jobId,
        body,
      );

      setMessages((current) =>
        current.some((message) => message.id === sent.id)
          ? current
          : [...current, sent],
      );
    } catch (sendError) {
      setDraft(body);

      setError(
        getApiErrorMessage(
          sendError,
          "Your message could not be sent. Please try again.",
        ),
      );
    } finally {
      setSending(false);
    }
  }, [conversation?.can_send, draft, jobId, sending]);

  const title =
    conversation?.participant_name ||
    conversation?.technician_name ||
    "Job conversation";

  const statusLabel =
    conversation?.status?.replaceAll("_", " ") ||
    "Loading status";

  return (
    <SafeAreaView
      style={styles.safe}
      edges={["top", "right", "bottom", "left"]}
    >
      <KeyboardAvoidingView
        style={styles.container}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        {/* Conversation header */}
        <View style={styles.header}>
          <View style={styles.avatar}>
            <Ionicons
              name="chatbubble-outline"
              size={20}
              color="#FFFFFF"
            />
          </View>

          <View style={styles.heading}>
            <Text
              numberOfLines={1}
              style={styles.headingTitle}
            >
              {title}
            </Text>

            <Text
              numberOfLines={1}
              style={styles.headingSubtitle}
            >
              {conversation?.job_reference || `JOB-${jobId}`}
              {" · "}
              {statusLabel}
            </Text>
          </View>

          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Close chat"
            hitSlop={10}
            onPress={() => router.back()}
            style={({ pressed }) => [
              styles.closeButton,
              pressed && styles.pressed,
            ]}
          >
            <Ionicons
              name="close"
              size={24}
              color="#FFFFFF"
            />
          </Pressable>
        </View>

        {/* Conversation messages */}
        <ScrollView
          ref={messageListRef}
          style={styles.messageList}
          contentContainerStyle={[
            styles.messageListContent,
            messages.length === 0 &&
              styles.emptyMessageList,
          ]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {loading ? (
            <View style={styles.statePanel}>
              <ActivityIndicator
                size="small"
                color={colors.brandMid}
              />
              <Text style={styles.stateText}>
                Loading conversation…
              </Text>
            </View>
          ) : error && !conversation ? (
            <View style={styles.statePanel}>
              <Ionicons
                name="alert-circle-outline"
                size={25}
                color={colors.danger}
              />

              <Text style={styles.errorText}>
                {error}
              </Text>

              <Pressable
                onPress={() =>
                  void loadConversation(true)
                }
                style={styles.retryButton}
              >
                <Text style={styles.retryText}>
                  Try again
                </Text>
              </Pressable>
            </View>
          ) : messages.length === 0 ? (
            <View style={styles.statePanel}>
              <Text style={styles.stateText}>
                Messages about this job will appear here.
              </Text>
            </View>
          ) : (
            messages.map((message) => {
              const mine = message.is_mine;

              return (
                <View
                  key={message.id}
                  style={[
                    styles.messageBubble,
                    mine
                      ? styles.myMessage
                      : styles.theirMessage,
                  ]}
                >
                  <Text
                    style={[
                      styles.messageBody,
                      mine && styles.myMessageBody,
                    ]}
                  >
                    {message.body}
                  </Text>

                  <View style={styles.messageMeta}>
                    <Text
                      style={[
                        styles.messageTime,
                        mine && styles.myMessageMeta,
                      ]}
                    >
                      {messageTime(message.created_at)}
                    </Text>

                    {mine ? (
                      <View style={styles.deliveryStatus}>
                        <Ionicons
                          name={
                            message.delivered_at ||
                            message.read_at
                              ? "checkmark-done"
                              : "checkmark"
                          }
                          size={13}
                          color="#FFFFFF"
                        />

                        <Text style={styles.myMessageMeta}>
                          {deliveryLabel(message)}
                        </Text>
                      </View>
                    ) : null}
                  </View>
                </View>
              );
            })
          )}
        </ScrollView>

        {/* Inline API errors */}
        {error && conversation ? (
          <Text
            accessibilityRole="alert"
            style={styles.inlineError}
          >
            {error}
          </Text>
        ) : null}

        {/* Allow typing only when the backend authorizes it. */}
        {conversation?.can_send ? (
          <View style={styles.composer}>
            <TextInput
              accessibilityLabel="Write a message"
              value={draft}
              onChangeText={setDraft}
              placeholder="Write a message…"
              placeholderTextColor="#8A9A93"
              maxLength={4000}
              multiline
              editable={!sending}
              style={styles.input}
              textAlignVertical="center"
            />

            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Send message"
              disabled={sending || !draft.trim()}
              onPress={() => void send()}
              style={({ pressed }) => [
                styles.sendButton,
                (!draft.trim() || sending) &&
                  styles.sendButtonDisabled,
                pressed && styles.pressed,
              ]}
            >
              {sending ? (
                <ActivityIndicator
                  size="small"
                  color="#FFFFFF"
                />
              ) : (
                <Ionicons
                  name="send-outline"
                  size={20}
                  color="#FFFFFF"
                />
              )}
            </Pressable>
          </View>
        ) : conversation ? (
          <View style={styles.readOnlyNotice}>
            <Ionicons
              name="lock-closed-outline"
              size={16}
              color={colors.muted}
            />

            <Text style={styles.readOnlyText}>
              {conversation.read_only_reason ||
                "Chat is read-only for this job."}
            </Text>
          </View>
        ) : null}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: "#FFFFFF",
  },

  container: {
    flex: 1,
    backgroundColor: "#FFFFFF",
  },

  header: {
    minHeight: 74,
    paddingHorizontal: 16,
    paddingVertical: 13,
    flexDirection: "row",
    alignItems: "center",
    gap: 11,
    backgroundColor: "#156B5B",
  },

  avatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#FFFFFF25",
  },

  heading: {
    flex: 1,
    minWidth: 0,
    gap: 4,
  },

  headingTitle: {
    color: "#FFFFFF",
    fontSize: 15,
    fontWeight: "800",
  },

  headingSubtitle: {
    color: "#E0F0EB",
    fontSize: 11,
    fontWeight: "600",
  },

  closeButton: {
    width: 36,
    height: 36,
    borderRadius: 9,
    alignItems: "center",
    justifyContent: "center",
  },

  messageList: {
    flex: 1,
    backgroundColor: "#F5F9F7",
  },

  messageListContent: {
    padding: 15,
    gap: 10,
    flexGrow: 1,
    justifyContent: "flex-end",
  },

  emptyMessageList: {
    justifyContent: "center",
  },

  statePanel: {
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    padding: 20,
  },

  stateText: {
    color: "#64756E",
    fontSize: 13,
    textAlign: "center",
    lineHeight: 19,
  },

  errorText: {
    color: colors.danger,
    fontSize: 13,
    lineHeight: 19,
    textAlign: "center",
  },

  retryButton: {
    paddingHorizontal: 17,
    paddingVertical: 9,
    borderRadius: 10,
    backgroundColor: colors.brandSoft,
  },

  retryText: {
    color: colors.brand,
    fontSize: 13,
    fontWeight: "800",
  },

  messageBubble: {
    maxWidth: "86%",
    paddingHorizontal: 12,
    paddingTop: 10,
    paddingBottom: 7,
    borderRadius: 13,
  },

  myMessage: {
    alignSelf: "flex-end",
    backgroundColor: "#156B5B",
    borderTopRightRadius: 4,
  },

  theirMessage: {
    alignSelf: "flex-start",
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#E1EBE6",
    borderTopLeftRadius: 4,
  },

  messageBody: {
    color: "#20362F",
    fontSize: 14,
    lineHeight: 20,
  },

  myMessageBody: {
    color: "#FFFFFF",
  },

  messageMeta: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "flex-end",
    gap: 7,
    marginTop: 5,
  },

  messageTime: {
    color: "#6D7B74",
    fontSize: 9,
  },

  myMessageMeta: {
    color: "#DCEFE8",
    fontSize: 9,
  },

  deliveryStatus: {
    flexDirection: "row",
    alignItems: "center",
    gap: 2,
  },

  inlineError: {
    paddingHorizontal: 13,
    paddingVertical: 8,
    color: colors.danger,
    fontSize: 12,
    backgroundColor: "#FFF2F0",
  },

  composer: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: 9,
    padding: 12,
    borderTopWidth: 1,
    borderTopColor: "#E3ECE8",
    backgroundColor: "#FFFFFF",
  },

  input: {
    flex: 1,
    minHeight: 45,
    maxHeight: 120,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: "#D2E0DA",
    borderRadius: 12,
    color: colors.text,
    fontSize: 14,
  },

  sendButton: {
    width: 45,
    height: 45,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#156B5B",
  },

  sendButtonDisabled: {
    opacity: 0.45,
  },

  readOnlyNotice: {
    minHeight: 54,
    paddingHorizontal: 15,
    paddingVertical: 12,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    borderTopWidth: 1,
    borderTopColor: "#E5EEEA",
    backgroundColor: "#F8FAF9",
  },

  readOnlyText: {
    flexShrink: 1,
    color: "#60726B",
    textAlign: "center",
    fontSize: 12,
    lineHeight: 17,
  },

  pressed: {
    opacity: 0.78,
  },
});