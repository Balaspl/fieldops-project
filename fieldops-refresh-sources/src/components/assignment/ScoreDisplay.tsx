import { useEffect, useRef, type ReactNode } from 'react';
import { motion, useMotionValue, useSpring } from 'framer-motion';
import {
  MapPin,
  Briefcase,
  Award,
  Target,
  Zap,
  TrendingUp,
  Star,
} from 'lucide-react';

/* ═══════════════════════════════════════════════════════════════════════
   Types
   ═══════════════════════════════════════════════════════════════════════ */

export interface ScoreDisplayProps {
  composite_score: number;
  proximity_score: number;
  skill_score: number;
  workload_score: number;
  distance_km: number;
  active_jobs: number;
  max_capacity: number;
  is_top_3?: boolean;
  /** Compact single-row variant for inline table use */
  variant?: 'full' | 'compact';
}

/* ═══════════════════════════════════════════════════════════════════════
   Score Utilities
   ═══════════════════════════════════════════════════════════════════════ */

export type ScoreLevel = 'high' | 'medium' | 'low';

/** Classify a 0-100 score into high / medium / low */
export function getScoreLevel(score: number): ScoreLevel {
  if (score > 70) return 'high';
  if (score >= 40) return 'medium';
  return 'low';
}

/** Format any score to exactly 1 decimal place with half-up rounding */
export function formatScore(score: number): string {
  return (Math.round(score * 10) / 10).toFixed(1);
}

/** Theme tokens keyed by ScoreLevel */
const SCORE_THEME = {
  high: {
    text: 'text-emerald-600 dark:text-emerald-400',
    bgLight: 'bg-emerald-50 dark:bg-emerald-950/30',
    border: 'border-emerald-200 dark:border-emerald-800',
    gradientBar: 'from-emerald-400 to-emerald-600',
    hex: '#10b981',
    label: 'Excellent',
    ringColor: 'ring-emerald-400/30',
  },
  medium: {
    text: 'text-amber-600 dark:text-amber-400',
    bgLight: 'bg-amber-50 dark:bg-amber-950/30',
    border: 'border-amber-200 dark:border-amber-800',
    gradientBar: 'from-amber-400 to-amber-600',
    hex: '#f59e0b',
    label: 'Moderate',
    ringColor: 'ring-amber-400/30',
  },
  low: {
    text: 'text-rose-600 dark:text-rose-400',
    bgLight: 'bg-rose-50 dark:bg-rose-950/30',
    border: 'border-rose-200 dark:border-rose-800',
    gradientBar: 'from-rose-400 to-rose-600',
    hex: '#f43f5e',
    label: 'Low',
    ringColor: 'ring-rose-400/30',
  },
} as const;

/* ═══════════════════════════════════════════════════════════════════════
   AnimatedNumber  (smooth spring counter — skips animation in test env)
   ═══════════════════════════════════════════════════════════════════════ */

