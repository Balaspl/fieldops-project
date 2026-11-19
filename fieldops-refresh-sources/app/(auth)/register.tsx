
import { useEffect, useState, type ComponentProps } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StatusBar,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import * as Location from "expo-location";
import { router } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { apiClient, getApiErrorMessage } from "../../src/api/client";
import { customerApi } from "../../src/api/customer";
import { useAuthStore } from "../../src/auth/authStore";
import type { LocationSearchResult } from "../../src/types/api";

const BG = "#05442E";
const PANEL = "#073B29";
const BORDER = "#15563A";
const PRIMARY = "#118B45";
const MINT = "#69E7AE";
const LABEL = "#A9C4B4";
const INPUT_BG = "#E8F0FF";
const INPUT_TEXT = "#14251C";

type RegistrationFieldProps = {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder: string;
  icon: ComponentProps<typeof Ionicons>["name"];
  keyboardType?: "default" | "email-address" | "phone-pad";
  secureTextEntry?: boolean;
  autoCapitalize?: "none" | "sentences" | "words";
  onSubmitEditing?: () => void;
  returnKeyType?: "next" | "search" | "done";
  maxLength?: number;
};

function RegistrationField({
  label,
  value,
  onChangeText,
  placeholder,
  icon,
  keyboardType = "default",
  secureTextEntry = false,
  autoCapitalize = "sentences",
  onSubmitEditing,
  returnKeyType = "next",
  maxLength,
}: RegistrationFieldProps) {
  return (
    <View style={{ gap: 6 }}>
      <Text style={{ color: LABEL, fontSize: 12, fontWeight: "700" }}>
        {label}
      </Text>

      <View
        style={{
          minHeight: 46,
          flexDirection: "row",
          alignItems: "center",
          gap: 10,
          paddingHorizontal: 12,
          borderRadius: 11,
          backgroundColor: INPUT_BG,
          borderWidth: 1,
          borderColor: "#D7E4F6",
        }}
      >
        <Ionicons name={icon} size={17} color="#35B983" />

        <TextInput
          value={value}
          onChangeText={onChangeText}
          placeholder={placeholder}
          placeholderTextColor="#8796A8"
          keyboardType={keyboardType}
          secureTextEntry={secureTextEntry}
          autoCapitalize={autoCapitalize}
          autoCorrect={false}
          onSubmitEditing={onSubmitEditing}
          returnKeyType={returnKeyType}
          maxLength={maxLength}
          style={{
            flex: 1,
            paddingVertical: 9,
            color: INPUT_TEXT,
            fontSize: 13,
          }}
          accessibilityLabel={label}
        />
      </View>
    </View>
  );
}

