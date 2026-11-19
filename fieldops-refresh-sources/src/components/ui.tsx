import React from "react";
import {
  ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput,
  type TextInputProps, View, type ViewStyle,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { colors, radii, spacing } from "../theme";

export function Screen({ children, scroll = true, contentStyle }: { children: React.ReactNode; scroll?: boolean; contentStyle?: ViewStyle }) {
  return (
    <SafeAreaView style={styles.safe} edges={["top", "left", "right"]}>
      {scroll ? <ScrollView contentContainerStyle={[styles.content, contentStyle]} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>{children}</ScrollView>
        : <View style={[styles.content, { flex: 1 }, contentStyle]}>{children}</View>}
    </SafeAreaView>
  );
}

export function Header({ title, subtitle, right }: { title: string; subtitle?: string; right?: React.ReactNode }) {
  return <View style={styles.headerRow}><View style={{ flex: 1, gap: 4 }}><Text style={styles.title}>{title}</Text>{subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}</View>{right}</View>;
}

export function Card({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function AppButton({ title, onPress, kind = "primary", disabled = false, loading = false, icon, style }: {
  title: string; onPress: () => void; kind?: "primary" | "secondary" | "ghost" | "danger"; disabled?: boolean; loading?: boolean; icon?: keyof typeof Ionicons.glyphMap; style?: ViewStyle;
}) {
  const background = kind === "primary" ? colors.brand : kind === "danger" ? colors.dangerSoft : kind === "secondary" ? colors.brandSoft : "transparent";
  const foreground = kind === "primary" ? "#FFFFFF" : kind === "danger" ? colors.danger : colors.brand;
  return <Pressable accessibilityRole="button" onPress={onPress} disabled={disabled || loading} style={({ pressed }) => [styles.button, { backgroundColor: background, opacity: disabled || loading ? 0.55 : pressed ? 0.82 : 1 }, style, kind === "ghost" && styles.ghostButton]}>
    {loading ? <ActivityIndicator size="small" color={foreground} /> : icon ? <Ionicons name={icon} size={18} color={foreground} /> : null}
    <Text style={[styles.buttonText, { color: foreground }]}>{loading ? "Please wait…" : title}</Text>
  </Pressable>;
}

export function IconButton({ icon, onPress, label, tone = "neutral" }: { icon: keyof typeof Ionicons.glyphMap; onPress: () => void; label: string; tone?: "neutral" | "brand" }) {
  return <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} style={[styles.iconButton, tone === "brand" && { backgroundColor: colors.brandSoft }]}><Ionicons name={icon} size={20} color={tone === "brand" ? colors.brand : colors.muted} /></Pressable>;
}

export function Field({ label, error, ...props }: TextInputProps & { label: string; error?: string }) {
  return <View style={styles.fieldWrap}><Text style={styles.label}>{label}</Text><TextInput
    placeholderTextColor="#94A29A" autoCapitalize={props.keyboardType === "email-address" ? "none" : props.autoCapitalize ?? "sentences"}
    {...props}
    style={[styles.input, props.multiline && styles.multiline, props.style]}
  />{error ? <Text style={styles.fieldError}>{error}</Text> : null}</View>;
}

export function ChoiceChips<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: readonly T[]; onChange: (value: T) => void }) {
  return <View style={styles.fieldWrap}><Text style={styles.label}>{label}</Text><View style={styles.chips}>{options.map((option) => <Pressable key={option} onPress={() => onChange(option)} style={[styles.chip, value === option && styles.chipSelected]}><Text style={[styles.chipText, value === option && styles.chipTextSelected]}>{option.replaceAll("_", " ")}</Text></Pressable>)}</View></View>;
}

