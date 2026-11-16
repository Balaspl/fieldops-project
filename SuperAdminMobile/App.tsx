import React from 'react';
import { StatusBar, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { AuthProvider, useAuth } from './src/auth/AuthContext';
import { LoadingState } from './src/components/UI';
import StaffShell from './src/components/StaffShell';
import LoginScreen from './src/screens/LoginScreen';
import { colors } from './src/theme';

function AppRoot() {
  const { user, loading } = useAuth();
  if (loading) return <View style={{ flex: 1, backgroundColor: colors.canvas, justifyContent: 'center' }}><LoadingState label="Restoring your secure FieldOps session…" /></View>;
  return user ? <StaffShell /> : <LoginScreen />;
}

export default function App() {
  return <SafeAreaProvider><StatusBar barStyle="dark-content" backgroundColor={colors.white} /><AuthProvider><AppRoot /></AuthProvider></SafeAreaProvider>;
}
