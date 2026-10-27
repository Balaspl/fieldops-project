
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Location from "expo-location";
import { WebView, type WebViewMessageEvent } from "react-native-webview";

import { apiClient } from "../../../../src/api/client";
import {
  getTechnicianJob,
  type TechnicianJob
} from "../../../../src/api/technician";

type Point = {
  lat: number;
  lng: number;
};

type OlaRouteResponse = {
  distance_meters: number;
  duration_seconds: number;
  duration_in_traffic_seconds?: number | null;
  route_points: [number, number][];
  provider?: string;
};

type MapPayload = {
  origin: Point | null;
  routePoints: [number, number][];
};

function isValidPoint(point: Point | null): point is Point {
  return Boolean(
    point &&
      Number.isFinite(point.lat) &&
      Number.isFinite(point.lng) &&
      point.lat >= -90 &&
      point.lat <= 90 &&
      point.lng >= -180 &&
      point.lng <= 180 &&
      !(point.lat === 0 && point.lng === 0)
  );
}

function distanceBetween(a: Point, b: Point): number {
  const latitudeMeters = (a.lat - b.lat) * 111_000;
  const longitudeMeters =
    (a.lng - b.lng) *
    111_000 *
    Math.cos((a.lat * Math.PI) / 180);

  return Math.hypot(latitudeMeters, longitudeMeters);
}

function formatDistance(meters: number | null): string {
  if (meters === null || !Number.isFinite(meters)) {
    return "Calculating...";
  }

  return meters >= 1_000
    ? `${(meters / 1_000).toFixed(1)} km`
    : `${Math.round(meters)} m`;
}

function formatEta(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) {
    return "Calculating...";
  }

  return `${Math.max(1, Math.round(seconds / 60))} min`;
}