export function StatusBadge({ status }: { status: string | null | undefined }) {
  const normalized = (status ?? "UNKNOWN").trim().toUpperCase().replaceAll("-", "_");
  const map: Record<string, { label: string; bg: string; fg: string }> = {
    CREATED: { label: "UNASSIGNED", bg: colors.warningSoft, fg: colors.warning },
    PENDING: { label: "UNASSIGNED", bg: colors.warningSoft, fg: colors.warning },
    UNASSIGNED: { label: "UNASSIGNED", bg: colors.warningSoft, fg: colors.warning },
    QUEUED: { label: "UNASSIGNED", bg: colors.warningSoft, fg: colors.warning },
    ASSIGNED: { label: "AWAITING ACCEPTANCE", bg: colors.blueSoft, fg: colors.blue },
    ACCEPTED: { label: "ASSIGNED", bg: colors.blueSoft, fg: colors.blue },
    EN_ROUTE: { label: "EN ROUTE", bg: colors.purpleSoft, fg: colors.purple },
    ON_SITE: { label: "IN PROGRESS", bg: colors.warningSoft, fg: colors.warning },
    IN_PROGRESS: { label: "IN PROGRESS", bg: colors.warningSoft, fg: colors.warning },
    COMPLETED: { label: "COMPLETED", bg: colors.successSoft, fg: colors.success },
    CLOSED: { label: "CLOSED", bg: "#E9ECEB", fg: "#47544C" },
    CANCELLED: { label: "CANCELLED", bg: colors.dangerSoft, fg: colors.danger },
    REJECTED_BY_TECHNICIAN: { label: "CANCELLED", bg: colors.dangerSoft, fg: colors.danger },
  };
  const entry = map[normalized] ?? { label: normalized.replaceAll("_", " "), bg: "#EFF2F0", fg: colors.muted };
  return <View style={[styles.badge, { backgroundColor: entry.bg }]}><Text style={[styles.badgeText, { color: entry.fg }]}>{entry.label}</Text></View>;
}

export function SectionTitle({ title, action, onAction }: { title: string; action?: string; onAction?: () => void }) {
  return <View style={styles.sectionRow}><Text style={styles.sectionTitle}>{title}</Text>{action && onAction ? <Pressable onPress={onAction}><Text style={styles.link}>{action}</Text></Pressable> : null}</View>;
}

export function LoadingView({ message = "Loading your FieldOps details…" }: { message?: string }) {
  return <View style={styles.centerState}><ActivityIndicator color={colors.brand} size="large" /><Text style={styles.stateText}>{message}</Text></View>;
}

export function EmptyState({ title, message, icon = "file-tray-outline", action }: { title: string; message: string; icon?: keyof typeof Ionicons.glyphMap; action?: React.ReactNode }) {
  return <View style={styles.empty}><View style={styles.emptyIcon}><Ionicons name={icon} size={28} color={colors.brand} /></View><Text style={styles.emptyTitle}>{title}</Text><Text style={styles.emptyMessage}>{message}</Text>{action}</View>;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <View style={styles.errorBox}><Ionicons name="alert-circle-outline" size={22} color={colors.danger} /><Text style={styles.errorText}>{message}</Text>{onRetry ? <AppButton title="Try again" onPress={onRetry} kind="secondary" /> : null}</View>;
}

export function LinkRow({ icon, title, subtitle, onPress, trailing }: { icon: keyof typeof Ionicons.glyphMap; title: string; subtitle?: string; onPress: () => void; trailing?: React.ReactNode }) {
  return <Pressable onPress={onPress} style={({ pressed }) => [styles.linkRow, pressed && { opacity: 0.72 }]}><View style={styles.linkIcon}><Ionicons name={icon} size={21} color={colors.brand} /></View><View style={{ flex: 1, gap: 3 }}><Text style={styles.linkRowTitle}>{title}</Text>{subtitle ? <Text style={styles.linkRowSub}>{subtitle}</Text> : null}</View>{trailing ?? <Ionicons name="chevron-forward" size={19} color={colors.muted} />}</Pressable>;
}

