import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { router, useLocalSearchParams } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { WebView, type WebViewMessageEvent } from "react-native-webview";
import * as Location from "expo-location";

import { customerApi } from "../src/api/customer";
import { env } from "../src/config/env";
import type { LocationSearchResult } from "../src/types/api";
import { setPickedServiceLocation } from "../src/utils/locationSelection";
import { AppButton, Screen } from "../src/components/ui";
import { colors } from "../src/theme";

type Point = { latitude: number; longitude: number };

const DEFAULT_CENTER: Point = { latitude: 13.0827, longitude: 80.2707 };
const OLA_STYLE_URL =
  "https://api.olamaps.io/tiles/vector/v1/styles/default-light-standard/style.json";

function validPoint(latitude: unknown, longitude: unknown): Point | null {
  const lat = Number(latitude);
  const lng = Number(longitude);
  if (
    latitude === null ||
    latitude === undefined ||
    longitude === null ||
    longitude === undefined ||
    !Number.isFinite(lat) ||
    !Number.isFinite(lng) ||
    lat < -90 ||
    lat > 90 ||
    lng < -180 ||
    lng > 180 ||
    (lat === 0 && lng === 0)
  ) {
    return null;
  }
  return { latitude: lat, longitude: lng };
}

function createPickerHtml(apiKey: string, center: Point): string {
  const safeKey = JSON.stringify(apiKey);
  const safeCenter = JSON.stringify([center.longitude, center.latitude]);

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
<style>
  html, body, #map { width:100%; height:100%; margin:0; padding:0; overflow:hidden; background:#edf3ee; }
  #map-error { display:none; position:absolute; inset:0; padding:22px; box-sizing:border-box; align-items:center; justify-content:center; text-align:center; color:#476258; background:#edf3ee; font:600 14px/1.5 -apple-system,BlinkMacSystemFont,Arial,sans-serif; }
</style>
<script src="https://www.unpkg.com/olamaps-web-sdk@1.4.0/dist/olamaps-web-sdk.umd.js"></script>
</head>
<body>
<div id="map"></div>
<div id="map-error">Ola Maps could not be loaded. Check your connection and map API key.</div>
<script>
(function () {
  const apiKey = ${safeKey};
  const styleUrl = ${JSON.stringify(OLA_STYLE_URL)};
  const initialCenter = ${safeCenter};
  let olaSdk = null;
  let map = null;
  let marker = null;

  function notify(payload) {
    try { window.ReactNativeWebView.postMessage(JSON.stringify(payload)); } catch (_) {}
  }

  function showError(message) {
    const panel = document.getElementById("map-error");
    panel.style.display = "flex";
    panel.textContent = message || "Ola Maps could not be loaded.";
    notify({ type: "error", message: panel.textContent });
  }

  function setSelection(latitude, longitude, moveCamera) {
    const lat = Number(latitude);
    const lng = Number(longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lng) ||
        lat < -90 || lat > 90 || lng < -180 || lng > 180 ||
        (lat === 0 && lng === 0) || !map || !olaSdk) return;

    if (marker) {
      try { marker.remove(); } catch (_) {}
      marker = null;
    }

    marker = olaSdk.addMarker({
      color: "#087653",
      anchor: "bottom"
    }).setLngLat([lng, lat]).addTo(map);

    if (moveCamera) {
      map.flyTo({ center: [lng, lat], zoom: 16, duration: 450 });
    }
  }

  window.setPickerLocation = function (latitude, longitude) {
    setSelection(latitude, longitude, true);
  };

  window.movePickerCamera = function (latitude, longitude) {
    const lat = Number(latitude);
    const lng = Number(longitude);
    if (!map || !Number.isFinite(lat) || !Number.isFinite(lng)) return;
    map.flyTo({ center: [lng, lat], zoom: 15, duration: 450 });
  };

  async function initialize() {
    try {
      if (!apiKey) {
        showError("Ola Maps API key is missing. Add EXPO_PUBLIC_OLA_MAPS_API_KEY to customer-mobile/.env.");
        return;
      }
      if (typeof window.OlaMaps !== "function") {
        showError("Ola Maps SDK could not be loaded. Check the device internet connection.");
        return;
      }

      olaSdk = new window.OlaMaps({ apiKey: apiKey });
      map = await olaSdk.init({
        style: styleUrl,
        container: "map",
        center: initialCenter,
        zoom: 14
      });

      try {
        map.addControl(olaSdk.addNavigationControls({ showCompass: true }), "top-right");
      } catch (_) {}

      map.on("click", function (event) {
        if (!event || !event.lngLat) return;
        const latitude = Number(event.lngLat.lat);
        const longitude = Number(event.lngLat.lng);
        setSelection(latitude, longitude, false);
        notify({ type: "selection", latitude: latitude, longitude: longitude });
      });

      notify({ type: "ready" });
    } catch (error) {
      showError(error && error.message ? error.message : "Ola Maps failed to initialize.");
    }
  }

  initialize();
})();
</script>
</body>
</html>`;
}

export default function LocationPickerScreen() {
  const params = useLocalSearchParams<{
    address?: string | string[];
    latitude?: string | string[];
    longitude?: string | string[];
  }>();

  const initialAddress = Array.isArray(params.address)
    ? params.address[0] || ""
    : params.address || "";
  const initialLatitude = Array.isArray(params.latitude)
    ? params.latitude[0]
    : params.latitude;
  const initialLongitude = Array.isArray(params.longitude)
    ? params.longitude[0]
    : params.longitude;

  const existingPoint = useMemo(
    () => validPoint(initialLatitude, initialLongitude),
    [initialLatitude, initialLongitude],
  );

  const [mapCenter, setMapCenter] = useState<Point>(existingPoint || DEFAULT_CENTER);
  const [selectedPoint, setSelectedPoint] = useState<Point | null>(existingPoint);
  const [searchText, setSearchText] = useState(initialAddress);
  const [searchResults, setSearchResults] = useState<LocationSearchResult[]>([]);
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState("");
  const [confirming, setConfirming] = useState(false);
  const webViewRef = useRef<WebView>(null);

  const html = useMemo(
    () => createPickerHtml(env.OLA_MAPS_API_KEY, existingPoint || DEFAULT_CENTER),
    [existingPoint],
  );

  // If the form has an address but no coordinates yet, use its search result
  // to open the map near that address instead of always opening central Chennai.
  useEffect(() => {
    if (existingPoint || !initialAddress.trim()) return;

    let active = true;
    customerApi.searchLocations(initialAddress.trim())
      .then((results) => {
        if (!active) return;
        const first = results.find((item) =>
          validPoint(item.latitude, item.longitude),
        );
        if (first) {
          setMapCenter({
            latitude: first.latitude,
            longitude: first.longitude,
          });
        }
      })
      .catch(() => {
        // The map remains usable from the default Chennai camera position.
      });

    return () => {
      active = false;
    };
  }, [existingPoint, initialAddress]);

  useEffect(() => {
    const query = searchText.trim();
    if (query.length < 3 || query === initialAddress.trim()) {
      setSearchResults([]);
      setSearchBusy(false);
      setSearchError("");
      return;
    }

    let active = true;
    const timer = setTimeout(async () => {
      setSearchBusy(true);
      setSearchError("");
      try {
        const results = await customerApi.searchLocations(query);
        if (active) setSearchResults(results.slice(0, 5));
      } catch {
        if (active) {
          setSearchResults([]);
          setSearchError("Address search is unavailable. You can still select a point on the map.");
        }
      } finally {
        if (active) setSearchBusy(false);
      }
    }, 350);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [searchText, initialAddress]);

  useEffect(() => {
    if (!mapReady || !webViewRef.current) return;

    if (selectedPoint) {
      webViewRef.current.injectJavaScript(
        `window.setPickerLocation && window.setPickerLocation(${selectedPoint.latitude}, ${selectedPoint.longitude}); true;`,
      );
    } else {
      webViewRef.current.injectJavaScript(
        `window.movePickerCamera && window.movePickerCamera(${mapCenter.latitude}, ${mapCenter.longitude}); true;`,
      );
    }
  }, [mapReady, mapCenter, selectedPoint]);

  const onMapMessage = useCallback((event: WebViewMessageEvent) => {
    try {
      const message = JSON.parse(event.nativeEvent.data) as {
        type?: string;
        message?: string;
        latitude?: number;
        longitude?: number;
      };

      if (message.type === "ready") {
        setMapReady(true);
        setMapError("");
      } else if (message.type === "selection") {
        const point = validPoint(message.latitude, message.longitude);
        if (point) setSelectedPoint(point);
      } else if (message.type === "error") {
        setMapError(message.message || "Ola Maps failed to load.");
      }
    } catch {
      // Ignore non-JSON messages from the map page.
    }
  }, []);

  const chooseSearchResult = (result: LocationSearchResult) => {
    const point = validPoint(result.latitude, result.longitude);
    if (!point) return;
    setSelectedPoint(point);
    setMapCenter(point);
    setSearchText(result.formatted_address);
    setSearchResults([]);
    setSearchError("");
  };

  const useCurrentPosition = async () => {
    try {
      const permission = await Location.requestForegroundPermissionsAsync();
      if (permission.status !== "granted") {
        setSearchError("Allow location access to move the map to your current position.");
        return;
      }
      const position = await Location.getCurrentPositionAsync({
        accuracy: Location.Accuracy.High,
      });
      const point = validPoint(
        position.coords.latitude,
        position.coords.longitude,
      );
      if (!point) {
        setSearchError("Your device did not return a valid current location.");
        return;
      }
      setSelectedPoint(point);
      setMapCenter(point);
    } catch {
      setSearchError("Unable to get your current location. Select a point directly on the map.");
    }
  };

  const confirmSelection = async () => {
    if (!selectedPoint) return;

    setConfirming(true);
    setSearchError("");

    try {
      let address = "";
      try {
        const result = await customerApi.reverseLocation(
          selectedPoint.latitude,
          selectedPoint.longitude,
        );
        address =
          result.address ||
          result.display_name ||
          result.formatted_address ||
          result.name ||
          "";
      } catch {
        // Fall back to Expo reverse geocoding below.
      }

      if (!address.trim()) {
        try {
          const results = await Location.reverseGeocodeAsync({
            latitude: selectedPoint.latitude,
            longitude: selectedPoint.longitude,
          });
          const result = results[0];
          if (result) {
            const street = [result.streetNumber, result.street]
              .filter(Boolean)
              .join(" ");
            address = [
              street,
              result.district,
              result.city,
              result.region,
              result.postalCode,
              result.country,
            ]
              .filter(Boolean)
              .filter((part, index, all) => all.indexOf(part) === index)
              .join(", ");
          }
        } catch {
          // A clear message is shown if neither geocoder returns an address.
        }
      }

      if (!address.trim()) {
        setSearchError(
          "We selected the map point, but could not resolve its address. Try another point or search for an address.",
        );
        return;
      }

      setPickedServiceLocation({
        address: address.trim(),
        latitude: selectedPoint.latitude,
        longitude: selectedPoint.longitude,
      });
      router.back();
    } finally {
      setConfirming(false);
    }
  };

  return (
    <Screen
      scroll={false}
      contentStyle={{
        paddingHorizontal: 0,
        paddingTop: 0,
        paddingBottom: 0,
        gap: 0,
      }}
    >
      <View style={styles.container}>
        <View style={styles.header}>
          <Pressable
            onPress={() => router.back()}
            style={styles.headerButton}
            accessibilityRole="button"
            accessibilityLabel="Go back to service address"
          >
            <Ionicons name="arrow-back" size={22} color={colors.brand} />
          </Pressable>
          <View style={styles.headerText}>
            <Text style={styles.title}>Change location</Text>
            <Text style={styles.subtitle}>Choose the service address on Ola Maps</Text>
          </View>
        </View>

        <View style={styles.searchWrap}>
          <Ionicons name="search-outline" size={19} color={colors.muted} />
          <TextInput
            value={searchText}
            onChangeText={setSearchText}
            placeholder="Search street, area or landmark"
            placeholderTextColor={colors.muted}
            style={styles.searchInput}
            returnKeyType="search"
          />
          {searchBusy ? <ActivityIndicator color={colors.brand} size="small" /> : null}
          {searchText ? (
            <Pressable onPress={() => setSearchText("")} accessibilityLabel="Clear address search">
              <Ionicons name="close-circle" size={19} color={colors.muted} />
            </Pressable>
          ) : null}
        </View>

        {searchResults.length > 0 ? (
          <View style={styles.suggestions}>
            {searchResults.map((result, index) => (
              <Pressable
                key={result.place_id || `${result.latitude}-${result.longitude}-${index}`}
                onPress={() => chooseSearchResult(result)}
                style={styles.suggestion}
              >
                <Ionicons name="location-outline" size={18} color={colors.brandMid} />
                <Text style={styles.suggestionText} numberOfLines={2}>
                  {result.formatted_address}
                </Text>
              </Pressable>
            ))}
          </View>
        ) : null}

        {searchError ? (
          <Text style={styles.inlineError}>{searchError}</Text>
        ) : null}

        <View style={styles.mapWrap}>
          {env.OLA_MAPS_API_KEY ? (
            <WebView
              ref={webViewRef}
              source={{ html }}
              originWhitelist={["*"]}
              javaScriptEnabled
              domStorageEnabled
              onMessage={onMapMessage}
              onError={(event) =>
                setMapError(event.nativeEvent.description || "Ola Maps could not load.")
              }
              style={styles.map}
              accessibilityLabel="Ola Maps location picker"
            />
          ) : (
            <View style={styles.mapUnavailable}>
              <Ionicons name="map-outline" size={32} color={colors.brand} />
              <Text style={styles.mapUnavailableTitle}>Ola Maps API key missing</Text>
              <Text style={styles.mapUnavailableText}>
                Add EXPO_PUBLIC_OLA_MAPS_API_KEY to customer-mobile/.env and restart Expo.
              </Text>
            </View>
          )}

          {mapError ? (
            <View style={styles.mapErrorBanner}>
              <Text style={styles.mapErrorText}>{mapError}</Text>
            </View>
          ) : null}
        </View>

        <View style={styles.footer}>
          <Pressable
            onPress={() => void useCurrentPosition()}
            style={styles.currentLocationButton}
            accessibilityRole="button"
          >
            <Ionicons name="locate-outline" size={18} color={colors.brand} />
            <Text style={styles.currentLocationText}>Use my current location</Text>
          </Pressable>

          <Text style={styles.selectionHint}>
            {selectedPoint
              ? "Location selected. Confirm to update your service address."
              : "Tap the map or search for an address to select your service location."}
          </Text>

          <AppButton
            title={confirming ? "Confirming location…" : "Use this location"}
            icon="checkmark-circle-outline"
            onPress={() => void confirmSelection()}
            loading={confirming}
            disabled={!selectedPoint || !mapReady || confirming}
          />
        </View>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    minHeight: 0,
    backgroundColor: "#F6FAF7",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: 11,
    paddingHorizontal: 16,
    paddingTop: 10,
    paddingBottom: 12,
  },
  headerButton: {
    width: 42,
    height: 42,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: colors.border,
  },
  headerText: {
    flex: 1,
    gap: 2,
  },
  title: {
    color: colors.text,
    fontSize: 20,
    fontWeight: "900",
  },
  subtitle: {
    color: colors.muted,
    fontSize: 11,
  },
  searchWrap: {
    minHeight: 48,
    marginHorizontal: 16,
    marginBottom: 8,
    paddingHorizontal: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
    borderRadius: 13,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: colors.border,
  },
  searchInput: {
    flex: 1,
    minWidth: 0,
    paddingVertical: 10,
    color: colors.text,
    fontSize: 13,
  },
  suggestions: {
    marginHorizontal: 16,
    marginBottom: 8,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 13,
    overflow: "hidden",
  },
  suggestion: {
    minHeight: 44,
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
    paddingHorizontal: 11,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
  },
  suggestionText: {
    flex: 1,
    color: colors.text,
    fontSize: 12,
    lineHeight: 17,
  },
  inlineError: {
    marginHorizontal: 16,
    marginBottom: 8,
    color: colors.danger,
    fontSize: 11,
    lineHeight: 16,
  },
  mapWrap: {
    flex: 1,
    minHeight: 220,
    marginHorizontal: 12,
    overflow: "hidden",
    borderRadius: 18,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: "#EAF1EC",
  },
  map: {
    flex: 1,
    backgroundColor: "#EAF1EC",
  },
  mapUnavailable: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    gap: 8,
  },
  mapUnavailableTitle: {
    color: colors.text,
    fontSize: 15,
    fontWeight: "900",
  },
  mapUnavailableText: {
    color: colors.muted,
    fontSize: 12,
    lineHeight: 18,
    textAlign: "center",
  },
  mapErrorBanner: {
    position: "absolute",
    left: 10,
    right: 10,
    top: 10,
    padding: 10,
    borderRadius: 10,
    backgroundColor: "#FFF7ED",
  },
  mapErrorText: {
    color: "#9A3412",
    fontSize: 11,
    lineHeight: 16,
  },
  footer: {
    paddingHorizontal: 16,
    paddingTop: 10,
    paddingBottom: 12,
    gap: 9,
    backgroundColor: "#F6FAF7",
  },
  currentLocationButton: {
    minHeight: 42,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "#CFE7DA",
    backgroundColor: "#EAF6EF",
  },
  currentLocationText: {
    color: colors.brand,
    fontSize: 12,
    fontWeight: "800",
  },
  selectionHint: {
    color: colors.muted,
    fontSize: 11,
    lineHeight: 16,
    textAlign: "center",
  },
});
