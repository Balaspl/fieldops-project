import React from 'react';
import { AlertTriangle } from 'lucide-react';

interface SLABreachBadgeProps {
  durationSeconds: number | null;
  slaLimitSeconds: number | null;
}

export const SLABreachBadge: React.FC<SLABreachBadgeProps> = ({ durationSeconds, slaLimitSeconds }) => {
  if (!durationSeconds || !slaLimitSeconds || durationSeconds <= slaLimitSeconds) {
    return null;
  }

  const breachOverBy = durationSeconds - slaLimitSeconds;
  const hoursOver = Math.floor(breachOverBy / 3600);
  const minutesOver = Math.floor((breachOverBy % 3600) / 60);
  const overStr = hoursOver > 0 ? `${hoursOver}h ${minutesOver}m` : `${minutesOver}m`;

  return (
    <div 
      className="inline-flex items-center gap-1 bg-red-50 dark:bg-red-950/20 text-red-600 dark:text-red-400 border border-red-100 dark:border-red-900/50 px-2 py-0.5 rounded-md text-[10px] font-extrabold select-none shadow-sm animate-pulse"
      title={`SLA Breached by ${overStr}`}
    >
      <AlertTriangle size={11} className="shrink-0 text-red-500" />
      <span>SLA BREACHED</span>
    </div>
  );
};

export default SLABreachBadge;
