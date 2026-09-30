import React, { useEffect, useMemo, useRef, useState } from "react";

import { OlaMaps } from "olamaps-web-sdk";

import { useTrackingStore } from "../../store/trackingStore";
import { useTrackingWebSocket } from "../../hooks/useTrackingWebSocket";

import {
  getOlaRoute,
  type OlaRouteResponse,
} from "../../services/olaMapService";

/**
 * JobLiveTrackingMap
 *
 * What changed compared with the old version
 * ------------------------------------------
 * 1. The 30 s `isRecentLocation(lastPing)` gate is GONE. It hid the marker when
 *    the ping timestamp was naive (read as local time, ~5.5 h old in IST), when
 *    device/server clocks differed, or when the technician was stationary.
 *    The marker now shows whenever the store has a valid position for this job.
 * 2. Freshness is judged from `receivedAt` (stamped in the browser when the WS
 *    message arrives) + `ageAtReceipt` (server `age_seconds`). The card shows
 *    "Live" or "Last known location · N s ago" (orange when stale).
 * 3. The marker glides over the REAL gap between updates (400 ms – 3 s)
 *    instead of a fixed 300 ms.
 * 4. The map fits both markers once, the first time the technician position
 *    arrives (before, the technician could be off-screen at the default zoom).
 * 5. DEBUG PANEL + console tags (see the DEBUG section below).
 *
 * DEBUG
 * -----
 * On in `vite dev` by default. Force on/off without editing code:
 *     localStorage.setItem("trackingDebug", "1")   // on   (then reload)
 *     localStorage.setItem("trackingDebug", "0")   // off  (then reload)
 *     or open the page with  ?trackdebug=1
 * Console helper:  window.__liveMapDebug   (latest snapshot of everything)
 * The panel's DIAGNOSIS line tells you which stage is failing.
 *
 * Requires (in your hook / store, see notes in the reply):
 *   store record fields:  receivedAt?: number; ageAtReceipt?: number; source?: string
 */

// ─────────────────────────────────────────────────────────────────────────────
// Types & constants
// ─────────────────────────────────────────────────────────────────────────────
type Props = {
  jobId: number | string;

  customerLatitude?: number | null;
  customerLongitude?: number | null;

  technicianLatitude?: number | null;
  technicianLongitude?: number | null;

  technicianId?: number | string | null;

  mode: "customer" | "technician";

  tenantId: string;
  trackingTenantId?: string | null;

  buildingAddress?: string | null;
};

type Point = { lat: number; lng: number };

const DEFAULT_CENTER: Point = { lat: 13.0827, lng: 80.2707 };
const DEFAULT_ZOOM = 14;

const ROUTE_REFRESH_MS = 15_000;
const ROUTE_MIN_MOVEMENT_METERS = 50;

const LIVE_LABEL_MAX_AGE_S = 10; // below this we say "Live"
const STALE_AFTER_S = 45; // above this the label turns orange

const MIN_ANIMATION_MS = 400;
const MAX_ANIMATION_MS = 3000;

// ─────────────────────────────────────────────────────────────────────────────
// Debug
// ─────────────────────────────────────────────────────────────────────────────
function readDebugFlag(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const stored = window.localStorage.getItem("trackingDebug");
    if (stored === "0") return false;
    if (stored === "1") return true;
    if (new URLSearchParams(window.location.search).has("trackdebug")) {
      return true;
    }
  } catch {
    // ignore storage errors
  }
  return Boolean(import.meta.env.DEV);
}

const DEBUG_ENABLED = readDebugFlag();

