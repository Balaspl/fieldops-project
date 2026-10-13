
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
import { useAuthStore } from "../../src/auth/authStore";

export default function LoginScreen() {
  const router = useRouter();

  const login = useAuthStore((state) => state.login);
  const authError = useAuthStore((state) => state.error);
  const clearError = useAuthStore((state) => state.clearError);
  const isLoading = useAuthStore((state) => state.isLoading);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  async function handleLogin() {
    setValidationError(null);
    clearError();

    const normalizedEmail = email.trim().toLowerCase();

    if (!normalizedEmail || !password) {
      setValidationError("Enter your email address and password.");
      return;
    }

    try {
      const result = await login({
        email: normalizedEmail,
        password
      });

      if (result.mfa_required) {
        router.replace("/(auth)/mfa");
        return;
      }

      router.replace("/(app)/dashboard");
    } catch {
      // The authentication store records the error message.
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.keyboardView}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={styles.container}>
        <View style={styles.brand}>
          <Text style={styles.logo}>FieldOps</Text>
          <Text style={styles.subtitle}>
            Sign in to your technician workspace
          </Text>
        </View>

        <View style={styles.form}>
          <Text style={styles.label}>Email address</Text>
          <TextInput
            value={email}
            onChangeText={setEmail}
            placeholder="you@example.com"
            placeholderTextColor="#94A3B8"
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="email-address"
            autoComplete="email"
            textContentType="emailAddress"
            accessibilityLabel="Email address"
            editable={!isLoading}
            style={styles.input}
          />

          <Text style={styles.label}>Password</Text>
          <TextInput
            value={password}
            onChangeText={setPassword}
            placeholder="Enter your password"
            placeholderTextColor="#94A3B8"
            secureTextEntry
            autoCapitalize="none"
            autoComplete="password"
            textContentType="password"
            accessibilityLabel="Password"
            editable={!isLoading}
            onSubmitEditing={() => void handleLogin()}
            style={styles.input}
          />

          {validationError || authError ? (
            <Text accessibilityRole="alert" style={styles.error}>
              {validationError ?? authError}
            </Text>
          ) : null}

          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Sign in"
            disabled={isLoading}
            onPress={() => void handleLogin()}
            style={({ pressed }) => [
              styles.button,
              pressed && styles.buttonPressed,
              isLoading && styles.buttonDisabled
            ]}
          >
            {isLoading ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.buttonText}>Sign in</Text>
            )}
          </Pressable>

          <Text style={styles.footer}>
            Access is managed by your FieldOps organization.
          </Text>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  keyboardView: {
    flex: 1,
    backgroundColor: "#F8FAFC"
  },
  container: {
    flex: 1,
    justifyContent: "center",
    paddingHorizontal: 26,
    paddingVertical: 32
  },
  brand: {
    marginBottom: 36
  },
  logo: {
    color: "#1D4ED8",
    fontSize: 34,
    fontWeight: "800",
    letterSpacing: -0.5
  },
  subtitle: {
    color: "#64748B",
    fontSize: 16,
    lineHeight: 23,
    marginTop: 8
  },
  form: {
    width: "100%"
  },
  label: {
    color: "#334155",
    fontSize: 14,
    fontWeight: "600",
    marginBottom: 8,
    marginTop: 16
  },
  input: {
    backgroundColor: "#FFFFFF",
    borderColor: "#CBD5E1",
    borderWidth: 1,
    borderRadius: 10,
    color: "#0F172A",
    fontSize: 16,
    minHeight: 52,
    paddingHorizontal: 14
  },
  error: {
    color: "#B91C1C",
    fontSize: 14,
    lineHeight: 20,
    marginTop: 14
  },
  button: {
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#1D4ED8",
    borderRadius: 10,
    minHeight: 52,
    marginTop: 24,
    paddingHorizontal: 18
  },
  buttonPressed: {
    backgroundColor: "#1E40AF"
  },
  buttonDisabled: {
    opacity: 0.65
  },
  buttonText: {
    color: "#FFFFFF",
    fontSize: 16,
    fontWeight: "700"
  },
  footer: {
    color: "#64748B",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 20,
    textAlign: "center"
  }
});
