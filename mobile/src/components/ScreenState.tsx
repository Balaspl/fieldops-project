import { useEffect, useRef } from "react";
import {
  Animated,
  Pressable,
  StyleProp,
  StyleSheet,
  Text,
  View,
  ViewStyle
} from "react-native";

interface LoadingStateProps {
  label?: string;
  variant?: "list" | "detail" | "dashboard" | "chat" | "map" | "form";
}

interface MessageStateProps {
  title: string;
  message: string;
  onRetry?: () => void;
}

export function LoadingState({ label = "Loading...", variant = "list" }: LoadingStateProps) {
  const pulse = useRef(new Animated.Value(0.42)).current;

  useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 0.9, duration: 720, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0.42, duration: 720, useNativeDriver: true })
      ])
    );
    animation.start();
    return () => animation.stop();
  }, [pulse]);

  const block = (style: StyleProp<ViewStyle>) => (
    <Animated.View style={[styles.skeletonBlock, style, { opacity: pulse }]} />
  );

  if (variant === "chat") {
    return (
      <View style={styles.chatSkeleton} accessibilityLabel={label}>
        {block({ width: "64%", height: 48, borderRadius: 18, alignSelf: "flex-start" })}
        {block({ width: "74%", height: 58, borderRadius: 18, alignSelf: "flex-end" })}
        {block({ width: "53%", height: 45, borderRadius: 18, alignSelf: "flex-start" })}
        {block({ width: "68%", height: 54, borderRadius: 18, alignSelf: "flex-end" })}
      </View>
    );
  }

  if (variant === "map") {
    return (
      <View style={styles.mapSkeleton} accessibilityLabel={label}>
        {block(StyleSheet.absoluteFill)}
        <View style={styles.mapMarkerSkeleton}>{block({ width: 26, height: 26, borderRadius: 13 })}</View>
        <View style={styles.mapSheetSkeleton}>
          {block({ width: "48%", height: 17, borderRadius: 6 })}
          {block({ width: "82%", height: 12, borderRadius: 5 })}
          {block({ width: "68%", height: 12, borderRadius: 5 })}
        </View>
      </View>
    );
  }

  return (
    <View style={styles.skeletonPage} accessibilityLabel={label}>
      {variant === "dashboard" ? (
        <>
          <View style={styles.skeletonDashboardHeader}>
            {block({ width: 160, height: 38, borderRadius: 10 })}
            {block({ width: 46, height: 46, borderRadius: 15 })}
          </View>
          {block(styles.skeletonHero)}
          <View style={styles.skeletonMetricGrid}>
            {[0, 1, 2, 3].map((item) => (
              <View key={item} style={styles.skeletonMetric}>
                {block({ width: 34, height: 34, borderRadius: 11 })}
                {block({ width: "66%", height: 12, borderRadius: 5 })}
                {block({ width: "42%", height: 20, borderRadius: 6 })}
              </View>
            ))}
          </View>
        </>
      ) : (
        <>
          <View style={styles.skeletonPageHeader}>
            {block({ width: 46, height: 46, borderRadius: 15 })}
            {block({ width: "48%", height: 20, borderRadius: 7 })}
            {variant === "detail" ? block({ width: 42, height: 42, borderRadius: 14 }) : null}
          </View>
          {variant === "detail" ? block(styles.skeletonHero) : null}
          {variant === "form" ? (
            <View style={styles.skeletonForm}>
              {[0, 1, 2, 3, 4].map((item) => (
                <View key={item} style={styles.skeletonField}>
                  {block({ width: "34%", height: 11, borderRadius: 5 })}
                  {block({ width: "100%", height: 46, borderRadius: 12 })}
                </View>
              ))}
            </View>
          ) : (
            <>
              <View style={styles.skeletonToolbar}>
                {block({ width: "100%", height: 45, borderRadius: 13 })}
                {block({ width: 84, height: 34, borderRadius: 18 })}
              </View>
              {[0, 1, 2, 3].map((item) => (
                <View key={item} style={styles.skeletonCard}>
                  {block({ width: 44, height: 44, borderRadius: 14 })}
                  <View style={{ flex: 1, gap: 9 }}>
                    {block({ width: "62%", height: 14, borderRadius: 5 })}
                    {block({ width: "88%", height: 11, borderRadius: 5 })}
                    {variant === "detail" ? block({ width: "52%", height: 11, borderRadius: 5 }) : null}
                  </View>
                  {block({ width: 16, height: 16, borderRadius: 6 })}
                </View>
              ))}
            </>
          )}
        </>
      )}
    </View>
  );
}

