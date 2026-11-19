import React, { useState, useEffect, useMemo } from 'react';
import { JobData } from '../../store/trackingStore';

interface ETACountdownProps {
  job: JobData;
  isCompact?: boolean;
}

export const ETACountdown: React.FC<ETACountdownProps> = ({ job, isCompact = false }) => {
  const {
    status: jobStatus,
    eta,
    eta_duration_minutes,
    traffic_delay_minutes,
    first_eta_duration_minutes,
    eta_history = [],
    eta_source,
    sla_deadline,
  } = job;

  // Track ticking seconds left locally
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);

  // Sync with store duration minutes
  useEffect(() => {
    if (eta_duration_minutes === undefined || eta_duration_minutes === null) {
      setSecondsLeft(null);
      return;
    }
    setSecondsLeft(Math.max(0, Math.round(eta_duration_minutes * 60)));
  }, [eta_duration_minutes]);

  // Tick down every 10 seconds as required
  useEffect(() => {
    if (secondsLeft === null || secondsLeft <= 0 || jobStatus === 'ON_SITE') return;
    const interval = setInterval(() => {
      setSecondsLeft((prev) => (prev !== null && prev > 0 ? Math.max(0, prev - 10) : 0));
    }, 10000);
    return () => clearInterval(interval);
  }, [secondsLeft, jobStatus]);

  // 1. Duration Formatting
  const formattedTime = useMemo(() => {
    if (secondsLeft === null) return 'Calculating...';
    if (secondsLeft < 60) return 'Arriving now';

    const hrs = Math.floor(secondsLeft / 3600);
    const mins = Math.floor((secondsLeft % 3600) / 60);
    const remainingSecs = secondsLeft % 60;

    if (hrs > 0) {
      return `${hrs}h ${mins}m`;
    }
    if (remainingSecs > 0) {
      return `${mins}m ${remainingSecs}s`;
    }
    return `${mins}m`;
  }, [secondsLeft]);

  // 2. Color Threshold Classes
  const colorClass = useMemo(() => {
    if (secondsLeft === null) return 'text-slate-400';
    if (secondsLeft > 1800) return 'text-emerald-500'; // > 30 mins
    if (secondsLeft >= 900) return 'text-amber-500';   // 15-30 mins
    return 'text-red-500';                             // < 15 mins
  }, [secondsLeft]);

  // 3. Late Check (exceeding SLA)
  const lateInfo = useMemo(() => {
    if (!eta || !sla_deadline) return null;
    try {
      const etaTime = new Date(eta).getTime();
      const slaTime = new Date(sla_deadline).getTime();
      if (etaTime > slaTime) {
        const lateMinutes = Math.round((etaTime - slaTime) / 60000);
        return lateMinutes > 0 ? lateMinutes : null;
      }
    } catch (_) {}
    return null;
  }, [eta, sla_deadline]);

  // 4. Delayed Check (eta delta > 15 mins from original)
  const delayDelta = useMemo(() => {
    if (
      eta_duration_minutes === undefined ||
      eta_duration_minutes === null ||
      first_eta_duration_minutes === undefined ||
      first_eta_duration_minutes === null
    ) {
      return null;
    }
    const delta = eta_duration_minutes - first_eta_duration_minutes;
    return delta > 15 ? Math.round(delta) : null;
  }, [eta_duration_minutes, first_eta_duration_minutes]);

  // 5. Sparkline coordinates builder
  const sparklineSvgPath = useMemo(() => {
    if (!eta_history || eta_history.length < 2) return null;
    const width = 100;
    const height = 30;
    const minVal = Math.min(...eta_history);
    const maxVal = Math.max(...eta_history);
    const range = maxVal - minVal || 1;

    return eta_history
      .map((val, index) => {
        const x = (index / (eta_history.length - 1)) * width;
        const y = height - 5 - ((val - minVal) / range) * (height - 10);
        return `${index === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(' ');
  }, [eta_history]);

  // 6. Trend color class
  const isTrendImproving = useMemo(() => {
    if (!eta_history || eta_history.length < 2) return true;
    return eta_history[eta_history.length - 1] <= eta_history[0];
  }, [eta_history]);

  // Rendering Compact layout (e.g. Map marker or mini text)
  if (isCompact) {
    if (jobStatus === 'ON_SITE') return <span className="text-emerald-500 font-bold">Arrived</span>;
    return (
      <span className={`font-bold ${colorClass}`} aria-live="polite">
        {formattedTime}
      </span>
    );
  }

  // Renders Arrived state
  if (jobStatus === 'ON_SITE') {
    return (
      <div 
        className="flex items-center gap-2 p-3 bg-emerald-50 border border-emerald-200 rounded-xl"
        data-testid="eta-arrived-state"
        aria-live="polite"
      >
        <span className="flex items-center justify-center w-5 h-5 rounded-full bg-emerald-500 text-white text-xs font-bold">
          ✓
        </span>
        <span className="text-sm font-bold text-emerald-800">Arrived</span>
      </div>
    );
  }

  return (
    <div 
      className="flex flex-col w-full bg-white rounded-2xl border border-slate-100 p-4 shadow-sm space-y-3"
      data-testid="eta-countdown-card"
    >
      {/* Upper line: Timer & Source badge */}
      <div className="flex items-center justify-between">
        <div className="flex flex-col">
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Estimated Arrival</span>
          <span 
            className={`text-xl font-extrabold tracking-tight ${colorClass}`}
            data-testid="countdown-timer"
            aria-live="polite"
          >
            {formattedTime}
          </span>
        </div>

        {/* Source indicator */}
        <div className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-50 border border-slate-100 rounded-full select-none">
          {(!eta_source || eta_source === 'calculating') && (
            <>
              <span className="w-1.5 h-1.5 rounded-full bg-slate-400" data-testid="source-calculating-dot" />
              <span className="text-[10px] font-bold text-slate-500">Calculating...</span>
            </>
          )}
          {eta_source === 'calculated' && !job.fallback && (
            <>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" data-testid="source-live-dot" />
              <span className="text-[10px] font-bold text-slate-700">Live</span>
            </>
          )}
          {(eta_source === 'estimated' || job.fallback) && (
            <>
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" data-testid="source-fallback-dot" />
              <span className="text-[10px] font-bold text-slate-600">Estimated</span>
            </>
          )}
        </div>
      </div>

      {/* SLA & Delay Flags */}
      {(delayDelta || lateInfo) && (
        <div className="flex flex-wrap gap-2 pt-0.5">
          {delayDelta && (
            <span 
              className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold bg-red-50 text-red-600 border border-red-100"
              data-testid="delay-badge"
            >
              Delayed +{delayDelta} min
            </span>
          )}
          {lateInfo && (
            <span 
              className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-bold bg-red-50 text-red-600 border border-red-100"
              data-testid="late-badge"
            >
              Late by {lateInfo} min
            </span>
          )}
        </div>
      )}

      {/* Traffic Delay Banner */}
      {traffic_delay_minutes && traffic_delay_minutes > 10 && (
        <div 
          className="flex items-center gap-2 p-2.5 bg-amber-50/75 border border-amber-100 rounded-lg"
          data-testid="traffic-warning-banner"
        >
          <span className="text-xs">⚠️</span>
          <span className="text-xs font-semibold text-amber-800">
            Traffic delay: +{Math.round(traffic_delay_minutes)} min
          </span>
        </div>
      )}

      {/* Trend sparkline */}
      {sparklineSvgPath && (
        <div className="flex items-center justify-between pt-2 border-t border-slate-50" data-testid="eta-sparkline">
          <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">ETA Trend</span>
          <svg className="w-24 h-8 overflow-visible" viewBox="0 0 100 30">
            <path
              d={sparklineSvgPath}
              fill="none"
              stroke={isTrendImproving ? '#10B981' : '#EF4444'}
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            {/* Draw a subtle pulsing dot on the latest point */}
            {eta_history.length > 0 && (
              <circle
                cx="100"
                cy={(
                  30 - 5 -
                  ((eta_history[eta_history.length - 1] - Math.min(...eta_history)) /
                    (Math.max(...eta_history) - Math.min(...eta_history) || 1)) *
                    20
                ).toFixed(1)}
                r="3"
                fill={isTrendImproving ? '#10B981' : '#EF4444'}
                className="animate-ping"
              />
            )}
          </svg>
        </div>
      )}
    </div>
  );
};
