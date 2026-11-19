import React from 'react';
import { User } from 'lucide-react';

interface ActorBadgeProps {
  name: string | null;
  role: string | null;
}

export const getInitials = (name: string): string => {
  if (!name) return 'U';
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
};

export const ActorBadge: React.FC<ActorBadgeProps> = ({ name, role }) => {
  const actorName = name || 'System';
  const actorRole = role || 'SYSTEM';

  const initials = getInitials(actorName);

  // Avatar background colors based on name hash
  const colors = [
    'bg-blue-500 shadow-blue-500/20 text-white',
    'bg-emerald-500 shadow-emerald-500/20 text-white',
    'bg-purple-500 shadow-purple-500/20 text-white',
    'bg-indigo-500 shadow-indigo-500/20 text-white',
    'bg-amber-500 shadow-amber-500/20 text-white',
    'bg-rose-500 shadow-rose-500/20 text-white',
  ];
  const charCodeSum = actorName.split('').reduce((sum, char) => sum + char.charCodeAt(0), 0);
  const colorClass = colors[charCodeSum % colors.length];

  return (
    <div className="flex items-center gap-2 select-none">
      {/* Initials Avatar */}
      <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-extrabold shadow-sm tracking-tighter ${colorClass}`} aria-hidden="true">
        {initials}
      </div>

      <div className="flex flex-col leading-tight">
        <span className="text-xs font-semibold text-slate-700 dark:text-slate-200">{actorName}</span>
        {/* Role Badge */}
        <span className={`text-[8px] font-extrabold tracking-wider uppercase inline-block max-w-max px-1.5 py-0.25 rounded border mt-0.5 ${
          actorRole.toLowerCase() === 'admin' || actorRole.toLowerCase() === 'administrator'
            ? 'bg-rose-50 dark:bg-rose-950/20 border-rose-100 dark:border-rose-900/50 text-rose-600 dark:text-rose-400'
            : actorRole.toLowerCase() === 'technician' || actorRole.toLowerCase() === 'tech'
            ? 'bg-emerald-50 dark:bg-emerald-950/20 border-emerald-100 dark:border-emerald-900/50 text-emerald-600 dark:text-emerald-400'
            : actorRole.toLowerCase() === 'dispatcher' || actorRole.toLowerCase() === 'dispatch'
            ? 'bg-blue-50 dark:bg-blue-950/20 border-blue-100 dark:border-blue-900/50 text-blue-600 dark:text-blue-400'
            : 'bg-slate-50 dark:bg-slate-800 border-slate-100 dark:border-slate-700 text-slate-500 dark:text-slate-400'
        }`}>
          {actorRole}
        </span>
      </div>
    </div>
  );
};

export default ActorBadge;
