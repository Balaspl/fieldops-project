import React, { useState, useEffect } from 'react';
import { AlertCircle, Clock } from 'lucide-react';

interface SLACountdownProps {
  deadline: string | null;
}

export const SLACountdown: React.FC<SLACountdownProps> = ({ deadline }) => {
  const [minutesRemaining, setMinutesRemaining] = useState<number | null>(null);

  const calculateMinutes = () => {
    if (!deadline) {
      setMinutesRemaining(null);
      return;
    }
    const diffMs = new Date(deadline).getTime() - new Date().getTime();
    const diffMins = Math.ceil(diffMs / (1000 * 60));
    setMinutesRemaining(diffMins);
  };

  useEffect(() => {
    calculateMinutes();

    const interval = setInterval(() => {
      calculateMinutes();
    }, 60000); // Update every minute

    return () => clearInterval(interval);
  }, [deadline]);

  if (!deadline || minutesRemaining === null) {
    return (
      <span className="inline-flex items-center gap-1 text-slate-500 font-semibold text-[11px] bg-slate-100 px-2 py-0.5 rounded">
        No Deadline
      </span>
    );
  }

  if (minutesRemaining <= 0) {
    return (
      <span className="inline-flex items-center gap-1.5 text-red-700 font-black text-xs bg-red-100 border border-red-200 px-2.5 py-1 rounded-full animate-pulse tracking-wide shadow-sm">
        <AlertCircle size={13} className="text-red-600 animate-bounce" />
        OVERDUE
      </span>
    );
  }

  const hours = Math.floor(minutesRemaining / 60);
  const mins = minutesRemaining % 60;
  const timeText = hours > 0 ? `${hours}h ${mins}m` : `${mins}m`;

  return (
    <span className="inline-flex items-center gap-1 text-emerald-800 font-bold text-[11px] bg-emerald-100 border border-emerald-200 px-2.5 py-0.5 rounded-full">
      <Clock size={11} className="text-emerald-700" />
      {timeText} remaining
    </span>
  );
};

export default SLACountdown;
