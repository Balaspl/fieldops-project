
import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  StyleProp,
  StyleSheet,
  Text,
  View,
  ViewStyle,
} from "react-native";
import { WebView, type WebViewMessageEvent } from "react-native-webview";

export interface OlaTechnician {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  online: boolean;
  status?: string | null;
  lastPing?: string | null;
  jobId?: string | number | null;
}

interface Props {
  technicians: OlaTechnician[];
  selectedTechnicianId: string | null;
  onSelectTechnician: (id: string) => void;
  style?: StyleProp<ViewStyle>;
}

const OLA_STYLE_URL =
  "https://api.olamaps.io/tiles/vector/v1/styles/default-light-standard/style.json";

function createMapHtml(apiKey: string): string {
  const safeKey = JSON.stringify(apiKey);

  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1"/>
<link rel="preconnect" href="https://api.olamaps.io" crossorigin />
<link rel="preconnect" href="https://www.unpkg.com" crossorigin />
<style>
html, body, #map {
  width: 100%;
  height: 100%;
  margin: 0;
  padding: 0;
  overflow: hidden;
  background: #edf3ee;
  font-family: Arial, sans-serif;
}

#map-error {
  display: none;
  position: absolute;
  inset: 0;
  padding: 20px;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: #9A3412;
  background: #FFF7ED;
  font-size: 14px;
}

.tech-marker {
  width: 38px;
  height: 38px;
  border: 3px solid white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-weight: bold;
  font-size: 13px;
  box-shadow: 0 3px 12px rgba(0,0,0,.28);
}

.tech-marker.selected {
  width: 46px;
  height: 46px;
  border-width: 4px;
  box-shadow: 0 0 0 5px rgba(22,163,74,.22),
              0 3px 12px rgba(0,0,0,.28);
}

#map-status {
  position: absolute;
  z-index: 5;
  left: 10px;
  top: 10px;
  padding: 7px 10px;
  border-radius: 9px;
  background: rgba(255,255,255,.95);
  color: #334155;
  font-size: 11px;
  box-shadow: 0 2px 8px rgba(0,0,0,.12);
}
</style>
<script src="https://www.unpkg.com/olamaps-web-sdk@1.4.0/dist/olamaps-web-sdk.umd.js"></script>
</head>
<body>
<div id="map"></div>
<div id="map-status">Loading technician locations...</div>
<div id="map-error"></div>

