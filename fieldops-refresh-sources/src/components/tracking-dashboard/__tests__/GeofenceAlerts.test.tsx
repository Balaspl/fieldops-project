import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';


import { useNotificationStore } from '../../../store/notificationStore';
import { NotificationBell } from '../NotificationBell';
import { NotificationPanel } from '../NotificationPanel';
import { GeofenceAlertToast, GeofenceToastContainer } from '../GeofenceAlertToast';
import TrackingTechnicianMarker from '../TrackingTechnicianMarker';
import GeofenceCircle from '../../customer-tracking/GeofenceCircle';

// Mock Web Audio API AudioContext using constructible function
const mockOscillator = {
  connect: vi.fn(),
  start: vi.fn(),
  stop: vi.fn(),
  frequency: {
    setValueAtTime: vi.fn(),
  },
};
const mockGain = {
  connect: vi.fn(),
  gain: {
    setValueAtTime: vi.fn(),
    exponentialRampToValueAtTime: vi.fn(),
  },
};
const mockAudioContext = vi.fn().mockImplementation(function (this: any) {
  this.createOscillator = vi.fn().mockReturnValue(mockOscillator);
  this.createGain = vi.fn().mockReturnValue(mockGain);
  this.destination = {};
  this.currentTime = 0;
});
vi.stubGlobal('AudioContext', mockAudioContext);

// Mock @react-google-maps/api CircleF and MarkerF
vi.mock('@react-google-maps/api', () => ({
  CircleF: vi.fn().mockImplementation(({ options, radius }) => (
    <div data-testid="google-circle" data-radius={radius} data-opacity={options?.fillOpacity} />
  )),
  MarkerF: vi.fn().mockImplementation(({ label }) => (
    <div data-testid="google-marker" data-label={label.text} />
  )),
}));

// Mock trackingStore
vi.mock('../../../store/trackingStore', () => ({
  useTrackingStore: vi.fn().mockReturnValue({
    geofenceRadii: {},
  }),
}));

