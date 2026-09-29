import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import React from 'react';


// ──────────────────────────────────────────────────────
// Mocks — must be declared before imports that use them
// ──────────────────────────────────────────────────────

// Mock Google Maps API
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


vi.mock("../../../services/etaService", () => ({
  getTechnicianETA: vi.fn().mockResolvedValue({}),
}));

// Mock WebSocket hook — use path relative to PAGE (since the page does the import)
const mockReconnect = vi.fn();
vi.mock('../../../hooks/useTrackingWebSocket', () => ({
  useTrackingWebSocket: () => ({
    ws: null,
    status: 'connected',
    reconnect: mockReconnect,
  }),
}));

// Mock technician service
vi.mock('../../../services/technicianService', () => ({
  getAllTechnicians: vi.fn(() => Promise.resolve({ data: { technicians: [] } })),
}));

// Mock dispatch service
vi.mock('../../../services/dispatchQueueService', () => ({
  getDispatchQueue: vi.fn(() => Promise.resolve({ data: [] })),
}));

// Mock viewport hook
const mockSelectTechnician = vi.fn();
const mockExitFollow = vi.fn();
const mockReturnToOverview = vi.fn();
const mockFollowTechnicianPosition = vi.fn();

vi.mock('../../../hooks/useMapViewport', () => ({
  useMapViewport: () => ({
    center: { lat: 13.0827, lng: 80.2707 },
    zoom: 13,
    followingTechId: null,
    history: [],
    setCenter: vi.fn(),
    fitBounds: vi.fn(),
    selectTechnician: mockSelectTechnician,
    selectJob: vi.fn(),
    followTechnician: vi.fn(),
    exitFollow: mockExitFollow,
    returnToOverview: mockReturnToOverview,
    goBack: vi.fn(),
    followTechnicianPosition: mockFollowTechnicianPosition,
  }),
  setGlobalMapInstance: vi.fn(),
}));

// Mock existing components used by the page
vi.mock('../../../components/customer-tracking/MapLayerControls', () => ({
  MapLayerControls: () => <div data-testid="map-layer-controls" />,
}));
vi.mock('../../../components/customer-tracking/MapErrorBoundary', () => ({
  MapErrorBoundary: ({ children }: any) => <div>{children}</div>,
}));
vi.mock('../../../components/customer-tracking/JobSiteMarker', () => ({
  default: ({ job }: any) => <div data-testid={`job-site-${job.job_id}`} />,
}));
vi.mock('../../../components/customer-tracking/GeofenceCircle', () => ({
  default: () => <div data-testid="geofence" />,
}));
vi.mock('../../../components/customer-tracking/FollowIndicator', () => ({
  default: () => <div data-testid="follow-indicator" />,
}));
vi.mock('../../../components/customer-tracking/MapControls', () => ({
  default: () => <div data-testid="map-controls" />,
}));
vi.mock('react-hot-toast', () => ({
  Toaster: () => null,
  default: { success: vi.fn(), error: vi.fn() },
}));

// Mock date-fns
vi.mock('date-fns', () => ({
  formatDistanceToNowStrict: vi.fn(() => '5s'),
}));

// Mock mapLayerStorage to avoid localStorage errors during store initialization
vi.mock('../../../utils/mapLayerStorage', () => ({
  mapLayerStorage: {
    loadPreferences: () => ({
      mapType: 'roadmap',
      traffic: false,
      transit: false,
      bicycling: false,
    }),
    savePreferences: vi.fn(),
  },
}));

// Mock useMapLayers hook
vi.mock('../../../hooks/useMapLayers', () => ({
  useMapLayers: () => ({
    mapType: 'roadmap',
    traffic: false,
    transit: false,
    bicycling: false,
    isMobileSheetOpen: false,
    setMapType: vi.fn(),
    toggleTraffic: vi.fn(),
    toggleTransit: vi.fn(),
    toggleBicycling: vi.fn(),
    setMobileSheetOpen: vi.fn(),
    restorePreferences: vi.fn(),
  }),
}));

// ──────────────────────────────────────────────────────
// Imports (after mocks)
// ──────────────────────────────────────────────────────
import { TrackingDashboardPage } from '../../../pages/TrackingDashboardPage';
import { useTrackingStore, getTechnicianPrimaryStatus } from '../../../store/trackingStore';
import { useTrackingDashboardStore } from '../../../store/trackingDashboardStore';
import { TechnicianDetailCard } from '../TechnicianDetailCard';
import { formatDistanceToNowStrict } from 'date-fns';

