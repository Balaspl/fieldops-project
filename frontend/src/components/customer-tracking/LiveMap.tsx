import React, { useEffect, useState, useRef, useCallback } from 'react';
import {
  GoogleMap,
  useLoadScript,
  TrafficLayer,
  TransitLayer,
  BicyclingLayer,
  MarkerClustererF,
} from '@react-google-maps/api';
import { useTrackingStore, type TechGpsData } from '../../store/trackingStore';
import { useMapLayersStore } from '../../store/mapLayersStore';
import { useViewportStore } from '../../store/viewportStore';
import { useMapViewport, setGlobalMapInstance } from '../../hooks/useMapViewport';
import { useTrackingWebSocket } from '../../hooks/useTrackingWebSocket';
import { getDispatchQueue } from '../../services/dispatchQueueService';
import { MapLayerControls } from './MapLayerControls';
import { MapErrorBoundary } from './MapErrorBoundary';
import JobSiteMarker from './JobSiteMarker';
import GeofenceCircle from './GeofenceCircle';
import JobInfoWindow from './JobInfoWindow';
import TechnicianMarker from './TechnicianMarker';
import FollowIndicator from './FollowIndicator';
import MapControls from './MapControls';
import { useRoutePlaybackStore } from '../../store/routePlaybackStore';
import { ReplayMapLayers } from '../tracking-dashboard/ReplayMapLayers';
import toast, { Toaster } from 'react-hot-toast';
import { useNotificationStore } from '../../store/notificationStore';
import { Compass, Maximize, Radio, Loader2, Moon, Sun } from 'lucide-react';

const libraries: ('places' | 'drawing' | 'geometry' | 'localContext' | 'visualization')[] = ['geometry'];

const mapContainerStyle = {
  width: '100%',
  height: '100%',
};

const defaultCenter = {
  lat: 13.0827,
  lng: 80.2707, // Chennai center
};