export const sharedStyles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: 10 },
  spaceBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 },
  body: { fontSize: 14, lineHeight: 21, color: colors.muted },
  strong: { fontSize: 15, fontWeight: "700", color: colors.text },
  money: { fontSize: 18, fontWeight: "800", color: colors.brand, fontVariant: ["tabular-nums"] },
});

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  content: { paddingHorizontal: 18, paddingTop: 14, paddingBottom: 34, gap: 18 },
  headerRow: { flexDirection: "row", alignItems: "center", gap: 12, marginBottom: 2 },
  title: { fontSize: 27, lineHeight: 32, fontWeight: "800", color: colors.brand, letterSpacing: -0.5 },
  subtitle: { fontSize: 14, lineHeight: 20, color: colors.muted },
  card: { backgroundColor: colors.surface, borderRadius: radii.md, padding: 16, borderWidth: 1, borderColor: colors.border, gap: 12 },
  button: { minHeight: 48, borderRadius: radii.md, paddingVertical: 12, paddingHorizontal: 16, flexDirection: "row", justifyContent: "center", alignItems: "center", gap: 9 },
  buttonText: { fontWeight: "700", fontSize: 14 },
  ghostButton: { borderWidth: 1, borderColor: colors.border },
  iconButton: { height: 42, width: 42, borderRadius: 14, backgroundColor: "#EEF2EF", alignItems: "center", justifyContent: "center" },
  fieldWrap: { gap: 7 },
  label: { fontSize: 13, fontWeight: "700", color: colors.text },
  input: { borderWidth: 1, borderColor: colors.border, backgroundColor: "#FFFFFF", borderRadius: 12, paddingVertical: 13, paddingHorizontal: 13, fontSize: 15, color: colors.text },
  multiline: { minHeight: 108, textAlignVertical: "top" },
  fieldError: { fontSize: 12, color: colors.danger },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: { paddingHorizontal: 12, paddingVertical: 9, borderRadius: radii.pill, backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: colors.border },
  chipSelected: { backgroundColor: colors.brand, borderColor: colors.brand },
  chipText: { fontSize: 12, fontWeight: "700", color: colors.muted },
  chipTextSelected: { color: "#FFFFFF" },
  badge: { alignSelf: "flex-start", borderRadius: radii.pill, paddingHorizontal: 10, paddingVertical: 6 },
  badgeText: { fontSize: 10, fontWeight: "800", letterSpacing: 0.25 },
  sectionRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 },
  sectionTitle: { fontSize: 17, fontWeight: "800", color: colors.text },
  link: { fontSize: 13, fontWeight: "700", color: colors.brandMid },
  centerState: { alignItems: "center", justifyContent: "center", padding: 36, gap: 14 },
  stateText: { fontSize: 14, color: colors.muted, textAlign: "center" },
  empty: { alignItems: "center", paddingVertical: 30, paddingHorizontal: 18, gap: 10 },
  emptyIcon: { width: 60, height: 60, borderRadius: 20, backgroundColor: colors.brandSoft, alignItems: "center", justifyContent: "center" },
  emptyTitle: { fontSize: 16, fontWeight: "800", color: colors.text, textAlign: "center" },
  emptyMessage: { fontSize: 13, lineHeight: 20, color: colors.muted, textAlign: "center" },
  errorBox: { padding: 14, borderRadius: radii.md, borderWidth: 1, borderColor: "#F1C4C0", backgroundColor: colors.dangerSoft, gap: 10 },
  errorText: { flex: 1, fontSize: 13, lineHeight: 19, color: colors.danger },
  linkRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: colors.border },
  linkIcon: { width: 42, height: 42, borderRadius: 14, backgroundColor: colors.brandSoft, alignItems: "center", justifyContent: "center" },
  linkRowTitle: { fontSize: 14, fontWeight: "700", color: colors.text },
  linkRowSub: { fontSize: 12, lineHeight: 17, color: colors.muted },
});
