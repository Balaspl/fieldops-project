import React, { useEffect, useState, useRef } from 'react';
import {
  getJobTimeline,
  type JobTimelineCategory,
  type JobTimelineEvent,
} from '../../services/planningService';
import { TimelineItem } from './TimelineItem';
import { RefreshCw, History, CalendarClock } from 'lucide-react';

interface JobStatusTimelineProps {
  jobId: string | number;
  currentStatus: string;
  refreshKey?: number;
}

export const SkeletonTimeline: React.FC = () => {
  return (
    <div
      className="flex flex-col gap-4 w-full animate-pulse select-none"
      data-testid="timeline-skeleton"
    >
      {[1, 2, 3].map((n) => (
        <div key={n} className="flex gap-4">
          <div className="flex flex-col items-center">
            <div className="w-4 h-4 rounded-full bg-slate-200 dark:bg-slate-700" />
            {n < 3 && (
              <div className="w-0.5 flex-1 bg-slate-100 dark:bg-slate-800 my-1 min-h-[40px]" />
            )}
          </div>
          <div className="flex-1 bg-slate-50 dark:bg-slate-800/50 border border-slate-100/50 dark:border-slate-800 rounded-xl h-16" />
        </div>
      ))}
    </div>
  );
};

export const JobStatusTimeline: React.FC<JobStatusTimelineProps> = ({
  jobId,
  currentStatus,
  refreshKey = 0,
}) => {
  const [events, setEvents] = useState<JobTimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState<JobTimelineCategory | undefined>(
    undefined
  );

  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [total, setTotal] = useState(0);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const requestIdRef = useRef(0);

  const fetchTimeline = async (
    requestedPage = page,
    requestedCategory = category,
    isRefresh = false
  ) => {
    const requestId = ++requestIdRef.current;

    if (isRefresh && events.length > 0) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    setError(null);

    try {
      const response = await getJobTimeline(jobId, {
        category: requestedCategory,
        page: requestedPage,
        page_size: 25,
      });

      // Ignore stale responses when a newer request has already started.
      if (requestId !== requestIdRef.current) {
        return;
      }

      setEvents(response.events || []);
      setPage(response.page);
      setHasMore(response.has_more);
      setTotal(response.total);
    } catch (e: any) {
      console.error(
        '[JobStatusTimeline] Error loading job status history:',
        e
      );

      // Preserve already-rendered data during refresh failures.
      if (events.length > 0 && isRefresh) {
        setError(
          'Status history refresh failed. Showing the last available history.'
        );
      } else if (e?.response?.status === 403) {
        setError(
          'You are not authorized to view this job status history.'
        );
      } else if (e?.response?.status === 404) {
        setError('Job status history was not found.');
      } else {
        setError('Failed to fetch job status history.');
      }
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  };

  useEffect(() => {
    if (!jobId) {
      return;
    }

    const isSameJobRefresh = events.length > 0;

    if (!isSameJobRefresh) {
      setPage(1);
      setEvents([]);
    }

    fetchTimeline(
      isSameJobRefresh ? page : 1,
      category,
      isSameJobRefresh
    );
  }, [jobId, refreshKey, category]);

  // Scroll to the active pulsing timeline item
  useEffect(() => {
    if (!loading && events.length > 0) {
      const timer = setTimeout(() => {
        const activeEl = containerRef.current?.querySelector(
          '.timeline-item-active'
        );

        if (activeEl) {
          activeEl.scrollIntoView({
            behavior: 'smooth',
            block: 'nearest',
          });
        }
      }, 150);

      return () => clearTimeout(timer);
    }
  }, [loading, events]);

  if (loading && events.length === 0) {
    return (
      <div className="flex flex-col p-4 w-full">
        <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-1.5">
          <History size={13} />
          Job Status History
        </h4>
        <SkeletonTimeline />
      </div>
    );
  }

  if (error && events.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-6 text-center bg-slate-50 dark:bg-slate-900 border border-slate-100 dark:border-slate-850 rounded-xl gap-3 w-full">
        <span className="text-xs text-rose-500 font-semibold">
          {error}
        </span>

        <button
          onClick={() =>
            fetchTimeline(
              page,
              category,
              false
            )
          }
          className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-bold rounded-lg shadow-sm transition cursor-pointer"
        >
          <RefreshCw size={11} className="shrink-0" />
          Retry Fetching
        </button>
      </div>
    );
  }

  if (!loading && events.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center bg-slate-50/50 dark:bg-slate-900/30 border border-slate-100/50 dark:border-slate-850 rounded-xl gap-2 w-full">
        <CalendarClock className="w-8 h-8 text-slate-300 mx-auto mb-1" />
        <span className="text-slate-900 dark:text-slate-100 font-bold text-sm">
          No status history
        </span>

        <span className="text-slate-400 text-xs max-w-xs">
          No job status history is currently available for this job.
        </span>
      </div>
    );
  }

  return (
    <div className="flex flex-col w-full h-full" ref={containerRef}>
      <h4 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-4 flex items-center gap-1.5 select-none">
        <History size={13} />
        Job Status History
      </h4>

      <div className="flex flex-wrap gap-1.5 mb-3">
        {(
          [
            ['ALL', undefined],
            ['CREATION', 'CREATION'],
            ['ASSIGNMENT', 'ASSIGNMENT'],
            ['STATUS', 'STATUS'],
            ['COMPLETION', 'COMPLETION'],
            ['OTHER', 'OTHER'],
          ] as const
        ).map(([label, value]) => (
          <button
            key={label}
            type="button"
            onClick={() => {
              setCategory(
                value as JobTimelineCategory | undefined
              );
              setPage(1);
            }}
            className={`px-2.5 py-1 rounded-lg text-[10px] font-bold transition ${
              category === value
                ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900'
                : 'bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {refreshing && (
        <div className="mb-2 flex items-center gap-1.5 text-[10px] text-slate-400">
          <RefreshCw size={11} className="animate-spin" />
          Refreshing status history...
        </div>
      )}

      {error && events.length > 0 && (
        <div className="mb-3 flex items-center justify-between gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-900/40 dark:bg-amber-950/20">
          <span className="text-[10px] font-medium text-amber-700 dark:text-amber-300">
            {error}
          </span>

          <button
            type="button"
            onClick={() =>
              fetchTimeline(
                page,
                category,
                true
              )
            }
            className="inline-flex items-center gap-1 text-[10px] font-bold text-amber-700 hover:text-amber-900 dark:text-amber-300 dark:hover:text-amber-100"
          >
            <RefreshCw size={10} />
            Retry
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto pr-1 max-h-[360px] custom-scrollbar scroll-smooth">
        {events.map((event, idx) => (
          <TimelineItem
            key={event.id}
            item={event}
            isCurrent={event.is_current}
            isLast={idx === events.length - 1}
          />
        ))}
      </div>

      {(page > 1 || hasMore) && (
        <div className="flex items-center justify-between pt-3 mt-2 border-t border-slate-100 dark:border-slate-800">
          <button
            type="button"
            disabled={page <= 1 || loading}
            onClick={() => {
              const nextPage = page - 1;
              setPage(nextPage);
              fetchTimeline(
                nextPage,
                category,
                true
              );
            }}
            className="px-2.5 py-1.5 rounded-lg text-[10px] font-bold bg-slate-100 text-slate-600 disabled:opacity-40 disabled:cursor-not-allowed dark:bg-slate-800 dark:text-slate-300"
          >
            Previous
          </button>

          <span className="text-[10px] text-slate-400">
            Page {page}
            {total > 0 ? ` • ${total} events` : ''}
          </span>

          <button
            type="button"
            disabled={!hasMore || loading}
            onClick={() => {
              const nextPage = page + 1;
              setPage(nextPage);
              fetchTimeline(
                nextPage,
                category,
                true
              );
            }}
            className="px-2.5 py-1.5 rounded-lg text-[10px] font-bold bg-slate-100 text-slate-600 disabled:opacity-40 disabled:cursor-not-allowed dark:bg-slate-800 dark:text-slate-300"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
};

export default JobStatusTimeline;