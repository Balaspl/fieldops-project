import { vi } from 'vitest';

// 1. Mock localStorage BEFORE importing anything else
const localStorageStore: Record<string, string> = {};
const localStorageMock = {
  getItem: vi.fn((key: string) => localStorageStore[key] || null),
  setItem: vi.fn((key: string, value: string) => {
    localStorageStore[key] = value;
  }),
  clear: vi.fn(() => {
    for (const key in localStorageStore) {
      delete localStorageStore[key];
    }
  }),
  removeItem: vi.fn((key: string) => {
    delete localStorageStore[key];
  }),
};
Object.defineProperty(global, 'localStorage', { value: localStorageMock, writable: true });

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import React from 'react';
import '@testing-library/jest-dom';
import { useMapLayersStore } from '../../../store/mapLayersStore';
import { MapLayerControls } from '../MapLayerControls';
import { mapLayerStorage } from '../../../utils/mapLayerStorage';

// Mock window.google object for react-google-maps script environment
beforeEach(() => {
  localStorage.clear();
  useMapLayersStore.getState().restorePreferences();
  
  // Setup standard google.maps mock
  global.window = global.window || {};
  (global.window as any).google = {
    maps: {
      Point: class {
        constructor(public x: number, public y: number) {}
      },
      MapTypeId: {
        ROADMAP: 'roadmap',
        SATELLITE: 'satellite',
        TERRAIN: 'terrain',
      },
    },
  };
});

describe('MapLayerControls & Preferences Store', () => {
  it('loads default preferences from localStorage if empty', () => {
    const state = useMapLayersStore.getState();
    expect(state.mapType).toBe('roadmap');
    expect(state.traffic).toBe(false);
    expect(state.transit).toBe(false);
    expect(state.bicycling).toBe(false);
  });

  it('restores preferences correctly on startup', () => {
    const mockPrefs = {
      mapType: 'satellite' as const,
      traffic: true,
      transit: false,
      bicycling: true,
    };
    mapLayerStorage.savePreferences(mockPrefs);

    useMapLayersStore.getState().restorePreferences();
    const state = useMapLayersStore.getState();

    expect(state.mapType).toBe('satellite');
    expect(state.traffic).toBe(true);
    expect(state.transit).toBe(false);
    expect(state.bicycling).toBe(true);
  });

  it('saves preference to localStorage when mapType or overlays change', () => {
    const store = useMapLayersStore.getState();
    
    // Switch mapType
    store.setMapType('terrain');
    let saved = mapLayerStorage.loadPreferences();
    expect(saved.mapType).toBe('terrain');

    // Toggle overlays
    store.toggleTraffic();
    saved = mapLayerStorage.loadPreferences();
    expect(saved.traffic).toBe(true);
  });

  it('renders MapLayerControls buttons and toggles active states', () => {
    render(<MapLayerControls />);

    // Roadmap option is default active
    const roadmapBtn = screen.getByRole('button', { name: /switch to roadmap view/i });
    expect(roadmapBtn).toBeInTheDocument();
    expect(roadmapBtn).toHaveAttribute('aria-pressed', 'true');

    // Satellite option is not active
    const satelliteBtn = screen.getByRole('button', { name: /switch to satellite view/i });
    expect(satelliteBtn).toBeInTheDocument();
    expect(satelliteBtn).toHaveAttribute('aria-pressed', 'false');

    // Click Satellite
    fireEvent.click(satelliteBtn);
    expect(useMapLayersStore.getState().mapType).toBe('satellite');
  });

  it('handles keyboard shortcuts correctly', () => {
    render(<MapLayerControls />);

    // Press S to switch to Satellite
    fireEvent.keyDown(window, { key: 's', code: 'KeyS' });
    expect(useMapLayersStore.getState().mapType).toBe('satellite');

    // Press R to switch to Roadmap
    fireEvent.keyDown(window, { key: 'r', code: 'KeyR' });
    expect(useMapLayersStore.getState().mapType).toBe('roadmap');

    // Press T to toggle Traffic
    expect(useMapLayersStore.getState().traffic).toBe(false);
    fireEvent.keyDown(window, { key: 't', code: 'KeyT' });
    expect(useMapLayersStore.getState().traffic).toBe(true);
  });

  it('ignores keyboard shortcuts when typing in inputs', () => {
    render(
      <div>
        <input data-testid="test-input" type="text" />
        <MapLayerControls />
      </div>
    );

    const input = screen.getByTestId('test-input');
    input.focus();

    // Press S inside input
    fireEvent.keyDown(input, { key: 's', code: 'KeyS' });
    // Map type should remain roadmap
    expect(useMapLayersStore.getState().mapType).toBe('roadmap');
  });

  it('opens and closes mobile layer bottom sheet', () => {
    render(<MapLayerControls />);

    // Mobile trigger button
    const trigger = screen.getByRole('button', { name: /map layers and settings/i });
    expect(trigger).toBeInTheDocument();

    // Bottom sheet is closed initially
    expect(useMapLayersStore.getState().isMobileSheetOpen).toBe(false);

    // Open sheet
    fireEvent.click(trigger);
    expect(useMapLayersStore.getState().isMobileSheetOpen).toBe(true);

    // Escape closes mobile sheet
    fireEvent.keyDown(window, { key: 'Escape', code: 'Escape' });
    expect(useMapLayersStore.getState().isMobileSheetOpen).toBe(false);
  });
});
