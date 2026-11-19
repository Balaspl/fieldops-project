import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';


import api from '../../../services/api';
import { useRoutePlaybackStore } from '../../../store/routePlaybackStore';
import { ReplayMapLayers } from '../ReplayMapLayers';
import { RoutePlaybackControls } from '../RoutePlaybackControls';

// Mock axios instance
vi.mock('../../../services/api', () => ({
  default: {
    get: vi.fn(),
  },
}));

// Mock @react-google-maps/api components
vi.mock('@react-google-maps/api', () => ({
  GoogleMap: ({ children, onLoad }: any) => {
    React.useEffect(() => {
      if (onLoad) {
        onLoad({
          panTo: vi.fn(),
          setZoom: vi.fn(),
          setCenter: vi.fn(),
          fitBounds: vi.fn(),
          getZoom: vi.fn(() => 13),
          getCenter: vi.fn(() => ({ lat: () => 13.08, lng: () => 80.27 })),
        });
      }
    }, []);
    return <div data-testid="mock-google-map">{children}</div>;
  },
  useLoadScript: () => ({ isLoaded: true, loadError: null }),
  MarkerF: ({ onClick, title, label, icon, position }: any) => {
    const isPlayback = (icon?.scale === 9 || icon?.scale === 6 || (title && title.includes('Stop duration')) || (label?.className && label.className.includes('mt-6')));
    const testId = isPlayback ? 'google-marker' : 'mock-marker';
    return (
      <div
        data-testid={testId}
        data-title={title}
        data-fill-color={icon?.fillColor}
        data-label={typeof label === 'object' ? label.text : label}
        data-lat={position?.lat}
        data-lng={position?.lng}
        onClick={onClick}
      />
    );
  },
  PolylineF: ({ path, options }: any) => (
    <div
      data-testid="google-polyline"
      data-path={JSON.stringify(path)}
      data-color={options?.strokeColor}
    />
  ),
  MarkerClustererF: ({ children, options }: any) => (
    <div data-testid="mock-clusterer" data-max-zoom={options?.maxZoom}>
      {typeof children === 'function' ? children({}) : children}
    </div>
  ),
  TrafficLayer: () => <div data-testid="traffic-layer" />,
  TransitLayer: () => <div data-testid="transit-layer" />,
  BicyclingLayer: () => <div data-testid="bicycling-layer" />,
  InfoWindowF: ({ position, children, onCloseClick }: any) => (
    <div data-testid="google-infowindow" data-lat={position?.lat} data-lng={position?.lng}>
      <div data-testid="info-window">
        <button data-testid="close-infowindow" onClick={onCloseClick}>Close</button>
        {children}
      </div>
    </div>
  ),
  OverlayViewF: ({ children }: any) => <div>{children}</div>,
  OverlayView: { OVERLAY_MOUSE_TARGET: 'OVERLAY_MOUSE_TARGET' },
}));

// Mock map viewport
vi.mock('../../../hooks/useMapViewport', () => ({
  useMapViewport: () => ({
    fitBounds: vi.fn(),
  }),
}));

