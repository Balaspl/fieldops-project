import React, { useCallback, useEffect, useState } from "react";
import { GoogleMap, Marker, useLoadScript } from "@react-google-maps/api";
import api from "../../services/api";

const mapContainerStyle = { width: "100%", height: "320px" };
const defaultCenter = { lat: 13.0827, lng: 80.2707 };

interface Props {
  latitude: number | null;
  longitude: number | null;
  onChange: (latitude: number, longitude: number, address?: string) => void;
}

export default function LocationPickerMap({ latitude, longitude, onChange }: Props) {
  const { isLoaded, loadError } = useLoadScript({
    googleMapsApiKey: import.meta.env.VITE_GOOGLE_MAPS_API_KEY || "",
    libraries: ["places"],
  });
  const [center, setCenter] = useState(
    latitude != null && longitude != null ? { lat: latitude, lng: longitude } : defaultCenter,
  );

  useEffect(() => {
    if (latitude != null && longitude != null) {
      setCenter({ lat: latitude, lng: longitude });
    }
  }, [latitude, longitude]);

  const selectLocation = useCallback(async (lat: number, lng: number) => {
    setCenter({ lat, lng });
    try {
      const response = await api.get("/organizations/reverse-location", {
        params: { latitude: lat, longitude: lng },
      });
      onChange(lat, lng, response.data?.verified ? response.data.address : undefined);
    } catch {
      onChange(lat, lng);
    }
  }, [onChange]);

  if (loadError) {
    return <div style={{ padding: 16, borderRadius: 10, background: "#FEF2F2", color: "#991B1B" }}>Unable to load the map. Check the Google Maps API key.</div>;
  }

  if (!isLoaded) {
    return <div style={{ height: 320, display: "grid", placeItems: "center", background: "#F8FAFC", borderRadius: 10 }}>Loading map...</div>;
  }

  return (
    <div style={{ borderRadius: 12, overflow: "hidden", border: "1px solid #D1D5DB" }}>
      <GoogleMap
        mapContainerStyle={mapContainerStyle}
        center={center}
        zoom={latitude != null && longitude != null ? 16 : 12}
        onClick={(event) => {
          if (event.latLng) void selectLocation(event.latLng.lat(), event.latLng.lng());
        }}
        options={{ streetViewControl: false, mapTypeControl: false, fullscreenControl: false }}
      >
        {latitude != null && longitude != null && (
          <Marker
            position={{ lat: latitude, lng: longitude }}
            draggable
            onDragEnd={(event) => {
              if (event.latLng) void selectLocation(event.latLng.lat(), event.latLng.lng());
            }}
          />
        )}
      </GoogleMap>
      <div style={{ padding: "8px 12px", background: "#fff", fontSize: 12, color: "#64748B" }}>
        Click the map or drag the marker to choose the service location.
      </div>
    </div>
  );
}
