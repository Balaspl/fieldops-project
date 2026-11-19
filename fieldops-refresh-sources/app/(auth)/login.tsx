import { useState } from "react";
import {
  ActivityIndicator,
  Image,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StatusBar,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { router } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useAuthStore } from "../../src/auth/authStore";

const BG = "#05442E";
const PANEL = "#073B29";
const BORDER = "#15563A";
const PRIMARY = "#118B45";
const MINT = "#69E7AE";
const LABEL = "#A9C4B4";
const INPUT_BG = "#E8F0FF";
const INPUT_TEXT = "#14251C";

export default function CustomerLoginScreen() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const { login, isLoading, error, clearError } = useAuthStore();

  const submit = async () => {
    clearError();
    try {
      const result = await login(email.trim().toLowerCase(), password);
      router.replace(result.mfaRequired ? "/(auth)/mfa" : "/(tabs)");
    } catch {
      // The authentication store exposes the customer-safe error message.
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: BG }} edges={["top", "bottom"]}>
      <StatusBar barStyle="light-content" backgroundColor={BG} />
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
      >
        <ScrollView
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{
            flexGrow: 1,
            justifyContent: "center",
            paddingHorizontal: 24,
            paddingTop: 18,
            paddingBottom: 24,
          }}
          showsVerticalScrollIndicator={false}
        >
          <View style={{ width: "100%", maxWidth: 440, alignSelf: "center" }}>
            <Image
              source={require("../../assets/images/fieldops-logo-dark.png")}
              resizeMode="contain"
              style={{ width: 165, height: 54, alignSelf: "center", marginBottom: 13 }}
              accessibilityLabel="FieldOps Commander logo"
            />

            <Text
              style={{
                color: "#F0F8F3",
                fontSize: 23,
                lineHeight: 29,
                fontWeight: "900",
                textAlign: "center",
                letterSpacing: -0.4,
              }}
            >
              FieldOps Commander
            </Text>
            <Text
              style={{
                color: "#A6BFB1",
                fontSize: 13,
                marginTop: 5,
                marginBottom: 27,
                textAlign: "center",
              }}
            >
              Customer service and home maintenance
            </Text>

            <View
              style={{
                backgroundColor: PANEL,
                borderWidth: 1,
                borderColor: BORDER,
                borderRadius: 24,
                padding: 20,
                gap: 16,
              }}
            >
              <View style={{ gap: 4, marginBottom: 2 }}>
                <Text style={{ color: "#EAF5EE", fontSize: 17, fontWeight: "800" }}>
                  Welcome back
                </Text>
                <Text style={{ color: LABEL, fontSize: 12, lineHeight: 18 }}>
                  Sign in to manage your service requests.
                </Text>
              </View>

              {error ? (
                <View
                  style={{
                    padding: 11,
                    borderRadius: 10,
                    backgroundColor: "#3D211F",
                    borderWidth: 1,
                    borderColor: "#85453E",
                  }}
                >
                  <Text style={{ color: "#FFD8D4", fontSize: 12, lineHeight: 18 }}>
                    {error}
                  </Text>
                </View>
              ) : null}

              <View style={{ gap: 7 }}>
                <Text style={{ color: LABEL, fontSize: 12, fontWeight: "700" }}>
                  Email address
                </Text>
                <View
                  style={{
                    minHeight: 48,
                    flexDirection: "row",
                    alignItems: "center",
                    gap: 10,
                    paddingHorizontal: 12,
                    borderRadius: 12,
                    backgroundColor: INPUT_BG,
                    borderWidth: 1,
                    borderColor: "#D7E4F6",
                  }}
                >
                  <Ionicons name="mail-outline" size={18} color="#35B983" />
                  <TextInput
                    value={email}
                    onChangeText={(value) => { setEmail(value); clearError(); }}
                    placeholder="you@example.com"
                    placeholderTextColor="#8796A8"
                    keyboardType="email-address"
                    autoCapitalize="none"
                    autoCorrect={false}
                    textContentType="emailAddress"
                    returnKeyType="next"
                    style={{ flex: 1, paddingVertical: 10, color: INPUT_TEXT, fontSize: 14 }}
                    accessibilityLabel="Email address"
                  />
                </View>
              </View>

              <View style={{ gap: 7 }}>
                <Text style={{ color: LABEL, fontSize: 12, fontWeight: "700" }}>
                  Password
                </Text>
                <View
                  style={{
                    minHeight: 48,
                    flexDirection: "row",
                    alignItems: "center",
                    gap: 10,
                    paddingHorizontal: 12,
                    borderRadius: 12,
                    backgroundColor: INPUT_BG,
                    borderWidth: 1,
                    borderColor: "#D7E4F6",
                  }}
                >
                  <Ionicons name="lock-closed-outline" size={18} color="#35B983" />
                  <TextInput
                    value={password}
                    onChangeText={(value) => { setPassword(value); clearError(); }}
                    placeholder="Enter your password"
                    placeholderTextColor="#8796A8"
                    secureTextEntry={!showPassword}
                    textContentType="password"
                    returnKeyType="done"
                    onSubmitEditing={() => void submit()}
                    style={{ flex: 1, paddingVertical: 10, color: INPUT_TEXT, fontSize: 14 }}
                    accessibilityLabel="Password"
                  />
                  <Pressable
                    onPress={() => setShowPassword((value) => !value)}
                    hitSlop={8}
                    accessibilityRole="button"
                    accessibilityLabel={showPassword ? "Hide password" : "Show password"}
                  >
                    <Ionicons
                      name={showPassword ? "eye-off-outline" : "eye-outline"}
                      size={19}
                      color="#8AA2B0"
                    />
                  </Pressable>
                </View>
                <Pressable
                  onPress={() => router.push("/(auth)/forgot-password")}
                  style={{ alignSelf: "flex-end", paddingVertical: 3 }}
                >
                  <Text style={{ color: MINT, fontSize: 12, fontWeight: "800" }}>
                    Forgot password?
                  </Text>
                </Pressable>
              </View>

              <Pressable
                onPress={() => void submit()}
                disabled={!email.trim() || !password || isLoading}
                accessibilityRole="button"
                style={({ pressed }) => ({
                  minHeight: 49,
                  borderRadius: 12,
                  backgroundColor: !email.trim() || !password || isLoading ? "#537D68" : PRIMARY,
                  alignItems: "center",
                  justifyContent: "center",
                  flexDirection: "row",
                  gap: 9,
                  opacity: pressed ? 0.86 : 1,
                  shadowColor: PRIMARY,
                  shadowOpacity: 0.18,
                  shadowRadius: 10,
                  shadowOffset: { width: 0, height: 4 },
                  elevation: 3,
                })}
              >
                {isLoading ? (
                  <ActivityIndicator color="#FFFFFF" />
                ) : (
                  <>
                    <Text style={{ color: "#FFFFFF", fontSize: 14, fontWeight: "900" }}>
                      Sign in
                    </Text>
                    <Ionicons name="arrow-forward" size={17} color="#FFFFFF" />
                  </>
                )}
              </Pressable>

              <View style={{ flexDirection: "row", alignItems: "center", gap: 10, marginTop: 1 }}>
                <View style={{ flex: 1, height: 1, backgroundColor: "#234D37" }} />
                <Text style={{ color: "#8EAA9A", fontSize: 11 }}>OR</Text>
                <View style={{ flex: 1, height: 1, backgroundColor: "#234D37" }} />
              </View>

              <Pressable
                onPress={() => router.push("/(auth)/register")}
                accessibilityRole="button"
                style={({ pressed }) => ({
                  minHeight: 47,
                  borderRadius: 12,
                  borderWidth: 1,
                  borderColor: "#167044",
                  alignItems: "center",
                  justifyContent: "center",
                  flexDirection: "row",
                  gap: 8,
                  backgroundColor: pressed ? "#10432D" : "transparent",
                })}
              >
                <Ionicons name="person-add-outline" size={17} color={MINT} />
                <Text style={{ color: MINT, fontSize: 13, fontWeight: "800" }}>
                  Create customer account
                </Text>
              </Pressable>

              <Text style={{ color: "#6F9480", fontSize: 10, lineHeight: 16, textAlign: "center" }}>
                Secure sign-in for FieldOps customer accounts only.
              </Text>
            </View>

            <View style={{ marginTop: 20, alignItems: "center" }}>
              <Text style={{ color: "#9AB6A6", fontSize: 11, textAlign: "center" }}>
                Need help with a service? Customer support is available after sign-in.
              </Text>
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
