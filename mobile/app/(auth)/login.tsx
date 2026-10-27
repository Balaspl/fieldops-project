
import { useState } from "react";
import {
  ActivityIndicator,
  Image,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { StatusBar } from "expo-status-bar";
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
  const [showPassword, setShowPassword] = useState(false);
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
        password,
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
      style={styles.screen}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <StatusBar style="light" />

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.card}>
          <View style={styles.brand}>
            <Image
              source={require("../../assets/images/fieldops-logo.png")}
              style={styles.logo}
              resizeMode="contain"
              accessibilityLabel="FieldOps Commander logo"
            />

            <Text style={styles.title}>FieldOps Commander</Text>
            <Text style={styles.subtitle}>
              Enterprise Field Operations Platform
            </Text>
          </View>

          <View style={styles.form}>
            <Text style={styles.label}>Email Address</Text>

            <View style={styles.inputContainer}>
              <Text style={styles.inputIcon}>✉</Text>
              <TextInput
                value={email}
                onChangeText={setEmail}
                placeholder="you@example.com"
                placeholderTextColor="#8290A3"
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="email-address"
                autoComplete="email"
                textContentType="emailAddress"
                accessibilityLabel="Email address"
                editable={!isLoading}
                returnKeyType="next"
                style={styles.input}
              />
            </View>

            <Text style={styles.label}>Password</Text>

            <View style={styles.inputContainer}>
              <Text style={styles.inputIcon}>♙</Text>
              <TextInput
                value={password}
                onChangeText={setPassword}
                placeholder="Enter your password"
                placeholderTextColor="#8290A3"
                secureTextEntry={!showPassword}
                autoCapitalize="none"
                autoComplete="password"
                textContentType="password"
                accessibilityLabel="Password"
                editable={!isLoading}
                onSubmitEditing={() => void handleLogin()}
                returnKeyType="done"
                style={styles.input}
              />

              <Pressable
                onPress={() => setShowPassword((visible) => !visible)}
                accessibilityRole="button"
                accessibilityLabel={
                  showPassword ? "Hide password" : "Show password"
                }
                style={styles.eyeButton}
              >
                <Text style={styles.eyeIcon}>
                  {showPassword ? "Hide" : "◉"}
                </Text>
              </Pressable>
            </View>

            <Pressable
              accessibilityRole="button"
              onPress={() => router.push("/(auth)/forgot-password" as any)}
              style={styles.forgotButton}
            >
              <Text style={styles.forgotText}>Forgot Password?</Text>
            </Pressable>

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
                styles.signInButton,
                pressed && styles.signInPressed,
                isLoading && styles.buttonDisabled,
              ]}
            >
              {isLoading ? (
                <ActivityIndicator color="#FFFFFF" />
              ) : (
                <Text style={styles.signInText}>Sign In  →</Text>
              )}
            </Pressable>

            <Text style={styles.footer}>
              Access is managed by your FieldOps organization.
            </Text>
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#062719",
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: "center",
    paddingHorizontal: 18,
    paddingVertical: 28,
  },
  card: {
    width: "100%",
    maxWidth: 500,
    alignSelf: "center",
    backgroundColor: "#0B2B1D",
    borderColor: "#174B32",
    borderWidth: 1,
    borderRadius: 24,
    paddingHorizontal: 22,
    paddingTop: 30,
    paddingBottom: 28,
  },
  brand: {
    alignItems: "center",
    marginBottom: 30,
  },
  logo: {
    width: "100%",
    height: 112,
    marginBottom: 14,
  },
  title: {
    color: "#E8F5EC",
    fontSize: 25,
    fontWeight: "800",
    textAlign: "center",
    letterSpacing: -0.6,
  },
  subtitle: {
    color: "#91B2A0",
    fontSize: 14,
    textAlign: "center",
    marginTop: 9,
  },
  form: {
    width: "100%",
  },
  label: {
    color: "#B5CCBE",
    fontSize: 14,
    fontWeight: "500",
    marginBottom: 9,
    marginTop: 17,
  },
  inputContainer: {
    minHeight: 56,
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: "#E7EFFD",
    borderColor: "#C6D6E9",
    borderWidth: 1,
    borderRadius: 14,
    paddingHorizontal: 14,
  },
  inputIcon: {
    color: "#16A765",
    fontSize: 21,
    width: 28,
    textAlign: "center",
    marginRight: 8,
  },
  input: {
    flex: 1,
    color: "#172033",
    fontSize: 15,
    paddingVertical: 14,
  },
  eyeButton: {
    paddingHorizontal: 5,
    paddingVertical: 10,
  },
  eyeIcon: {
    color: "#8298A7",
    fontSize: 16,
    fontWeight: "600",
  },
  forgotButton: {
    alignSelf: "flex-end",
    marginTop: 16,
    paddingVertical: 3,
  },
  forgotText: {
    color: "#80EBAF",
    fontSize: 14,
    fontWeight: "700",
  },
  error: {
    color: "#FF8B8B",
    fontSize: 13,
    lineHeight: 19,
    marginTop: 14,
  },
  signInButton: {
    minHeight: 58,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#12833F",
    borderColor: "#1A9C50",
    borderWidth: 1,
    borderRadius: 14,
    marginTop: 28,
    paddingHorizontal: 18,
  },
  signInPressed: {
    backgroundColor: "#0E7136",
  },
  buttonDisabled: {
    opacity: 0.65,
  },
  signInText: {
    color: "#FFFFFF",
    fontSize: 17,
    fontWeight: "800",
  },
  footer: {
    color: "#A5BEB0",
    fontSize: 12,
    lineHeight: 19,
    marginTop: 24,
    textAlign: "center",
  },
});
