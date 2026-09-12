import React, { useState } from 'react';
import { ChevronDown, ChevronRight, AlertCircle } from 'lucide-react';
import ActorBadge from './ActorBadge';
import DurationBadge from './DurationBadge';
import SLABreachBadge from './SLABreachBadge';
import ReasonTooltip from './ReasonTooltip';

export interface TransitionHistoryItem {
  id: number;
  job_id: number;
  from_status: string | null;
  to_status: string;
  changed_at: string;
  changed_by_name: string | null;
  changed_by_role: string | null;
  transition_reason: string | null;
  duration_seconds: number | null;
  sla_limit_seconds: number | null;
}

interface TimelineItemProps {
  item: TransitionHistoryItem;
  isCurrent: boolean;
  isLast: boolean;
}

export const getStatusColor = (status: string): string => {
  switch (status.toUpperCase()) {
    case 'CREATED':
      return '#F59E0B'; // Orange
    case 'ASSIGNED':
      return '#3B82F6'; // Blue
    case 'EN_ROUTE':
      return '#10B981'; // Green
    case 'ON_SITE':
      return '#F59E0B'; // Amber
    case 'COMPLETED':
      return '#10B981'; // Emerald/Green
    case 'CANCELLED':
      return '#EF4444'; // Red
    case 'CLOSED':
      return '#64748B'; // Slate
    default:
      return '#9CA3AF';
  }
};

export const TimelineItem: React.FC<TimelineItemProps> = ({ item, isCurrent, isLast }) => {
  const [expanded, setExpanded] = useState(isCurrent);

  const statusColor = getStatusColor(item.to_status);
  const formattedTime = new Date(item.changed_at).toLocaleString();

  // Check if it was a backward transition or cancellation
  const isCanceled = item.to_status.toUpperCase() === 'CANCELLED';
  const isBackward = () => {
    const order = ['CREATED', 'ASSIGNED', 'EN_ROUTE', 'ON_SITE', 'COMPLETED', 'CLOSED'];
    if (!item.from_status) return false;
    const fromIdx = order.indexOf(item.from_status.toUpperCase());
    const toIdx = order.indexOf(item.to_status.toUpperCase());
    return fromIdx !== -1 && toIdx !== -1 && toIdx < fromIdx;
  };

  const showReason = isCanceled || isBackward();

  return (
    <div 
      className={`flex gap-4 relative group ${isCurrent ? 'timeline-item-active' : ''}`}
      data-testid={isCurrent ? "active-timeline-item" : "timeline-item"}
    >
      {/* Visual Dot and Connector Line */}
      <div className="flex flex-col items-center">
        <div 
          className={`w-4.5 h-4.5 rounded-full border-2 border-white dark:border-slate-900 shadow-md flex items-center justify-center z-10 transition duration-300 ${
            isCurrent ? 'animate-pulse scale-110 shadow-emerald-500/20' : ''
          }`}
          style={{ backgroundColor: statusColor }}
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
            <div className="flex items-center gap-2">
              <span 
                className="text-[10px] font-black tracking-widest uppercase px-2 py-0.5 rounded-full text-white"
                style={{ backgroundColor: statusColor }}
              >
                {item.to_status === 'CREATED' ? 'UNASSIGNED' : item.to_status}
              </span>
              <span className="text-[10px] text-slate-400 font-medium">
                {formattedTime}
              </span>
              {showReason && item.transition_reason && (
                <ReasonTooltip reason={item.transition_reason} />
              )}
            </div>

            <div className="flex items-center gap-1.5">
              <SLABreachBadge 
                durationSeconds={item.duration_seconds} 
                slaLimitSeconds={item.sla_limit_seconds} 
              />
              {expanded ? (
                <ChevronDown size={14} className="text-slate-400" />
              ) : (
                <ChevronRight size={14} className="text-slate-400" />
              )}
            </div>
          </div>

          {/* Details body */}
          {expanded && (
            <div className="mt-3.5 pt-3.5 border-t border-slate-50 dark:border-slate-800/50 flex flex-wrap gap-4 items-center justify-between animate-slide-down">
              {/* Actor profile */}
              <ActorBadge name={item.changed_by_name} role={item.changed_by_role} />

              {/* Time spent duration */}
              {item.duration_seconds !== null && (
                <div className="flex flex-col items-end gap-1 leading-none">
                  <span className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">Time in previous status</span>
                  <DurationBadge durationSeconds={item.duration_seconds} />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default TimelineItem;
