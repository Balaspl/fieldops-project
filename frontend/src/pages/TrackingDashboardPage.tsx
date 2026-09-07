import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react';
import {
  GoogleMap,
  useLoadScript,
  TrafficLayer,
  TransitLayer,
  BicyclingLayer,
  MarkerClustererF,
  OverlayViewF,
  OverlayView,
} from '@react-google-maps/api';
import { useTrackingStore, type TechGpsData } from '../store/trackingStore';
import { useTrackingDashboardStore } from '../store/trackingDashboardStore';
import { useMapLayersStore } from '../store/mapLayersStore';
import { useViewportStore } from '../store/viewportStore';
import { useMapViewport, setGlobalMapInstance } from '../hooks/useMapViewport';
import { useTrackingWebSocket } from '../hooks/useTrackingWebSocket';
import { getAllTechnicians } from '../services/technicianService';
import { getDispatchQueue } from '../services/dispatchQueueService';

// Tracking Dashboard components
import TrackingTechnicianMarker from '../components/tracking-dashboard/TrackingTechnicianMarker';
import TechnicianDetailCard from '../components/tracking-dashboard/TechnicianDetailCard';
import FilterToolbar from '../components/tracking-dashboard/FilterToolbar';
import LayerTogglePanel from '../components/tracking-dashboard/LayerTogglePanel';
import ConnectionStatusIndicator from '../components/tracking-dashboard/ConnectionStatusIndicator';
import LoadingSpinner from '../components/ui/LoadingSpinner';
import NotificationBell from '../components/tracking-dashboard/NotificationBell';
import NotificationPanel from '../components/tracking-dashboard/NotificationPanel';
import GeofenceToastContainer from '../components/tracking-dashboard/GeofenceAlertToast';
import { useRoutePlaybackStore } from '../store/routePlaybackStore';
import { ReplayMapLayers } from '../components/tracking-dashboard/ReplayMapLayers';
import { RoutePlaybackControls } from '../components/tracking-dashboard/RoutePlaybackControls';

// Existing shared components
import { MapLayerControls } from '../components/customer-tracking/MapLayerControls';
import { MapErrorBoundary } from '../components/customer-tracking/MapErrorBoundary';
import JobSiteMarker from '../components/customer-tracking/JobSiteMarker';
import GeofenceCircle from '../components/customer-tracking/GeofenceCircle';
import FollowIndicator from '../components/customer-tracking/FollowIndicator';
import MapControls from '../components/customer-tracking/MapControls';

import { Toaster } from 'react-hot-toast';
import { Radio, Users, MapPin } from 'lucide-react';

const libraries: ('places' | 'drawing' | 'geometry' | 'localContext' | 'visualization')[] = ['geometry'];

const mapContainerStyle = {
  width: '100%',
  height: '100%',
};

const defaultCenter = {
  lat: 13.0827,
  lng: 80.2707,
};

/** Active technician statuses to display */
const ACTIVE_STATUSES = new Set(['ASSIGNED', 'EN_ROUTE', 'ON_SITE', 'BUSY']);

/** Premium dark map styles */
const darkMapStyles = [
  { elementType: 'geometry', stylers: [{ color: '#1f2937' }] },
  { elementType: 'labels.text.stroke', stylers: [{ color: '#1f2937' }] },
  { elementType: 'labels.text.fill', stylers: [{ color: '#9ca3af' }] },
  { featureType: 'administrative.locality', elementType: 'labels.text.fill', stylers: [{ color: '#f3f4f6' }] },
  { featureType: 'poi', elementType: 'labels.text.fill', stylers: [{ color: '#9ca3af' }] },
  { featureType: 'poi.park', elementType: 'geometry', stylers: [{ color: '#111827' }] },
  { featureType: 'road', elementType: 'geometry', stylers: [{ color: '#374151' }] },
  { featureType: 'road.highway', elementType: 'geometry', stylers: [{ color: '#4b5563' }] },
  { featureType: 'water', elementType: 'geometry', stylers: [{ color: '#111827' }] },
];

