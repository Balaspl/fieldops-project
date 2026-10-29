
import { useEffect } from "react";
import { ActivityIndicator, Image, Text, View } from "react-native";
import { Redirect } from "expo-router";
import { useAuthStore } from "../src/auth/authStore";
import { colors } from "../src/theme";

export default function EntryRoute() {
  const initialized = useAuthStore((state) => state.initialized);
  const user = useAuthStore((state) => state.user);
  const restoreSession = useAuthStore((state) => state.restoreSession);

  useEffect(() => {
    if (!initialized) {
      void restoreSession();
    }
  }, [initialized, restoreSession]);

  if (initialized) {
    return <Redirect href={user ? "/(tabs)" : "/(auth)/login"} />;
  }

  return (
    <View
      style={{
        flex: 1,
        backgroundColor: colors.brand,
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
        gap: 16,
      }}
    >
      <Image
        source={require("../assets/images/fieldops-logo.png")}
        resizeMode="contain"
        style={{ width: 220, height: 76 }}
        accessibilityLabel="FieldOps Commander"
      />

      <Text
        style={{
          color: "#FFFFFF",
          fontSize: 22,
          fontWeight: "800",
        }}
      >
        FieldOps Customer
      </Text>

      <ActivityIndicator color="#FFFFFF" size="large" />

      <Text
        style={{
          color: "#FFFFFF",
          fontSize: 13,
          opacity: 0.85,
        }}
      >
        Preparing your account…
      </Text>
    </View>
  );
}
