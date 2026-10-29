import { useCallback, useState } from "react";
import { Alert, Text, View } from "react-native";
import { router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { useAuthStore } from "../../src/auth/authStore";
import { Card, Header, LinkRow, Screen, AppButton } from "../../src/components/ui";
import { colors } from "../../src/theme";
import { customerApi } from "../../src/api/customer";

export default function CustomerAccountScreen() {
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const [profileName, setProfileName] = useState("");

  useFocusEffect(
    useCallback(() => {
      let active = true;

      customerApi
        .profile()
        .then((profile) => {
          if (active) {
            setProfileName(profile.full_name?.trim() || "");
          }
        })
        .catch(() => {
          if (active) {
            setProfileName("");
          }
        });

      return () => {
        active = false;
      };
    }, []),
  );
  const [loggingOut, setLoggingOut] = useState(false);
  const name =
    profileName ||
    [user?.first_name, user?.last_name]
      .filter(Boolean)
      .join(" ")
      .trim() ||
    "FieldOps customer";
  const confirmLogout = () => Alert.alert("Sign out?", "You’ll need to sign in again to view your service details.", [
    { text: "Cancel", style: "cancel" },
    { text: "Sign out", style: "destructive", onPress: () => { setLoggingOut(true); void logout().finally(() => { setLoggingOut(false); router.replace("/(auth)/login"); }); } },
  ]);

  return <Screen>
    <Header title="Your account" subtitle="Profile, preferences and customer support" />
    <Card style={{ backgroundColor: colors.brand, borderColor: colors.brand, padding: 20 }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 14 }}>
        <View style={{ height: 58, width: 58, borderRadius: 20, backgroundColor: colors.accent, alignItems: "center", justifyContent: "center" }}><Text style={{ color: colors.brand, fontSize: 23, fontWeight: "900" }}>{(name[0] || user?.email?.[0] || "C").toUpperCase()}</Text></View>
        <View style={{ flex: 1, gap: 4 }}><Text style={{ fontSize: 18, fontWeight: "900", color: "white" }}>{name}</Text><Text style={{ color: "#D5E6DD", fontSize: 12 }}>{user?.email}</Text><Text style={{ color: colors.accent, fontSize: 10, fontWeight: "800", letterSpacing: 0.6 }}>CUSTOMER ACCOUNT</Text></View>
        <Ionicons name="shield-checkmark" color={colors.accent} size={22} />
      </View>
    </Card>
    <Card style={{ gap: 0 }}>
      <Text style={{ fontSize: 12, fontWeight: "800", color: colors.muted, letterSpacing: 0.8, marginBottom: 4 }}>YOUR DETAILS</Text>
      <LinkRow icon="person-outline" title="Profile" subtitle="Name, phone and service address" onPress={() => router.push("/profile")} />
      <LinkRow icon="notifications-outline" title="Notifications" subtitle="Service updates and unread messages" onPress={() => router.push("/notifications")} />
      <LinkRow icon="options-outline" title="Settings" subtitle="Notification preferences and password" onPress={() => router.push("/settings")} />
    </Card>
    <Card style={{ gap: 0 }}>
      <Text style={{ fontSize: 12, fontWeight: "800", color: colors.muted, letterSpacing: 0.8, marginBottom: 4 }}>SERVICES & BILLING</Text>
      <LinkRow icon="time-outline" title="Service history" subtitle="Past services and feedback" onPress={() => router.push("/history")} />
      <LinkRow icon="receipt-outline" title="Invoices and payments" subtitle="Invoice totals and recorded payment status" onPress={() => router.push("/invoices")} />
      <LinkRow icon="chatbubbles-outline" title="Customer support" subtitle="Create and track support requests" onPress={() => router.push("/support")} />
    </Card>
    <AppButton title="Sign out" kind="danger" icon="log-out-outline" onPress={confirmLogout} loading={loggingOut} />
    <Text style={{ color: colors.muted, fontSize: 11, textAlign: "center" }}>FieldOps Customer · Version 1.0.0</Text>
  </Screen>;
}