export default function CustomerRegistrationScreen() {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const [locationQuery, setLocationQuery] = useState("");
  const [locationResults, setLocationResults] = useState<
    LocationSearchResult[]
  >([]);
  const [searchingLocations, setSearchingLocations] = useState(false);
  const [locating, setLocating] = useState(false);
  const [locationError, setLocationError] = useState("");
  const [address, setAddress] = useState("");
  const [city, setCity] = useState("");
  const [region, setRegion] = useState("");
  const [pincode, setPincode] = useState("");
  const [coordinates, setCoordinates] = useState<{
    latitude: number;
    longitude: number;
  } | null>(null);

  const login = useAuthStore((state) => state.login);

  const update =
    (setter: (value: string) => void) =>
    (value: string) => {
      setter(value);
      setError("");
    };

  // Search using the existing backend Ola Maps location-search endpoint.
  useEffect(() => {
    let active = true;
    const query = locationQuery.trim();

    if (query.length < 3 || (address && query === address)) {
      setLocationResults([]);
      setSearchingLocations(false);
      return;
    }

    setSearchingLocations(true);

    const timer = setTimeout(async () => {
      try {
        const results = await customerApi.searchLocations(query);

        if (active) {
          setLocationResults(results.slice(0, 6));
          setLocationError(
            results.length
              ? ""
              : "No matching places found. Try a nearby landmark or full address.",
          );
        }
      } catch (e) {
        if (active) {
          setLocationResults([]);
          setLocationError(
            getApiErrorMessage(
              e,
              "Could not search locations. Try using your current location.",
            ),
          );
        }
      } finally {
        if (active) {
          setSearchingLocations(false);
        }
      }
    }, 400);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [locationQuery, address]);

  const applyCoordinates = async (
    latitude: number,
    longitude: number,
    fallbackAddress?: string,
  ) => {
    const result = await customerApi.reverseLocation(latitude, longitude);

    const resolvedAddress =
      result.formatted_address ||
      result.address ||
      result.display_name ||
      result.name ||
      fallbackAddress;

    if (!resolvedAddress) {
      throw new Error(
        result.message || "Could not resolve an address for this location.",
      );
    }

    setCoordinates({ latitude, longitude });
    setAddress(resolvedAddress);
    setLocationQuery(resolvedAddress);
    setCity(result.city || "");
    setRegion(result.state || "");
    setPincode((result.pincode || "").replace(/\D/g, "").slice(0, 6));
    setLocationResults([]);
    setLocationError("");
  };

  const useCurrentLocation = async () => {
    setLocating(true);
    setLocationError("");

    try {
      const permission =
        await Location.requestForegroundPermissionsAsync();

      if (permission.status !== "granted") {
        throw new Error(
          "Allow location access to fetch your current address.",
        );
      }

      const position = await Location.getCurrentPositionAsync({
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

      await applyCoordinates(latitude, longitude);
    } catch (e) {
      setLocationError(
        getApiErrorMessage(e, "Could not fetch your current location."),
      );
    } finally {
      setLocating(false);
    }
  };

  const selectLocation = async (place: LocationSearchResult) => {
    setLocating(true);
    setLocationError("");

    setLocationQuery(
      place.formatted_address || place.name || "Selected place",
    );
    setLocationResults([]);

    try {
      await applyCoordinates(
        place.latitude,
        place.longitude,
        place.formatted_address,
      );
    } catch (e) {
      // Keep the selected result if reverse geocoding fails.
      if (place.formatted_address) {
        setCoordinates({
          latitude: place.latitude,
          longitude: place.longitude,
        });
        setAddress(place.formatted_address);
        setLocationQuery(place.formatted_address);
        setLocationError(
          "Place selected. Please verify the city, state, and PIN code if needed.",
        );
      } else {
        setLocationError(
          getApiErrorMessage(e, "Could not select this location."),
        );
      }
    } finally {
      setLocating(false);
    }
  };

  const submit = async () => {
    setError("");

    const normalizedEmail = email.trim().toLowerCase();
    const cleanPhone = phone.trim();

    if (!firstName.trim() || !lastName.trim()) {
      setError("Enter your first name and last name.");
      return;
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)) {
      setError("Enter a valid email address.");
      return;
    }

    if (!/^\d{10}$/.test(cleanPhone)) {
      setError("Enter a valid 10-digit mobile number.");
      return;
    }

    if (
      password.length < 8 ||
      !/[A-Z]/.test(password) ||
      !/[a-z]/.test(password) ||
      !/\d/.test(password) ||
      !/[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>/?]/.test(password)
    ) {
      setError(
        "Password must be at least 8 characters and include uppercase, lowercase, a number, and a special character.",
      );
      return;
    }

    if (password !== confirmPassword) {
      setError("The passwords do not match.");
      return;
    }

    setSubmitting(true);

    try {
      // Do not send tenant_id from the customer app.
      // The backend determines the registration tenant.
      await apiClient.post("/auth/register", {
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: normalizedEmail,
        password,
        phone_number: cleanPhone,
        address: address.trim() || null,
        city: city.trim() || null,
        state: region.trim() || null,
        pincode: pincode.trim() || null,
      });

      try {
        const result = await login(normalizedEmail, password);

        router.replace(
          result.mfaRequired ? "/(auth)/mfa" : "/(tabs)",
        );
      } catch {
        // Registration may have succeeded even if automatic login fails.
        router.replace("/(auth)/login");
      }
    } catch (e) {
      const responseData = (
        e as {
          response?: {
            data?: {
              detail?: unknown;
              message?: unknown;
              error?: unknown;
            };
          };
        }
      )?.response?.data;

      const detail = responseData?.detail;

      if (typeof detail === "string" && detail.trim()) {
        setError(detail.trim());
      } else if (Array.isArray(detail)) {
        const messages = detail.map((item: unknown) => {
          if (
            item &&
            typeof item === "object" &&
            "msg" in item
          ) {
            return String((item as { msg: unknown }).msg);
          }

          return typeof item === "string"
            ? item
            : JSON.stringify(item);
        });

        setError(
          messages.filter(Boolean).join("\n") ||
            "Registration request was rejected.",
        );
      } else if (detail && typeof detail === "object") {
        const fields = detail as {
          errors?: unknown;
          error?: unknown;
          message?: unknown;
        };

        if (Array.isArray(fields.errors) && fields.errors.length > 0) {
          setError(
            fields.errors
              .map((item: unknown) => {
                if (
                  item &&
                  typeof item === "object" &&
                  "msg" in item
                ) {
                  return String((item as { msg: unknown }).msg);
                }

                return typeof item === "string"
                  ? item
                  : JSON.stringify(item);
              })
              .filter(Boolean)
              .join("\n"),
          );
        } else if (
          typeof fields.message === "string" &&
          fields.message.trim()
        ) {
          setError(fields.message.trim());
        } else if (
          typeof fields.error === "string" &&
          fields.error.trim()
        ) {
          setError(fields.error.trim());
        } else {
          setError(
            getApiErrorMessage(
              e,
              "Could not create your customer account.",
            ),
          );
        }
      } else if (
        typeof responseData?.message === "string" &&
        responseData.message.trim()
      ) {
        setError(responseData.message.trim());
      } else if (
        typeof responseData?.error === "string" &&
        responseData.error.trim()
      ) {
        setError(responseData.error.trim());
      } else {
        setError(
          getApiErrorMessage(
            e,
            "Could not create your customer account.",
          ),
        );
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView
      style={{ flex: 1, backgroundColor: BG }}
      edges={["top", "bottom"]}
    >
      <StatusBar barStyle="light-content" backgroundColor={BG} />

      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
      >
        <ScrollView
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{
            flexGrow: 1,
            justifyContent: "center",
            paddingHorizontal: 24,
            paddingTop: 16,
            paddingBottom: 24,
          }}
          showsVerticalScrollIndicator={false}
        >
          <View
            style={{
              width: "100%",
              maxWidth: 440,
              alignSelf: "center",
            }}
          >
            <Pressable
              onPress={() => router.back()}
              hitSlop={8}
              style={{
                alignSelf: "flex-start",
                flexDirection: "row",
                alignItems: "center",
                gap: 7,
                marginBottom: 12,
              }}
            >
              <Ionicons name="arrow-back" size={19} color={MINT} />
              <Text
                style={{
                  color: MINT,
                  fontSize: 12,
                  fontWeight: "800",
                }}
              >
                Back to sign in
              </Text>
            </Pressable>

            <Text
              style={{
                color: "#F0F8F3",
                fontSize: 23,
                lineHeight: 29,
                fontWeight: "900",
                textAlign: "center",
              }}
            >
              Create customer account
            </Text>

            <Text
              style={{
                color: "#A6BFB1",
                fontSize: 13,
                marginTop: 5,
                marginBottom: 20,
                textAlign: "center",
                lineHeight: 19,
              }}
            >
              Register to book services and manage your requests.
            </Text>

            <View
              style={{
                backgroundColor: PANEL,
                borderWidth: 1,
                borderColor: BORDER,
                borderRadius: 24,
                padding: 18,
                gap: 13,
              }}
            >
              {error ? (
                <View
                  style={{
                    padding: 11,
                    borderRadius: 10,
                    backgroundColor: "#3D211F",
                    borderWidth: 1,
                    borderColor: "#85453E",
                  }}
                >
                  <Text
                    style={{
                      color: "#FFD8D4",
                      fontSize: 12,
                      lineHeight: 18,
                    }}
                  >
                    {error}
                  </Text>
                </View>
              ) : null}

              <View style={{ flexDirection: "row", gap: 10 }}>
                <View style={{ flex: 1 }}>
                  <RegistrationField
                    label="First name *"
                    value={firstName}
                    onChangeText={update(setFirstName)}
                    placeholder="First name"
                    icon="person-outline"
                    autoCapitalize="words"
                  />
                </View>

                <View style={{ flex: 1 }}>
                  <RegistrationField
                    label="Last name *"
                    value={lastName}
                    onChangeText={update(setLastName)}
                    placeholder="Last name"
                    icon="person-outline"
                    autoCapitalize="words"
                  />
                </View>
              </View>

              <RegistrationField
                label="Email address *"
                value={email}
                onChangeText={update(setEmail)}
                placeholder="you@example.com"
                icon="mail-outline"
                keyboardType="email-address"
                autoCapitalize="none"
              />

              <RegistrationField
                label="Phone number *"
                value={phone}
                onChangeText={(value) =>
                  update(setPhone)(
                    value.replace(/\D/g, "").slice(0, 10),
                  )
                }
                placeholder="10-digit mobile number"
                icon="call-outline"
                keyboardType="phone-pad"
                autoCapitalize="none"
                maxLength={10}
              />

              <View
                style={{
                  height: 1,
                  backgroundColor: BORDER,
                  marginVertical: 2,
                }}
              />

              <View style={{ gap: 4 }}>
                <Text
                  style={{
                    color: "#F0F8F3",
                    fontSize: 14,
                    fontWeight: "900",
                  }}
                >
                  Service location{" "}
                  <Text
                    style={{
                      color: "#8FAE9C",
                      fontSize: 11,
                      fontWeight: "500",
                    }}
                  >
                    (optional)
                  </Text>
                </Text>

                <Text
                  style={{
                    color: "#8FAE9C",
                    fontSize: 11,
                    lineHeight: 16,
                  }}
                >
                  Use your live location or search for an address or
                  landmark with Ola Maps.
                </Text>
              </View>

              <RegistrationField
                label="Search address or place"
                value={locationQuery}
                onChangeText={(value) => {
                  setLocationQuery(value);
                  setLocationError("");

                  if (value !== address) {
                    setAddress("");
                    setCity("");
                    setRegion("");
                    setPincode("");
                    setCoordinates(null);
                  }
                }}
                placeholder="Street, area, landmark..."
                icon="search-outline"
                autoCapitalize="words"
                returnKeyType="search"
              />

              {searchingLocations ? (
                <View
                  style={{
                    flexDirection: "row",
                    alignItems: "center",
                    gap: 8,
                    paddingVertical: 5,
                  }}
                >
                  <ActivityIndicator size="small" color={MINT} />
                  <Text style={{ color: LABEL, fontSize: 11 }}>
                    Searching locations...
                  </Text>
                </View>
              ) : null}

              {locationResults.length > 0 ? (
                <View
                  style={{
                    borderWidth: 1,
                    borderColor: BORDER,
                    borderRadius: 12,
                    overflow: "hidden",
                  }}
                >
                  {locationResults.map((place, index) => (
                    <Pressable
                      key={`${place.place_id || place.formatted_address}-${index}`}
                      onPress={() => void selectLocation(place)}
                      style={({ pressed }) => ({
                        flexDirection: "row",
                        alignItems: "center",
                        gap: 9,
                        paddingHorizontal: 11,
                        paddingVertical: 11,
                        backgroundColor: pressed ? "#104B35" : PANEL,
                        borderBottomWidth:
                          index === locationResults.length - 1
                            ? 0
                            : 1,
                        borderBottomColor: BORDER,
                      })}
                    >
                      <Ionicons
                        name="location-outline"
                        size={17}
                        color={MINT}
                      />
                      <Text
                        style={{
                          flex: 1,
                          color: "#E8F4EC",
                          fontSize: 11,
                          lineHeight: 16,
                        }}
                      >
                        {place.formatted_address ||
                          place.name ||
                          "Location result"}
                      </Text>
                    </Pressable>
                  ))}
                </View>
              ) : null}

              <Pressable
                onPress={() => void useCurrentLocation()}
                disabled={locating || submitting}
                style={({ pressed }) => ({
                  minHeight: 44,
                  borderRadius: 11,
                  backgroundColor: "#103F2E",
                  borderWidth: 1,
                  borderColor: "#267650",
                  flexDirection: "row",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 8,
                  opacity:
                    pressed || locating || submitting ? 0.75 : 1,
                })}
              >
                {locating ? (
                  <ActivityIndicator color={MINT} size="small" />
                ) : (
                  <Ionicons
                    name="navigate-outline"
                    size={17}
                    color={MINT}
                  />
                )}

                <Text
                  style={{
                    color: MINT,
                    fontSize: 12,
                    fontWeight: "800",
                  }}
                >
                  {locating
                    ? "Finding location..."
                    : "Use my live location"}
                </Text>
              </Pressable>

              {locationError ? (
                <Text
                  style={{
                    color: locationResults.length ? LABEL : "#FFD8D4",
                    fontSize: 11,
                    lineHeight: 16,
                  }}
                >
                  {locationError}
                </Text>
              ) : null}

              {address ? (
                <View
                  style={{
                    padding: 11,
                    borderRadius: 11,
                    backgroundColor: "#0B4B34",
                    borderWidth: 1,
                    borderColor: BORDER,
                    gap: 4,
                  }}
                >
                  <View
                    style={{
                      flexDirection: "row",
                      alignItems: "center",
                      gap: 7,
                    }}
                  >
                    <Ionicons
                      name="checkmark-circle"
                      size={16}
                      color={MINT}
                    />
                    <Text
                      style={{
                        color: MINT,
                        fontSize: 11,
                        fontWeight: "800",
                      }}
                    >
                      Selected address
                    </Text>
                  </View>

                  <Text
                    style={{
                      color: "#F0F8F3",
                      fontSize: 12,
                      lineHeight: 17,
                    }}
                  >
                    {address}
                  </Text>

                  {city || region || pincode ? (
                    <Text style={{ color: LABEL, fontSize: 11 }}>
                      {[city, region, pincode]
                        .filter(Boolean)
                        .join(", ")}
                    </Text>
                  ) : null}

                  {coordinates ? (
                    <Text
                      style={{
                        color: "#8FAE9C",
                        fontSize: 9,
                      }}
                    >
                      Location coordinates captured
                    </Text>
                  ) : null}
                </View>
              ) : null}

              <View style={{ gap: 6 }}>
                <Text
                  style={{
                    color: LABEL,
                    fontSize: 12,
                    fontWeight: "700",
                  }}
                >
                  Password *
                </Text>

                <View
                  style={{
                    minHeight: 46,
                    flexDirection: "row",
                    alignItems: "center",
                    gap: 10,
                    paddingHorizontal: 12,
                    borderRadius: 11,
                    backgroundColor: INPUT_BG,
                    borderWidth: 1,
                    borderColor: "#D7E4F6",
                  }}
                >
                  <Ionicons
                    name="lock-closed-outline"
                    size={17}
                    color="#35B983"
                  />

                  <TextInput
                    value={password}
                    onChangeText={update(setPassword)}
                    placeholder="Create a strong password"
                    placeholderTextColor="#8796A8"
                    secureTextEntry={!showPassword}
                    autoCapitalize="none"
                    autoCorrect={false}
                    style={{
                      flex: 1,
                      paddingVertical: 9,
                      color: INPUT_TEXT,
                      fontSize: 13,
                    }}
                    accessibilityLabel="Password"
                  />

                  <Pressable
                    onPress={() =>
                      setShowPassword((value) => !value)
                    }
                    hitSlop={8}
                    accessibilityLabel={
                      showPassword ? "Hide password" : "Show password"
                    }
                  >
                    <Ionicons
                      name={
                        showPassword
                          ? "eye-off-outline"
                          : "eye-outline"
                      }
                      size={18}
                      color="#8AA2B0"
                    />
                  </Pressable>
                </View>
              </View>

              <View style={{ gap: 6 }}>
                <Text
                  style={{
                    color: LABEL,
                    fontSize: 12,
                    fontWeight: "700",
                  }}
                >
                  Confirm password *
                </Text>

                <View
                  style={{
                    minHeight: 46,
                    flexDirection: "row",
                    alignItems: "center",
                    gap: 10,
                    paddingHorizontal: 12,
                    borderRadius: 11,
                    backgroundColor: INPUT_BG,
                    borderWidth: 1,
                    borderColor: "#D7E4F6",
                  }}
                >
                  <Ionicons
                    name="shield-checkmark-outline"
                    size={17}
                    color="#35B983"
                  />

                  <TextInput
                    value={confirmPassword}
                    onChangeText={update(setConfirmPassword)}
                    placeholder="Re-enter your password"
                    placeholderTextColor="#8796A8"
                    secureTextEntry={!showConfirmPassword}
                    autoCapitalize="none"
                    autoCorrect={false}
                    returnKeyType="done"
                    onSubmitEditing={() => void submit()}
                    style={{
                      flex: 1,
                      paddingVertical: 9,
                      color: INPUT_TEXT,
                      fontSize: 13,
                    }}
                    accessibilityLabel="Confirm password"
                  />

                  <Pressable
                    onPress={() =>
                      setShowConfirmPassword((value) => !value)
                    }
                    hitSlop={8}
                    accessibilityLabel={
                      showConfirmPassword
                        ? "Hide confirmation password"
                        : "Show confirmation password"
                    }
                  >
                    <Ionicons
                      name={
                        showConfirmPassword
                          ? "eye-off-outline"
                          : "eye-outline"
                      }
                      size={18}
                      color="#8AA2B0"
                    />
                  </Pressable>
                </View>
              </View>

              <Text
                style={{
                  color: "#8FAE9C",
                  fontSize: 10,
                  lineHeight: 15,
                }}
              >
                Use at least 8 characters with an uppercase letter,
                lowercase letter, number, and special character.
              </Text>

              <Pressable
                onPress={() => void submit()}
                disabled={submitting || locating}
                accessibilityRole="button"
                style={({ pressed }) => ({
                  minHeight: 48,
                  borderRadius: 12,
                  backgroundColor: submitting ? "#537D68" : PRIMARY,
                  alignItems: "center",
                  justifyContent: "center",
                  flexDirection: "row",
                  gap: 9,
                  opacity: pressed ? 0.86 : 1,
                  marginTop: 2,
                })}
              >
                {submitting ? (
                  <ActivityIndicator color="#FFFFFF" />
                ) : (
                  <>
                    <Text
                      style={{
                        color: "#FFFFFF",
                        fontSize: 13,
                        fontWeight: "900",
                      }}
                    >
                      Create customer account
                    </Text>
                    <Ionicons
                      name="arrow-forward"
                      size={17}
                      color="#FFFFFF"
                    />
                  </>
                )}
              </Pressable>

              <Text
                style={{
                  color: "#6F9480",
                  fontSize: 10,
                  lineHeight: 15,
                  textAlign: "center",
                }}
              >
                Customer registration only. Your account will be
                connected to FieldOps automatically.
              </Text>
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
