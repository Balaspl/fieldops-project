import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View, type ViewStyle } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors } from "../theme";

export function Screen({ children, scroll = false }: { children: React.ReactNode; scroll?: boolean }) {
  return <SafeAreaView style={styles.safe} edges={["top", "left", "right"]}>{scroll ? <ScrollView contentContainerStyle={styles.content}>{children}</ScrollView> : <View style={styles.content}>{children}</View>}</SafeAreaView>;
}
export function Heading({ title, subtitle }: { title: string; subtitle?: string }) {
  return <View style={styles.heading}><Text style={styles.title}>{title}</Text>{subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}</View>;
}
export function Card({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  return <View style={[styles.card, style]}>{children}</View>;
}
export function ActionButton({ title, onPress, secondary = false, disabled = false }: { title: string; onPress: () => void; secondary?: boolean; disabled?: boolean }) {
  return <Pressable accessibilityRole="button" disabled={disabled} onPress={onPress} style={[styles.button, secondary && styles.buttonSecondary, disabled && { opacity: 0.6 }]}><Text style={[styles.buttonText, secondary && styles.secondaryText]}>{title}</Text></Pressable>;
}
export function LoadingState() {
  return <View style={styles.loading}><ActivityIndicator color={colors.brand} /><Text style={styles.subtitle}>Loading FieldOps…</Text></View>;
}
export function SkeletonRows() {
  return <View>{[0, 1, 2].map((i) => <View key={i} style={styles.skeletonCard}><View style={styles.skeletonLine} /><View style={[styles.skeletonLine, { width: "55%" }]} /></View>)}</View>;
}
export function ErrorMessage({ message }: { message: string }) {
  return <Card><Text style={{ color: colors.danger, fontWeight: "600" }}>{message}</Text></Card>;
}
export function ListRow({ title, detail, onPress }: { title: string; detail?: string; onPress?: () => void }) {
  const content = <><Text style={styles.rowTitle}>{title}</Text>{detail ? <Text style={styles.subtitle}>{detail}</Text> : null}</>;
  return onPress ? <Pressable onPress={onPress} style={styles.row}>{content}<Text style={styles.chevron}>›</Text></Pressable> : <View style={styles.row}>{content}</View>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.canvas }, content: { flexGrow: 1, padding: 20, gap: 16 },
  heading: { gap: 5, marginBottom: 4 }, title: { color: colors.ink, fontSize: 27, fontWeight: "800" }, subtitle: { color: colors.muted, fontSize: 14, lineHeight: 20 },
  card: { backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, borderRadius: 18, padding: 16, gap: 9 },
  button: { alignItems: "center", justifyContent: "center", minHeight: 50, borderRadius: 14, backgroundColor: colors.brand, paddingHorizontal: 18 }, buttonSecondary: { backgroundColor: colors.accent }, buttonText: { color: "white", fontWeight: "700", fontSize: 15 }, secondaryText: { color: colors.brandDark },
  loading: { flex: 1, alignItems: "center", justifyContent: "center", gap: 12 }, skeletonCard: { height: 82, backgroundColor: colors.surface, borderRadius: 16, padding: 16, gap: 12, marginBottom: 12 }, skeletonLine: { height: 13, width: "75%", borderRadius: 8, backgroundColor: "#E6EEE9" },
  row: { backgroundColor: colors.surface, borderColor: colors.border, borderWidth: 1, borderRadius: 16, padding: 16, minHeight: 68, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 }, rowTitle: { color: colors.ink, fontSize: 15, fontWeight: "700", flexShrink: 1 }, chevron: { fontSize: 26, color: colors.brand },
});
export const uiStyles = styles;
