import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

import { ETACountdown } from '../ETACountdown';
import { JobData } from '../../../store/trackingStore';

describe('ETACountdown Component', () => {
  const baseJob: JobData = {
    job_id: 'job-test',
    title: 'Test Job',
    customer: 'Cust Name',
    location: 'Loc Address',
    status: 'EN_ROUTE',
    latitude: 13.08,
    longitude: 80.27,
    eta_source: 'calculated',
  };

  beforeEach(() => {
    vi.useFakeTimers();
    if (typeof window !== 'undefined') {
      global.localStorage = window.localStorage;
    }
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('renders correctly with default calculating state', () => {
    const job = { ...baseJob, eta_duration_minutes: undefined, eta_source: 'calculating' };
    render(<ETACountdown job={job} />);
    expect(screen.getAllByText('Calculating...').length).toBeGreaterThan(0);
    expect(screen.getByTestId('source-calculating-dot')).toBeDefined();
  });

  it('formats remaining time correctly for various duration values', () => {
    const testCases = [
      { mins: 135, expected: '2h 15m' },
      { mins: 45, expected: '45m' },
      { mins: 5.5, expected: '5m 30s' },
      { mins: 1, expected: '1m' },
      { mins: 0.5, expected: 'Arriving now' },
    ];

    testCases.forEach(({ mins, expected }) => {
      const { container, unmount } = render(
        <ETACountdown job={{ ...baseJob, eta_duration_minutes: mins }} />
      );
      const timerElement = screen.getByTestId('countdown-timer');
      expect(timerElement.textContent).toBe(expected);
      unmount();
    });
  });

  it('decrements countdown timer every 10 seconds', async () => {
    const { act } = await import('@testing-library/react');
    render(<ETACountdown job={{ ...baseJob, eta_duration_minutes: 5 }} />);
    const timer = screen.getByTestId('countdown-timer');
    expect(timer.textContent).toBe('5m');

    // Advance 10 seconds
    await act(async () => {
      vi.advanceTimersByTime(10000);
    });
    expect(timer.textContent).toBe('4m 50s');

    // Advance another 10 seconds
    await act(async () => {
      vi.advanceTimersByTime(10000);
    });
    expect(timer.textContent).toBe('4m 40s');
  });

  it('shows Arrived state when status is ON_SITE', () => {
    const job = { ...baseJob, status: 'ON_SITE', eta_duration_minutes: 5 };
    render(<ETACountdown job={job} />);
    expect(screen.getByTestId('eta-arrived-state')).toBeDefined();
    expect(screen.getByText('Arrived')).toBeDefined();
  });

  it('applies color classes based on remaining time thresholds', () => {
    const greenJob = { ...baseJob, eta_duration_minutes: 35 }; // > 30 mins
    const amberJob = { ...baseJob, eta_duration_minutes: 20 }; // 15-30 mins
    const redJob = { ...baseJob, eta_duration_minutes: 10 };   // < 15 mins

    const { container: gContainer, unmount: gUnmount } = render(<ETACountdown job={greenJob} />);
    expect(screen.getByTestId('countdown-timer').className).toContain('text-emerald-500');
    gUnmount();

    const { container: aContainer, unmount: aUnmount } = render(<ETACountdown job={amberJob} />);
    expect(screen.getByTestId('countdown-timer').className).toContain('text-amber-500');
    aUnmount();

    const { container: rContainer, unmount: rUnmount } = render(<ETACountdown job={redJob} />);
    expect(screen.getByTestId('countdown-timer').className).toContain('text-red-500');
    rUnmount();
  });

  it('renders Google Maps Live source badge for calculated source', () => {
    const job = { ...baseJob, eta_source: 'calculated', fallback: false };
    render(<ETACountdown job={job} />);
    expect(screen.getByTestId('source-live-dot')).toBeDefined();
    expect(screen.getByText('Live')).toBeDefined();
  });

  it('renders Fallback Estimated badge when source is estimated or fallback is true', () => {
    const fallbackJob1 = { ...baseJob, eta_source: 'estimated' };
    const { unmount } = render(<ETACountdown job={fallbackJob1} />);
    expect(screen.getByTestId('source-fallback-dot')).toBeDefined();
    expect(screen.getByText('Estimated')).toBeDefined();
    unmount();

    const fallbackJob2 = { ...baseJob, eta_source: 'calculated', fallback: true };
    render(<ETACountdown job={fallbackJob2} />);
    expect(screen.getByTestId('source-fallback-dot')).toBeDefined();
    expect(screen.getByText('Estimated')).toBeDefined();
  });

  it('renders traffic warning banner if delay exceeds 10 minutes', () => {
    const job = { ...baseJob, traffic_delay_minutes: 12.4 };
    render(<ETACountdown job={job} />);
    expect(screen.getByTestId('traffic-warning-banner')).toBeDefined();
    expect(screen.getByText('Traffic delay: +12 min')).toBeDefined();
  });

  it('renders Delayed badge when current ETA duration exceeds first ETA duration by > 15 minutes', () => {
    const job = {
      ...baseJob,
      first_eta_duration_minutes: 20,
      eta_duration_minutes: 38.3,
    };
    render(<ETACountdown job={job} />);
    expect(screen.getByTestId('delay-badge')).toBeDefined();
    expect(screen.getByText('Delayed +18 min')).toBeDefined();
  });

  it('renders Late badge when ETA is past SLA deadline', () => {
    const job = {
      ...baseJob,
      sla_deadline: '2026-06-30T10:00:00.000Z',
      eta: '2026-06-30T10:10:00.000Z',
      eta_duration_minutes: 10,
    };
    render(<ETACountdown job={job} />);
    expect(screen.getByTestId('late-badge')).toBeDefined();
    expect(screen.getByText('Late by 10 min')).toBeDefined();
  });

  it('renders sparkline SVG trend line if history data is present', () => {
    const job = {
      ...baseJob,
      eta_history: [25, 23, 24, 22, 20],
      eta_duration_minutes: 20,
    };
    const { container } = render(<ETACountdown job={job} />);
    expect(screen.getByTestId('eta-sparkline')).toBeDefined();
    expect(container.querySelector('svg')).not.toBeNull();
  });
});
