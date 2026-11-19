import { MapTypeId } from '../constants/mapLayers';

export interface MapPreferences {
  mapType: MapTypeId;
  traffic: boolean;
  transit: boolean;
  bicycling: boolean;
}

const STORAGE_KEY = 'fieldops_map_preferences';

export const DEFAULT_PREFERENCES: MapPreferences = {
  mapType: 'roadmap',
  traffic: false,
  transit: false,
  bicycling: false,
};

export const mapLayerStorage = {
  loadPreferences(): MapPreferences {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (!stored) {
        return DEFAULT_PREFERENCES;
      }
      const parsed = JSON.parse(stored);
      return {
        mapType: (parsed.mapType === 'roadmap' || parsed.mapType === 'satellite' || parsed.mapType === 'terrain')
          ? parsed.mapType
          : DEFAULT_PREFERENCES.mapType,
        traffic: typeof parsed.traffic === 'boolean' ? parsed.traffic : DEFAULT_PREFERENCES.traffic,
        transit: typeof parsed.transit === 'boolean' ? parsed.transit : DEFAULT_PREFERENCES.transit,
        bicycling: typeof parsed.bicycling === 'boolean' ? parsed.bicycling : DEFAULT_PREFERENCES.bicycling,
      };
    } catch (e) {
      console.error('Failed to load map preferences from localStorage', e);
      return DEFAULT_PREFERENCES;
    }
  },

  savePreferences(prefs: MapPreferences): void {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
    } catch (e) {
      console.error('Failed to save map preferences to localStorage', e);
    }
  },
};
