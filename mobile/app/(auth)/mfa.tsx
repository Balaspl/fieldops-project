
import { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View
} from "react-native";
import { useRouter } from "expo-router";
import {
  verifyMfa,
  verifyMfaRecovery
} from "../../src/auth/mfaService";
import { useAuthStore } from "../../src/auth/authStore";

export default function MfaScreen() {
  const router = useRouter();
  const restoreSession = useAuthStore((state) => state.restoreSession);

  const [code, setCode] = useState("");
  const [recoveryCode, setRecoveryCode] = useState("");
  const [useRecoveryCode, setUseRecoveryCode] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleVerify() {
    const value = (
      useRecoveryCode ? recoveryCode : code
    ).trim();

    if (!value) {
      setError(
        useRecoveryCode
          ? "Enter your recovery code."
          : "Enter your verification code."
      );
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const result = useRecoveryCode
        ? await verifyMfaRecovery({ recovery_code: value })
        : await verifyMfa({ code: value });

      if (!result.access_token) {
        throw new Error(
          "Verification completed without an access token. Please check the backend response contract."
        );
      }

      await restoreSession();

      const authenticated = useAuthStore.getState().isAuthenticated;

      if (!authenticated) {
        throw new Error(
          "Your session could not be restored after verification."
        );
      }

      router.replace("/(app)/dashboard");
    } catch (verificationError: unknown) {
      setError(
        verificationError instanceof Error
          ? verificationError.message
          : "Verification failed. Please try again."
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={styles.content}>
        <Text style={styles.brand}>FieldOps</Text>
        <Text style={styles.title}>Verify your identity</Text>
        <Text style={styles.description}>
          Enter the verification code required by your organization.
        </Text>

        <Text style={styles.label}>
          {useRecoveryCode ? "Recovery code" : "Verification code"}
        </Text>

        <TextInput
          value={useRecoveryCode ? recoveryCode : code}
          onChangeText={useRecoveryCode ? setRecoveryCode : setCode}
          placeholder={
            useRecoveryCode ? "Enter recovery code" : "Enter verification code"
          }
          placeholderTextColor="#94A3B8"
          autoCapitalize="none"
          autoCorrect={false}
          editable={!isSubmitting}
          accessibilityLabel={
            useRecoveryCode ? "Recovery code" : "Verification code"
          }
          style={styles.input}
        />

        {error ? (
          <Text accessibilityRole="alert" style={styles.error}>
            {error}
          </Text>
        ) : null}

        <Pressable
          accessibilityRole="button"
          disabled={isSubmitting}
          onPress={() => void handleVerify()}
          style={({ pressed }) => [
            styles.button,
            pressed && styles.buttonPressed,
            isSubmitting && styles.disabled
          ]}
        >
          {isSubmitting ? (
            <ActivityIndicator color="#FFFFFF" />
          ) : (
            <Text style={styles.buttonText}>Verify and continue</Text>
          )}
        </Pressable>

        <Pressable
          accessibilityRole="button"
          disabled={isSubmitting}
          onPress={() => {
            setUseRecoveryCode((current) => !current);
            setError(null);
          }}
          style={styles.secondaryButton}
        >
          <Text style={styles.secondaryButtonText}>
            {useRecoveryCode
              ? "Use verification code instead"
              : "Use a recovery code"}
          </Text>
        </Pressable>

        <Pressable
          accessibilityRole="button"
          disabled={isSubmitting}
          onPress={() => router.replace("/(auth)/login")}
          style={styles.secondaryButton}
        >
          <Text style={styles.secondaryButtonText}>Back to sign in</Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#F8FAFC"
  },
  content: {
    flex: 1,
    justifyContent: "center",
    paddingHorizontal: 26,
    paddingVertical: 32
  },
  brand: {
    color: "#1D4ED8",
    fontSize: 29,
    fontWeight: "800",
    marginBottom: 24
  },
  title: {
    color: "#0F172A",
    fontSize: 25,
    fontWeight: "800",
    marginBottom: 10
  },
  description: {
    color: "#64748B",
    fontSize: 15,
    lineHeight: 22,
    marginBottom: 26
  },
  label: {
    color: "#334155",
    fontSize: 14,
    fontWeight: "600",
    marginBottom: 8
  },
  input: {
    backgroundColor: "#FFFFFF",
    borderColor: "#CBD5E1",
    borderWidth: 1,
    borderRadius: 10,
    minHeight: 52,
    paddingHorizontal: 14,
    color: "#0F172A",
    fontSize: 16
  },
  error: {
    color: "#B91C1C",
    fontSize: 14,
    lineHeight: 20,
    marginTop: 14
  },
  button: {
    minHeight: 52,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#1D4ED8",
    borderRadius: 10,
    paddingHorizontal: 18,
    marginTop: 22
  },
  buttonPressed: {
    backgroundColor: "#1E40AF"
  },
  disabled: {
    opacity: 0.6
  },
  buttonText: {
    color: "#FFFFFF",
    fontSize: 15,
    fontWeight: "700"
  },
  secondaryButton: {
    alignItems: "center",
    paddingVertical: 13,
    marginTop: 8
  },
  secondaryButtonText: {
    color: "#1D4ED8",
    fontSize: 14,
    fontWeight: "600"
  }
});
