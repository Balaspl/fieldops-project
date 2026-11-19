import React, { useCallback, useMemo } from 'react';
import { useTrackingDashboardStore, type TechStatusFilter } from '../../store/trackingDashboardStore';
import { useTrackingStore } from '../../store/trackingStore';
import { Search, Filter, X } from 'lucide-react';

const STATUS_PILLS: { value: TechStatusFilter; label: string; color: string; activeColor: string }[] = [
  { value: 'ALL', label: 'All', color: 'bg-slate-100 text-slate-600 hover:bg-slate-200', activeColor: 'bg-slate-800 text-white shadow-sm' },
  { value: 'ASSIGNED', label: 'Assigned', color: 'bg-blue-50 text-blue-600 hover:bg-blue-100', activeColor: 'bg-blue-600 text-white shadow-sm shadow-blue-500/20' },
  { value: 'EN_ROUTE', label: 'En Route', color: 'bg-emerald-50 text-emerald-600 hover:bg-emerald-100', activeColor: 'bg-emerald-600 text-white shadow-sm shadow-emerald-500/20' },
  { value: 'ON_SITE', label: 'On Site', color: 'bg-amber-50 text-amber-600 hover:bg-amber-100', activeColor: 'bg-amber-500 text-white shadow-sm shadow-amber-500/20' },
];

const JOB_TYPES = ['All', 'HVAC', 'Plumbing', 'Electrical', 'General'];

/**
 * FilterToolbar — floating toolbar with status pills, name search, and job type filter.
 * Reads/writes from trackingDashboardStore.
 */
export const FilterToolbar: React.FC = () => {
  const {
    statusFilter,
    searchQuery,
    jobTypeFilter,
    setStatusFilter,
    setSearchQuery,
    setJobTypeFilter,
  } = useTrackingDashboardStore();

  const jobs = useTrackingStore((state) => state.jobs);

  const summary = useMemo(() => {
    const counts = {
      ON_SITE: 0,
      EN_ROUTE: 0,
      ASSIGNED: 0,
      CREATED: 0,
    };

    Object.values(jobs).forEach((job) => {
      const statusKey = (job.status || '').toUpperCase();
      if (statusKey in counts) {
        counts[statusKey as keyof typeof counts]++;
      }
    });

    return counts;
  }, [jobs]);

  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      setSearchQuery(e.target.value);
    },
    [setSearchQuery]
  );

  const clearSearch = useCallback(() => {
    setSearchQuery('');
  }, [setSearchQuery]);

  return (
    <div
      className="flex flex-wrap items-center gap-2 bg-white/95 backdrop-blur-md shadow-lg rounded-xl border border-slate-200/80 px-3 py-2 select-none"
      data-testid="filter-toolbar"
      role="toolbar"
      aria-label="Technician filters"
    >
      {/* Status Filter Pills */}
      <div className="flex items-center gap-1" role="radiogroup" aria-label="Status filter">
        {STATUS_PILLS.map((pill) => (
          <button
            key={pill.value}
            onClick={() => setStatusFilter(pill.value)}
            role="radio"
            aria-checked={statusFilter === pill.value}
            className={`px-3 py-1.5 rounded-full text-[11px] font-bold uppercase tracking-wider transition-all cursor-pointer ${
              statusFilter === pill.value ? pill.activeColor : pill.color
            }`}
            data-testid={`filter-${pill.value.toLowerCase()}`}
          >
            {pill.label}
          </button>
        ))}
      </div>

      {/* Divider */}
      <div className="h-5 w-px bg-slate-200 mx-1 hidden sm:block" />

      {/* Search Input */}
      <div className="relative flex items-center">
        <Search size={13} className="absolute left-2.5 text-slate-400 pointer-events-none" />
        <input
          type="text"
          value={searchQuery}
          onChange={handleSearchChange}
          placeholder="Search technician..."
          className="pl-7 pr-7 py-1.5 text-xs font-medium bg-slate-50 border border-slate-200 rounded-lg w-40 focus:outline-none focus:ring-2 focus:ring-emerald-500/30 focus:border-emerald-400 transition placeholder:text-slate-400"
          aria-label="Search by technician name"
          data-testid="search-input"
        />
        {searchQuery && (
          <button
            onClick={clearSearch}
            className="absolute right-2 text-slate-400 hover:text-slate-600 cursor-pointer"
            aria-label="Clear search"
            data-testid="clear-search"
          >
            <X size={12} />
          </button>
        )}
      </div>




      {/* Status Summary Chips */}
      <div className="flex flex-wrap items-center gap-1.5" data-testid="status-summary-chips">
        {summary.ON_SITE > 0 && (
          <span className="flex items-center gap-1 px-2 py-1 rounded bg-amber-50 text-amber-700 text-[10px] font-bold border border-amber-200 uppercase tracking-wider" data-testid="summary-onsite">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
            {summary.ON_SITE} On Site
          </span>
        )}
        {summary.EN_ROUTE > 0 && (
          <span className="flex items-center gap-1 px-2 py-1 rounded bg-emerald-50 text-emerald-700 text-[10px] font-bold border border-emerald-200 uppercase tracking-wider" data-testid="summary-enroute">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            {summary.EN_ROUTE} En Route
          </span>
        )}
        {summary.ASSIGNED > 0 && (
          <span className="flex items-center gap-1 px-2 py-1 rounded bg-blue-50 text-blue-700 text-[10px] font-bold border border-blue-200 uppercase tracking-wider" data-testid="summary-assigned">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
            {summary.ASSIGNED} Assigned
          </span>
        )}
        {summary.CREATED > 0 && (
          <span className="flex items-center gap-1 px-2 py-1 rounded bg-slate-50 text-slate-650 text-[10px] font-bold border border-slate-200 uppercase tracking-wider" data-testid="summary-created">
            <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
            {summary.CREATED} Created
          </span>
        )}
      </div>
    </div>
  );
};

export default FilterToolbar;
