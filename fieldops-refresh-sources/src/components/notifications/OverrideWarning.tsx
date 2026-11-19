import React, { useState } from "react";
import { AlertTriangle, Shield, ChevronDown, ChevronUp, History } from "lucide-react";

interface OverrideWarningProps {
  actorName: string;
  actorRole: string;
  assignedAt: string;
  reason: string;
  onViewHistory: () => void;
}

export default function OverrideWarning({
  actorName,
  actorRole,
  assignedAt,
  reason,
  onViewHistory
}: OverrideWarningProps) {
  const [expanded, setExpanded] = useState(false);

  const role = (actorRole || "").toLowerCase();
  
  // Define banner variant settings
  let bannerClass = "bg-amber-50 border-amber-200 text-amber-900"; // default yellow for dispatcher
  let icon = <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0" />;
  let labelText = "MANUALLY ASSIGNED by Dispatcher";

  if (role === "manager") {
    bannerClass = "bg-orange-50 border-orange-200 text-orange-950"; // orange for manager
    icon = <AlertTriangle className="w-5 h-5 text-orange-600 shrink-0" />;
    labelText = "MANUALLY ASSIGNED by Manager";
  } else if (role === "admin") {
    bannerClass = "bg-purple-50 border-purple-200 text-purple-950"; // purple for admin
    icon = <Shield className="w-5 h-5 text-purple-600 shrink-0" />;
    labelText = "MANUALLY ASSIGNED by Admin";
  }

  const formattedDate = new Date(assignedAt).toLocaleString([], {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });

  return (
    <div 
      className={`border rounded-xl p-4 flex flex-col gap-2.5 transition shadow-sm ${bannerClass}`}
      style={{ fontFamily: "'Inter', sans-serif" }}
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        {/* Icon & Message */}
        <div className="flex items-center gap-2.5">
          <div className="shrink-0">{icon}</div>
          <div>
            <span className="text-xs font-black uppercase tracking-wider block">
              {labelText}
            </span>
            <span className="text-[11px] font-semibold text-slate-500 block mt-0.5">
              Assigned to tech by {actorName} on {formattedDate}
            </span>
          </div>
        </div>

        {/* View History Button Link */}
        <button
          type="button"
          onClick={onViewHistory}
          className="flex items-center gap-1 text-[11px] font-extrabold hover:underline transition underline text-slate-800 shrink-0 self-end sm:self-auto"
          aria-label="View manual overrides history"
        >
          <History size={12} />
          <span>View Override History</span>
        </button>
      </div>

      {/* Justification details */}
      <div className="border-t border-black/5 pt-2 flex flex-col gap-1">
        <div 
          onClick={() => setExpanded(prev => !prev)}
          className="flex items-center justify-between text-[11px] font-bold text-slate-700 cursor-pointer select-none"
        >
          <span>Override Reason:</span>
          {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </div>
        <p className={`text-xs leading-relaxed font-semibold ${expanded ? "" : "line-clamp-1"}`}>
          {reason}
        </p>
      </div>
    </div>
  );
}