/** Custom cluster icon SVG data URL */
const createClusterIcon = (count: number) => {
  const size = count > 20 ? 56 : count > 10 ? 48 : 40;
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
      <circle cx="${size / 2}" cy="${size / 2}" r="${size / 2 - 2}" fill="#10B981" fill-opacity="0.9" stroke="#fff" stroke-width="2"/>
      <circle cx="${size / 2}" cy="${size / 2}" r="${size / 2 - 8}" fill="#059669" fill-opacity="0.6"/>
      <text x="50%" y="50%" text-anchor="middle" dy=".35em" fill="#fff" font-family="Inter,sans-serif" font-weight="700" font-size="${size > 48 ? 14 : 12}">${count}</text>
    </svg>
  `;
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
};

export const TrackingDashboardPage: React.FC = () => {
  const { isLoaded, loadError } = useLoadScript({
    googleMapsApiKey: (import.meta as any).env?.VITE_GOOGLE_MAPS_API_KEY || '',
    libraries,
  });

  // WebSocket lifecycle with reconnect support
  const { reconnect } = useTrackingWebSocket('tenant-1');

  // Tracking store
  const {
    technicians,
    updateTechnicianLocation,
    geofenceRadii,
    jobs: storeJobs,
    setJobs: setStoreJobs,
  } = useTrackingStore();
  const activeTechId = useRoutePlaybackStore((state) => state.activeTechId);

  // Dashboard-specific UI store
  const {
    statusFilter,
    searchQuery,
    jobTypeFilter,
    selectedTechId,
    showJobSites,
    showRoutes,
    selectTechnician,
    clearSelection,
  } = useTrackingDashboardStore();

  // Map layers
  const { mapType, traffic, transit, bicycling } = useMapLayersStore();

  // Viewport management
  const {
    center,
    zoom,
    followingTechId,
    exitFollow,
    returnToOverview,
    followTechnicianPosition,
    selectTechnician: zoomToTechnician,
  } = useMapViewport();

  const [loading, setLoading] = useState(true);
  const [isDarkMode, setIsDarkMode] = useState(false);

  const jobs = useMemo(() => Object.values(storeJobs), [storeJobs]);

  const mapRef = useRef<google.maps.Map | null>(null);

  // --- Seed technician data on mount ---
  useEffect(() => {
    const loadData = async () => {
      try {
        const [techResponse, jobResponse] = await Promise.allSettled([
          getAllTechnicians({ limit: 100 }),
          getDispatchQueue(),
        ]);

        // Load jobs first, and map active jobs to technicians
        let activeJobs: any[] = [];
        const techJobStatusMap: Record<string, string> = {};
        const techJobIdMap: Record<string, string> = {};
        const techJobTitleMap: Record<string, string> = {};
        const techCustomerMap: Record<string, string> = {};
        const techJobsMap: Record<string, string[]> = {};

        if (jobResponse.status === 'fulfilled') {
          const jobList = jobResponse.value?.data || [];
          activeJobs = jobList
            .filter((j: any) => j.location)
            .map((j: any) => {
              const numId = Number(j.job_id || 100);
              const jobStatus = (j.status || '').toUpperCase();
              
              if (j.assigned_technician_id) {
                const techKey = String(j.assigned_technician_id);
                if (!techJobsMap[techKey]) {
                  techJobsMap[techKey] = [];
                }
                techJobsMap[techKey].push(String(j.job_id));

                if (['ASSIGNED', 'EN_ROUTE', 'ON_SITE'].includes(jobStatus)) {
                  techJobStatusMap[techKey] = jobStatus;
                  techJobIdMap[techKey] = String(j.job_id);
                  techJobTitleMap[techKey] = j.title || `Job #${j.job_id}`;
                  techCustomerMap[techKey] = j.customer || j.customer_name || 'Customer';
                }
              }

              return {
                job_id: String(j.job_id),
                title: j.title || `Job #${j.job_id}`,
                customer: j.customer || j.customer_name || 'Customer',
                location: j.location,
                status: j.status || 'QUEUED',
                sla_deadline: j.sla?.deadline || null,
                latitude: 13.0827 + (numId % 20) * 0.004 - 0.03,
                longitude: 80.2707 + (numId % 15) * 0.003 - 0.02,
              };
            });

          // Save mapped jobs to the tracking store
          const jobsRecord: Record<string, any> = {};
          activeJobs.forEach((job) => {
            jobsRecord[job.job_id] = job;
          });
          setStoreJobs(jobsRecord);
        }

        // Seed technicians with correct job-mapped status
        if (techResponse.status === 'fulfilled') {
          const list = techResponse.value?.data?.technicians || techResponse.value?.data || [];
          list.forEach((t: any) => {
            const techId = String(t.tech_id || t.id);
            const dbIntId = String(t.technician_id || '');
            
            const rawStatus = t.technician_status || t.status || 'Available';
            const mappedStatus = techJobStatusMap[techId] || techJobStatusMap[dbIntId] || rawStatus;
            const assigned = techJobsMap[techId] || techJobsMap[dbIntId] || [];

            const name = t.technician_name || t.name || 'Unknown';
            let lat: number | undefined, lng: number | undefined;

            if (t.technician_location && typeof t.technician_location === 'string') {
              const parts = t.technician_location.split(',');
              if (parts.length === 2) { lat = Number(parts[0]); lng = Number(parts[1]); }
            } else if (t.latitude !== undefined && t.longitude !== undefined) {
              lat = Number(t.latitude); lng = Number(t.longitude);
            }

            if (lat && lng && !isNaN(lat) && !isNaN(lng)) {
              updateTechnicianLocation(techId, {
                id: techId,
                name,
                latitude: lat,
                longitude: lng,
                status: mappedStatus,
                lastPing: t.last_ping || t.updated_at,
                phone: t.phone || t.technician_phone || null,
                photoUrl: t.photo_url || t.avatar || null,
                jobType: t.job_type || t.specialization || null,
                assignedJobs: assigned,
                job_id: techJobIdMap[techId] || techJobIdMap[dbIntId] || null,
                title: techJobTitleMap[techId] || techJobTitleMap[dbIntId] || null,
                customer: techCustomerMap[techId] || techCustomerMap[dbIntId] || null,
              });
            } else {
              updateTechnicianLocation(techId, { id: techId, name });
            }
          });
        }
      } catch (err) {
        printError('[TrackingDashboard] Failed to load initial data:', err);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, [updateTechnicianLocation, setStoreJobs]);

  // Helper to prevent log pollution
  const printError = (msg: string, err: any) => {
    console.error(msg, err);
  };

  // --- Restore viewport on mount ---
  useEffect(() => {
    useViewportStore.getState().restoreLastCenter();
  }, []);

  // --- Filter technicians ---
  const filteredTechnicians = useMemo(() => {
    return Object.values(technicians).filter((tech) => {
      // Must have valid coordinates
      if (!tech.latitude || !tech.longitude) return false;

      // Normalize status and replace spaces with underscores (e.g. "EN ROUTE" -> "EN_ROUTE")
      const normStatus = (tech.status || '').toUpperCase().replace(' ', '_');

      // Status filter matching
      if (statusFilter !== 'ALL') {
        if (statusFilter === 'ASSIGNED') {
          // Both ASSIGNED and BUSY statuses represent active assignments
          if (normStatus !== 'ASSIGNED' && normStatus !== 'BUSY') return false;
        } else {
          if (normStatus !== statusFilter) return false;
        }
      } else {
        // When showing ALL, restrict to ACTIVE_STATUSES to hide offline/break techs
        if (!ACTIVE_STATUSES.has(normStatus)) return false;
      }

      // Name search
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        if (!tech.name.toLowerCase().includes(q)) return false;
      }

      // Job type filter
      if (jobTypeFilter !== 'All') {
        const techJobType = (tech.jobType || '').toUpperCase();
        if (techJobType !== jobTypeFilter.toUpperCase()) return false;
      }

      return true;
    });
  }, [technicians, statusFilter, searchQuery, jobTypeFilter]);

  // --- Map load callback ---
  const onLoad = useCallback((map: google.maps.Map) => {
    mapRef.current = map;
    setGlobalMapInstance(map);

    const savedState = useViewportStore.getState();
    if (savedState.center.lat !== defaultCenter.lat || savedState.center.lng !== defaultCenter.lng) {
      map.setCenter(savedState.center);
      map.setZoom(savedState.zoom);
    } else {
      // Fit bounds to all known coords
      if (typeof google !== 'undefined') {
        const bounds = new google.maps.LatLngBounds();
        let hasBounds = false;
        Object.values(technicians).forEach((t) => {
          if (t.latitude && t.longitude) { bounds.extend({ lat: t.latitude, lng: t.longitude }); hasBounds = true; }
        });
        if (hasBounds) {
          map.fitBounds(bounds, 100);
          const z = map.getZoom();
          if (z && z > 15) map.setZoom(14);
        } else {
          map.setCenter(defaultCenter);
          map.setZoom(13);
        }
      }
    }
  }, [technicians]);

  // --- Follow mode ---
  useEffect(() => {
    if (followingTechId) {
      const activeTech = technicians[followingTechId];
      if (activeTech?.latitude && activeTech?.longitude) {
        followTechnicianPosition(followingTechId, activeTech.latitude, activeTech.longitude);
      }
    }
  }, [technicians, followingTechId, followTechnicianPosition]);

  // --- Keyboard shortcuts ---
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const activeEl = document.activeElement;
      if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.tagName === 'SELECT')) return;

      if (e.key === 'Escape') {
        if (selectedTechId) { clearSelection(); } else { exitFollow(); }
      } else if (e.key === ' ') {
        e.preventDefault();
        returnToOverview(jobs);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [exitFollow, returnToOverview, jobs, selectedTechId, clearSelection]);

  // --- Marker interaction handlers ---
  const handleMarkerSelect = useCallback((techId: string) => {
    selectTechnician(techId);
  }, [selectTechnician]);

  const handleMarkerZoom = useCallback((techId: string) => {
    zoomToTechnician(techId);
  }, [zoomToTechnician]);

  // --- Selected technician data ---
  const selectedTech = selectedTechId ? technicians[selectedTechId] : null;

  // --- Memoized map options to prevent re-render loops in react-google-maps ---
  const mapOptions = useMemo(() => ({
    mapTypeId: mapType,
    disableDefaultUI: false,
    fullscreenControl: false,
    streetViewControl: false,
    mapTypeControl: false,
    zoomControl: true,
    styles: isDarkMode ? darkMapStyles : [],
  }), [mapType, isDarkMode]);

  const clustererOptions = useMemo(() => ({
    maxZoom: 11,
    minimumClusterSize: 2,
    gridSize: 60,
    calculator: (markers: any[], numStyles: number) => {
      return {
        text: String(markers.length),
        index: Math.min(markers.length > 20 ? 3 : markers.length > 10 ? 2 : 1, numStyles),
        title: `${markers.length} technicians`,
      };
    },
    styles: [
      { url: createClusterIcon(5), height: 40, width: 40, textColor: '#fff', textSize: 12, fontFamily: 'Inter, sans-serif' },
      { url: createClusterIcon(15), height: 48, width: 48, textColor: '#fff', textSize: 13, fontFamily: 'Inter, sans-serif' },
      { url: createClusterIcon(30), height: 56, width: 56, textColor: '#fff', textSize: 14, fontFamily: 'Inter, sans-serif' },
    ],
  }), []);

  // --- Active tech count for header ---
  const activeTechCount = filteredTechnicians.length;

  // --- Error state ---
  if (loadError) {
    return (
      <div className="flex items-center justify-center h-full bg-slate-50">
        <div className="text-center p-8">
          <div className="w-16 h-16 bg-red-50 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <MapPin className="w-8 h-8 text-red-400" />
          </div>
          <p className="text-red-500 font-semibold mb-1">Error Loading Maps API</p>
          <p className="text-slate-500 text-sm">Verify your API credentials and internet connection.</p>
        </div>
      </div>
    );
  }

  // --- Loading state ---
  if (!isLoaded || loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%', height: '100vh', background: '#F3F8F5' }}>
        <LoadingSpinner message="Initializing Live Tracking..." fullPage={true} />
      </div>
    );
  }

  return (
    <MapErrorBoundary>
      <div className="flex flex-col w-full h-full overflow-hidden bg-slate-50" data-testid="tracking-dashboard">
        <Toaster position="top-right" reverseOrder={false} />

        {/* ─── Static Dashboard Control Header ─── */}
        <header className="bg-white border-b border-slate-200/80 px-4 py-2.5 flex items-center gap-3 shadow-sm z-30 select-none pointer-events-auto">
          <FollowIndicator />
          <MapControls jobs={jobs} />
          <div className="mx-2 h-6 w-px bg-slate-200" />
          <FilterToolbar />
          <div className="ml-auto">
            <NotificationBell />
          </div>
        </header>

        {/* ─── Map Viewport container ─── */}
        <div className="flex-1 relative overflow-hidden">
          <GoogleMap
            mapContainerStyle={mapContainerStyle}
            zoom={zoom}
            center={center}
            onLoad={onLoad}
            onDragStart={exitFollow}
            onZoomChanged={() => { if (followingTechId) exitFollow(); }}
            options={mapOptions}
          >
            {/* Traffic / Transit / Bicycling layers */}
            {traffic && <TrafficLayer />}
            {transit && <TransitLayer />}
            {bicycling && <BicyclingLayer />}

            {/* Job site markers — conditionally visible */}
            {showJobSites && jobs.map((job) => (
              <React.Fragment key={`job-${job.job_id}`}>
                <JobSiteMarker job={job} onClick={() => {}} />
                <GeofenceCircle job={job} />
              </React.Fragment>
            ))}

            {/* 1. Playback Route History Overlay Layer */}
            {activeTechId && <ReplayMapLayers />}

            {/* 2. Technician Marker Clusters (hidden during route playback) */}
            {!activeTechId && (
              <MarkerClustererF options={clustererOptions}>
                {(clusterer) => (
                  <>
                    {filteredTechnicians.map((tech) => (
                      <TrackingTechnicianMarker
                        key={`tracking-tech-${tech.id}`}
                        tech={tech}
                        clusterer={clusterer}
                        onSelect={handleMarkerSelect}
                        onZoomTo={handleMarkerZoom}
                      />
                    ))}
                  </>
                )}
              </MarkerClustererF>
            )}
          </GoogleMap>

          {/* ─── Floating Layer Controls (Top-Right of Map) ─── */}
          <div className="absolute top-4 right-4 z-20 flex flex-col gap-2 items-end pointer-events-auto">
            <MapLayerControls />
            <LayerTogglePanel />
          </div>

          {/* Bottom-Left: Connection Status + Active count */}
          <div className="absolute bottom-4 left-4 z-20 flex items-center gap-2 pointer-events-auto">
            <ConnectionStatusIndicator reconnect={reconnect} />
            <div className="flex items-center gap-1.5 bg-white/95 backdrop-blur-md shadow-lg px-3 py-2 rounded-xl border border-slate-100 select-none">
              <Users size={13} className="text-emerald-600" />
              <span className="text-xs font-bold text-slate-700" data-testid="active-tech-count">
                {activeTechCount} Active
              </span>
            </div>
          </div>

          {/* Empty state overlay when no technicians match */}
          {activeTechCount === 0 && !loading && (
            <div
              className="absolute inset-0 flex items-center justify-center z-10 pointer-events-none"
              data-testid="empty-state"
            >
              <div className="bg-white/95 backdrop-blur-md shadow-xl rounded-2xl p-8 text-center border border-slate-200 pointer-events-auto max-w-xs">
                <div className="w-14 h-14 bg-slate-50 rounded-2xl flex items-center justify-center mx-auto mb-3 border border-slate-100">
                  <Radio className="w-7 h-7 text-slate-300" />
                </div>
                <h3 className="text-sm font-bold text-slate-800 mb-1">No Active Technicians</h3>
                <p className="text-xs text-slate-500 leading-relaxed">
                  No technicians match the current filters. Try adjusting your status filter or search query.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* ─── Technician Detail Card (slide-out) ─── */}
        {selectedTech && (
          <TechnicianDetailCard
            tech={selectedTech}
            onClose={clearSelection}
          />
        )}

        {/* ─── Geofence alerts custom components ─── */}
        <GeofenceToastContainer />
        <NotificationPanel />

        {/* ─── Route Playback HUD Overlays ─── */}
        <RoutePlaybackControls />
      </div>
    </MapErrorBoundary>
  );
};

export default TrackingDashboardPage;
