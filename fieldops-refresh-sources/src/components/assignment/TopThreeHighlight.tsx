/**
 * TopThreeHighlight.tsx
 *
 * Displays the top 3 ranked technicians for a pending job with
 * gold / silver / bronze medal styling, recommendation reasons,
 * stagger-animated entrance, and an override ("Select Other") path.
 *
 * Props
 * ─────
 *  technicians  — ranked array (index 0 = rank 1). Pass ≤ 3 items.
 *  jobId        — ID of the pending job being considered
 *  jobLabel     — short human-readable job title for the header
 *  onSelect     — fired with technician_id when dispatcher clicks "Select"
 *  onClose      — fired when dispatcher clicks "Select Other Technician"
 */

import { useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Star,
  MapPin,
  Briefcase,
  Target,
  X,
  ChevronDown,
  Medal,
  CheckCircle2,
  User,
} from 'lucide-react';
import { getScoreLevel, formatScore, ScoreBadge } from './ScoreDisplay';
import StatusBadge from '../ui/StatusBadge';

/* ═══════════════════════════════════════════════════════════════════════
   Public Types
   ═══════════════════════════════════════════════════════════════════════ */

export interface RankedTechnician {
  technician_id: number;
  technician_name: string;
  technician_skill: string;
  technician_status: string;
  composite_score: number;   // 0–100
  proximity_score: number;
  skill_score: number;
  workload_score: number;
  distance_km: number;
  active_jobs: number;
  max_capacity: number;
}

export type MedalTier = 'gold' | 'silver' | 'bronze';

export interface TopThreeHighlightProps {
  technicians: RankedTechnician[];
  jobId: number;
  jobLabel?: string;
  onSelect: (technicianId: number) => void;
  onClose?: () => void;
  onSelectOther?: () => void;
  hideCloseBtn?: boolean;
}

/* ═══════════════════════════════════════════════════════════════════════
   Medal Tokens
   ═══════════════════════════════════════════════════════════════════════ */

export const MEDAL_CONFIG: Record<MedalTier, {
  label: string;
  rank: number;
  gradient: string;
  border: string;
  bg: string;
  textAccent: string;
  iconColor: string;
  glowColor: string;
  hex: string;
}> = {
  gold: {
    label: 'Gold',
    rank: 1,
    gradient: 'from-amber-400 via-yellow-300 to-amber-500',
    border: 'border-amber-400',
    bg: 'bg-gradient-to-br from-amber-50 to-yellow-50',
    textAccent: 'text-amber-700',
    iconColor: 'text-amber-500',
    glowColor: 'shadow-amber-200',
    hex: '#F59E0B',
  },
  silver: {
    label: 'Silver',
    rank: 2,
    gradient: 'from-slate-400 via-slate-300 to-slate-500',
    border: 'border-slate-400',
    bg: 'bg-gradient-to-br from-slate-50 to-gray-50',
    textAccent: 'text-slate-600',
    iconColor: 'text-slate-400',
    glowColor: 'shadow-slate-200',
    hex: '#94A3B8',
  },
  bronze: {
    label: 'Bronze',
    rank: 3,
    gradient: 'from-orange-400 via-amber-300 to-orange-500',
    border: 'border-orange-400',
    bg: 'bg-gradient-to-br from-orange-50 to-amber-50',
    textAccent: 'text-orange-700',
    iconColor: 'text-orange-500',
    glowColor: 'shadow-orange-200',
    hex: '#CD7C3A',
  },
};

const TIER_ORDER: MedalTier[] = ['gold', 'silver', 'bronze'];

/* ═══════════════════════════════════════════════════════════════════════
   Recommendation Reason Derivation
   ═══════════════════════════════════════════════════════════════════════ */

