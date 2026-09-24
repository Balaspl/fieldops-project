import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { JobStatusTimeline } from '../JobStatusTimeline';
import { DurationBadge, formatDurationString } from '../DurationBadge';
import { SLABreachBadge } from '../SLABreachBadge';
import { ActorBadge, getInitials } from '../ActorBadge';
import { getJobTimeline } from '../../../services/planningService';

// Mock the authoritative job timeline service.
vi.mock('../../../services/planningService', () => ({
  getJobTimeline: vi.fn(),
}));

// Mock scrollIntoView
const mockScrollIntoView = vi.fn();
window.HTMLElement.prototype.scrollIntoView = mockScrollIntoView;

describe('Job Status Timeline System', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.mocked(getJobTimeline).mockReset();
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
      render(
        <SLABreachBadge
          durationSeconds={3600}
          slaLimitSeconds={1800}
        />
      );

      expect(screen.getByText('SLA BREACHED')).toBeDefined();
    });

    it('does not render SLABreachBadge if SLA limits are satisfied', () => {
      const { container } = render(
        <SLABreachBadge
          durationSeconds={900}
          slaLimitSeconds={1800}
        />
      );

      expect(container.firstChild).toBeNull();
    });
  });

  describe('JobStatusTimeline Layout Wrapper', () => {
    const mockTimelineResponse = {
      job_id: 10,
      page: 1,
      page_size: 25,
      total: 5,
      has_more: false,
      events: [
        {
          id: 'job:10:JOB_CREATED',
          job_id: 10,
          event_type: 'JOB_CREATED',
          event_category: 'CREATION' as const,
          title: 'Job Created',
          description: 'Job record was created.',
          timestamp: '2026-09-23T08:00:00.000Z',
          from_status: null,
          to_status: 'CREATED',
          actor_name: 'System',
          actor_role: 'SYSTEM',
          source: 'job',
          is_current: false,
        },
        {
          id: 'job:10:JOB_ASSIGNED',
          job_id: 10,
          event_type: 'JOB_ASSIGNED',
          event_category: 'ASSIGNMENT' as const,
          title: 'Technician Assigned',
          description: 'Job was assigned to the technician.',
          timestamp: '2026-09-23T08:10:00.000Z',
          from_status: 'CREATED',
          to_status: 'ASSIGNED',
          actor_name: 'Vijay Iyer',
          actor_role: 'TECHNICIAN',
          source: 'job',
          is_current: false,
        },
        {
          id: 'enterprise:100',
          job_id: 10,
          event_type: 'JOB_ACCEPTED',
          event_category: 'STATUS' as const,
          title: 'Job Accepted',
          description: 'Assigned technician accepted the job.',
          timestamp: '2026-09-23T08:20:00.000Z',
          from_status: 'ASSIGNED',
          to_status: 'ACCEPTED',
          actor_name: 'Vijay Iyer',
          actor_role: 'TECHNICIAN',
          source: 'enterprise_audit',
          is_current: true,
        },
        {
          id: 'job:10:JOB_COMPLETED',
          job_id: 10,
          event_type: 'JOB_COMPLETED',
          event_category: 'COMPLETION' as const,
          title: 'Job Completed',
          description: 'Job completion was recorded.',
          timestamp: '2026-09-23T09:00:00.000Z',
          from_status: 'ACCEPTED',
          to_status: 'COMPLETED',
          actor_name: 'Vijay Iyer',
          actor_role: 'TECHNICIAN',
          source: 'job',
          is_current: false,
        },
        {
          id: 'other:100',
          job_id: 10,
          event_type: 'JOB_UPDATED',
          event_category: 'OTHER' as const,
          title: 'Job Updated',
          description: 'Job details were updated.',
          timestamp: '2026-09-23T09:05:00.000Z',
          from_status: null,
          to_status: null,
          actor_name: 'Staff',
          actor_role: 'STAFF',
          source: 'enterprise_audit',
          is_current: false,
        },
      ],
    };

    it('renders loading skeleton initially', () => {
      vi.mocked(getJobTimeline).mockReturnValue(
        new Promise(() => {})
      );

      render(
        <JobStatusTimeline
          jobId={10}
          currentStatus="ASSIGNED"
        />
      );

      expect(
        screen.getByTestId('timeline-skeleton')
      ).toBeDefined();
    });

    it('renders the empty status history state when no events are returned', async () => {
      vi.mocked(getJobTimeline).mockResolvedValue({
        ...mockTimelineResponse,
        total: 0,
        events: [],
        has_more: false,
      });

      render(
        <JobStatusTimeline
          jobId={10}
          currentStatus="UNASSIGNED"
        />
      );

      await waitFor(() => {
        expect(
          screen.getByText('No status history')
        ).toBeDefined();
      });

      expect(
        screen.getByText(
          'No job status history is currently available for this job.'
        )
      ).toBeDefined();
    });

    it('renders chronological status history events and highlights the backend-marked current event', async () => {
      vi.mocked(getJobTimeline).mockResolvedValue(
        mockTimelineResponse
      );

      render(
        <JobStatusTimeline
          jobId={10}
          currentStatus="ACCEPTED"
        />
      );

      await waitFor(() => {
        expect(
          screen.getAllByText('Job Created').length
        ).toBeGreaterThan(0);

        expect(
          screen.getByText('Technician Assigned')
        ).toBeDefined();

        expect(
          screen.getAllByText('Job Accepted').length
        ).toBeGreaterThan(0);

        expect(
          screen.getByText('Job Completed')
        ).toBeDefined();

        expect(
          screen.getByText('Job Updated')
        ).toBeDefined();
      });

      expect(
        screen.getByTestId('active-timeline-item')
      ).toBeDefined();

      expect(
        screen.getByText('CREATION')
      ).toBeDefined();

      expect(
        screen.getByText('ASSIGNMENT')
      ).toBeDefined();

      expect(
        screen.getByText('COMPLETION')
      ).toBeDefined();

      expect(
        screen.getByText('Assigned technician accepted the job.')
      ).toBeDefined();

      expect(
        screen.getByText('TECHNICIAN')
      ).toBeDefined();

      expect(
        screen.getByText('Source: enterprise_audit')
      ).toBeDefined();
    });

    it('collapses and expands timeline events on user click interaction', async () => {
      vi.mocked(getJobTimeline).mockResolvedValue(
        mockTimelineResponse
      );

      render(
        <JobStatusTimeline
          jobId={10}
          currentStatus="ACCEPTED"
        />
      );

      await waitFor(() => {
        expect(
          screen.getAllByText('Job Created').length
        ).toBeGreaterThan(0);

        expect(
          screen.getAllByText('Job Accepted').length
        ).toBeGreaterThan(0);
      });

      // Current event is expanded by default.
      expect(
        screen.getByText(
          'Assigned technician accepted the job.'
        )
      ).toBeDefined();

      // Job Created starts collapsed.
      expect(
        screen.queryByText(
          'Job record was created.'
        )
      ).toBeNull();

      fireEvent.click(
        screen.getByText('Job Created')
      );

      expect(
        screen.getByText(
          'Job record was created.'
        )
      ).toBeDefined();
    });

    it('renders an error state and retries the authoritative status history request', async () => {
      vi.mocked(getJobTimeline)
        .mockRejectedValueOnce(
          new Error('Network Error')
        )
        .mockResolvedValueOnce(
          mockTimelineResponse
        );

      render(
        <JobStatusTimeline
          jobId={10}
          currentStatus="ASSIGNED"
        />
      );

      await waitFor(() => {
        expect(
          screen.getByText(
            'Failed to fetch job status history.'
          )
        ).toBeDefined();
      });

      fireEvent.click(
        screen.getByText('Retry Fetching')
      );

      await waitFor(() => {
        expect(
          screen.getByText('Job Created')
        ).toBeDefined();

        expect(
          screen.getByText('Technician Assigned')
        ).toBeDefined();
      });

      expect(
        getJobTimeline
      ).toHaveBeenCalledTimes(2);
    });

    it('shows the authorization error when the status history API returns 403', async () => {
      vi.mocked(getJobTimeline).mockRejectedValueOnce({
        response: {
          status: 403,
        },
      });

      render(
        <JobStatusTimeline
          jobId={10}
          currentStatus="ASSIGNED"
        />
      );

      await waitFor(() => {
        expect(
          screen.getByText(
            'You are not authorized to view this job status history.'
          )
        ).toBeDefined();
      });
    });

    it('requests the selected status history category from the backend', async () => {
      vi.mocked(getJobTimeline).mockResolvedValue(
        mockTimelineResponse
      );

      render(
        <JobStatusTimeline
          jobId={10}
          currentStatus="ACCEPTED"
        />
      );

      await waitFor(() => {
        expect(
          screen.getByText('Job Created')
        ).toBeDefined();
      });

      fireEvent.click(
        screen.getByRole('button', {
          name: 'ASSIGNMENT',
        })
      );

      await waitFor(() => {
        expect(
          getJobTimeline
        ).toHaveBeenLastCalledWith(
          10,
          {
            category: 'ASSIGNMENT',
            page: 1,
            page_size: 25,
          }
        );
      });
    });

    it('refreshes the status history when refreshKey changes', async () => {
      vi.mocked(getJobTimeline).mockResolvedValue(
        mockTimelineResponse
      );

      const { rerender } = render(
        <JobStatusTimeline
          jobId={10}
          currentStatus="ACCEPTED"
          refreshKey={0}
        />
      );

      await waitFor(() => {
        expect(
          screen.getByText('Job Created')
        ).toBeDefined();
      });

      expect(
        getJobTimeline
      ).toHaveBeenCalledTimes(1);

      rerender(
        <JobStatusTimeline
          jobId={10}
          currentStatus="COMPLETED"
          refreshKey={1}
        />
      );

      await waitFor(() => {
        expect(
          getJobTimeline
        ).toHaveBeenCalledTimes(2);
      });
    });
  });
});