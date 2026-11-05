import React, { useCallback, useEffect, useRef, useState, useMemo } from "react";
import { OlaMaps } from "olamaps-web-sdk";
import { MapContainer, TileLayer, Marker, useMap, useMapEvents } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import api from "../../services/api";

const defaultCenter = { lat: 13.0827, lng: 80.2707 };
const OLA_STYLE = "https://api.olamaps.io/tiles/vector/v1/styles/default-light-standard/style.json";

interface Props {
  latitude: number | null;
  longitude: number | null;
  onChange: (latitude: number, longitude: number, address?: string) => void;
}

// Clean Emerald Vector Pin for Leaflet Fallback
const customLeafletPinIcon = L.divIcon({
  className: "custom-map-pin",
  html: `
    <div style="
      position: relative;
      width: 36px;
      height: 36px;
      display: flex;
      align-items: center;
      justify-content: center;
    ">
      <div style="
        width: 30px;
        height: 30px;
        background: #059669;
        border: 2.5px solid #FFFFFF;
        border-radius: 50% 50% 50% 0;
        transform: rotate(-45deg);
        box-shadow: 0 4px 12px rgba(5, 150, 105, 0.45);
        display: flex;
        align-items: center;
        justify-content: center;
      ">
        <div style="
          width: 9px;
          height: 9px;
          background: #FFFFFF;
          border-radius: 50%;
        "></div>
      </div>
    </div>
  `,
  iconSize: [36, 36],
  iconAnchor: [18, 34],
});

function createOlaPinElement(): HTMLElement {
  const el = document.createElement("div");
  el.className = "custom-ola-pin";
  el.style.width = "36px";
  el.style.height = "36px";
  el.style.display = "flex";
  el.style.alignItems = "center";
  el.style.justifyContent = "center";
  el.style.cursor = "grab";
  el.innerHTML = `
    <div style="
      width: 32px;
      height: 32px;
      background: #059669;
      border: 2.5px solid #FFFFFF;
      border-radius: 50% 50% 50% 0;
      transform: rotate(-45deg);
      box-shadow: 0 4px 14px rgba(5, 150, 105, 0.5);
      display: flex;
      align-items: center;
      justify-content: center;
      transition: transform 0.15s ease;
    ">
      <div style="
        width: 9px;
        height: 9px;
        background: #FFFFFF;
        border-radius: 50%;
      "></div>
    </div>
  `;
  return el;
}