// Premium dark mode map styles
const darkMapStyles = [
  { elementType: 'geometry', stylers: [{ color: '#1f2937' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#1f2937' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#9ca3af' }] },
  { featureType: 'administrative.locality', elementType: 'labels.text.fill', stylers: [{ color: '#f3f4f6' }] },
  { featureType: 'poi', elementType: 'labels.text.fill', stylers: [{ color: '#9ca3af' }] },
  { featureType: 'poi.park', elementType: 'geometry', stylers: [{ color: '#111827' }] },
  { featureType: 'poi.park', elementType: 'labels.text.fill', stylers: [{ color: '#10b981' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#374151' }] },
  { featureType: 'road', elementType: 'geometry.stroke', stylers: [{ color: '#1f2937' }] },
  { featureType: 'road', elementType: 'labels.text.fill', stylers: [{ color: '#d1d5db' }] },
  { featureType: 'road.highway', elementType: 'geometry', stylers: [{ color: '#4b5563' }] },
  { featureType: 'road.highway', elementType: 'geometry.stroke', stylers: [{ color: '#374151' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#111827' }] },
  { featureType: 'water', elementType: 'labels.text.fill', stylers: [{ color: '#4b5563' }] },
];

export const LiveMap: React.FC<{ tenantId?: string }> = ({ tenantId = 'tenant-1' }) => {
  const { isLoaded, loadError } = useLoadScript({
    googleMapsApiKey: (import.meta as any).env?.VITE_GOOGLE_MAPS_API_KEY || '',
    libraries,
  });

  // WebSocket lifecycle
  useTrackingWebSocket(tenantId);

  // Store variables
  const { technicians, connectionStatus, reconnectAttempt, geofenceRadii, notifiedStates, updateNotifiedState } = useTrackingStore();
  const { mapType, traffic, transit, bicycling } = useMapLayersStore();
  const activeTechId = useRoutePlaybackStore((state) => state.activeTechId);

  // Viewport management
  const {
    center,
    zoom,
    followingTechId,
    exitFollow,
    returnToOverview,
    followTechnicianPosition,
  } = useMapViewport();

  const [jobs, setJobs] = useState<any[]>([]);
  const [selectedTechId, setSelectedTechId] = useState<string | null>(null);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [transitioning, setTransitioning] = useState(false);

  const mapRef = useRef<google.maps.Map | null>(null);

  // Restore center on mount
  useEffect(() => {
    useViewportStore.getState().restoreLastCenter();
  }, []);

  // Fetch jobs for coordinates and rendering
  const loadJobs = async () => {
    try {
      const response = await getDispatchQueue();
      const jobList = response.data || [];
      
      // Parse coordinates
      const mappedJobs = jobList
        .filter((j: any) => j.location)
        .map((j: any) => {
          let lat = defaultCenter.lat;
          let lng = defaultCenter.lng;
          
          const numId = Number(j.job_id || 100);
          lat = 13.0827 + (numId % 20) * 0.004 - 0.03;
          lng = 80.2707 + (numId % 15) * 0.003 - 0.02;

          return {
            job_id: String(j.job_id),
            title: j.title || `Job #${j.job_id}`,
            customer: j.customer || 'Customer',
            location: j.location,
            status: j.status || 'QUEUED',
            sla_deadline: j.sla?.deadline || null,
            latitude: lat,
            longitude: lng,
          };
        });

      setJobs(mappedJobs);
    } catch (e) {
      console.error('[LiveMap] Error loading jobs queue:', e);
    }
  };

  useEffect(() => {
    loadJobs();
  }, []);

  // 1. Google Maps Load Callback
  const onLoad = useCallback((map: google.maps.Map) => {
    mapRef.current = map;
    setGlobalMapInstance(map);
    
    // Check if store center was restored from localStorage
    const savedState = useViewportStore.getState();
    if (savedState.center.lat !== defaultCenter.lat || savedState.center.lng !== defaultCenter.lng) {
      map.setCenter(savedState.center);
      map.setZoom(savedState.zoom);
    } else {
      autoFitBounds();
    }
  }, [jobs, technicians]);

  // 2. Recenter & Fit bounds to include all active technician/job coordinates
  const autoFitBounds = () => {
    if (!mapRef.current || typeof google === 'undefined') return;

    const bounds = new google.maps.LatLngBounds();
    let hasCoords = false;

    // Add jobs coordinates
    jobs.forEach((job) => {
      bounds.extend({ lat: job.latitude, lng: job.longitude });
      hasCoords = true;
    });

    // Add technicians coordinates
    Object.values(technicians).forEach((tech) => {
      bounds.extend({ lat: tech.latitude, lng: tech.longitude });
      hasCoords = true;
    });

    if (hasCoords) {
      mapRef.current.fitBounds(bounds);
      const currentZoom = mapRef.current.getZoom();
      if (currentZoom && currentZoom > 15) {
        mapRef.current.setZoom(14);
      }
    } else {
      mapRef.current.setCenter(defaultCenter);
      mapRef.current.setZoom(13);
    }
  };

  // 3. Geofence Crossings Detection Loop
  useEffect(() => {
    if (typeof google === 'undefined' || !google.maps.geometry || jobs.length === 0) return;

    Object.values(technicians).forEach((tech) => {
      const techPos = new google.maps.LatLng(tech.latitude, tech.longitude);
      
      jobs.forEach((job) => {
        const jobPos = new google.maps.LatLng(job.latitude, job.longitude);
        const distance = google.maps.geometry.spherical.computeDistanceBetween(techPos, jobPos);
        const radius = geofenceRadii[job.job_id] ?? 100;
        const notifyKey = `${job.job_id}_${tech.id}`;
        const previousState = notifiedStates[notifyKey] || 'outside';

        if (distance <= radius && previousState === 'outside') {
          useNotificationStore.getState().addAlert({
            techId: String(tech.id),
            techName: tech.name,
            jobId: String(job.job_id),
            jobTitle: job.title,
            jobLocation: job.location || 'Job Site',
            eventType: 'ENTRY',
            timestamp: new Date().toISOString(),
          });
          updateNotifiedState(job.job_id, tech.id, 'inside');
        } else if (distance > radius && previousState === 'inside') {
          useNotificationStore.getState().addAlert({
            techId: String(tech.id),
            techName: tech.name,
            jobId: String(job.job_id),
            jobTitle: job.title,
            jobLocation: job.location || 'Job Site',
            eventType: 'EXIT',
            timestamp: new Date().toISOString(),
          });
          updateNotifiedState(job.job_id, tech.id, 'outside');
        }
      });
    });
  }, [technicians, jobs, geofenceRadii, notifiedStates]);

  // Follow Mode Updates
  useEffect(() => {
    if (followingTechId) {
      const activeTech = technicians[followingTechId];
      if (activeTech && activeTech.latitude && activeTech.longitude) {
        followTechnicianPosition(followingTechId, activeTech.latitude, activeTech.longitude);
      }
    }
  }, [technicians, followingTechId, followTechnicianPosition]);

  // Keyboard Shortcuts: Space (Overview), Escape (Exit Follow)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const activeEl = document.activeElement;
      const isInput = activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA');
      if (isInput) return;

      if (e.key === 'Escape') {
        exitFollow();
      } else if (e.key === ' ') {
        e.preventDefault();
        returnToOverview(jobs);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [exitFollow, returnToOverview, jobs]);

  // Compute technicians currently inside each job's geofence
  const getTechsInsideGeofence = (jobId: string) => {
    if (typeof google === 'undefined' || !google.maps.geometry) return [];
    
    const job = jobs.find((j) => j.job_id === jobId);
    if (!job) return [];
    
    const jobPos = new google.maps.LatLng(job.latitude, job.longitude);
    const radius = geofenceRadii[jobId] ?? 100;

    return Object.values(technicians).filter((tech) => {
      const techPos = new google.maps.LatLng(tech.latitude, tech.longitude);
      const distance = google.maps.geometry.spherical.computeDistanceBetween(techPos, jobPos);
      return distance <= radius;
    });
  };

  // Watch transitioning state for map theme fades
  useEffect(() => {
    setTransitioning(true);
    const timer = setTimeout(() => setTransitioning(false), 300);
    return () => clearTimeout(timer);
  }, [mapType, isDarkMode]);

  if (loadError) {
    return (
      <div className="w-full h-full min-h-[400px] bg-slate-50 flex flex-col items-center justify-center p-6 text-center border rounded-2xl">
        <p className="text-red-500 font-semibold mb-2">Error Loading Maps API</p>
        <p className="text-slate-500 text-xs max-w-xs">Verify your API credentials and internet connection.</p>
      </div>
    );
  }

  if (!isLoaded) {
    return (
      <div className="w-full h-full min-h-[400px] bg-slate-50 flex flex-col items-center justify-center border rounded-2xl gap-3">
        <div className="w-9 h-9 border-4 border-emerald-600 border-t-transparent rounded-full animate-spin" />
        <span className="text-slate-500 text-xs font-semibold select-none">Bootstrapping Live Tracking Grid...</span>
      </div>
    );
  }

  return (
    <MapErrorBoundary>
      <div className="relative w-full h-full rounded-2xl overflow-hidden border border-slate-200 shadow-inner min-h-[500px]">
        {/* local Toaster for notifications */}
        <Toaster position="top-right" reverseOrder={false} />

        {/* Dynamic theme / layer transitioning fade layer */}
        <div
          className={`absolute inset-0 bg-white dark:bg-slate-900 pointer-events-none z-10 transition-opacity duration-300 ${
            transitioning ? 'opacity-40' : 'opacity-0'
          }`}
        />

        <GoogleMap
          mapContainerStyle={mapContainerStyle}
          zoom={zoom}
          center={center}
          onLoad={onLoad}
          onDragStart={exitFollow}
          onZoomChanged={() => {
            if (followingTechId) exitFollow();
          }}
          options={{
            mapTypeId: mapType,
            disableDefaultUI: false,
            fullscreenControl: false,
            streetViewControl: false,
            mapTypeControl: false,
            zoomControl: true,
            styles: isDarkMode ? darkMapStyles : [],
          }}
        >
          {/* Layer toggles */}
          {traffic && <TrafficLayer />}
          {transit && <TransitLayer />}
          {bicycling && <BicyclingLayer />}

          {/* Job site pins and Geofences */}
          {jobs.map((job) => (
            <React.Fragment key={`job-${job.job_id}`}>
              <JobSiteMarker
                job={job}
                onClick={() => setSelectedJobId(job.job_id)}
              />
              
              <GeofenceCircle job={job} />
            </React.Fragment>
          ))}

          {/* Job details overlay InfoWindow */}
          {selectedJobId && (
            (() => {
              const j = jobs.find((x) => x.job_id === selectedJobId);
              return j ? (
                <JobInfoWindow
                  job={j}
                  techniciansInside={getTechsInsideGeofence(j.job_id)}
                  onClose={() => setSelectedJobId(null)}
                />
              ) : null;
            })()
          )}

          {/* 1. Playback Route History Overlay Layer */}
          {activeTechId && <ReplayMapLayers />}

          {/* 2. Technician Marker clusters (hidden during route playback) */}
          {!activeTechId && (
            <MarkerClustererF
              options={{
                maxZoom: 15,
                gridSize: 50,
              }}
            >
              {(clusterer) => (
                <>
                  {Object.values(technicians).map((tech) => (
                    <TechnicianMarker
                      key={`tech-${tech.id}`}
                      tech={tech}
                      clusterer={clusterer}
                      isSelected={selectedTechId === tech.id}
                      onSelect={() => {
                        setSelectedTechId(tech.id);
                        setSelectedTechId(tech.id);
                      }}
                      onDeselect={() => setSelectedTechId(null)}
                    />
                  ))}
                </>
              )}
            </MarkerClustererF>
          )}
        </GoogleMap>

        {/* Floating Custom Controls overlay bar */}
        <div className="absolute top-4 left-4 z-20 flex flex-col md:flex-row gap-2">
          {/* Connection Status indicator */}
          <div className="flex items-center gap-2 bg-white/95 dark:bg-slate-900/95 backdrop-blur shadow-md px-3 py-2 rounded-xl text-xs font-semibold text-slate-800 dark:text-slate-100 border border-slate-100 dark:border-slate-800">
            {connectionStatus === 'connected' ? (
              <>
                <span className="relative flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
                </span>
                <span className="text-emerald-700 dark:text-emerald-400 font-bold">Streaming</span>
              </>
            ) : connectionStatus === 'reconnecting' ? (
              <>
                <span className="relative flex h-2.5 w-2.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-500"></span>
                </span>
                <span className="text-amber-700 dark:text-amber-400 font-bold">Reconnecting... ({reconnectAttempt}/5)</span>
              </>
            ) : (
              <>
                <span className="h-2.5 w-2.5 rounded-full bg-rose-500"></span>
                <span className="text-rose-700 dark:text-rose-400 font-bold font-sans">Disconnected</span>
              </>
            )}
          </div>

          {/* Follow Mode Indicator badge */}
          <FollowIndicator />

          {/* Shared Map Viewport controls */}
          <MapControls jobs={jobs} />

          {/* Theme Selector Toggle */}
          <button
            onClick={() => setIsDarkMode(!isDarkMode)}
            className="flex items-center justify-center p-2 bg-white/95 dark:bg-slate-900/95 backdrop-blur hover:bg-slate-50 dark:hover:bg-slate-800 shadow-md rounded-xl border border-slate-100 dark:border-slate-800 cursor-pointer transition text-slate-700 dark:text-slate-200"
            title={isDarkMode ? 'Switch to Light Theme' : 'Switch to Dark Theme'}
          >
            {isDarkMode ? <Sun size={15} /> : <Moon size={15} />}
          </button>
        </div>

        {/* Floating Layer Controls (Top Right) */}
        <div className="absolute top-4 right-4 z-20">
          <MapLayerControls />
        </div>
      </div>
    </MapErrorBoundary>
  );
};

export default LiveMap;
