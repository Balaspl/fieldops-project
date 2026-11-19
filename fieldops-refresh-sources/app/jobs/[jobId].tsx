import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Image,
  Linking,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { router, useFocusEffect, useLocalSearchParams } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { customerApi } from "../../src/api/customer";
import { apiClient, getApiErrorMessage } from "../../src/api/client";
import {
  AppButton,
  ErrorState,
  Field,
  LoadingView,
  Screen,
} from "../../src/components/ui";
import type { CustomerFeedback, CustomerJob } from "../../src/types/api";
import { colors } from "../../src/theme";
import { env } from "../../src/config/env";
import { WebView, type WebViewMessageEvent } from "react-native-webview";

const GREEN = "#087653";
const DARK_GREEN = "#064E3B";
const TEXT = "#102A24";
const MUTED = "#71847D";
const BORDER = "#E3EEE8";
const PALE = "#F3FAF6";
const REFRESH_INTERVAL_MS = 2000;

type TrackingJob = CustomerJob & {
  accepted_at?: string | null;
  assigned_at?: string | null;
  en_route_at?: string | null;
  distance_travelled_km?: number | null;
  technician_accepted?: boolean;
  issue_description?: string | null;
  preferred_service_date?: string | null;
  preferred_service_time?: string | null;
};

type Milestone = {
  key: string;
  title: string;
  icon: keyof typeof Ionicons.glyphMap;
  time?: string | null;
};

