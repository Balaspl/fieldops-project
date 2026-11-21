import { useState } from "react";
import { Alert, Text } from "react-native";
import { router } from "expo-router";
import { customerApi } from "../../src/customer/api/customer";
import { getApiErrorMessage } from "../../src/customer/api/client";
import { AppButton, Card, Field, Header, Screen } from "../../src/customer/components/ui";
import { colors } from "../../src/customer/theme";

export default function CustomerSettingsScreen() {
  const [savingPassword, setSavingPassword] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");

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

  return <Screen>
    <Header title="Account security" subtitle="Update your account password" />
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
