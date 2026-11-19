import React, { useEffect, useState, useRef } from 'react';
import { MarkerF, InfoWindowF } from '@react-google-maps/api';
import type { TechGpsData } from '../../store/trackingStore';
import { Clock, Navigation, CheckCircle, Radio } from 'lucide-react';

interface TechnicianMarkerProps {
  tech: TechGpsData;
  isSelected: boolean;
  onSelect: () => void;
  onDeselect: () => void;
  clusterer?: any;
}

export const TechnicianMarker: React.FC<TechnicianMarkerProps> = ({
  tech,
  isSelected,
  onSelect,
  onDeselect,
  clusterer,
}) => {
  const { latitude, longitude, status, name, lastPing, accuracy } = tech;

  // 1. Smooth Coordinate Interpolation (300ms glide transition)
  const [animatedPos, setAnimatedPos] = useState({ lat: latitude, lng: longitude });
  const animRef = useRef<number | null>(null);
  const startTimeRef = useRef<number | null>(null);
  const startPosRef = useRef({ lat: latitude, lng: longitude });

  useEffect(() => {
    // Check if position changed
    if (latitude !== startPosRef.current.lat || longitude !== startPosRef.current.lng) {
      if (animRef.current) {
        cancelAnimationFrame(animRef.current);
      }
      startTimeRef.current = null;
      startPosRef.current = { lat: animatedPos.lat, lng: animatedPos.lng };

      const duration = 300; // 300ms

      const animate = (timestamp: number) => {
        if (!startTimeRef.current) startTimeRef.current = timestamp;
        const elapsed = timestamp - startTimeRef.current;
        const progress = Math.min(elapsed / duration, 1);

        const currentLat = startPosRef.current.lat + (latitude - startPosRef.current.lat) * progress;
        const currentLng = startPosRef.current.lng + (longitude - startPosRef.current.lng) * progress;

        setAnimatedPos({ lat: currentLat, lng: currentLng });

        if (progress < 1) {
          animRef.current = requestAnimationFrame(animate);
        } else {
          startPosRef.current = { lat: latitude, lng: longitude };
        }
      };

      animRef.current = requestAnimationFrame(animate);
    }
  }, [latitude, longitude]);

  // Clean up animation on unmount
  useEffect(() => {
    return () => {
      if (animRef.current) {
        cancelAnimationFrame(animRef.current);
      }
    };
  }, []);

  // 2. Hover Tooltip State
  const [isHovered, setIsHovered] = useState(false);

  // 3. Color mapping by Job Status
  const getMarkerIcon = (jobStatus: string) => {
    const normStatus = (jobStatus || '').toUpperCase();
    let fillColor = '#64748B'; // Default Slate

    if (normStatus === 'ASSIGNED') {
      fillColor = '#3B82F6'; // Blue
    } else if (normStatus === 'EN_ROUTE') {
      fillColor = '#10B981'; // Green
    } else if (normStatus === 'ON_SITE') {
      fillColor = '#F59E0B'; // Orange
    }

    return {
      path: 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z',
      fillColor,
      fillOpacity: 1.0,
      strokeColor: '#FFFFFF',
      strokeWeight: 2,
      scale: 1.5,
      anchor: typeof google !== 'undefined' ? new google.maps.Point(12, 22) : undefined,
    };
  };

  const getInitials = (fullName: string) => {
    return fullName
      .split(' ')
      .map((w) => w[0])
      .join('')
      .slice(0, 2)
      .toUpperCase();
  };

  const getStatusBadgeClass = (jobStatus: string) => {
    const normStatus = (jobStatus || '').toUpperCase();
    if (normStatus === 'ASSIGNED') return 'bg-blue-100 text-blue-800';
    if (normStatus === 'EN_ROUTE') return 'bg-green-100 text-green-800';
    if (normStatus === 'ON_SITE') return 'bg-amber-100 text-amber-800';
    return 'bg-slate-100 text-slate-800';
  };

  const formatTime = (timeStr: string) => {
    try {
      return new Date(timeStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch (e) {
      return '—';
    }
  };

  return (
    <>
      <MarkerF
        position={animatedPos}
        onClick={onSelect}
        onMouseOver={() => setIsHovered(true)}
        onMouseOut={() => setIsHovered(false)}
        icon={getMarkerIcon(status)}
        clusterer={clusterer}
      />

      {/* 4. Hover Tooltip (lightweight InfoWindow without close box) */}
      {isHovered && !isSelected && (
        <InfoWindowF
          position={animatedPos}
          options={{
            disableAutoPan: true,
            closeBoxURL: '',
          }}
        >
          <div className="flex items-center gap-2.5 p-1 select-none font-sans max-w-[200px]">
            <div className="bg-slate-100 text-slate-800 font-bold text-xs h-7 w-7 rounded-full flex items-center justify-center border border-slate-200">
              {getInitials(name)}
            </div>
            <div>
              <h4 className="font-bold text-slate-900 text-xs">{name}</h4>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase ${getStatusBadgeClass(status)}`}>
                  {status}
                </span>
                <span className="text-[9px] text-slate-400 font-medium">
                  {formatTime(lastPing)}
                </span>
              </div>
            </div>
          </div>
        </InfoWindowF>
      )}

      {/* 5. Detailed InfoWindow on Marker Click */}
      {isSelected && (
        <InfoWindowF
          position={animatedPos}
          onCloseClick={onDeselect}
        >
          <div className="p-2 select-none min-w-[240px] font-sans text-slate-800">
            {/* Header / Avatar */}
            <div className="flex items-center gap-2.5 pb-2.5 border-b border-slate-100">
              <div className="bg-emerald-600 text-white font-bold text-sm h-9 w-9 rounded-full flex items-center justify-center shadow-inner">
                {getInitials(name)}
              </div>
              <div>
                <h4 className="font-bold text-slate-900 text-sm">{name}</h4>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border uppercase ${getStatusBadgeClass(status)}`}>
                    {status}
                  </span>
                </div>
              </div>
            </div>

            {/* Details Grid */}
            <div className="py-2.5 space-y-2 text-xs">
              {tech.job_id && (
                <div className="bg-slate-50 border border-slate-100 rounded-lg p-2 space-y-1.5">
                  <p className="font-bold text-[10px] text-slate-400 uppercase tracking-wider">Active Job</p>
                  <p className="font-bold text-slate-900">{tech.title || `Job #${tech.job_id}`}</p>
                  <p className="text-[11px] text-slate-600 font-medium leading-relaxed">
                    Customer: <span className="font-semibold text-slate-900">{tech.customer || '—'}</span>
                  </p>
                  <p className="text-[11px] text-slate-500 font-medium">
                    Addr: <span className="font-normal text-slate-600">{tech.location || '—'}</span>
                  </p>
                </div>
              )}

              {/* ETA Display */}
              <div className="flex justify-between items-center bg-emerald-50/50 border border-emerald-100/50 rounded-lg p-2 text-emerald-950 font-medium">
                <span className="flex items-center gap-1">
                  <Clock size={12} className="text-emerald-600" />
                  ETA:
                </span>
                <span className="font-bold">
                  {tech.eta ? tech.eta : 'Calculating...'}
                  {tech.eta_duration_minutes !== undefined && tech.eta_duration_minutes !== null && (
                    <span className="text-[10px] text-emerald-600 font-medium ml-1">
                      ({tech.eta_duration_minutes}m)
                    </span>
                  )}
                </span>
              </div>

              {/* Accuracy & Update details */}
              <div className="flex justify-between text-[10px] text-slate-400 pt-1">
                <span className="flex items-center gap-1">
                  <Radio size={10} className="text-slate-400" />
                  Accuracy: {accuracy ? `${accuracy.toFixed(1)}m` : '—'}
                </span>
                <span>
                  Updated: {formatTime(lastPing)}
                </span>
              </div>
            </div>
          </div>
        </InfoWindowF>
      )}
    </>
  );
};

export default TechnicianMarker;