function asDate(value?: string | null): Date | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatDateTime(value?: string | null): string {
  const date = asDate(value);
  if (!date) return "";
  return date.toLocaleString([], {
    day: "2-digit",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatClock(value?: string | null): string {
  const date = asDate(value);
  if (!date) return "";
  return date.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

function relativeTime(value?: string | null): string {
  const date = asDate(value);
  if (!date) return "No recent GPS update";
  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return "Live location updated just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `Live location updated ${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `Last location update ${hours} hr ago`;
  return `Last location update ${Math.floor(hours / 24)} day(s) ago`;
}

function durationBetween(startValue?: string | null, endValue?: string | null): number | null {
  const start = asDate(startValue);
  const end = endValue ? asDate(endValue) : new Date();
  if (!start || !end || end.getTime() < start.getTime()) return null;
  return (end.getTime() - start.getTime()) / 1000;
}

function formatHours(seconds: number | null): string {
  if (seconds == null) return "Not available";
  const hours = seconds / 3600;
  if (hours < 1) return `${Math.max(1, Math.round(seconds / 60))} min`;
  return `${hours.toFixed(1)} hrs`;
}

function formatAppointment(dateValue?: string | null, timeValue?: string | null): string {
  let dayLabel = "";
  if (dateValue) {
    const match = dateValue.match(/^(\d{4})-(\d{2})-(\d{2})/);
    const date = match
      ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
      : asDate(dateValue);
    if (date) {
      const today = new Date();
      const tomorrow = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1);
      const normalized = new Date(date.getFullYear(), date.getMonth(), date.getDate());
      if (normalized.getTime() === new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime()) {
        dayLabel = "Today";
      } else if (normalized.getTime() === tomorrow.getTime()) {
        dayLabel = "Tomorrow";
      } else {
        dayLabel = date.toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric" });
      }
    }
  }

  let clockLabel = "";
  const timeMatch = timeValue?.match(/^(\d{1,2}):(\d{2})/);
  if (timeMatch) {
    const clock = new Date(2000, 0, 1, Number(timeMatch[1]), Number(timeMatch[2]));
    clockLabel = clock.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  } else if (timeValue) {
    clockLabel = timeValue;
  }

  return [dayLabel, clockLabel].filter(Boolean).join(" · ") || "Appointment details unavailable";
}

function normalizedStatus(status?: string | null): string {
  return String(status ?? "")
    .trim()
    .toUpperCase()
    .replace(/[ -]+/g, "_");
}

function getProgressStage(job: TrackingJob): number {
  const status = normalizedStatus(job.status);
  const accepted = Boolean(job.technician_accepted) || [
    "ACCEPTED",
    "EN_ROUTE",
    "ENROUTE",
    "ON_SITE",
    "ONSITE",
    "IN_PROGRESS",
    "COMPLETED",
    "CLOSED",
  ].includes(status);

  if (job.completed_at || ["COMPLETED", "CLOSED"].includes(status)) return 5;
  if (job.work_started_at || status === "IN_PROGRESS" || status === "WORK_STARTED") return 4;
  if (job.on_site_at || ["ON_SITE", "ONSITE"].includes(status)) return 3;
  if (job.en_route_at || ["EN_ROUTE", "ENROUTE"].includes(status)) return 2;
  if (accepted) return 1;
  return 0;
}

function milestoneTimeLabel(time: string | null | undefined, reached: boolean): string {
  if (time) return formatDateTime(time) || "Time unavailable";
  return reached ? "Time unavailable" : "Pending";
}

function MilestoneTimeline({ job, currentStage }: { job: TrackingJob; currentStage: number }) {
  const milestones: Milestone[] = [
    { key: "booked", title: "Booked", icon: "checkmark-outline", time: job.created_at },
    { key: "accepted", title: "Accepted", icon: "navigate-outline", time: job.accepted_at },
    { key: "enroute", title: "On the way", icon: "car-outline", time: job.en_route_at },
    { key: "arrived", title: "Arrived", icon: "location-outline", time: job.on_site_at },
    { key: "work", title: "Work started", icon: "construct-outline", time: job.work_started_at },
    { key: "completed", title: "Completed", icon: "checkmark-circle-outline", time: job.completed_at },
  ];

  return (
    <View style={styles.timelineCard}>
      <View style={styles.timelineIntro}>
        <View style={styles.timelineIntroIcon}>
          <Ionicons name={currentStage >= 2 ? "navigate" : "paper-plane-outline"} size={22} color={GREEN} />
        </View>
        <View style={styles.flexOne}>
          <Text style={styles.timelineHeading}>
            {currentStage >= 5
              ? "Your service job is completed"
              : currentStage >= 4
                ? "Work has started at your site"
                : currentStage >= 3
                  ? "Your technician has arrived"
                  : currentStage >= 2
                    ? "Your technician is on the way"
                    : currentStage >= 1
                      ? "Your technician accepted the job"
                      : job.assigned_technician_id
                        ? "Your technician is assigned"
                        : "Your service request is booked"}
          </Text>
          <Text style={styles.timelineSubtitle}>
            {currentStage >= 5
              ? "Your service journey is complete"
              : currentStage >= 3
                ? "We'll keep you updated as work progresses"
                : currentStage >= 1
                  ? "We'll keep you updated as your visit progresses"
                  : "We'll notify you when a technician accepts the job"}
          </Text>
        </View>
      </View>

      <View style={styles.milestoneTrack}>
        <View style={styles.trackBase} />
        <View style={[styles.trackActive, { width: `${(currentStage / (milestones.length - 1)) * 83.4}%` }]} />
        {milestones.map((milestone, index) => {
          const reached = index <= currentStage;
          const current = index === currentStage;
          return (
            <View key={milestone.key} style={styles.milestoneItem}>
              <View style={[styles.milestoneCircle, reached && styles.milestoneCircleDone, current && styles.milestoneCircleCurrent]}>
                <Ionicons
                  name={index < currentStage ? "checkmark" : milestone.icon}
                  size={17}
                  color={reached ? "#FFFFFF" : "#91A39B"}
                />
              </View>
              <Text style={[styles.milestoneTitle, reached && styles.milestoneTitleActive]} numberOfLines={1}>
                {milestone.title}
              </Text>
              <Text style={styles.milestoneTime} numberOfLines={2}>
                {milestoneTimeLabel(milestone.time, reached)}
              </Text>
            </View>
          );
        })}
      </View>
    </View>
  );
}

type OlaRouteResponse = {
  distance_meters?: number;
  duration_seconds?: number;
  route_points?: [number, number][];
  provider?: string;
  fallback?: boolean;
};

type MapPoint = { lat: number; lng: number };
type OlaMapData = {
  customer: MapPoint | null;
  technician: MapPoint | null;
  routePoints: [number, number][];
};

const OLA_STYLE_URL = "https://api.olamaps.io/tiles/vector/v1/styles/default-light-standard/style.json";

function createOlaMapHtml(apiKey: string): string {
  const safeKey = JSON.stringify(apiKey);
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
<style>
  html, body, #map { width:100%; height:100%; margin:0; padding:0; overflow:hidden; background:#edf3ee; }
  #map-error { display:none; position:absolute; inset:0; padding:22px; box-sizing:border-box; align-items:center; justify-content:center; text-align:center; color:#476258; background:#edf3ee; font:600 14px/1.5 -apple-system,BlinkMacSystemFont,Arial,sans-serif; }
  .fieldops-pin { width:42px; height:42px; box-sizing:border-box; display:flex; align-items:center; justify-content:center; border-radius:50% 50% 50% 8px; transform:rotate(-45deg); border:3px solid #fff; box-shadow:0 3px 12px rgba(0,45,29,.25); }
  .fieldops-pin-inner { transform:rotate(45deg); color:#fff; font:800 16px Arial,sans-serif; }
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
  const routeSourceId = "fieldops-customer-route";
  const routeLayerId = "fieldops-customer-route-line";
  let olaSdk = null;
  let map = null;
  let markerRefs = { customer: null, technician: null };
  let latestData = null;
  let initialCameraSet = false;

  function notify(payload) {
    try { window.ReactNativeWebView.postMessage(JSON.stringify(payload)); } catch (_) {}
  }

  function showError(message) {
    const panel = document.getElementById("map-error");
    panel.style.display = "flex";
    panel.textContent = message || "Ola Maps could not be loaded.";
    notify({ type: "error", message: panel.textContent });
  }

  function markerElement(kind) {
    const element = document.createElement("div");
    element.className = "fieldops-pin";
    element.style.background = kind === "customer" ? "#087653" : "#0F766E";
    const inner = document.createElement("div");
    inner.className = "fieldops-pin-inner";
    inner.textContent = kind === "customer" ? "⌂" : "T";
    element.appendChild(inner);
    return element;
  }

  function setMarker(kind, point) {
    if (markerRefs[kind]) {
      try { markerRefs[kind].remove(); } catch (_) {}
      markerRefs[kind] = null;
    }
    if (!point || !Number.isFinite(point.lat) || !Number.isFinite(point.lng)) return;
    markerRefs[kind] = olaSdk.addMarker({ element: markerElement(kind), anchor: "bottom" })
      .setLngLat([point.lng, point.lat])
      .addTo(map);
  }

  function setRoute(points) {
    const valid = Array.isArray(points) && points.length >= 2;
    const existing = map.getSource(routeSourceId);
    if (!valid) {
      if (map.getLayer(routeLayerId)) map.removeLayer(routeLayerId);
      if (existing) map.removeSource(routeSourceId);
      return;
    }
    if (typeof map.isStyleLoaded === "function" && !map.isStyleLoaded()) {
      map.once("idle", function () { setRoute(points); });
      return;
    }
    const geojson = {
      type: "Feature",
      properties: {},
      geometry: { type: "LineString", coordinates: points }
    };
    if (existing) existing.setData(geojson);
    else map.addSource(routeSourceId, { type: "geojson", data: geojson });
    if (!map.getLayer(routeLayerId)) {
      map.addLayer({
        id: routeLayerId,
        type: "line",
        source: routeSourceId,
        layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": "#087653", "line-width": 5, "line-opacity": 0.94 }
      });
    }
  }

  function updateMap(data) {
    latestData = data;
    if (!map || !olaSdk || !data) return;

    setMarker("customer", data.customer);
    setMarker("technician", data.technician);
    setRoute(data.routePoints);

    if (!initialCameraSet) {
      const points = [];
      if (data.customer) points.push(data.customer);
      if (data.technician) points.push(data.technician);
      if (points.length > 1) {
        const lngs = points.map((point) => point.lng);
        const lats = points.map((point) => point.lat);
        const west = Math.min.apply(null, lngs);
        const east = Math.max.apply(null, lngs);
        const south = Math.min.apply(null, lats);
        const north = Math.max.apply(null, lats);
        if (Math.abs(east - west) < 0.0008 && Math.abs(north - south) < 0.0008) {
          map.flyTo({ center: [points[0].lng, points[0].lat], zoom: 14, duration: 450 });
        } else {
          map.fitBounds([[west, south], [east, north]], { padding: 48, maxZoom: 15, duration: 450 });
        }
      } else if (points.length === 1) {
        map.flyTo({ center: [points[0].lng, points[0].lat], zoom: 14, duration: 450 });
      }
      initialCameraSet = points.length > 0;
    }
  }

  window.updateFieldOpsOlaMap = updateMap;
  window.resizeFieldOpsOlaMap = function () { if (map && typeof map.resize === "function") map.resize(); };

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
        center: [80.2707, 13.0827],
        zoom: 11
      });
      try { map.addControl(olaSdk.addNavigationControls({ showCompass: true }), "top-right"); } catch (_) {}
      if (latestData) updateMap(latestData);
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

function isValidCoordinates(latitude: unknown, longitude: unknown): boolean {
  const lat = Number(latitude);
  const lng = Number(longitude);
  return latitude !== null && latitude !== undefined && longitude !== null && longitude !== undefined
    && Number.isFinite(lat) && Number.isFinite(lng)
    && lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180
    && !(lat === 0 && lng === 0);
}

function MapPreview({ job }: { job: TrackingJob }) {
  const webViewRef = useRef<WebView>(null);
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState("");
  const [expanded, setExpanded] = useState(false);
  const [routePoints, setRoutePoints] = useState<[number, number][]>([]);
  const [routeLoading, setRouteLoading] = useState(false);
  const [routeUnavailable, setRouteUnavailable] = useState(false);

  const hasTechnicianGps = Boolean(
    job.live_tracking && isValidCoordinates(job.technician_latitude, job.technician_longitude),
  );
  const hasCustomerCoordinates = isValidCoordinates(job.site_latitude, job.site_longitude);
  const technicianLat = hasTechnicianGps ? Number(job.technician_latitude) : null;
  const technicianLng = hasTechnicianGps ? Number(job.technician_longitude) : null;
  const customerLat = hasCustomerCoordinates ? Number(job.site_latitude) : null;
  const customerLng = hasCustomerCoordinates ? Number(job.site_longitude) : null;
  const hasAnyCoordinates = hasTechnicianGps || hasCustomerCoordinates;
  const html = useMemo(() => createOlaMapHtml(env.OLA_MAPS_API_KEY), [env.OLA_MAPS_API_KEY]);

  useEffect(() => {
    if (!hasTechnicianGps || !hasCustomerCoordinates || technicianLat === null || technicianLng === null || customerLat === null || customerLng === null) {
      setRoutePoints([]);
      setRouteLoading(false);
      setRouteUnavailable(false);
      return;
    }

    let cancelled = false;
    const controller = new AbortController();
    setRouteLoading(true);
    setRouteUnavailable(false);

    apiClient.get<OlaRouteResponse>("/api/v1/gps/route", {
      params: {
        origin_lat: technicianLat,
        origin_lng: technicianLng,
        dest_lat: customerLat,
        dest_lng: customerLng,
      },
      signal: controller.signal,
    }).then(({ data }) => {
      if (cancelled) return;
      const validPoints = Array.isArray(data.route_points)
        && data.route_points.length >= 2
        && data.route_points.every((point) => Array.isArray(point)
          && point.length >= 2
          && Number.isFinite(point[0]) && Number.isFinite(point[1])
          && point[0] >= -180 && point[0] <= 180
          && point[1] >= -90 && point[1] <= 90);
      const authoritativeOlaRoute = data.provider === "ola_maps" && data.fallback !== true && validPoints;
      setRoutePoints(authoritativeOlaRoute ? data.route_points! : []);
      setRouteUnavailable(!authoritativeOlaRoute);
    }).catch(() => {
      if (!cancelled) {
        setRoutePoints([]);
        setRouteUnavailable(true);
      }
    }).finally(() => {
      if (!cancelled) setRouteLoading(false);
    });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [hasTechnicianGps, hasCustomerCoordinates, technicianLat, technicianLng, customerLat, customerLng]);

  const mapData = useMemo<OlaMapData>(() => ({
    customer: hasCustomerCoordinates && customerLat !== null && customerLng !== null
      ? { lat: customerLat, lng: customerLng }
      : null,
    technician: hasTechnicianGps && technicianLat !== null && technicianLng !== null
      ? { lat: technicianLat, lng: technicianLng }
      : null,
    routePoints,
  }), [hasCustomerCoordinates, customerLat, customerLng, hasTechnicianGps, technicianLat, technicianLng, routePoints]);

  useEffect(() => {
    if (!mapReady || !webViewRef.current) return;
    const payload = JSON.stringify(mapData).replace(/</g, "\\u003c");
    webViewRef.current.injectJavaScript(`window.updateFieldOpsOlaMap && window.updateFieldOpsOlaMap(${payload}); true;`);
  }, [mapReady, mapData]);

  useEffect(() => {
    if (!mapReady || !webViewRef.current) return;
    const timer = setTimeout(() => {
      webViewRef.current?.injectJavaScript("window.resizeFieldOpsOlaMap && window.resizeFieldOpsOlaMap(); true;");
    }, 150);
    return () => clearTimeout(timer);
  }, [expanded, mapReady]);

  const onMapMessage = useCallback((event: WebViewMessageEvent) => {
    try {
      const message = JSON.parse(event.nativeEvent.data) as { type?: string; message?: string };
      if (message.type === "ready") {
        setMapReady(true);
        setMapError("");
      } else if (message.type === "error") {
        setMapError(message.message || "Ola Maps failed to load.");
      }
    } catch {
      // Ignore non-JSON messages from the map page.
    }
  }, []);

  const statusSubtitle = hasTechnicianGps
    ? routeLoading
      ? "Live GPS available · Calculating Ola Maps route…"
      : routePoints.length >= 2
        ? `${relativeTime(job.technician_last_ping)} · Ola Maps road route`
        : routeUnavailable
          ? `${relativeTime(job.technician_last_ping)} · Road route unavailable`
          : relativeTime(job.technician_last_ping)
    : hasCustomerCoordinates
      ? "Showing the service location until live technician GPS is available."
      : "Map coordinates have not been provided by the backend yet.";

  return (
    <View style={[styles.mapCard, expanded && styles.mapCardExpanded]}>
      {env.OLA_MAPS_API_KEY && hasAnyCoordinates ? (
        <WebView
          ref={webViewRef}
          source={{ html }}
          originWhitelist={["*"]}
          javaScriptEnabled
          domStorageEnabled
          onMessage={onMapMessage}
          onError={(event) => setMapError(event.nativeEvent.description || "Ola Maps could not load.")}
          style={styles.mapWebView}
          accessibilityLabel="Ola Maps live job tracking map"
        />
      ) : (
        <View style={styles.mapUnavailableCard}>
          <Ionicons name="map-outline" size={28} color={GREEN} />
          <Text style={styles.mapNoticeTitle}>
            {!env.OLA_MAPS_API_KEY ? "Ola Maps needs an API key" : "Location unavailable"}
          </Text>
          <Text style={styles.mapNoticeSubtitle}>
            {!env.OLA_MAPS_API_KEY
              ? "Set EXPO_PUBLIC_OLA_MAPS_API_KEY in customer-mobile/.env and restart Expo."
              : "The backend has not returned valid service-site or live technician coordinates yet."}
          </Text>
        </View>
      )}

      {env.OLA_MAPS_API_KEY && hasAnyCoordinates ? (
        <>
          <View pointerEvents="none" style={styles.mapNotice}>
            <View style={[styles.liveDot, hasTechnicianGps ? styles.liveDotOn : styles.liveDotOff]} />
            <View style={styles.flexOne}>
              <Text style={styles.mapNoticeTitle}>
                {hasTechnicianGps ? "Technician location available" : "Service location shown"}
              </Text>
              <Text style={styles.mapNoticeSubtitle} numberOfLines={2}>
                {mapError ? "Map could not load · check the Ola Maps key or network." : statusSubtitle}
              </Text>
            </View>
          </View>
          <Pressable
            onPress={() => setExpanded((value) => !value)}
            style={styles.mapOpenButton}
            accessibilityRole="button"
            accessibilityLabel={expanded ? "Collapse map" : "Expand map"}
          >
            <Ionicons name={expanded ? "contract-outline" : "expand-outline"} size={19} color={DARK_GREEN} />
          </Pressable>
        </>
      ) : null}
    </View>
  );
}

function Metric({
  icon,
  label,
  value,
  detail,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  value: string;
  detail?: string;
}) {
  return (
    <View style={styles.metric}>
      <Ionicons name={icon} size={23} color={DARK_GREEN} />
      <Text style={styles.metricLabel} numberOfLines={2}>{label}</Text>
      <Text style={styles.metricValue} numberOfLines={2}>{value}</Text>
      {detail ? <Text style={styles.metricDetail} numberOfLines={2}>{detail}</Text> : null}
    </View>
  );
}

function TechnicianCard({ job, onCall, onChat }: { job: TrackingJob; onCall: () => void; onChat: () => void }) {
  const technicianName = job.assigned_technician_name || "Technician details pending";
  const initials = technicianName
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("") || "TE";

  return (
    <View style={styles.technicianCard}>
      <View style={styles.technicianAvatar}>
        {job.assigned_technician_photo ? (
          <Image source={{ uri: job.assigned_technician_photo }} style={styles.technicianPhoto} />
        ) : (
          <Text style={styles.technicianInitials}>{initials}</Text>
        )}
        {job.assigned_technician_id != null ? <View style={styles.technicianOnlineDot} /> : null}
      </View>

      <View style={styles.technicianInfo}>
        <Text style={styles.technicianName} numberOfLines={1}>{technicianName}</Text>
        <Text style={styles.technicianRole} numberOfLines={2}>
          {job.assigned_technician_skills?.slice(0, 2).join(" · ") || job.service_type || "Field technician"}
        </Text>
        {job.assigned_technician_experience ? (
          <Text style={styles.technicianExperience} numberOfLines={1}>{job.assigned_technician_experience} experience</Text>
        ) : null}
      </View>

      <Pressable onPress={onCall} style={styles.technicianAction} accessibilityRole="button" accessibilityLabel="Call technician">
        <View style={styles.technicianActionIcon}><Ionicons name="call-outline" size={22} color={DARK_GREEN} /></View>
        <Text style={styles.technicianActionLabel}>Call</Text>
      </Pressable>

      <Pressable onPress={onChat} style={styles.technicianAction} accessibilityRole="button" accessibilityLabel="Chat with technician">
        <View style={styles.technicianActionIcon}><Ionicons name="chatbubble-ellipses-outline" size={22} color={DARK_GREEN} /></View>
        <Text style={styles.technicianActionLabel}>Chat</Text>
      </Pressable>
    </View>
  );
}

function ServiceDetailsCard({ job }: { job: TrackingJob }) {
  const appointment = formatAppointment(job.preferred_service_date, job.preferred_service_time);

  return (
    <View style={styles.sectionCard}>
      <View style={styles.sectionHeadingRow}>
        <View style={styles.sectionHeadingIcon}><Ionicons name="document-text-outline" size={21} color={GREEN} /></View>
        <Text style={styles.sectionHeading}>Service details</Text>
      </View>

      <View style={styles.serviceDetailsRow}>
        <View style={styles.detailIconCircle}><Ionicons name="location-outline" size={22} color={GREEN} /></View>
        <View style={styles.serviceDetailText}>
          <Text style={styles.detailLabel}>Service address</Text>
          <Text style={styles.detailValue}>{job.site_address || job.location || "Address not available"}</Text>
        </View>
      </View>

      <View style={styles.horizontalDivider} />

      <View style={styles.serviceDetailsRow}>
        <View style={styles.detailIconCircle}><Ionicons name="calendar-outline" size={22} color={GREEN} /></View>
        <View style={styles.serviceDetailText}>
          <Text style={styles.detailLabel}>Scheduled appointment</Text>
          <Text style={styles.detailValue}>{appointment}</Text>
        </View>
      </View>

      <View style={styles.horizontalDivider} />

      <View style={styles.serviceBottomDetails}>
        <View style={styles.serviceBottomItem}>
          <View style={styles.detailIconCircle}><Ionicons name="construct-outline" size={21} color={GREEN} /></View>
          <View style={styles.serviceDetailText}>
            <Text style={styles.detailLabel}>Service type</Text>
            <Text style={styles.detailValue}>{job.service_type || "Not available"}</Text>
          </View>
        </View>
        <View style={styles.serviceBottomItem}>
          <View style={styles.detailIconCircle}><Ionicons name="alert-circle-outline" size={21} color={GREEN} /></View>
          <View style={styles.serviceDetailText}>
            <Text style={styles.detailLabel}>Issue description</Text>
            <Text style={styles.detailValue}>{job.issue_description || "Not provided"}</Text>
          </View>
        </View>
      </View>
    </View>
  );
}

export default function CustomerJobDetailScreen() {
  const params = useLocalSearchParams<{ jobId: string }>();
  const jobId = Number(params.jobId);
  const [job, setJob] = useState<TrackingJob | null>(null);
  const [feedback, setFeedback] = useState<CustomerFeedback | null>(null);
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const [showFeedback, setShowFeedback] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [feedbackError, setFeedbackError] = useState("");

  const load = useCallback(async (pull = false, silent = false) => {
    if (pull) setRefreshing(true);
    else if (!silent) setLoading(true);
    if (!silent) setError("");

    try {
      if (!Number.isSafeInteger(jobId) || jobId <= 0) {
        throw new Error("This job ID is invalid.");
      }
      const result = await customerApi.job(jobId) as TrackingJob;
      setJob(result);

      if (["COMPLETED", "CLOSED"].includes(normalizedStatus(result.status))) {
        try {
          setFeedback(await customerApi.feedback(jobId));
        } catch {
          setFeedback(null);
        }
      } else {
        setFeedback(null);
      }
    } catch (e) {
      if (!silent) {
        setError(getApiErrorMessage(e, "Unable to load job tracking details."));
      }
    } finally {
      if (!silent) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [jobId]);

  useFocusEffect(
    useCallback(() => {
      void load();
      const timer = setInterval(() => void load(false, true), REFRESH_INTERVAL_MS);
      return () => clearInterval(timer);
    }, [load]),
  );

  const progressStage = useMemo(() => job ? getProgressStage(job) : 0, [job]);
  const isCompleted = Boolean(job && ["COMPLETED", "CLOSED"].includes(normalizedStatus(job.status)));
  const onSiteDuration = useMemo(() => job ? durationBetween(job.on_site_at, job.completed_at) : null, [job]);

  const callTechnician = async () => {
    if (!job?.assigned_technician_phone) {
      Alert.alert("Phone number unavailable", "The backend has not provided a technician phone number for this job.");
      return;
    }
    try {
      await Linking.openURL(`tel:${job.assigned_technician_phone}`);
    } catch {
      Alert.alert("Unable to call", "This device cannot open the phone dialer.");
    }
  };

  const openChat = () => {
    if (!job) return;
    if (!job.assigned_technician_id) {
      Alert.alert("Chat not available yet", "Chat becomes available after a technician is assigned to this job.");
      return;
    }
    router.push({ pathname: "/job-chat/[jobId]", params: { jobId: String(job.id) } });
  };

  const submitFeedback = async () => {
    setFeedbackError("");
    if (rating < 1 || rating > 5) {
      setFeedbackError("Choose a rating from 1 to 5 stars.");
      return;
    }
    setSubmitting(true);
    try {
      setFeedback(await customerApi.submitFeedback(jobId, rating, comment));
      setShowFeedback(false);
      Alert.alert("Thank you", "Your feedback was submitted.");
    } catch (e) {
      setFeedbackError(getApiErrorMessage(e, "Could not submit feedback."));
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <Screen><LoadingView message="Loading job tracking…" /></Screen>;
  if (!job) {
    return (
      <Screen>
        <ErrorState message={error || "Job could not be found."} onRetry={() => void load()} />
        <AppButton title="Back to tracking" onPress={() => router.replace("/(tabs)/tracking")} />
      </Screen>
    );
  }

  const arrivalMinutes = job.eta_duration_minutes != null && job.eta_duration_minutes >= 0
    ? `${Math.round(job.eta_duration_minutes)} min`
    : "Not available";
  const etaClock = job.estimated_arrival ? formatClock(job.estimated_arrival) : "";
  const remainingDistance = job.eta_distance_km != null && job.eta_distance_km >= 0
    ? `${job.eta_distance_km.toFixed(1)} km`
    : "Not available";
  const travelledDistance = job.distance_travelled_km != null && Number.isFinite(job.distance_travelled_km)
    ? `${job.distance_travelled_km.toFixed(1)} km`
    : "Not available";
  const lastUpdate = job.technician_last_ping || job.eta_updated_at;

  return (
    <Screen scroll={false} contentStyle={{ paddingHorizontal: 0, paddingTop: 0, paddingBottom: 0 }}>
      <ScrollView
        style={styles.screen}
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load(true)} tintColor={GREEN} />}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.pageHeader}>
          <Pressable onPress={() => router.back()} style={styles.headerIconButton} accessibilityRole="button" accessibilityLabel="Go back">
            <Ionicons name="arrow-back" size={23} color={DARK_GREEN} />
          </Pressable>
          <View style={styles.pageHeaderText}>
            <Text style={styles.pageTitle}>Track Job</Text>
            <Text style={styles.pageSubtitle}>Job #{job.id}</Text>
          </View>
          <Pressable onPress={() => void load(true)} style={styles.headerIconButton} accessibilityRole="button" accessibilityLabel="Refresh tracking details">
            <Ionicons name="refresh" size={22} color={DARK_GREEN} />
          </Pressable>
        </View>

        {error ? <ErrorState message={error} onRetry={() => void load()} /> : null}

        <MilestoneTimeline job={job} currentStage={progressStage} />

        {["EN_ROUTE", "ENROUTE"].includes(
          normalizedStatus(job.status),
        ) ? (
          <MapPreview job={job} />
        ) : null}

        <View style={styles.metricsCard}>
          <Metric
            icon="car-outline"
            label="Distance to you"
            value={remainingDistance}
            detail={job.eta_source === "estimated" ? "Estimated route distance" : job.eta_source === "calculated" ? "Current route estimate" : "Waiting for route data"}
          />
          <View style={styles.metricDivider} />
          <Metric
            icon="time-outline"
            label="Estimated arrival"
            value={arrivalMinutes}
            detail={etaClock ? `Around ${etaClock}` : job.eta_message || "Waiting for GPS update"}
          />
          <View style={styles.metricDivider} />
          <Metric
            icon="navigate-outline"
            label="Distance travelled"
            value={travelledDistance}
            detail={job.distance_travelled_km != null ? "GPS route distance" : "GPS route history unavailable"}
          />
          <View style={styles.metricDivider} />
          <Metric
            icon="hourglass-outline"
            label="Time on site"
            value={job.on_site_at ? formatHours(onSiteDuration) : "Pending"}
            detail={job.on_site_at ? (job.completed_at ? "Final duration" : "Elapsed since arrival") : "Starts when technician arrives"}
          />
        </View>

        <TechnicianCard job={job} onCall={() => void callTechnician()} onChat={openChat} />

        <ServiceDetailsCard job={job} />

        <View style={styles.lastUpdateRow}>
          <Ionicons name="sync-outline" size={15} color={MUTED} />
          <Text style={styles.lastUpdateText}>
            {lastUpdate ? `Last update: ${formatDateTime(lastUpdate)}` : "Waiting for the first live tracking update"}
          </Text>
          <View style={styles.statusChip}>
            <Text style={styles.statusChipText}>{String(job.status || "UNKNOWN").replaceAll("_", " ")}</Text>
          </View>
        </View>

        {isCompleted ? (
          <View style={styles.sectionCard}>
            <Text style={styles.sectionHeading}>Your feedback</Text>
            {feedback?.has_feedback && feedback.feedback ? (
              <>
                <Text style={styles.feedbackRating}>{"★".repeat(feedback.feedback.rating)}{"☆".repeat(5 - feedback.feedback.rating)} · {feedback.feedback.rating}/5</Text>
                {feedback.feedback.comment ? <Text style={styles.detailValue}>{feedback.feedback.comment}</Text> : null}
                <Text style={styles.milestoneTime}>{formatDateTime(feedback.feedback.created_at)}</Text>
              </>
            ) : showFeedback ? (
              <>
                <View style={styles.ratingRow}>
                  {[1, 2, 3, 4, 5].map((value) => (
                    <Pressable key={value} onPress={() => setRating(value)} accessibilityLabel={`${value} stars`}>
                      <Ionicons name={rating >= value ? "star" : "star-outline"} size={31} color={rating >= value ? "#E3A008" : "#A3ADA6"} />
                    </Pressable>
                  ))}
                </View>
                <Field label="Comment (optional)" value={comment} onChangeText={setComment} multiline placeholder="Share your service experience" maxLength={1500} />
                {feedbackError ? <Text style={styles.errorInline}>{feedbackError}</Text> : null}
                <AppButton title="Submit feedback" onPress={() => void submitFeedback()} loading={submitting} />
              </>
            ) : (
              <AppButton title="Rate this service" icon="star-outline" kind="secondary" onPress={() => setShowFeedback(true)} />
            )}
          </View>
        ) : null}

        {["COMPLETED", "CLOSED"].includes(
          String(job.status ?? "").trim().toUpperCase(),
        ) ? (
          <AppButton
            title="View invoice details"
            icon="receipt-outline"
            kind="secondary"
            onPress={() =>
              router.push({
                pathname: "/invoices",
                params: { jobId: String(job.id) },
              })
            }
          />
        ) : null}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#F7FBF8",
  },
  content: {
    paddingHorizontal: 14,
    paddingTop: 10,
    paddingBottom: 28,
    gap: 14,
  },
  flexOne: {
    flex: 1,
    minWidth: 0,
  },
  pageHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 11,
    paddingBottom: 2,
  },
  headerIconButton: {
    width: 43,
    height: 43,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#EAF6EF",
  },
  pageHeaderText: {
    flex: 1,
  },
  pageTitle: {
    color: TEXT,
    fontSize: 25,
    fontWeight: "900",
    letterSpacing: -0.6,
  },
  pageSubtitle: {
    color: "#26372D",
    fontSize: 13,
    marginTop: 2,
  },

  timelineCard: {
    paddingHorizontal: 14,
    paddingTop: 15,
    paddingBottom: 13,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: BORDER,
    borderRadius: 20,
    shadowColor: "#123D2B",
    shadowOpacity: 0.035,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
    elevation: 1,
  },
  timelineIntro: {
    flexDirection: "row",
    alignItems: "center",
    gap: 11,
    marginBottom: 17,
  },
  timelineIntroIcon: {
    width: 42,
    height: 42,
    borderRadius: 14,
    backgroundColor: "#EAF7EF",
    alignItems: "center",
    justifyContent: "center",
  },
  timelineHeading: {
    color: TEXT,
    fontSize: 14,
    lineHeight: 19,
    fontWeight: "800",
  },
  timelineSubtitle: {
    color: "#26372D",
    fontSize: 11,
    lineHeight: 16,
    marginTop: 2,
  },
  milestoneTrack: {
    flexDirection: "row",
    justifyContent: "space-between",
    position: "relative",
    paddingTop: 2,
  },
  trackBase: {
    position: "absolute",
    top: 19,
    left: "8.3%",
    right: "8.3%",
    height: 3,
    borderRadius: 2,
    backgroundColor: "#E0EAE4",
  },
  trackActive: {
    position: "absolute",
    top: 19,
    left: "8.3%",
    height: 3,
    borderRadius: 2,
    backgroundColor: DARK_GREEN,
  },
  milestoneItem: {
    width: "16.66%",
    alignItems: "center",
    paddingHorizontal: 0,
  },
  milestoneCircle: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: "#FFFFFF",
    borderColor: "#DCE7E1",
    borderWidth: 1.2,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 8,
  },
  milestoneCircleDone: {
    backgroundColor: DARK_GREEN,
    borderColor: "#FFFFFF",
    borderWidth: 2,
  },
  milestoneCircleCurrent: {
    backgroundColor: DARK_GREEN,
    borderColor: "#FFFFFF",
    borderWidth: 4,
    width: 40,
    height: 40,
    borderRadius: 20,
    marginTop: -2,
    marginBottom: 6,
  },
  milestoneTitle: {
    width: "100%",
    textAlign: "center",
    color: DARK_GREEN,
    fontSize: 9,
    fontWeight: "900",
  },
  milestoneTitleActive: {
    color: DARK_GREEN,
  },
  milestoneTime: {
    color: "#26372D",
    fontSize: 8,
    lineHeight: 12,
    textAlign: "center",
    marginTop: 4,
    fontWeight: "700",
  },

  mapCard: {
    height: 190,
    borderRadius: 20,
    overflow: "hidden",
    borderColor: BORDER,
    borderWidth: 1,
    backgroundColor: "#E8F0E9",
    position: "relative",
  },
  mapCardExpanded: {
    height: 310,
  },
  mapWebView: {
    flex: 1,
    backgroundColor: "#EDF3EE",
  },
  mapUnavailableCard: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 24,
    gap: 8,
    backgroundColor: "#EDF3EE",
  },
  mapNotice: {
    position: "absolute",
    left: 12,
    top: 12,
    right: 58,
    flexDirection: "row",
    alignItems: "center",
    gap: 9,
    paddingHorizontal: 12,
    paddingVertical: 10,
    backgroundColor: "#FFFFFF",
    borderRadius: 14,
    shadowColor: "#193B2A",
    shadowOpacity: 0.08,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
    elevation: 2,
  },
  liveDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  liveDotOn: {
    backgroundColor: "#079669",
  },
  liveDotOff: {
    backgroundColor: "#A8B5AE",
  },
  mapNoticeTitle: {
    color: TEXT,
    fontSize: 12,
    fontWeight: "800",
  },
  mapNoticeSubtitle: {
    color: "#26372D",
    fontSize: 10,
    lineHeight: 14,
    marginTop: 2,
  },
  mapOpenButton: {
    position: "absolute",
    bottom: 12,
    right: 12,
    width: 38,
    height: 38,
    borderRadius: 12,
    backgroundColor: "#FFFFFF",
    alignItems: "center",
    justifyContent: "center",
    elevation: 2,
  },

  metricsCard: {
    flexDirection: "row",
    borderRadius: 20,
    paddingVertical: 12,
    paddingHorizontal: 4,
    backgroundColor: "#F2FAF5",
    borderWidth: 1,
    borderColor: BORDER,
  },
  metric: {
    flex: 1,
    minWidth: 0,
    alignItems: "flex-start",
    paddingHorizontal: 7,
    gap: 5,
  },
  metricDivider: {
    width: 1,
    backgroundColor: "#DFECE4",
    marginVertical: 5,
  },
  metricLabel: {
    color: "#26372D",
    fontSize: 9,
    lineHeight: 12,
    minHeight: 24,
  },
  metricValue: {
    color: TEXT,
    fontSize: 12,
    lineHeight: 16,
    fontWeight: "900",
  },
  metricDetail: {
    color: "#26372D",
    fontSize: 8,
    lineHeight: 11,
  },

  technicianCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 12,
    paddingVertical: 14,
    borderRadius: 20,
    borderColor: BORDER,
    borderWidth: 1,
    backgroundColor: "#FFFFFF",
  },
  technicianAvatar: {
    width: 54,
    height: 54,
    borderRadius: 27,
    backgroundColor: DARK_GREEN,
    alignItems: "center",
    justifyContent: "center",
    position: "relative",
  },
  technicianPhoto: {
    width: 54,
    height: 54,
    borderRadius: 27,
  },
  technicianInitials: {
    color: "#FFFFFF",
    fontSize: 16,
    fontWeight: "900",
  },
  technicianOnlineDot: {
    width: 13,
    height: 13,
    borderRadius: 7,
    position: "absolute",
    right: -1,
    bottom: 0,
    backgroundColor: "#18B66A",
    borderWidth: 2,
    borderColor: "#FFFFFF",
  },
  technicianInfo: {
    flex: 1,
    minWidth: 0,
    gap: 3,
  },
  technicianName: {
    color: TEXT,
    fontSize: 14,
    fontWeight: "900",
  },
  technicianRole: {
    color: "#26372D",
    fontSize: 10,
    lineHeight: 14,
  },
  technicianExperience: {
    color: GREEN,
    fontSize: 9,
    fontWeight: "700",
  },
  technicianAction: {
    width: 43,
    alignItems: "center",
    gap: 4,
  },
  technicianActionIcon: {
    width: 39,
    height: 39,
    borderRadius: 13,
    backgroundColor: "#EAF7EF",
    alignItems: "center",
    justifyContent: "center",
  },
  technicianActionLabel: {
    color: DARK_GREEN,
    fontSize: 10,
    fontWeight: "800",
  },

  sectionCard: {
    padding: 15,
    borderRadius: 20,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: BORDER,
    gap: 13,
  },
  sectionHeadingRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    marginBottom: 2,
  },
  sectionHeadingIcon: {
    width: 32,
    height: 32,
    borderRadius: 10,
    backgroundColor: "#EAF7EF",
    alignItems: "center",
    justifyContent: "center",
  },
  sectionHeading: {
    flex: 1,
    color: TEXT,
    fontSize: 16,
    fontWeight: "900",
  },
  serviceDetailsRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 11,
  },
  detailIconCircle: {
    width: 39,
    height: 39,
    borderRadius: 20,
    backgroundColor: "#EAF7EF",
    alignItems: "center",
    justifyContent: "center",
  },
  serviceDetailText: {
    flex: 1,
    minWidth: 0,
    gap: 3,
  },
  detailLabel: {
    color: "#26372D",
    fontSize: 11,
    fontWeight: "700",
  },
  detailValue: {
    color: TEXT,
    fontSize: 12,
    lineHeight: 18,
  },
  horizontalDivider: {
    height: 1,
    backgroundColor: "#EAF1EC",
  },
  serviceBottomDetails: {
    flexDirection: "row",
    gap: 13,
  },
  serviceBottomItem: {
    flex: 1,
    minWidth: 0,
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 8,
  },

  lastUpdateRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 2,
  },
  lastUpdateText: {
    flex: 1,
    color: "#26372D",
    fontSize: 10,
  },
  statusChip: {
    borderRadius: 9,
    backgroundColor: "#EAF7EF",
    paddingHorizontal: 8,
    paddingVertical: 5,
  },
  statusChipText: {
    color: GREEN,
    fontSize: 9,
    fontWeight: "900",
  },
  feedbackRating: {
    color: "#E3A008",
    fontSize: 18,
  },
  ratingRow: {
    flexDirection: "row",
    justifyContent: "center",
    gap: 10,
    paddingVertical: 8,
  },
  errorInline: {
    color: colors.danger,
    fontSize: 12,
  },
});