export function ErrorState({ title = "Something went wrong", message, onRetry }: MessageStateProps) {
  return (
    <View style={messageStyles.container}>
      <Text style={messageStyles.title}>{title}</Text>
      <Text style={messageStyles.message}>{message}</Text>
      {onRetry ? (
        <Pressable accessibilityRole="button" onPress={onRetry} style={messageStyles.button}>
          <Text style={messageStyles.buttonText}>Try again</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

export function EmptyState({ title = "Nothing here yet", message, onRetry }: MessageStateProps) {
  return (
    <View style={messageStyles.container}>
      <Text style={messageStyles.title}>{title}</Text>
      <Text style={messageStyles.message}>{message}</Text>
      {onRetry ? (
        <Pressable accessibilityRole="button" onPress={onRetry} style={messageStyles.button}>
          <Text style={messageStyles.buttonText}>Refresh</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  skeletonPage: { flex: 1, backgroundColor: "#F3F8F4", paddingHorizontal: 16, paddingTop: 18 },
  skeletonPageHeader: { minHeight: 54, flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 16 },
  skeletonDashboardHeader: { minHeight: 60, flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 14 },
  skeletonHero: { height: 142, borderRadius: 20, marginBottom: 16, backgroundColor: "#FFFFFF" },
  skeletonMetricGrid: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  skeletonMetric: { width: "48%", height: 125, borderRadius: 18, backgroundColor: "#FFFFFF", padding: 14, justifyContent: "space-between", alignItems: "flex-start" },
  skeletonToolbar: { gap: 10, marginBottom: 14 },
  skeletonCard: { minHeight: 88, flexDirection: "row", alignItems: "center", gap: 12, backgroundColor: "#FFFFFF", borderRadius: 17, marginBottom: 11, padding: 14, elevation: 1 },
  skeletonForm: { gap: 18, marginTop: 12 },
  skeletonField: { gap: 8 },
  skeletonBlock: { backgroundColor: "#CADBCF" },
  chatSkeleton: { flex: 1, justifyContent: "flex-end", gap: 16, padding: 18, backgroundColor: "#F5F8F6" },
  mapSkeleton: { flex: 1, overflow: "hidden", backgroundColor: "#DFEAE3" },
  mapMarkerSkeleton: { position: "absolute", top: "42%", left: "48%", width: 42, height: 42, borderRadius: 21, backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center", elevation: 3 },
  mapSheetSkeleton: { position: "absolute", left: 12, right: 12, bottom: 12, gap: 12, padding: 18, borderRadius: 20, backgroundColor: "#FFFFFF", elevation: 4 }
});

const messageStyles = StyleSheet.create({
  container: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24, backgroundColor: "#F3F8F4" },
  title: { fontSize: 20, fontWeight: "700", color: "#173B29", textAlign: "center", marginBottom: 8 },
  message: { fontSize: 15, color: "#647A6C", textAlign: "center", marginTop: 12, lineHeight: 22 },
  button: { backgroundColor: "#078A4D", paddingHorizontal: 20, paddingVertical: 12, borderRadius: 10, marginTop: 20 },
  buttonText: { color: "#FFFFFF", fontSize: 15, fontWeight: "700" }
});
