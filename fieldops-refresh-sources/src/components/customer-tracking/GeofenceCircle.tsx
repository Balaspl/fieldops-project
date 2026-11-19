import React, { useState, useEffect, useRef } from 'react';
import { CircleF } from '@react-google-maps/api';
import { useTrackingStore } from '../../store/trackingStore';
import { useNotificationStore } from '../../store/notificationStore';

interface GeofenceCircleProps {
  job: {
    job_id: string;
    latitude: number;
    longitude: number;
    status: string;
    sla_deadline: string | null;
  };
}

export const GeofenceCircle: React.FC<GeofenceCircleProps> = ({ job }) => {
  const { geofenceRadii } = useTrackingStore();
  const radius = geofenceRadii[job.job_id] ?? 100; // Default 100m

  // 1. Overdue Checker
  const [isOverdue, setIsOverdue] = useState(false);

  useEffect(() => {
    const checkOverdue = () => {
      if (!job.sla_deadline) {
        setIsOverdue(false);
        return;
      }
      setIsOverdue(new Date(job.sla_deadline).getTime() < new Date().getTime());
    };

    checkOverdue();
    const interval = setInterval(checkOverdue, 30000); // Check every 30 seconds
    return () => clearInterval(interval);
  }, [job.sla_deadline]);

  // 2. Color code geofence
  const getGeofenceColors = () => {
    if (isOverdue) {
      return {
        strokeColor: '#EF4444', // Red
        fillColor: '#EF4444',
      };
    }
    const status = (job.status || '').toUpperCase();
    if (status === 'QUEUED' || status === 'ASSIGNED') {
      return {
        strokeColor: '#3B82F6', // Blue
        fillColor: '#3B82F6',
      };
    }
    // Active / On Site / En Route
    return {
      strokeColor: '#10B981', // Green
      fillColor: '#10B981',
    };
  };

  const { strokeColor, fillColor } = getGeofenceColors();

  // 3. Pulsing animation for EN_ROUTE
  const [pulseRadius, setPulseRadius] = useState(radius);
  const [pulseOpacity, setPulseOpacity] = useState(0.3);

  useEffect(() => {
    const normStatus = (job.status || '').toUpperCase();
    if (normStatus !== 'EN_ROUTE') {
      return;
    }

    let direction = 1;
    const animationInterval = setInterval(() => {
      setPulseRadius((prev) => {
        const next = prev + direction * (radius * 0.03);
        if (next >= radius * 1.3) {
          direction = -1;
          return radius * 1.3;
        }
        if (next <= radius) {
          direction = 1;
          return radius;
        }
        return next;
      });

      setPulseOpacity((prev) => {
        const next = prev - direction * 0.015;
        return Math.max(0.05, Math.min(0.35, next));
      });
    }, 80);

    return () => {
      clearInterval(animationInterval);
      setPulseRadius(radius);
      setPulseOpacity(0.3);
    };
  }, [job.status, radius]);

  const normStatus = (job.status || '').toUpperCase();
  const showPulse = normStatus === 'EN_ROUTE';

  const activeAnimations = useNotificationStore((state) => state.activeAnimations);
  const animTrigger = activeAnimations[job.job_id];
  const [pulseStep, setPulseStep] = useState<number | null>(null);
  const animationFrameRef = useRef<number | null>(null);

  useEffect(() => {
    if (!animTrigger) {
      setPulseStep(null);
      return;
    }

    const duration = 2000; // 2 seconds
    const start = Date.now();
    setPulseStep(0);

    const animationFrame = () => {
      const elapsed = Date.now() - start;
      const progress = Math.min(1, elapsed / duration);
      setPulseStep(progress);

      if (progress < 1) {
        animationFrameRef.current = requestAnimationFrame(animationFrame);
      } else {
        setPulseStep(null);
      }
    };

    animationFrameRef.current = requestAnimationFrame(animationFrame);

    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, [animTrigger]);

  return (
    <>
      {/* Base Geofence Circle */}
      <CircleF
        center={{ lat: job.latitude, lng: job.longitude }}
        radius={radius}
        options={{
          strokeColor,
          strokeOpacity: 0.8,
          strokeWeight: 2,
          fillColor,
          fillOpacity: 0.15,
          clickable: false,
          editable: false,
        }}
      />

      {/* Pulsing Outer Radar Circle (only active when technician is En Route) */}
      {showPulse && (
        <CircleF
          center={{ lat: job.latitude, lng: job.longitude }}
          radius={pulseRadius}
          options={{
            strokeColor,
            strokeOpacity: pulseOpacity * 1.5,
            strokeWeight: 1,
            fillColor,
            fillOpacity: pulseOpacity,
            clickable: false,
            editable: false,
          }}
        />
      )}

      {/* Three-ring Expanding Pulse animation on Geofence Alert */}
      {pulseStep !== null && (
        <>
          <CircleF
            center={{ lat: job.latitude, lng: job.longitude }}
            radius={radius * (1 + 0.3 * pulseStep)}
            options={{
              strokeColor,
              strokeOpacity: (1 - pulseStep) * 0.5,
              strokeWeight: 2,
              fillColor,
              fillOpacity: (1 - pulseStep) * 0.1,
              clickable: false,
              editable: false,
            }}
          />
          <CircleF
            center={{ lat: job.latitude, lng: job.longitude }}
            radius={radius * (1 + 0.6 * pulseStep)}
            options={{
              strokeColor,
              strokeOpacity: (1 - pulseStep) * 0.4,
              strokeWeight: 1.5,
              fillColor,
              fillOpacity: (1 - pulseStep) * 0.08,
              clickable: false,
              editable: false,
            }}
          />
          <CircleF
            center={{ lat: job.latitude, lng: job.longitude }}
            radius={radius * (1 + 0.9 * pulseStep)}
            options={{
              strokeColor,
              strokeOpacity: (1 - pulseStep) * 0.3,
              strokeWeight: 1,
              fillColor,
              fillOpacity: (1 - pulseStep) * 0.05,
              clickable: false,
              editable: false,
            }}
          />
        </>
      )}
    </>
  );
};

export default GeofenceCircle;
