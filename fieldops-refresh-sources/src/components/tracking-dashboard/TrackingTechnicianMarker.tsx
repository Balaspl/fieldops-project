import React, { useEffect, useState, useRef, useCallback } from 'react';
import { MarkerF } from '@react-google-maps/api';
import type { TechGpsData } from '../../store/trackingStore';
import { formatDistanceToNowStrict } from 'date-fns';
import useInterval from '../../hooks/useInterval';
import { useNotificationStore } from '../../store/notificationStore';

interface TrackingTechnicianMarkerProps {
  tech: TechGpsData;
  clusterer?: any;
  onSelect: (techId: string) => void;
  onZoomTo: (techId: string) => void;
}

const STATUS_COLORS: Record<string, string> = {
  ASSIGNED: '#3B82F6',
  EN_ROUTE: '#10B981',
  ON_SITE: '#F59E0B',
  CREATED: '#3B82F6',
  NO_ACTIVE_JOBS: '#64748B',
};

const DEFAULT_COLOR = '#64748B';

/**
 * TrackingTechnicianMarker — custom marker for the Tracking Dashboard.
 */
export const TrackingTechnicianMarker: React.FC<TrackingTechnicianMarkerProps> = ({
  tech,
  clusterer,
  onSelect,
  onZoomTo,
}) => {
  const { latitude, longitude, status, name, lastPing, assignedJobs, job_id } = tech;
  const normStatus = (status || '').toUpperCase();
  const fillColor = STATUS_COLORS[normStatus] || DEFAULT_COLOR;

  // --- Smooth coordinate interpolation (300ms) ---
  const [animatedPos, setAnimatedPos] = useState({ lat: latitude, lng: longitude });
  const animRef = useRef<number | null>(null);
  const startTimeRef = useRef<number | null>(null);
  const startPosRef = useRef({ lat: latitude, lng: longitude });

  useEffect(() => {
    if (latitude !== startPosRef.current.lat || longitude !== startPosRef.current.lng) {
      if (animRef.current) cancelAnimationFrame(animRef.current);
      startTimeRef.current = null;
      startPosRef.current = { lat: animatedPos.lat, lng: animatedPos.lng };

      const duration = 300;
      const animate = (timestamp: number) => {
        if (!startTimeRef.current) startTimeRef.current = timestamp;
        const elapsed = timestamp - startTimeRef.current;
        const progress = Math.min(elapsed / duration, 1);

        setAnimatedPos({
          lat: startPosRef.current.lat + (latitude - startPosRef.current.lat) * progress,
          lng: startPosRef.current.lng + (longitude - startPosRef.current.lng) * progress,
        });

        if (progress < 1) {
          animRef.current = requestAnimationFrame(animate);
        } else {
          startPosRef.current = { lat: latitude, lng: longitude };
        }
      };

      animRef.current = requestAnimationFrame(animate);
    }
  }, [latitude, longitude]);

  useEffect(() => {
    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current);
    };
  }, []);

  // --- Relative timestamp updated every second ---
  const [relativeTime, setRelativeTime] = useState('');

  const updateRelativeTime = useCallback(() => {
    if (lastPing) {
      try {
        let dateStr = lastPing;
        if (typeof dateStr === 'string' && dateStr.includes('T') && !dateStr.endsWith('Z') && !dateStr.match(/[\+\-]\d{2}:\d{2}$/)) {
          dateStr = dateStr + 'Z';
        }
        const dist = formatDistanceToNowStrict(new Date(dateStr), { addSuffix: false });
        setRelativeTime(`Updated ${dist} ago`);
      } catch {
        setRelativeTime('');
      }
    }
  }, [lastPing]);

  // Initial computation
  useEffect(() => {
    updateRelativeTime();
  }, [updateRelativeTime]);

  // Refresh every second
  useInterval(updateRelativeTime, 1000);

  // --- Job count ---
  const jobCount = assignedJobs?.length ?? (job_id ? 1 : 0);

  // --- Marker icon ---
  const markerIcon = {
    path: 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z',
    fillColor,
    fillOpacity: 1.0,
    strokeColor: '#FFFFFF',
    strokeWeight: 2,
    scale: 1.6,
    anchor: typeof google !== 'undefined' ? new google.maps.Point(12, 22) : undefined,
    labelOrigin: typeof google !== 'undefined' ? new google.maps.Point(12, 30) : undefined,
  };

  // --- Double-click handler ---
  const lastClickRef = useRef<number>(0);
  const clickTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleClick = useCallback(() => {
    const now = Date.now();
    const timeSinceLastClick = now - lastClickRef.current;
    lastClickRef.current = now;

    if (timeSinceLastClick < 350) {
      if (clickTimeoutRef.current) {
        clearTimeout(clickTimeoutRef.current);
        clickTimeoutRef.current = null;
      }
      onZoomTo(tech.id);
    } else {
      clickTimeoutRef.current = setTimeout(() => {
        onSelect(tech.id);
        clickTimeoutRef.current = null;
      }, 350);
    }
  }, [tech.id, onSelect, onZoomTo]);

  useEffect(() => {
    return () => {
      if (clickTimeoutRef.current) clearTimeout(clickTimeoutRef.current);
    };
  }, []);

  const alerts = useNotificationStore((state) => state.alerts);
  const hasUnread = alerts.some((a) => a.techId === String(tech.id) && !a.isRead);

  // Build label showing name + primary status + job count + relative time
  const primaryLabel = status || 'NO_ACTIVE_JOBS';
  const prefix = hasUnread ? '🔴 ' : '';
  const labelText = relativeTime 
    ? `${prefix}${name} (${jobCount} jobs) [${primaryLabel}]\n${relativeTime}` 
    : `${prefix}${name} (${jobCount} jobs) [${primaryLabel}]`;

  return (
    <MarkerF
      position={animatedPos}
      onClick={handleClick}
      icon={markerIcon}
      clusterer={clusterer}
      label={{
        text: labelText,
        color: '#334155',
        fontSize: '10px',
        fontWeight: '600',
        fontFamily: 'Inter, sans-serif',
        className: 'tracking-marker-label',
      }}
      title={`${name} — ${status || 'NO_ACTIVE_JOBS'} (${jobCount} jobs) | ${relativeTime || 'Just now'}`}
      data-testid={`tech-marker-${tech.id}`}
    />
  );
};

export default TrackingTechnicianMarker;