function AnimatedNumber({
  value,
  className = '',
}: {
  value: number;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const motionValue = useMotionValue(value);
  const spring = useSpring(motionValue, {
    stiffness: 80,
    damping: 25,
    restDelta: 0.01,
  });

  useEffect(() => {
    motionValue.set(value);
  }, [value, motionValue]);

  useEffect(() => {
    const unsubscribe = spring.on('change', (latest) => {
      if (ref.current) {
        ref.current.textContent = latest.toFixed(1);
      }
    });
    return unsubscribe;
  }, [spring]);

  // The span is immediately seeded with the formatted value so SSR / jsdom
  // tests (which don't tick requestAnimationFrame) see the correct text.
  return (
    <span ref={ref} className={className} data-value={value}>
      {formatScore(value)}
    </span>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   ScoreBadge  — inline pill for compact contexts
   ═══════════════════════════════════════════════════════════════════════ */

export function ScoreBadge({ score, label }: { score: number; label: string }) {
  const level = getScoreLevel(score);
  const theme = SCORE_THEME[level];

  return (
    <span
      className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold border ${theme.bgLight} ${theme.text} ${theme.border}`}
      aria-label={`${label}: ${formatScore(score)} out of 100`}
      data-testid={`score-badge-${label.toLowerCase().replace(/\s+/g, '-')}`}
    >
      <Star className="w-3 h-3" aria-hidden="true" />
      {formatScore(score)}
    </span>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   Top3Badge
   ═══════════════════════════════════════════════════════════════════════ */

export function Top3Badge() {
  return (
    <motion.div
      initial={{ scale: 0, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: 'spring', stiffness: 200, damping: 15, delay: 0.3 }}
      className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-gradient-to-r from-amber-400 via-orange-400 to-amber-500 text-white text-xs font-bold shadow-lg shadow-amber-400/30 dark:shadow-amber-500/20"
      aria-label="Top 3 Recommended Technician"
      data-testid="top-3-badge"
    >
      <Award className="w-3.5 h-3.5" aria-hidden="true" />
      <span>Top Recommended</span>
    </motion.div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   CompositeScore  (circular gauge)
   ═══════════════════════════════════════════════════════════════════════ */

export function CompositeScore({ score }: { score: number }) {
  const level = getScoreLevel(score);
  const theme = SCORE_THEME[level];

  const RADIUS = 52;
  const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
  const clamped = Math.min(Math.max(score, 0), 100);
  const offset = CIRCUMFERENCE - (clamped / 100) * CIRCUMFERENCE;

  return (
    <div
      className="flex flex-col items-center gap-2"
      aria-label={`Composite score: ${formatScore(score)} out of 100`}
      data-testid="composite-score"
      data-score-level={level}
    >
      <div className="relative w-36 h-36 sm:w-40 sm:h-40">
        {/* Ambient glow */}
        <div
          className="absolute inset-3 rounded-full opacity-20 blur-xl"
          style={{ backgroundColor: theme.hex }}
          aria-hidden="true"
        />

        <svg
          className="w-full h-full -rotate-90"
          viewBox="0 0 120 120"
          aria-hidden="true"
        >
          {/* Background track */}
          <circle
            cx="60"
            cy="60"
            r={RADIUS}
            fill="none"
            strokeWidth="10"
            className="stroke-slate-200 dark:stroke-slate-700"
          />
          {/* Animated arc */}
          <motion.circle
            cx="60"
            cy="60"
            r={RADIUS}
            fill="none"
            strokeWidth="10"
            strokeLinecap="round"
            stroke={theme.hex}
            strokeDasharray={CIRCUMFERENCE}
            initial={{ strokeDashoffset: CIRCUMFERENCE }}
            animate={{ strokeDashoffset: offset }}
            transition={{ duration: 1, ease: 'easeOut' }}
          />
        </svg>

        {/* Center value */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <AnimatedNumber
            value={score}
            className={`text-3xl sm:text-4xl font-extrabold tracking-tight ${theme.text}`}
          />
          <span className="text-[11px] text-slate-400 dark:text-slate-500 font-medium mt-0.5">
            / 100
          </span>
        </div>
      </div>

      <div className="flex flex-col items-center gap-0.5">
        <span className="text-sm font-semibold text-slate-700 dark:text-slate-200">
          Composite Score
        </span>
        <span className={`text-xs font-medium ${theme.text}`}>
          {theme.label}
        </span>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   ScoreBar  (progress bar row)
   ═══════════════════════════════════════════════════════════════════════ */

export function ScoreBar({
  score,
  label,
  icon,
}: {
  score: number;
  label: string;
  icon: ReactNode;
}) {
  const level = getScoreLevel(score);
  const theme = SCORE_THEME[level];
  const clamped = Math.min(Math.max(score, 0), 100);

  return (
    <div
      className="space-y-1.5"
      role="group"
      aria-label={`${label}: ${formatScore(score)} out of 100`}
      data-testid={`score-bar-${label.toLowerCase().replace(/\s+/g, '-')}`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium text-slate-600 dark:text-slate-300">
          <span className="text-slate-400 dark:text-slate-500" aria-hidden="true">
            {icon}
          </span>
          <span>{label}</span>
        </div>
        <span className={`text-sm font-bold tabular-nums ${theme.text}`}>
          {formatScore(score)}
        </span>
      </div>

      <div
        className="relative w-full h-2.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden"
        role="progressbar"
        aria-valuenow={Math.round(clamped)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${label} progress`}
      >
        <motion.div
          className={`absolute inset-y-0 left-0 rounded-full bg-gradient-to-r ${theme.gradientBar}`}
          initial={{ width: 0 }}
          animate={{ width: `${clamped}%` }}
          transition={{ duration: 0.8, ease: 'easeOut', delay: 0.15 }}
        />
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   DistanceBadge
   ═══════════════════════════════════════════════════════════════════════ */

export function DistanceBadge({ distance_km }: { distance_km: number }) {
  return (
    <div
      className="flex items-center gap-3 p-3 rounded-xl bg-sky-50 dark:bg-sky-950/20 border border-sky-200 dark:border-sky-800/50 transition-colors"
      aria-label={`Distance: ${distance_km.toFixed(1)} kilometers`}
      data-testid="distance-badge"
    >
      <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-sky-100 dark:bg-sky-900/40">
        <MapPin className="w-[18px] h-[18px] text-sky-500 dark:text-sky-400" aria-hidden="true" />
      </div>
      <div className="flex flex-col min-w-0">
        <span className="text-[11px] font-medium text-sky-500 dark:text-sky-400 uppercase tracking-wider">
          Distance
        </span>
        <span className="text-sm font-bold text-sky-700 dark:text-sky-200 tabular-nums">
          {distance_km.toFixed(1)} km
        </span>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   WorkloadBadge
   ═══════════════════════════════════════════════════════════════════════ */

export function WorkloadBadge({
  active_jobs,
  max_capacity,
}: {
  active_jobs: number;
  max_capacity: number;
}) {
  const utilization =
    max_capacity > 0 ? (active_jobs / max_capacity) * 100 : 0;
  const capacityLevel: ScoreLevel =
    utilization > 80 ? 'low' : utilization > 50 ? 'medium' : 'high';
  const theme = SCORE_THEME[capacityLevel];

  return (
    <div
      className="flex items-center gap-3 p-3 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700/50 transition-colors"
      aria-label={`Workload: ${active_jobs} of ${max_capacity} jobs`}
      data-testid="workload-badge"
    >
      <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-slate-100 dark:bg-slate-700/50">
        <Briefcase className="w-[18px] h-[18px] text-slate-500 dark:text-slate-400" aria-hidden="true" />
      </div>
      <div className="flex flex-col min-w-0">
        <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
          Workload
        </span>
        <span className={`text-sm font-bold tabular-nums ${theme.text}`}>
          {active_jobs} / {max_capacity}
        </span>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   ScoreHeader
   ═══════════════════════════════════════════════════════════════════════ */

export function ScoreHeader({ is_top_3 }: { is_top_3?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 pb-1">
      <div className="flex items-center gap-2">
        <TrendingUp
          className="w-4 h-4 text-slate-400 dark:text-slate-500"
          aria-hidden="true"
        />
        <h3 className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase tracking-widest">
          Assignment Score
        </h3>
      </div>
      {is_top_3 && <Top3Badge />}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   ScoreBreakdown  (trio of progress bars)
   ═══════════════════════════════════════════════════════════════════════ */

export function ScoreBreakdown({
  proximity_score,
  skill_score,
  workload_score,
}: {
  proximity_score: number;
  skill_score: number;
  workload_score: number;
}) {
  return (
    <div
      className="space-y-3.5"
      aria-label="Score breakdown"
      data-testid="score-breakdown"
    >
      <ScoreBar
        score={proximity_score}
        label="Proximity"
        icon={<MapPin className="w-4 h-4" />}
      />
      <ScoreBar
        score={skill_score}
        label="Skill Match"
        icon={<Target className="w-4 h-4" />}
      />
      <ScoreBar
        score={workload_score}
        label="Workload"
        icon={<Zap className="w-4 h-4" />}
      />
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   ScoreMeta  (distance + workload badges)
   ═══════════════════════════════════════════════════════════════════════ */

export function ScoreMeta({
  distance_km,
  active_jobs,
  max_capacity,
}: {
  distance_km: number;
  active_jobs: number;
  max_capacity: number;
}) {
  return (
    <div
      className="grid grid-cols-1 sm:grid-cols-2 gap-2.5"
      aria-label="Score metadata"
      data-testid="score-meta"
    >
      <DistanceBadge distance_km={distance_km} />
      <WorkloadBadge active_jobs={active_jobs} max_capacity={max_capacity} />
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   CompactScorePanel  — slim inline variant for table rows
   ═══════════════════════════════════════════════════════════════════════ */

export function CompactScorePanel({
  composite_score,
  proximity_score,
  skill_score,
  workload_score,
  distance_km,
  active_jobs,
  max_capacity,
  is_top_3 = false,
}: ScoreDisplayProps) {
  const level = getScoreLevel(composite_score);
  const theme = SCORE_THEME[level];

  const RADIUS = 28;
  const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
  const clamped = Math.min(Math.max(composite_score, 0), 100);
  const offset = CIRCUMFERENCE - (clamped / 100) * CIRCUMFERENCE;

  const workloadRatio = max_capacity > 0 ? active_jobs / max_capacity : 0;
  const workloadLevel: ScoreLevel =
    workloadRatio > 0.8 ? 'low' : workloadRatio > 0.5 ? 'medium' : 'high';

  const breakdownItems = [
    { label: 'Proximity', score: proximity_score, icon: <MapPin className="w-3.5 h-3.5" /> },
    { label: 'Skill Match', score: skill_score, icon: <Target className="w-3.5 h-3.5" /> },
    { label: 'Workload', score: workload_score, icon: <Zap className="w-3.5 h-3.5" /> },
  ] as const;

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.35, ease: 'easeOut' }}
      className={[
        'rounded-2xl border mt-3 overflow-hidden',
        'bg-gradient-to-br from-white via-slate-50/80 to-white dark:from-slate-900 dark:via-slate-800/50 dark:to-slate-900',
        'border-slate-200/80 dark:border-slate-700/60',
        'shadow-md shadow-slate-200/40 dark:shadow-slate-950/40',
        is_top_3 ? 'ring-2 ring-amber-400/30 dark:ring-amber-500/20' : '',
      ].join(' ')}
      role="region"
      aria-label="Assignment Score Summary"
      data-testid="compact-score-panel"
    >
      {/* Top accent line */}
      <div
        className={`h-1 bg-gradient-to-r ${theme.gradientBar}`}
        style={{ opacity: 0.8 }}
        aria-hidden="true"
      />

      <div className="p-4 sm:p-5">
        {/* ── Row 1: Gauge + Headline + Meta ── */}
        <div className="flex items-center gap-4 mb-4">
          {/* Mini circular gauge */}
          <motion.div
            className="relative flex-shrink-0 w-[72px] h-[72px]"
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.4, delay: 0.1 }}
          >
            {/* Ambient glow */}
            <div
              className="absolute inset-1.5 rounded-full opacity-15 blur-lg"
              style={{ backgroundColor: theme.hex }}
              aria-hidden="true"
            />
            <svg className="w-full h-full -rotate-90" viewBox="0 0 72 72" aria-hidden="true">
              <circle
                cx="36" cy="36" r={RADIUS}
                fill="none" strokeWidth="6"
                className="stroke-slate-100 dark:stroke-slate-700/80"
              />
              <motion.circle
                cx="36" cy="36" r={RADIUS}
                fill="none" strokeWidth="6"
                strokeLinecap="round"
                stroke={theme.hex}
                strokeDasharray={CIRCUMFERENCE}
                initial={{ strokeDashoffset: CIRCUMFERENCE }}
                animate={{ strokeDashoffset: offset }}
                transition={{ duration: 0.9, ease: 'easeOut', delay: 0.15 }}
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className={`text-lg font-extrabold tabular-nums leading-none ${theme.text}`}>
                {formatScore(composite_score)}
              </span>
              <span className="text-[8px] text-slate-400 font-medium mt-0.5">/ 100</span>
            </div>
          </motion.div>

          {/* Headline area */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className={`text-xs font-bold px-2.5 py-1 rounded-lg ${theme.bgLight} ${theme.text} border ${theme.border}`}>
                {theme.label}
              </span>
              {is_top_3 && (
                <motion.span
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ type: 'spring', stiffness: 300, damping: 15, delay: 0.3 }}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-gradient-to-r from-amber-400 via-orange-400 to-amber-500 text-white text-xs font-bold shadow-sm shadow-amber-400/25"
                >
                  <Award className="w-3 h-3" aria-hidden="true" />
                  Top Pick
                </motion.span>
              )}
            </div>

            {/* Meta pills */}
            <div className="flex items-center gap-3 mt-2">
              <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-sky-50 dark:bg-sky-950/30 border border-sky-200/60 dark:border-sky-800/40">
                <MapPin className="w-3 h-3 text-sky-500" aria-hidden="true" />
                <span className="text-xs font-bold text-sky-700 dark:text-sky-300 tabular-nums">
                  {distance_km.toFixed(1)} km
                </span>
              </div>
              <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border ${SCORE_THEME[workloadLevel].bgLight} ${SCORE_THEME[workloadLevel].border}`}>
                <Briefcase className="w-3 h-3 text-slate-500 dark:text-slate-400" aria-hidden="true" />
                <span className={`text-xs font-bold tabular-nums ${SCORE_THEME[workloadLevel].text}`}>
                  {active_jobs}/{max_capacity} jobs
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* ── Row 2: Breakdown bars ── */}
        <div className="grid grid-cols-3 gap-3">
          {breakdownItems.map(({ label, score, icon }, i) => {
            const lv = getScoreLevel(score);
            const th = SCORE_THEME[lv];
            return (
              <motion.div
                key={label}
                className="flex flex-col gap-1.5 p-2.5 rounded-xl bg-white/60 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-700/40"
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, delay: 0.2 + i * 0.08 }}
              >
                <div className="flex items-center gap-1.5">
                  <span className={`${th.text} opacity-70`} aria-hidden="true">{icon}</span>
                  <span className="text-[10px] font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide truncate">
                    {label}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <div
                    className="flex-1 h-2 rounded-full bg-slate-100 dark:bg-slate-700/60 overflow-hidden"
                    role="progressbar"
                    aria-valuenow={Math.round(score)}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-label={`${label} score`}
                  >
                    <motion.div
                      className={`h-full rounded-full bg-gradient-to-r ${th.gradientBar}`}
                      initial={{ width: 0 }}
                      animate={{ width: `${Math.min(Math.max(score, 0), 100)}%` }}
                      transition={{ duration: 0.7, ease: 'easeOut', delay: 0.25 + i * 0.08 }}
                    />
                  </div>
                  <span className={`text-xs font-bold tabular-nums min-w-[32px] text-right ${th.text}`}>
                    {formatScore(score)}
                  </span>
                </div>
              </motion.div>
            );
          })}
        </div>
      </div>
    </motion.div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════
   ScoreDisplay  (main export — full card)
   ═══════════════════════════════════════════════════════════════════════ */

export default function ScoreDisplay({
  composite_score,
  proximity_score,
  skill_score,
  workload_score,
  distance_km,
  active_jobs,
  max_capacity,
  is_top_3 = false,
  variant = 'full',
}: ScoreDisplayProps) {
  if (variant === 'compact') {
    return (
      <CompactScorePanel
        composite_score={composite_score}
        proximity_score={proximity_score}
        skill_score={skill_score}
        workload_score={workload_score}
        distance_km={distance_km}
        active_jobs={active_jobs}
        max_capacity={max_capacity}
        is_top_3={is_top_3}
      />
    );
  }

  const level = getScoreLevel(composite_score);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: [0.25, 0.46, 0.45, 0.94] }}
      className={[
        'w-full max-w-2xl rounded-2xl border p-5 sm:p-6',
        'bg-white dark:bg-slate-900',
        'border-slate-200 dark:border-slate-700/60',
        'shadow-sm shadow-slate-200/60 dark:shadow-slate-950/40',
        'transition-shadow duration-300',
        'hover:shadow-md hover:shadow-slate-200/80 dark:hover:shadow-slate-950/60',
        is_top_3 ? 'ring-2 ring-amber-400/40 dark:ring-amber-500/25' : '',
      ].join(' ')}
      role="region"
      aria-label="Technician Assignment Score"
      data-testid="score-display"
      data-score-level={level}
    >
      <div className="space-y-5">
        {/* ── Header ── */}
        <ScoreHeader is_top_3={is_top_3} />

        {/* ── Divider ── */}
        <div className="h-px bg-slate-100 dark:bg-slate-800" aria-hidden="true" />

        {/* ── Body: gauge + breakdown ── */}
        <div className="flex flex-col md:flex-row md:items-center gap-6">
          {/* Composite Score Gauge */}
          <div className="flex-shrink-0 self-center">
            <CompositeScore score={composite_score} />
          </div>

          {/* Breakdown + Meta */}
          <div className="flex-1 min-w-0 space-y-5">
            <ScoreBreakdown
              proximity_score={proximity_score}
              skill_score={skill_score}
              workload_score={workload_score}
            />

            {/* Divider */}
            <div
              className="h-px bg-slate-100 dark:bg-slate-800"
              aria-hidden="true"
            />

            <ScoreMeta
              distance_km={distance_km}
              active_jobs={active_jobs}
              max_capacity={max_capacity}
            />
          </div>
        </div>
      </div>
    </motion.div>
  );
}