describe('Geofence Alerts System Tests', () => {
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

    useNotificationStore.getState().clearAlerts();
    useNotificationStore.setState({
      soundEnabled: true,
      autoDismiss: true,
      isPanelOpen: false,
      activeToasts: [],
      activeAnimations: {},
    });
    localStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
    if (originalLocalStorage) {
      Object.defineProperty(global, 'localStorage', { value: originalLocalStorage, writable: true, configurable: true });
    }
    if (originalWindowLocalStorage && typeof window !== 'undefined') {
      Object.defineProperty(window, 'localStorage', { value: originalWindowLocalStorage, writable: true, configurable: true });
    }
  });

  it('correctly maps and saves alerts in notificationStore', () => {
    const store = useNotificationStore.getState();
    expect(store.alerts.length).toBe(0);

    act(() => {
      store.addAlert({
        techId: 'tech-1',
        techName: 'Raj',
        jobId: 'job-101',
        jobTitle: 'AC Repair',
        jobLocation: '123 Main St',
        eventType: 'ENTRY',
        timestamp: new Date().toISOString(),
      });
    });

    const updated = useNotificationStore.getState();
    expect(updated.alerts.length).toBe(1);
    expect(updated.alerts[0].techName).toBe('Raj');
    expect(updated.alerts[0].isRead).toBe(false);
  });

  it('plays chime sound on ENTRY when preference is enabled, and does not play on EXIT', () => {
    const audioContextSpy = vi.spyOn(window, 'AudioContext');
    const store = useNotificationStore.getState();

    act(() => {
      store.addAlert({
        techId: 'tech-1',
        techName: 'Raj',
        jobId: 'job-101',
        jobTitle: 'AC Repair',
        jobLocation: '123 Main St',
        eventType: 'ENTRY',
        timestamp: new Date().toISOString(),
      });
    });

    expect(audioContextSpy).toHaveBeenCalled();
    audioContextSpy.mockClear();

    // Now test with sound preference disabled
    act(() => {
      useNotificationStore.getState().setSoundEnabled(false);
      useNotificationStore.getState().addAlert({
        techId: 'tech-2',
        techName: 'Bob',
        jobId: 'job-102',
        jobTitle: 'Fridge Fix',
        jobLocation: '456 Elm St',
        eventType: 'ENTRY',
        timestamp: new Date().toISOString(),
      });
    });
    expect(audioContextSpy).not.toHaveBeenCalled();
    audioContextSpy.mockClear();

    // Now test EXIT events (sound should not play on exit)
    act(() => {
      useNotificationStore.getState().setSoundEnabled(true);
      useNotificationStore.getState().addAlert({
        techId: 'tech-3',
        techName: 'Alice',
        jobId: 'job-103',
        jobTitle: 'Leaky Pipe',
        jobLocation: '789 Oak St',
        eventType: 'EXIT',
        timestamp: new Date().toISOString(),
      });
    });
    expect(audioContextSpy).not.toHaveBeenCalled();
  });

  it('groups alerts by job in the notification panel and sorts them newest first', () => {
    act(() => {
      useNotificationStore.getState().addAlert({
        techId: 'tech-1',
        techName: 'Raj',
        jobId: 'job-101',
        jobTitle: 'AC Repair',
        jobLocation: '123 Main St',
        eventType: 'ENTRY',
        timestamp: new Date(Date.now() - 60000).toISOString(), // 1m ago
      });
      useNotificationStore.getState().addAlert({
        techId: 'tech-2',
        techName: 'Alice',
        jobId: 'job-101',
        jobTitle: 'AC Repair',
        jobLocation: '123 Main St',
        eventType: 'EXIT',
        timestamp: new Date().toISOString(), // Just now
      });
    });

    render(<NotificationPanel />);
    expect(screen.getByTestId('job-group-job-101')).toBeTruthy();
    
    // Check unread count dot
    const unreadDots = screen.getAllByTestId('unread-dot');
    expect(unreadDots.length).toBe(2);
  });

  it('marks single alert as read on click, and clears all alerts', () => {
    act(() => {
      useNotificationStore.getState().addAlert({
        techId: 'tech-1',
        techName: 'Raj',
        jobId: 'job-101',
        jobTitle: 'AC Repair',
        jobLocation: '123 Main St',
        eventType: 'ENTRY',
        timestamp: new Date().toISOString(),
      });
    });

    render(<NotificationPanel />);
    const alertItem = screen.getByTestId(/^alert-item-/);
    
    // Click single item to mark as read
    fireEvent.click(alertItem);
    expect(useNotificationStore.getState().alerts[0].isRead).toBe(true);

    // Clear all alerts
    const clearBtn = screen.getByTestId('clear-all');
    fireEvent.click(clearBtn);
    expect(useNotificationStore.getState().alerts.length).toBe(0);
  });

  it('renders notification bell badge up to 99+', () => {
    render(<NotificationBell />);
    expect(screen.queryByTestId('bell-badge')).toBeNull();

    // Add 5 alerts
    act(() => {
      for (let i = 0; i < 5; i++) {
        useNotificationStore.getState().addAlert({
          techId: `tech-${i}`,
          techName: `Tech ${i}`,
          jobId: 'job-1',
          jobTitle: 'Job',
          jobLocation: 'Loc',
          eventType: 'ENTRY',
          timestamp: new Date().toISOString(),
        });
      }
    });
    expect(screen.getByTestId('bell-badge').textContent).toBe('5');

    // Add 100 alerts to verify 99+ ceiling
    act(() => {
      for (let i = 5; i < 105; i++) {
        useNotificationStore.getState().addAlert({
          techId: `tech-${i}`,
          techName: `Tech ${i}`,
          jobId: 'job-1',
          jobTitle: 'Job',
          jobLocation: 'Loc',
          eventType: 'ENTRY',
          timestamp: new Date().toISOString(),
        });
      }
    });
    expect(screen.getByTestId('bell-badge').textContent).toBe('99+');
  });

  it('correctly handles toast auto-dismiss countdown with hover pausing', () => {
    act(() => {
      useNotificationStore.getState().addAlert({
        techId: 'tech-1',
        techName: 'Raj',
        jobId: 'job-1',
        jobTitle: 'AC Repair',
        jobLocation: '123 Main St',
        eventType: 'ENTRY',
        timestamp: new Date().toISOString(),
      });
    });

    render(<GeofenceToastContainer />);
    const toastElem = screen.getByRole('alert');
    expect(toastElem).toBeTruthy();

    // Advance 10s: timer decrements
    act(() => {
      vi.advanceTimersByTime(10000);
    });
    expect(screen.getByText(/Auto-dismissing in 20s/)).toBeTruthy();

    // Hover mouse over toast: check timer pause
    fireEvent.mouseEnter(toastElem);
    act(() => {
      vi.advanceTimersByTime(10000);
    });
    // Text stays 20s because it is paused
    expect(screen.getByText(/Auto-dismissing in 20s \(paused\)/)).toBeTruthy();

    // Unhover: timer resumes
    fireEvent.mouseLeave(toastElem);
    act(() => {
      vi.advanceTimersByTime(20000);
    });
    // Toast gets dismissed
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('technician marker prepends unread dot indicator and clears it once read', () => {
    const tech = {
      id: 'tech-1',
      name: 'Raj',
      latitude: 10,
      longitude: 20,
      status: 'ASSIGNED',
      jobCount: 0,
      job_id: 'job-1',
      lastPing: new Date().toISOString(),
      accuracy: 10,
      altitude: 0,
      eta: null,
      eta_duration_minutes: null,
    };

    const { rerender } = render(
      <TrackingTechnicianMarker tech={tech} onSelect={vi.fn()} onZoomTo={vi.fn()} />
    );

    // Initial label contains name without red dot
    let label = screen.getByTestId('google-marker').getAttribute('data-label') || '';
    expect(label).toContain('Raj');
    expect(label).not.toContain('🔴');

    // Add unread alert
    act(() => {
      useNotificationStore.getState().addAlert({
        techId: 'tech-1',
        techName: 'Raj',
        jobId: 'job-1',
        jobTitle: 'AC Repair',
        jobLocation: 'Loc',
        eventType: 'ENTRY',
        timestamp: new Date().toISOString(),
      });
    });

    rerender(<TrackingTechnicianMarker tech={tech} onSelect={vi.fn()} onZoomTo={vi.fn()} />);
    label = screen.getByTestId('google-marker').getAttribute('data-label') || '';
    expect(label).toContain('🔴');
    expect(label).toContain('Raj');

    // Mark all as read
    act(() => {
      useNotificationStore.getState().markAllAsRead();
    });

    rerender(<TrackingTechnicianMarker tech={tech} onSelect={vi.fn()} onZoomTo={vi.fn()} />);
    label = screen.getByTestId('google-marker').getAttribute('data-label') || '';
    expect(label).toContain('Raj');
    expect(label).not.toContain('🔴');
  });

  it('triggers geofence circle pulse expanding animation on alert arrival', async () => {
    const job = {
      job_id: 'job-1',
      latitude: 10,
      longitude: 20,
      status: 'ASSIGNED',
      sla_deadline: null,
    };

    render(<GeofenceCircle job={job} />);

    // Initially, only base circle is rendered
    let circles = screen.getAllByTestId('google-circle');
    expect(circles.length).toBe(1);

    // Trigger animation
    act(() => {
      useNotificationStore.getState().triggerGeofenceAnimation('job-1');
    });

    // Ring animation is triggered, rendering 3 additional rings + 1 base ring = 4 circles total
    circles = screen.getAllByTestId('google-circle');
    expect(circles.length).toBe(4);

    // Tick forward 2.5 seconds to complete animation
    act(() => {
      vi.advanceTimersByTime(2500);
    });

    // Concentric expanding animation completes and returns to only base circle
    circles = screen.getAllByTestId('google-circle');
    expect(circles.length).toBe(1);
  });
});
