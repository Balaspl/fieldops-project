import React from 'react';
import {
  ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text, TextInput,
  View, type TextInputProps, type ViewStyle, type TextStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { AlertCircle, ChevronRight, RefreshCw, Search } from 'lucide-react-native';
import { colors, radii, spacing } from '../theme';
import { statusTone } from '../utils/format';

export function AppScreen({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  return <SafeAreaView style={[styles.safe, style]} edges={['top', 'left', 'right']}><View style={styles.screen}>{children}</View></SafeAreaView>;
}

export function ScreenScroll({ children, contentContainerStyle, refreshControl }: { children: React.ReactNode; contentContainerStyle?: ViewStyle; refreshControl?: React.ReactElement }) {
  return <ScrollView style={styles.scroll} contentContainerStyle={[styles.scrollContent, contentContainerStyle]} keyboardShouldPersistTaps="handled" refreshControl={refreshControl} showsVerticalScrollIndicator={false}>{children}</ScrollView>;
}

export function Card({ children, style, onPress }: { children: React.ReactNode; style?: ViewStyle; onPress?: () => void }) {
  if (onPress) return <Pressable onPress={onPress} accessibilityRole="button" style={({ pressed }) => [styles.card, style, pressed && { opacity: 0.88 }]}>{children}</Pressable>;
  return <View style={[styles.card, style]}>{children}</View>;
}

export function PrimaryButton({ title, onPress, loading, disabled, variant = 'primary', compact, style }: {
  title: string; onPress: () => void; loading?: boolean; disabled?: boolean; variant?: 'primary' | 'secondary' | 'danger' | 'ghost'; compact?: boolean; style?: ViewStyle;
}) {
  const backgroundColor = variant === 'primary' ? colors.forest : variant === 'danger' ? '#FEF2F2' : variant === 'secondary' ? '#E8F3EC' : 'transparent';
  const color = variant === 'danger' ? colors.red : variant === 'ghost' ? colors.forest : variant === 'primary' ? colors.white : colors.forest;
  return <Pressable accessibilityRole="button" onPress={onPress} disabled={disabled || loading} style={({ pressed }) => [styles.button, style, { backgroundColor, minHeight: compact ? 38 : 46, paddingHorizontal: compact ? 12 : 16 }, (disabled || loading) && { opacity: 0.5 }, pressed && { opacity: 0.84 }]}>
    {loading ? <ActivityIndicator size="small" color={color} /> : <Text style={[styles.buttonText, { color, fontSize: compact ? 12 : 14 }]}>{title}</Text>}
  </Pressable>;
}

export function Field({ label, error, left, ...props }: TextInputProps & { label: string; error?: string; left?: React.ReactNode }) {
  return <View style={{ gap: 7 }}>
    <Text style={styles.fieldLabel}>{label}</Text>
    <View style={[styles.inputWrap, error && { borderColor: colors.red }]}>
      {left}
      <TextInput placeholderTextColor="#9AA59E" style={styles.input} {...props} />
    </View>
    {error ? <Text style={styles.fieldError}>{error}</Text> : null}
  </View>;
}

export function SearchField({ value, onChangeText, placeholder = 'Search…' }: { value: string; onChangeText: (value: string) => void; placeholder?: string }) {
  return <View style={styles.searchWrap}><Search size={17} color={colors.muted} /><TextInput value={value} onChangeText={onChangeText} placeholder={placeholder} placeholderTextColor="#9AA59E" style={styles.searchInput} returnKeyType="search" /></View>;
}

export function Pill({ label, tone }: { label: string; tone?: 'green' | 'red' | 'amber' | 'blue' | 'purple' | 'neutral' }) {
  const resolved = tone || statusTone(label);
  const map = {
    green: { bg: '#E7F6ED', fg: '#087443' }, red: { bg: '#FEECEC', fg: '#B91C1C' },
    amber: { bg: '#FFF4DE', fg: '#A65B00' }, blue: { bg: '#EAF1FF', fg: '#2556A8' },
    purple: { bg: '#F2EBFF', fg: '#6B32C9' }, neutral: { bg: '#EFF2F0', fg: '#536159' },
  }[resolved];
  return <View style={[styles.pill, { backgroundColor: map.bg }]}><Text style={[styles.pillText, { color: map.fg }]}>{label.replace(/[_-]/g, ' ')}</Text></View>;
}

export function SectionTitle({ title, action, onAction, subtitle }: { title: string; action?: string; onAction?: () => void; subtitle?: string }) {
  return <View style={styles.sectionTitle}><View style={{ flex: 1, gap: 3 }}><Text style={styles.sectionHeading}>{title}</Text>{subtitle ? <Text style={styles.sectionSubtitle}>{subtitle}</Text> : null}</View>{action && onAction ? <Pressable onPress={onAction} style={styles.sectionAction}><Text style={styles.sectionActionText}>{action}</Text><ChevronRight size={15} color={colors.forest} /></Pressable> : null}</View>;
}

export function MetricCard({ label, value, caption, icon, tone = 'green', onPress }: { label: string; value: string | number; caption?: string; icon?: React.ReactNode; tone?: 'green' | 'blue' | 'amber' | 'red' | 'purple'; onPress?: () => void }) {
  const accent = { green: colors.forest, blue: colors.blue, amber: colors.amber, red: colors.red, purple: colors.purple }[tone];
  return <Card onPress={onPress} style={styles.metricCard}>
    <View style={[styles.metricIcon, { backgroundColor: `${accent}15` }]}>{icon}</View>
    <Text style={styles.metricLabel}>{label}</Text>
    <Text style={[styles.metricValue, { color: colors.ink }]}>{value}</Text>
    {caption ? <Text style={styles.metricCaption}>{caption}</Text> : null}
  </Card>;
}

export function LoadingState({ label = 'Loading FieldOps data…' }: { label?: string }) {
  return <View style={styles.loading}><ActivityIndicator color={colors.forest} size="large" /><Text style={styles.loadingText}>{label}</Text></View>;
}

export function EmptyState({ title, detail, onRetry }: { title: string; detail?: string; onRetry?: () => void }) {
  return <View style={styles.empty}><View style={styles.emptyIcon}><AlertCircle size={24} color={colors.forest} /></View><Text style={styles.emptyTitle}>{title}</Text>{detail ? <Text style={styles.emptyDetail}>{detail}</Text> : null}{onRetry ? <PrimaryButton title="Refresh" onPress={onRetry} variant="secondary" compact /> : null}</View>;
}

export function ErrorBanner({ message, onDismiss }: { message: string; onDismiss?: () => void }) {
  return <View style={styles.errorBanner}><AlertCircle size={17} color={colors.red} /><Text style={styles.errorText}>{message}</Text>{onDismiss ? <Pressable onPress={onDismiss}><Text style={{ color: colors.red, fontWeight: '800' }}>×</Text></Pressable> : null}</View>;
}

export function RefreshAction({ onPress, loading }: { onPress: () => void; loading?: boolean }) {
  return <Pressable onPress={onPress} disabled={loading} style={styles.refreshAction}>{loading ? <ActivityIndicator size="small" color={colors.forest} /> : <RefreshCw size={18} color={colors.forest} />}</Pressable>;
}

export function BrandMark({ compact = false }: { compact?: boolean }) {
  return <Image source={require('../../assets/brand/logo.png')} resizeMode="contain" style={{ width: compact ? 126 : 164, height: compact ? 40 : 50 }} />;
}

export function ScreenHeading({ title, subtitle, action }: { title: string; subtitle?: string; action?: React.ReactNode }) {
  return <View style={styles.screenHeading}><View style={{ flex: 1, gap: 4 }}><Text style={styles.screenTitle}>{title}</Text>{subtitle ? <Text style={styles.screenSubtitle}>{subtitle}</Text> : null}</View>{action}</View>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.canvas }, screen: { flex: 1, backgroundColor: colors.canvas },
  scroll: { flex: 1 }, scrollContent: { padding: spacing.lg, paddingBottom: 38, gap: spacing.lg },
  card: { backgroundColor: colors.white, borderRadius: radii.lg, padding: spacing.lg, borderWidth: 1, borderColor: colors.border, shadowColor: '#153D29', shadowOffset: { width: 0, height: 3 }, shadowOpacity: 0.045, shadowRadius: 9, elevation: 2 },
  button: { borderRadius: 13, paddingVertical: 11, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 8 }, buttonText: { fontWeight: '800', letterSpacing: 0.1 },
  fieldLabel: { fontSize: 12, color: colors.text, fontWeight: '800' }, inputWrap: { minHeight: 48, borderWidth: 1, borderColor: colors.border, borderRadius: 13, backgroundColor: '#FBFDFC', flexDirection: 'row', alignItems: 'center', paddingHorizontal: 13 }, input: { flex: 1, color: colors.ink, fontSize: 14, minHeight: 46, paddingVertical: 8 }, fieldError: { color: colors.red, fontSize: 11 },
  searchWrap: { height: 46, borderWidth: 1, borderColor: colors.border, borderRadius: 14, backgroundColor: colors.white, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 13, gap: 9 }, searchInput: { flex: 1, paddingVertical: 0, color: colors.ink, fontSize: 14 },
  pill: { alignSelf: 'flex-start', paddingHorizontal: 9, paddingVertical: 5, borderRadius: radii.pill }, pillText: { fontSize: 10, fontWeight: '800', textTransform: 'capitalize' },
  sectionTitle: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 3, gap: 10 }, sectionHeading: { fontSize: 16, fontWeight: '900', color: colors.ink }, sectionSubtitle: { fontSize: 11, color: colors.muted }, sectionAction: { flexDirection: 'row', alignItems: 'center', gap: 2 }, sectionActionText: { fontSize: 12, fontWeight: '800', color: colors.forest },
  metricCard: { flex: 1, minWidth: '45%', padding: 13, gap: 6 }, metricIcon: { height: 34, width: 34, borderRadius: 11, justifyContent: 'center', alignItems: 'center', marginBottom: 2 }, metricLabel: { color: colors.muted, fontSize: 11, fontWeight: '700' }, metricValue: { fontSize: 24, fontWeight: '900', letterSpacing: -0.6 }, metricCaption: { color: colors.muted, fontSize: 10 },
  loading: { padding: 40, alignItems: 'center', justifyContent: 'center', gap: 12 }, loadingText: { color: colors.muted, fontSize: 12, fontWeight: '600' }, empty: { padding: 28, borderRadius: 18, alignItems: 'center', backgroundColor: colors.white, borderWidth: 1, borderColor: colors.border, gap: 10 }, emptyIcon: { width: 48, height: 48, backgroundColor: colors.mint, borderRadius: 16, alignItems: 'center', justifyContent: 'center' }, emptyTitle: { fontWeight: '900', fontSize: 15, color: colors.ink, textAlign: 'center' }, emptyDetail: { color: colors.muted, fontSize: 12, textAlign: 'center', lineHeight: 18 },
  errorBanner: { borderRadius: 12, borderWidth: 1, borderColor: '#FECACA', backgroundColor: '#FFF5F5', padding: 12, flexDirection: 'row', alignItems: 'center', gap: 8 }, errorText: { flex: 1, color: '#991B1B', fontSize: 12, fontWeight: '600', lineHeight: 17 }, refreshAction: { width: 40, height: 40, borderRadius: 13, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.white, borderWidth: 1, borderColor: colors.border },
  screenHeading: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 }, screenTitle: { fontSize: 24, color: colors.ink, fontWeight: '900', letterSpacing: -0.7 }, screenSubtitle: { fontSize: 12, lineHeight: 18, color: colors.muted },
});
