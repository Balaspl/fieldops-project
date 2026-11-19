import React from 'react';
import { useMapViewport } from '../../hooks/useMapViewport';
import { ArrowLeft, Maximize, Keyboard } from 'lucide-react';

interface MapControlsProps {
  jobs: any[];
}

export const MapControls: React.FC<MapControlsProps> = ({ jobs }) => {
  const { history, returnToOverview, goBack } = useMapViewport();
  const hasHistory = history.length > 0;

  return (
    <div className="flex items-center gap-2 bg-white/95 dark:bg-slate-900/95 backdrop-blur shadow-md px-2.5 py-1.5 rounded-xl border border-slate-100 dark:border-slate-800 select-none">
      {/* Back button */}
      <button
        onClick={goBack}
        disabled={!hasHistory}
        className={`flex items-center justify-center p-2 rounded-lg border transition ${
          hasHistory
            ? 'bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 cursor-pointer'
            : 'bg-slate-50 dark:bg-slate-900 border-slate-100 dark:border-slate-800 text-slate-300 dark:text-slate-600 cursor-not-allowed'
        }`}
        title="Go to Previous View"
        aria-label="Go to Previous View"
      >
        <ArrowLeft size={14} />
      </button>

      {/* Return to Overview button */}
      <button
        onClick={() => returnToOverview(jobs)}
        className="flex items-center gap-1.5 px-3 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold rounded-lg shadow-sm transition cursor-pointer border border-emerald-500"
        title="Fit Map to Include All Active Coords"
        aria-label="Fit Map to Include All Active Coords"
      >
        <Maximize size={13} />
        Overview
      </button>

      {/* Hotkeys helper hints */}
      <div className="hidden md:flex items-center gap-2 border-l border-slate-200 dark:border-slate-700 pl-2.5 ml-1 text-[10px] text-slate-400 font-bold tracking-wider">
        <Keyboard size={12} className="text-slate-400 shrink-0" />
        <span className="flex items-center gap-1">
          <kbd className="px-1.5 py-0.5 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded text-slate-600 dark:text-slate-300 shadow-sm uppercase font-mono font-black">Space</kbd> Reset
        </span>
        <span className="flex items-center gap-1">
          <kbd className="px-1.5 py-0.5 bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded text-slate-600 dark:text-slate-300 shadow-sm uppercase font-mono font-black">Esc</kbd> Unfollow
        </span>
      </div>
    </div>
  );
};

export default MapControls;
