import { useState } from "react";
import { Alert, Text, View } from "react-native";
import { router } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { customerApi } from "../../src/api/customer";
import { getApiErrorMessage } from "../../src/api/client";
import { AppButton, Card, Field, Header, Screen } from "../../src/components/ui";
import { colors } from "../../src/theme";

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
      const response = await customerApi.requestPasswordReset(normalized);
      setRequested(true);
      Alert.alert("Check your email", response.message || "If an account with that email exists, a password reset link has been sent.");
    } catch (e) {
      setError(getApiErrorMessage(e, "Could not request a password reset. Try again shortly."));
    } finally {
      setBusy(false);
    }
  };

  return <Screen>
    <Header title="Reset your password" subtitle="Request a secure reset link for your FieldOps account" right={<AppButton title="Back" kind="ghost" onPress={() => router.back()} />} />
    <View style={{ alignItems: "center", paddingVertical: 10, gap: 10 }}>
      <View style={{ width: 72, height: 72, borderRadius: 24, backgroundColor: colors.brandSoft, alignItems: "center", justifyContent: "center" }}><Ionicons name="lock-open-outline" size={32} color={colors.brand} /></View>
      <Text style={{ color: colors.text, fontSize: 21, fontWeight: "900", textAlign: "center" }}>{requested ? "Request submitted" : "Forgot your password?"}</Text>
      <Text style={{ color: colors.muted, fontSize: 13, textAlign: "center", lineHeight: 20 }}>{requested ? "For security, FieldOps uses the same confirmation whether or not an account matches. Check your inbox and spam folder." : "Enter the email address associated with your customer account. FieldOps will email a single-use reset link if the account exists."}</Text>
    </View>
    {error ? <Card style={{ backgroundColor: "#FDECEA", borderColor: "#F1C4C0" }}><Text style={{ color: colors.danger, fontSize: 13, lineHeight: 20 }}>{error}</Text></Card> : null}
    <Card>
      <Field label="Email address" value={email} onChangeText={(value) => { setEmail(value); setError(""); }} placeholder="you@example.com" keyboardType="email-address" autoCapitalize="none" autoCorrect={false} textContentType="emailAddress" editable={!requested} />
      {!requested ? <AppButton title="Email reset link" icon="mail-outline" onPress={() => void submit()} loading={busy} disabled={!email.trim()} /> : <AppButton title="Request another link" icon="refresh-outline" kind="secondary" onPress={() => setRequested(false)} />}
      <AppButton title="Return to sign in" kind="ghost" onPress={() => router.replace("/(auth)/login")} />
    </Card>
    <Text style={{ color: colors.muted, fontSize: 11, lineHeight: 17, textAlign: "center" }}>Password reset links are delivered by the configured FieldOps email service and open the reset page configured by your backend administrator.</Text>
  </Screen>;
}