function MapClickHandler({ onSelect }: { onSelect: (lat: number, lng: number) => void }) {
  useMapEvents({
    click(e) {
      onSelect(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

function RecenterMap({ lat, lng }: { lat: number; lng: number }) {
  const map = useMap();
  useEffect(() => {
    map.setView([lat, lng], map.getZoom());
  }, [lat, lng, map]);
  return null;
}

export default function LocationPickerMap({ latitude, longitude, onChange }: Props) {
  const pos = useMemo(() => {
    if (latitude != null && longitude != null && !isNaN(latitude) && !isNaN(longitude)) {
      return { lat: latitude, lng: longitude };
    }
    return defaultCenter;
  }, [latitude, longitude]);

  const [markerPos, setMarkerPos] = useState<{ lat: number; lng: number }>(pos);
  const [addressLoading, setAddressLoading] = useState(false);
  const [useFallback, setUseFallback] = useState(false);
  const [olaLoaded, setOlaLoaded] = useState(false);

  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const olaMapRef = useRef<any>(null);
  const olaMarkerRef = useRef<any>(null);
  const disposedRef = useRef<boolean>(false);

  useEffect(() => {
    setMarkerPos(pos);
  }, [pos]);

  const selectLocation = useCallback(
    async (lat: number, lng: number) => {
      setMarkerPos({ lat, lng });
      setAddressLoading(true);
      try {
        const response = await api.get("/organizations/reverse-location", {
          params: { latitude: lat, longitude: lng },
        });
        const resolvedAddr = response.data?.verified
          ? response.data.address
          : response.data?.address || undefined;
        onChange(lat, lng, resolvedAddr);
      } catch {
        onChange(lat, lng);
      } finally {
        setAddressLoading(false);
      }
    },
    [onChange]
  );

  // Initialize Ola Maps Web SDK (Vector Tiles)
  useEffect(() => {
    disposedRef.current = false;
    const apiKey = import.meta.env.VITE_OLA_MAPS_API_KEY;

    if (!apiKey) {
      setUseFallback(true);
      return;
    }

    let mapInstance: any = null;

    const initOlaMap = async () => {
      try {
        if (!mapContainerRef.current) return;

        const olaMaps = new OlaMaps({ apiKey });
        mapInstance = await olaMaps.init({
          style: OLA_STYLE,
          container: mapContainerRef.current,
          center: [pos.lng, pos.lat],
          zoom: 15,
        });

        if (disposedRef.current) {
          mapInstance?.remove?.();
          return;
        }

        olaMapRef.current = mapInstance;

        const pinElement = createOlaPinElement();
        const marker = olaMaps
          .addMarker({
            element: pinElement,
            anchor: "bottom",
            draggable: true,
          })
          .setLngLat([pos.lng, pos.lat])
          .addTo(mapInstance);

        olaMarkerRef.current = marker;

        marker.on("dragend", () => {
          const lngLat = marker.getLngLat();
          void selectLocation(lngLat.lat, lngLat.lng);
        });

        mapInstance.on("click", (e: any) => {
          if (!e?.lngLat) return;
          const { lng, lat } = e.lngLat;
          marker.setLngLat([lng, lat]);
          void selectLocation(lat, lng);
        });

        setOlaLoaded(true);
      } catch (err) {
        console.warn("Ola Maps initialization failed, switching to clean OpenStreetMap tiles:", err);
        if (!disposedRef.current) {
          setUseFallback(true);
        }
      }
    };

    void initOlaMap();

    return () => {
      disposedRef.current = true;
      if (olaMapRef.current) {
        try {
          olaMapRef.current.remove?.();
        } catch {}
        olaMapRef.current = null;
      }
    };
  }, []);

  // Update Ola marker when coordinates update externally
  useEffect(() => {
    if (olaMarkerRef.current && olaMapRef.current && !useFallback) {
      olaMarkerRef.current.setLngLat([pos.lng, pos.lat]);
      olaMapRef.current.flyTo({ center: [pos.lng, pos.lat], zoom: 15 });
    }
  }, [pos, useFallback]);

  return (
    <div
      style={{
        borderRadius: "14px",
        overflow: "hidden",
        border: "1.5px solid #CBD5E1",
        boxShadow: "0 4px 14px rgba(15, 23, 42, 0.06)",
        background: "#FFFFFF",
      }}
    >
      <div style={{ height: "340px", width: "100%", position: "relative" }}>
        {/* Ola Maps Native Container */}
        {!useFallback && (
          <div
            ref={mapContainerRef}
            style={{
              height: "100%",
              width: "100%",
              display: "block",
            }}
          />
        )}

        {/* Leaflet OpenStreetMap Fallback (Never Carto) */}
        {useFallback && (
          <MapContainer
            center={[markerPos.lat, markerPos.lng]}
            zoom={15}
            scrollWheelZoom={true}
            style={{ height: "100%", width: "100%" }}
          >
            {/* Clean OpenStreetMap Tiles: No API Key requirement, No watermark */}
            <TileLayer
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
              url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
              maxZoom={19}
            />

            <RecenterMap lat={markerPos.lat} lng={markerPos.lng} />
            <MapClickHandler onSelect={selectLocation} />

            <Marker
              position={[markerPos.lat, markerPos.lng]}
              icon={customLeafletPinIcon}
              draggable={true}
              eventHandlers={{
                dragend: (e) => {
                  const marker = e.target;
                  const newPos = marker.getLatLng();
                  void selectLocation(newPos.lat, newPos.lng);
                },
              }}
            />
          </MapContainer>
        )}

        {addressLoading && (
          <div
            style={{
              position: "absolute",
              top: "12px",
              left: "50%",
              transform: "translateX(-50%)",
              zIndex: 1000,
              background: "#0F172A",
              color: "#FFFFFF",
              fontSize: "12px",
              fontWeight: 700,
              padding: "6px 14px",
              borderRadius: "999px",
              boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
              pointerEvents: "none",
            }}
          >
            Fetching street address...
          </div>
        )}
      </div>

      <div
        style={{
          padding: "10px 16px",
          background: "#F8FAFC",
          borderTop: "1px solid #E2E8F0",
          fontSize: "12.5px",
          color: "#475569",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <span style={{ fontWeight: 600 }}>
          💡 Click anywhere on the map or drag the green pin to pick your exact service address.
        </span>
        <span
          style={{
            fontSize: "11px",
            color: "#059669",
            fontWeight: 800,
            display: "inline-flex",
            alignItems: "center",
            gap: "5px",
            background: "#ECFDF5",
            padding: "3px 8px",
            borderRadius: "6px",
            border: "1px solid #A7F3D0",
          }}
        >
          ⚡ Powered by Ola Maps
        </span>
      </div>
    </div>
  );
}
