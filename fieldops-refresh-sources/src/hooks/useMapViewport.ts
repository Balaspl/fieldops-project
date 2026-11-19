import { useCallback, useRef } from 'react';
import { useViewportStore } from '../store/viewportStore';
import { useTrackingStore } from '../store/trackingStore';
import debounce from 'lodash.debounce';

// Shared module-level map reference
let activeMap: google.maps.Map | null = null;

export const setGlobalMapInstance = (map: google.maps.Map | null) => {
  activeMap = map;
};

export const useMapViewport = () => {
  const {
    center,
    zoom,
    followingTechId,
    history,
    updateViewport,
    setFollow,
    clearFollow,
    popHistory,
  } = useViewportStore();

  const { technicians } = useTrackingStore();

  // Throttled follow update logic to prevent jarring jumps on rapid coordinate feeds (limit to once every 5 seconds)
  const lastPanTimeRef = useRef<number>(0);

  const followTechnicianPosition = useCallback(
    (techId: string, lat: number, lng: number) => {
      if (!activeMap) return;
      const now = Date.now();
      if (now - lastPanTimeRef.current >= 5000) {
        activeMap.panTo({ lat, lng });
        updateViewport({ lat, lng }, activeMap.getZoom() || 16, false); // don't push live trace pings to user history
        lastPanTimeRef.current = now;
      }
    },
    [updateViewport]
  );

  const setCenter = useCallback((lat: number, lng: number, animate = true) => {
    if (!activeMap) return;
    const targetZoom = activeMap.getZoom() || DEFAULT_ZOOM;
    
    if (animate) {
      activeMap.panTo({ lat, lng });
    } else {
      activeMap.setCenter({ lat, lng });
    }

    updateViewport({ lat, lng }, targetZoom);
  }, [updateViewport]);

  const fitBounds = useCallback((bounds: google.maps.LatLngBounds, padding = 50) => {
    if (!activeMap) return;
    activeMap.fitBounds(bounds, padding);
    
    const newCenter = activeMap.getCenter();
    if (newCenter) {
      updateViewport(
        { lat: newCenter.lat(), lng: newCenter.lng() },
        activeMap.getZoom() || 13
      );
    }
  }, [updateViewport]);

  const selectTechnician = useCallback((techId: string) => {
    const tech = technicians[techId];
    if (!tech || !tech.latitude || !tech.longitude) return;

    if (activeMap) {
      activeMap.panTo({ lat: tech.latitude, lng: tech.longitude });
      activeMap.setZoom(16);
    }

    updateViewport({ lat: tech.latitude, lng: tech.longitude }, 16);
    setFollow(techId);
  }, [technicians, updateViewport, setFollow]);

  const selectJob = useCallback((job: { latitude: number; longitude: number; job_id: string }) => {
    if (!job || !job.latitude || !job.longitude) return;

    if (activeMap) {
      activeMap.panTo({ lat: job.latitude, lng: job.longitude });
      activeMap.setZoom(15);
    }

    updateViewport({ lat: job.latitude, lng: job.longitude }, 15);
    clearFollow();
  }, [updateViewport, clearFollow]);

  const returnToOverview = useCallback((jobsList: any[]) => {
    if (!activeMap || typeof google === 'undefined') return;

    const bounds = new google.maps.LatLngBounds();
    let hasCoords = false;

    // Extend jobs coords
    jobsList.forEach((job) => {
      bounds.extend({ lat: job.latitude, lng: job.longitude });
      hasCoords = true;
    });

    // Extend active tech coords
    Object.values(technicians).forEach((tech) => {
      if (tech.latitude && tech.longitude) {
        bounds.extend({ lat: tech.latitude, lng: tech.longitude });
        hasCoords = true;
      }
    });

    if (hasCoords) {
      activeMap.fitBounds(bounds, 100); // 100px padding
      
      // Limit overview zoom between 12 and 14
      google.maps.event.addListenerOnce(activeMap, 'bounds_changed', () => {
        const currentZoom = activeMap!.getZoom() || 13;
        if (currentZoom > 14) {
          activeMap!.setZoom(14);
        } else if (currentZoom < 12) {
          activeMap!.setZoom(12);
        }
        
        const newCenter = activeMap!.getCenter();
        if (newCenter) {
          updateViewport(
            { lat: newCenter.lat(), lng: newCenter.lng() },
            activeMap!.getZoom() || 13
          );
        }
      });
    }

    clearFollow();
  }, [technicians, updateViewport, clearFollow]);

  const goBack = useCallback(() => {
    const previousSnapshot = popHistory();
    if (previousSnapshot && activeMap) {
      activeMap.panTo(previousSnapshot.center);
      activeMap.setZoom(previousSnapshot.zoom);
    }
  }, [popHistory]);

  const exitFollow = useCallback(() => {
    clearFollow();
  }, [clearFollow]);

  return {
    center,
    zoom,
    followingTechId,
    history,
    setCenter,
    fitBounds,
    selectTechnician,
    selectJob,
    followTechnician: setFollow,
    exitFollow,
    returnToOverview,
    goBack,
    followTechnicianPosition,
  };
};

const DEFAULT_ZOOM = 13;
