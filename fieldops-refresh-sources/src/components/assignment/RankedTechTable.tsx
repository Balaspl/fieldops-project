import React, { useState, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Search,
  ArrowUpDown,
  CheckCircle2,
  ChevronDown,
  User,
  X,
  SlidersHorizontal,
} from 'lucide-react';
import TopThreeHighlight, {
  RankedTechnician,
  MEDAL_CONFIG,
  MedalTier,
} from './TopThreeHighlight';
import { getScoreLevel, formatScore, ScoreBadge, CompactScorePanel } from './ScoreDisplay';
import StatusBadge from '../ui/StatusBadge';

export interface RankedTechTableProps {
  job: {
    id: number;
    customer_name: string;
    priority?: string;
    location?: string;
    issue_description?: string;
    service_type?: string;
    required_skill?: string;
  };
  candidates: RankedTechnician[];
  selectedTechId?: number;
  onSelect: (techId: number) => void;
  onAssign?: (techId: number) => void;
  onClose: () => void;
  hideHeader?: boolean;
}

type SortField = 'score' | 'distance' | 'skill' | 'workload';
type SortOrder = 'asc' | 'desc';

export default function RankedTechTable({
  job,
  candidates,
  selectedTechId,
  onSelect,
  onAssign,
  onClose,
  hideHeader = false,
}: RankedTechTableProps) {
  // Sort and Filter States
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('All');
  const [skillFilter, setSkillFilter] = useState('All');
  const [sortField, setSortField] = useState<SortField>('score');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');

  // Ensure overall descending order by score for ranking determination
  const rankedAll = useMemo(() => {
    return [...candidates].sort((a, b) => b.composite_score - a.composite_score);
  }, [candidates]);

  // Pinned Top 3 candidates
  const pinnedTop3 = useMemo(() => {
    return rankedAll.slice(0, 3);
  }, [rankedAll]);

  // The rest of the candidates (Rank 4+) which are subject to filter & sort
  const otherCandidates = useMemo(() => {
    return rankedAll.slice(3);
  }, [rankedAll]);

  // Selected candidate object containing scores
  const selectedCandidate = useMemo(() => {
    if (!selectedTechId) return null;
    return candidates.find((c) => c.technician_id === selectedTechId) || null;
  }, [candidates, selectedTechId]);

  // Extract unique skills for the filter dropdown
  const uniqueSkills = useMemo(() => {
    const seen = new Set();
    const result: string[] = [];
    candidates.forEach((c) => {
      if (c.technician_skill) {
        const val = c.technician_skill.trim();
        const norm = val.toUpperCase().replace(/_/g, " ").replace(/\s+/g, " ");
        if (!seen.has(norm)) {
          seen.add(norm);
          result.push(val);
        }
      }
    });
    return result;
  }, [candidates]);

  // Filtered & Sorted normal list
  const filteredAndSortedOthers = useMemo(() => {
    let result = [...otherCandidates];

    // Search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      result = result.filter(
        (c) =>
          c.technician_name.toLowerCase().includes(q) ||
          c.technician_skill.toLowerCase().includes(q)
      );
    }

    // Status filter
    if (statusFilter !== 'All') {
      result = result.filter(
        (c) => c.technician_status.toLowerCase() === statusFilter.toLowerCase()
      );
    }

    // Skill filter
    if (skillFilter !== 'All') {
      result = result.filter(
        (c) => c.technician_skill.toLowerCase() === skillFilter.toLowerCase()
      );
    }

    // Sort
    result.sort((a, b) => {
      let valA: number = 0;
      let valB: number = 0;

      if (sortField === 'score') {
        valA = a.composite_score;
        valB = b.composite_score;
      } else if (sortField === 'distance') {
        valA = a.distance_km;
        valB = b.distance_km;
      } else if (sortField === 'skill') {
        valA = a.skill_score;
        valB = b.skill_score;
      } else if (sortField === 'workload') {
        valA = a.workload_score;
        valB = b.workload_score;
      }

      if (sortOrder === 'asc') {
        return valA - valB;
      } else {
        return valB - valA;
      }
    });

    return result;
  }, [otherCandidates, searchQuery, statusFilter, skillFilter, sortField, sortOrder]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      // Distance and workload default to asc, score and skill default to desc
      setSortOrder(field === 'distance' || field === 'workload' ? 'asc' : 'desc');
    }
  };



  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -16 }}
      transition={{ duration: 0.35, ease: 'easeOut' }}
      className="bg-white rounded-2xl border border-slate-200/80 shadow-2xl shadow-slate-300/30 overflow-hidden flex flex-col"
      style={{ maxHeight: 'calc(100vh - 120px)' }}
      role="region"
      aria-label={`Technician Selection for Job ${job.id}`}
      data-testid="ranked-tech-selection-panel"
    >
      {/* ── Panel Header (sticky) ── */}
      {!hideHeader && (
        <div className="sticky top-0 z-20 bg-white/90 backdrop-blur-xl border-b border-slate-200/80 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 shadow-lg shadow-emerald-200/50">
              <User className="w-5 h-5 text-white" />
            </div>
            <div>
              <h2 className="text-base font-black text-slate-800 flex items-center gap-2">
                <span>Candidate Selection</span>
                <span className="text-[10px] px-2.5 py-1 rounded-lg bg-gradient-to-r from-slate-100 to-slate-50 text-slate-600 font-bold border border-slate-200/60">
                  Job #{job.id}
                </span>
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Assigning technician for <strong className="text-slate-700">{job.customer_name}</strong>
                {job.location && <span className="text-slate-400"> · {job.location}</span>}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close candidate selection panel"
            className="p-2 rounded-xl text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-all focus:outline-none focus:ring-2 focus:ring-slate-400"
            data-testid="panel-close-btn"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      )}

      {/* ── Scrollable content area ── */}
      <div className="flex-1 overflow-y-auto">

      {/* ── Pinned Top 3 Cards ── */}
      {pinnedTop3.length > 0 && (
        <div className="px-6 py-5 bg-gradient-to-b from-amber-50/30 via-white to-white border-b border-slate-100">
          <TopThreeHighlight
            technicians={pinnedTop3}
            jobId={job.id}
            jobLabel={`Job #${job.id}`}
            onSelect={onSelect}
            hideCloseBtn={true}
          />
        </div>
      )}

      {/* ── Selected Candidate Scoreboard ── */}
      {selectedCandidate && (
        <div className="px-6 py-4 bg-slate-50/50 border-b border-slate-200/60">
          <div className="max-w-[700px] mx-auto bg-white rounded-xl border border-slate-200/80 p-4 shadow-sm">
            <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-3 flex items-center gap-1.5">
              ⭐ Score Details: <span className="text-slate-800">{selectedCandidate.technician_name}</span>
            </h4>
            <CompactScorePanel
              composite_score={selectedCandidate.composite_score}
              proximity_score={selectedCandidate.proximity_score}
              skill_score={selectedCandidate.skill_score}
              workload_score={selectedCandidate.workload_score}
              distance_km={selectedCandidate.distance_km}
              active_jobs={selectedCandidate.active_jobs}
              max_capacity={selectedCandidate.max_capacity}
              is_top_3={pinnedTop3.some(c => c.technician_id === selectedCandidate.technician_id)}
            />
          </div>
        </div>
      )}

      {/* ── Filter / Sort Toolbar (sticky within scroll area) ── */}
      <div className="sticky top-0 z-10 px-6 py-3.5 border-b border-slate-200/80 bg-white/95 backdrop-blur-md flex flex-col md:flex-row md:items-center justify-between gap-3">
        {/* Search */}
        <div className="relative flex-1 max-w-md">
          <span className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
            <Search className="w-4 h-4" />
          </span>
          <input
            type="text"
            placeholder="Search technician by name or skill..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 border border-slate-200/80 rounded-xl text-sm bg-slate-50/80 focus:bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500/25 focus:border-emerald-500 transition-all placeholder-slate-400"
            aria-label="Search technicians"
            data-testid="toolbar-search-input"
          />
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex items-center gap-1.5 text-[10px] font-bold text-slate-400 uppercase tracking-widest">
            <SlidersHorizontal className="w-3.5 h-3.5" />
            <span>Filters:</span>
          </div>

          {/* Skill Filter */}
          <select
            value={skillFilter}
            onChange={(e) => setSkillFilter(e.target.value)}
            className="px-3 py-2 border border-slate-200/80 rounded-xl text-xs font-semibold bg-slate-50/80 focus:bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500/25 cursor-pointer transition-colors"
            aria-label="Filter by skill"
            data-testid="toolbar-skill-filter"
          >
            <option value="All">All Skills</option>
            {uniqueSkills.map((skill) => (
              <option key={skill} value={skill}>
                {skill}
              </option>
            ))}
          </select>

          {/* Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2 border border-slate-200/80 rounded-xl text-xs font-semibold bg-slate-50/80 focus:bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500/25 cursor-pointer transition-colors"
            aria-label="Filter by status"
            data-testid="toolbar-status-filter"
          >
            <option value="All">All Statuses</option>
            <option value="Available">Available</option>
            <option value="Busy">Busy</option>
            <option value="Assigned">Assigned</option>
            <option value="Offline">Offline</option>
            <option value="En Route">En Route</option>
            <option value="On Site">On Site</option>
            <option value="On Break">On Break</option>
            <option value="Suspended">Suspended</option>
          </select>
        </div>
      </div>

      {/* ── Table Area ── */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse" role="table" aria-label="Technician candidate pool">
          <thead>
            <tr className="bg-slate-50 border-b border-slate-200">
              <th className="px-6 py-3.5 text-[10.5px] font-black uppercase text-slate-400 tracking-wider whitespace-nowrap">Rank</th>
              <th className="px-6 py-3.5 text-[10.5px] font-black uppercase text-slate-400 tracking-wider whitespace-nowrap">Technician</th>
              <th className="px-6 py-3.5 text-[10.5px] font-black uppercase text-slate-400 tracking-wider whitespace-nowrap">Status</th>
              <th
                onClick={() => handleSort('distance')}
                className="px-6 py-3.5 text-[10.5px] font-black uppercase text-slate-400 tracking-wider cursor-pointer hover:bg-slate-100/80 transition-colors whitespace-nowrap"
                role="columnheader"
                aria-sort={sortField === 'distance' ? sortOrder : 'none'}
              >
                <div className="flex items-center gap-1.5">
                  Distance
                  <ArrowUpDown className="w-3.5 h-3.5" />
                </div>
              </th>
              <th
                onClick={() => handleSort('skill')}
                className="px-6 py-3.5 text-[10.5px] font-black uppercase text-slate-400 tracking-wider cursor-pointer hover:bg-slate-100/80 transition-colors whitespace-nowrap"
                role="columnheader"
                aria-sort={sortField === 'skill' ? sortOrder : 'none'}
              >
                <div className="flex items-center gap-1.5">
                  Skill Match
                  <ArrowUpDown className="w-3.5 h-3.5" />
                </div>
              </th>
              <th
                onClick={() => handleSort('workload')}
                className="px-6 py-3.5 text-[10.5px] font-black uppercase text-slate-400 tracking-wider cursor-pointer hover:bg-slate-100/80 transition-colors whitespace-nowrap"
                role="columnheader"
                aria-sort={sortField === 'workload' ? sortOrder : 'none'}
              >
                <div className="flex items-center gap-1.5">
                  Workload
                  <ArrowUpDown className="w-3.5 h-3.5" />
                </div>
              </th>
              <th
                onClick={() => handleSort('score')}
                className="px-6 py-3.5 text-[10.5px] font-black uppercase text-slate-400 tracking-wider cursor-pointer hover:bg-slate-100/80 transition-colors whitespace-nowrap"
                role="columnheader"
                aria-sort={sortField === 'score' ? sortOrder : 'none'}
              >
                <div className="flex items-center gap-1.5">
                  Score
                  <ArrowUpDown className="w-3.5 h-3.5" />
                </div>
              </th>
              <th className="px-6 py-3.5 text-[10.5px] font-black uppercase text-slate-400 tracking-wider text-right whitespace-nowrap">Actions</th>
            </tr>
          </thead>
          <tbody>
            {/* 1. Pinned Top 3 Pinned Rows */}
            {pinnedTop3.map((tech, idx) => {
              const tier = (idx === 0 ? 'gold' : idx === 1 ? 'silver' : 'bronze') as MedalTier;
              const cfg = MEDAL_CONFIG[tier];
              const isSelected = selectedTechId === tech.technician_id;
              const isUnavailable = ["busy", "offline"].includes((tech.technician_status || "").toLowerCase().trim());

              return (
                <tr
                  key={`pinned-${tech.technician_id}`}
                  className={[
                    'border-b border-slate-100 transition-colors',
                    isSelected ? 'bg-amber-50/40' : 'bg-gradient-to-r from-amber-50/20 to-transparent hover:bg-slate-50/60',
                  ].join(' ')}
                  data-testid={`table-pinned-row-${idx + 1}`}
                  role="row"
                  aria-label={`Pinned Rank ${idx + 1} recommended: ${tech.technician_name}`}
                >
                  {/* Rank */}
                  <td className="px-6 py-4 font-black text-slate-800 whitespace-nowrap">
                    <span
                      style={{ color: cfg.hex }}
                      className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-white border border-slate-200 text-xs shadow-sm font-black"
                    >
                      {idx + 1}
                    </span>
                  </td>
                  {/* Technician info */}
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center gap-3">
                      <div
                        style={{ background: `linear-gradient(135deg, ${cfg.hex}aa, ${cfg.hex})` }}
                        className="w-8 h-8 rounded-full flex items-center justify-center text-white font-extrabold text-xs shadow-sm"
                      >
                        {tech.technician_name.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <div className="text-sm font-bold text-slate-800 leading-tight">
                          {tech.technician_name}
                        </div>
                        <div className="text-[11px] text-slate-400 mt-0.5">
                          {tech.technician_skill}
                        </div>
                      </div>
                    </div>
                  </td>
                  {/* Status */}
                  <td className="px-6 py-4 whitespace-nowrap">
                    <StatusBadge status={tech.technician_status as any} size="sm" />
                  </td>
                  {/* Distance */}
                  <td className="px-6 py-4 font-bold text-slate-600 text-sm whitespace-nowrap">{tech.distance_km.toFixed(1)} km</td>
                  {/* Skill match */}
                  <td className="px-6 py-4 font-bold text-slate-600 text-sm whitespace-nowrap">{tech.skill_score.toFixed(0)}%</td>
                  {/* Workload */}
                  <td className="px-6 py-4 font-bold text-slate-600 text-sm whitespace-nowrap">
                    {tech.active_jobs}/{tech.max_capacity}
                  </td>
                  {/* Score */}
                  <td className="px-6 py-4 whitespace-nowrap">
                    <ScoreBadge score={tech.composite_score} label="Score" />
                  </td>
                  {/* Select Actions */}
                  <td className="px-6 py-4 text-right whitespace-nowrap">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => !isUnavailable && onSelect(tech.technician_id)}
                        disabled={isUnavailable}
                        className={[
                          'px-3 py-1.5 rounded-lg text-xs font-bold transition-all shadow-sm focus:outline-none focus:ring-2',
                          isUnavailable
                            ? 'bg-slate-100 text-slate-400 border border-slate-200 cursor-not-allowed opacity-60'
                            : isSelected
                            ? 'bg-emerald-600 text-white hover:bg-emerald-700 focus:ring-emerald-500'
                            : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-50 focus:ring-slate-300',
                        ].join(' ')}
                        aria-label={`Select ${tech.technician_name} for Job ${job.id}`}
                        data-testid={`table-pinned-select-${idx + 1}`}
                        title={isUnavailable ? `Cannot select: Technician is ${tech.technician_status}` : undefined}
                      >
                        {isUnavailable ? 'Unavailable' : isSelected ? 'Selected' : 'Select'}
                      </button>
                      {onAssign && (
                        <button
                          onClick={() => !isUnavailable && onAssign(tech.technician_id)}
                          disabled={isUnavailable}
                          className={[
                            'px-3 py-1.5 rounded-lg text-xs font-bold focus:outline-none focus:ring-2 shadow-sm',
                            isUnavailable
                              ? 'bg-slate-100 text-slate-400 cursor-not-allowed opacity-60'
                              : 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200 focus:ring-emerald-400'
                          ].join(' ')}
                          aria-label={`Assign ${tech.technician_name} immediately`}
                          data-testid={`table-pinned-assign-${idx + 1}`}
                          title={isUnavailable ? `Cannot assign: Technician is ${tech.technician_status}` : undefined}
                        >
                          Assign
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}

            {/* Divider row */}
            {filteredAndSortedOthers.length > 0 && (
              <tr>
                <td colSpan={8} className="bg-slate-50/80 px-6 py-2 border-y border-slate-200/60">
                  <span className="text-[10px] font-black uppercase text-slate-400 tracking-wider">
                    Other Candidates (Filtered & Sorted)
                  </span>
                </td>
              </tr>
            )}

            {/* 2. Sorted and Filtered Others list */}
            {filteredAndSortedOthers.map((tech, idx) => {
              const overallRank = idx + 4;
              const isSelected = selectedTechId === tech.technician_id;
              const isUnavailable = ["busy", "offline"].includes((tech.technician_status || "").toLowerCase().trim());

              return (
                <tr
                  key={`other-${tech.technician_id}`}
                  className={[
                    'border-b border-slate-100 transition-colors',
                    isSelected ? 'bg-emerald-50/40' : 'hover:bg-slate-50/40',
                  ].join(' ')}
                  data-testid={`table-other-row-${idx}`}
                  role="row"
                  aria-label={`Rank ${overallRank}: ${tech.technician_name}`}
                >
                  {/* Rank */}
                  <td className="px-6 py-4 font-semibold text-slate-400 text-sm whitespace-nowrap">#{overallRank}</td>
                  {/* Technician info */}
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-slate-200 text-slate-600 font-extrabold text-xs flex items-center justify-center shadow-sm">
                        {tech.technician_name.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <div className="text-sm font-bold text-slate-700 leading-tight">
                          {tech.technician_name}
                        </div>
                        <div className="text-[11px] text-slate-400 mt-0.5">
                          {tech.technician_skill}
                        </div>
                      </div>
                    </div>
                  </td>
                  {/* Status */}
                  <td className="px-6 py-4 whitespace-nowrap">
                    <StatusBadge status={tech.technician_status as any} size="sm" />
                  </td>
                  {/* Distance */}
                  <td className="px-6 py-4 font-semibold text-slate-500 text-sm whitespace-nowrap">{tech.distance_km.toFixed(1)} km</td>
                  {/* Skill match */}
                  <td className="px-6 py-4 font-semibold text-slate-500 text-sm whitespace-nowrap">{tech.skill_score.toFixed(0)}%</td>
                  {/* Workload */}
                  <td className="px-6 py-4 font-semibold text-slate-500 text-sm whitespace-nowrap">
                    {tech.active_jobs}/{tech.max_capacity}
                  </td>
                  {/* Score */}
                  <td className="px-6 py-4 whitespace-nowrap">
                    <ScoreBadge score={tech.composite_score} label="Score" />
                  </td>
                  {/* Select Actions */}
                  <td className="px-6 py-4 text-right whitespace-nowrap">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => !isUnavailable && onSelect(tech.technician_id)}
                        disabled={isUnavailable}
                        className={[
                          'px-3 py-1.5 rounded-lg text-xs font-bold transition-all shadow-sm focus:outline-none focus:ring-2',
                          isUnavailable
                            ? 'bg-slate-100 text-slate-400 border border-slate-200 cursor-not-allowed opacity-60'
                            : isSelected
                            ? 'bg-emerald-600 text-white hover:bg-emerald-700 focus:ring-emerald-500'
                            : 'bg-white text-slate-700 border border-slate-200 hover:bg-slate-50 focus:ring-slate-300',
                        ].join(' ')}
                        aria-label={`Select ${tech.technician_name} for Job ${job.id}`}
                        data-testid={`table-other-select-${idx}`}
                        title={isUnavailable ? `Cannot select: Technician is ${tech.technician_status}` : undefined}
                      >
                        {isUnavailable ? 'Unavailable' : isSelected ? 'Selected' : 'Select'}
                      </button>
                      {onAssign && (
                        <button
                          onClick={() => !isUnavailable && onAssign(tech.technician_id)}
                          disabled={isUnavailable}
                          className={[
                            'px-3 py-1.5 rounded-lg text-xs font-bold focus:outline-none focus:ring-2 shadow-sm',
                            isUnavailable
                              ? 'bg-slate-100 text-slate-400 cursor-not-allowed opacity-60'
                              : 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200 focus:ring-emerald-400'
                          ].join(' ')}
                          aria-label={`Assign ${tech.technician_name} immediately`}
                          data-testid={`table-other-assign-${idx}`}
                          title={isUnavailable ? `Cannot assign: Technician is ${tech.technician_status}` : undefined}
                        >
                          Assign
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}

            {/* Empty state for search/filters */}
            {filteredAndSortedOthers.length === 0 && (
              <tr>
                <td colSpan={8} className="px-6 py-10 text-center text-slate-400 text-sm">
                  No other candidates match the selected filters or search criteria.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* ── Table Footer ── */}
      <div className="bg-gradient-to-r from-slate-50 to-white px-6 py-3 border-t border-slate-200/80 flex items-center justify-between text-[11px] text-slate-400 font-medium">
        <span>Total Candidates: <strong className="text-slate-600">{candidates.length}</strong></span>
        <span>Top 3 pinned · Sort & filters affect lower list</span>
      </div>

      </div>{/* end scrollable content area */}
    </motion.div>
  );
}
