import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import * as Location from "expo-location";
import { router, useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { customerApi } from "../../src/customer/api/customer";
import { getApiErrorMessage } from "../../src/customer/api/client";
import { useAuthStore } from "../../src/customer/auth/authStore";
import { AppButton, ErrorState, LoadingView, Screen } from "../../src/customer/components/ui";
import type { CustomerProfile, ReverseLocation } from "../../src/customer/types/api";
import { colors } from "../../src/customer/theme";
import { useFocusedAutoRefresh } from "../../src/customer/hooks/useFocusedAutoRefresh";
import { consumePickedServiceLocation } from "../../src/customer/utils/locationSelection";

type CustomerProfileWithDefault = CustomerProfile & {
  is_default_location?: boolean;
};

type LocationDetails = {
  address: string;
  city: string;
  state: string;
  pincode: string;
};

async function resolveLocationDetails(
  latitude: number,
  longitude: number,
): Promise<LocationDetails> {
  let remote: ReverseLocation | null = null;
  try {
    remote = await customerApi.reverseLocation(latitude, longitude);
  } catch {
    // Expo's reverse geocoder below is the fallback when the app API is unavailable.
  }

  let local: Location.LocationGeocodedAddress | null = null;
  if (!remote?.address || !remote.city || !remote.state || !remote.pincode) {
    try {
      const addresses = await Location.reverseGeocodeAsync({ latitude, longitude });
      local = addresses[0] ?? null;
    } catch {
      // Keep any fields returned by the app API.
    }
  }

  const localAddress = local
    ? [
        [local.streetNumber, local.street].filter(Boolean).join(" "),
        local.district,
        local.city,
        local.region,
        local.postalCode,
        local.country,
      ]
        .filter(Boolean)
        .filter((part, index, all) => all.indexOf(part) === index)
        .join(", ")
    : "";

  return {
    address:
      remote?.formatted_address ||
      remote?.address ||
      remote?.display_name ||
      remote?.name ||
      localAddress,
    city: remote?.city || local?.city || local?.district || local?.subregion || "",
    state: remote?.state || local?.region || "",
    pincode: (remote?.pincode || local?.postalCode || "").replace(/\D/g, "").slice(0, 6),
  };
}

function ProfileSectionHeading({
  icon,
  title,
  subtitle,
  onEdit,
  editing,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  subtitle: string;
  onEdit: () => void;
  editing: boolean;
}) {
  return (
    <View style={styles.sectionHeading}>
      <View style={styles.sectionIcon}>
        <Ionicons name={icon} size={25} color={colors.brand} />
      </View>
      <View style={styles.sectionHeadingCopy}>
        <Text style={styles.sectionTitle}>{title}</Text>
        <Text style={styles.sectionSubtitle}>{subtitle}</Text>
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Edit ${title.toLowerCase()}`}
        onPress={onEdit}
        style={({ pressed }) => [styles.editButton, pressed && styles.pressed]}
      >
        <Ionicons name={editing ? "checkmark" : "create-outline"} size={17} color={colors.brand} />
        <Text style={styles.editButtonText}>{editing ? "Editing" : "Edit"}</Text>
      </Pressable>
    </View>
  );
}

function DetailRow({
  icon,
  label,
  value,
  editing,
  onChangeText,
  placeholder,
  keyboardType,
  autoCapitalize,
  maxLength,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  value: string;
  editing: boolean;
  onChangeText?: (value: string) => void;
  placeholder?: string;
  keyboardType?: "default" | "email-address" | "phone-pad" | "number-pad";
  autoCapitalize?: "none" | "sentences" | "words";
  maxLength?: number;
}) {
  const canEdit = editing && Boolean(onChangeText);
  return (
    <View style={styles.detailRow}>
      <Ionicons name={icon} size={21} color={colors.brandMid} style={styles.detailIcon} />
      <Text style={styles.detailLabel}>{label}</Text>
      {canEdit ? (
        <TextInput
          value={value}
          onChangeText={onChangeText}
          placeholder={placeholder}
          placeholderTextColor="#99A69F"
          keyboardType={keyboardType}
          autoCapitalize={autoCapitalize}
          maxLength={maxLength}
          style={styles.detailInput}
        />
      ) : (
        <Text style={styles.detailValue} numberOfLines={2}>
          {value.trim() || "—"}
        </Text>
      )}
      {!canEdit ? <Ionicons name="chevron-forward" size={19} color="#87938B" /> : null}
    </View>
  );
}

export default function CustomerProfileScreen() {
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const [profile, setProfile] = useState<CustomerProfile | null>(null);
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [city, setCity] = useState("");
  const [state, setState] = useState("");
  const [pincode, setPincode] = useState("");
  const [company, setCompany] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [locating, setLocating] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [isDefaultLocation, setIsDefaultLocation] = useState(true);
  const [error, setError] = useState("");
  const [loadingProfileFailed, setLoadingProfileFailed] = useState(false);

  const loadProfile = useCallback(async (silent = false) => {
    if (!silent) {
      setLoading(true);
      setError("");
    }
    try {
      const value = await customerApi.profile();
      setProfile(value);
      setFullName(value.full_name || "");
      setPhone(value.mobile_number || "");
      setAddress(value.address || "");
      setCity(value.city || "");
      setState(value.state || "");
      setPincode(value.pincode || "");
      setCompany(value.company_name || "");
      setIsDefaultLocation((value as CustomerProfileWithDefault).is_default_location ?? true);
      setLoadingProfileFailed(false);
    } catch (e) {
      setLoadingProfileFailed(true);
      const status = (e as { response?: { status?: number } })?.response?.status;
      if (status !== 404) {
        setError(getApiErrorMessage(e, "Could not load your customer profile."));
      }
      setProfile(null);
      setFullName([user?.first_name, user?.last_name].filter(Boolean).join(" "));
      setPhone("");
      setAddress("");
      setCity("");
      setState("");
      setPincode("");
      setCompany("");
    } finally {
      if (!silent) setLoading(false);
    }
  }, [user?.first_name, user?.last_name]);

  useEffect(() => {
    void loadProfile();
  }, [loadProfile]);

  useFocusedAutoRefresh(
    () => loadProfile(true),
    !isEditing && !saving && !locating,
  );

  useFocusEffect(
    useCallback(() => {
      let active = true;
      const selection = consumePickedServiceLocation();
      if (!selection) return;

      setError("");
      setIsEditing(true);
      setAddress(selection.address);
      setCity("");
      setState("");
      setPincode("");

      void resolveLocationDetails(selection.latitude, selection.longitude)
        .then((details) => {
          if (!active) return;
          setCity(details.city);
          setState(details.state);
          setPincode(details.pincode);
          if (!details.city || !details.state || !details.pincode) {
            Alert.alert(
              "Location selected",
              "The address was added. Please verify the city, state and PIN code before saving.",
            );
          }
        })
        .catch(() => {
          if (active) {
            Alert.alert(
              "Location selected",
              "The address was added. Please enter or verify the city, state and PIN code before saving.",
            );
          }
        });

      return () => {
        active = false;
      };
    }, []),
  );

  const useCurrentLocation = async () => {
    setLocating(true);
    setError("");
    setIsEditing(true);
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (permission.status !== "granted") {
        throw new Error("Location permission is required to find your address.");
      }
      const position = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
      const latitude = position.coords.latitude;
      const longitude = position.coords.longitude;
      if (!Number.isFinite(latitude) || !Number.isFinite(longitude) || (latitude === 0 && longitude === 0)) {
        throw new Error("Your device did not return valid GPS coordinates.");
      }

      const details = await resolveLocationDetails(latitude, longitude);
      if (!details.address) {
        throw new Error("Your location was found, but its address could not be resolved. Please try again.");
      }
      setAddress(details.address);
      setCity(details.city);
      setState(details.state);
      setPincode(details.pincode);
      Alert.alert("Location fetched", "Your address, city, state and PIN code have been filled in. Please verify them before saving.");
    } catch (e) {
      setError(e instanceof Error ? e.message : getApiErrorMessage(e, "Could not fetch your current address."));
    } finally {
      setLocating(false);
    }
  };

  const openMapPicker = () => {
    setError("");
    setIsEditing(true);
    router.push({
      pathname: "/customer/location-picker",
      params: { address: address.trim() },
    });
  };

  const save = async () => {
    setError("");
    if (fullName.trim().length < 2) {
      setError("Enter your full name.");
      return;
    }
    if (!/^\d{10}$/.test(phone.trim())) {
      setError("Enter a 10-digit mobile number.");
      return;
    }
    if (pincode.trim() && !/^\d{6}$/.test(pincode.trim())) {
      setError("Enter a 6-digit PIN code.");
      return;
    }

    setSaving(true);
    try {
      const payload = {
        full_name: fullName.trim(),
        mobile_number: phone.trim(),
        address: address.trim() || null,
        city: city.trim() || null,
        state: state.trim() || null,
        pincode: pincode.trim() || null,
        company_name: company.trim() || null,
      };
      const updated = profile?.id && !loadingProfileFailed
        ? await customerApi.updateProfile(payload)
        : await customerApi.createProfile(payload);
      setProfile(updated);
      setLoadingProfileFailed(false);
      setIsEditing(false);
      Alert.alert("Profile saved", "Your profile has been updated.");
    } catch (e) {
      setError(getApiErrorMessage(e, "Could not save your profile."));
    } finally {
      setSaving(false);
    }
  };

  const goHome = () => router.replace("/customer/(tabs)/index");

  const cancel = () => {
    if (!isEditing) {
      goHome();
      return;
    }
    setFullName(profile?.full_name || [user?.first_name, user?.last_name].filter(Boolean).join(" "));
    setPhone(profile?.mobile_number || "");
    setAddress(profile?.address || "");
    setCity(profile?.city || "");
    setState(profile?.state || "");
    setPincode(profile?.pincode || "");
    setCompany(profile?.company_name || "");
    setIsDefaultLocation((profile as CustomerProfileWithDefault | null)?.is_default_location ?? true);
    setError("");
    setIsEditing(false);
  };

  const confirmLogout = () => {
    Alert.alert("Sign out", "Are you sure you want to sign out?", [
      { text: "Cancel", style: "cancel" },
      { text: "Sign out", style: "destructive", onPress: () => void logout() },
    ]);
  };

  const addressSummary = [address, city, state, pincode].filter(Boolean).join(", ");
  const displayName = fullName.trim() || user?.email || "Customer";
  const initials = displayName.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
  if (loading) return <Screen><LoadingView message="Loading your profile…" /></Screen>;

  return (
    <Screen contentStyle={styles.screenContent}>
      <View style={styles.pageHeading}>
        <Pressable onPress={goHome} style={styles.backButton} accessibilityRole="button" accessibilityLabel="Go to home">
          <Ionicons name="arrow-back" size={21} color={colors.brand} />
        </Pressable>
        <View style={styles.pageHeadingText}>
          <Text style={styles.pageTitle}>My Profile</Text>
          <Text style={styles.pageSubtitle}>Manage your personal details and service address</Text>
        </View>
      </View>

      <View style={styles.hero}>
        <View style={styles.heroOrbOne} />
        <View style={styles.heroOrbTwo} />
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>{initials || "C"}</Text>
          <View style={styles.avatarBadge}><Ionicons name="person" size={18} color="#FFFFFF" /></View>
        </View>
        <View style={styles.heroDetails}>
          <Text style={styles.heroName} numberOfLines={1}>{displayName}</Text>
          <Text style={styles.heroEmail} numberOfLines={1}>{profile?.email || user?.email || "Email not available"}</Text>
          {phone ? (
            <View style={styles.heroPhoneRow}>
              <Ionicons name="call-outline" size={17} color="#D6F4E6" />
              <Text style={styles.heroPhone}>{phone}</Text>
            </View>
          ) : null}
          <View style={styles.customerBadge}><Ionicons name="checkmark-circle" size={17} color="#8DF0A8" /><Text style={styles.customerBadgeText}>Customer</Text></View>
        </View>
        <Pressable onPress={() => setIsEditing(true)} style={styles.heroEdit} accessibilityRole="button" accessibilityLabel="Edit profile">
          <Ionicons name="create-outline" size={24} color="#FFFFFF" />
        </Pressable>
      </View>

      {error ? <ErrorState message={error} /> : null}

      <View style={styles.sectionCard}>
        <ProfileSectionHeading
          icon="person-outline"
          title="Personal Details"
          subtitle="Your basic account information"
          editing={isEditing}
          onEdit={() => setIsEditing(true)}
        />
        <View style={styles.rowsCard}>
          <DetailRow icon="person-outline" label="Full Name" value={fullName} editing={isEditing} onChangeText={setFullName} placeholder="Full name" autoCapitalize="words" maxLength={200} />
          <DetailRow icon="mail-outline" label="Email Address" value={profile?.email || user?.email || ""} editing={false} />
          <DetailRow icon="call-outline" label="Mobile Number" value={phone} editing={isEditing} onChangeText={(value) => setPhone(value.replace(/\D/g, "").slice(0, 10))} placeholder="10-digit mobile number" keyboardType="phone-pad" maxLength={10} />
          <DetailRow icon="briefcase-outline" label="Company" value={company} editing={isEditing} onChangeText={setCompany} placeholder="Optional" autoCapitalize="words" />
        </View>
      </View>

      <View style={styles.sectionCard}>
        <ProfileSectionHeading
          icon="location-outline"
          title="Default Service Address"
          subtitle="Your current service location for bookings"
          editing={isEditing}
          onEdit={() => setIsEditing(true)}
        />

        {isEditing ? (
          <View style={styles.addressFields}>
            <Text style={styles.inputLabel}>Street address</Text>
            <TextInput value={address} onChangeText={setAddress} placeholder="House, street and area" placeholderTextColor="#89968F" multiline style={[styles.addressInput, styles.multilineInput]} />
            <View style={styles.localityRow}>
              <View style={styles.localityField}><Text style={styles.inputLabel}>City</Text><TextInput value={city} onChangeText={setCity} placeholder="City" placeholderTextColor="#89968F" style={styles.addressInput} /></View>
              <View style={styles.localityField}><Text style={styles.inputLabel}>State</Text><TextInput value={state} onChangeText={setState} placeholder="State" placeholderTextColor="#89968F" style={styles.addressInput} /></View>
              <View style={styles.pinField}><Text style={styles.inputLabel}>PIN code</Text><TextInput value={pincode} onChangeText={(value) => setPincode(value.replace(/\D/g, "").slice(0, 6))} placeholder="6 digits" placeholderTextColor="#89968F" keyboardType="number-pad" maxLength={6} style={styles.addressInput} /></View>
            </View>
          </View>
        ) : (
          <View style={styles.addressSummary}>
            <Ionicons name="location-outline" size={25} color={colors.brandMid} />
            <Text style={styles.addressSummaryText}>{addressSummary || "Add a service address to speed up future bookings."}</Text>
            <Ionicons name="map-outline" size={38} color="#58A77A" />
          </View>
        )}

        <View style={styles.locationActions}>
          <Pressable style={({ pressed }) => [styles.locationButton, pressed && styles.pressed]} onPress={() => void useCurrentLocation()} disabled={locating || saving}>
            <Ionicons name="locate-outline" size={22} color={colors.brand} />
            <Text style={styles.locationButtonText}>{locating ? "Finding…" : "Use My Location"}</Text>
          </Pressable>
          <Pressable style={({ pressed }) => [styles.locationButton, pressed && styles.pressed]} onPress={openMapPicker} disabled={locating || saving}>
            <Ionicons name="map-outline" size={22} color={colors.brand} />
            <Text style={styles.locationButtonText}>Change Location</Text>
          </Pressable>
        </View>

        <Pressable
          accessibilityRole="checkbox"
          accessibilityState={{ checked: isDefaultLocation }}
          onPress={() => { setIsEditing(true); setIsDefaultLocation((value) => !value); }}
          style={styles.defaultAddressRow}
        >
          <Ionicons name={isDefaultLocation ? "checkbox" : "square-outline"} size={24} color={isDefaultLocation ? colors.brandMid : colors.muted} />
          <View style={styles.defaultAddressCopy}>
            <Text style={styles.defaultAddressTitle}>Use as my default service address</Text>
            <Text style={styles.defaultAddressSubtitle}>Use this address for future service bookings.</Text>
          </View>
        </Pressable>
      </View>

      {isEditing ? (
        <>
          <AppButton title="Save Changes" icon="checkmark-circle-outline" onPress={() => void save()} loading={saving} disabled={locating} style={styles.saveButton} />
          <AppButton title="Cancel" kind="ghost" onPress={cancel} disabled={saving || locating} style={styles.cancelButton} />
        </>
      ) : (
        <AppButton title="Edit Profile" icon="create-outline" onPress={() => setIsEditing(true)} style={styles.saveButton} />
      )}
      <AppButton title="Sign out" icon="log-out-outline" kind="danger" onPress={confirmLogout} disabled={saving || locating} style={styles.logoutButton} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  screenContent: { paddingHorizontal: 16, paddingTop: 10, paddingBottom: 28, gap: 16 },
  pageHeading: { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 4 },
  backButton: { width: 43, height: 43, borderRadius: 22, backgroundColor: "#E6F4EC", alignItems: "center", justifyContent: "center" },
  pageHeadingText: { flex: 1, gap: 2 },
  pageTitle: { color: colors.brand, fontSize: 24, lineHeight: 29, fontWeight: "900" },
  pageSubtitle: { color: colors.muted, fontSize: 12, lineHeight: 17 },
  hero: { minHeight: 168, borderRadius: 25, padding: 18, flexDirection: "row", alignItems: "center", gap: 14, backgroundColor: "#064B38", overflow: "hidden", position: "relative" },
  heroOrbOne: { position: "absolute", width: 210, height: 210, borderRadius: 110, backgroundColor: "#0B6248", top: -128, right: -30, opacity: 0.7 },
  heroOrbTwo: { position: "absolute", width: 190, height: 150, borderRadius: 100, backgroundColor: "#07543E", bottom: -112, left: 40, opacity: 0.9 },
  avatar: { width: 78, height: 78, borderRadius: 40, backgroundColor: "#D9F3E3", alignItems: "center", justifyContent: "center", borderWidth: 3, borderColor: "#77D99A" },
  avatarText: { color: colors.brand, fontSize: 25, fontWeight: "900" },
  avatarBadge: { position: "absolute", right: -2, bottom: -1, width: 28, height: 28, borderRadius: 15, alignItems: "center", justifyContent: "center", backgroundColor: "#08724F", borderWidth: 2, borderColor: "#D9F3E3" },
  heroDetails: { flex: 1, gap: 4 },
  heroName: { color: "#FFFFFF", fontSize: 20, fontWeight: "900" },
  heroEmail: { color: "#D5E9DF", fontSize: 12 },
  heroPhoneRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 2 },
  heroPhone: { color: "#FFFFFF", fontSize: 13, fontWeight: "700" },
  customerBadge: { alignSelf: "flex-start", flexDirection: "row", alignItems: "center", gap: 5, marginTop: 5, paddingHorizontal: 9, paddingVertical: 4, borderRadius: 20, backgroundColor: "#0D694B", borderWidth: 1, borderColor: "#288E68" },
  customerBadgeText: { color: "#FFFFFF", fontSize: 11, fontWeight: "800" },
  heroEdit: { width: 42, height: 42, borderRadius: 14, backgroundColor: "#FFFFFF1A", borderWidth: 1, borderColor: "#69A88B", alignItems: "center", justifyContent: "center" },
  sectionCard: { padding: 14, borderRadius: 22, backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#DCE9E1", gap: 12, shadowColor: "#16432E", shadowOpacity: 0.05, shadowRadius: 8, shadowOffset: { width: 0, height: 3 }, elevation: 2 },
  sectionHeading: { flexDirection: "row", alignItems: "center", gap: 10 },
  sectionIcon: { width: 46, height: 46, borderRadius: 15, backgroundColor: "#DDF9E8", alignItems: "center", justifyContent: "center" },
  sectionHeadingCopy: { flex: 1, gap: 2 },
  sectionTitle: { color: colors.text, fontSize: 16, fontWeight: "900" },
  sectionSubtitle: { color: colors.muted, fontSize: 11, lineHeight: 15 },
  editButton: { minWidth: 66, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 4, paddingHorizontal: 9, paddingVertical: 8, borderRadius: 12, backgroundColor: "#F0FBF4", borderWidth: 1, borderColor: "#91D4A9" },
  editButtonText: { color: colors.brand, fontSize: 12, fontWeight: "800" },
  rowsCard: { paddingHorizontal: 12, borderRadius: 17, backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#E8EFEB" },
  detailRow: { minHeight: 54, flexDirection: "row", alignItems: "center", gap: 9, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: "#DCE5DF" },
  detailIcon: { width: 23 },
  detailLabel: { width: 92, color: colors.text, fontSize: 11, fontWeight: "700" },
  detailValue: { flex: 1, color: colors.text, fontSize: 12, fontWeight: "600" },
  detailInput: { flex: 1, minHeight: 40, paddingVertical: 5, color: colors.text, fontSize: 12, borderBottomWidth: 1, borderBottomColor: "#94CDA6" },
  addressSummary: { minHeight: 96, flexDirection: "row", alignItems: "center", gap: 12, padding: 15, borderRadius: 18, backgroundColor: "#F0F8F3" },
  addressSummaryText: { flex: 1, color: colors.text, fontSize: 14, lineHeight: 21, fontWeight: "700" },
  addressFields: { gap: 8 },
  inputLabel: { color: colors.muted, fontSize: 11, fontWeight: "800" },
  addressInput: { minHeight: 43, borderRadius: 11, borderWidth: 1, borderColor: "#D9E5DD", paddingHorizontal: 11, paddingVertical: 9, color: colors.text, fontSize: 13, backgroundColor: "#FFFFFF" },
  multilineInput: { minHeight: 70, textAlignVertical: "top" },
  localityRow: { flexDirection: "row", gap: 8 },
  localityField: { flex: 1, gap: 5 },
  pinField: { width: 88, gap: 5 },
  locationActions: { flexDirection: "row", gap: 8 },
  locationButton: { flex: 1, minHeight: 48, paddingHorizontal: 8, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, borderRadius: 14, backgroundColor: "#F2F9F5", borderWidth: 1, borderColor: "#CDE6D6" },
  locationButtonText: { color: colors.brand, fontSize: 11, fontWeight: "800" },
  defaultAddressRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingTop: 2 },
  defaultAddressCopy: { flex: 1, gap: 3 },
  defaultAddressTitle: { color: colors.text, fontSize: 13, fontWeight: "900" },
  defaultAddressSubtitle: { color: colors.muted, fontSize: 11, lineHeight: 16 },
  saveButton: { minHeight: 54, borderRadius: 18, backgroundColor: "#00613F", borderWidth: 1, borderColor: "#52CB74" },
  cancelButton: { minHeight: 48, borderRadius: 18, borderColor: "#C9DCD1" },
  logoutButton: { minHeight: 48, borderRadius: 16 },
  pressed: { opacity: 0.76 },
});
