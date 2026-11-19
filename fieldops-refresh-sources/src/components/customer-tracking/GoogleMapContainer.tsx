import React, { useEffect, useState } from 'react';
import {
  GoogleMap,
  useLoadScript,
  TrafficLayer,
  TransitLayer,
  BicyclingLayer,
  Marker,
  InfoWindow,
} from '@react-google-maps/api';
import { useMapLayersStore } from '../../store/mapLayersStore';
import { MapLayerControls } from './MapLayerControls';

const libraries: ('places' | 'drawing' | 'geometry' | 'localContext' | 'visualization')[] = [];

const mapContainerStyle = {
  width: '100%',
  height: '100%',
};

// Default center (e.g., Chennai or general coordinates)
const defaultCenter = {
  lat: 13.0827,
  lng: 80.2707,
};

interface TechGpsData {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  status: string;
  lastPing?: string;
}

interface GoogleMapContainerProps {
  technicians: TechGpsData[];
}

export const GoogleMapContainer: React.FC<GoogleMapContainerProps> = ({ technicians }) => {
  const { mapType, traffic, transit, bicycling } = useMapLayersStore();
  const [transitioning, setTransitioning] = useState(false);
  const [selectedTech, setSelectedTech] = useState<TechGpsData | null>(null);

  // Load Google Maps Script
  const { isLoaded, loadError } = useLoadScript({
    googleMapsApiKey: import.meta.env.VITE_GOOGLE_MAPS_API_KEY || '',
    libraries,
  });

  // Track map type changes to trigger 300ms fade overlay transition
  useEffect(() => {
    setTransitioning(true);
    const timer = setTimeout(() => {
      setTransitioning(false);
    }, 300);
    return () => clearTimeout(timer);
  }, [mapType]);

  if (loadError) {
    return (
      <div className="w-100 h-100 bg-slate-100 flex flex-col items-center justify-center p-6 text-center border rounded-2xl">
        <p className="text-red-500 font-semibold mb-2">Error Loading Google Maps</p>
        <p className="text-slate-500 text-xs max-w-xs">
          Please verify your connection and check your API key settings.
        </p>
      </div>
    );
  }

  if (!isLoaded) {
    return (
      <div className="w-100 h-100 bg-slate-50 flex items-center justify-center border rounded-2xl">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-4 border-emerald-500 border-t-transparent rounded-full animate-spin" />
          <span className="text-slate-500 text-xs font-medium">Loading Google Maps...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="relative w-full h-full rounded-2xl overflow-hidden border border-slate-200 shadow-inner">
      {/* 300ms Fade Transition Overlay */}
      <div
        className={`absolute inset-0 bg-white pointer-events-none z-10 transition-opacity duration-300 ${
          transitioning ? 'opacity-50' : 'opacity-0'
        }`}
      />

      <GoogleMap
        mapContainerStyle={mapContainerStyle}
        zoom={13}
        center={technicians.length > 0 ? { lat: technicians[0].latitude, lng: technicians[0].longitude } : defaultCenter}
        options={{
          mapTypeId: mapType,
          disableDefaultUI: false,
          fullscreenControl: false,
          streetViewControl: false,
          mapTypeControl: false,
          zoomControl: true,
          styles: [
            {
              featureType: 'all',
              elementType: 'geometry.fill',
              stylers: [{ weight: '2.00' }],
            },
          ],
        }}
      >
        {/* Custom Overlays based on state */}
        {traffic && <TrafficLayer />}
        {transit && <TransitLayer />}
        {bicycling && <BicyclingLayer />}

        {/* Technician Markers */}
        {technicians.map((tech) => (
          <Marker
            key={tech.id}
            position={{ lat: tech.latitude, lng: tech.longitude }}
            onClick={() => setSelectedTech(tech)}
            icon={{
              path: 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z',
              fillColor: tech.status === 'Available' ? '#10B981' : tech.status === 'Busy' ? '#EF4444' : '#64748B',
              fillOpacity: 1,
              strokeColor: '#FFFFFF',
              strokeWeight: 2,
              scale: 1.5,
              anchor: new google.maps.Point(12, 22),
            }}
          />
        ))}

        {selectedTech && (
          <InfoWindow
            position={{ lat: selectedTech.latitude, lng: selectedTech.longitude }}
            onCloseClick={() => setSelectedTech(null)}
          >
            <div className="p-2 select-none min-w-[150px]">
              <h4 className="font-semibold text-slate-800 text-sm">{selectedTech.name}</h4>
              <p className="text-slate-500 text-xs mt-0.5">Status: <span className="font-medium text-emerald-600">{selectedTech.status}</span></p>
              {selectedTech.lastPing && (
                <p className="text-[10px] text-slate-400 mt-1">
                  Last Active: {new Date(selectedTech.lastPing).toLocaleTimeString()}
                </p>
              )}
            </div>
          </InfoWindow>
        )}
      </GoogleMap>

      {/* Floating Layer Controls */}
      <div className="absolute top-4 right-4 z-20">
        <MapLayerControls />
      </div>
    </div>
  );
};
export default GoogleMapContainer;