/** Compute a short, human-readable recommendation reason for a technician. */
export function getRecommendationReason(tech: RankedTechnician): string {
  const { proximity_score, skill_score, workload_score, distance_km, active_jobs, max_capacity } = tech;
  const max = Math.max(proximity_score, skill_score, workload_score);

  if (skill_score === max && skill_score > proximity_score && skill_score > workload_score) {
    return `Best skill match (${skill_score.toFixed(0)}%)`;
  }
  if (proximity_score === max && proximity_score > skill_score && proximity_score > workload_score) {
    return `Nearest available (${distance_km.toFixed(1)}km)`;
  }
  if (workload_score === max && workload_score > skill_score && workload_score > proximity_score) {
    return `Low workload (${active_jobs}/${max_capacity} jobs)`;
  }
  // Tie-break: pick strongest
  if (skill_score >= proximity_score && skill_score >= workload_score) {
    return `Best skill match (${skill_score.toFixed(0)}%)`;
  }
  if (proximity_score >= workload_score) {
    return `Nearest available (${distance_km.toFixed(1)}km)`;
  }
  return `Best overall balance`;
}

/** Return the Lucide icon component name for a reason string. */
function ReasonIcon({ reason }: { reason: string }) {
  if (reason.startsWith('Best skill')) return <Target className="w-3.5 h-3.5" aria-hidden="true" />;
  if (reason.startsWith('Nearest')) return <MapPin className="w-3.5 h-3.5" aria-hidden="true" />;
  if (reason.startsWith('Low workload')) return <Briefcase className="w-3.5 h-3.5" aria-hidden="true" />;
  return <Star className="w-3.5 h-3.5" aria-hidden="true" />;
}


/* ═══════════════════════════════════════════════════════════════════════
   MedalIcon  (SVG medal shape with gradient fill)
   ═══════════════════════════════════════════════════════════════════════ */

