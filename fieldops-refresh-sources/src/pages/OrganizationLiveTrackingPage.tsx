import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { OlaMaps } from "olamaps-web-sdk";
import {
  MapPin,
  RefreshCw,
  Search,
  Users,
  Wifi,
  WifiOff,
} from "lucide-react";

import { getAllTechnicians } from "../services/technicianService";
import { useTrackingWebSocket } from "../hooks/useTrackingWebSocket";
import { useTrackingStore } from "../store/trackingStore";

type RawTechnician = {
  technician_id?: number | string;
  tech_id?: string;
  id?: number | string;
  technician_name?: string;
  name?: string;
  technician_status?: string;
  status?: string;
  technician_skill?: string;
  latitude?: number | string | null;
  longitude?: number | string | null;
  last_ping?: string | null;
  phone?: string;
  technician_phone?: string;
};

type TrackingTechnician = {
  id: string;
  name: string;
  status: string;
  lastPing: string | null;
  latitude: number | null;
  longitude: number | null;
  online: boolean;
  skill: string;
  phone: string;
};

type Filter = "ALL" | "ONLINE" | "OFFLINE";

const DEFAULT_CENTER: [number, number] = [80.2707, 13.0827];
const ONLINE_WINDOW_MS = 120_000;

function numberOrNull(value: unknown): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function validCoordinates(
  latitude: number | null,
  longitude: number | null,
): boolean {
  return (
    latitude !== null &&
    longitude !== null &&
    latitude >= -90 &&
    latitude <= 90 &&
    longitude >= -180 &&
    longitude <= 180 &&
    !(latitude === 0 && longitude === 0)
  );
}

function timestampMs(value?: string | null): number {
  if (!value) return Number.NaN;

  let normalized = value.trim();

  if (
    normalized.includes("T") &&
    !normalized.endsWith("Z") &&
    !/[+-]\d{2}:\d{2}$/.test(normalized)
  ) {
    normalized += "Z";
  }

  return Date.parse(normalized);
}

function formatLastSeen(value: string | null, now: number): string {
  const time = timestampMs(value);

  if (!Number.isFinite(time)) return "No heartbeat received";

  const seconds = Math.max(0, Math.floor((now - time) / 1000));

  if (seconds < 60) return `Last seen ${seconds}s ago`;

  const minutes = Math.floor(seconds / 60);

  if (minutes < 60) return `Last seen ${minutes}m ago`;

  return `Last seen ${Math.floor(minutes / 60)}h ago`;
}

