import React, { useState } from 'react';
import { ImageBackground, KeyboardAvoidingView, Platform, Text, View } from 'react-native';
import { LockKeyhole, Mail, ShieldCheck, UserRound } from 'lucide-react-native';
import { useAuth } from '../auth/AuthContext';
import { BrandMark, Card, ErrorBanner, Field, PrimaryButton } from '../components/UI';
import { colors, spacing } from '../theme';

export default function LoginScreen() {
  const { signIn, verifyMfa, error, clearError } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [challenge, setChallenge] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [localError, setLocalError] = useState('');

  const submit = async () => {
    clearError(); setLocalError('');
    if (!email.trim() || !password) { setLocalError('Enter your work email and password.'); return; }
    setLoading(true);
    try {
      const result = await signIn(email, password);
      if (result.mfaRequired) setChallenge(result.challenge);
    } catch (err: any) {
      setLocalError(err?.message || 'Unable to sign in.');
    } finally { setLoading(false); }
  };

  const submitMfa = async () => {
    setLocalError('');
    if (!challenge || !/^\d{6}$/.test(code)) { setLocalError('Enter the 6-digit authenticator code.'); return; }
    setLoading(true);
    try { await verifyMfa(challenge, code); }
    catch (err: any) { setLocalError(err?.message || 'MFA verification failed.'); }
    finally { setLoading(false); }
  };

  return <KeyboardAvoidingView style={{ flex: 1, backgroundColor: colors.canvas }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
    <View style={{ flex: 1 }}>
      <ImageBackground source={require('../../assets/banners/dispatcher-banner.png')} resizeMode="cover" style={{ height: 235, justifyContent: 'flex-end', padding: 22 }} imageStyle={{ opacity: 0.98 }}>
        <View style={{ position: 'absolute', inset: 0, backgroundColor: 'rgba(4,55,32,0.45)' }} />
        <BrandMark />
        <Text style={{ color: '#fff', fontSize: 27, fontWeight: '900', marginTop: 20 }}>Operations, in control.</Text>
        <Text style={{ color: '#EAF8EF', fontSize: 13, marginTop: 5 }}>Super Admin & Dispatcher workspace</Text>
      </ImageBackground>
      <View style={{ flex: 1, padding: 20, justifyContent: 'center' }}>
        <Card style={{ padding: 20, gap: 18 }}>
          <View style={{ gap: 5 }}>
            <Text style={{ color: colors.ink, fontSize: 23, fontWeight: '900' }}>{challenge ? 'Verify your identity' : 'Welcome back'}</Text>
            <Text style={{ color: colors.muted, fontSize: 12, lineHeight: 18 }}>{challenge ? 'Enter the code from your authenticator app to continue securely.' : 'Sign in with your FieldOps staff credentials.'}</Text>
          </View>
          {localError || error ? <ErrorBanner message={localError || error || 'Sign-in failed'} /> : null}
          {!challenge ? <>
            <Field label="WORK EMAIL" value={email} onChangeText={setEmail} placeholder="you@company.com" autoCapitalize="none" keyboardType="email-address" autoComplete="email" left={<Mail size={17} color={colors.muted} />} />
            <Field label="PASSWORD" value={password} onChangeText={setPassword} placeholder="Enter your password" secureTextEntry autoComplete="password" left={<LockKeyhole size={17} color={colors.muted} />} onSubmitEditing={submit} />
            <PrimaryButton title="Sign in to FieldOps" onPress={submit} loading={loading} />
          </> : <>
            <Field label="AUTHENTICATOR CODE" value={code} onChangeText={value => setCode(value.replace(/\D/g, '').slice(0, 6))} placeholder="000000" keyboardType="number-pad" maxLength={6} left={<ShieldCheck size={17} color={colors.muted} />} onSubmitEditing={submitMfa} />
            <PrimaryButton title="Verify and continue" onPress={submitMfa} loading={loading} />
            <PrimaryButton title="Back to login" variant="ghost" onPress={() => { setChallenge(null); setCode(''); setLocalError(''); }} />
          </>}
          <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', marginTop: 2 }}>
            <UserRound size={14} color={colors.muted} /><Text style={{ color: colors.muted, fontSize: 11 }}>Only Super Admin and Dispatcher accounts can sign in.</Text>
          </View>
        </Card>
        <Text style={{ color: colors.muted, fontSize: 10, textAlign: 'center', marginTop: 18 }}>FieldOps Commander · Secure staff access</Text>
      </View>
    </View>
  </KeyboardAvoidingView>;
}
