import React, {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { OlaMaps } from "olamaps-web-sdk";

import { useTrackingStore } from "../../store/trackingStore";
import { useTrackingWebSocket } from "../../hooks/useTrackingWebSocket";

import {
  getOlaRoute,
  type OlaRouteResponse,
} from "../../services/olaMapService";

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

type Point = {
  lat: number;
  lng: number;
};

const DEFAULT_CENTER: Point = {
  lat: 13.0827,
  lng: 80.2707,
};

const DEFAULT_ZOOM = 14;

const ROUTE_REFRESH_MS = 15_000;

const ROUTE_MIN_MOVEMENT_METERS = 50;

function toFiniteNumber(
  value: unknown,
): number | null {
  if (
    value === null ||
    value === undefined ||
    value === ""
  ) {
    return null;
  }

  const parsed = Number(value);

  return Number.isFinite(parsed)
    ? parsed
    : null;
}

function isValidPoint(
  point: Point | null,
): boolean {
  if (!point) {
    return false;
  }

  return (
    Number.isFinite(point.lat) &&
    Number.isFinite(point.lng) &&
    point.lat >= -90 &&
    point.lat <= 90 &&
    point.lng >= -180 &&
    point.lng <= 180
  );
}

function formatDistance(
  meters: number | null,
): string {
  if (
    meters === null ||
    !Number.isFinite(meters)
  ) {
    return "Calculating...";
  }

  if (meters >= 1000) {
    return `${(meters / 1000).toFixed(1)} km`;
  }

  return `${Math.round(meters)} m`;
}

function formatEta(
  seconds: number | null,
): string {
  if (
    seconds === null ||
    !Number.isFinite(seconds)
  ) {
    return "Calculating...";
  }

  return `${Math.max(
    1,
    Math.round(seconds / 60),
  )} min`;
}

/**
 * Custom Ola Maps marker.
 *
 * C   = Customer
 * T   = Technician
 * YOU = Technician's own map
 */
function markerElement(
  label: string,
  background: string,
): HTMLDivElement {
  const element =
    document.createElement("div");

  const isCustomer =
    label === "C";

  element.setAttribute(
    "aria-label",
    isCustomer
      ? "Customer home location"
      : "Technician location",
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
    element.style.background =
      background;
    element.style.border =
      "3px solid #ffffff";
    element.style.boxShadow =
      "0 4px 14px rgba(0,0,0,0.30)";

    element.innerHTML = `
      <svg
        width="25"
        height="25"
        viewBox="0 0 24 24"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        <path
          d="M3 10.8L12 3L21 10.8"
          stroke="#FFFFFF"
          stroke-width="2.2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />

        <path
          d="M5.5 9.5V20H18.5V9.5"
          stroke="#FFFFFF"
          stroke-width="2.2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />

        <path
          d="M9.5 20V14H14.5V20"
          stroke="#FFFFFF"
          stroke-width="2.2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    `;
  } else {
    element.style.width = "56px";
    element.style.height = "70px";
    element.style.background =
      "transparent";
    element.style.border = "none";
    element.style.boxShadow = "none";
    element.style.padding = "0";
    element.style.margin = "0";
    element.style.overflow = "visible";
    element.style.pointerEvents = "auto";
    element.style.userSelect = "none";

    element.innerHTML = `
      <div
        style="
          position: relative;
          width: 56px;
          height: 70px;
        "
      >

        <div
          style="
            position: absolute;
            top: 0;
            left: 3px;
            width: 45px;
            height: 45px;
            background: #ffffff;
            border: 2px solid #2c874f;
            border-radius: 50% 50% 50% 0;
            transform: rotate(-45deg);
            box-sizing: border-box;
            box-shadow: 0 2px 6px rgb(103, 221, 74);
          "
        ></div>

        <img
          src="/technician_icon.png"
          alt="Technician"
          style="
            position: absolute;
            top: 7px;
            left: 11px;
            width: 34px;
            height: 34px;
            object-fit: contain;
            z-index: 2;
          "
        />

      </div>
    `;
  }

  return element;
}

function distanceBetweenPoints(
  a: Point,
  b: Point,
): number {
  const latMeters =
    (a.lat - b.lat) * 111_000;

  const lngMeters =
    (a.lng - b.lng) *
    111_000 *
    Math.cos(
      (a.lat * Math.PI) / 180,
    );

  return Math.sqrt(
    latMeters * latMeters +
      lngMeters * lngMeters,
  );
}

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
  // =========================================================
  // MAP REFS
  // =========================================================

  const containerRef =
    useRef<HTMLDivElement | null>(null);

  const mapRef =
    useRef<any>(null);

  const olaRef =
    useRef<OlaMaps | null>(null);

  const technicianMarkerRef =
    useRef<any>(null);

  const customerMarkerRef =
    useRef<any>(null);

  const routeSourceId =
    useRef(
      `fieldops-route-${String(jobId)}`,
    );

  const routeLayerId =
    useRef(
      `fieldops-route-layer-${String(jobId)}`,
    );

  const lastRouteRef =
    useRef<{
      lat: number;
      lng: number;
      at: number;
    } | null>(null);

  const lastMarkerPositionRef =
    useRef<Point | null>(null);

  const markerAnimationRef =
    useRef<number | null>(null);

  const mapReadyRef =
    useRef(false);

  const mapInitializingRef =
    useRef(false);

  // =========================================================
  // CONNECT WEBSOCKET
  // =========================================================

  useTrackingWebSocket(
    tenantId,
    String(jobId),
    trackingTenantId || tenantId,
  );

  // =========================================================
  // IMPORTANT FIX
  //
  // DO NOT SELECT THE WHOLE TECHNICIAN OBJECT.
  //
  // Read latitude and longitude separately.
  //
  // This ensures that when the store changes the
  // coordinates, the map gets a new value.
  // =========================================================

  const technicianStoreKey =
    useTrackingStore((state) => {
      let matchedKey = "";
      let matchedTimestamp = Number.NEGATIVE_INFINITY;

      for (const [key, technician] of Object.entries(state.technicians)) {
        if (String(technician.job_id ?? "") !== String(jobId)) {
          continue;
        }

        const latitude = toFiniteNumber(technician.latitude);
        const longitude = toFiniteNumber(technician.longitude);
        if (
          latitude === null ||
          longitude === null ||
          !isValidPoint({ lat: latitude, lng: longitude })
        ) {
          continue;
        }

        const timestamp = Date.parse(technician.lastPing || "");
        const comparableTimestamp = Number.isFinite(timestamp)
          ? timestamp
          : 0;
        if (comparableTimestamp >= matchedTimestamp) {
          matchedKey = key;
          matchedTimestamp = comparableTimestamp;
        }
      }

      return matchedKey || (technicianId != null ? String(technicianId) : "");
    });

  const storeTechnicianLatitude =
    useTrackingStore((state) =>
      technicianStoreKey
        ? state.technicians[
            technicianStoreKey
          ]?.latitude
        : undefined,
    );

  const storeTechnicianLongitude =
    useTrackingStore((state) =>
      technicianStoreKey
        ? state.technicians[
            technicianStoreKey
          ]?.longitude
        : undefined,
    );

  const storeTechnicianAccuracy =
    useTrackingStore((state) =>
      technicianStoreKey
        ? state.technicians[
            technicianStoreKey
          ]?.accuracy
        : undefined,
    );

  // =========================================================
  // TECHNICIAN OWN GPS
  // Only used when mode === "technician"
  // =========================================================

  const [ownPosition, setOwnPosition] =
    useState<Point | null>(null);

  const [ownAccuracy, setOwnAccuracy] =
    useState<number | null>(null);

  const [gpsError, setGpsError] =
    useState("");

  // =========================================================
  // ROUTE
  // =========================================================

  const [route, setRoute] =
    useState<OlaRouteResponse | null>(null);

  const [mapError, setMapError] =
    useState("");

  const [mapReady, setMapReady] = useState(false);


  // =========================================================
  // BUILD LIVE TECHNICIAN LOCATION
  //
  // Priority:
  //
  // 1. WebSocket/store
  // 2. Props fallback
  // =========================================================

  const storePoint =
    useMemo<Point | null>(() => {
      const lat = toFiniteNumber(storeTechnicianLatitude);
      const lng = toFiniteNumber(storeTechnicianLongitude);
      const point = lat === null || lng === null
        ? null
        : { lat, lng };
      return isValidPoint(point) ? point : null;
    }, [storeTechnicianLatitude, storeTechnicianLongitude]);

  const propPoint =
    useMemo<Point | null>(() => {
      const lat = toFiniteNumber(technicianLatitude);
      const lng = toFiniteNumber(technicianLongitude);
      const point = lat === null || lng === null
        ? null
        : { lat, lng };
      return isValidPoint(point) ? point : null;
    }, [technicianLatitude, technicianLongitude]);

  const [lastKnownTechnician, setLastKnownTechnician] =
    useState<{ point: Point; accuracy: number | null } | null>(null);

  const validAccuracy =
    typeof storeTechnicianAccuracy === "number" &&
    Number.isFinite(storeTechnicianAccuracy) &&
    storeTechnicianAccuracy >= 0
      ? storeTechnicianAccuracy
      : null;

  useEffect(() => {
    if (storePoint) {
      setLastKnownTechnician((previous) => {
        if (
          previous?.point.lat === storePoint.lat &&
          previous?.point.lng === storePoint.lng &&
          previous?.accuracy === validAccuracy
        ) {
          return previous;
        }

        return {
          point: storePoint,
          accuracy: validAccuracy,
        };
      });
    } else if (propPoint) {
      setLastKnownTechnician((previous) => previous ?? {
        point: propPoint,
        accuracy: null,
      });
    }
  }, [storePoint, validAccuracy, propPoint]);

  const streamedTechnician =
    storePoint ?? lastKnownTechnician?.point ?? propPoint;

  const streamedAccuracy =
    storePoint
      ? validAccuracy
      : lastKnownTechnician?.accuracy ?? null;

  // =========================================================
  // DEBUG LIVE LOCATION
  // =========================================================

  useEffect(() => {
    if (
      mode !== "customer"
    ) {
      return;
    }

    if (!streamedTechnician) {
      console.log(
        "[LIVE MAP] Waiting for technician location...",
      );

      return;
    }

    console.log(
      "========================================",
    );

    console.log(
      "[LIVE MAP] TECHNICIAN LOCATION RECEIVED",
    );

    console.log(
      "[LIVE MAP] Technician ID:",
      technicianId,
    );

    console.log(
      "[LIVE MAP] Latitude:",
      streamedTechnician.lat,
    );

    console.log(
      "[LIVE MAP] Longitude:",
      streamedTechnician.lng,
    );

    console.log(
      "========================================",
    );
  }, [
    streamedTechnician?.lat,
    streamedTechnician?.lng,
    mode,
    technicianId,
  ]);

  // =========================================================
  // ROUTE ORIGIN
  //
  // CUSTOMER:
  //     WebSocket/store technician location
  //
  // TECHNICIAN:
  //     own browser GPS
  // =========================================================

  const origin =
    mode === "technician"
      ? ownPosition
      : streamedTechnician;

  // =========================================================
  // CUSTOMER LOCATION
  // =========================================================

  const destination =
    useMemo<Point | null>(() => {
      const lat =
        toFiniteNumber(
          customerLatitude,
        );

      const lng =
        toFiniteNumber(
          customerLongitude,
        );

      if (
        lat === null ||
        lng === null
      ) {
        return null;
      }

      if (
        lat < -90 ||
        lat > 90 ||
        lng < -180 ||
        lng > 180
      ) {
        return null;
      }

      return {
        lat,
        lng,
      };
    }, [
      customerLatitude,
      customerLongitude,
    ]);

  // =========================================================
  // TECHNICIAN BROWSER GPS
  // =========================================================

  useEffect(() => {
    if (
      mode !== "technician" ||
      !navigator.geolocation
    ) {
      return;
    }

    let active = true;

    const handleSuccess = (
      position: GeolocationPosition,
    ) => {
      if (!active) {
        return;
      }

      const latitude =
        position.coords.latitude;

      const longitude =
        position.coords.longitude;

      const accuracy =
        position.coords.accuracy;

      setGpsError("");

      setOwnAccuracy(
        accuracy,
      );

      if (
        Number.isFinite(latitude) &&
        Number.isFinite(longitude)
      ) {
        setOwnPosition({
          lat: latitude,
          lng: longitude,
        });
      }
    };

    const handleError = (
      error: GeolocationPositionError,
    ) => {
      if (!active) {
        return;
      }

      console.warn(
        "[LIVE MAP] Geolocation error:",
        error,
      );

      setGpsError(
        "Unable to get your current location. Please allow location access.",
      );
    };

    const watchId =
      navigator.geolocation.watchPosition(
        handleSuccess,
        handleError,
        {
          enableHighAccuracy: true,
          maximumAge: 3000,
          timeout: 20000,
        },
      );

    return () => {
      active = false;

      navigator.geolocation.clearWatch(
        watchId,
      );
    };
  }, [mode]);

  // =========================================================
  // INITIALIZE OLA MAP
  //
  // IMPORTANT:
  // The map itself is created only once.
  // =========================================================

  useEffect(() => {
    if (
      !containerRef.current ||
      mapInitializingRef.current ||
      mapReadyRef.current
    ) {
      return;
    }

    let cancelled = false;

    const apiKey =
      import.meta.env
        .VITE_OLA_MAPS_API_KEY;

    if (!apiKey) {
      setMapError(
        "VITE_OLA_MAPS_API_KEY is missing.",
      );

      return;
    }

    mapInitializingRef.current =
      true;

    const ola =
      new OlaMaps({
        apiKey,
      });

    olaRef.current = ola;

    const initialCenter =
      origin ??
      destination ??
      DEFAULT_CENTER;

    const initializeMap =
      async () => {
        try {
          const map =
            await ola.init({
              style:
                "https://api.olamaps.io/tiles/vector/v1/styles/default-light-standard/style.json",

              container:
                containerRef.current,

              center: [
                initialCenter.lng,
                initialCenter.lat,
              ],

              zoom: DEFAULT_ZOOM,
            });

          if (cancelled) {
            return;
          }

          mapRef.current = map;

          mapReadyRef.current =
            true;
          setMapReady(true);

          mapInitializingRef.current =
            false;

          // -------------------------------------------------
          // NAVIGATION CONTROLS
          // -------------------------------------------------

          try {
            map.addControl(
              ola.addNavigationControls({
                showCompass: true,
              }),
              "top-right",
            );
          } catch (error) {
            console.warn(
              "[LIVE MAP] Navigation control error:",
              error,
            );
          }

          // -------------------------------------------------
          // CUSTOMER MARKER
          // -------------------------------------------------

          if (destination) {
            customerMarkerRef.current =
              ola
                .addMarker({
                  element:
                    markerElement(
                      "C",
                      "#111827",
                    ),

                  anchor:
                    "bottom",
                })
                .setLngLat([
                  destination.lng,
                  destination.lat,
                ])
                .addTo(map);
          }

          // -------------------------------------------------
          // TECHNICIAN MARKER
          // -------------------------------------------------

          if (origin) {
            technicianMarkerRef.current =
              ola
                .addMarker({
                  element:
                    markerElement(
                      mode ===
                        "technician"
                        ? "YOU"
                        : "T",

                      "#2563EB",
                    ),

                  anchor:
                    "bottom",
                })
                .setLngLat([
                  origin.lng,
                  origin.lat,
                ])
                .addTo(map);

            lastMarkerPositionRef.current =
              {
                ...origin,
              };
          }

          // -------------------------------------------------
          // CUSTOMER ONLY + NO TECH LOCATION
          // -------------------------------------------------

          if (
            !origin &&
            destination
          ) {
            try {
              map.flyTo({
                center: [
                  destination.lng,
                  destination.lat,
                ],

                zoom: DEFAULT_ZOOM,

                essential: true,
              });
            } catch {
              // Ignore animation errors.
            }
          }
        } catch (error) {
          if (!cancelled) {
            console.error(
              "[LIVE MAP] Ola Maps initialization error:",
              error,
            );

            setMapError(
              error instanceof Error
                ? error.message
                : "Unable to load Ola Maps.",
            );
          }

          mapInitializingRef.current =
            false;
        }
      };

    void initializeMap();

    return () => {
      cancelled = true;

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

      if (markerAnimationRef.current !== null) {
        cancelAnimationFrame(markerAnimationRef.current);
        markerAnimationRef.current = null;
      }

      technicianMarkerRef.current =
        null;

      customerMarkerRef.current =
        null;

      mapRef.current = null;

      olaRef.current = null;

      mapReadyRef.current =
        false;
      setMapReady(false);

      mapInitializingRef.current =
        false;

      lastMarkerPositionRef.current =
        null;
    };

    // Do NOT recreate map for GPS changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, mode]);

  // =========================================================
  // UPDATE CUSTOMER MARKER
  // =========================================================

  useEffect(() => {
    if (
      !mapReadyRef.current ||
      !destination
    ) {
      return;
    }

    if (
      customerMarkerRef.current
    ) {
      try {
        customerMarkerRef.current.setLngLat(
          [
            destination.lng,
            destination.lat,
          ],
        );
      } catch (error) {
        console.warn(
          "[LIVE MAP] Unable to update customer marker:",
          error,
        );
      }

      return;
    }

    const ola =
      olaRef.current;

    const map =
      mapRef.current;

    if (!ola || !map) {
      return;
    }

    try {
      customerMarkerRef.current =
        ola
          .addMarker({
            element:
              markerElement(
                "C",
                "#111827",
              ),

            anchor:
              "bottom",
          })
          .setLngLat([
            destination.lng,
            destination.lat,
          ])
          .addTo(map);
    } catch (error) {
      console.error(
        "[LIVE MAP] Unable to create customer marker:",
        error,
      );
    }
  }, [
    destination?.lat,
    destination?.lng,
  ]);

  // =========================================================
  // UPDATE TECHNICIAN MARKER
  //
  // THIS IS THE IMPORTANT PART.
  //
  // Every time the WebSocket/store gives us a new
  // latitude or longitude, this effect runs.
  // =========================================================

  useEffect(() => {
    if (
      !origin ||
      !isValidPoint(origin)
    ) {
      return;
    }

    const lngLat: [
      number,
      number,
    ] = [
      origin.lng,
      origin.lat,
    ];

    console.log(
      "========================================",
    );

    console.log(
      "[LIVE MAP] MOVING TECHNICIAN MARKER",
    );

    console.log(
      "[LIVE MAP] Latitude:",
      origin.lat,
    );

    console.log(
      "[LIVE MAP] Longitude:",
      origin.lng,
    );

    console.log(
      "========================================",
    );

    // -------------------------------------------------------
    // MARKER EXISTS
    // -------------------------------------------------------

    if (
      technicianMarkerRef.current
    ) {
      try {
        const marker = technicianMarkerRef.current;

        if (markerAnimationRef.current !== null) {
          cancelAnimationFrame(markerAnimationRef.current);
          markerAnimationRef.current = null;
        }

        const currentLngLat = marker.getLngLat?.();
        const start = currentLngLat
          ? {
              lat: Number(currentLngLat.lat),
              lng: Number(currentLngLat.lng),
            }
          : lastMarkerPositionRef.current ?? origin;

        if (
          !isValidPoint(start) ||
          (start.lat === origin.lat && start.lng === origin.lng)
        ) {
          marker.setLngLat(lngLat);
          lastMarkerPositionRef.current = { ...origin };
          return;
        }

        const durationMs = 300;
        let animationStart: number | null = null;
        const animateToRealFix = (timestamp: number) => {
          if (animationStart === null) animationStart = timestamp;
          const progress = Math.min((timestamp - animationStart) / durationMs, 1);
          const animatedLatitude = start.lat + (origin.lat - start.lat) * progress;
          const animatedLongitude = start.lng + (origin.lng - start.lng) * progress;
          marker.setLngLat([animatedLongitude, animatedLatitude]);

          if (progress < 1) {
            markerAnimationRef.current = requestAnimationFrame(animateToRealFix);
          } else {
            marker.setLngLat(lngLat);
            lastMarkerPositionRef.current = { ...origin };
            markerAnimationRef.current = null;
          }
        };

        markerAnimationRef.current = requestAnimationFrame(animateToRealFix);

        console.log(
          "[LIVE MAP] ✅ MARKER MOVED",
        );
      } catch (error) {
        console.warn(
          "[LIVE MAP] Failed to move technician marker:",
          error,
        );
      }

      return;
    }

    // -------------------------------------------------------
    // CREATE MARKER IF IT DOES NOT EXIST
    // -------------------------------------------------------

    const ola =
      olaRef.current;

    const map =
      mapRef.current;

    if (!ola || !map) {
      console.warn(
        "[LIVE MAP] Map not ready; technician marker will be created later.",
      );

      return;
    }

    try {
      technicianMarkerRef.current =
        ola
          .addMarker({
            element:
              markerElement(
                "T",
                "#2563EB",
              ),

            anchor:
              "bottom",
          })
          .setLngLat(
            lngLat,
          )
          .addTo(map);

      lastMarkerPositionRef.current =
        {
          ...origin,
        };

      console.log(
        "[LIVE MAP] ✅ TECHNICIAN MARKER CREATED",
      );
    } catch (error) {
      console.error(
        "[LIVE MAP] Unable to create technician marker:",
        error,
      );
    }
  }, [
    mapReady,
    mode,
    origin?.lat,
    origin?.lng,
  ]);

  // =========================================================
  // ROUTE CALCULATION
  // =========================================================

  useEffect(() => {
    if (
      !origin ||
      !destination ||
      !isValidPoint(origin) ||
      !isValidPoint(destination)
    ) {
      setRoute(null);

      return;
    }

    const previous =
      lastRouteRef.current;

    const now =
      Date.now();

    if (previous) {
      const movedMeters =
        distanceBetweenPoints(
          origin,
          previous,
        );

      const timeSinceLastRequest =
        now -
        previous.at;

      if (
        timeSinceLastRequest <
          ROUTE_REFRESH_MS &&
        movedMeters <
          ROUTE_MIN_MOVEMENT_METERS
      ) {
        return;
      }
    }

    lastRouteRef.current = {
      ...origin,
      at: now,
    };

    let cancelled = false;

    const calculateRoute =
      async () => {
        try {
          const result =
            await getOlaRoute({
              originLat:
                origin.lat,

              originLng:
                origin.lng,

              destinationLat:
                destination.lat,

              destinationLng:
                destination.lng,
            });

          if (!cancelled) {
            setRoute(result);
          }
        } catch (error) {
          if (!cancelled) {
            console.error(
              "[LIVE MAP] Ola route error:",
              error,
            );
          }
        }
      };

    void calculateRoute();

    return () => {
      cancelled = true;
    };
  }, [
    origin?.lat,
    origin?.lng,
    destination?.lat,
    destination?.lng,
  ]);

  // =========================================================
  // DRAW / UPDATE ROUTE
  // =========================================================

 // =========================================================
// DRAW / UPDATE ROUTE
// =========================================================

useEffect(() => {
  const map = mapRef.current;

  if (
    !map ||
    !route ||
    !route.route_points ||
    route.route_points.length < 2
  ) {
    return;
  }

  const sourceId = routeSourceId.current;
  const layerId = routeLayerId.current;

  // ---------------------------------------------------------
  // IMPORTANT:
  // Ola Maps requires sources/layers to be added after
  // the map style has finished loading.
  // ---------------------------------------------------------

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
    if (cancelled) {
      return;
    }

    const currentMap = mapRef.current;

    if (!currentMap) {
      return;
    }

    try {
      // -----------------------------------------------------
      // MAP STYLE NOT READY
      // -----------------------------------------------------
      //
      // Wait for Ola Maps "load" event.
      // This is especially important on the customer page
      // because the technician location may already exist
      // when the modal opens.
      //
      if (
        typeof currentMap.isStyleLoaded === "function" &&
        !currentMap.isStyleLoaded()
      ) {
        console.log(
          "[LIVE MAP] Map style not ready. Waiting for load event..."
        );

        const handleMapLoad = () => {
          if (!cancelled) {
            console.log(
              "[LIVE MAP] Map loaded. Drawing route..."
            );

            drawRoute();
          }
        };

        currentMap.once?.("load", handleMapLoad);

        return;
      }

      // -----------------------------------------------------
      // CHECK IF SOURCE ALREADY EXISTS
      // -----------------------------------------------------

      const existingSource =
        currentMap.getSource?.(sourceId);

      if (existingSource) {
        try {
          existingSource.setData(geojson);

          console.log(
            "[LIVE MAP] Route source updated."
          );

          return;
        } catch (error) {
          console.warn(
            "[LIVE MAP] Existing route source could not be updated:",
            error
          );
        }
      }

      // -----------------------------------------------------
      // ADD ROUTE SOURCE
      // -----------------------------------------------------

      currentMap.addSource(sourceId, {
        type: "geojson",
        data: geojson,
      });

      console.log(
        "[LIVE MAP] Route source added:",
        sourceId
      );

      // -----------------------------------------------------
      // ADD ROUTE LAYER
      // -----------------------------------------------------

      if (!currentMap.getLayer?.(layerId)) {
        currentMap.addLayer({
          id: layerId,
          type: "line",
          source: sourceId,

          layout: {
            "line-join": "round",
            "line-cap": "round",
          },

          paint: {
            "line-color": "#2563EB",
            "line-width": 6,
            "line-opacity": 0.95,
          },
        });

        console.log(
          "[LIVE MAP] ✅ BLUE ROUTE DRAWN:",
          route.route_points.length,
          "points"
        );
      }

    } catch (error) {
      console.error(
        "[LIVE MAP] ❌ Unable to draw route:",
        error
      );

      // -----------------------------------------------------
      // RETRY
      // -----------------------------------------------------
      //
      // If the style became ready between checks, retry
      // shortly instead of permanently losing the route.
      //
      window.setTimeout(() => {
        if (!cancelled) {
          drawRoute();
        }
      }, 300);
    }
  };

  drawRoute();

  return () => {
    cancelled = true;
  };

}, [
  mapReady,
  route,
]);

  // =========================================================
  // DISPLAY ADDRESS
  // =========================================================

  const displayAddress =
    buildingAddress?.trim() ||
    "";

  // =========================================================
  // RENDER
  // =========================================================

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
      {/* ===================================================
          MAP
      =================================================== */}

      <div
        ref={containerRef}
        style={{
          width: "100%",
          height: "100%",
        }}
      />

      {/* ===================================================
          SERVICE ADDRESS
      =================================================== */}

      {displayAddress && (
        <div
          style={{
            position: "absolute",
            top: 16,
            left: 16,
            right: 16,
            zIndex: 5,
            maxWidth: 520,
            background:
              "rgba(255,255,255,.97)",
            borderRadius: 12,
            padding:
              "12px 16px",
            boxShadow:
              "0 4px 18px rgba(0,0,0,.16)",
          }}
        >
          <div
            style={{
              fontSize: 11,
              color: "#64748B",
              fontWeight: 800,
              textTransform:
                "uppercase",
              marginBottom: 4,
            }}
          >
            Service Location
          </div>

          <div
            style={{
              fontSize: 14,
              color: "#1F2937",
              fontWeight: 600,
              lineHeight: 1.4,
            }}
          >
            {displayAddress}
          </div>
        </div>
      )}

      {/* ===================================================
          MAP ERROR
      =================================================== */}

      {mapError && (
        <div
          style={{
            position: "absolute",
            left: 16,
            right: 16,
            top: displayAddress
              ? 100
              : 16,
            padding: 12,
            background:
              "#FEF2F2",
            color: "#991B1B",
            border:
              "1px solid #FECACA",
            borderRadius: 10,
            zIndex: 10,
            fontSize: 13,
          }}
        >
          {mapError}
        </div>
      )}

      {/* ===================================================
          STATUS CARD
      =================================================== */}

      <div
        style={{
          position: "absolute",
          left: 16,
          right: 16,
          bottom: 16,
          zIndex: 5,
          background:
            "rgba(255,255,255,.96)",
          borderRadius: 14,
          padding:
            "12px 16px",
          boxShadow:
            "0 4px 20px rgba(0,0,0,.15)",
          display: "flex",
          justifyContent:
            "space-between",
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div>
          <div
            style={{
              fontSize: 11,
              color: "#64748B",
              textTransform:
                "uppercase",
              fontWeight: 700,
            }}
          >
            {mode ===
            "technician"
              ? "To customer"
              : "Technician"}
          </div>

          <strong
            style={{
              fontSize: 18,
              color: "#111827",
            }}
          >
            {formatDistance(
              route?.distance_meters ??
                null,
            )}
          </strong>

          <span
            style={{
              marginLeft: 10,
              color: "#475569",
            }}
          >
            {formatEta(
              route?.duration_in_traffic_seconds ??
                route?.duration_seconds ??
                null,
            )}
          </span>
        </div>

        <div
          style={{
            fontSize: 12,
            color: "#475569",
            textAlign: "right",
          }}
        >
          <div>
            Map:{" "}
            <strong>
              Ola Maps
            </strong>
          </div>

          <div>
            Route:{" "}
            <strong>
              {route?.provider ||
                "waiting"}
            </strong>

            {route?.cached
              ? " · cached"
              : ""}
          </div>

          {mode ===
            "technician" &&
            ownAccuracy !==
              null && (
              <div>
                GPS accuracy:{" "}
                <strong>
                  {Math.round(
                    ownAccuracy,
                  )}{" "}
                  m
                </strong>
              </div>
            )}

          {mode ===
            "customer" &&
            streamedTechnician && (
              <div
                style={{
                  marginTop: 4,
                  color: "#15803D",
                }}
              >
                Live GPS:{" "}
                <strong>
                  {streamedTechnician.lat.toFixed(
                    6,
                  )}
                  ,{" "}
                  {streamedTechnician.lng.toFixed(
                    6,
                  )}
                </strong>
              </div>
            )}

          {mode === "customer" && streamedAccuracy !== null && (
            <div style={{ marginTop: 4 }}>
              GPS accuracy: <strong>{streamedAccuracy.toFixed(1)} m</strong>
            </div>
          )}

          {gpsError && (
            <div
              style={{
                color: "#B91C1C",
                marginTop: 4,
              }}
            >
              {gpsError}
            </div>
          )}

          {!origin &&
            mode ===
              "customer" && (
              <div
                style={{
                  color: "#B45309",
                  marginTop: 4,
                }}
              >
                Waiting for
                technician
                location...
              </div>
            )}
        </div>
      </div>
    </div>
  );
}
