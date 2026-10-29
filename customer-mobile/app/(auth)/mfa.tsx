import { useState } from "react";
import { Pressable, Text, View } from "react-native";
import { router } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { AppButton, Field, Screen } from "../../src/components/ui";
import { useAuthStore } from "../../src/auth/authStore";
import { colors, radii } from "../../src/theme";

export default function MfaScreen() {
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState(false);
  const [trustDevice, setTrustDevice] = useState(false);
  const [localError, setLocalError] = useState("");
  const { verifyMfa, verifyRecovery, isLoading, error, mfaChallenge } = useAuthStore();

  const submit = async () => {
    setLocalError("");
    try {
      if (recovery) await verifyRecovery(code);
      else await verifyMfa(code, trustDevice);
      router.replace("/(tabs)");
    } catch (e) { setLocalError(e instanceof Error ? e.message : "Verification failed."); }
  };

  if (!mfaChallenge) {
    return <Screen><View style={{ alignItems: "center", gap: 12, paddingTop: 60 }}><Ionicons name="shield-checkmark-outline" size={44} color={colors.brand} /><Text style={{ color: colors.text, fontSize: 18, fontWeight: "800" }}>Verification session expired</Text><AppButton title="Return to sign in" onPress={() => router.replace("/(auth)/login")} /></View></Screen>;
  }

  return <Screen contentStyle={{ flexGrow: 1, justifyContent: "center" }}>
    <View style={{ backgroundColor: colors.brand, borderRadius: radii.lg, padding: 24, gap: 12 }}>
      <View style={{ height: 56, width: 56, borderRadius: 18, backgroundColor: "#164B3C", alignItems: "center", justifyContent: "center" }}><Ionicons name="shield-checkmark" color="#FFFFFF" size={28} /></View>
      <Text style={{ color: "#FFFFFF", fontSize: 26, fontWeight: "900" }}>Verify it’s you</Text>
      <Text style={{ color: "#D5E6DD", fontSize: 14, lineHeight: 21 }}>Enter the code from your authenticator app to finish signing in securely.</Text>
    </View>
    <View style={{ backgroundColor: "#FFFFFF", borderColor: colors.border, borderWidth: 1, borderRadius: radii.lg, padding: 20, gap: 18 }}>
      {localError || error ? <Text style={{ color: colors.danger, fontSize: 13, lineHeight: 19 }}>{localError || error}</Text> : null}
      <Field label={recovery ? "Recovery code" : "6-digit authenticator code"} value={code} onChangeText={(value) => setCode(recovery ? value : value.replace(/\D/g, "").slice(0, 6))} keyboardType={recovery ? "default" : "number-pad"} autoCapitalize="characters" autoCorrect={false} placeholder={recovery ? "Enter a recovery code" : "000000"} maxLength={recovery ? 64 : 6} />
      {!recovery ? <Pressable onPress={() => setTrustDevice((v) => !v)} style={{ flexDirection: "row", alignItems: "center", gap: 10 }}><Ionicons name={trustDevice ? "checkbox" : "square-outline"} color={colors.brand} size={22} /><Text style={{ color: colors.text, fontSize: 13 }}>Trust this device for future sign-ins</Text></Pressable> : null}
      <AppButton title="Verify and continue" onPress={() => void submit()} loading={isLoading} disabled={recovery ? !code.trim() : code.length !== 6} />
      <Pressable onPress={() => { setRecovery((v) => !v); setCode(""); setLocalError(""); }}><Text style={{ color: colors.brandMid, fontWeight: "700", textAlign: "center", fontSize: 13 }}>{recovery ? "Use authenticator code instead" : "Use a recovery code instead"}</Text></Pressable>
      <AppButton title="Cancel sign in" kind="ghost" onPress={() => router.replace("/(auth)/login")} />
    </View>
  </Screen>;
}