function MedalIcon({ tier }: { tier: MedalTier }) {
  const colors: Record<MedalTier, string> = {
    gold: '#F59E0B',
    silver: '#94A3B8',
    bronze: '#CD7C3A',
  };
  const fill = colors[tier];
  const rank = MEDAL_CONFIG[tier].rank;

  return (
    <div
      className="relative flex items-center justify-center"
      aria-hidden="true"
      data-testid={`medal-icon-${tier}`}
    >
      <Medal
        style={{ color: fill, filter: `drop-shadow(0 2px 4px ${fill}55)` }}
        className="w-10 h-10"
        strokeWidth={1.5}
      />
      <span
        className="absolute text-white font-black text-[11px] leading-none"
        style={{ top: '44%', transform: 'translateY(-50%)' }}
      >
        {rank}
      </span>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   RankCard
   ═══════════════════════════════════════════════════════════════════════ */

export interface RankCardProps {
  rank: 1 | 2 | 3;
  medal: MedalTier;
  tech: RankedTechnician;
  reason: string;
  onSelect: (technicianId: number) => void;
  animationDelay?: number;
}

export function RankCard({ rank, medal, tech, reason, onSelect, animationDelay = 0 }: RankCardProps) {
  const cfg = MEDAL_CONFIG[medal];
  const level = getScoreLevel(tech.composite_score);

  return (
    <motion.div
      role="listitem"
      aria-label={`Rank ${rank} — ${tech.technician_name}`}
      data-testid={`rank-card-${rank}`}
      data-medal={medal}
      initial={{ opacity: 0, y: 24, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -16, scale: 0.97 }}
      transition={{
        duration: 0.4,
        delay: animationDelay,
        ease: [0.25, 0.46, 0.45, 0.94],
      }}
      className={[
        'relative flex flex-col gap-2.5 rounded-xl p-4 pt-6 border-2',
        cfg.bg,
        cfg.border,
        `shadow-md ${cfg.glowColor}`,
        'transition-all duration-200 hover:shadow-lg hover:-translate-y-0.5',
        rank === 1 ? 'ring-2 ring-amber-400/20' : '',
      ].join(' ')}
    >
      {/* ── Rank badge (top-left) ── */}
      <div className="absolute -top-3 -left-1 z-10">
        <MedalIcon tier={medal} />
      </div>

      {/* ── Recommended badge (top-right, rank 1 only) ── */}
      {rank === 1 && (
        <motion.div
          initial={{ scale: 0, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: 'spring', stiffness: 220, damping: 14, delay: animationDelay + 0.25 }}
          className="absolute -top-3 right-3"
          data-testid="recommended-badge"
        >
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-gradient-to-r from-amber-500 to-orange-500 text-white text-[10px] font-black uppercase tracking-wider shadow-md shadow-amber-400/40">
            <Star className="w-3 h-3 fill-white" aria-hidden="true" />
            Recommended
          </span>
        </motion.div>
      )}

      {/* ── Header row: avatar + name + score ── */}
      <div className="flex items-start gap-3 mt-1">
        {/* Avatar */}
        <div
          className={`flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center bg-gradient-to-br ${cfg.gradient} text-white font-black text-base shadow-sm ml-1`}
          aria-hidden="true"
        >
          {tech.technician_name.charAt(0).toUpperCase()}
        </div>

        {/* Name + skill + status */}
        <div className="flex-1 min-w-0">
          <p className="text-xs font-extrabold text-slate-800 truncate leading-tight">
            {tech.technician_name}
          </p>
          <p className="text-[10px] text-slate-500 truncate mt-0.5">{tech.technician_skill}</p>
          <div className="mt-1">
            <StatusBadge status={tech.technician_status as any} size="sm" data-testid={`status-pill-${tech.technician_status.toLowerCase()}`} />
          </div>
        </div>

        {/* Composite score */}
        <div className="flex-shrink-0 text-right">
          <ScoreBadge score={tech.composite_score} label="Score" />
          <p className={`text-[9px] mt-0.5 font-semibold ${cfg.textAccent}`}>
            {level === 'high' ? 'Excellent' : level === 'medium' ? 'Good' : 'Fair'}
          </p>
        </div>
      </div>

      {/* ── Recommendation reason chip ── */}
      <div
        className={`flex items-center gap-1 px-2 py-1 rounded-md bg-white/70 border ${cfg.border} backdrop-blur-sm`}
        data-testid={`reason-chip-${rank}`}
      >
        <span className={cfg.textAccent}>
          <ReasonIcon reason={reason} />
        </span>
        <span className={`text-[11px] font-semibold ${cfg.textAccent}`} data-testid={`reason-text-${rank}`}>
          {reason}
        </span>
      </div>

      {/* ── Mini stat row ── */}
      <div className="grid grid-cols-3 gap-1.5 text-center">
        {[
          { label: 'Skill', value: tech.skill_score },
          { label: 'Proximity', value: tech.proximity_score },
          { label: 'Workload', value: tech.workload_score },
        ].map(({ label, value }) => {
          const lv = getScoreLevel(value);
          const color = lv === 'high' ? 'text-emerald-600' : lv === 'medium' ? 'text-amber-600' : 'text-rose-600';
          return (
            <div key={label} className="flex flex-col items-center gap-0.5 bg-white/70 rounded-lg py-1 px-1 border border-white/80 shadow-sm">
              <span className={`text-sm font-black tabular-nums ${color}`}>{formatScore(value)}</span>
              <span className="text-[8px] font-bold text-slate-400 uppercase tracking-wider">{label}</span>
            </div>
          );
        })}
      </div>

      {/* ── Meta row: distance + workload ── */}
      <div className="flex items-center gap-2 text-[11px] text-slate-500 px-1">
        <span className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-sky-50 border border-sky-100">
          <MapPin className="w-3 h-3 text-sky-500" aria-hidden="true" />
          <span className="font-bold text-sky-700">{tech.distance_km.toFixed(1)} km</span>
        </span>
        <span className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-50 border border-slate-100">
          <Briefcase className="w-3 h-3 text-slate-400" aria-hidden="true" />
          <span className="font-bold text-slate-600">{tech.active_jobs}/{tech.max_capacity} jobs</span>
        </span>
      </div>

      {/* ── Select button ── */}
      <motion.button
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.97 }}
        onClick={() => onSelect(tech.technician_id)}
        aria-label={`Select ${tech.technician_name} for this job`}
        data-testid={`select-btn-${rank}`}
        className={[
          'w-full flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg',
          'text-white text-xs font-extrabold tracking-wide',
          `bg-gradient-to-r ${cfg.gradient}`,
          'shadow-sm transition-all duration-200 hover:shadow-md',
          'focus:outline-none focus:ring-2 focus:ring-offset-2',
          rank === 1 ? 'focus:ring-amber-400' : rank === 2 ? 'focus:ring-slate-400' : 'focus:ring-orange-400',
        ].join(' ')}
      >
        <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />
        Select {tech.technician_name.split(' ')[0]}
      </motion.button>
    </motion.div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   TopThreeHighlight  (main export)
   ═══════════════════════════════════════════════════════════════════════ */

export default function TopThreeHighlight({
  technicians,
  jobId,
  jobLabel,
  onSelect,
  onClose,
  onSelectOther,
  hideCloseBtn,
}: TopThreeHighlightProps) {
  // Ensure sorted descending by composite_score, cap at 3
  const ranked = useMemo(
    () =>
      [...technicians]
        .sort((a, b) => b.composite_score - a.composite_score)
        .slice(0, 3),
    [technicians]
  );

  // Pre-compute reasons
  const reasons = useMemo(() => ranked.map(getRecommendationReason), [ranked]);

  return (
    <AnimatePresence>
      <motion.section
        key={`top3-job-${jobId}`}
        initial={{ opacity: 0, height: 0 }}
        animate={{ opacity: 1, height: 'auto' }}
        exit={{ opacity: 0, height: 0 }}
        transition={{ duration: 0.35, ease: 'easeOut' }}
        className="overflow-hidden"
        aria-label="Top 3 Recommended Technicians"
        data-testid="top-three-highlight"
      >
        <div className="rounded-xl border border-amber-200/80 bg-gradient-to-br from-white via-amber-50/10 to-white shadow-md p-4 mb-2">

          {/* ── Section header ── */}
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-amber-400 to-orange-500 shadow-md">
                <Star className="w-4 h-4 text-white fill-white" aria-hidden="true" />
              </div>
              <div>
                <h3 className="text-xs font-black text-slate-800 leading-tight">
                  Top 3 Recommended
                </h3>
                {jobLabel && (
                  <p className="text-[10px] text-slate-400 leading-tight mt-0.5">
                    for {jobLabel}
                  </p>
                )}
              </div>
              <span
                className="ml-1 inline-flex items-center px-2 py-0.5 rounded-md bg-amber-100/80 text-amber-700 text-[9px] font-bold border border-amber-200/80"
                data-testid="top-3-section-badge"
              >
                AI Ranked
              </span>
            </div>

            {/* Close / Select Other */}
            <div className="flex items-center gap-1.5">
              {onSelectOther && (
                <button
                  onClick={onSelectOther}
                  aria-label="Select other technician"
                  data-testid="select-other-btn"
                  className="flex items-center gap-1 text-[11px] font-semibold text-slate-500 hover:text-slate-700 px-2 py-1 rounded-lg hover:bg-slate-100 transition-all"
                >
                  <User className="w-3 h-3" aria-hidden="true" />
                  Select Other
                  <ChevronDown className="w-3 h-3" aria-hidden="true" />
                </button>
              )}
              {onClose && !hideCloseBtn && (
                <button
                  onClick={onClose}
                  aria-label="Close recommendations panel"
                  data-testid="close-btn"
                  className="flex items-center justify-center w-7 h-7 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-all"
                >
                  <X className="w-3.5 h-3.5" aria-hidden="true" />
                </button>
              )}
            </div>
          </div>

          {/* ── Rank cards grid ── */}
          <div
            role="list"
            aria-label="Ranked technician recommendations"
            className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-3 pt-1"
          >
            {ranked.map((tech, idx) => {
              const tier = TIER_ORDER[idx];
              const rank = (idx + 1) as 1 | 2 | 3;
              return (
                <RankCard
                  key={tech.technician_id}
                  rank={rank}
                  medal={tier}
                  tech={tech}
                  reason={reasons[idx]}
                  onSelect={onSelect}
                  animationDelay={idx * 0.1}
                />
              );
            })}
          </div>

          {/* ── Footer note ── */}
          <p className="mt-2 text-center text-[9px] text-slate-400">
            Scores based on skill match · proximity · current workload · Dispatcher can override at any time
          </p>
        </div>
      </motion.section>
    </AnimatePresence>
  );
}
