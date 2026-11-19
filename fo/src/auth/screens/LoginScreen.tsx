
import { useEffect, useRef, useState } from "react";
import {
  Animated,
  Easing,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { router } from "expo-router";
import { useAuthStore } from "../authStore";

export default function LoginScreen() {
  const login = useAuthStore((state) => state.login);
  const isLoading = useAuthStore((state) => state.isLoading);
  const error = useAuthStore((state) => state.error);
  const clearError = useAuthStore((state) => state.clearError);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [localError, setLocalError] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  // Silver shimmer animation progress
  const shimmerProgress = useRef(new Animated.Value(0)).current;

  // Repeating silver shimmer animation
  useEffect(() => {
    let isMounted = true;
    let pauseTimer: ReturnType<typeof setTimeout> | undefined;

    const runShimmer = () => {
      if (!isMounted) return;

      shimmerProgress.setValue(0);

      Animated.timing(shimmerProgress, {
        toValue: 1,
        duration: 1200,
        easing: Easing.inOut(Easing.ease),
        useNativeDriver: true,
      }).start(({ finished }) => {
        if (!finished || !isMounted) return;

        // Wait before starting the next shimmer
        pauseTimer = setTimeout(() => {
          runShimmer();
        }, 2500);
      });
    };

    // First shimmer starts after 2 seconds
    pauseTimer = setTimeout(() => {
      runShimmer();
    }, 2000);

    return () => {
      isMounted = false;

      if (pauseTimer) {
        clearTimeout(pauseTimer);
      }

      shimmerProgress.stopAnimation();
    };
  }, [shimmerProgress]);

  const shimmerTranslateX = shimmerProgress.interpolate({
    inputRange: [0, 1],
    outputRange: [-100, 500],
  });

  const shimmerOpacity = shimmerProgress.interpolate({
    inputRange: [0, 0.08, 0.2, 0.8, 0.95, 1],
    outputRange: [0, 0.9, 0.9, 0.9, 0, 0],
  });

  const submit = async () => {
    clearError();
    setLocalError("");

    const normalizedEmail = email.trim().toLowerCase();

    if (!normalizedEmail || !password) {
      setLocalError("Enter your email address and password.");
      return;
    }

    try {
      await login(normalizedEmail, password);
      router.replace("/");
    } catch (err: unknown) {
      setLocalError(
        err instanceof Error ? err.message : "Unable to sign in."
      );
    }
  };

  return (
    <View style={styles.screen}>
      <KeyboardAvoidingView
        style={styles.keyboardContainer}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.loginCard}>
            {/* Brand */}
            <View style={styles.brand}>
              <View style={styles.logoRow}>
                <View style={styles.logoMark}>
                  <Text style={styles.logoText}>FO</Text>
                </View>

                <View>
                  <Text style={styles.brandName}>FieldOps</Text>
                  <Text style={styles.brandSmall}>
                    C O M M A N D E R
                  </Text>
                </View>
              </View>

              <Text style={styles.heading}>FieldOps Commander</Text>

              <Text style={styles.subtitle}>
                Enterprise Field Operations Platform
              </Text>
            </View>

            {/* Login Form */}
            <View style={styles.form}>
              {localError || error ? (
                <View style={styles.errorBox}>
                  <Text style={styles.errorText}>
                    {localError || error}
                  </Text>
                </View>
              ) : null}

              <Text style={styles.label}>Email Address</Text>

              <View style={styles.inputContainer}>
                <Text style={styles.inputIcon}>✉</Text>

                <TextInput
                  value={email}
                  onChangeText={setEmail}
                  placeholder="Email address"
                  placeholderTextColor="#8997A8"
                  keyboardType="email-address"
                  autoCapitalize="none"
                  autoCorrect={false}
                  autoComplete="email"
                  style={styles.input}
                  editable={!isLoading}
                />
              </View>

              <Text style={[styles.label, styles.passwordLabel]}>
                Password
              </Text>

              <View style={styles.inputContainer}>
                <Text style={styles.inputIcon}>♙</Text>

                <TextInput
                  value={password}
                  onChangeText={setPassword}
                  placeholder="Enter your password"
                  placeholderTextColor="#8997A8"
                  secureTextEntry={!showPassword}
                  autoCapitalize="none"
                  autoComplete="password"
                  style={styles.input}
                  editable={!isLoading}
                  onSubmitEditing={() => void submit()}
                  returnKeyType="go"
                />

                <Pressable
                  onPress={() => setShowPassword((value) => !value)}
                  hitSlop={10}
                >
                  <Text style={styles.eyeIcon}>
                    {showPassword ? "◉" : "◎"}
                  </Text>
                </Pressable>
              </View>

              <Pressable
                onPress={() => router.push("/forgot-password")}
                style={styles.forgotButton}
              >
                <Text style={styles.forgotText}>
                  Forgot Password?
                </Text>
              </Pressable>

              {/* Sign In Button */}
              <Pressable
                onPress={() => void submit()}
                disabled={isLoading || !email.trim() || !password}
                style={({ pressed }) => [
                  styles.signInButton,
                  pressed && styles.buttonPressed,
                  (isLoading || !email.trim() || !password) &&
                    styles.buttonDisabled,
                ]}
              >
                <View style={styles.buttonContent}>
                  <Text style={styles.signInText}>
                    {isLoading ? "Signing In..." : "Sign In"}
                  </Text>

                  {!isLoading && (
                    <Text style={styles.arrow}>→</Text>
                  )}
                </View>

                {!isLoading && (
                  <View
                    pointerEvents="none"
                    style={styles.shimmerContainer}
                  >
                    <Animated.View
                      style={[
                        styles.shimmer,
                        {
                          opacity: shimmerOpacity,
                          transform: [
                            { translateX: shimmerTranslateX },
                            { rotate: "20deg" },
                          ],
                        },
                      ]}
                    />
                  </View>
                )}
              </Pressable>

              {/* Divider */}
              <View style={styles.dividerRow}>
                <View style={styles.divider} />
                <Text style={styles.orText}>OR</Text>
                <View style={styles.divider} />
              </View>

              {/* Customer Registration */}
              <Pressable
                onPress={() => router.push("/customer-register")}
                style={({ pressed }) => [
                  styles.registerButton,
                  pressed && styles.secondaryPressed,
                ]}
              >
                <Text style={styles.registerText}>
                  New customer? Create account
                </Text>
              </Pressable>
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#073B27",
  },
  keyboardContainer: {
    flex: 1,
  },
  scrollContent: {
    flexGrow: 1,
    justifyContent: "center",
    alignItems: "center",
    paddingVertical: 20,
    paddingHorizontal: 16,
  },
  loginCard: {
    width: "100%",
    maxWidth: 464,
    backgroundColor: "#0D271B",
    borderRadius: 23,
    borderWidth: 1,
    borderColor: "rgba(105, 174, 130, 0.12)",
    paddingHorizontal: 40,
    paddingTop: 48,
    paddingBottom: 32,
  },
  brand: {
    alignItems: "center",
    marginBottom: 43,
  },
  logoRow: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    marginBottom: 25,
    gap: 9,
  },
  logoMark: {
    width: 49,
    height: 43,
    alignItems: "center",
    justifyContent: "center",
  },
  logoText: {
    color: "#00D6B0",
    fontSize: 28,
    fontWeight: "900",
    fontStyle: "italic",
  },
  brandName: {
    color: "#0757C9",
    fontSize: 20,
    fontWeight: "900",
  },
  brandSmall: {
    color: "#19A9A0",
    fontSize: 8,
    fontWeight: "900",
    marginTop: -1,
  },
  heading: {
    color: "#F0F6F1",
    fontSize: 24,
    fontWeight: "800",
    textAlign: "center",
  },
  subtitle: {
    color: "#82998C",
    fontSize: 14,
    marginTop: 13,
    textAlign: "center",
  },
  form: {
    width: "100%",
  },
  label: {
    color: "#92A99B",
    fontSize: 13,
    marginBottom: 9,
  },
  passwordLabel: {
    marginTop: 23,
  },
  inputContainer: {
    minHeight: 55,
    backgroundColor: "#E8F0FF",
    borderRadius: 13,
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: "#D5E3F8",
  },
  inputIcon: {
    color: "#81D6AF",
    fontSize: 21,
    marginRight: 12,
  },
  input: {
    flex: 1,
    color: "#172033",
    fontSize: 15,
    paddingVertical: 12,
  },
  eyeIcon: {
    color: "#A5B8C6",
    fontSize: 20,
    paddingLeft: 8,
  },
  forgotButton: {
    alignSelf: "flex-end",
    paddingVertical: 13,
    marginBottom: 12,
  },
  forgotText: {
    color: "#80DFA8",
    fontSize: 13,
    fontWeight: "800",
  },
  signInButton: {
    height: 54,
    borderRadius: 14,
    backgroundColor: "#109C50",
    overflow: "hidden",
    alignItems: "center",
    justifyContent: "center",
    elevation: 5,
    shadowColor: "#12B85B",
    shadowOpacity: 0.28,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
  },
  buttonContent: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    zIndex: 2,
  },
  signInText: {
    color: "#FFFFFF",
    fontSize: 16,
    fontWeight: "900",
  },
  arrow: {
    color: "#FFFFFF",
    fontSize: 22,
  },
  shimmerContainer: {
    ...StyleSheet.absoluteFill,
    overflow: "hidden",
  },
  shimmer: {
    position: "absolute",
    top: -20,
    left: 0,
    width: 48,
    height: 100,
    backgroundColor: "rgba(255,255,255,0.85)",
    shadowColor: "#FFFFFF",
    shadowOpacity: 0.9,
    shadowRadius: 14,
    elevation: 8,
  },
  buttonPressed: {
    opacity: 0.88,
    transform: [{ scale: 0.99 }],
  },
  buttonDisabled: {
    opacity: 0.65,
  },
  dividerRow: {
    flexDirection: "row",
    alignItems: "center",
    marginVertical: 27,
    gap: 13,
  },
  divider: {
    flex: 1,
    height: 1,
    backgroundColor: "rgba(148, 170, 153, 0.16)",
  },
  orText: {
    color: "#647B6D",
    fontSize: 12,
  },
  registerButton: {
    minHeight: 49,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: "rgba(35, 153, 83, 0.35)",
    backgroundColor: "rgba(18, 100, 51, 0.18)",
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 10,
  },
  registerText: {
    color: "#80DFA8",
    fontSize: 14,
    fontWeight: "800",
    textAlign: "center",
  },
  secondaryPressed: {
    backgroundColor: "rgba(18, 100, 51, 0.4)",
  },
  errorBox: {
    backgroundColor: "#421D25",
    borderRadius: 9,
    padding: 11,
    marginBottom: 16,
  },
  errorText: {
    color: "#FFB8BE",
    fontSize: 13,
  },
});
