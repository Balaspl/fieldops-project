import React from 'react';

interface LayerButtonProps {
  active: boolean;
  onClick: () => void;
  icon: React.ComponentType<{ className?: string; size?: number }>;
  label: string;
  ariaLabel: string;
  tooltip: string;
  shortcutHint?: string;
}

export const LayerButton: React.FC<LayerButtonProps> = ({
  active,
  onClick,
  icon: Icon,
  label,
  ariaLabel,
  tooltip,
  shortcutHint,
}) => {
  return (
    <div className="relative group/tooltip flex flex-col items-center">
      <button
        onClick={onClick}
        aria-label={ariaLabel}
        aria-pressed={active}
        className={`
          flex items-center gap-1.5 px-2 py-1 rounded-lg border text-xs font-semibold transition-all duration-200 cursor-pointer
          ${
            active
              ? 'bg-emerald-600 border-emerald-600 text-white shadow-md shadow-emerald-500/20 scale-[1.02]'
              : 'bg-white border-slate-200 text-slate-700 hover:bg-slate-50 hover:border-slate-300'
          }
        `}
      >
        <Icon className={`w-3.5 h-3.5 ${active ? 'text-white' : 'text-slate-500'}`} size={14} />
        <span>{label}</span>
      </button>

      {/* Accessibility/Shortcut-aware Premium Tooltip */}
      <div
        className="
          pointer-events-none absolute bottom-full mb-2 left-1/2 -translate-x-1/2 
          opacity-0 scale-95 group-hover/tooltip:opacity-100 group-hover/tooltip:scale-100 
          transition-all duration-150 ease-out z-50 whitespace-nowrap 
          bg-slate-900 text-white text-[11px] py-1 px-2.5 rounded-md shadow-lg flex items-center gap-1.5
        "
      >
        <span>{tooltip}</span>
        {shortcutHint && (
          <span className="bg-slate-800 text-[10px] px-1.5 py-0.5 rounded border border-slate-700 font-mono text-emerald-400">
            {shortcutHint}
          </span>
        )}
      </div>
    </div>
  );
};