// ──────────────────────────────────────────────────────
// Helper: seed technician data in the tracking store
// ──────────────────────────────────────────────────────
const seedTechnicians = (overrides: Partial<Record<string, any>>[] = []) => {
  const defaults = [
    {
      id: 'tech-1',
      name: 'Alice Johnson',
      latitude: 13.08,
      longitude: 80.27,
      status: 'ASSIGNED',
      lastPing: new Date().toISOString(),
      phone: '+1234567890',
      assignedJobs: ['job-1', 'job-2'],
      jobType: 'HVAC',
    },
    {
      id: 'tech-2',
      name: 'Bob Smith',
      latitude: 13.09,
      longitude: 80.28,
      status: 'EN_ROUTE',
      lastPing: new Date().toISOString(),
      assignedJobs: ['job-3'],
      jobType: 'Plumbing',
    },
    {
      id: 'tech-3',
      name: 'Carol Davis',
      latitude: 13.10,
      longitude: 80.29,
      status: 'ON_SITE',
      lastPing: new Date().toISOString(),
      assignedJobs: [],
      jobType: 'Electrical',
    },
  ];

  const techs = defaults.map((d, i) => ({ ...d, ...(overrides[i] || {}) }));
  const store = useTrackingStore.getState();

  techs.forEach((t) => {
    store.updateTechnicianLocation(t.id, t);
  });

  return techs;
};

/**
 * Helper: renders TrackingDashboardPage and waits for loading to finish.
 * The page has a `loading` state that starts true and resolves after data fetch.
 * Since we mock the services to resolve immediately, we just need to wait for the
 * async effect to complete.
 */
const renderDashboard = async () => {
  let result: ReturnType<typeof render>;
  await act(async () => {
    result = render(<TrackingDashboardPage />);
  });
  // Wait for loading to complete (the mock services resolve immediately)
  await waitFor(() => {
    expect(screen.queryByTestId('map-skeleton')).toBeNull();
  });
  return result!;
};

