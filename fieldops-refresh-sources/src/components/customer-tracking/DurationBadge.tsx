import React from 'react';
import { Clock } from 'lucide-react';

interface DurationBadgeProps {
  durationSeconds: number | null;
}

export const formatDurationString = (totalSeconds: number): string => {
  if (totalSeconds < 60) {
    return '< 1 min';
  }

  const minutes = Math.floor(totalSeconds / 60);
  if (minutes < 60) {
    return `${minutes}m`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (hours < 24) {
    return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
  }

  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  return remainingHours > 0 ? `${days}d ${remainingHours}h` : `${days}d`;
};

export const DurationBadge: React.FC<DurationBadgeProps> = ({ durationSeconds }) => {
  if (durationSeconds === null || durationSeconds === undefined || durationSeconds < 0) {
    return null;
  }

  const durationStr = formatDurationString(durationSeconds);

  return (
    <div className="inline-flex items-center gap-1 bg-slate-50 dark:bg-slate-800 text-slate-500 dark:text-slate-400 border border-slate-100 dark:border-slate-700 px-2 py-0.5 rounded-md text-[10px] font-bold select-none shadow-sm">
      <Clock size={11} className="shrink-0" />
      <span>{durationStr}</span>
    </div>
  );
};

export default DurationBadge;
