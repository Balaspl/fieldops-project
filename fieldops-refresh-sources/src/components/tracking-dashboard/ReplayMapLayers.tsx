import React, { useEffect, useState } from 'react';
import { PolylineF, MarkerF, InfoWindowF } from '@react-google-maps/api';
import { useRoutePlaybackStore, DetectedStop } from '../../store/routePlaybackStore';
import { useMapViewport } from '../../hooks/useMapViewport';

export const ReplayMapLayers: React.FC = () => {
  const {
    activeTechId,
    activeTechName,
    historyPoints,
    coloredSegments,
    stops,
    getInterpolatedPosition,
    loading,
  } = useRoutePlaybackStore();

  const { fitBounds } = useMapViewport();
  const [selectedStop, setSelectedStop] = useState<DetectedStop | null>(null);

  // Auto-fit bounds when history points load
  useEffect(() => {
    if (activeTechId && historyPoints.length > 0 && typeof google !== 'undefined') {
      const bounds = new google.maps.LatLngBounds();
      historyPoints.forEach((pt) => {
        bounds.extend({ lat: pt.latitude, lng: pt.longitude });
      });
      fitBounds(bounds, 80);
    }
  }, [activeTechId, historyPoints, fitBounds]);

  if (!activeTechId || historyPoints.length === 0) return null;

  const currentPos = getInterpolatedPosition();

  // Premium Custom Symbols
  const playheadIcon = typeof google !== 'undefined' ? {
    path: google.maps.SymbolPath.CIRCLE,
    fillColor: '#3B82F6', // Blue
    fillOpacity: 1,
    strokeColor: '#FFFFFF',
    strokeWeight: 2.5,
    scale: 9,
  } : undefined;

  const stopIcon = typeof google !== 'undefined' ? {
    path: google.maps.SymbolPath.CIRCLE,
    fillColor: '#F59E0B', // Amber/Yellow
    fillOpacity: 1,
    strokeColor: '#FFFFFF',
    strokeWeight: 1.5,
    scale: 6,
  } : undefined;

  return (
    <>
      {/* 1. Playback Segments Colored by Speed */}
      {coloredSegments.map((seg, idx) => (
        <PolylineF
          key={`segment-${idx}`}
          path={seg.path}
          options={{
            strokeColor: seg.color,
            strokeOpacity: 0.8,
            strokeWeight: 5,
          }}
        />
      ))}

      {/* 2. Yellow Stop Markers */}
      {stops.map((stop, idx) => (
        <MarkerF
          key={`stop-${idx}`}
          position={{ lat: stop.latitude, lng: stop.longitude }}
          icon={stopIcon}
          onClick={() => setSelectedStop(stop)}
          title={`Stop duration: ${stop.durationMinutes} mins`}
        />
      ))}

      {/* 3. Stop Tooltip Info Window */}
      {selectedStop && (
        <InfoWindowF
          position={{ lat: selectedStop.latitude, lng: selectedStop.longitude }}
          onCloseClick={() => setSelectedStop(null)}
        >
          <div className="p-2 min-w-[200px] text-slate-800 font-sans">
            <h4 className="font-bold text-amber-600 flex items-center gap-1 mb-1">
              🛑 Stopped
            </h4>
            <div className="text-xs space-y-1">
              <p>
                <strong>Duration:</strong> {selectedStop.durationMinutes} minutes
              </p>
              <p>
                <strong>Arrived:</strong>{' '}
                {new Date(selectedStop.arrivalTimestamp).toLocaleTimeString()}
              </p>
              <p>
                <strong>Departed:</strong>{' '}
                {new Date(selectedStop.departureTimestamp).toLocaleTimeString()}
              </p>
            </div>
          </div>
        </InfoWindowF>
      )}

      {/* 4. Smoothly Animated Current Position Marker */}
      {currentPos && (
        <MarkerF
          position={currentPos}
          icon={playheadIcon}
          zIndex={9999}
          label={{
            text: activeTechName || 'Technician',
            className: 'bg-blue-600 text-white text-[10px] font-bold px-1.5 py-0.5 rounded shadow mt-6 border border-white',
          }}
        />
      )}
    </>
  );
};
