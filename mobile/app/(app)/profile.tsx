
import { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View
} from "react-native";
import { useRouter } from "expo-router";
import { useAuthStore } from "../../src/auth/authStore";

export default function ProfileScreen() {
  const router = useRouter();

  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  const [isLoggingOut, setIsLoggingOut] = useState(false);

  async function handleLogout() {
    if (isLoggingOut) {
      return;
    }

    setIsLoggingOut(true);

    try {
      await logout();
      router.replace("/(auth)/login");
    } catch {
      Alert.alert(
        "Sign-out issue",
        "Your session could not be cleared completely. Please try again."
      );
    } finally {
      setIsLoggingOut(false);
    }
  }

  const displayName =
    user?.full_name?.trim() || user?.email || "Technician";

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
    >
      <Text style={styles.heading}>My Profile</Text>
      <Text style={styles.subtitle}>
        Your FieldOps account information
      </Text>

      <View style={styles.profileCard}>
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>
            {displayName.charAt(0).toUpperCase()}
          </Text>
        </View>

        <Text style={styles.name}>{displayName}</Text>
        <Text style={styles.role}>
          {user?.role || "Technician"}
        </Text>
      </View>

      <Text style={styles.sectionTitle}>Account details</Text>

      <View style={styles.detailsCard}>
        <DetailRow
          label="Full name"
          value={user?.full_name || "Not provided"}
        />

        <DetailRow
          label="Email"
          value={user?.email || "Not available"}
        />

        <DetailRow
          label="Account ID"
          value={user?.id != null ? String(user.id) : "Not available"}
        />

        <DetailRow
          label="Role"
          value={user?.role || "Not available"}
        />
      </View>

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Sign out"
        disabled={isLoggingOut}
        onPress={() => void handleLogout()}
        style={({ pressed }) => [
          styles.signOutButton,
          pressed && styles.signOutPressed,
          isLoggingOut && styles.disabledButton
        ]}
      >
        {isLoggingOut ? (
          <ActivityIndicator color="#FFFFFF" />
        ) : (
          <Text style={styles.signOutText}>Sign out</Text>
        )}
      </Pressable>
    </ScrollView>
  );
}

interface DetailRowProps {
  label: string;
  value: string;
}

function DetailRow({ label, value }: DetailRowProps) {
  return (
    <View style={styles.detailRow}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.value}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#F8FAFC"
  },
  content: {
    paddingHorizontal: 22,
    paddingTop: 42,
    paddingBottom: 36
  },
  heading: {
    color: "#0F172A",
    fontSize: 28,
    fontWeight: "800"
  },
  subtitle: {
    color: "#64748B",
    fontSize: 14,
    marginTop: 6,
    marginBottom: 24
  },
  profileCard: {
    alignItems: "center",
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#E2E8F0",
    borderRadius: 16,
    padding: 24,
    marginBottom: 28
  },
  avatar: {
    width: 76,
    height: 76,
    borderRadius: 38,
    backgroundColor: "#DBEAFE",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 14
  },
  avatarText: {
    color: "#1D4ED8",
    fontSize: 30,
    fontWeight: "800"
  },
  name: {
    color: "#0F172A",
    fontSize: 21,
    fontWeight: "700",
    textAlign: "center"
  },
  role: {
    color: "#64748B",
    fontSize: 14,
    textTransform: "capitalize",
    marginTop: 6
  },
  sectionTitle: {
    color: "#0F172A",
    fontSize: 18,
    fontWeight: "700",
    marginBottom: 12
  },
  detailsCard: {
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#E2E8F0",
    borderRadius: 12,
    paddingHorizontal: 16,
    marginBottom: 24
  },
  detailRow: {
    borderBottomWidth: 1,
    borderBottomColor: "#F1F5F9",
    paddingVertical: 14
  },
  label: {
    color: "#64748B",
    fontSize: 12,
    marginBottom: 5
  },
  value: {
    color: "#0F172A",
    fontSize: 15,
    fontWeight: "600"
  },
  signOutButton: {
    alignItems: "center",
    justifyContent: "center",
    minHeight: 50,
    backgroundColor: "#DC2626",
    borderRadius: 10
  },
  signOutPressed: {
    backgroundColor: "#B91C1C"
  },
  disabledButton: {
    opacity: 0.6
  },
  signOutText: {
    color: "#FFFFFF",
    fontSize: 15,
    fontWeight: "700"
  }
});
