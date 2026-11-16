import React, { useState } from 'react';
import { Alert, Text, View } from 'react-native';
import { KeyRound, Mail, ShieldCheck, UserRound } from 'lucide-react-native';
import { api, getApiErrorMessage } from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { Card, ErrorBanner, Field, PrimaryButton, ScreenHeading, ScreenScroll } from '../components/UI';
import { colors } from '../theme';

export default function ProfileScreen() {
  const { user, reloadUser } = useAuth();
  const [firstName, setFirstName] = useState(user?.first_name || '');
  const [lastName, setLastName] = useState(user?.last_name || '');
  const [savingProfile, setSavingProfile] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [savingPassword, setSavingPassword] = useState(false);
  const [error, setError] = useState('');

  const saveProfile = async () => {
    setError('');
    if (!firstName.trim() || !lastName.trim()) { setError('First name and last name are required.'); return; }
    setSavingProfile(true);
    try {
      await api.put('/auth/profile', { first_name: firstName.trim(), last_name: lastName.trim() });
      await reloadUser();
      Alert.alert('Profile updated', 'Your staff profile name has been updated.');
    } catch (e) { setError(getApiErrorMessage(e, 'Profile update failed.')); }
    finally { setSavingProfile(false); }
  };

  const changePassword = async () => {
    setError('');
    if (!currentPassword || !newPassword || !confirmPassword) { setError('Complete all password fields.'); return; }
    if (newPassword !== confirmPassword) { setError('New password and confirmation do not match.'); return; }
    if (newPassword.length < 8) { setError('Use at least 8 characters for the new password.'); return; }
    setSavingPassword(true);
    try {
      await api.put('/auth/change-password', { current_password: currentPassword, new_password: newPassword });
      setCurrentPassword(''); setNewPassword(''); setConfirmPassword('');
      Alert.alert('Password changed', 'Your password has been updated.');
    } catch (e) { setError(getApiErrorMessage(e, 'Password change failed.')); }
    finally { setSavingPassword(false); }
  };

  return <ScreenScroll>
    <ScreenHeading title="My profile" subtitle="Manage your FieldOps staff identity and account security." />
    <Card style={{ gap: 10, backgroundColor: '#F0F7F2' }}>
      <View style={{ width: 48, height: 48, borderRadius: 16, backgroundColor: '#DDEFE3', justifyContent: 'center', alignItems: 'center' }}><UserRound size={23} color={colors.forest} /></View>
      <Text style={{ color: colors.ink, fontSize: 17, fontWeight: '900' }}>{user?.first_name} {user?.last_name}</Text>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}><Mail size={13} color={colors.muted} /><Text style={{ color: colors.muted, fontSize: 11 }}>{user?.email}</Text></View>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}><ShieldCheck size={13} color={colors.forest} /><Text style={{ color: colors.forest, fontSize: 10, fontWeight: '900' }}>{user?.role === 'super_admin' ? 'SUPER ADMIN' : 'DISPATCHER'} · {user?.organization_name || 'Organization staff'}</Text></View>
    </Card>
    {error ? <ErrorBanner message={error} /> : null}
    <Card style={{ gap: 13 }}>
      <Text style={{ color: colors.ink, fontWeight: '900', fontSize: 15 }}>Personal information</Text>
      <Field label="FIRST NAME" value={firstName} onChangeText={setFirstName} placeholder="First name" left={<UserRound size={16} color={colors.muted} />} />
      <Field label="LAST NAME" value={lastName} onChangeText={setLastName} placeholder="Last name" />
      <PrimaryButton title="Save profile" onPress={() => void saveProfile()} loading={savingProfile} />
    </Card>
    <Card style={{ gap: 13 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}><KeyRound size={17} color={colors.forest} /><Text style={{ color: colors.ink, fontWeight: '900', fontSize: 15 }}>Change password</Text></View>
      <Field label="CURRENT PASSWORD" value={currentPassword} onChangeText={setCurrentPassword} secureTextEntry placeholder="Enter current password" />
      <Field label="NEW PASSWORD" value={newPassword} onChangeText={setNewPassword} secureTextEntry placeholder="At least 8 characters" />
      <Field label="CONFIRM NEW PASSWORD" value={confirmPassword} onChangeText={setConfirmPassword} secureTextEntry placeholder="Re-enter new password" />
      <PrimaryButton title="Update password" onPress={() => void changePassword()} loading={savingPassword} />
    </Card>
  </ScreenScroll>;
}
