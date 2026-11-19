import { create } from 'zustand';

interface ViewportState {
  lat: number;
  lng: number;
}

export interface ViewportSnapshot {
  center: ViewportState;
  zoom: number;
}

interface ViewportStore {
  center: ViewportState;
  zoom: number;
  followingTechId: string | null;
  history: ViewportSnapshot[];
  updateViewport: (center: ViewportState, zoom: number, recordHistory?: boolean) => void;
  setFollow: (techId: string) => void;
  clearFollow: () => void;
  popHistory: () => ViewportSnapshot | null;
  restoreLastCenter: () => void;
}

const DEFAULT_CENTER: ViewportState = { lat: 13.0827, lng: 80.2707 }; // Chennai
const DEFAULT_ZOOM = 13;
const STORAGE_KEY = 'fieldops_map_viewport';

export const useViewportStore = create<ViewportStore>((set, get) => ({
  center: DEFAULT_CENTER,
  zoom: DEFAULT_ZOOM,
  followingTechId: null,
  history: [],

  updateViewport: (center, zoom, recordHistory = true) => {
    const state = get();
    let updatedHistory = [...state.history];

    if (recordHistory) {
      // Don't push duplicate states
      const last = state.history[state.history.length - 1];
      const isDuplicate = last && 
        Math.abs(last.center.lat - state.center.lat) < 0.0001 &&
        Math.abs(last.center.lng - state.center.lng) < 0.0001 &&
        last.zoom === state.zoom;

      if (!isDuplicate) {
        updatedHistory.push({ center: state.center, zoom: state.zoom });
        if (updatedHistory.length > 10) {
          updatedHistory.shift(); // Keep last 10 entries
        }
      }
    }

    set({
      center,
      zoom,
      history: updatedHistory,
    });

    // Save to localStorage
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ center, zoom }));
    } catch (e) {
      console.error('[viewportStore] Error saving viewport to localStorage:', e);
    }
  },

  setFollow: (techId) => set({ followingTechId: techId }),
  
  clearFollow: () => set({ followingTechId: null }),

  popHistory: () => {
    const state = get();
    if (state.history.length === 0) return null;

    const nextHistory = [...state.history];
    const previousSnapshot = nextHistory.pop()!;

    set({
      center: previousSnapshot.center,
      zoom: previousSnapshot.zoom,
      history: nextHistory,
      followingTechId: null, // Clear follow when navigating back
    });

    return previousSnapshot;
  },

  restoreLastCenter: () => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (parsed.center && typeof parsed.center.lat === 'number' && typeof parsed.center.lng === 'number') {
          set({
            center: parsed.center,
            zoom: typeof parsed.zoom === 'number' ? parsed.zoom : DEFAULT_ZOOM,
          });
        }
      }
    } catch (e) {
      console.error('[viewportStore] Error loading viewport from localStorage:', e);
    }
  },
}));
