
import React, { useState } from "react";
import {
  ImageBackground,
  KeyboardAvoidingView,
  Platform,
  Text,
  View,
} from "react-native";
import { router } from "expo-router";
import {
  LockKeyhole,
  Mail,
  UserRound,
} from "lucide-react-native";

import { useAuthStore } from "../../auth/authStore";
import {
  BrandMark,
  Card,
  ErrorBanner,
  Field,
  PrimaryButton,
} from "../components/UI";
import { colors } from "../theme";

export default function LoginScreen() {
  const login = useAuthStore((state) => state.login);
  const error = useAuthStore((state) => state.error);
  const clearError = useAuthStore((state) => state.clearError);
  const isLoading = useAuthStore((state) => state.isLoading);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [localError, setLocalError] = useState("");

  const submit = async () => {
    clearError();
    setLocalError("");

    const normalizedEmail = email.trim().toLowerCase();

    if (!normalizedEmail || !password) {
      setLocalError("Enter your email address and password.");
      return;
    }

  try {
  // MFA is disabled. Login completes authentication directly.
  await login(normalizedEmail, password);

  // The home route checks the authenticated user's actual role.
  router.replace("/");
} catch (err: unknown) {
  const message =
    err instanceof Error ? err.message : "Unable to sign in.";

  setLocalError(message);
}
  };

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: colors.canvas }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <View style={{ flex: 1 }}>
        <ImageBackground
          source={require("../../../assets/banners/dispatcher-banner.png")}
          resizeMode="cover"
          style={{
            height: 235,
            justifyContent: "flex-end",
            padding: 22,
          }}
          imageStyle={{ opacity: 0.98 }}
        >
          <View
            style={{
              position: "absolute",
              inset: 0,
              backgroundColor: "rgba(4,55,32,0.45)",
            }}
          />

          <BrandMark />

          <Text
            style={{
              color: "#fff",
              fontSize: 27,
              fontWeight: "900",
              marginTop: 20,
            }}
          >
            Operations, in control.
          </Text>

          <Text
            style={{
              color: "#EAF8EF",
              fontSize: 13,
              marginTop: 5,
            }}
          >
            FieldOps Commander
          </Text>
        </ImageBackground>

        <View
          style={{
            flex: 1,
            padding: 20,
            justifyContent: "center",
          }}
        >
          <Card style={{ padding: 20, gap: 18 }}>
            <View style={{ gap: 5 }}>
              <Text
                style={{
                  color: colors.ink,
                  fontSize: 23,
                  fontWeight: "900",
                }}
              >
                Welcome back
              </Text>

              <Text
                style={{
                  color: colors.muted,
                  fontSize: 12,
                  lineHeight: 18,
                }}
              >
                Sign in to access your FieldOps account.
              </Text>
            </View>

            {localError || error ? (
              <ErrorBanner
                message={localError || error || "Sign-in failed"}
              />
            ) : null}

            <Field
              label="EMAIL ADDRESS"
              value={email}
              onChangeText={setEmail}
              placeholder="you@example.com"
              autoCapitalize="none"
              keyboardType="email-address"
              autoComplete="email"
              left={<Mail size={17} color={colors.muted} />}
            />

            <Field
              label="PASSWORD"
              value={password}
              onChangeText={setPassword}
              placeholder="Enter your password"
              secureTextEntry
              autoComplete="password"
              left={<LockKeyhole size={17} color={colors.muted} />}
              onSubmitEditing={submit}
            />

            <PrimaryButton
              title="Sign in to FieldOps"
              onPress={submit}
              loading={isLoading}
            />

            <View
              style={{
                flexDirection: "row",
                gap: 8,
                alignItems: "center",
                justifyContent: "center",
                marginTop: 2,
              }}
            >
              <UserRound size={14} color={colors.muted} />

              <Text
                style={{
                  color: colors.muted,
                  fontSize: 11,
                  textAlign: "center",
                }}
              >
                Access is managed by your FieldOps organization.
              </Text>
            </View>
          </Card>

          <Text
            style={{
              color: colors.muted,
              fontSize: 10,
              textAlign: "center",
              marginTop: 18,
            }}
          >
            FieldOps Commander · Secure access
          </Text>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}
