import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';
import { useTrackingStore } from '../../../store/trackingStore';
import { SLACountdown } from '../SLACountdown';
import { JobInfoWindow } from '../JobInfoWindow';
import { GeofenceCircle } from '../GeofenceCircle';

// Mock Zustand Store
vi.mock('../../../store/trackingStore', () => {
  let radii: Record<string, number> = { 'job-1': 100 };
  const store = {
    geofenceRadii: radii,
    setGeofenceRadius: vi.fn((jobId, val) => {
      radii[jobId] = val;
    }),
  };
  return {
    useTrackingStore: () => store,
  };
});

// Mock @react-google-maps/api
vi.mock('@react-google-maps/api', () => ({
  InfoWindowF: ({ children, onCloseClick }: any) => (
    <div data-testid="mock-infowindow">
      <button onClick={onCloseClick}>Close</button>
      {children}
    </div>
  ),
  CircleF: ({ options, center, radius }: any) => (
    <div
      data-testid="mock-circle"
      data-color={options.strokeColor}
      data-opacity={options.fillOpacity}
      data-radius={radius}
      data-lat={center.lat}
      data-lng={center.lng}
    />
  ),
}));

describe('Geofence Components', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    const store = useTrackingStore();
    store.geofenceRadii['job-1'] = 100;
  });

  describe('SLACountdown', () => {
    it('renders remaining minutes when deadline is in the future', () => {
      // Set deadline 30 minutes in the future
      const future = new Date(Date.now() + 30 * 60 * 1000).toISOString();
      render(<SLACountdown deadline={future} />);
      expect(screen.getByText(/30m remaining/)).toBeDefined();
    });

    it('renders OVERDUE when deadline has passed', () => {
      // Set deadline 5 minutes in the past
      const past = new Date(Date.now() - 5 * 60 * 1000).toISOString();
      render(<SLACountdown deadline={past} />);
      expect(screen.getByText('OVERDUE')).toBeDefined();
    });
  });

  describe('JobInfoWindow', () => {
    const job = {
      job_id: 'job-1',
      title: 'Fix Air Conditioner',
      customer: 'Alice Jenkins',
      location: '123 Coconut Grove, Chennai',
      status: 'ASSIGNED',
      sla_deadline: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
      latitude: 13.0827,
      longitude: 80.2707,
    };

    const techInside = [
      {
        id: 'tech-1',
        name: 'Vijay Kumar',
        latitude: 13.0825,
        longitude: 80.2705,
        status: 'EN_ROUTE',
        lastPing: new Date().toISOString(),
      },
    ];

    it('renders job details and slider correctly', () => {
      const onClose = vi.fn();
      render(<JobInfoWindow job={job} techniciansInside={techInside} onClose={onClose} />);

      expect(screen.getByText('Fix Air Conditioner')).toBeDefined();
      expect(screen.getByText('Alice Jenkins')).toBeDefined();
      expect(screen.getByText('123 Coconut Grove, Chennai')).toBeDefined();
      expect(screen.getByText('Vijay Kumar')).toBeDefined();
      expect(screen.getByText('EN_ROUTE')).toBeDefined();
    });

    it('allows changing geofence radius via slider input', () => {
      const onClose = vi.fn();
      render(<JobInfoWindow job={job} techniciansInside={[]} onClose={onClose} />);

      const slider = screen.getByRole('slider') as HTMLInputElement;
      expect(slider.value).toBe('100');

      fireEvent.change(slider, { target: { value: '250' } });
      const store = useTrackingStore();
      expect(store.setGeofenceRadius).toHaveBeenCalledWith('job-1', 250);
    });
  });

  describe('GeofenceCircle', () => {
    it('renders base circle with correct radius', () => {
      const job = {
        job_id: 'job-1',
        latitude: 13.0827,
        longitude: 80.2707,
        status: 'ASSIGNED',
        sla_deadline: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
      };

      render(<GeofenceCircle job={job} />);
      const circles = screen.getAllByTestId('mock-circle');
      
      // Base circle
      expect(circles[0].getAttribute('data-radius')).toBe('100');
      // Blue for Pending/Assigned
      expect(circles[0].getAttribute('data-color')).toBe('#3B82F6');
    });

    it('colors circle green when status is active (e.g. EN_ROUTE) and runs pulse', () => {
      const job = {
        job_id: 'job-1',
        latitude: 13.0827,
        longitude: 80.2707,
        status: 'EN_ROUTE',
        sla_deadline: new Date(Date.now() + 60 * 60 * 1000).toISOString(),
      };

      render(<GeofenceCircle job={job} />);
      const circles = screen.getAllByTestId('mock-circle');
      
      // Green color code
      expect(circles[0].getAttribute('data-color')).toBe('#10B981');
      // Verify pulsing circle exists
      expect(circles.length).toBe(2);
    });

    it('colors circle red when SLA is overdue', () => {
      const job = {
        job_id: 'job-1',
        latitude: 13.0827,
        longitude: 80.2707,
        status: 'ASSIGNED',
        sla_deadline: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
      };

      render(<GeofenceCircle job={job} />);
      const circles = screen.getAllByTestId('mock-circle');
      expect(circles[0].getAttribute('data-color')).toBe('#EF4444');
    });
  });
});