function dbg(tag: string, data?: unknown): void {
  if (!DEBUG_ENABLED) return;
  if (data === undefined) {
    console.log(`[LIVE MAP] ${tag}`);
  } else {
    console.log(`[LIVE MAP] ${tag}`, data);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────
function toFiniteNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function isValidPoint(point: Point | null): point is Point {
  if (!point) return false;
  return (
    Number.isFinite(point.lat) &&
    Number.isFinite(point.lng) &&
    point.lat >= -90 &&
    point.lat <= 90 &&
    point.lng >= -180 &&
    point.lng <= 180
  );
}

function formatDistance(meters: number | null): string {
  if (meters === null || !Number.isFinite(meters)) return "Calculating...";
  if (meters >= 1000) return `${(meters / 1000).toFixed(1)} km`;
  return `${Math.round(meters)} m`;
}

function formatEta(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return "Calculating...";
  return `${Math.max(1, Math.round(seconds / 60))} min`;
}

function distanceBetweenPoints(a: Point, b: Point): number {
  const latMeters = (a.lat - b.lat) * 111_000;
  const lngMeters =
    (a.lng - b.lng) * 111_000 * Math.cos((a.lat * Math.PI) / 180);
  return Math.sqrt(latMeters * latMeters + lngMeters * lngMeters);
}

/** When did this store record last change? receivedAt wins over lastPing. */
function recordTime(technician: any): number {
  const received = Number(technician?.receivedAt);
  if (Number.isFinite(received) && received > 0) return received;
  const parsed = Date.parse(technician?.lastPing || "");
  return Number.isFinite(parsed) ? parsed : 0;
}

/** Read one field of the chosen technician record as a primitive (stable). */
function useTechField(storeKey: string, field: string): unknown {
  return useTrackingStore((state) =>
    storeKey ? (state.technicians[storeKey] as any)?.[field] : undefined,
  );
}

/**
 * Custom Ola Maps marker.
 *   label "C"      -> customer (home icon)
 *   anything else  -> technician pin
 */
function markerElement(label: string, background: string): HTMLDivElement {
  const element = document.createElement("div");
  const isCustomer = label === "C";

  element.setAttribute(
    "aria-label",
    isCustomer ? "Customer home location" : "Technician location",
  );

  if (isCustomer) {
    element.style.width = "46px";
    element.style.height = "46px";
    element.style.display = "flex";
    element.style.alignItems = "center";
    element.style.justifyContent = "center";
    element.style.boxSizing = "border-box";
    element.style.pointerEvents = "auto";
    element.style.userSelect = "none";
    element.style.borderRadius = "50%";
    element.style.background = background;
    element.style.border = "3px solid #ffffff";
    element.style.boxShadow = "0 4px 14px rgba(0,0,0,0.30)";

    element.innerHTML = `
      <svg width="25" height="25" viewBox="0 0 24 24" fill="none"
           xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <path d="M3 10.8L12 3L21 10.8" stroke="#FFFFFF" stroke-width="2.2"
              stroke-linecap="round" stroke-linejoin="round" />
        <path d="M5.5 9.5V20H18.5V9.5" stroke="#FFFFFF" stroke-width="2.2"
              stroke-linecap="round" stroke-linejoin="round" />
        <path d="M9.5 20V14H14.5V20" stroke="#FFFFFF" stroke-width="2.2"
              stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    `;
  } else {
    element.style.width = "56px";
    element.style.height = "70px";
    element.style.background = "transparent";
    element.style.border = "none";
    element.style.boxShadow = "none";
    element.style.padding = "0";
    element.style.margin = "0";
    element.style.overflow = "visible";
    element.style.pointerEvents = "auto";
    element.style.userSelect = "none";

    element.innerHTML = `
      <div style="position: relative; width: 56px; height: 70px;">
        <div style="
          position: absolute; top: 0; left: 3px; width: 45px; height: 45px;
          background: #ffffff; border: 2px solid #2c874f;
          border-radius: 50% 50% 50% 0; transform: rotate(-45deg);
          box-sizing: border-box; box-shadow: 0 2px 6px rgb(103, 221, 74);
        "></div>
        <img src="/technician_icon.png" alt="Technician" style="
          position: absolute; top: 7px; left: 11px; width: 34px; height: 34px;
          object-fit: contain; z-index: 2;
        " />
      </div>
    `;
  }

  return element;
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────
export default function JobLiveTrackingMap({
  jobId,
  customerLatitude,
  customerLongitude,
  technicianLatitude,
  technicianLongitude,
  technicianId,
  mode,
  tenantId,
  trackingTenantId,
  buildingAddress,
}: Props) {
  // ── Map refs ───────────────────────────────────────────────────────────────
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<any>(null);
  const olaRef = useRef<OlaMaps | null>(null);

  const technicianMarkerRef = useRef<any>(null);
  const customerMarkerRef = useRef<any>(null);

  const routeSourceId = useRef(`fieldops-route-${String(jobId)}`);
  const routeLayerId = useRef(`fieldops-route-layer-${String(jobId)}`);

  const lastRouteRef = useRef<{ lat: number; lng: number; at: number } | null>(
    null,
  );
  const lastMarkerPositionRef = useRef<Point | null>(null);
  const lastMoveAtRef = useRef(0);
  const markerAnimationRef = useRef<number | null>(null);
  const hasFittedRef = useRef(false);

  const mapReadyRef = useRef(false);
  const mapInitializingRef = useRef(false);

  // ── WebSocket ──────────────────────────────────────────────────────────────
  // The hook must use the CUSTOMER's own token (same one api.ts sends) and take
  // the tenant from the JWT. Arguments are logged below so you can verify them.
  const hookTenant = trackingTenantId || tenantId;
  useTrackingWebSocket(tenantId, String(jobId), hookTenant);

  useEffect(() => {
    dbg("hook args", {
      mode,
      jobId: String(jobId),
      tenantId,
      trackingTenantId,
      passedToHook: hookTenant,
    });
  }, [mode, jobId, tenantId, trackingTenantId, hookTenant]);

  // ── Store: pick the newest record that belongs to THIS job ────────────────
  const technicianStoreKey = useTrackingStore((state) => {
    let matchedKey = "";
    let matchedTime = Number.NEGATIVE_INFINITY;

    for (const [key, technician] of Object.entries(state.technicians)) {
      if (String((technician as any).job_id ?? "") !== String(jobId)) continue;

      const latitude = toFiniteNumber((technician as any).latitude);
      const longitude = toFiniteNumber((technician as any).longitude);
      if (
        latitude === null ||
        longitude === null ||
        !isValidPoint({ lat: latitude, lng: longitude })
      ) {
        continue;
      }

      const time = recordTime(technician);
      if (time >= matchedTime) {
        matchedKey = key;
        matchedTime = time;
      }
    }

    return matchedKey || (technicianId != null ? String(technicianId) : "");
  });

  // Read primitives separately so the component re-renders on every new fix.
  const storeLatitude = useTechField(technicianStoreKey, "latitude");
  const storeLongitude = useTechField(technicianStoreKey, "longitude");
  const storeAccuracy = useTechField(technicianStoreKey, "accuracy");
  const storeReceivedAt = useTechField(technicianStoreKey, "receivedAt");
  const storeAgeAtReceipt = useTechField(technicianStoreKey, "ageAtReceipt");
  const storeSource = useTechField(technicianStoreKey, "source");
  const storeJobId = useTechField(technicianStoreKey, "job_id");

  // Debug only: every record currently in the store.
  const allTechnicians = useTrackingStore((state) => state.technicians);

  const storePoint = useMemo<Point | null>(() => {
    const lat = toFiniteNumber(storeLatitude);
    const lng = toFiniteNumber(storeLongitude);
    if (lat === null || lng === null) return null;
    const point = { lat, lng };
    return isValidPoint(point) ? point : null;
  }, [storeLatitude, storeLongitude]);

  const accuracy =
    typeof storeAccuracy === "number" &&
    Number.isFinite(storeAccuracy) &&
    storeAccuracy >= 0
      ? storeAccuracy
      : null;

  // ── Technician's own GPS (technician mode only) ───────────────────────────
  const [ownPosition, setOwnPosition] = useState<Point | null>(null);
  const [ownAccuracy, setOwnAccuracy] = useState<number | null>(null);
  const [gpsError, setGpsError] = useState("");

  // ── Route / map state ─────────────────────────────────────────────────────
  const [route, setRoute] = useState<OlaRouteResponse | null>(null);
  const [mapError, setMapError] = useState("");
  const [mapReady, setMapReady] = useState(false);

  // ── 1 s ticker: drives the "N s ago" label and keeps the debug panel live ─
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Customer: whatever the store has for this job. NO freshness gate.
  // (Never falls back to the coordinates saved when the job was created.)
  const streamedTechnician = mode === "customer" ? storePoint : ownPosition;
  const streamedAccuracy = mode === "customer" ? accuracy : ownAccuracy;

  const receivedAtMs = toFiniteNumber(storeReceivedAt);
  const ageAtReceiptS = toFiniteNumber(storeAgeAtReceipt) ?? 0;
  const ageSec =
    receivedAtMs !== null
      ? Math.max(0, ageAtReceiptS + (now - receivedAtMs) / 1000)
      : null;
  const isStale = ageSec !== null && ageSec > STALE_AFTER_S;

  const freshnessLabel =
    ageSec === null
      ? "Live position"
      : ageSec < LIVE_LABEL_MAX_AGE_S
        ? "Live"
        : `Last known location · ${Math.round(ageSec)} s ago`;

  const origin: Point | null =
    mode === "technician" ? ownPosition : streamedTechnician;

  const destination = useMemo<Point | null>(() => {
    const lat = toFiniteNumber(customerLatitude);
    const lng = toFiniteNumber(customerLongitude);
    if (lat === null || lng === null) return null;
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
    return { lat, lng };
  }, [customerLatitude, customerLongitude]);

  // ── DEBUG: log every position that reaches the map ────────────────────────
  useEffect(() => {
    if (mode !== "customer") return;
    if (!storePoint) {
      dbg("waiting for technician location (store has no valid point for job)", {
        jobId: String(jobId),
        storeKey: technicianStoreKey || "(none)",
      });
      return;
    }
    dbg("POSITION IN STORE", {
      storeKey: technicianStoreKey,
      lat: storePoint.lat,
      lng: storePoint.lng,
      accuracy,
      source: storeSource,
      ageSec: ageSec === null ? null : Math.round(ageSec),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storePoint?.lat, storePoint?.lng, mode, jobId, technicianStoreKey]);

  // ── DEBUG: explain WHY the marker is missing ──────────────────────────────
  const storeEntries = useMemo(
    () => Object.entries(allTechnicians ?? {}),
    [allTechnicians],
  );
  const matchingEntries = storeEntries.filter(
    ([, t]) => String((t as any).job_id ?? "") === String(jobId),
  );

  let diagnosis = "OK: position received and marker should be visible";
  if (mode === "customer") {
    if (storeEntries.length === 0) {
      diagnosis =
        "STORE_EMPTY: no position_update reached the store. Check the WS Messages tab: " +
        "is a subscribe frame sent, is there an error frame, is the token role 'customer', " +
        "and does the channel tenant match the job's tenant?";
    } else if (matchingEntries.length === 0) {
      diagnosis =
        "STORE_HAS_OTHER_JOBS: the store has records, but none for job " +
        `${String(jobId)}. Compare job_id values below (type/format mismatch?).`;
    } else if (!storePoint) {
      diagnosis =
        "BAD_COORDS: a record exists for this job but latitude/longitude are invalid.";
    } else if (!mapReady) {
      diagnosis = "MAP_NOT_READY: position received, waiting for Ola Maps to load.";
    } else if (!technicianMarkerRef.current) {
      diagnosis =
        "MARKER_NOT_CREATED: position and map are ready but no marker exists (see console errors).";
    }
  }

  useEffect(() => {
    if (!DEBUG_ENABLED) return;
    (window as any).__liveMapDebug = {
      jobId: String(jobId),
      mode,
      hookArgs: { tenantId, trackingTenantId, passedToHook: hookTenant },
      technicianStoreKey,
      storeEntries: storeEntries.map(([key, t]) => ({
        key,
        job_id: (t as any).job_id,
        lat: (t as any).latitude,
        lng: (t as any).longitude,
        receivedAt: (t as any).receivedAt,
        source: (t as any).source,
      })),
      storePoint,
      origin,
      destination,
      mapReady,
      markers: {
        technician: Boolean(technicianMarkerRef.current),
        customer: Boolean(customerMarkerRef.current),
      },
      route: route
        ? {
            provider: route.provider,
            points: route.route_points?.length ?? 0,
            distance_meters: route.distance_meters,
          }
        : null,
      props: { technicianLatitude, technicianLongitude, technicianId },
      diagnosis,
    };
  });

  // ── Technician browser GPS (technician mode only) ─────────────────────────
  useEffect(() => {
    if (mode !== "technician" || !navigator.geolocation) return;

    let active = true;

    const handleSuccess = (position: GeolocationPosition) => {
      if (!active) return;
      const { latitude, longitude, accuracy: acc } = position.coords;
      setGpsError("");
      setOwnAccuracy(acc);
      if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
        setOwnPosition({ lat: latitude, lng: longitude });
      }
    };

    const handleError = (error: GeolocationPositionError) => {
      if (!active) return;
      console.warn("[LIVE MAP] Geolocation error:", error);
      setGpsError(
        "Unable to get your current location. Please allow location access.",
      );
    };

    const watchId = navigator.geolocation.watchPosition(
      handleSuccess,
      handleError,
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 8000 },
    );

    return () => {
      active = false;
      navigator.geolocation.clearWatch(watchId);
    };
  }, [mode]);

  // ── Initialize Ola Map (once per job/mode) ────────────────────────────────
  useEffect(() => {
    if (
      !containerRef.current ||
      mapInitializingRef.current ||
      mapReadyRef.current
    ) {
      return;
    }

    let cancelled = false;

    const apiKey = import.meta.env.VITE_OLA_MAPS_API_KEY;
    if (!apiKey) {
      setMapError("VITE_OLA_MAPS_API_KEY is missing.");
      return;
    }

    mapInitializingRef.current = true;

    const ola = new OlaMaps({ apiKey });
    olaRef.current = ola;

    const initialCenter = origin ?? destination ?? DEFAULT_CENTER;

    const initializeMap = async () => {
      try {
        const map = await ola.init({
          style:
            "https://api.olamaps.io/tiles/vector/v1/styles/default-light-standard/style.json",
          container: containerRef.current,
          center: [initialCenter.lng, initialCenter.lat],
          zoom: DEFAULT_ZOOM,
        });

        if (cancelled) return;

        mapRef.current = map;
        mapReadyRef.current = true;
        setMapReady(true);
        mapInitializingRef.current = false;
        dbg("map ready");

        try {
          map.addControl(
            ola.addNavigationControls({ showCompass: true }),
            "top-right",
          );
        } catch (error) {
          console.warn("[LIVE MAP] Navigation control error:", error);
        }

        if (destination) {
          customerMarkerRef.current = ola
            .addMarker({ element: markerElement("C", "#111827"), anchor: "bottom" })
            .setLngLat([destination.lng, destination.lat])
            .addTo(map);
          dbg("customer marker created", destination);
        }

        if (origin) {
          technicianMarkerRef.current = ola
            .addMarker({
              element: markerElement(mode === "technician" ? "YOU" : "T", "#2563EB"),
              anchor: "bottom",
            })
            .setLngLat([origin.lng, origin.lat])
            .addTo(map);
          lastMarkerPositionRef.current = { ...origin };
          dbg("technician marker created at init", origin);
        }

        if (!origin && destination) {
          try {
            map.flyTo({
              center: [destination.lng, destination.lat],
              zoom: DEFAULT_ZOOM,
              essential: true,
            });
          } catch {
            // ignore animation errors
          }
        }
      } catch (error) {
        if (!cancelled) {
          console.error("[LIVE MAP] Ola Maps initialization error:", error);
          setMapError(
            error instanceof Error ? error.message : "Unable to load Ola Maps.",
          );
        }
        mapInitializingRef.current = false;
      }
    };

    void initializeMap();

    return () => {
      cancelled = true;

      if (markerAnimationRef.current !== null) {
        cancelAnimationFrame(markerAnimationRef.current);
        markerAnimationRef.current = null;
      }

      try {
        technicianMarkerRef.current?.remove();
      } catch {
        // noop
      }
      try {
        customerMarkerRef.current?.remove();
      } catch {
        // noop
      }
      try {
        mapRef.current?.remove();
      } catch {
        // noop
      }

      technicianMarkerRef.current = null;
      customerMarkerRef.current = null;
      mapRef.current = null;
      olaRef.current = null;
      mapReadyRef.current = false;
      mapInitializingRef.current = false;
      lastMarkerPositionRef.current = null;
      lastMoveAtRef.current = 0;
      hasFittedRef.current = false;
      setMapReady(false);
    };
    // The map is created once. GPS changes must NOT recreate it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, mode]);

  // ── Customer marker follow / create ───────────────────────────────────────
  useEffect(() => {
    if (!mapReadyRef.current || !destination) return;

    if (customerMarkerRef.current) {
      try {
        customerMarkerRef.current.setLngLat([destination.lng, destination.lat]);
      } catch (error) {
        console.warn("[LIVE MAP] Unable to update customer marker:", error);
      }
      return;
    }

    const ola = olaRef.current;
    const map = mapRef.current;
    if (!ola || !map) return;

    try {
      customerMarkerRef.current = ola
        .addMarker({ element: markerElement("C", "#111827"), anchor: "bottom" })
        .setLngLat([destination.lng, destination.lat])
        .addTo(map);
      dbg("customer marker created (late)", destination);
    } catch (error) {
      console.error("[LIVE MAP] Unable to create customer marker:", error);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapReady, destination?.lat, destination?.lng]);

  // ── Technician marker: create, or glide to each new fix ───────────────────
  useEffect(() => {
    if (!origin || !isValidPoint(origin)) return;

    const lngLat: [number, number] = [origin.lng, origin.lat];

    if (technicianMarkerRef.current) {
      try {
        const marker = technicianMarkerRef.current;

        if (markerAnimationRef.current !== null) {
          cancelAnimationFrame(markerAnimationRef.current);
          markerAnimationRef.current = null;
        }

        const current = marker.getLngLat?.();
        const start: Point = current
          ? { lat: Number(current.lat), lng: Number(current.lng) }
          : (lastMarkerPositionRef.current ?? origin);

        if (
          !isValidPoint(start) ||
          (start.lat === origin.lat && start.lng === origin.lng)
        ) {
          marker.setLngLat(lngLat);
          lastMarkerPositionRef.current = { ...origin };
          return;
        }

        // Animate over the real time since the previous update.
        const t = performance.now();
        const gap = lastMoveAtRef.current ? t - lastMoveAtRef.current : 1000;
        lastMoveAtRef.current = t;
        const durationMs = Math.min(
          Math.max(gap, MIN_ANIMATION_MS),
          MAX_ANIMATION_MS,
        );

        let animationStart: number | null = null;
        const step = (timestamp: number) => {
          if (animationStart === null) animationStart = timestamp;
          const progress = Math.min((timestamp - animationStart) / durationMs, 1);
          marker.setLngLat([
            start.lng + (origin.lng - start.lng) * progress,
            start.lat + (origin.lat - start.lat) * progress,
          ]);

          if (progress < 1) {
            markerAnimationRef.current = requestAnimationFrame(step);
          } else {
            marker.setLngLat(lngLat);
            lastMarkerPositionRef.current = { ...origin };
            markerAnimationRef.current = null;
          }
        };
        markerAnimationRef.current = requestAnimationFrame(step);

        dbg("marker moving", { to: origin, durationMs: Math.round(durationMs) });
      } catch (error) {
        console.warn("[LIVE MAP] Failed to move technician marker:", error);
      }
      return;
    }

    const ola = olaRef.current;
    const map = mapRef.current;

    if (!ola || !map) {
      dbg("map not ready; technician marker will be created when it is");
      return;
    }

    try {
      technicianMarkerRef.current = ola
        .addMarker({
          element: markerElement(mode === "technician" ? "YOU" : "T", "#2563EB"),
          anchor: "bottom",
        })
        .setLngLat(lngLat)
        .addTo(map);
      lastMarkerPositionRef.current = { ...origin };
      lastMoveAtRef.current = performance.now();
      dbg("technician marker created", origin);
    } catch (error) {
      console.error("[LIVE MAP] Unable to create technician marker:", error);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapReady, mode, origin?.lat, origin?.lng]);

  // ── Fit both markers ONCE, the first time the technician appears ──────────
  useEffect(() => {
    if (
      hasFittedRef.current ||
      !mapReady ||
      !mapRef.current ||
      !origin ||
      !destination
    ) {
      return;
    }

    try {
      mapRef.current.fitBounds(
        [
          [Math.min(origin.lng, destination.lng), Math.min(origin.lat, destination.lat)],
          [Math.max(origin.lng, destination.lng), Math.max(origin.lat, destination.lat)],
        ],
        { padding: 90, maxZoom: 16, duration: 600 },
      );
      hasFittedRef.current = true;
      dbg("fitted map to technician + customer");
    } catch (error) {
      console.warn("[LIVE MAP] fitBounds failed:", error);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapReady, origin?.lat, origin?.lng, destination?.lat, destination?.lng]);

  // ── Route calculation (throttled) ─────────────────────────────────────────
  useEffect(() => {
    if (!origin || !destination || !isValidPoint(origin) || !isValidPoint(destination)) {
      setRoute(null);
      return;
    }

    const previous = lastRouteRef.current;
    const nowMs = Date.now();

    if (previous) {
      const movedMeters = distanceBetweenPoints(origin, previous);
      const sinceLast = nowMs - previous.at;
      if (sinceLast < ROUTE_REFRESH_MS && movedMeters < ROUTE_MIN_MOVEMENT_METERS) {
        return;
      }
    }

    lastRouteRef.current = { ...origin, at: nowMs };

    let cancelled = false;

    const calculateRoute = async () => {
      try {
        const result = await getOlaRoute({
          originLat: origin.lat,
          originLng: origin.lng,
          destinationLat: destination.lat,
          destinationLng: destination.lng,
        });
        if (!cancelled) {
          setRoute(result);
          dbg("route received", {
            points: result?.route_points?.length ?? 0,
            distance_meters: result?.distance_meters,
          });
        }
      } catch (error) {
        if (!cancelled) console.error("[LIVE MAP] Ola route error:", error);
      }
    };

    void calculateRoute();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [origin?.lat, origin?.lng, destination?.lat, destination?.lng]);

  // ── Draw / update the route line ──────────────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;

    if (!map || !route || !route.route_points || route.route_points.length < 2) {
      return;
    }

    const sourceId = routeSourceId.current;
    const layerId = routeLayerId.current;

    const geojson = {
      type: "Feature" as const,
      properties: {},
      geometry: {
        type: "LineString" as const,
        coordinates: route.route_points,
      },
    };

    let cancelled = false;

    const drawRoute = () => {
      if (cancelled) return;

      const currentMap = mapRef.current;
      if (!currentMap) return;

      try {
        // Sources/layers can only be added after the style has loaded.
        if (
          typeof currentMap.isStyleLoaded === "function" &&
          !currentMap.isStyleLoaded()
        ) {
          dbg("style not ready; waiting for load event before drawing route");
          currentMap.once?.("load", () => {
            if (!cancelled) drawRoute();
          });
          return;
        }

        const existingSource = currentMap.getSource?.(sourceId);
        if (existingSource) {
          try {
            existingSource.setData(geojson);
            return;
          } catch (error) {
            console.warn("[LIVE MAP] Route source could not be updated:", error);
          }
        }

        if (!existingSource) {
          currentMap.addSource(sourceId, { type: "geojson", data: geojson });
        }

        if (!currentMap.getLayer?.(layerId)) {
          currentMap.addLayer({
            id: layerId,
            type: "line",
            source: sourceId,
            layout: { "line-join": "round", "line-cap": "round" },
            paint: {
              "line-color": "#2563EB",
              "line-width": 6,
              "line-opacity": 0.95,
            },
          });
          dbg("route drawn", { points: route.route_points.length });
        }
      } catch (error) {
        console.error("[LIVE MAP] Unable to draw route:", error);
        window.setTimeout(() => {
          if (!cancelled) drawRoute();
        }, 300);
      }
    };

    drawRoute();

    return () => {
      cancelled = true;
    };
  }, [mapReady, route]);

  // ── Render ────────────────────────────────────────────────────────────────
  const displayAddress = buildingAddress?.trim() || "";
  const [debugOpen, setDebugOpen] = useState(true);

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: 560,
        borderRadius: 14,
        overflow: "hidden",
        background: "#E5E7EB",
      }}
    >
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />

      {displayAddress && (
        <div
          style={{
            position: "absolute",
            top: 16,
            left: 16,
            right: 16,
            zIndex: 5,
            maxWidth: 520,
            background: "rgba(255,255,255,.97)",
            borderRadius: 12,
            padding: "12px 16px",
            boxShadow: "0 4px 18px rgba(0,0,0,.16)",
          }}
        >
          <div
            style={{
              fontSize: 11,
              color: "#64748B",
              fontWeight: 800,
              textTransform: "uppercase",
              marginBottom: 4,
            }}
          >
            Service Location
          </div>
          <div style={{ fontSize: 14, color: "#1F2937", fontWeight: 600, lineHeight: 1.4 }}>
            {displayAddress}
          </div>
        </div>
      )}

      {mapError && (
        <div
          style={{
            position: "absolute",
            left: 16,
            right: 16,
            top: displayAddress ? 100 : 16,
            padding: 12,
            background: "#FEF2F2",
            color: "#991B1B",
            border: "1px solid #FECACA",
            borderRadius: 10,
            zIndex: 10,
            fontSize: 13,
          }}
        >
          {mapError}
        </div>
      )}

      {/* ── Debug panel (only when DEBUG_ENABLED) ───────────────────────────
      {DEBUG_ENABLED && (
        <div
          style={{
            position: "absolute",
            top: displayAddress ? 110 : 16,
            left: 16,
            zIndex: 20,
            maxWidth: 380,
            background: "rgba(17,24,39,.92)",
            color: "#E5E7EB",
            borderRadius: 10,
            padding: debugOpen ? "10px 12px" : "6px 10px",
            fontFamily: "ui-monospace, Menlo, Consolas, monospace",
            fontSize: 11,
            lineHeight: 1.5,
          }}
        >
          <button
            type="button"
            onClick={() => setDebugOpen((open) => !open)}
            style={{
              background: "transparent",
              border: "none",
              color: "#93C5FD",
              cursor: "pointer",
              padding: 0,
              fontSize: 11,
              fontWeight: 700,
            }}
          >
            {debugOpen ? "Tracking debug (hide)" : "Tracking debug (show)"}
          </button>

          {debugOpen && (
            <div style={{ marginTop: 6 }}>
              <div>job: {String(jobId)} · mode: {mode}</div>
              <div>hook tenant: {hookTenant || "(empty)"}</div>
              <div>
                store: {storeEntries.length} record(s), {matchingEntries.length} for this job
              </div>
              {storeEntries.slice(0, 4).map(([key, t]) => (
                <div key={key} style={{ color: "#9CA3AF" }}>
                  · {key}: job {String((t as any).job_id)} @{" "}
                  {toFiniteNumber((t as any).latitude)?.toFixed(5) ?? "?"},
                  {toFiniteNumber((t as any).longitude)?.toFixed(5) ?? "?"}
                </div>
              ))}
              <div>chosen key: {technicianStoreKey || "(none)"}</div>
              <div>
                point:{" "}
                {storePoint
                  ? `${storePoint.lat.toFixed(6)}, ${storePoint.lng.toFixed(6)}`
                  : "none"}
              </div>
              <div>
                age: {ageSec === null ? "n/a" : `${Math.round(ageSec)} s`} · source:{" "}
                {String(storeSource ?? "n/a")} · store job_id: {String(storeJobId ?? "n/a")}
              </div>
              <div>
                map: {mapReady ? "ready" : "loading"} · tech marker:{" "}
                {technicianMarkerRef.current ? "yes" : "no"} · customer marker:{" "}
                {customerMarkerRef.current ? "yes" : "no"}
              </div>
              <div>
                route:{" "}
                {route
                  ? `${route.route_points?.length ?? 0} pts (${route.provider ?? "?"})`
                  : "none"}
              </div>
              <div
                style={{
                  marginTop: 6,
                  padding: "6px 8px",
                  borderRadius: 6,
                  background: diagnosis.startsWith("OK") ? "#064E3B" : "#7C2D12",
                  color: "#FFFFFF",
                }}
              >
                DIAGNOSIS: {diagnosis}
              </div>
              <div style={{ marginTop: 4, color: "#9CA3AF" }}>
                Console: window.__liveMapDebug
              </div>
            </div>
          )}
        </div>
      )} */}

      {/* ── Status card ───────────────────────────────────────────────────── */}
      <div
        style={{
          position: "absolute",
          left: 16,
          right: 16,
          bottom: 16,
          zIndex: 5,
          background: "rgba(255,255,255,.96)",
          borderRadius: 14,
          padding: "12px 16px",
          boxShadow: "0 4px 20px rgba(0,0,0,.15)",
          display: "flex",
          justifyContent: "space-between",
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div>
          <div
            style={{
              fontSize: 11,
              color: "#64748B",
              textTransform: "uppercase",
              fontWeight: 700,
            }}
          >
            {mode === "technician" ? "To customer" : "Technician"}
          </div>

          <strong style={{ fontSize: 18, color: "#111827" }}>
            {formatDistance(route?.distance_meters ?? null)}
          </strong>

          <span style={{ marginLeft: 10, color: "#475569" }}>
            {formatEta(
              route?.duration_in_traffic_seconds ?? route?.duration_seconds ?? null,
            )}
          </span>
        </div>

        <div style={{ fontSize: 12, color: "#475569", textAlign: "right" }}>
          <div>
            Map: <strong>Ola Maps</strong>
          </div>

          <div>
            Route: <strong>{route?.provider || "waiting"}</strong>
            {route?.cached ? " · cached" : ""}
          </div>

          {mode === "technician" && ownAccuracy !== null && (
            <div>
              GPS accuracy: <strong>{Math.round(ownAccuracy)} m</strong>
            </div>
          )}

          {mode === "customer" && streamedTechnician && (
            <div
              style={{
                marginTop: 4,
                color: isStale ? "#B45309" : "#15803D",
                fontWeight: 600,
              }}
            >
              {freshnessLabel}
            </div>
          )}

          {mode === "customer" && streamedTechnician && streamedAccuracy !== null && (
            <div style={{ marginTop: 4 }}>
              GPS accuracy: <strong>{streamedAccuracy.toFixed(1)} m</strong>
            </div>
          )}

          {gpsError && (
            <div style={{ color: "#B91C1C", marginTop: 4 }}>{gpsError}</div>
          )}

          {!origin && mode === "customer" && (
            <div style={{ color: "#B45309", marginTop: 4 }}>
              Waiting for technician location...
            </div>
          )}
        </div>
      </div>
    </div>
  );
}