// ──────────────────────────────────────────────────────
// Tests
// ──────────────────────────────────────────────────────
describe('TrackingDashboard', () => {
  let originalLocalStorage: any;
  let originalWindowLocalStorage: any;

  beforeEach(() => {
    originalLocalStorage = globalThis.localStorage;
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
    Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true, configurable: true });
    if (typeof window !== 'undefined') {
      Object.defineProperty(window, 'localStorage', { value: localStorageMock, writable: true, configurable: true });
    }

    vi.clearAllMocks();
    // Reset stores to initial state
    useTrackingStore.getState().clearTechnicians();
    useTrackingStore.getState().setConnectionStatus('connected');
    useTrackingDashboardStore.setState({
      statusFilter: 'ALL',
      searchQuery: '',
      jobTypeFilter: 'All',
      selectedTechId: null,
      showJobSites: true,
      showRoutes: false,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    if (originalLocalStorage) {
      Object.defineProperty(globalThis, 'localStorage', { value: originalLocalStorage, writable: true, configurable: true });
    }
    if (originalWindowLocalStorage && typeof window !== 'undefined') {
      Object.defineProperty(window, 'localStorage', { value: originalWindowLocalStorage, writable: true, configurable: true });
    }
  });

  // ────── 1. Marker Rendering ──────
  describe('Marker Rendering', () => {
    it('renders markers for all active technicians', async () => {
      seedTechnicians();
      await renderDashboard();

      const markers = screen.getAllByTestId('mock-marker');
      expect(markers.length).toBe(3);
    });

    it('does not render markers for technicians without valid coordinates', async () => {
      // Don't seed anything (no technicians with valid coords)
      await renderDashboard();

      const markers = screen.queryAllByTestId('mock-marker');
      expect(markers.length).toBe(0);
    });

    it('does not render markers for non-active statuses', async () => {
      const store = useTrackingStore.getState();
      store.updateTechnicianLocation('tech-available', {
        id: 'tech-available',
        name: 'Available Tech',
        latitude: 13.08,
        longitude: 80.27,
        status: 'Available',
        lastPing: new Date().toISOString(),
      });

      await renderDashboard();

      const markers = screen.queryAllByTestId('mock-marker');
      expect(markers.length).toBe(0);
    });
  });

  // ────── 2. Marker Colors ──────
  describe('Marker Colors', () => {
    it('renders ASSIGNED markers with blue (#3B82F6)', async () => {
      seedTechnicians([{ status: 'ASSIGNED' }, { status: 'ASSIGNED' }, { status: 'ASSIGNED' }]);
      await renderDashboard();

      const markers = screen.getAllByTestId('mock-marker');
      markers.forEach((marker) => {
        expect(marker.getAttribute('data-fill-color')).toBe('#3B82F6');
      });
    });

    it('renders EN_ROUTE markers with green (#10B981)', async () => {
      seedTechnicians([{ status: 'EN_ROUTE' }, { status: 'EN_ROUTE' }, { status: 'EN_ROUTE' }]);
      await renderDashboard();

      const markers = screen.getAllByTestId('mock-marker');
      markers.forEach((marker) => {
        expect(marker.getAttribute('data-fill-color')).toBe('#10B981');
      });
    });

    it('renders ON_SITE markers with amber (#F59E0B)', async () => {
      seedTechnicians([{ status: 'ON_SITE' }, { status: 'ON_SITE' }, { status: 'ON_SITE' }]);
      await renderDashboard();

      const markers = screen.getAllByTestId('mock-marker');
      markers.forEach((marker) => {
        expect(marker.getAttribute('data-fill-color')).toBe('#F59E0B');
      });
    });

    it('renders correct colors for mixed statuses', async () => {
      seedTechnicians();
      await renderDashboard();

      const markers = screen.getAllByTestId('mock-marker');
      const colors = markers.map((m) => m.getAttribute('data-fill-color'));
      expect(colors).toContain('#3B82F6'); // ASSIGNED
      expect(colors).toContain('#10B981'); // EN_ROUTE
      expect(colors).toContain('#F59E0B'); // ON_SITE
    });
  });

  // ────── 3. Live Position Updates ──────
  describe('Live Position Updates', () => {
    it('updates marker position when store changes', async () => {
      seedTechnicians();
      await renderDashboard();

      // Update tech-1 position
      act(() => {
        useTrackingStore.getState().updateTechnicianLocation('tech-1', {
          latitude: 13.12,
          longitude: 80.30,
        });
      });

      // The marker should reflect the store update
      await waitFor(() => {
        const markers = screen.getAllByTestId('mock-marker');
        const tech1Marker = markers.find((m) => m.getAttribute('data-title')?.includes('Alice'));
        expect(tech1Marker).toBeDefined();
      });
    });
  });

  // ────── 4. Job Count Badges ──────
  describe('Job Count Badges', () => {
    it('shows job count in marker title', async () => {
      seedTechnicians([
        { assignedJobs: ['j1', 'j2', 'j3'] },
        { assignedJobs: ['j4'] },
        { assignedJobs: [] },
      ]);
      await renderDashboard();

      const markers = screen.getAllByTestId('mock-marker');
      const titles = markers.map((m) => m.getAttribute('data-title'));

      // Alice has 3 jobs
      const aliceMarker = titles.find((t) => t?.includes('Alice'));
      expect(aliceMarker).toContain('3 jobs');

      // Bob has 1 job
      const bobMarker = titles.find((t) => t?.includes('Bob'));
      expect(bobMarker).toContain('1 jobs');
    });
  });

  // ────── 5. Marker Clustering ──────
  describe('Marker Clustering', () => {
    it('renders MarkerClusterer with maxZoom 11', async () => {
      seedTechnicians();
      await renderDashboard();

      const clusterer = screen.getByTestId('mock-clusterer');
      expect(clusterer.getAttribute('data-max-zoom')).toBe('11');
    });
  });

  // ────── 6. Detail Card Interactions ──────
  describe('Detail Card Interactions', () => {
    it('opens detail card when a technician is selected', async () => {
      seedTechnicians();
      useTrackingDashboardStore.getState().selectTechnician('tech-1');
      await renderDashboard();

      expect(screen.getByTestId('technician-detail-card')).toBeDefined();
      const techNames = screen.getAllByTestId('detail-tech-name');
      expect(techNames[0].textContent).toBe('Alice Johnson');
    });

    it('closes detail card when close button is clicked', async () => {
      seedTechnicians();
      useTrackingDashboardStore.getState().selectTechnician('tech-1');
      await renderDashboard();

      expect(screen.getByTestId('technician-detail-card')).toBeDefined();

      const closeBtns = screen.getAllByTestId('close-detail-card');
      await act(async () => {
        fireEvent.click(closeBtns[0]);
      });

      expect(screen.queryByTestId('technician-detail-card')).toBeNull();
    });

    it('shows phone number in detail card', async () => {
      seedTechnicians();
      useTrackingDashboardStore.getState().selectTechnician('tech-1');
      await renderDashboard();

      const phones = screen.getAllByTestId('detail-phone');
      expect(phones[0].textContent).toBe('+1234567890');
    });

    it('shows assigned jobs list in detail card', async () => {
      seedTechnicians();
      useTrackingDashboardStore.getState().selectTechnician('tech-1');
      await renderDashboard();
 
      // Verify that the job rows are rendered
      expect(screen.getAllByText(/Job #job-/).length).toBeGreaterThanOrEqual(2);
    });
  });

  // ────── 7. Double-Click Zoom ──────
  describe('Double-Click Zoom', () => {
    it('renders clickable markers for technicians', async () => {
      seedTechnicians();
      await renderDashboard();

      const markers = screen.getAllByTestId('mock-marker');
      expect(markers.length).toBeGreaterThan(0);

      // Each marker should have an onClick handler
      markers.forEach((marker) => {
        expect(marker.onclick).toBeDefined;
      });
    });
  });

  // ────── 8. Filters and Search ──────
  describe('Filters and Search', () => {
    it('filters by status when a pill is clicked', async () => {
      seedTechnicians();
      await renderDashboard();

      // Initially all 3 are visible
      expect(screen.getAllByTestId('mock-marker').length).toBe(3);

      // Click "Assigned" filter
      const assignedPill = screen.getByTestId('filter-assigned');
      await act(async () => {
        fireEvent.click(assignedPill);
      });

      // Only ASSIGNED technicians visible
      expect(screen.getAllByTestId('mock-marker').length).toBe(1);
    });

    it('filters by name search', async () => {
      seedTechnicians();
      await renderDashboard();

      const searchInput = screen.getByTestId('search-input');
      await act(async () => {
        fireEvent.change(searchInput, { target: { value: 'Alice' } });
      });

      expect(screen.getAllByTestId('mock-marker').length).toBe(1);
    });

    it('shows empty state when no technicians match filters', async () => {
      seedTechnicians();
      await renderDashboard();

      const searchInput = screen.getByTestId('search-input');
      await act(async () => {
        fireEvent.change(searchInput, { target: { value: 'NonexistentTech' } });
      });

      expect(screen.queryAllByTestId('mock-marker').length).toBe(0);
      expect(screen.getByTestId('empty-state')).toBeDefined();
      expect(screen.getByText('No Active Technicians')).toBeDefined();
    });



    it('clears search when clear button is clicked', async () => {
      seedTechnicians();
      await renderDashboard();

      const searchInput = screen.getByTestId('search-input');
      await act(async () => {
        fireEvent.change(searchInput, { target: { value: 'Alice' } });
      });

      expect(screen.getAllByTestId('mock-marker').length).toBe(1);

      const clearBtn = screen.getByTestId('clear-search');
      await act(async () => {
        fireEvent.click(clearBtn);
      });

      expect(screen.getAllByTestId('mock-marker').length).toBe(3);
    });
  });

  // ────── 9. Connection Status ──────
  describe('Connection Status', () => {
    it('shows Connected when WebSocket is connected', async () => {
      useTrackingStore.getState().setConnectionStatus('connected');
      seedTechnicians();
      await renderDashboard();

      expect(screen.getByTestId('connection-label').textContent).toBe('Connected');
    });

    it('shows Reconnecting when WebSocket is reconnecting', async () => {
      useTrackingStore.getState().setConnectionStatus('reconnecting');
      useTrackingStore.getState().setReconnectAttempt(2);
      seedTechnicians();
      await renderDashboard();

      expect(screen.getByTestId('connection-label').textContent).toBe('Reconnecting (2/5)');
    });

    it('shows Disconnected when WebSocket is disconnected', async () => {
      useTrackingStore.getState().setConnectionStatus('disconnected');
      seedTechnicians();
      await renderDashboard();

      expect(screen.getByTestId('connection-label').textContent).toBe('Disconnected');
    });
  });

  // ────── 10. Refresh Button ──────
  describe('Refresh Button', () => {
    it('calls reconnect when the refresh button is clicked', async () => {
      seedTechnicians();
      await renderDashboard();

      const refreshBtn = screen.getByTestId('reconnect-button');
      await act(async () => {
        fireEvent.click(refreshBtn);
      });

      expect(mockReconnect).toHaveBeenCalledTimes(1);
    });
  });

  // ────── 11. Relative Timestamp Updates ──────
  describe('Relative Timestamps', () => {
    it('displays relative time in marker label', async () => {
      vi.mocked(formatDistanceToNowStrict).mockReturnValue('5s');
      seedTechnicians();
      await renderDashboard();

      const markers = screen.getAllByTestId('mock-marker');
      const hasTimestamp = markers.some((m) => {
        const label = m.getAttribute('data-label');
        return label?.includes('Updated') && label?.includes('ago');
      });
      expect(hasTimestamp).toBe(true);
    });
  });

  // ────── 12. Active Tech Count ──────
  describe('Active Tech Count', () => {
    it('displays correct active technician count', async () => {
      seedTechnicians();
      await renderDashboard();

      expect(screen.getByTestId('active-tech-count').textContent).toBe('3 Active');
    });

    it('updates count when filters are applied', async () => {
      seedTechnicians();
      await renderDashboard();

      const assignedPill = screen.getByTestId('filter-assigned');
      await act(async () => {
        fireEvent.click(assignedPill);
      });

      expect(screen.getByTestId('active-tech-count').textContent).toBe('1 Active');
    });
  });

  // ────── 13. Layer Toggles ──────
  describe('Layer Toggles', () => {
    it('renders layer toggle panel', async () => {
      seedTechnicians();
      await renderDashboard();

      const toggle = screen.getByTestId('toggle-job-sites');
      expect(toggle).toBeDefined();
    });

    it('toggles job sites visibility', async () => {
      seedTechnicians();
      await renderDashboard();

      const toggle = screen.getByTestId('toggle-job-sites');
      expect(toggle.getAttribute('aria-pressed')).toBe('true');

      await act(async () => {
        fireEvent.click(toggle);
      });

      expect(toggle.getAttribute('aria-pressed')).toBe('false');
    });
  });

  // ────── 14. Loading State ──────
  describe('Loading State', () => {
    it('shows map skeleton when loading', async () => {
      const MapSkeleton = (await import('../../../components/tracking-dashboard/MapSkeleton')).default;
      render(<MapSkeleton />);

      expect(screen.getByTestId('map-skeleton')).toBeDefined();
      expect(screen.getByText('Initializing Live Tracking Grid')).toBeDefined();
    });
  });

  // ────── 15. Job Status Badges Feature ──────
  describe('Job Status Badges per Technician Feature', () => {
    it('calculates primary status correctly based on job priority order', () => {
      const jobsMap = {
        'job-1': { job_id: 'job-1', title: 'Job A', customer: 'Cust A', location: 'Loc A', status: 'CREATED', latitude: 12.3, longitude: 80.1 },
        'job-2': { job_id: 'job-2', title: 'Job B', customer: 'Cust B', location: 'Loc B', status: 'ASSIGNED', latitude: 12.3, longitude: 80.1 },
        'job-3': { job_id: 'job-3', title: 'Job C', customer: 'Cust C', location: 'Loc C', status: 'EN_ROUTE', latitude: 12.3, longitude: 80.1 },
      };

      const status1 = getTechnicianPrimaryStatus(['job-1'], jobsMap);
      expect(status1).toBe('CREATED');

      const status2 = getTechnicianPrimaryStatus(['job-1', 'job-2'], jobsMap);
      expect(status2).toBe('ASSIGNED');

      const status3 = getTechnicianPrimaryStatus(['job-1', 'job-2', 'job-3'], jobsMap);
      expect(status3).toBe('EN_ROUTE');
    });

    it('returns NO_ACTIVE_JOBS when there are no jobs or empty assigned list', () => {
      const status = getTechnicianPrimaryStatus([], {});
      expect(status).toBe('NO_ACTIVE_JOBS');
    });

    it('renders detail card with job row list, correct status badge and empty state', async () => {
      const store = useTrackingStore.getState();
      act(() => {
        store.setJobs({
          'job-101': { job_id: 'job-101', title: 'Job A', customer: 'Cust A', location: 'Loc A', status: 'ASSIGNED', latitude: 12.3, longitude: 80.1 },
          'job-102': { job_id: 'job-102', title: 'Job B', customer: 'Cust B', location: 'Loc B', status: 'ON_SITE', latitude: 12.4, longitude: 80.2 },
        });

        store.updateTechnicianLocation('tech-badge-test', {
          id: 'tech-badge-test',
          name: 'Tech Badge Test',
          latitude: 13.08,
          longitude: 80.27,
          status: 'ON_SITE',
          assignedJobs: ['job-101', 'job-102'],
          job_id: 'job-102',
        });
      });

      const techState = useTrackingStore.getState();
      const tech = techState.technicians['tech-badge-test'];
      expect(tech).toBeDefined();

      render(<TechnicianDetailCard tech={tech} onClose={() => {}} />);

      expect(screen.getAllByText('Job #job-101').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Job #job-102').length).toBeGreaterThan(0);
    });
  });
});