export default function OrganizationLiveTrackingPage() {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const olaRef = useRef<any>(null);

  const markersRef = useRef<
    Map<string, { marker: any; element: HTMLButtonElement }>
  >(new Map());

  const hasAutoFitRef = useRef(false);

  const [rawTechnicians, setRawTechnicians] = useState<RawTechnician[]>([]);
  const [filter, setFilter] = useState<Filter>("ALL");
  const [searchText, setSearchText] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [mapReady, setMapReady] = useState(false);
  const [mapError, setMapError] = useState("");
  const [now, setNow] = useState(Date.now());

  const storeTechnicians = useTrackingStore((state) => state.technicians);
  const updateTechnicianLocation = useTrackingStore(
    (state) => state.updateTechnicianLocation,
  );
  const connectionStatus = useTrackingStore(
    (state) => state.connectionStatus,
  );

  // The authenticated JWT determines the organization for tracking.
  const { reconnect } = useTrackingWebSocket("");

  const fetchTechnicians = useCallback(async () => {
    try {
      setRefreshing(true);
      setLoadError("");

      const response = await getAllTechnicians({
        page: 1,
        limit: 100,
      });

      const payload = response?.data;

      const list: RawTechnician[] = Array.isArray(payload)
        ? payload
        : Array.isArray(payload?.technicians)
          ? payload.technicians
          : Array.isArray(payload?.data)
            ? payload.data
            : [];

      setRawTechnicians(list);

      // Seed the live store with saved coordinates when available.
      // Do not invent coordinates for technicians without a GPS fix.
      list.forEach((tech) => {
        const id = String(
          tech.technician_id ?? tech.tech_id ?? tech.id ?? "",
        );

        if (!id) return;

        const latitude = numberOrNull(tech.latitude);
        const longitude = numberOrNull(tech.longitude);

        if (!validCoordinates(latitude, longitude)) return;

        updateTechnicianLocation(id, {
          id,
          name: tech.technician_name || tech.name || `Technician ${id}`,
          latitude: latitude as number,
          longitude: longitude as number,
          status:
            tech.technician_status ||
            tech.status ||
            "NO_ACTIVE_JOBS",
          lastPing: tech.last_ping || undefined,
          phone: tech.phone || tech.technician_phone || null,
          jobType: tech.technician_skill || null,
        });
      });
    } catch (error) {
      console.error("Failed to load organization technicians:", error);
      setLoadError(
        "Unable to load technicians. Check the backend connection and try refreshing.",
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [updateTechnicianLocation]);

  // Initial load and automatic refresh.
  useEffect(() => {
    void fetchTechnicians();

    const fetchTimer = window.setInterval(() => {
      void fetchTechnicians();
    }, 15_000);

    const clockTimer = window.setInterval(() => {
      setNow(Date.now());
    }, 10_000);

    return () => {
      window.clearInterval(fetchTimer);
      window.clearInterval(clockTimer);
    };
  }, [fetchTechnicians]);

  const technicians = useMemo<TrackingTechnician[]>(() => {
    return rawTechnicians.map((tech) => {
      const ids = [
        tech.technician_id,
        tech.tech_id,
        tech.id,
      ]
        .filter((value) => value !== null && value !== undefined)
        .map(String);

      // GPS WebSocket messages may use the database technician ID,
      // while older tracking data may use tech_id.
      const liveCandidates = ids
        .map((id) => storeTechnicians[id])
        .filter(Boolean);

      const live = liveCandidates.sort((a, b) => {
        return (
          timestampMs(b.lastPing) - timestampMs(a.lastPing)
        );
      })[0];

      const apiLastPing = tech.last_ping || null;
      const liveLastPing = live?.lastPing || null;

      const useLiveFix =
        !!live &&
        live.latitude != null &&
        live.longitude != null &&
        (
          !apiLastPing ||
          timestampMs(liveLastPing) >= timestampMs(apiLastPing)
        );

      const latitude = useLiveFix
        ? numberOrNull(live?.latitude)
        : numberOrNull(tech.latitude);

      const longitude = useLiveFix
        ? numberOrNull(live?.longitude)
        : numberOrNull(tech.longitude);

      const lastPing = useLiveFix
        ? liveLastPing || apiLastPing
        : apiLastPing || liveLastPing;

      const pingTime = timestampMs(lastPing);

      const online =
        Number.isFinite(pingTime) &&
        now >= pingTime - 30_000 &&
        now - pingTime <= ONLINE_WINDOW_MS;

      const id = String(
        tech.technician_id ?? tech.tech_id ?? tech.id ?? "",
      );

      return {
        id,
        name:
          live?.name ||
          tech.technician_name ||
          tech.name ||
          `Technician ${id}`,
        status:
          live?.status ||
          tech.technician_status ||
          tech.status ||
          "Unknown",
        lastPing,
        latitude,
        longitude,
        online,
        skill: tech.technician_skill || "",
        phone:
          tech.phone ||
          tech.technician_phone ||
          live?.phone ||
          "",
      };
    });
  }, [rawTechnicians, storeTechnicians, now]);

  const filteredTechnicians = useMemo(() => {
    const query = searchText.trim().toLowerCase();

    return technicians.filter((tech) => {
      if (filter === "ONLINE" && !tech.online) return false;
      if (filter === "OFFLINE" && tech.online) return false;

      if (
        query &&
        !tech.name.toLowerCase().includes(query) &&
        !tech.skill.toLowerCase().includes(query)
      ) {
        return false;
      }

      return true;
    });
  }, [technicians, filter, searchText]);

  // Initialize Ola Maps.
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const apiKey = import.meta.env.VITE_OLA_MAPS_API_KEY;

    if (!apiKey) {
      setMapError("VITE_OLA_MAPS_API_KEY is missing from your frontend environment.");
      return;
    }

    let cancelled = false;

    const initialize = async () => {
      try {
        const ola = new OlaMaps({ apiKey });
        olaRef.current = ola;

        const map = await ola.init({
          style:
            "https://api.olamaps.io/tiles/vector/v1/styles/default-light-standard/style.json",
          container: mapContainerRef.current,
          center: DEFAULT_CENTER,
          zoom: 11,
        });

        if (cancelled) {
          map.remove();
          return;
        }

        mapRef.current = map;
        setMapReady(true);

        try {
          map.addControl(
            ola.addNavigationControls({ showCompass: true }),
            "top-right",
          );
        } catch (error) {
          console.warn("Could not add Ola Maps navigation controls:", error);
        }
      } catch (error) {
        console.error("Failed to initialize Ola Maps:", error);

        setMapError(
          error instanceof Error
            ? error.message
            : "Unable to initialize Ola Maps.",
        );
      }
    };

    void initialize();

    return () => {
      cancelled = true;

      markersRef.current.forEach(({ marker }) => {
        try {
          marker.remove();
        } catch {
          // Ignore marker cleanup errors.
        }
      });

      markersRef.current.clear();

      try {
        mapRef.current?.remove();
      } catch {
        // Ignore map cleanup errors.
      }

      mapRef.current = null;
      olaRef.current = null;
    };
  }, []);

  // Keep technician markers synchronized with API and live GPS updates.
  useEffect(() => {
    const map = mapRef.current;
    const ola = olaRef.current;

    if (!mapReady || !map || !ola) return;

    const withCoordinates = filteredTechnicians.filter((tech) =>
      validCoordinates(tech.latitude, tech.longitude),
    );

    const wantedIds = new Set(withCoordinates.map((tech) => tech.id));

    // Remove markers no longer included in the current organization/filter.
    markersRef.current.forEach(({ marker }, id) => {
      if (!wantedIds.has(id)) {
        marker.remove();
        markersRef.current.delete(id);
      }
    });

    withCoordinates.forEach((tech) => {
      const latitude = tech.latitude as number;
      const longitude = tech.longitude as number;

      let entry = markersRef.current.get(tech.id);

      if (!entry) {
        const element = document.createElement("button");
        element.type = "button";
        element.title = tech.name;
        element.style.cssText = `
          border: 0;
          background: transparent;
          padding: 0;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 4px;
          cursor: pointer;
          white-space: nowrap;
          font-family: Inter, sans-serif;
        `;

        const dot = document.createElement("span");
        dot.dataset.role = "status-dot";
        dot.style.cssText = `
          width: 34px;
          height: 34px;
          border: 3px solid white;
          border-radius: 50%;
          display: grid;
          place-items: center;
          color: white;
          font-size: 12px;
          font-weight: 800;
          box-shadow: 0 2px 8px rgba(15,23,42,.3);
        `;

        const label = document.createElement("span");
        label.dataset.role = "label";
        label.style.cssText = `
          padding: 3px 7px;
          border-radius: 6px;
          color: #1F2937;
          background: rgba(255,255,255,.96);
          border: 1px solid #DDE7E1;
          font-size: 11px;
          font-weight: 700;
          box-shadow: 0 1px 4px rgba(15,23,42,.12);
        `;

        element.append(dot, label);

        element.onclick = () => {
          setSelectedId(tech.id);
          map.flyTo({
            center: [longitude, latitude],
            zoom: 15,
            essential: true,
          });
        };

        const marker = ola
          .addMarker({ element, anchor: "bottom" })
          .setLngLat([longitude, latitude])
          .addTo(map);

        entry = { marker, element };
        markersRef.current.set(tech.id, entry);
      } else {
        entry.marker.setLngLat([longitude, latitude]);

        entry.element.onclick = () => {
          setSelectedId(tech.id);
          map.flyTo({
            center: [longitude, latitude],
            zoom: 15,
            essential: true,
          });
        };
      }

      const dot = entry.element.querySelector<HTMLElement>(
        '[data-role="status-dot"]',
      );

      const label = entry.element.querySelector<HTMLElement>(
        '[data-role="label"]',
      );

      const initials = tech.name
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0].toUpperCase())
        .join("");

      if (dot) {
        dot.style.background = tech.online ? "#059669" : "#64748B";
        dot.textContent = initials || "?";
      }

      if (label) {
        label.textContent = `${tech.name} · ${tech.online ? "Online" : "Offline"}`;
      }

      entry.element.title =
        `${tech.name} — ${tech.online ? "Online" : "Offline"}\n` +
        formatLastSeen(tech.lastPing, now);
    });

    // Fit the map to the known technician locations on its first data load.
    if (withCoordinates.length > 0 && !hasAutoFitRef.current) {
      hasAutoFitRef.current = true;

      if (withCoordinates.length === 1) {
        const tech = withCoordinates[0];

        map.flyTo({
          center: [
            tech.longitude as number,
            tech.latitude as number,
          ],
          zoom: 14,
        });
      } else {
        const longitudes = withCoordinates.map(
          (tech) => tech.longitude as number,
        );
        const latitudes = withCoordinates.map(
          (tech) => tech.latitude as number,
        );

        map.fitBounds(
          [
            [Math.min(...longitudes), Math.min(...latitudes)],
            [Math.max(...longitudes), Math.max(...latitudes)],
          ],
          { padding: 90, maxZoom: 14 },
        );
      }
    }
  }, [mapReady, filteredTechnicians, now]);

  const selectedTechnician =
    technicians.find((tech) => tech.id === selectedId) || null;

  const onlineCount = technicians.filter((tech) => tech.online).length;
  const offlineCount = technicians.length - onlineCount;

  const buttonStyle = (active: boolean): React.CSSProperties => ({
    border: active ? "1px solid #15803D" : "1px solid #DCE7E1",
    borderRadius: 9,
    padding: "8px 12px",
    color: active ? "#FFFFFF" : "#475569",
    background: active ? "#15803D" : "#FFFFFF",
    fontWeight: 700,
    fontSize: 12,
    cursor: "pointer",
  });

  return (
    <div
      style={{
        position: "relative",
        height: "100%",
        minHeight: 0,
        width: "100%",
        overflow: "hidden",
        background: "#EEF4F1",
        fontFamily: "Inter, sans-serif",
      }}
    >
      <div
        ref={mapContainerRef}
        style={{
          position: "absolute",
          inset: 0,
        }}
      />

      {/* Search and status filters */}
      <div
        style={{
          position: "absolute",
          zIndex: 5,
          top: 14,
          left: 14,
          right: 350,
          display: "flex",
          alignItems: "center",
          gap: 8,
          flexWrap: "wrap",
          padding: 12,
          background: "rgba(255,255,255,.97)",
          border: "1px solid #DCE7E1",
          borderRadius: 12,
          boxShadow: "0 3px 12px rgba(15,23,42,.1)",
        }}
      >
        <strong
          style={{
            fontSize: 14,
            color: "#1F2937",
            marginRight: 8,
          }}
        >
          Live Technician Tracking
        </strong>

        {(["ALL", "ONLINE", "OFFLINE"] as Filter[]).map((value) => (
          <button
            key={value}
            type="button"
            style={buttonStyle(filter === value)}
            onClick={() => setFilter(value)}
          >
            {value === "ALL" ? "All" : value === "ONLINE" ? "Online" : "Offline"}
          </button>
        ))}

        <div
          style={{
            flex: "1 1 180px",
            minWidth: 150,
            display: "flex",
            alignItems: "center",
            gap: 6,
            border: "1px solid #DCE7E1",
            borderRadius: 9,
            padding: "7px 10px",
            background: "#FFFFFF",
          }}
        >
          <Search size={15} color="#94A3B8" />

          <input
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
            placeholder="Search technician..."
            aria-label="Search technician"
            style={{
              border: 0,
              outline: 0,
              flex: 1,
              width: "100%",
              fontSize: 12,
              background: "transparent",
            }}
          />
        </div>

        <button
          type="button"
          onClick={() => void fetchTechnicians()}
          title="Refresh technicians"
          style={buttonStyle(false)}
          disabled={refreshing}
        >
          <RefreshCw
            size={14}
            style={{ verticalAlign: "middle", marginRight: 5 }}
          />
          {refreshing ? "Refreshing" : "Refresh"}
        </button>
      </div>

      {/* Organization technician list */}
      <div
        style={{
          position: "absolute",
          zIndex: 5,
          top: 88,
          right: 14,
          width: 320,
          maxWidth: "calc(100% - 28px)",
          maxHeight: "calc(100% - 112px)",
          overflowY: "auto",
          background: "rgba(255,255,255,.97)",
          border: "1px solid #DCE7E1",
          borderRadius: 12,
          boxShadow: "0 3px 12px rgba(15,23,42,.12)",
        }}
      >
        <div
          style={{
            padding: 14,
            borderBottom: "1px solid #E5ECE8",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 8,
            }}
          >
            <strong style={{ fontSize: 13, color: "#1F2937" }}>
              Organization Technicians
            </strong>

            <span
              style={{
                background: "#ECFDF5",
                color: "#047857",
                padding: "4px 7px",
                borderRadius: 7,
                fontSize: 11,
                fontWeight: 800,
              }}
            >
              {technicians.length}
            </span>
          </div>

          <div
            style={{
              display: "flex",
              gap: 12,
              marginTop: 10,
              fontSize: 11,
              fontWeight: 700,
            }}
          >
            <span style={{ color: "#047857" }}>
              ● {onlineCount} Online
            </span>
            <span style={{ color: "#64748B" }}>
              ● {offlineCount} Offline
            </span>
          </div>
        </div>

        {loading && technicians.length === 0 && (
          <p style={{ padding: 14, fontSize: 12, color: "#64748B" }}>
            Loading organization technicians...
          </p>
        )}

        {loadError && (
          <div
            role="alert"
            style={{ padding: 14, color: "#B91C1C", fontSize: 12 }}
          >
            {loadError}
            <button
              type="button"
              onClick={() => void fetchTechnicians()}
              style={{ display: "block", marginTop: 8 }}
            >
              Try again
            </button>
          </div>
        )}

        {!loading && !loadError && filteredTechnicians.length === 0 && (
          <p style={{ padding: 14, fontSize: 12, color: "#64748B" }}>
            No technicians match the selected filter.
          </p>
        )}

        {filteredTechnicians.map((tech) => (
          <button
            type="button"
            key={tech.id}
            onClick={() => {
              setSelectedId(tech.id);

              if (validCoordinates(tech.latitude, tech.longitude)) {
                mapRef.current?.flyTo({
                  center: [
                    tech.longitude as number,
                    tech.latitude as number,
                  ],
                  zoom: 15,
                  essential: true,
                });
              }
            }}
            style={{
              width: "100%",
              display: "flex",
              alignItems: "flex-start",
              gap: 10,
              padding: 13,
              textAlign: "left",
              border: 0,
              borderBottom: "1px solid #EDF2EF",
              background: selectedId === tech.id ? "#F0FDF4" : "#FFFFFF",
              cursor: "pointer",
            }}
          >
            <span
              style={{
                width: 10,
                height: 10,
                flexShrink: 0,
                marginTop: 4,
                borderRadius: "50%",
                background: tech.online ? "#059669" : "#64748B",
              }}
            />

            <span style={{ flex: 1, minWidth: 0 }}>
              <strong
                style={{
                  display: "block",
                  color: "#1F2937",
                  fontSize: 12,
                }}
              >
                {tech.name}
              </strong>

              <span
                style={{
                  display: "block",
                  marginTop: 4,
                  fontSize: 11,
                  color: tech.online ? "#047857" : "#64748B",
                  fontWeight: 700,
                }}
              >
                {tech.online ? "Online" : "Offline"}
              </span>

              <span
                style={{
                  display: "block",
                  marginTop: 4,
                  fontSize: 10,
                  color: "#64748B",
                }}
              >
                {validCoordinates(tech.latitude, tech.longitude)
                  ? `${tech.latitude!.toFixed(5)}, ${tech.longitude!.toFixed(5)}`
                  : "No GPS location received"}
              </span>

              <span
                style={{
                  display: "block",
                  marginTop: 4,
                  fontSize: 10,
                  color: "#94A3B8",
                }}
              >
                {formatLastSeen(tech.lastPing, now)}
              </span>

              {tech.skill && (
                <span
                  style={{
                    display: "block",
                    marginTop: 4,
                    fontSize: 10,
                    color: "#64748B",
                  }}
                >
                  {tech.skill}
                </span>
              )}
            </span>
          </button>
        ))}
      </div>

      {/* Selected technician details */}
      {selectedTechnician && (
        <div
          style={{
            position: "absolute",
            zIndex: 5,
            left: 14,
            bottom: 14,
            maxWidth: "calc(100% - 370px)",
            padding: "12px 14px",
            background: "#FFFFFF",
            border: "1px solid #DCE7E1",
            borderRadius: 10,
            boxShadow: "0 3px 12px rgba(15,23,42,.12)",
            fontSize: 12,
          }}
        >
          <button
            type="button"
            aria-label="Close technician details"
            onClick={() => setSelectedId(null)}
            style={{
              float: "right",
              border: 0,
              background: "transparent",
              cursor: "pointer",
              color: "#64748B",
              marginLeft: 15,
            }}
          >
            ×
          </button>

          <strong>{selectedTechnician.name}</strong>

          <div
            style={{
              marginTop: 5,
              color: selectedTechnician.online ? "#047857" : "#64748B",
              fontWeight: 700,
            }}
          >
            {selectedTechnician.online ? (
              <Wifi size={13} style={{ verticalAlign: "middle", marginRight: 5 }} />
            ) : (
              <WifiOff size={13} style={{ verticalAlign: "middle", marginRight: 5 }} />
            )}

            {selectedTechnician.online ? "Online" : "Offline"}
          </div>

          <div style={{ marginTop: 5, color: "#64748B" }}>
            {selectedTechnician.phone || "No phone number available"}
          </div>
        </div>
      )}

      {/* Map and connection status */}
      <div
        style={{
          position: "absolute",
          zIndex: 5,
          left: 14,
          bottom: selectedTechnician ? 110 : 14,
          display: "flex",
          alignItems: "center",
          gap: 7,
          background: "#FFFFFF",
          border: "1px solid #DCE7E1",
          borderRadius: 9,
          padding: "8px 11px",
          fontSize: 11,
          fontWeight: 700,
          color: "#475569",
        }}
      >
        <MapPin size={14} color="#059669" />
        <Users size={14} />
        {filteredTechnicians.length} technicians shown
        <span
          style={{
            marginLeft: 5,
            color: connectionStatus === "connected" ? "#047857" : "#B45309",
          }}
        >
          {connectionStatus === "connected" ? "Live connected" : "Connecting"}
        </span>

        <button
          type="button"
          onClick={reconnect}
          title="Reconnect live tracking"
          style={{
            border: 0,
            background: "transparent",
            cursor: "pointer",
            color: "#64748B",
          }}
        >
          <RefreshCw size={13} />
        </button>
      </div>

      {mapError && (
        <div
          role="alert"
          style={{
            position: "absolute",
            zIndex: 10,
            top: "45%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            padding: 20,
            maxWidth: 440,
            background: "#FFFFFF",
            border: "1px solid #FECACA",
            borderRadius: 12,
            color: "#B91C1C",
            fontSize: 13,
            boxShadow: "0 4px 16px rgba(15,23,42,.15)",
          }}
        >
          {mapError}
        </div>
      )}
    </div>
  );
}