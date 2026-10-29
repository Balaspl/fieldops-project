import { router } from "expo-router";
import { AppButton, Screen } from "../src/components/ui";
import { Text, View } from "react-native";
import { colors } from "../src/theme";
export default function NotFoundScreen() {
  return <Screen><View style={{ flex: 1, justifyContent: "center", alignItems: "center", gap: 12, paddingVertical: 60 }}><Text style={{ color: colors.brand, fontSize: 26, fontWeight: "900" }}>Page not found</Text><Text style={{ color: colors.muted, textAlign: "center", lineHeight: 21 }}>This FieldOps customer screen does not exist or may have moved.</Text><AppButton title="Go to home" onPress={() => router.replace("/(tabs)")} /></View></Screen>;
}
