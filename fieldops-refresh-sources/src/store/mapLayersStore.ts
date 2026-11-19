import { create } from 'zustand';
import { MapTypeId } from '../constants/mapLayers';
import { mapLayerStorage, MapPreferences } from '../utils/mapLayerStorage';

export interface MapLayersState extends MapPreferences {
  isMobileSheetOpen: boolean;
  setMapType: (mapType: MapTypeId) => void;
  toggleTraffic: () => void;
  toggleTransit: () => void;
  toggleBicycling: () => void;
  setMobileSheetOpen: (isOpen: boolean) => void;
  restorePreferences: () => void;
}

export const useMapLayersStore = create<MapLayersState>((set, get) => ({
  // Load initially from storage (or defaults if empty)
  ...mapLayerStorage.loadPreferences(),
  isMobileSheetOpen: false,

  setMapType: (mapType: MapTypeId) => {
    set({ mapType });
    const { traffic, transit, bicycling } = get();
    mapLayerStorage.savePreferences({ mapType, traffic, transit, bicycling });
  },

  toggleTraffic: () => {
    set((state) => {
      const traffic = !state.traffic;
      const { mapType, transit, bicycling } = state;
      mapLayerStorage.savePreferences({ mapType, traffic, transit, bicycling });
      return { traffic };
    });
  },

  toggleTransit: () => {
    set((state) => {
      const transit = !state.transit;
      const { mapType, traffic, bicycling } = state;
      mapLayerStorage.savePreferences({ mapType, traffic, transit, bicycling });
      return { transit };
    });
  },

  toggleBicycling: () => {
    set((state) => {
      const bicycling = !state.bicycling;
      const { mapType, traffic, transit } = state;
      mapLayerStorage.savePreferences({ mapType, traffic, transit, bicycling });
      return { bicycling };
    });
  },

  setMobileSheetOpen: (isMobileSheetOpen: boolean) => {
    set({ isMobileSheetOpen });
  },

  restorePreferences: () => {
    const prefs = mapLayerStorage.loadPreferences();
    set({ ...prefs });
  },
}));
