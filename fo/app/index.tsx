import { useEffect } from "react";
import { Redirect } from "expo-router";
import { Text } from "react-native";
import { useAuthStore } from "../src/auth/authStore";
import { homeRoute } from "../src/auth/roles";
import { ActionButton, Card, LoadingState, Screen } from "../src/components/ui";

export default function Index() {
  const { user, initialized, logout } = useAuthStore();
  const restoreSession = useAuthStore((state) => state.restoreSession);
  useEffect(() => { if (!initialized) void restoreSession(); }, [initialized, restoreSession]);
  if (!initialized) return <Screen><LoadingState /></Screen>;
  if (!user) return <Redirect href="/login" />;
  const route = homeRoute(user.role);
  if (route) return <Redirect href={route} />;
  return <Screen><Card><Text style={{ fontSize: 20, fontWeight: "800" }}>Access unavailable</Text><Text>Your account role is not supported by this app. Contact your administrator.</Text><ActionButton title="Sign out" onPress={() => void logout()} /></Card></Screen>;
}
