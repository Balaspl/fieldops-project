import React, { useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  Clock3,
  Tag,
} from 'lucide-react';
import ActorBadge from './ActorBadge';
import type { JobTimelineEvent } from '../../services/planningService';

interface TimelineItemProps {
  item: JobTimelineEvent;
  isCurrent: boolean;
  isLast: boolean;
}

export const getTimelineColor = (event: JobTimelineEvent): string => {
  const status = event.to_status?.toUpperCase();

  switch (status) {
    case 'CREATED':
      return '#F59E0B';
    case 'ASSIGNED':
      return '#3B82F6';
    case 'EN_ROUTE':
      return '#10B981';
    case 'ON_SITE':
    case 'IN_PROGRESS':
      return '#F59E0B';
    case 'COMPLETED':
      return '#10B981';
    case 'CANCELLED':
      return '#EF4444';
    case 'CLOSED':
      return '#64748B';
    case 'REJECTED_BY_TECHNICIAN':
      return '#EF4444';
    default:
      switch (event.event_category) {
        case 'CREATION':
          return '#F59E0B';
        case 'ASSIGNMENT':
          return '#3B82F6';
        case 'STATUS':
          return '#10B981';
        case 'COMPLETION':
          return '#10B981';
        default:
          return '#9CA3AF';
      }
  }
};

export const TimelineItem: React.FC<TimelineItemProps> = ({
  item,
  isCurrent,
  isLast,
}) => {
  const [expanded, setExpanded] = useState(isCurrent);

  const timelineColor = getTimelineColor(item);

  const formattedTime = new Date(item.timestamp).toLocaleString();

  const displayStatus =
    item.to_status?.toUpperCase() === 'CREATED'
      ? 'UNASSIGNED'
      : item.to_status || null;

  const hasTransition =
    Boolean(item.from_status) ||
    Boolean(item.to_status);

  const eventTypeLabel = item.event_type
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (char) => char.toUpperCase());

  const categoryLabel = item.event_category
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (char) => char.toUpperCase());

  return (
    <div
      className={`flex gap-4 relative group ${
        isCurrent ? 'timeline-item-active' : ''
      }`}
      data-testid={isCurrent ? 'active-timeline-item' : 'timeline-item'}
    >
      {/* Visual Dot and Connector Line */}
      <div className="flex flex-col items-center">
        <div
          className={`w-4.5 h-4.5 rounded-full border-2 border-white dark:border-slate-900 shadow-md flex items-center justify-center z-10 transition duration-300 ${
            isCurrent ? 'animate-pulse scale-110 shadow-emerald-500/20' : ''
          }`}
          style={{ backgroundColor: timelineColor }}
        >
          {isCurrent && (
            <div className="w-1.5 h-1.5 bg-white rounded-full animate-ping" />
          )}
        </div>

        {!isLast && (
          <div
            className="w-0.5 flex-1 bg-slate-200 dark:bg-slate-700 my-1 transition-colors"
            style={{ minHeight: '40px' }}
          />
        )}
      </div>

      {/* Main Card Content */}
      <div className="flex-1 pb-6">
        <div
          className={`bg-white dark:bg-slate-900 border rounded-xl shadow-sm transition p-3.5 hover:shadow-md cursor-pointer select-none ${
            isCurrent
              ? 'border-emerald-500/30 ring-1 ring-emerald-500/10'
              : 'border-slate-100 dark:border-slate-800'
          }`}
          onClick={() => setExpanded(!expanded)}
        >
          {/* Header row */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <span
                className="text-[10px] font-black tracking-widest uppercase px-2 py-0.5 rounded-full text-white shrink-0"
                style={{ backgroundColor: timelineColor }}
              >
                {displayStatus || categoryLabel}
              </span>

              <span className="text-[10px] font-bold text-slate-700 dark:text-slate-200 truncate">
                {item.title}
              </span>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <span className="text-[10px] text-slate-400 font-medium">
                {formattedTime}
              </span>

              {expanded ? (
                <ChevronDown size={14} className="text-slate-400" />
              ) : (
                <ChevronRight size={14} className="text-slate-400" />
              )}
            </div>
          </div>

          {/* Details body */}
          {expanded && (
            <div className="mt-3.5 pt-3.5 border-t border-slate-50 dark:border-slate-800/50 space-y-3 animate-slide-down">
              <p className="text-[11px] leading-relaxed text-slate-600 dark:text-slate-300">
                {item.description}
              </p>

              <div className="flex flex-wrap items-center gap-3">
                <ActorBadge
                  name={item.actor_name}
                  role={item.actor_role}
                />

                <div className="flex items-center gap-1.5">
                  <Tag size={12} className="text-slate-400" />
                  <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">
                    {categoryLabel}
                  </span>
                </div>

                <div className="flex items-center gap-1.5">
                  <Clock3 size={12} className="text-slate-400" />
                  <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">
                    {eventTypeLabel}
                  </span>
                </div>
              </div>

              {hasTransition && (
                <div className="flex flex-wrap items-center gap-2 text-[10px] font-semibold">
                  {item.from_status && (
                    <span className="rounded-md bg-slate-100 px-2 py-1 text-slate-500 dark:bg-slate-800 dark:text-slate-300">
                      {item.from_status}
                    </span>
                  )}

                  {item.from_status && item.to_status && (
                    <span className="text-slate-400">
                      →
                    </span>
                  )}

                  {item.to_status && (
                    <span className="rounded-md bg-slate-100 px-2 py-1 text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                      {displayStatus}
                    </span>
                  )}
                </div>
              )}

              <div className="text-[9px] text-slate-400">
                Source: {item.source}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default TimelineItem;