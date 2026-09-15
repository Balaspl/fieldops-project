import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import axios from 'axios';
import api from '../../../services/api';
import { JobStatusTimeline } from '../JobStatusTimeline';
import { DurationBadge, formatDurationString } from '../DurationBadge';
import { SLABreachBadge } from '../SLABreachBadge';
import { ActorBadge, getInitials } from '../ActorBadge';

// Mock API Client
vi.mock('../../../services/api', () => ({
  default: {
    get: vi.fn(),
  },
}));

// Mock scrollIntoView
const mockScrollIntoView = vi.fn();
window.HTMLElement.prototype.scrollIntoView = mockScrollIntoView;

describe('Job Status Timeline System', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockScrollIntoView.mockClear();
  });

  describe('Duration Parsing Utilities', () => {
    it('formats duration ranges correctly', () => {
      expect(formatDurationString(30)).toBe('< 1 min');
      expect(formatDurationString(900)).toBe('15m');
      expect(formatDurationString(8100)).toBe('2h 15m');
      expect(formatDurationString(86400 + 14400)).toBe('1d 4h');
    });
  });

  describe('Actor Profile Initials Extraction', () => {
    it('creates initials fallback characters from names', () => {
      expect(getInitials('Vijay Iyer')).toBe('VI');
      expect(getInitials('Manoj Bajpayee')).toBe('MB');
      expect(getInitials('Vijay')).toBe('VI');
      expect(getInitials('')).toBe('U');
    });
  });

  describe('Sub-Components Rendering', () => {
    it('renders ActorBadge with name and role', () => {
      render(<ActorBadge name="Rajesh Kumar" role="Admin" />);
      expect(screen.getByText('Rajesh Kumar')).toBeDefined();
      expect(screen.getByText('Admin')).toBeDefined();
    });

    it('renders SLABreachBadge when duration exceeds target limit', () => {
      render(<SLABreachBadge durationSeconds={3600} slaLimitSeconds={1800} />);
      expect(screen.getByText('SLA BREACHED')).toBeDefined();
    });

    it('does not render SLABreachBadge if SLA limits are satisfied', () => {
      const { container } = render(<SLABreachBadge durationSeconds={900} slaLimitSeconds={1800} />);
      expect(container.firstChild).toBeNull();
    });
  });

  describe('JobStatusTimeline Layout Wrapper', () => {
    const mockHistory = [
      {
        id: 1,
        job_id: 10,
        from_status: null,
        to_status: 'CREATED',
        changed_at: new Date(Date.now() - 600000).toISOString(),
        changed_by_name: 'Rajesh Kumar',
        changed_by_role: 'Admin',
        transition_reason: null,
        duration_seconds: 60,
        sla_limit_seconds: 300,
      },
      {
        id: 2,
        job_id: 10,
        from_status: 'CREATED',
        to_status: 'ASSIGNED',
        changed_at: new Date().toISOString(),
        changed_by_name: 'Vijay Iyer',
        changed_by_role: 'Technician',
        transition_reason: 'Assigned tech on site',
        duration_seconds: 540,
        sla_limit_seconds: 300, // SLA Breached!
      },
    ];

    it('renders loading skeleton initially', () => {
      vi.mocked(api.get).mockReturnValue(new Promise(() => {})); // pending promise
      render(<JobStatusTimeline jobId={10} currentStatus="ASSIGNED" />);
      expect(screen.getByTestId('timeline-skeleton')).toBeDefined();
    });

    it('renders empty placeholder if history is empty', async () => {
      vi.mocked(api.get).mockResolvedValue({ data: [] });
      render(<JobStatusTimeline jobId={10} currentStatus="UNASSIGNED" />);

      await waitFor(() => {
        expect(screen.getByText('No status changes')).toBeDefined();
      });
    });

    it('renders timeline elements, pulses active state, and displays breach alert', async () => {
      vi.mocked(api.get).mockResolvedValue({ data: mockHistory });
      render(<JobStatusTimeline jobId={10} currentStatus="ASSIGNED" />);

      await waitFor(() => {
        expect(screen.getByText('UNASSIGNED')).toBeDefined();
        expect(screen.getByText('ASSIGNED')).toBeDefined();
      });

      // Verification of active timeline pulsing item
      const activeItem = screen.getByTestId('active-timeline-item');
      expect(activeItem).toBeDefined();

      // Verification of SLA breached warning
      expect(screen.getByText('SLA BREACHED')).toBeDefined();
    });

    it('collapses and expands segments on user click interaction', async () => {
      vi.mocked(api.get).mockResolvedValue({ data: mockHistory });
      render(<JobStatusTimeline jobId={10} currentStatus="ASSIGNED" />);

      await waitFor(() => {
        expect(screen.getByText('UNASSIGNED')).toBeDefined();
        expect(screen.getByText('ASSIGNED')).toBeDefined();
      });

      // The active item 'ASSIGNED' is expanded by default, 'CREATED' is collapsed
      expect(screen.queryByText('Rajesh Kumar')).toBeNull(); // Rajesh is in CREATED (collapsed)
      expect(screen.getByText('Vijay Iyer')).toBeDefined(); // Vijay is in ASSIGNED (expanded)

      // Click header of 'CREATED' to expand it
      const unassignedHeader = screen.getByText('UNASSIGNED');
      fireEvent.click(unassignedHeader);

      expect(screen.getByText('Rajesh Kumar')).toBeDefined(); // Now expanded!
    });

    it('renders error state notice and supports retry fetch clicks', async () => {
      vi.mocked(api.get)
        .mockRejectedValueOnce(new Error('Network Error'))
        .mockResolvedValueOnce({ data: mockHistory });

      render(<JobStatusTimeline jobId={10} currentStatus="ASSIGNED" />);

      await waitFor(() => {
        expect(screen.getByText('Failed to fetch status transition timeline history.')).toBeDefined();
      });

      // Trigger retry
      const retryBtn = screen.getByText('Retry Fetching');
      fireEvent.click(retryBtn);

      await waitFor(() => {
        expect(screen.getByText('UNASSIGNED')).toBeDefined();
        expect(screen.getByText('ASSIGNED')).toBeDefined();
      });
    });
  });
});
