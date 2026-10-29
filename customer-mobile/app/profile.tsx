
import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Pressable,
  Text,
  View,
} from "react-native";
import * as Location from "expo-location";
import { router } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { customerApi } from "../src/api/customer";
import { getApiErrorMessage } from "../src/api/client";
import { useAuthStore } from "../src/auth/authStore";
import {
  AppButton,
  Card,
  ErrorState,
  Field,
  Header,
  LoadingView,
  Screen,
} from "../src/components/ui";
import type { CustomerProfile } from "../src/types/api";
import { colors } from "../src/theme";

type CustomerProfileWithDefault = CustomerProfile & {
  is_default_location?: boolean;
};

export default function CustomerProfileScreen() {
  const user = useAuthStore((state) => state.user);

  const [profile, setProfile] =
    useState<CustomerProfile | null>(null);

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

  const [isDefaultLocation, setIsDefaultLocation] =
    useState(true);

  const [error, setError] = useState("");
  const [loadingProfileFailed, setLoadingProfileFailed] =
    useState(false);

  const loadProfile = useCallback(async () => {
    let active = true;

    setLoading(true);
    setError("");

    try {
      const value = await customerApi.profile();

      if (!active) return;

      setProfile(value);
      setFullName(value.full_name || "");
      setPhone(value.mobile_number || "");
      setAddress(value.address || "");
      setCity(value.city || "");
      setState(value.state || "");
      setPincode(value.pincode || "");
      setCompany(value.company_name || "");

      const savedDefault =
        (value as CustomerProfileWithDefault)
          .is_default_location;

      setIsDefaultLocation(savedDefault ?? true);
      setLoadingProfileFailed(false);
    } catch (e) {
      if (!active) return;

      setLoadingProfileFailed(true);

      const status = (
        e as { response?: { status?: number } }
      )?.response?.status;

      if (status !== 404) {
        setError(
          getApiErrorMessage(
            e,
            "Could not load your customer profile.",
          ),
        );
      }

      setFullName(
        [user?.first_name, user?.last_name]
          .filter(Boolean)
          .join(" "),
      );
      setPhone("");
      setProfile(null);
    } finally {
      if (active) {
        setLoading(false);
      }
    }

    return () => {
      active = false;
    };
  }, [user?.first_name, user?.last_name]);

  useEffect(() => {
    let active = true;

    const run = async () => {
      try {
        const value = await customerApi.profile();

        if (!active) return;

        setProfile(value);
        setFullName(value.full_name || "");
        setPhone(value.mobile_number || "");
        setAddress(value.address || "");
        setCity(value.city || "");
        setState(value.state || "");
        setPincode(value.pincode || "");
        setCompany(value.company_name || "");

        const savedDefault =
          (value as CustomerProfileWithDefault)
            .is_default_location;

        setIsDefaultLocation(savedDefault ?? true);
        setLoadingProfileFailed(false);
      } catch (e) {
        if (!active) return;

        setLoadingProfileFailed(true);

        const status = (
          e as { response?: { status?: number } }
        )?.response?.status;

        if (status !== 404) {
          setError(
            getApiErrorMessage(
              e,
              "Could not load your customer profile.",
            ),
          );
        }

        setFullName(
          [user?.first_name, user?.last_name]
            .filter(Boolean)
            .join(" "),
        );
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    void run();

    return () => {
      active = false;
    };
  }, [user?.first_name, user?.last_name]);

  const useCurrentLocation = async () => {
    setLocating(true);
    setError("");

    try {
      const permission =
        await Location.requestForegroundPermissionsAsync();

      if (permission.status !== "granted") {
        throw new Error(
          "Location permission is required to find your address.",
        );
      }

      const position =
        await Location.getCurrentPositionAsync({
          accuracy: Location.Accuracy.High,
        });

      const latitude = position.coords.latitude;
      const longitude = position.coords.longitude;

      if (
        !Number.isFinite(latitude) ||
        !Number.isFinite(longitude) ||
        (latitude === 0 && longitude === 0)
      ) {
        throw new Error(
          "Your device did not return valid GPS coordinates.",
        );
      }

      const result = await customerApi.reverseLocation(
        latitude,
        longitude,
      );

      const resolvedAddress =
        result.formatted_address ||
        result.address ||
        result.display_name ||
        result.name;

      if (!resolvedAddress) {
        throw new Error(
          "Your location was found, but its address could not be resolved. Please try again.",
        );
      }

      setAddress(resolvedAddress);
      setCity(result.city || "");
      setState(result.state || "");
      setPincode(
        (result.pincode || "")
          .replace(/\D/g, "")
          .slice(0, 6),
      );

      Alert.alert(
        "Location fetched",
        "Your address details have been filled in. Please verify the address and PIN code before saving.",
      );
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : getApiErrorMessage(
              e,
              "Could not fetch your current address.",
            ),
      );
    } finally {
      setLocating(false);
    }
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

    if (
      pincode.trim() &&
      !/^\d{6}$/.test(pincode.trim())
    ) {
      setError("Enter a 6-digit postal code.");
      return;
    }

    setSaving(true);

    try {
      // Do not send is_default_location until the backend
      // schema and persistence support that field.
      const payload = {
        full_name: fullName.trim(),
        mobile_number: phone.trim(),
        address: address.trim() || null,
        city: city.trim() || null,
        state: state.trim() || null,
        pincode: pincode.trim() || null,
        company_name: company.trim() || null,
      };

      const updated =
        profile?.id && !loadingProfileFailed
          ? await customerApi.updateProfile(payload)
          : await customerApi.createProfile(payload);

      setProfile(updated);
      setLoadingProfileFailed(false);

      Alert.alert(
        "Profile saved",
        "Your customer profile has been updated.",
        [
          {
            text: "Done",
            onPress: () => router.back(),
          },
        ],
      );
    } catch (e) {
      setError(
        getApiErrorMessage(
          e,
          "Could not save your profile.",
        ),
      );
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Screen>
        <LoadingView message="Loading your profile…" />
      </Screen>
    );
  }

  return (
    <Screen>
      <Header
        title="Your profile"
        subtitle="Keep your contact details and service address up to date"
        right={
          <View
            style={{
              height: 40,
              width: 40,
              borderRadius: 14,
              backgroundColor: colors.brandSoft,
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Ionicons
              name="person-outline"
              size={20}
              color={colors.brand}
            />
          </View>
        }
      />

      {error ? <ErrorState message={error} /> : null}

      <Card>
        <Text
          style={{
            color: colors.text,
            fontSize: 17,
            fontWeight: "800",
          }}
        >
          Personal details
        </Text>

        <Field
          label="Full name"
          value={fullName}
          onChangeText={setFullName}
          editable={isEditing}
          placeholder="Your full name"
          maxLength={200}
        />

        <Field
          label="Email address"
          value={profile?.email || user?.email || ""}
          editable={false}
          placeholder="Email associated with your account"
          keyboardType="email-address"
          autoCapitalize="none"
        />

        <Field
          label="Mobile number"
          value={phone}
          onChangeText={(value) =>
            setPhone(value.replace(/\D/g, "").slice(0, 10))
          }
          editable={isEditing}
          placeholder="10-digit mobile number"
          keyboardType="phone-pad"
          maxLength={10}
        />

        <Field
          label="Company (optional)"
          value={company}
          onChangeText={setCompany}
          editable={isEditing}
          placeholder="Company or business name"
        />
      </Card>

      <Card>
        <Text
          style={{
            color: colors.text,
            fontSize: 17,
            fontWeight: "800",
          }}
        >
          Default service address
        </Text>

        <Field
          label="Address"
          value={address}
          onChangeText={setAddress}
          editable={isEditing}
          placeholder="House / flat, street, area"
          multiline
        />

        <AppButton
          title="Use my location"
          icon="locate-outline"
          kind="secondary"
          loading={locating}
          disabled={!isEditing || locating}
          onPress={() => void useCurrentLocation()}
        />

        <Pressable
          accessibilityRole="checkbox"
          accessibilityState={{
            checked: isDefaultLocation,
          }}
          onPress={() =>
            setIsDefaultLocation((current) => !current)
          }
          disabled={!isEditing}
          style={{
            flexDirection: "row",
            alignItems: "center",
            gap: 10,
            paddingVertical: 8,
          }}
        >
          <Ionicons
            name={
              isDefaultLocation
                ? "checkbox"
                : "square-outline"
            }
            size={23}
            color={
              isDefaultLocation
                ? colors.brand
                : colors.muted
            }
          />

          <View style={{ flex: 1, gap: 3 }}>
            <Text
              style={{
                color: colors.text,
                fontSize: 13,
                fontWeight: "800",
              }}
            >
              Use as my default service address
            </Text>

            <Text
              style={{
                color: colors.muted,
                fontSize: 11,
                lineHeight: 16,
              }}
            >
              Use this address for future service bookings.
            </Text>
          </View>
        </Pressable>

        <Field
          label="City"
          value={city}
          onChangeText={setCity}
          editable={isEditing}
          placeholder="City"
        />

        <Field
          label="State"
          value={state}
          onChangeText={setState}
          editable={isEditing}
          placeholder="State"
        />

        <Field
          label="PIN / postal code"
          value={pincode}
          onChangeText={(value) =>
            setPincode(value.replace(/\D/g, "").slice(0, 6))
          }
          editable={isEditing}
          keyboardType="number-pad"
          placeholder="6-digit postal code"
          maxLength={6}
        />

        <View
          style={{
            backgroundColor: colors.accentLight,
            borderRadius: 12,
            padding: 12,
            flexDirection: "row",
            gap: 8,
            alignItems: "flex-start",
          }}
        >
          <Ionicons
            name="information-circle-outline"
            color={colors.brandMid}
            size={20}
          />

          <Text
            style={{
              flex: 1,
              color: colors.muted,
              fontSize: 12,
              lineHeight: 18,
            }}
          >
            Verify the detected address and postal code before saving.
            Each new booking still requires its own confirmed
            service-site coordinates.
          </Text>
        </View>
      </Card>

      <AppButton
        title={isEditing ? "Save profile" : "Edit profile"}
        icon={
          isEditing
            ? "checkmark-circle-outline"
            : "create-outline"
        }
        onPress={() => {
          if (isEditing) {
            void save();
          } else {
            setError("");
            setIsEditing(true);
          }
        }}
        loading={saving}
        disabled={saving || locating}
      />

      <AppButton
        title="Cancel"
        kind="ghost"
        onPress={() => router.back()}
      />
    </Screen>
  );
}
