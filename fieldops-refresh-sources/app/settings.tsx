import { useEffect, useState } from "react";
import { Alert, Switch, Text, View } from "react-native";
import { router } from "expo-router";
import { customerApi } from "../src/api/customer";
import { getApiErrorMessage } from "../src/api/client";
import { AppButton, Card, ErrorState, Field, Header, LoadingView, Screen } from "../src/components/ui";
import type { NotificationPreferences } from "../src/types/api";
import { colors } from "../src/theme";

const defaultPrefs: Partial<NotificationPreferences> = { sms_enabled: true, email_enabled: true, push_enabled: true, portal_enabled: true, daily_engagement_enabled: false, preferred_locale: "en", timezone: "Asia/Kolkata", quiet_hours_start: "22:00", quiet_hours_end: "08:00" };

function PreferenceToggle({ label, description, value, onChange }: { label: string; description: string; value: boolean; onChange: (v: boolean) => void }) {
  return <View style={{ flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 11, borderBottomWidth: 1, borderBottomColor: colors.border }}><View style={{ flex: 1, gap: 4 }}><Text style={{ color: colors.text, fontSize: 14, fontWeight: "700" }}>{label}</Text><Text style={{ color: colors.muted, fontSize: 12, lineHeight: 17 }}>{description}</Text></View><Switch value={value} onValueChange={onChange} trackColor={{ false: "#D7DFD9", true: colors.accent }} thumbColor={value ? colors.brand : "#FFFFFF"} /></View>;
}

export default function CustomerSettingsScreen() {
  const [preferences, setPreferences] = useState<Partial<NotificationPreferences>>(defaultPrefs);
  const [loading, setLoading] = useState(true);
  const [savingPreferences, setSavingPreferences] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [passwordError, setPasswordError] = useState("");

  useEffect(() => {
    let active = true;
    customerApi.notificationPreferences().then((value) => { if (active) setPreferences(value); })
      .catch((e) => { if (active) setError(getApiErrorMessage(e, "Could not load notification preferences.")); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const setBool = (key: keyof NotificationPreferences, value: boolean) => setPreferences((old) => ({ ...old, [key]: value }));
  const savePrefs = async () => {
    setError(""); setSavingPreferences(true);
    try {
      const payload = {
        sms_enabled: Boolean(preferences.sms_enabled), email_enabled: Boolean(preferences.email_enabled), push_enabled: Boolean(preferences.push_enabled),
        portal_enabled: Boolean(preferences.portal_enabled), daily_engagement_enabled: Boolean(preferences.daily_engagement_enabled),
        preferred_locale: String(preferences.preferred_locale || "en"), timezone: String(preferences.timezone || "Asia/Kolkata"),
        quiet_hours_start: String(preferences.quiet_hours_start || "22:00"), quiet_hours_end: String(preferences.quiet_hours_end || "08:00"),
      };
      setPreferences(await customerApi.updateNotificationPreferences(payload));
      Alert.alert("Preferences saved", "Your notification preferences have been updated.");
    } catch (e) { setError(getApiErrorMessage(e, "Could not save notification preferences.")); }
    finally { setSavingPreferences(false); }
  };

  const changePassword = async () => {
    setPasswordError("");
    if (!currentPassword) { setPasswordError("Enter your current password."); return; }
    if (newPassword.length < 8) { setPasswordError("Your new password must contain at least 8 characters."); return; }
    if (newPassword !== confirmPassword) { setPasswordError("The new password and confirmation do not match."); return; }
    setSavingPassword(true);
    try {
      await customerApi.changePassword(currentPassword, newPassword, confirmPassword);
      setCurrentPassword(""); setNewPassword(""); setConfirmPassword("");
      Alert.alert("Password changed", "Your password has been changed successfully.");
    } catch (e) { setPasswordError(getApiErrorMessage(e, "Could not change your password.")); }
    finally { setSavingPassword(false); }
  };

  if (loading) return <Screen><LoadingView message="Loading settings…" /></Screen>;
  return <Screen>
    <Header title="Settings" subtitle="Control customer notifications and account security" />
    {error ? <ErrorState message={error} /> : null}
    <Card>
      <Text style={{ color: colors.text, fontSize: 17, fontWeight: "800" }}>Notification preferences</Text>
      <Text style={{ color: colors.muted, fontSize: 12, lineHeight: 18 }}>Choose how FieldOps should contact you. Available delivery channels depend on server-side notification configuration.</Text>
      <PreferenceToggle label="In-app / portal updates" description="Service status and account messages inside FieldOps" value={Boolean(preferences.portal_enabled)} onChange={(v) => setBool("portal_enabled", v)} />
      <PreferenceToggle label="Email updates" description="Service progress and important account messages" value={Boolean(preferences.email_enabled)} onChange={(v) => setBool("email_enabled", v)} />
      <PreferenceToggle label="SMS updates" description="Text messages where enabled for your account" value={Boolean(preferences.sms_enabled)} onChange={(v) => setBool("sms_enabled", v)} />
      <PreferenceToggle label="Push preference" description="Saved server preference; native customer push registration is not yet available in the backend contract" value={Boolean(preferences.push_enabled)} onChange={(v) => setBool("push_enabled", v)} />
      <PreferenceToggle label="Daily engagement messages" description="Optional non-urgent service reminders where configured" value={Boolean(preferences.daily_engagement_enabled)} onChange={(v) => setBool("daily_engagement_enabled", v)} />
      <Field label="Preferred language / locale" value={String(preferences.preferred_locale || "en")} onChangeText={(v) => setPreferences((old) => ({ ...old, preferred_locale: v }))} placeholder="en" autoCapitalize="none" />
      <Field label="Time zone" value={String(preferences.timezone || "Asia/Kolkata")} onChangeText={(v) => setPreferences((old) => ({ ...old, timezone: v }))} placeholder="Asia/Kolkata" autoCapitalize="none" />
      <View style={{ flexDirection: "row", gap: 10 }}><View style={{ flex: 1 }}><Field label="Quiet hours start" value={String(preferences.quiet_hours_start || "22:00")} onChangeText={(v) => setPreferences((old) => ({ ...old, quiet_hours_start: v }))} placeholder="22:00" /></View><View style={{ flex: 1 }}><Field label="Quiet hours end" value={String(preferences.quiet_hours_end || "08:00")} onChangeText={(v) => setPreferences((old) => ({ ...old, quiet_hours_end: v }))} placeholder="08:00" /></View></View>
      <AppButton title="Save notification settings" onPress={() => void savePrefs()} loading={savingPreferences} icon="checkmark-circle-outline" />
    </Card>
    <Card>
      <Text style={{ color: colors.text, fontSize: 17, fontWeight: "800" }}>Change password</Text>
      {passwordError ? <Text style={{ color: colors.danger, fontSize: 13, lineHeight: 19 }}>{passwordError}</Text> : null}
      <Field label="Current password" value={currentPassword} onChangeText={setCurrentPassword} secureTextEntry textContentType="password" placeholder="Current password" />
      <Field label="New password" value={newPassword} onChangeText={setNewPassword} secureTextEntry textContentType="newPassword" placeholder="At least 8 characters" />
      <Field label="Confirm new password" value={confirmPassword} onChangeText={setConfirmPassword} secureTextEntry textContentType="newPassword" placeholder="Enter the new password again" />
      <AppButton title="Change password" onPress={() => void changePassword()} loading={savingPassword} kind="secondary" icon="lock-closed-outline" />
    </Card>
    <AppButton title="Back to account" kind="ghost" onPress={() => router.back()} />
  </Screen>;
}
