import React, { useEffect, useMemo, useRef, useState } from "react";
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
  authToken?: string;
  buildingAddress?: string | null;
};

type Point = { lat: number; lng: number };

type StoredTechnician = {
  latitude?: number | null;
  longitude?: number | null;
  accuracy?: number | null;
  receivedAt?: number;
  ageAtReceipt?: number;
  source?: string;
  job_id?: string | null;
  lastPing?: string;
};

const DEFAULT_CENTER: Point = {
  lat: 13.0827,
  lng: 80.2707,
};

const DEFAULT_ZOOM = 14;

const ROUTE_REFRESH_MS = 15_000;
const ROUTE_MIN_MOVEMENT_METERS = 50;

const LIVE_LOCATION_CLOCK_REFRESH_MS = 5_000;

const LIVE_LABEL_MAX_AGE_S = 10;
const STALE_AFTER_S = 45;

const MIN_ANIMATION_MS = 400;
const MAX_ANIMATION_MS = 3_000;

// -----------------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------------

function toFiniteNumber(value: unknown): number | null {
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
): point is Point {
  return Boolean(
    point &&
      Number.isFinite(point.lat) &&
      Number.isFinite(point.lng) &&
      point.lat >= -90 &&
      point.lat <= 90 &&
      point.lng >= -180 &&
      point.lng <= 180,
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

  return meters >= 1_000
    ? `${(meters / 1_000).toFixed(1)} km`
    : `${Math.round(meters)} m`;
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

  return Math.hypot(
    latMeters,
    lngMeters,
  );
}

function recordTime(
  value: StoredTechnician,
): number {
  const received = Number(
    value.receivedAt,
  );

  if (
    Number.isFinite(received) &&
    received > 0
  ) {
    return received;
  }

  const parsed = Date.parse(
    value.lastPing || "",
  );

  return Number.isFinite(parsed)
    ? parsed
    : 0;
}

function readDebugFlag(): boolean {
  if (
    typeof window ===
    "undefined"
  ) {
    return false;
  }

  try {
    const stored =
      window.localStorage.getItem(
        "trackingDebug",
      );

    if (stored === "0") {
      return false;
    }

    if (stored === "1") {
      return true;
    }

    if (
      new URLSearchParams(
        window.location.search,
      ).has("trackdebug")
    ) {
      return true;
    }
  } catch {
    // Ignore storage errors.
  }

  return Boolean(
    import.meta.env.DEV,
  );
}

const DEBUG_ENABLED =
  readDebugFlag();

function dbg(
  tag: string,
  data?: unknown,
): void {
  if (!DEBUG_ENABLED) {
    return;
  }

  if (data === undefined) {
    console.log(
      `[LIVE MAP] ${tag}`,
    );
  } else {
    console.log(
      `[LIVE MAP] ${tag}`,
      data,
    );
  }
}

// -----------------------------------------------------------------------------
// Marker
// -----------------------------------------------------------------------------

function markerElement(
  label: "C" | "T" | "YOU",
): HTMLDivElement {
  const element =
    document.createElement("div");

  element.setAttribute(
    "aria-label",
    label === "C"
      ? "Customer home location"
      : "Technician location",
  );

  if (label === "C") {
    element.style.width = "46px";
    element.style.height = "46px";
    element.style.display = "flex";
    element.style.alignItems =
      "center";
    element.style.justifyContent =
      "center";
    element.style.boxSizing =
      "border-box";
    element.style.borderRadius =
      "50%";
    element.style.background =
      "#111827";
    element.style.border =
      "3px solid #ffffff";
    element.style.boxShadow =
      "0 4px 14px rgba(0,0,0,0.30)";
    element.style.userSelect =
      "none";

    element.innerHTML = `
      <svg width="25" height="25" viewBox="0 0 24 24" fill="none"
           xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <path d="M3 10.8L12 3L21 10.8"
              stroke="#FFFFFF"
              stroke-width="2.2"
              stroke-linecap="round"
              stroke-linejoin="round" />
        <path d="M5.5 9.5V20H18.5V9.5"
              stroke="#FFFFFF"
              stroke-width="2.2"
              stroke-linecap="round"
              stroke-linejoin="round" />
        <path d="M9.5 20V14H14.5V20"
              stroke="#FFFFFF"
              stroke-width="2.2"
              stroke-linecap="round"
              stroke-linejoin="round" />
      </svg>
    `;

    return element;
  }

  element.style.width = "56px";
  element.style.height = "70px";
  element.style.background =
    "transparent";
  element.style.border = "none";
  element.style.padding = "0";
  element.style.margin = "0";
  element.style.overflow =
    "visible";
  element.style.userSelect =
    "none";

  element.innerHTML = `
    <div style="position: relative; width: 56px; height: 70px;">
      <div style="
        position:absolute;
        top:0;
        left:3px;
        width:45px;
        height:45px;
        background:#ffffff;
        border:2px solid #2c874f;
        border-radius:50% 50% 50% 0;
        transform:rotate(-45deg);
        box-sizing:border-box;
        box-shadow:0 2px 6px rgb(103,221,74);
      "></div>

      <img
        src="/technician_icon.png"
        alt="Technician"
        style="
          position:absolute;
          top:7px;
          left:11px;
          width:34px;
          height:34px;
          object-fit:contain;
          z-index:2;
        "
      />
    </div>
  `;

  return element;
}

// -----------------------------------------------------------------------------
// Component
// -----------------------------------------------------------------------------

export default function JobLiveTrackingMap({
  jobId,
  customerLatitude,
  customerLongitude,
  technicianLatitude: _technicianLatitude,
  technicianLongitude: _technicianLongitude,
  technicianId,
  mode,
  tenantId,
  trackingTenantId,
  authToken,
  buildingAddress,
}: Props) {
  // ---------------------------------------------------------------------------
  // Map refs
  // ---------------------------------------------------------------------------

  const containerRef =
    useRef<HTMLDivElement | null>(
      null,
    );

  const mapRef =
    useRef<any>(null);

  const olaRef =
    useRef<OlaMaps | null>(null);

  const technicianMarkerRef =
    useRef<any>(null);

  const customerMarkerRef =
    useRef<any>(null);

  const markerAnimationRef =
    useRef<number | null>(null);

  const lastMarkerPositionRef =
    useRef<Point | null>(null);

  const lastMoveAtRef =
    useRef(0);

  const hasFittedRef =
    useRef(false);

  const mapReadyRef =
    useRef(false);

  const mapInitializingRef =
    useRef(false);

  const routeSourceId =
    useRef(
      `fieldops-route-${String(
        jobId,
      )}`,
    );

  const routeLayerId =
    useRef(
      `fieldops-route-layer-${String(
        jobId,
      )}`,
    );

  const lastRouteRef =
    useRef<{
      lat: number;
      lng: number;
      at: number;
    } | null>(null);

  // ---------------------------------------------------------------------------
  // Local component state
  // ---------------------------------------------------------------------------

  const [
    ownPosition,
    setOwnPosition,
  ] =
    useState<Point | null>(
      null,
    );

  const [
    ownAccuracy,
    setOwnAccuracy,
  ] =
    useState<number | null>(
      null,
    );

  const [
    gpsError,
    setGpsError,
  ] = useState("");

  const [
    route,
    setRoute,
  ] =
    useState<OlaRouteResponse | null>(
      null,
    );

  const [
    mapError,
    setMapError,
  ] = useState("");

  const [
    mapReady,
    setMapReady,
  ] = useState(false);

  const [now, setNow] =
    useState(() => Date.now());

  const [
    lastKnownTechnician,
    setLastKnownTechnician,
  ] = useState<{
    point: Point;
    accuracy: number | null;
  } | null>(null);

  // ---------------------------------------------------------------------------
  // WebSocket
  // ---------------------------------------------------------------------------
  //
  // Customer tracking:
  //   tenantId          = authenticated customer tenant
  //   trackingTenantId  = actual job/provider tenant
  //
  // The WebSocket hook uses the authenticated JWT as the authorization source
  // and uses trackingTenantId only to construct the authorized job channel.
  //

  const hookTenant =
    trackingTenantId ||
    tenantId;

  const {
    status: trackingStatus,
  } =
    useTrackingWebSocket(
      tenantId,
      String(jobId),
      hookTenant,
      authToken,
    );

  // ---------------------------------------------------------------------------
  // Select ONLY the newest technician record for this job
  // ---------------------------------------------------------------------------

  const technicianStoreKey =
    useTrackingStore(
      (state) => {
        let bestKey = "";
        let bestTime =
          Number.NEGATIVE_INFINITY;

        for (const [
          key,
          value,
        ] of Object.entries(
          state.technicians,
        )) {
          const technician =
            value as StoredTechnician;

          if (
            String(
              technician.job_id ??
                "",
            ) !== String(jobId)
          ) {
            continue;
          }

          const latitude =
            toFiniteNumber(
              technician.latitude,
            );

          const longitude =
            toFiniteNumber(
              technician.longitude,
            );

          if (
            latitude === null ||
            longitude === null ||
            !isValidPoint({
              lat: latitude,
              lng: longitude,
            })
          ) {
            continue;
          }

          const timestamp =
            recordTime(
              technician,
            );

          if (
            timestamp >=
            bestTime
          ) {
            bestKey = key;
            bestTime = timestamp;
          }
        }

        /*
         * Legacy compatibility:
         * only accept the technicianId fallback when the stored record still
         * explicitly belongs to this job. This prevents a technician currently
         * working on another job from appearing on this map.
         */
        if (!bestKey) {
          const fallbackKey =
            technicianId == null
              ? ""
              : String(
                  technicianId,
                );

          const fallback =
            state.technicians[
              fallbackKey
            ] as
              | StoredTechnician
              | undefined;

          if (
            fallback &&
            String(
              fallback.job_id ??
                "",
            ) ===
              String(jobId)
          ) {
            return fallbackKey;
          }
        }

        return bestKey;
      },
    );

  // ---------------------------------------------------------------------------
  // Stable primitive store subscriptions
  // ---------------------------------------------------------------------------

  const storeLatitude =
    useTrackingStore(
      (state) =>
        technicianStoreKey
          ? (
              state
                .technicians[
                technicianStoreKey
              ] as
                | StoredTechnician
                | undefined
            )?.latitude
          : undefined,
    );

  const storeLongitude =
    useTrackingStore(
      (state) =>
        technicianStoreKey
          ? (
              state
                .technicians[
                technicianStoreKey
              ] as
                | StoredTechnician
                | undefined
            )?.longitude
          : undefined,
    );

  const storeAccuracy =
    useTrackingStore(
      (state) =>
        technicianStoreKey
          ? (
              state
                .technicians[
                technicianStoreKey
              ] as
                | StoredTechnician
                | undefined
            )?.accuracy
          : undefined,
    );

  const storeReceivedAt =
    useTrackingStore(
      (state) =>
        technicianStoreKey
          ? (
              state
                .technicians[
                technicianStoreKey
              ] as
                | StoredTechnician
                | undefined
            )?.receivedAt
          : undefined,
    );

  const storeAgeAtReceipt =
    useTrackingStore(
      (state) =>
        technicianStoreKey
          ? (
              state
                .technicians[
                technicianStoreKey
              ] as
                | StoredTechnician
                | undefined
            )?.ageAtReceipt
          : undefined,
    );

  const storeSource =
    useTrackingStore(
      (state) =>
        technicianStoreKey
          ? (
              state
                .technicians[
                technicianStoreKey
              ] as
                | StoredTechnician
                | undefined
            )?.source
          : undefined,
    );

  const storeLastPing =
    useTrackingStore(
      (state) =>
        technicianStoreKey
          ? (
              state
                .technicians[
                technicianStoreKey
              ] as
                | StoredTechnician
                | undefined
            )?.lastPing
          : undefined,
    );

  const allTechnicians =
    useTrackingStore(
      (state) =>
        state.technicians,
    );

  // ---------------------------------------------------------------------------
  // Build current store location
  // ---------------------------------------------------------------------------

  const storePoint =
    useMemo<Point | null>(
      () => {
        const latitude =
          toFiniteNumber(
            storeLatitude,
          );

        const longitude =
          toFiniteNumber(
            storeLongitude,
          );

        const point =
          latitude === null ||
          longitude === null
            ? null
            : {
                lat: latitude,
                lng: longitude,
              };

        return isValidPoint(
          point,
        )
          ? point
          : null;
      },
      [
        storeLatitude,
        storeLongitude,
      ],
    );

  const validStoreAccuracy =
    useMemo(
      () => {
        const accuracy =
          toFiniteNumber(
            storeAccuracy,
          );

        return accuracy !==
          null &&
          accuracy >= 0
          ? accuracy
          : null;
      },
      [storeAccuracy],
    );

  // ---------------------------------------------------------------------------
  // Preserve the last valid technician position as "last known"
  // ---------------------------------------------------------------------------

  useEffect(
    () => {
      if (!storePoint) {
        return;
      }

      setLastKnownTechnician(
        (previous) => {
          if (
            previous?.point.lat ===
              storePoint.lat &&
            previous.point.lng ===
              storePoint.lng &&
            previous.accuracy ===
              validStoreAccuracy
          ) {
            return previous;
          }

          return {
            point: storePoint,
            accuracy:
              validStoreAccuracy,
          };
        },
      );
    },
    [
      storePoint,
      validStoreAccuracy,
    ],
  );

  // ---------------------------------------------------------------------------
  // Customer freshness clock
  // ---------------------------------------------------------------------------

  useEffect(
    () => {
      if (mode !== "customer") {
        return;
      }

      const timer =
        window.setInterval(
          () =>
            setNow(
              Date.now(),
            ),
          LIVE_LOCATION_CLOCK_REFRESH_MS,
        );

      return () =>
        window.clearInterval(
          timer,
        );
    },
    [mode],
  );

  // ---------------------------------------------------------------------------
  // Technician location displayed by the map
  // ---------------------------------------------------------------------------

  const streamedTechnician =
    mode === "customer"
      ? storePoint ??
        lastKnownTechnician?.point ??
        null
      : ownPosition;

  const streamedAccuracy =
    mode === "customer"
      ? storePoint
        ? validStoreAccuracy
        : lastKnownTechnician?.accuracy ??
          null
      : ownAccuracy;

  // ---------------------------------------------------------------------------
  // Freshness calculation
  // ---------------------------------------------------------------------------

  const receivedAtMs =
    toFiniteNumber(
      storeReceivedAt,
    );

  const ageAtReceiptS =
    toFiniteNumber(
      storeAgeAtReceipt,
    ) ?? 0;

  const ageSec =
    receivedAtMs !== null
      ? Math.max(
          0,
          ageAtReceiptS +
            (now -
              receivedAtMs) /
              1000,
        )
      : null;

  const isLocationStale =
    mode === "customer" &&
    streamedTechnician !==
      null &&
    ageSec !== null &&
    ageSec >
      STALE_AFTER_S;

  const hasLiveLocation =
    mode === "customer" &&
    streamedTechnician !==
      null &&
    !isLocationStale;

  const freshnessLabel =
    ageSec === null
      ? "Last known location"
      : ageSec <
          LIVE_LABEL_MAX_AGE_S
        ? "Live"
        : `Last known location · ${Math.round(
            ageSec,
          )} s ago`;

  // ---------------------------------------------------------------------------
  // Map origin/destination
  // ---------------------------------------------------------------------------

  const origin: Point | null =
    mode === "technician"
      ? ownPosition
      : streamedTechnician;

  const destination =
    useMemo<Point | null>(
      () => {
        const latitude =
          toFiniteNumber(
            customerLatitude,
          );

        const longitude =
          toFiniteNumber(
            customerLongitude,
          );

        const point =
          latitude === null ||
          longitude === null
            ? null
            : {
                lat: latitude,
                lng: longitude,
              };

        return isValidPoint(
          point,
        )
          ? point
          : null;
      },
      [
        customerLatitude,
        customerLongitude,
      ],
    );

  // ---------------------------------------------------------------------------
  // Debug state
  // ---------------------------------------------------------------------------

  const storeEntries =
    useMemo(
      () =>
        Object.entries(
          allTechnicians ??
            {},
        ),
      [allTechnicians],
    );

  const matchingEntries =
    useMemo(
      () =>
        storeEntries.filter(
          ([, value]) =>
            String(
              (
                value as StoredTechnician
              ).job_id ??
                "",
            ) ===
            String(jobId),
        ),
      [
        storeEntries,
        jobId,
      ],
    );

  let diagnosis =
    "OK: position received and marker should be visible";

  if (
    mode === "customer"
  ) {
    if (
      storeEntries.length ===
      0
    ) {
      diagnosis =
        "STORE_EMPTY: no technician position has reached the store.";
    } else if (
      matchingEntries.length ===
      0
    ) {
      diagnosis =
        `STORE_HAS_OTHER_JOBS: no store position exists for job ${String(
          jobId,
        )}.`;
    } else if (
      !storePoint &&
      !lastKnownTechnician
    ) {
      diagnosis =
        "BAD_COORDS: the job position contains invalid coordinates.";
    } else if (
      !mapReady
    ) {
      diagnosis =
        "MAP_NOT_READY: position received, waiting for Ola Maps.";
    } else if (
      !technicianMarkerRef.current
    ) {
      diagnosis =
        "MARKER_NOT_CREATED: the map is ready but the technician marker is missing.";
    }
  }

  useEffect(
    () => {
      dbg("hook args", {
        mode,
        jobId: String(jobId),
        tenantId,
        trackingTenantId,
        passedToHook:
          hookTenant,
        hasAuthToken:
          Boolean(
            authToken,
          ),
      });
    },
    [
      mode,
      jobId,
      tenantId,
      trackingTenantId,
      hookTenant,
      authToken,
    ],
  );

  useEffect(
    () => {
      if (
        !DEBUG_ENABLED
      ) {
        return;
      }

      (
        window as any
      ).__liveMapDebug = {
        jobId: String(jobId),
        mode,
        hookArgs: {
          tenantId,
          trackingTenantId,
          passedToHook:
            hookTenant,
        },
        technicianStoreKey,
        storeEntries:
          storeEntries.map(
            ([key, value]) => ({
              key,
              job_id:
                (
                  value as StoredTechnician
                ).job_id,
              lat:
                (
                  value as StoredTechnician
                ).latitude,
              lng:
                (
                  value as StoredTechnician
                ).longitude,
              receivedAt:
                (
                  value as StoredTechnician
                ).receivedAt,
              source:
                (
                  value as StoredTechnician
                ).source,
            }),
          ),
        storePoint,
        origin,
        destination,
        ageSec,
        mapReady,
        trackingStatus,
        route: route
          ? {
              provider:
                route.provider,
              points:
                route
                  .route_points
                  ?.length ??
                0,
              distance_meters:
                route.distance_meters,
            }
          : null,
        diagnosis,
      };
    },
  );

  // ---------------------------------------------------------------------------
  // Technician browser GPS
  // ---------------------------------------------------------------------------

  useEffect(
    () => {
      if (
        mode !==
          "technician" ||
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

        const {
          latitude,
          longitude,
          accuracy,
        } =
          position.coords;

        setGpsError("");

        if (
          !Number.isFinite(
            latitude,
          ) ||
          !Number.isFinite(
            longitude,
          )
        ) {
          return;
        }

        setOwnAccuracy(
          Number.isFinite(
            accuracy,
          )
            ? accuracy
            : null,
        );

        setOwnPosition({
          lat: latitude,
          lng: longitude,
        });
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
            maximumAge: 5_000,
            timeout: 8_000,
          },
        );

      return () => {
        active = false;

        navigator.geolocation.clearWatch(
          watchId,
        );
      };
    },
    [mode],
  );

  // ---------------------------------------------------------------------------
  // Initialize Ola Maps once per job/mode
  // ---------------------------------------------------------------------------

  useEffect(
    () => {
      if (
        !containerRef.current ||
        mapInitializingRef.current ||
        mapReadyRef.current
      ) {
        return;
      }

      const apiKey =
        import.meta.env
          .VITE_OLA_MAPS_API_KEY;

      if (!apiKey) {
        setMapError(
          "VITE_OLA_MAPS_API_KEY is missing.",
        );
        return;
      }

      let cancelled =
        false;

      mapInitializingRef.current =
        true;

      const ola =
        new OlaMaps({
          apiKey,
        });

      olaRef.current =
        ola;

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
                zoom:
                  DEFAULT_ZOOM,
              });

            if (
              cancelled
            ) {
              try {
                map.remove();
              } catch {
                // Ignore cleanup failure.
              }

              return;
            }

            mapRef.current =
              map;

            mapReadyRef.current =
              true;

            mapInitializingRef.current =
              false;

            setMapReady(
              true,
            );

            dbg(
              "map ready",
            );

            try {
              map.addControl(
                ola.addNavigationControls(
                  {
                    showCompass:
                      true,
                  },
                ),
                "top-right",
              );
            } catch (
              error
            ) {
              console.warn(
                "[LIVE MAP] Navigation control error:",
                error,
              );
            }

            if (
              destination
            ) {
              customerMarkerRef.current =
                ola
                  .addMarker(
                    {
                      element:
                        markerElement(
                          "C",
                        ),
                      anchor:
                        "bottom",
                    },
                  )
                  .setLngLat(
                    [
                      destination.lng,
                      destination.lat,
                    ],
                  )
                  .addTo(
                    map,
                  );
            }

            if (
              origin
            ) {
              technicianMarkerRef.current =
                ola
                  .addMarker(
                    {
                      element:
                        markerElement(
                          mode ===
                          "technician"
                            ? "YOU"
                            : "T",
                        ),
                      anchor:
                        "bottom",
                    },
                  )
                  .setLngLat(
                    [
                      origin.lng,
                      origin.lat,
                    ],
                  )
                  .addTo(
                    map,
                  );

              lastMarkerPositionRef.current =
                {
                  ...origin,
                };

              lastMoveAtRef.current =
                performance.now();
            }

            if (
              !origin &&
              destination
            ) {
              try {
                map.flyTo(
                  {
                    center: [
                      destination.lng,
                      destination.lat,
                    ],
                    zoom:
                      DEFAULT_ZOOM,
                    essential:
                      true,
                  },
                );
              } catch {
                // Ignore camera errors.
              }
            }
          } catch (
            error
          ) {
            if (
              !cancelled
            ) {
              console.error(
                "[LIVE MAP] Ola Maps initialization error:",
                error,
              );

              setMapError(
                error instanceof
                  Error
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
        cancelled =
          true;

        if (
          markerAnimationRef.current !==
          null
        ) {
          cancelAnimationFrame(
            markerAnimationRef.current,
          );

          markerAnimationRef.current =
            null;
        }

        try {
          technicianMarkerRef.current?.remove();
        } catch {
          // Ignore marker cleanup errors.
        }

        try {
          customerMarkerRef.current?.remove();
        } catch {
          // Ignore marker cleanup errors.
        }

        try {
          mapRef.current?.remove();
        } catch {
          // Ignore map cleanup errors.
        }

        technicianMarkerRef.current =
          null;

        customerMarkerRef.current =
          null;

        mapRef.current =
          null;

        olaRef.current =
          null;

        mapReadyRef.current =
          false;

        mapInitializingRef.current =
          false;

        lastMarkerPositionRef.current =
          null;

        lastMoveAtRef.current =
          0;

        hasFittedRef.current =
          false;

        lastRouteRef.current =
          null;

        setMapReady(
          false,
        );
      };
    },
    // Position updates must never recreate the map.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [jobId, mode],
  );

  // ---------------------------------------------------------------------------
  // Customer marker
  // ---------------------------------------------------------------------------

  useEffect(
    () => {
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
        } catch (
          error
        ) {
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
            .addMarker(
              {
                element:
                  markerElement(
                    "C",
                  ),
                anchor:
                  "bottom",
              },
            )
            .setLngLat(
              [
                destination.lng,
                destination.lat,
              ],
            )
            .addTo(
              map,
            );
      } catch (
        error
      ) {
        console.error(
          "[LIVE MAP] Unable to create customer marker:",
          error,
        );
      }
    },
    [
      mapReady,
      destination?.lat,
      destination?.lng,
    ],
  );

  // ---------------------------------------------------------------------------
  // Technician marker
  // ---------------------------------------------------------------------------

  useEffect(
    () => {
      if (
        !origin ||
        !isValidPoint(
          origin,
        )
      ) {
        return;
      }

      const target: [
        number,
        number,
      ] = [
        origin.lng,
        origin.lat,
      ];

      if (
        technicianMarkerRef.current
      ) {
        try {
          const marker =
            technicianMarkerRef.current;

          if (
            markerAnimationRef.current !==
            null
          ) {
            cancelAnimationFrame(
              markerAnimationRef.current,
            );

            markerAnimationRef.current =
              null;
          }

          const current =
            marker.getLngLat?.();

          const candidateStart: Point =
            current
              ? {
                  lat: Number(
                    current.lat,
                  ),
                  lng: Number(
                    current.lng,
                  ),
                }
              : lastMarkerPositionRef.current ??
                origin;

          const start =
            isValidPoint(
              candidateStart,
            )
              ? candidateStart
              : origin;

          if (
            start.lat ===
              origin.lat &&
            start.lng ===
              origin.lng
          ) {
            marker.setLngLat(
              target,
            );

            lastMarkerPositionRef.current =
              {
                ...origin,
              };

            return;
          }

          const currentTime =
            performance.now();

          const gap =
            lastMoveAtRef.current >
            0
              ? currentTime -
                lastMoveAtRef.current
              : 1_000;

          lastMoveAtRef.current =
            currentTime;

          const durationMs =
            Math.min(
              Math.max(
                gap,
                MIN_ANIMATION_MS,
              ),
              MAX_ANIMATION_MS,
            );

          let animationStart:
            | number
            | null = null;

          const step = (
            timestamp: number,
          ) => {
            if (
              animationStart ===
              null
            ) {
              animationStart =
                timestamp;
            }

            const progress =
              Math.min(
                (timestamp -
                  animationStart) /
                  durationMs,
                1,
              );

            marker.setLngLat(
              [
                start.lng +
                  (origin.lng -
                    start.lng) *
                    progress,
                start.lat +
                  (origin.lat -
                    start.lat) *
                    progress,
              ],
            );

            if (
              progress <
              1
            ) {
              markerAnimationRef.current =
                requestAnimationFrame(
                  step,
                );
            } else {
              marker.setLngLat(
                target,
              );

              lastMarkerPositionRef.current =
                {
                  ...origin,
                };

              markerAnimationRef.current =
                null;
            }
          };

          markerAnimationRef.current =
            requestAnimationFrame(
              step,
            );
        } catch (
          error
        ) {
          console.warn(
            "[LIVE MAP] Failed to move technician marker:",
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
        dbg(
          "map not ready; technician marker will be created when it is",
        );

        return;
      }

      try {
        technicianMarkerRef.current =
          ola
            .addMarker(
              {
                element:
                  markerElement(
                    mode ===
                    "technician"
                      ? "YOU"
                      : "T",
                  ),
                anchor:
                  "bottom",
              },
            )
            .setLngLat(
              target,
            )
            .addTo(
              map,
            );

        lastMarkerPositionRef.current =
          {
            ...origin,
          };

        lastMoveAtRef.current =
          performance.now();
      } catch (
        error
      ) {
        console.error(
          "[LIVE MAP] Unable to create technician marker:",
          error,
        );
      }
    },
    [
      mapReady,
      mode,
      origin?.lat,
      origin?.lng,
    ],
  );

  // ---------------------------------------------------------------------------
  // Fit technician + customer once
  // ---------------------------------------------------------------------------

  useEffect(
    () => {
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
        const minLng =
          Math.min(
            origin.lng,
            destination.lng,
          );

        const minLat =
          Math.min(
            origin.lat,
            destination.lat,
          );

        const maxLng =
          Math.max(
            origin.lng,
            destination.lng,
          );

        const maxLat =
          Math.max(
            origin.lat,
            destination.lat,
          );

        mapRef.current.fitBounds(
          [
            [
              minLng,
              minLat,
            ],
            [
              maxLng,
              maxLat,
            ],
          ],
          {
            padding: 90,
            maxZoom: 16,
            duration: 600,
          },
        );

        hasFittedRef.current =
          true;
      } catch (
        error
      ) {
        console.warn(
          "[LIVE MAP] fitBounds failed:",
          error,
        );
      }
    },
    [
      mapReady,
      origin?.lat,
      origin?.lng,
      destination?.lat,
      destination?.lng,
    ],
  );

  // ---------------------------------------------------------------------------
  // Route calculation
  // ---------------------------------------------------------------------------

  useEffect(
    () => {
      if (
        !origin ||
        !destination ||
        !isValidPoint(
          origin,
        ) ||
        !isValidPoint(
          destination,
        )
      ) {
        setRoute(
          null,
        );

        return;
      }

      const previous =
        lastRouteRef.current;

      const nowMs =
        Date.now();

      if (previous) {
        const movedMeters =
          distanceBetweenPoints(
            origin,
            previous,
          );

        const elapsed =
          nowMs -
          previous.at;

        if (
          elapsed <
            ROUTE_REFRESH_MS &&
          movedMeters <
            ROUTE_MIN_MOVEMENT_METERS
        ) {
          return;
        }
      }

      lastRouteRef.current =
        {
          ...origin,
          at: nowMs,
        };

      let cancelled =
        false;

      const calculateRoute =
        async () => {
          try {
            const result =
              await getOlaRoute(
                {
                  originLat:
                    origin.lat,
                  originLng:
                    origin.lng,
                  destinationLat:
                    destination.lat,
                  destinationLng:
                    destination.lng,
                },
              );

            if (
              !cancelled
            ) {
              setRoute(
                result,
              );

              dbg(
                "route received",
                {
                  points:
                    result
                      ?.route_points
                      ?.length ??
                    0,
                  distance_meters:
                    result?.distance_meters,
                },
              );
            }
          } catch (
            error
          ) {
            if (
              !cancelled
            ) {
              console.error(
                "[LIVE MAP] Ola route error:",
                error,
              );
            }
          }
        };

      void calculateRoute();

      return () => {
        cancelled =
          true;
      };
    },
    [
      origin?.lat,
      origin?.lng,
      destination?.lat,
      destination?.lng,
    ],
  );

  // ---------------------------------------------------------------------------
  // Draw/update route line
  // ---------------------------------------------------------------------------

  useEffect(
    () => {
      const map =
        mapRef.current;

      const points =
        route?.route_points;

      if (
        !map ||
        !points ||
        points.length <
          2
      ) {
        return;
      }

      const sourceId =
        routeSourceId.current;

      const layerId =
        routeLayerId.current;

      const geojson = {
        type: "Feature" as const,
        properties: {},
        geometry: {
          type: "LineString" as const,
          coordinates:
            points,
        },
      };

      let cancelled =
        false;

      let retryTimer:
        | number
        | null = null;

      const drawRoute =
        () => {
          if (
            cancelled
          ) {
            return;
          }

          const currentMap =
            mapRef.current;

          if (
            !currentMap
          ) {
            return;
          }

          try {
            if (
              typeof currentMap.isStyleLoaded ===
                "function" &&
              !currentMap.isStyleLoaded()
            ) {
              currentMap.once?.(
                "load",
                () => {
                  if (
                    !cancelled
                  ) {
                    drawRoute();
                  }
                },
              );

              return;
            }

            const source =
              currentMap.getSource?.(
                sourceId,
              );

            if (source) {
              source.setData(
                geojson,
              );
            } else {
              currentMap.addSource(
                sourceId,
                {
                  type: "geojson",
                  data: geojson,
                },
              );
            }

            if (
              !currentMap.getLayer?.(
                layerId,
              )
            ) {
              currentMap.addLayer(
                {
                  id: layerId,
                  type: "line",
                  source: sourceId,
                  layout: {
                    "line-join":
                      "round",
                    "line-cap":
                      "round",
                  },
                  paint: {
                    "line-color":
                      "#2563EB",
                    "line-width":
                      6,
                    "line-opacity":
                      0.95,
                  },
                },
              );
            }
          } catch (
            error
          ) {
            console.error(
              "[LIVE MAP] Unable to draw route:",
              error,
            );

            retryTimer =
              window.setTimeout(
                drawRoute,
                300,
              );
          }
        };

      drawRoute();

      return () => {
        cancelled =
          true;

        if (
          retryTimer !==
          null
        ) {
          window.clearTimeout(
            retryTimer,
          );
        }
      };
    },
    [
      mapReady,
      route,
    ],
  );

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  const displayAddress =
    buildingAddress
      ?.trim() ||
    "";

  return (
    <div
      data-testid={`job-live-tracking-map-${jobId}`}
      style={{
        position:
          "relative",
        width: "100%",
        height: 560,
        borderRadius: 14,
        overflow:
          "hidden",
        background:
          "#E5E7EB",
      }}
    >
      <div
        ref={
          containerRef
        }
        style={{
          width: "100%",
          height: "100%",
        }}
      />

      {displayAddress && (
        <div
          style={{
            position:
              "absolute",
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
              marginBottom:
                4,
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

      {mapError && (
        <div
          role="alert"
          style={{
            position:
              "absolute",
            left: 16,
            right: 16,
            top:
              displayAddress
                ? 100
                : 16,
            padding: 12,
            background:
              "#FEF2F2",
            color:
              "#991B1B",
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

      <div
        style={{
          position:
            "absolute",
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
          display:
            "flex",
          justifyContent:
            "space-between",
          gap: 16,
          flexWrap:
            "wrap",
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
              color:
                "#475569",
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
            color:
              "#475569",
            textAlign:
              "right",
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
                  color:
                    hasLiveLocation
                      ? "#15803D"
                      : "#B45309",
                  fontWeight:
                    600,
                }}
              >
                {freshnessLabel}:{" "}
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

          {mode ===
            "customer" &&
            streamedTechnician &&
            streamedAccuracy !==
              null && (
              <div
                style={{
                  marginTop: 4,
                }}
              >
                GPS accuracy:{" "}
                <strong>
                  {streamedAccuracy.toFixed(
                    1,
                  )}{" "}
                  m
                </strong>
              </div>
            )}

          {mode ===
            "customer" &&
            isLocationStale && (
              <div
                style={{
                  marginTop: 4,
                  color:
                    "#B45309",
                }}
              >
                Technician GPS is stale.
                Showing the last known location.
              </div>
            )}

          {mode ===
            "customer" && (
            <div
              style={{
                marginTop: 4,
                fontWeight:
                  600,
                color:
                  trackingStatus ===
                  "connected"
                    ? "#15803D"
                    : trackingStatus ===
                        "reconnecting"
                      ? "#B45309"
                      : "#B91C1C",
              }}
            >
              Tracking:{" "}
              {trackingStatus ===
              "connected"
                ? "Connected"
                : trackingStatus ===
                    "reconnecting"
                  ? "Reconnecting..."
                  : "Disconnected"}
            </div>
          )}

          {gpsError && (
            <div
              style={{
                color:
                  "#B91C1C",
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
                  color:
                    "#B45309",
                  marginTop: 4,
                }}
              >
                Waiting for technician location...
              </div>
            )}
        </div>
      </div>
    </div>
  );
}