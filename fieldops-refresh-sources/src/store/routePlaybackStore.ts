import { create } from 'zustand';
import { getGPSHistory, GPSHistoryPoint } from '../services/gpsService';

export interface DetectedStop {
  latitude: number;
  longitude: number;
  arrivalTimestamp: string;
  departureTimestamp: string;
  durationMinutes: number;
}

export interface ColoredSegment {
  path: { lat: number; lng: number }[];
  color: string;
  speedKmH: number;
}

export interface RoutePlaybackState {
  activeTechId: string | null;
  activeTechName: string | null;
  historyPoints: GPSHistoryPoint[];
  currentProgress: number; // Index value (can be float between 0 and points.length - 1)
  isPlaying: boolean;
  playbackSpeed: 1 | 2 | 4;
  stops: DetectedStop[];
  coloredSegments: ColoredSegment[];
  dateRange: { start: string; end: string };
  loading: boolean;
  error: string | null;
  
  // Actions
  startPlayback: (techId: string, techName: string) => void;
  exitPlayback: () => void;
  setDateRange: (start: string, end: string) => void;
  loadHistory: () => Promise<void>;
  play: () => void;
  pause: () => void;
  reset: () => void;
  setPlaybackSpeed: (speed: 1 | 2 | 4) => void;
  setProgress: (progress: number) => void;
  
  // Computed values
  getInterpolatedPosition: () => { lat: number; lng: number } | null;
  getDistanceTravelled: () => number; // in km
  getElapsedTime: () => string; // HH:MM:SS
}

