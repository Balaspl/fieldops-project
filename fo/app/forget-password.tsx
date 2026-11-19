
import { useState } from "react";
import {
  Alert,
  Text,
  TextInput,
  View,
  StyleSheet,
} from "react-native";
import { router } from "expo-router";

import { customerApi } from "../src/customer/api/customer";
import { getApiErrorMessage } from "../src/api/client";
import {
  Screen,
  Heading,
  Card,
  ActionButton,
  ErrorMessage,
} from "../src/components/ui";
import { colors } from "../src/theme";

export default function ForgotPasswordScreen() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [requested, setRequested] = useState(false);

  const submit = async () => {
    setError("");

    const normalized = email.trim().toLowerCase();

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized)) {
      setError("Enter a valid email address.");
      return;
    }

    setBusy(true);

    try {
      const response =
        await customerApi.requestPasswordReset(normalized);

      setRequested(true);

      Alert.alert(
        "Check your email",
        response.message ||
          "If an account with that email exists, a password reset link has been sent.",
      );
    } catch (e) {
      setError(
        getApiErrorMessage(
          e,
          "Could not request a password reset. Try again shortly.",
        ),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen scroll>
      <View style={styles.container}>
        <Heading
          title="Reset your password"
          subtitle="Request a secure reset link for your FieldOps account."
        />

        <View style={styles.iconContainer}>
          <Text style={styles.icon}>🔐</Text>
        </View>

        <Heading
          title={requested ? "Request submitted" : "Forgot your password?"}
          subtitle={
            requested
              ? "For security, FieldOps uses the same confirmation whether or not an account matches. Check your inbox and spam folder."
              : "Enter the email address associated with your FieldOps account. We will email a reset link if the account exists."
          }
        />

        {error ? <ErrorMessage message={error} /> : null}

        <Card>
          <Text style={styles.label}>EMAIL ADDRESS</Text>

          <TextInput
            value={email}
            onChangeText={(value) => {
              setEmail(value);
              setError("");
            }}
            placeholder="you@example.com"
            placeholderTextColor={colors.muted}
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="email"
            editable={!requested && !busy}
            style={styles.input}
          />

          {!requested ? (
            <ActionButton
              title={busy ? "Sending..." : "Email reset link"}
              onPress={() => void submit()}
              disabled={busy || !email.trim()}
            />
          ) : (
            <ActionButton
              title="Request another link"
              secondary
              onPress={() => {
                setRequested(false);
                setError("");
              }}
            />
          )}

          <ActionButton
            title="Return to sign in"
            secondary
            onPress={() => router.replace("/login")}
          />
        </Card>

        <Text style={styles.footer}>
          Password reset links are delivered through the configured
          FieldOps email service.
        </Text>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: "center",
    gap: 20,
  },
  iconContainer: {
    alignSelf: "center",
    width: 76,
    height: 76,
    borderRadius: 24,
    backgroundColor: "#E5F3EA",
    alignItems: "center",
    justifyContent: "center",
  },
  icon: {
    fontSize: 32,
  },
  label: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: "800",
  },
  input: {
    minHeight: 50,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: 14,
    color: colors.ink,
    fontSize: 15,
  },
  footer: {
    color: colors.muted,
    fontSize: 11,
    lineHeight: 18,
    textAlign: "center",
  },
});