function createMapHtml(apiKey: string, destination: Point): string {
  const keyJson = JSON.stringify(apiKey);
  const destinationJson = JSON.stringify(destination);

  return `<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
  <style>
    html, body, #map {
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      background: #eef2f4;
      font-family: Arial, sans-serif;
    }

    #map {
      position: absolute;
      inset: 0;
    }

    #map-tools {
      position: absolute;
      z-index: 10;
      right: 12px;
      top: 58px;
      display: flex;
      flex-direction: column;
      gap: 9px;
    }

    .map-button {
      width: 44px;
      height: 44px;
      border: none;
      border-radius: 14px;
      background: white;
      color: #16382A;
      box-shadow: 0 2px 10px rgba(15, 23, 42, .2);
      font-size: 22px;
      font-weight: bold;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .map-button:active {
      background: #eaf4ee;
    }

    #message {
      position: absolute;
      z-index: 5;
      top: 12px;
      left: 12px;
      right: 68px;
      padding: 10px 12px;
      border-radius: 10px;
      background: rgba(255, 255, 255, .96);
      color: #334155;
      font-size: 13px;
      box-shadow: 0 2px 12px rgba(15, 23, 42, .12);
    }
  </style>
  <script src="https://www.unpkg.com/olamaps-web-sdk@1.4.0/dist/olamaps-web-sdk.umd.js"></script>
</head>
<body>
  <div id="map"></div>

  <div id="message">Loading Ola Maps...</div>

  <div id="map-tools">
    <button class="map-button" id="my-location" aria-label="My location" title="My location">➤</button>
    <button class="map-button" id="job-location" aria-label="Service destination" title="Service destination">⌖</button>
    <button class="map-button" id="route-overview" aria-label="Show complete route" title="Show complete route">↔</button>
  </div>

  <script>
    (function () {
      const apiKey = ${keyJson};
      const destination = ${destinationJson};

      let ola = null;
      let map = null;
      let technicianMarker = null;
      let customerMarker = null;
      let mapReady = false;
      let hasFittedBounds = false;
      let pendingPayload = null;
      let latestOrigin = null;
      let latestRoutePoints = [];

      const routeSourceId = "fieldops-mobile-route";
      const routeLayerId = "fieldops-mobile-route-line";

      function sendMessage(payload) {
        try {
          window.ReactNativeWebView.postMessage(JSON.stringify(payload));
        } catch (_) {}
      }

      function setMessage(message) {
        const element = document.getElementById("message");
        if (element) element.textContent = message;
      }

      function createMarker(label) {
        const element = document.createElement("button");

        element.type = "button";
        element.setAttribute(
          "aria-label",
          label === "YOU" ? "Zoom to technician location" : "Zoom to service destination"
        );
        element.style.width = "44px";
        element.style.height = "44px";
        element.style.padding = "0";
        element.style.display = "flex";
        element.style.alignItems = "center";
        element.style.justifyContent = "center";
        element.style.borderRadius = "50%";
        element.style.border = "3px solid white";
        element.style.boxSizing = "border-box";
        element.style.boxShadow = "0 3px 12px rgba(15,23,42,.3)";
        element.style.font = "bold 13px Arial";
        element.style.color = "#ffffff";
        element.style.background = label === "YOU" ? "#16834a" : "#172033";
        element.textContent = label;

        element.addEventListener("click", function (event) {
          event.stopPropagation();

          if (label === "YOU") {
            focusTechnician();
          } else {
            focusDestination();
          }
        });

        return element;
      }

      function focusTechnician() {
        if (!map || !latestOrigin) {
          setMessage("Waiting for your current GPS location...");
          return;
        }

        map.flyTo({
          center: [latestOrigin.lng, latestOrigin.lat],
          zoom: 16,
          duration: 800
        });

        setMessage("Your current location");
      }

      function focusDestination() {
        if (!map) return;

        map.flyTo({
          center: [destination.lng, destination.lat],
          zoom: 16,
          duration: 800
        });

        setMessage("Service destination");
      }

      function showRouteOverview() {
        if (!map || !latestOrigin) {
          setMessage("Waiting for your current GPS location...");
          return;
        }

        try {
          map.fitBounds([
            [
              Math.min(latestOrigin.lng, destination.lng),
              Math.min(latestOrigin.lat, destination.lat)
            ],
            [
              Math.max(latestOrigin.lng, destination.lng),
              Math.max(latestOrigin.lat, destination.lat)
            ]
          ], {
            padding: 65,
            maxZoom: 15,
            duration: 800
          });

          setMessage("Route overview");
        } catch (error) {
          console.warn("Unable to show route overview", error);
        }
      }

      function updateRoute(points) {
        if (!map || !Array.isArray(points) || points.length < 2) {
          return;
        }

        latestRoutePoints = points;

        const draw = function () {
          try {
            if (!map || !map.isStyleLoaded()) {
              map.once("idle", draw);
              return;
            }

            const geojson = {
              type: "Feature",
              properties: {},
              geometry: {
                type: "LineString",
                coordinates: points
              }
            };

            const source = map.getSource(routeSourceId);

            if (source) {
              source.setData(geojson);
            } else {
              map.addSource(routeSourceId, {
                type: "geojson",
                data: geojson
              });
            }

            if (!map.getLayer(routeLayerId)) {
              map.addLayer({
                id: routeLayerId,
                type: "line",
                source: routeSourceId,
                layout: {
                  "line-join": "round",
                  "line-cap": "round"
                },
                paint: {
                  "line-color": "#2563eb",
                  "line-width": 6,
                  "line-opacity": 0.95
                }
              });
            }
          } catch (error) {
            console.error("Unable to draw Ola route", error);
          }
        };

        draw();
      }

      window.updateFieldOpsMap = function (payload) {
        pendingPayload = payload;

        if (!mapReady || !map || !payload) return;

        const origin = payload.origin;

        if (origin) {
          latestOrigin = origin;

          const position = [origin.lng, origin.lat];

          if (!technicianMarker) {
            technicianMarker = ola.addMarker({
              element: createMarker("YOU"),
              anchor: "bottom"
            }).setLngLat(position).addTo(map);
          } else {
            technicianMarker.setLngLat(position);
          }

          if (!hasFittedBounds) {
            showRouteOverview();
            hasFittedBounds = true;
          }
        }

        updateRoute(payload.routePoints);

        setMessage(
          origin
            ? "Technician route to service location"
            : "Waiting for current location..."
        );
      };

      document.getElementById("my-location").addEventListener("click", focusTechnician);
      document.getElementById("job-location").addEventListener("click", focusDestination);
      document.getElementById("route-overview").addEventListener("click", showRouteOverview);

      async function initializeMap() {
        try {
          if (!window.OlaMaps) {
            throw new Error("Ola Maps SDK could not be loaded.");
          }

          ola = new window.OlaMaps({ apiKey: apiKey });

          map = await ola.init({
            style: "https://api.olamaps.io/tiles/vector/v1/styles/default-light-standard/style.json",
            container: "map",
            center: [destination.lng, destination.lat],
            zoom: 14
          });

          try {
            map.addControl(
              ola.addNavigationControls({ showCompass: true }),
              "top-right"
            );
          } catch (_) {}

          customerMarker = ola.addMarker({
            element: createMarker("JOB"),
            anchor: "bottom"
          }).setLngLat([
            destination.lng,
            destination.lat
          ]).addTo(map);

          mapReady = true;
          setMessage("Waiting for current location...");

          sendMessage({ type: "READY" });

          if (pendingPayload) {
            window.updateFieldOpsMap(pendingPayload);
          }
        } catch (error) {
          const message =
            error instanceof Error
              ? error.message
              : "Unable to initialize Ola Maps.";

          setMessage(message);
          sendMessage({ type: "ERROR", message: message });
        }
      }

      void initializeMap();
    })();
  </script>
</body>
</html>`;
}