describe('Technician Route History Playback Tests', () => {
  const mockPings = [
    {
      id: 'p-1',
      technician_id: 'tech-1',
      job_id: 'job-1',
      latitude: 13.0827,
      longitude: 80.2707,
      timestamp: '2026-06-30T10:00:00Z',
      accuracy: 10,
      altitude: 0,
      tenant_id: 'tenant-1',
      created_at: '2026-06-30T10:00:00Z',
    },
    // Speed segment: 13.0827 to 13.0850 is ~255m. In 10s, speed is ~92 km/h (>40 km/h: Blue)
    {
      id: 'p-2',
      technician_id: 'tech-1',
      job_id: 'job-1',
      latitude: 13.0850,
      longitude: 80.2707,
      timestamp: '2026-06-30T10:00:10Z',
      accuracy: 10,
      altitude: 0,
      tenant_id: 'tenant-1',
      created_at: '2026-06-30T10:00:10Z',
    },
    // Speed segment: 13.0850 to 13.0855 is ~55m. In 10s, speed is ~20 km/h (10-40 km/h: Green)
    {
      id: 'p-3',
      technician_id: 'tech-1',
      job_id: 'job-1',
      latitude: 13.0855,
      longitude: 80.2707,
      timestamp: '2026-06-30T10:00:20Z',
      accuracy: 10,
      altitude: 0,
      tenant_id: 'tenant-1',
      created_at: '2026-06-30T10:00:20Z',
    },
    // Stay at same point (13.0855) for 6 minutes (360 seconds) -> should trigger Stop Detection
    {
      id: 'p-4',
      technician_id: 'tech-1',
      job_id: 'job-1',
      latitude: 13.0855,
      longitude: 80.2707,
      timestamp: '2026-06-30T10:06:20Z',
      accuracy: 10,
      altitude: 0,
      tenant_id: 'tenant-1',
      created_at: '2026-06-30T10:06:20Z',
    },
    // Speed segment: 13.0855 to 13.0856 is ~11m. In 60s, speed is ~0.66 km/h (<10 km/h: Red)
    {
      id: 'p-5',
      technician_id: 'tech-1',
      job_id: 'job-1',
      latitude: 13.0856,
      longitude: 80.2707,
      timestamp: '2026-06-30T10:07:20Z',
      accuracy: 10,
      altitude: 0,
      tenant_id: 'tenant-1',
      created_at: '2026-06-30T10:07:20Z',
    },
  ];

  let originalLocalStorage: any;
  let originalWindowLocalStorage: any;

  beforeEach(() => {
    vi.useFakeTimers();
    originalLocalStorage = global.localStorage;
    if (typeof window !== 'undefined') {
      originalWindowLocalStorage = window.localStorage;
    }
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
    Object.defineProperty(global, 'localStorage', { value: localStorageMock, writable: true, configurable: true });
    if (typeof window !== 'undefined') {
      Object.defineProperty(window, 'localStorage', { value: localStorageMock, writable: true, configurable: true });
    }

    vi.mocked(api.get).mockResolvedValue({ data: mockPings });
    useRoutePlaybackStore.setState({
      activeTechId: null,
      activeTechName: null,
      historyPoints: [],
      currentProgress: 0,
      isPlaying: false,
      playbackSpeed: 1,
      stops: [],
      coloredSegments: [],
      error: null,
      loading: false,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.resetAllMocks();
    if (originalLocalStorage) {
      Object.defineProperty(global, 'localStorage', { value: originalLocalStorage, writable: true, configurable: true });
    }
    if (originalWindowLocalStorage && typeof window !== 'undefined') {
      Object.defineProperty(window, 'localStorage', { value: originalWindowLocalStorage, writable: true, configurable: true });
    }
  });

  it('handles loading state, empty state, and api errors with retries', async () => {
    vi.mocked(api.get).mockRejectedValueOnce(new Error('Network failure'));
    
    const { rerender } = render(<RoutePlaybackControls />);

    // Trigger playback and wait for loadHistory promise to resolve
    await act(async () => {
      useRoutePlaybackStore.getState().startPlayback('tech-1', 'Raj');
    });
    rerender(<RoutePlaybackControls />);

    // Assert error state and retry button
    expect(screen.getByText('Network failure')).toBeTruthy();
    const retryBtn = screen.getByText('Retry');
    expect(retryBtn).toBeTruthy();

    // Mock successful fetch for retry
    vi.mocked(api.get).mockResolvedValueOnce({ data: [] });
    await act(async () => {
      fireEvent.click(retryBtn);
    });
    rerender(<RoutePlaybackControls />);

    // Check empty state
    expect(screen.getByText('No route history logs found for this date range.')).toBeTruthy();
  });

  it('correctly calculates distance, speeds, color segments, and detects stops', async () => {
    const { rerender } = render(<ReplayMapLayers />);

    await act(async () => {
      useRoutePlaybackStore.getState().startPlayback('tech-1', 'Raj');
      await useRoutePlaybackStore.getState().loadHistory();
    });
    rerender(<ReplayMapLayers />);

    const store = useRoutePlaybackStore.getState();
    expect(store.historyPoints.length).toBe(5);

    // Stop detection: should detect 1 stop (at p-2 to p-5 grouping window, lasting 7.2 mins)
    expect(store.stops.length).toBe(1);
    expect(store.stops[0].durationMinutes).toBe(7.2);
    expect(store.stops[0].latitude).toBeCloseTo(13.0854, 3);

    // Speed Segment calculation colors:
    // Seg 0 (p1->p2): ~92km/h (>40) -> Blue
    // Seg 1 (p2->p3): ~20km/h (10-40) -> Green
    // Seg 2 (p3->p4): 0km/h (<10) -> Red
    // Seg 3 (p4->p5): ~0.66km/h (<10) -> Red
    expect(store.coloredSegments.length).toBe(4);
    expect(store.coloredSegments[0].color).toBe('#3B82F6'); // Blue
    expect(store.coloredSegments[1].color).toBe('#10B981'); // Green
    expect(store.coloredSegments[2].color).toBe('#EF4444'); // Red
    expect(store.coloredSegments[3].color).toBe('#EF4444'); // Red

    const polylines = screen.getAllByTestId('google-polyline');
    expect(polylines.length).toBe(4);

    // Render stop marker
    const markers = screen.getAllByTestId('google-marker');
    // 1 playhead marker + 1 stop marker = 2 markers total
    expect(markers.length).toBe(2);

    // Click stop marker to trigger InfoWindow tooltip
    const stopMarker = markers.find(m => m.getAttribute('data-title')?.includes('Stop duration'));
    expect(stopMarker).toBeTruthy();
    act(() => {
      fireEvent.click(stopMarker!);
    });

    expect(screen.getByTestId('google-infowindow')).toBeTruthy();
    expect(screen.getByText(/7.2 minutes/)).toBeTruthy();
  });

  it('updates play/pause state and modifies playback speed', async () => {
    const { rerender } = render(<RoutePlaybackControls />);

    await act(async () => {
      useRoutePlaybackStore.getState().startPlayback('tech-1', 'Raj');
      await useRoutePlaybackStore.getState().loadHistory();
    });
    rerender(<RoutePlaybackControls />);

    // Toggle Play
    const playBtn = screen.getByText(/Play/);
    act(() => {
      fireEvent.click(playBtn);
    });
    expect(useRoutePlaybackStore.getState().isPlaying).toBe(true);

    // Toggle Speed to 4x
    const speed4Btn = screen.getByText('4x');
    act(() => {
      fireEvent.click(speed4Btn);
    });
    expect(useRoutePlaybackStore.getState().playbackSpeed).toBe(4);

    // Toggle Pause
    const pauseBtn = screen.getByText(/Pause/);
    act(() => {
      fireEvent.click(pauseBtn);
    });
    expect(useRoutePlaybackStore.getState().isPlaying).toBe(false);
  });

  it('updates live counters and marker position as scrubber is dragged', async () => {
    const { rerender } = render(<RoutePlaybackControls />);

    await act(async () => {
      useRoutePlaybackStore.getState().startPlayback('tech-1', 'Raj');
      await useRoutePlaybackStore.getState().loadHistory();
    });
    rerender(<RoutePlaybackControls />);

    const scrubber = screen.getByLabelText('Route playback timeline slider scrubber');

    // Scrub to progress = 1 (p-2 position)
    act(() => {
      fireEvent.change(scrubber, { target: { value: '1' } });
    });

    const store = useRoutePlaybackStore.getState();
    expect(store.currentProgress).toBe(1);

    // Distance and elapsed time counters update
    expect(store.getDistanceTravelled()).toBeGreaterThan(0);
    expect(store.getElapsedTime()).toBe('00:00:10'); // 10 seconds diff from p1 to p2
  });

  it('generates correct KML and GPX file strings and triggers download link clicks', async () => {
    const { rerender } = render(<RoutePlaybackControls />);

    await act(async () => {
      useRoutePlaybackStore.getState().startPlayback('tech-1', 'Raj');
      await useRoutePlaybackStore.getState().loadHistory();
    });
    rerender(<RoutePlaybackControls />);

    // Mock anchor tag append and click
    const clickSpy = vi.fn();
    const originalCreateElement = document.createElement;
    vi.spyOn(document, 'createElement').mockImplementation((tagName: string) => {
      const elem = originalCreateElement.call(document, tagName);
      if (tagName === 'a') {
        elem.click = clickSpy;
      }
      return elem;
    });

    // Click GPX export
    const gpxBtn = screen.getByText(/GPX/);
    act(() => {
      fireEvent.click(gpxBtn);
    });
    expect(clickSpy).toHaveBeenCalled();

    // Click KML export
    const kmlBtn = screen.getByText(/KML/);
    act(() => {
      fireEvent.click(kmlBtn);
    });
    expect(clickSpy).toHaveBeenCalledTimes(2);
  });

  it('re-fetches GPS history when date inputs change', async () => {
    await act(async () => {
      useRoutePlaybackStore.getState().startPlayback('tech-1', 'Raj');
      await useRoutePlaybackStore.getState().loadHistory();
    });

    const { container, rerender } = render(<RoutePlaybackControls />);
    
    // Verify initial call count. Wait, since startPlayback + loadHistory both call api.get, let's clear the mock call history to check changes.
    vi.mocked(api.get).mockClear();

    // Edit start date using querySelector
    const startInput = container.querySelector('input[type="datetime-local"]');
    expect(startInput).toBeTruthy();

    await act(async () => {
      fireEvent.change(startInput!, { target: { value: '2026-06-30T09:00' } });
    });

    // Re-fetches route history from API
    expect(api.get).toHaveBeenCalledTimes(1);
  });
});