<script>
(function () {
  const apiKey = ${safeKey};
  const styleUrl = ${JSON.stringify(OLA_STYLE_URL)};

  let ola = null;
  let map = null;
  let mapReady = false;
  let pendingPayload = null;
  let markers = {};
  let lastFocusedId = null;
  let hasInitialView = false;

  function sendMessage(payload) {
    try {
      window.ReactNativeWebView.postMessage(JSON.stringify(payload));
    } catch (_) {}
  }

  function setStatus(message) {
    const element = document.getElementById("map-status");
    if (element) element.textContent = message;
  }

  function showError(message) {
    const element = document.getElementById("map-error");
    element.style.display = "flex";
    element.textContent = message;
    sendMessage({ type: "ERROR", message: message });
  }

  function createMarker(technician) {
    const element = document.createElement("div");
    element.className = "tech-marker";
    element.textContent = (technician.name || "T").trim().charAt(0).toUpperCase() || "T";

    element.style.background = technician.online ? "#168653" : "#D97706";

    element.addEventListener("click", function (event) {
      event.stopPropagation();
      sendMessage({
        type: "SELECT",
        id: technician.id
      });
    });

    return element;
  }

  function updateMarkers(payload) {
    if (!mapReady || !map || !payload) return;

    const technicians = Array.isArray(payload.technicians)
      ? payload.technicians
      : [];

    const currentIds = {};

    technicians.forEach(function (technician) {
      if (!technician || !technician.id) return;

      const lat = Number(technician.latitude);
      const lng = Number(technician.longitude);

      if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
      if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return;
      if (lat === 0 && lng === 0) return;

      const id = String(technician.id);
      currentIds[id] = true;

      const position = [lng, lat];
      const selected = id === payload.selectedTechnicianId;

      if (!markers[id]) {
        const element = createMarker(technician);

        markers[id] = {
          element: element,
          marker: ola.addMarker({
            element: element,
            anchor: "bottom"
          }).setLngLat(position).addTo(map)
        };
      } else {
        markers[id].marker.setLngLat(position);

        const element = markers[id].element;
        element.style.background = technician.online
          ? "#168653"
          : "#D97706";

        element.textContent =
          (technician.name || "T").trim().charAt(0).toUpperCase() || "T";

        element.classList.toggle("selected", selected);
      }

      markers[id].element.classList.toggle("selected", selected);
    });

    Object.keys(markers).forEach(function (id) {
      if (!currentIds[id]) {
        try {
          markers[id].marker.remove();
        } catch (_) {}
        delete markers[id];
      }
    });

    const visibleCount = Object.keys(currentIds).length;
    setStatus(visibleCount + " technicians mapped");

    if (!hasInitialView && visibleCount > 0) {
      const first = technicians.find(function (item) {
        return currentIds[String(item.id)];
      });

      if (first) {
        map.flyTo({
          center: [Number(first.longitude), Number(first.latitude)],
          zoom: 11,
          duration: 500
        });
        hasInitialView = true;
      }
    }

    const focusId = payload.selectedTechnicianId
      ? String(payload.selectedTechnicianId)
      : null;

    if (focusId && focusId !== lastFocusedId && markers[focusId]) {
      const position = markers[focusId].marker.getLngLat();

      map.flyTo({
        center: [position.lng, position.lat],
        zoom: 15,
        duration: 500
      });
    }

    lastFocusedId = focusId;
  }

  window.updateTechnicianMarkers = function (payload) {
    pendingPayload = payload;

    if (mapReady) {
      updateMarkers(payload);
    }
  };

  async function initializeMap() {
    try {
      if (!apiKey) {
        throw new Error("Ola Maps API key is missing.");
      }

      if (typeof window.OlaMaps !== "function") {
        throw new Error("Ola Maps SDK could not be loaded. Check internet connectivity.");
      }

      ola = new window.OlaMaps({ apiKey: apiKey });

      map = await ola.init({
        style: styleUrl,
        container: "map",
        center: [80.2707, 13.0827],
        zoom: 10
      });

      try {
        map.addControl(
          ola.addNavigationControls({ showCompass: true }),
          "top-right"
        );
      } catch (_) {}

      mapReady = true;

      setStatus("Live technician locations");

      sendMessage({ type: "READY" });

      if (pendingPayload) {
        updateMarkers(pendingPayload);
      }
    } catch (error) {
      showError(
        error instanceof Error
          ? error.message
          : "Unable to initialize Ola Maps."
      );
    }
  }

  initializeMap();
})();
</script>
</body>
</html>`;
}

export default function OlaTechnicianMap({
  technicians,
  selectedTechnicianId,
  onSelectTechnician,
  style,
}: Props) {
  const webViewRef = useRef<WebView>(null);
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState("");

  const apiKey =
    process.env.EXPO_PUBLIC_OLA_MAPS_API_KEY?.trim() ?? "";

  const mapHtml = useMemo(
    () => (apiKey ? createMapHtml(apiKey) : null),
    [apiKey]
  );

  const payload = useMemo(
    () => ({
      technicians,
      selectedTechnicianId,
    }),
    [technicians, selectedTechnicianId]
  );

  useEffect(() => {
    if (!mapReady) return;

    const json = JSON.stringify(payload);

    webViewRef.current?.injectJavaScript(
      `window.updateTechnicianMarkers && window.updateTechnicianMarkers(${json}); true;`
    );
  }, [mapReady, payload]);

  const handleMessage = (event: WebViewMessageEvent) => {
    try {
      const message = JSON.parse(event.nativeEvent.data);

      if (message.type === "READY") {
        setMapReady(true);
        setMapError("");
      }

      if (message.type === "SELECT" && message.id) {
        onSelectTechnician(String(message.id));
      }

      if (message.type === "ERROR") {
        setMapError(message.message || "Ola Maps failed to load.");
      }
    } catch {
      // Ignore invalid WebView messages.
    }
  };

  if (!apiKey) {
    return (
      <View style={[styles.container, style, styles.centered]}>
        <Text style={styles.errorText}>
          Ola Maps API key is missing from fo/.env.
        </Text>
      </View>
    );
  }

  return (
    <View style={[styles.container, style]}>
      <WebView
        ref={webViewRef}
        source={{ html: mapHtml ?? "" }}
        javaScriptEnabled
        domStorageEnabled
        onMessage={handleMessage}
        onError={() => setMapError("Ola Maps WebView failed to load.")}
        style={styles.webView}
      />

      {mapError ? (
        <View style={styles.errorOverlay}>
          <Text style={styles.errorText}>{mapError}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    overflow: "hidden",
    borderRadius: 15,
    backgroundColor: "#edf3ee",
  },
  webView: {
    flex: 1,
    backgroundColor: "transparent",
  },
  centered: {
    alignItems: "center",
    justifyContent: "center",
    padding: 20,
  },
  errorOverlay: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    padding: 10,
    backgroundColor: "#FFF7ED",
  },
  errorText: {
    color: "#9A3412",
    fontSize: 12,
    textAlign: "center",
  },
});