export default function JobLiveMapScreen() {
  const router = useRouter();
  const { jobId } = useLocalSearchParams<{ jobId: string }>();

  const webViewRef = useRef<WebView>(null);
  const mountedRef = useRef(false);

  const lastRouteRequestRef = useRef<{
    point: Point;
    at: number;
  } | null>(null);

  const routeRequestIdRef = useRef(0);

  const [job, setJob] = useState<TechnicianJob | null>(null);
  const [loadingJob, setLoadingJob] = useState(true);
  const [jobError, setJobError] = useState("");
  const [location, setLocation] =
    useState<Location.LocationObject | null>(null);
  const [gpsError, setGpsError] = useState("");
  const [route, setRoute] = useState<OlaRouteResponse | null>(null);
  const [routeError, setRouteError] = useState("");
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState("");

  const apiKey = process.env.EXPO_PUBLIC_OLA_MAPS_API_KEY?.trim() ?? "";

  const destination = useMemo<Point | null>(() => {
    if (!job) return null;

    const lat = Number(job.site_latitude);
    const lng = Number(job.site_longitude);

    const point = { lat, lng };
    return isValidPoint(point) ? point : null;
  }, [job]);

  const origin = useMemo<Point | null>(() => {
    if (!location) return null;

    const point = {
      lat: location.coords.latitude,
      lng: location.coords.longitude
    };

    return isValidPoint(point) ? point : null;
  }, [location]);

  const mapHtml = useMemo(() => {
    if (!apiKey || !destination) return null;

    return createMapHtml(apiKey, destination);
  }, [apiKey, destination]);

  const mapPayload = useMemo<MapPayload>(() => ({
    origin,
    routePoints: route?.route_points ?? []
  }), [origin, route]);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    let subscription: Location.LocationSubscription | null = null;

    async function startLocationUpdates() {
      try {
        let permission = await Location.getForegroundPermissionsAsync();

        if (!permission.granted) {
          permission = await Location.requestForegroundPermissionsAsync();
        }

        if (!active) return;

        if (!permission.granted) {
          setGpsError(
            "Location permission is required to show your route. Enable it in your phone settings."
          );
          return;
        }

        const providerStatus = await Location.getProviderStatusAsync();

        if (!active) return;

        if (!providerStatus.locationServicesEnabled) {
          setGpsError(
            "Device location is turned off. Enable Location in Android settings."
          );
          return;
        }

        setGpsError("");

        const lastKnown = await Location.getLastKnownPositionAsync();

        if (active && lastKnown) {
          setLocation(lastKnown);
        }

        const watch = await Location.watchPositionAsync(
          {
            accuracy: Location.Accuracy.High,
            timeInterval: 10_000,
            distanceInterval: 25,
            mayShowUserSettingsDialog: true
          },
          (position) => {
            if (active) {
              setLocation(position);
              setGpsError("");
            }
          },
          (reason) => {
            if (active) {
              console.warn(
                "[LIVE MAP] Location watcher failed:",
                reason
              );

              setGpsError(
                reason ||
                  "Unable to receive live GPS updates. Check device location settings."
              );
            }
          }
        );

        if (!active) {
          watch.remove();
          return;
        }

        subscription = watch;

        try {
          const currentPosition =
            await Location.getCurrentPositionAsync({
              accuracy: Location.Accuracy.High,
              mayShowUserSettingsDialog: true
            });

          if (active) {
            setLocation(currentPosition);
            setGpsError("");

            console.info("[LIVE MAP] Current GPS position received", {
              latitude: currentPosition.coords.latitude,
              longitude: currentPosition.coords.longitude,
              accuracy: currentPosition.coords.accuracy
            });
          }
        } catch (error) {
          if (active) {
            console.warn(
              "[LIVE MAP] Initial GPS position request failed:",
              error
            );

            if (!lastKnown) {
              setGpsError(
                "Unable to get a fresh GPS fix. Check that Android Location is enabled."
              );
            }
          }
        }
      } catch (error) {
        if (active) {
          console.error(
            "[LIVE MAP] Unable to start location updates:",
            error
          );

          setGpsError(
            "Unable to access your current location. Check GPS and location permission."
          );
        }
      }
    }

    void startLocationUpdates();

    return () => {
      active = false;
      subscription?.remove();
    };
  }, [jobId]);

  useEffect(() => {
    let active = true;

    async function loadJob() {
      if (!jobId) {
        setJobError("The job ID is missing.");
        setLoadingJob(false);
        return;
      }

      try {
        setLoadingJob(true);
        setJobError("");

        const result = await getTechnicianJob(jobId);

        if (active) {
          setJob(result);
        }
      } catch {
        if (active) {
          setJobError(
            "Unable to load the service location. Return to the job and try again."
          );
        }
      } finally {
        if (active) {
          setLoadingJob(false);
        }
      }
    }

    void loadJob();

    return () => {
      active = false;
    };
  }, [jobId]);

  useEffect(() => {
    if (!origin || !destination) {
      setRoute(null);
      return;
    }

    const routeOrigin: Point = origin;
    const routeDestination: Point = destination;

    const now = Date.now();
    const previous = lastRouteRequestRef.current;

    if (previous) {
      const movedMeters = distanceBetween(
        routeOrigin,
        previous.point
      );
      const elapsed = now - previous.at;

      if (elapsed < 15_000 && movedMeters < 50) {
        return;
      }
    }

    lastRouteRequestRef.current = {
      point: routeOrigin,
      at: now
    };

    const requestId = ++routeRequestIdRef.current;

    async function calculateRoute(
      requestOrigin: Point,
      requestDestination: Point
    ) {
      try {
        setRouteError("");

        const response = await apiClient.get<OlaRouteResponse>(
          "/api/v1/gps/route",
          {
            params: {
              origin_lat: requestOrigin.lat,
              origin_lng: requestOrigin.lng,
              dest_lat: requestDestination.lat,
              dest_lng: requestDestination.lng
            }
          }
        );

        const result = response.data;

        const validRoute =
          Number.isFinite(result.distance_meters) &&
          result.distance_meters > 0 &&
          Number.isFinite(result.duration_seconds) &&
          result.duration_seconds >= 0 &&
          Array.isArray(result.route_points) &&
          result.route_points.length >= 2 &&
          result.route_points.every(
            (point) =>
              Array.isArray(point) &&
              point.length >= 2 &&
              Number.isFinite(point[0]) &&
              Number.isFinite(point[1]) &&
              point[0] >= -180 &&
              point[0] <= 180 &&
              point[1] >= -90 &&
              point[1] <= 90
          );

        if (!validRoute) {
          throw new Error("The route response was invalid.");
        }

        if (
          mountedRef.current &&
          requestId === routeRequestIdRef.current
        ) {
          setRoute(result);
          setRouteError("");
        }
      } catch (error: unknown) {
        const response =
          typeof error === "object" &&
          error !== null &&
          "response" in error
            ? (
                error as {
                  response?: {
                    status?: number;
                    data?: unknown;
                  };
                }
              ).response
            : undefined;

        console.warn("[LIVE MAP] Route request failed", {
          status: response?.status,
          data: response?.data,
          message:
            error instanceof Error
              ? error.message
              : String(error)
        });

        if (
          mountedRef.current &&
          requestId === routeRequestIdRef.current
        ) {
          setRoute(null);
          setRouteError(
            "Unable to calculate the road route. Check your connection."
          );
        }
      }
    }

    void calculateRoute(routeOrigin, routeDestination);
  }, [origin, destination]);

  useEffect(() => {
    if (!mapReady) return;

    const payload = JSON.stringify(mapPayload);

    webViewRef.current?.injectJavaScript(
      `window.updateFieldOpsMap && window.updateFieldOpsMap(${payload}); true;`
    );
  }, [mapReady, mapPayload]);

  function handleMapMessage(event: WebViewMessageEvent) {
    try {
      const message = JSON.parse(event.nativeEvent.data) as {
        type?: string;
        message?: string;
      };

      if (message.type === "READY") {
        setMapReady(true);
        setMapError("");
      } else if (message.type === "ERROR") {
        setMapError(message.message ?? "Unable to load Ola Maps.");
      }
    } catch {
      // Ignore messages that are not JSON.
    }
  }

  const distance = route
    ? formatDistance(route.distance_meters)
    : routeError
      ? "Unavailable"
      : "Calculating...";

  const duration = route
    ? formatEta(
        route.duration_in_traffic_seconds ??
          route.duration_seconds
      )
    : routeError
      ? "Unavailable"
      : "Calculating...";

  const address =
    job?.site_address?.trim() ||
    job?.address?.trim() ||
    job?.location?.trim() ||
    "Service location";

  const statusMessage =
    jobError ||
    mapError ||
    gpsError ||
    routeError ||
    (!origin ? "Waiting for your current location..." : "");

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Return to job details"
          onPress={() => router.back()}
          style={styles.backButton}
        >
          <Ionicons name="arrow-back" size={23} color="#16382A" />
        </Pressable>

        <View style={styles.headerText}>
          <Text style={styles.headerTitle}>Live Route</Text>
          <Text style={styles.headerSubtitle}>
            Job #{job?.job_number ?? jobId}
          </Text>
        </View>

        <View style={styles.mapBadge}>
          <Ionicons name="navigate" size={17} color="#087653" />
        </View>
      </View>

      <View style={styles.addressCard}>
        <Ionicons name="location" size={21} color="#087653" />

        <View style={styles.addressTextContainer}>
          <Text style={styles.addressLabel}>SERVICE DESTINATION</Text>
          <Text style={styles.addressText}>{address}</Text>
        </View>
      </View>

      <View style={styles.mapContainer}>
        {loadingJob ? (
          <View style={styles.centered}>
            <ActivityIndicator size="large" color="#087653" />
            <Text style={styles.centeredText}>Loading job location...</Text>
          </View>
        ) : !job ? (
          <View style={styles.centered}>
            <Ionicons name="alert-circle-outline" size={34} color="#B91C1C" />
            <Text style={styles.centeredText}>
              {jobError || "Job details are unavailable."}
            </Text>
          </View>
        ) : !destination ? (
          <View style={styles.centered}>
            <Ionicons name="location-outline" size={34} color="#B45309" />
            <Text style={styles.centeredText}>
              This job does not have valid service coordinates. The route cannot be calculated yet.
            </Text>
          </View>
        ) : !apiKey ? (
          <View style={styles.centered}>
            <Text style={styles.centeredText}>
              The Ola Maps key is missing from mobile/.env. Check the Expo environment configuration.
            </Text>
          </View>
        ) : (
          <WebView
            ref={webViewRef}
            source={{ html: mapHtml ?? "" }}
            javaScriptEnabled
            domStorageEnabled
            onMessage={handleMapMessage}
            onError={() => setMapError("The Ola Maps view failed to load.")}
            style={styles.webView}
          />
        )}
      </View>

      <View style={styles.routeCard}>
        <View style={styles.routeMetric}>
          <Text style={styles.metricLabel}>ROAD DISTANCE</Text>
          <Text style={styles.metricValue}>{distance}</Text>
        </View>

        <View style={styles.metricDivider} />

        <View style={styles.routeMetric}>
          <Text style={styles.metricLabel}>ESTIMATED TIME</Text>
          <Text style={styles.metricValue}>{duration}</Text>
        </View>

        <View style={styles.provider}>
          <Ionicons name="map-outline" size={16} color="#087653" />
          <Text style={styles.providerText}>Ola Maps</Text>
        </View>
      </View>

      {statusMessage ? (
        <View style={styles.statusMessage}>
          <Text style={styles.statusMessageText}>{statusMessage}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#F4F7F5"
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 12,
    backgroundColor: "#FFFFFF"
  },
  backButton: {
    width: 42,
    height: 42,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 14,
    backgroundColor: "#EAF4EE"
  },
  headerText: {
    flex: 1,
    marginLeft: 12
  },
  headerTitle: {
    color: "#16382A",
    fontSize: 20,
    fontWeight: "800"
  },
  headerSubtitle: {
    color: "#64748B",
    marginTop: 2,
    fontSize: 12
  },
  mapBadge: {
    width: 40,
    height: 40,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 14,
    backgroundColor: "#EAF4EE"
  },
  addressCard: {
    flexDirection: "row",
    alignItems: "center",
    marginHorizontal: 12,
    marginTop: 10,
    marginBottom: 10,
    padding: 13,
    borderRadius: 15,
    backgroundColor: "#FFFFFF",
    gap: 10
  },
  addressTextContainer: {
    flex: 1
  },
  addressLabel: {
    color: "#64748B",
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 0.8,
    marginBottom: 4
  },
  addressText: {
    color: "#1E293B",
    fontSize: 13,
    lineHeight: 19,
    fontWeight: "600"
  },
  mapContainer: {
    flex: 1,
    overflow: "hidden",
    marginHorizontal: 12,
    borderRadius: 18,
    backgroundColor: "#E7ECE9"
  },
  webView: {
    flex: 1,
    backgroundColor: "transparent"
  },
  centered: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    gap: 12
  },
  centeredText: {
    color: "#475569",
    fontSize: 14,
    lineHeight: 21,
    textAlign: "center"
  },
  routeCard: {
    flexDirection: "row",
    alignItems: "center",
    margin: 12,
    marginBottom: 8,
    padding: 15,
    borderRadius: 16,
    backgroundColor: "#FFFFFF",
    gap: 12
  },
  routeMetric: {
    flex: 1
  },
  metricLabel: {
    color: "#64748B",
    fontSize: 10,
    fontWeight: "800",
    letterSpacing: 0.5
  },
  metricValue: {
    color: "#16382A",
    fontSize: 20,
    fontWeight: "800",
    marginTop: 5
  },
  metricDivider: {
    width: 1,
    alignSelf: "stretch",
    backgroundColor: "#E2E8F0"
  },
  provider: {
    alignItems: "center",
    justifyContent: "center",
    gap: 4
  },
  providerText: {
    color: "#087653",
    fontSize: 10,
    fontWeight: "700"
  },
  statusMessage: {
    marginHorizontal: 12,
    marginBottom: 10,
    padding: 10,
    borderRadius: 10,
    backgroundColor: "#FFF7ED"
  },
  statusMessageText: {
    color: "#9A3412",
    fontSize: 12,
    lineHeight: 18
  }
});
