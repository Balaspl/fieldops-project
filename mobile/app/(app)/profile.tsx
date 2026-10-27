import { useEffect, useState } from "react";
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
import {
  hasTechnicianLocationConsent,
  setTechnicianLocationConsent,
  startTechnicianLocationTracking,
  stopTechnicianLocationTracking
} from "../../src/gps/backgroundLocationService";
import { logError } from "../../src/observability/logger";

export default function ProfileScreen() {
  const router = useRouter();

  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);

  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [hasLocationConsent, setHasLocationConsent] = useState(false);
  const [isLoadingConsent, setIsLoadingConsent] = useState(true);
  const [isUpdatingConsent, setIsUpdatingConsent] = useState(false);

  useEffect(() => {
    let mounted = true;

    if (user?.id == null || user.tenant_id == null) {
      setHasLocationConsent(false);
      setIsLoadingConsent(false);

      return () => {
        mounted = false;
      };
    }

    setIsLoadingConsent(true);

    void hasTechnicianLocationConsent({
      technicianId: user.id,
      tenantId: user.tenant_id
    })
      .then((granted) => {
        if (mounted) {
          setHasLocationConsent(granted);
        }
      })
      .catch((error: unknown) => {
        logError("gps.location_consent_read_failed", error);

        if (mounted) {
          setHasLocationConsent(false);
        }
      })
      .finally(() => {
        if (mounted) {
          setIsLoadingConsent(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, [user?.id, user?.tenant_id]);

  async function updateLocationConsent(
    granted: boolean
  ): Promise<void> {
    if (isUpdatingConsent) {
      return;
    }

    if (user?.id == null || user.tenant_id == null) {
      Alert.alert(
        "Account unavailable",
        "Please sign in again before changing location-sharing preferences."
      );
      return;
    }

    const identity = {
      technicianId: user.id,
      tenantId: user.tenant_id
    };

    setIsUpdatingConsent(true);

    try {
      if (granted) {
        await setTechnicianLocationConsent(identity, true);

        try {
          await startTechnicianLocationTracking(identity);
        } catch (error: unknown) {
          // Do not leave consent enabled when tracking could not start.
          try {
            await setTechnicianLocationConsent(identity, false);
          } catch (rollbackError: unknown) {
            logError(
              "gps.location_consent_rollback_failed",
              rollbackError
            );
          }

          throw error;
        }

        setHasLocationConsent(true);

        Alert.alert(
          "Location sharing enabled",
          "FieldOps can now share your location for technician availability and active job tracking, subject to your device permissions."
        );
      } else {
        // Persist withdrawal before stopping the native tracking service.
        await setTechnicianLocationConsent(identity, false);
        setHasLocationConsent(false);

        await stopTechnicianLocationTracking();

        Alert.alert(
          "Location sharing disabled",
          "Background tracking has been stopped. Any locally queued GPS points associated with the active job are cleared."
        );
      }
    } catch (error: unknown) {
      logError("gps.location_consent_update_failed", error);

      Alert.alert(
        granted ? "Unable to enable tracking" : "Tracking cleanup issue",
        granted
          ? "Location sharing could not be enabled. Check your device's location permissions and try again."
          : "Your consent has been withdrawn, but tracking cleanup reported an error. Please check the app before continuing to use location-dependent features."
      );

      try {
        const savedConsent = await hasTechnicianLocationConsent(identity);
        setHasLocationConsent(savedConsent);
      } catch {
        setHasLocationConsent(false);
      }
    } finally {
      setIsUpdatingConsent(false);
    }
  }

  function confirmLocationConsentChange(): void {
    if (hasLocationConsent) {
      Alert.alert(
        "Turn off location sharing?",
        "Background GPS tracking will stop. Any locally queued GPS points associated with the active job will be cleared.",
        [
          { text: "Keep enabled", style: "cancel" },
          {
            text: "Turn off",
            style: "destructive",
            onPress: () => {
              void updateLocationConsent(false);
            }
          }
        ]
      );

      return;
    }

    Alert.alert(
      "Enable background location?",
      "While you are signed in, FieldOps will use your location for technician availability and active job tracking, including when the app is in the background. You can withdraw this consent from your profile. Device location permissions are also required.",
      [
        { text: "Not now", style: "cancel" },
        {
          text: "Allow location sharing",
          onPress: () => {
            void updateLocationConsent(true);
          }
        }
      ]
    );
  }

  async function handleLogout(): Promise<void> {
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

      <Text style={styles.sectionTitle}>Location sharing</Text>

      <View style={styles.locationCard}>
        <Text style={styles.locationHeading}>
          Background location tracking
        </Text>

        <Text style={styles.locationDescription}>
          Allow FieldOps to use your location for technician
          availability and active job tracking while you are signed in,
          including when the app is in the background.
        </Text>

        <View style={styles.consentStatus}>
          <View
            style={[
              styles.statusDot,
              hasLocationConsent
                ? styles.statusEnabled
                : styles.statusDisabled
            ]}
          />

          <Text style={styles.consentStatusText}>
            {isLoadingConsent
              ? "Checking preference..."
              : hasLocationConsent
                ? "Consent granted"
                : "Consent not granted"}
          </Text>
        </View>

        <Pressable
          accessibilityRole="button"
          accessibilityLabel={
            hasLocationConsent
              ? "Withdraw location-sharing consent"
              : "Enable background location sharing"
          }
          disabled={
            isLoadingConsent ||
            isUpdatingConsent ||
            user?.id == null ||
            user.tenant_id == null
          }
          onPress={confirmLocationConsentChange}
          style={({ pressed }) => [
            styles.consentButton,
            hasLocationConsent && styles.withdrawButton,
            pressed && styles.consentButtonPressed,
            (isLoadingConsent || isUpdatingConsent) &&
              styles.disabledButton
          ]}
        >
          {isUpdatingConsent || isLoadingConsent ? (
            <ActivityIndicator color="#FFFFFF" />
          ) : (
            <Text style={styles.consentButtonText}>
              {hasLocationConsent
                ? "Turn off location sharing"
                : "Enable location sharing"}
            </Text>
          )}
        </Pressable>

        <Text style={styles.locationFootnote}>
          Device location permissions are required. Withdrawing consent
          stops tracking; previously submitted backend records are not
          deleted by this setting.
        </Text>
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
  locationCard: {
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#E2E8F0",
    borderRadius: 12,
    padding: 18,
    marginBottom: 24
  },
  locationHeading: {
    color: "#0F172A",
    fontSize: 16,
    fontWeight: "700"
  },
  locationDescription: {
    color: "#64748B",
    fontSize: 14,
    lineHeight: 21,
    marginTop: 8
  },
  consentStatus: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: 16,
    marginBottom: 14
  },
  statusDot: {
    width: 9,
    height: 9,
    borderRadius: 5,
    marginRight: 8
  },
  statusEnabled: {
    backgroundColor: "#15803D"
  },
  statusDisabled: {
    backgroundColor: "#64748B"
  },
  consentStatusText: {
    color: "#334155",
    fontSize: 13,
    fontWeight: "600"
  },
  consentButton: {
    minHeight: 48,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#0F766E",
    borderRadius: 10,
    paddingHorizontal: 12
  },
  withdrawButton: {
    backgroundColor: "#475569"
  },
  consentButtonPressed: {
    opacity: 0.85
  },
  disabledButton: {
    opacity: 0.6
  },
  consentButtonText: {
    color: "#FFFFFF",
    fontSize: 14,
    fontWeight: "700",
    textAlign: "center"
  },
  locationFootnote: {
    color: "#64748B",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 12
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
  signOutText: {
    color: "#FFFFFF",
    fontSize: 15,
    fontWeight: "700"
  }
});