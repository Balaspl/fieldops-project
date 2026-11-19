import React, { useState } from 'react';
import { HelpCircle, Info } from 'lucide-react';

interface ReasonTooltipProps {
  reason: string;
}

export const ReasonTooltip: React.FC<ReasonTooltipProps> = ({ reason }) => {
  const [visible, setVisible] = useState(false);

  if (!reason) return null;

  return (
    <div className="relative inline-block leading-none">
      <button
        type="button"
        onMouseEnter={() => setVisible(true)}
        onMouseLeave={() => setVisible(false)}
        onClick={() => setVisible(!visible)}
        className="p-1 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-full transition cursor-pointer text-amber-500 hover:text-amber-600 dark:text-amber-400 shrink-0"
        title="Reason details"
        aria-label="Reason details"
      >
        <HelpCircle size={13} />
      </button>

      {visible && (
        <div className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 z-30 w-52 bg-slate-900/95 dark:bg-slate-950/95 backdrop-blur text-white text-[11px] p-2.5 rounded-lg shadow-xl border border-slate-700/50 leading-relaxed pointer-events-none select-none animate-fade-in animate-scale-up">
          <div className="flex gap-1.5 items-start">
            <Info size={13} className="text-amber-400 shrink-0 mt-0.5" />
            <div className="flex-1">
              <span className="font-extrabold text-amber-300 block mb-0.5 uppercase tracking-wider text-[9px]">Transition Reason</span>
              <span className="text-slate-200">{reason}</span>
            </div>
          </div>
          {/* Tooltip caret */}
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-900/95 dark:border-t-slate-950/95" />
        </div>
      )}
    </div>
  );
};

export default ReasonTooltip;
