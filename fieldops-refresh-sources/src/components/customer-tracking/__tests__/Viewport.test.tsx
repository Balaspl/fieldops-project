import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, renderHook } from '@testing-library/react';
import React from 'react';
import { useViewportStore } from '../../../store/viewportStore';
import { useMapViewport, setGlobalMapInstance } from '../../../hooks/useMapViewport';
import { useTrackingStore } from '../../../store/trackingStore';
import { MapControls } from '../MapControls';
import { FollowIndicator } from '../FollowIndicator';

// Mock store resets
const DEFAULT_CENTER = { lat: 13.0827, lng: 80.2707 };

describe('Map Viewport System', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    
    // Reset Zustand store state before each test
    const store = useViewportStore.getState();
    store.center = DEFAULT_CENTER;
    store.zoom = 13;
    store.followingTechId = null;
    store.history = [];
    
    const trackingStore = useTrackingStore.getState();
    trackingStore.technicians = {};
    
    setGlobalMapInstance(null);
  });

  describe('Zustand viewportStore', () => {
    it('sets initial state correctly', () => {
      const state = useViewportStore.getState();
      expect(state.center).toEqual(DEFAULT_CENTER);
      expect(state.zoom).toBe(13);
      expect(state.followingTechId).toBeNull();
      expect(state.history.length).toBe(0);
    });

    it('updates viewport and stores history snapshot', () => {
      const store = useViewportStore.getState();
      store.updateViewport({ lat: 13.0900, lng: 80.2800 }, 15);

      const state = useViewportStore.getState();
      expect(state.center).toEqual({ lat: 13.0900, lng: 80.2800 });
      expect(state.zoom).toBe(15);
      expect(state.history.length).toBe(1);
      expect(state.history[0].center).toEqual(DEFAULT_CENTER);
      expect(state.history[0].zoom).toBe(13);
    });

    it('caps history stack to a maximum of 10 snapshots', () => {
      const store = useViewportStore.getState();
      
      // Perform 12 updates
      for (let i = 0; i < 12; i++) {
        store.updateViewport({ lat: 13.0827 + i * 0.001, lng: 80.2707 }, 14);
      }

      const state = useViewportStore.getState();
      expect(state.history.length).toBe(10);
    });

    it('pops history snapshots to restore previous views', () => {
      const store = useViewportStore.getState();
      store.updateViewport({ lat: 13.0900, lng: 80.2800 }, 14);
      store.updateViewport({ lat: 13.1000, lng: 80.2900 }, 15);

      let state = useViewportStore.getState();
      expect(state.center).toEqual({ lat: 13.1000, lng: 80.2900 });

      // Pop back 1
      store.popHistory();
      state = useViewportStore.getState();
      expect(state.center).toEqual({ lat: 13.0900, lng: 80.2800 });
      expect(state.zoom).toBe(14);

      // Pop back 2
      store.popHistory();
      state = useViewportStore.getState();
      expect(state.center).toEqual(DEFAULT_CENTER);
      expect(state.zoom).toBe(13);
    });
  });

  describe('useMapViewport Hook', () => {
    let mockMap: any;

    beforeEach(() => {
      mockMap = {
        panTo: vi.fn(),
        setCenter: vi.fn(),
        setZoom: vi.fn(),
        getZoom: vi.fn(() => 13),
        getCenter: vi.fn(() => ({
          lat: () => 13.0827,
          lng: () => 80.2707,
        })),
        fitBounds: vi.fn(),
      };
      setGlobalMapInstance(mockMap as any);
    });

    it('pans map to technician location and sets zoom to 16', () => {
      // Seed tracking store
      useTrackingStore.getState().updateTechnicianLocation('tech-1', {
        id: 'tech-1',
        name: 'Vijay Kumar',
        latitude: 13.0910,
        longitude: 80.2810,
        status: 'EN_ROUTE',
      });

      const { result } = renderHook(() => useMapViewport());
      
      result.current.selectTechnician('tech-1');

      expect(mockMap.panTo).toHaveBeenCalledWith({ lat: 13.0910, lng: 80.2810 });
      expect(mockMap.setZoom).toHaveBeenCalledWith(16);
      
      const state = useViewportStore.getState();
      expect(state.followingTechId).toBe('tech-1');
    });

    it('pans map to job location and sets zoom to 15', () => {
      const { result } = renderHook(() => useMapViewport());
      const job = {
        latitude: 13.1000,
        longitude: 80.2900,
        job_id: 'job-12',
      };

      result.current.selectJob(job);

      expect(mockMap.panTo).toHaveBeenCalledWith({ lat: 13.1000, lng: 80.2900 });
      expect(mockMap.setZoom).toHaveBeenCalledWith(15);
      
      const state = useViewportStore.getState();
      expect(state.followingTechId).toBeNull();
    });

    it('throttles automatic follow mode updates to once every 5 seconds', () => {
      const { result } = renderHook(() => useMapViewport());
      
      // First update pans immediately
      result.current.followTechnicianPosition('tech-1', 13.0827, 80.2707);
      expect(mockMap.panTo).toHaveBeenCalledTimes(1);

      // Rapid successive updates are throttled
      result.current.followTechnicianPosition('tech-1', 13.0828, 80.2708);
      result.current.followTechnicianPosition('tech-1', 13.0829, 80.2709);
      expect(mockMap.panTo).toHaveBeenCalledTimes(1);
    });
  });

  describe('UI Controls', () => {
    it('renders FollowIndicator with name when following active tech', () => {
      useTrackingStore.getState().updateTechnicianLocation('tech-123', {
        id: 'tech-123',
        name: 'Vijay Kumar',
        latitude: 13.0827,
        longitude: 80.2707,
        status: 'EN_ROUTE',
      });
      useViewportStore.getState().setFollow('tech-123');

      render(<FollowIndicator />);

      expect(screen.getByText('Following:')).toBeDefined();
      expect(screen.getByText('Vijay Kumar')).toBeDefined();
    });

    it('renders MapControls buttons properly', () => {
      render(<MapControls jobs={[]} />);
      expect(screen.getByText('Overview')).toBeDefined();
    });
  });
});