function calculateDistanceMeters(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 6371e3; // Earth radius in meters
  const phi1 = (lat1 * Math.PI) / 180;
  const phi2 = (lat2 * Math.PI) / 180;
  const deltaPhi = ((lat2 - lat1) * Math.PI) / 180;
  const deltaLambda = ((lon2 - lon1) * Math.PI) / 180;

  const a =
    Math.sin(deltaPhi / 2) * Math.sin(deltaPhi / 2) +
    Math.cos(phi1) * Math.cos(phi2) * Math.sin(deltaLambda / 2) * Math.sin(deltaLambda / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

  return R * c;
}

function detectStops(points: GPSHistoryPoint[]): DetectedStop[] {
  const stops: DetectedStop[] = [];
  if (points.length < 2) return stops;

  let anchorIdx = 0;
  let i = 1;

  while (i < points.length) {
    const anchor = points[anchorIdx];
    const current = points[i];

    const dist = calculateDistanceMeters(anchor.latitude, anchor.longitude, current.latitude, current.longitude);

    if (dist <= 100) {
      i++;
    } else {
      const lastInStop = points[i - 1];
      const durationMs = new Date(lastInStop.timestamp).getTime() - new Date(anchor.timestamp).getTime();
      const durationMins = durationMs / 60000;

      if (durationMins >= 5) {
        const stopPoints = points.slice(anchorIdx, i);
        const meanLat = stopPoints.reduce((sum, p) => sum + p.latitude, 0) / stopPoints.length;
        const meanLon = stopPoints.reduce((sum, p) => sum + p.longitude, 0) / stopPoints.length;

        stops.push({
          latitude: meanLat,
          longitude: meanLon,
          arrivalTimestamp: anchor.timestamp,
          departureTimestamp: lastInStop.timestamp,
          durationMinutes: Math.round(durationMins * 10) / 10,
        });
      }
      anchorIdx = i;
      i++;
    }
  }

  // Handle ending stop window
  if (anchorIdx < points.length - 1) {
    const anchor = points[anchorIdx];
    const lastInStop = points[points.length - 1];
    const durationMs = new Date(lastInStop.timestamp).getTime() - new Date(anchor.timestamp).getTime();
    const durationMins = durationMs / 60000;

    if (durationMins >= 5) {
      const stopPoints = points.slice(anchorIdx);
      const meanLat = stopPoints.reduce((sum, p) => sum + p.latitude, 0) / stopPoints.length;
      const meanLon = stopPoints.reduce((sum, p) => sum + p.longitude, 0) / stopPoints.length;

      stops.push({
        latitude: meanLat,
        longitude: meanLon,
        arrivalTimestamp: anchor.timestamp,
        departureTimestamp: lastInStop.timestamp,
        durationMinutes: Math.round(durationMins * 10) / 10,
      });
    }
  }

  return stops;
}

function computeColoredSegments(points: GPSHistoryPoint[]): ColoredSegment[] {
  const segments: ColoredSegment[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    const p1 = points[i];
    const p2 = points[i + 1];

    const distMeters = calculateDistanceMeters(p1.latitude, p1.longitude, p2.latitude, p2.longitude);
    const dtSeconds = (new Date(p2.timestamp).getTime() - new Date(p1.timestamp).getTime()) / 1000;

    let speedKmH = 0;
    if (dtSeconds > 0) {
      speedKmH = (distMeters / 1000) / (dtSeconds / 3600);
    }

    let color = '#3B82F6'; // Blue (>40 km/h)
    if (speedKmH < 10) {
      color = '#EF4444'; // Red (<10 km/h)
    } else if (speedKmH <= 40) {
      color = '#10B981'; // Green (10-40 km/h)
    }

    segments.push({
      path: [
        { lat: p1.latitude, lng: p1.longitude },
        { lat: p2.latitude, lng: p2.longitude }
      ],
      color,
      speedKmH: Math.round(speedKmH * 10) / 10,
    });
  }
  return segments;
}

export const useRoutePlaybackStore = create<RoutePlaybackState>((set, get) => ({
  activeTechId: null,
  activeTechName: null,
  historyPoints: [],
  currentProgress: 0,
  isPlaying: false,
  playbackSpeed: 1,
  stops: [],
  coloredSegments: [],
  dateRange: {
    start: new Date(Date.now() - 24 * 3600 * 1000).toISOString().slice(0, 16), // 24h ago
    end: new Date().toISOString().slice(0, 16), // Now
  },
  loading: false,
  error: null,

  startPlayback: (techId, techName) => {
    set({
      activeTechId: techId,
      activeTechName: techName,
      historyPoints: [],
      currentProgress: 0,
      isPlaying: false,
      playbackSpeed: 1,
      stops: [],
      coloredSegments: [],
      error: null,
    });
    get().loadHistory();
  },

  exitPlayback: () => {
    set({
      activeTechId: null,
      activeTechName: null,
      historyPoints: [],
      currentProgress: 0,
      isPlaying: false,
      stops: [],
      coloredSegments: [],
      error: null,
    });
  },

  setDateRange: (start, end) => {
    set({ dateRange: { start, end } });
    if (get().activeTechId) {
      get().loadHistory();
    }
  },

  loadHistory: async () => {
    const { activeTechId, dateRange } = get();
    if (!activeTechId) return;

    set({ loading: true, error: null, currentProgress: 0, isPlaying: false });
    try {
      const startIso = new Date(dateRange.start).toISOString();
      const endIso = new Date(dateRange.end).toISOString();
      const points = await getGPSHistory(activeTechId, {
        start_time: startIso,
        end_time: endIso,
      });

      const stops = detectStops(points);
      const coloredSegments = computeColoredSegments(points);

      set({
        historyPoints: points,
        stops,
        coloredSegments,
        loading: false,
      });
    } catch (err: any) {
      set({
        error: err.message || 'Failed to load technician GPS route history',
        loading: false,
      });
    }
  },

  play: () => set({ isPlaying: true }),
  pause: () => set({ isPlaying: false }),
  reset: () => set({ currentProgress: 0, isPlaying: false }),
  setPlaybackSpeed: (playbackSpeed) => set({ playbackSpeed }),
  setProgress: (currentProgress) => {
    const points = get().historyPoints;
    if (points.length === 0) return;
    const max = points.length - 1;
    set({ currentProgress: Math.max(0, Math.min(max, currentProgress)) });
  },

  getInterpolatedPosition: () => {
    const { historyPoints, currentProgress } = get();
    if (historyPoints.length === 0) return null;
    
    const idx = Math.floor(currentProgress);
    const fraction = currentProgress - idx;

    if (idx >= historyPoints.length - 1) {
      const last = historyPoints[historyPoints.length - 1];
      return { lat: last.latitude, lng: last.longitude };
    }

    const p1 = historyPoints[idx];
    const p2 = historyPoints[idx + 1];

    const lat = p1.latitude + (p2.latitude - p1.latitude) * fraction;
    const lng = p1.longitude + (p2.longitude - p1.longitude) * fraction;

    return { lat, lng };
  },

  getDistanceTravelled: () => {
    const { historyPoints, currentProgress } = get();
    if (historyPoints.length === 0) return 0;

    let distMeters = 0;
    const targetIdx = Math.floor(currentProgress);

    for (let i = 0; i < targetIdx; i++) {
      const p1 = historyPoints[i];
      const p2 = historyPoints[i + 1];
      distMeters += calculateDistanceMeters(p1.latitude, p1.longitude, p2.latitude, p2.longitude);
    }

    // Interpolate final segment distance
    if (targetIdx < historyPoints.length - 1) {
      const fraction = currentProgress - targetIdx;
      const p1 = historyPoints[targetIdx];
      const p2 = historyPoints[targetIdx + 1];
      const segDist = calculateDistanceMeters(p1.latitude, p1.longitude, p2.latitude, p2.longitude);
      distMeters += segDist * fraction;
    }

    return Math.round((distMeters / 1000) * 100) / 100; // in km
  },

  getElapsedTime: () => {
    const { historyPoints, currentProgress } = get();
    if (historyPoints.length === 0) return '00:00:00';

    const idx = Math.floor(currentProgress);
    const fraction = currentProgress - idx;

    const startMs = new Date(historyPoints[0].timestamp).getTime();
    let currentMs = new Date(historyPoints[idx].timestamp).getTime();

    if (idx < historyPoints.length - 1) {
      const nextMs = new Date(historyPoints[idx + 1].timestamp).getTime();
      currentMs += (nextMs - currentMs) * fraction;
    }

    const elapsedSeconds = Math.max(0, Math.floor((currentMs - startMs) / 1000));
    const hrs = Math.floor(elapsedSeconds / 3600).toString().padStart(2, '0');
    const mins = Math.floor((elapsedSeconds % 3600) / 60).toString().padStart(2, '0');
    const secs = (elapsedSeconds % 60).toString().padStart(2, '0');

    return `${hrs}:${mins}:${secs}`;
  },
}));
