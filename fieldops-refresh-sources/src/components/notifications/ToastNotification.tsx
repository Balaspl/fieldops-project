/**
 * ToastNotification.tsx
 * Single animated toast card with:
 * - Color-coded border & icon per type
 * - Hover-to-pause auto-dismiss progress bar
 * - Manual dismiss (X button)
 * - Batch count badge
 * - Click-to-navigate callback
 * - ARIA live region support
 * - Framer Motion enter/exit animations
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  Info,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Navigation,
  X,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import type { ToastItem } from '../../types/notifications';

// ─── Config ──────────────────────────────────────────────────────────

const VARIANTS = {
  success: {
    border: 'border-l-emerald-500',
    icon: CheckCircle2,
    iconColor: 'text-emerald-500',
    bg: 'bg-emerald-50',
    title: 'text-emerald-800',
    badge: 'bg-emerald-100 text-emerald-700',
    progress: 'bg-emerald-400',
  },
  warning: {
    border: 'border-l-amber-500',
    icon: AlertTriangle,
    iconColor: 'text-amber-500',
    bg: 'bg-amber-50',
    title: 'text-amber-800',
    badge: 'bg-amber-100 text-amber-700',
    progress: 'bg-amber-400',
  },
  error: {
    border: 'border-l-red-500',
    icon: XCircle,
    iconColor: 'text-red-500',
    bg: 'bg-red-50',
    title: 'text-red-800',
    badge: 'bg-red-100 text-red-700',
    progress: 'bg-red-400',
  },
  info: {
    border: 'border-l-blue-500',
    icon: Info,
    iconColor: 'text-blue-500',
    bg: 'bg-blue-50',
    title: 'text-blue-800',
    badge: 'bg-blue-100 text-blue-700',
    progress: 'bg-blue-400',
  },
};

// Override icon for en_route
function resolveIcon(toast: ToastItem) {
  if (toast.eventType === 'job.en_route') return Navigation;
  const variant = VARIANTS[toast.type] || VARIANTS.info;
  return variant.icon;
}

// ─── Props ────────────────────────────────────────────────────────────

interface ToastNotificationProps {
  toast: ToastItem;
  onDismiss: (id: string) => void;
  onPause: (id: string) => void;
  onResume: (id: string) => void;
  onNavigate?: (jobId: string | number) => void;
}

// ─── Component ────────────────────────────────────────────────────────

export default function ToastNotification({
  toast,
  onDismiss,
  onPause,
  onResume,
  onNavigate,
}: ToastNotificationProps) {
  const v = VARIANTS[toast.type] || VARIANTS.info;
  const Icon = resolveIcon(toast);
  const isCritical = toast.priority === 'critical';

  const stylesMap = {
    success: {
      border: '#10b981',
      bg: '#ecfdf5',
      color: '#10b981',
      title: '#065f46',
      badgeBg: '#d1fae5',
      badgeColor: '#065f46',
      progress: '#34d399',
    },
    warning: {
      border: '#f59e0b',
      bg: '#fffbeb',
      color: '#f59e0b',
      title: '#92400e',
      badgeBg: '#fef3c7',
      badgeColor: '#92400e',
      progress: '#fbbf24',
    },
    error: {
      border: '#ef4444',
      bg: '#fef2f2',
      color: '#ef4444',
      title: '#991b1b',
      badgeBg: '#fee2e2',
      badgeColor: '#991b1b',
      progress: '#f87171',
    },
    info: {
      border: '#3b82f6',
      bg: '#eff6ff',
      color: '#3b82f6',
      title: '#1e3a8a',
      badgeBg: '#dbeafe',
      badgeColor: '#1e3a8a',
      progress: '#60a5fa',
    },
  }[toast.type] || {
    border: '#3b82f6',
    bg: '#eff6ff',
    color: '#3b82f6',
    title: '#1e3a8a',
    badgeBg: '#dbeafe',
    badgeColor: '#1e3a8a',
    progress: '#60a5fa',
  };

  // Progress bar — counts down from 100 to 0
  const [progress, setProgress] = useState(100);
  const [paused, setPaused] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef<number>(Date.now());
  const elapsedRef = useRef<number>(0);

  const hasBatch = (toast.batchCount ?? 1) > 1;
  const hasAutoDismiss = toast.autoDismiss > 0;

  // Progress countdown
  const startProgress = useCallback(() => {
    if (!hasAutoDismiss) return;
    if (intervalRef.current) clearInterval(intervalRef.current);
    startTimeRef.current = Date.now();

    intervalRef.current = setInterval(() => {
      const totalElapsed = elapsedRef.current + (Date.now() - startTimeRef.current);
      const pct = Math.max(0, 100 - (totalElapsed / toast.autoDismiss) * 100);
      setProgress(pct);
      if (pct <= 0) {
        clearInterval(intervalRef.current!);
      }
    }, 50);
  }, [toast.autoDismiss, hasAutoDismiss]);

  const stopProgress = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    elapsedRef.current += Date.now() - startTimeRef.current;
  }, []);

  useEffect(() => {
    startProgress();
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleMouseEnter = () => {
    setPaused(true);
    stopProgress();
    onPause(toast.id);
  };

  const handleMouseLeave = () => {
    setPaused(false);
    startProgress();
    onResume(toast.id);
  };

  const handleClick = () => {
    if (toast.jobId && onNavigate) {
      onNavigate(toast.jobId);
      onDismiss(toast.id);
    }
  };

  const styles = {
    container: {
      position: 'relative' as const,
      width: '320px',
      maxWidth: 'calc(100vw - 2rem)',
      backgroundColor: '#ffffff',
      borderRadius: '12px',
      borderLeft: `4px solid ${stylesMap.border}`,
      boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05), 0 0 0 1px rgba(0, 0, 0, 0.05)',
      overflow: 'hidden',
      cursor: toast.jobId ? 'pointer' : 'default',
      transition: 'transform 0.2s ease, box-shadow 0.2s ease',
      fontFamily: "'Inter', sans-serif",
    },
    body: {
      padding: '14px 36px 12px 16px',
    },
    flexRow: {
      display: 'flex',
      alignItems: 'flex-start',
      gap: '12px',
    },
    iconWrap: {
      marginTop: '2px',
      flexShrink: 0,
      borderRadius: '50%',
      padding: '6px',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: stylesMap.bg,
      color: stylesMap.color,
    },
    content: {
      flex: 1,
      minWidth: 0,
    },
    title: {
      fontSize: '13px',
      fontWeight: 700,
      margin: 0,
      lineHeight: '16px',
      color: stylesMap.title,
      display: 'flex',
      alignItems: 'center',
      gap: '6px',
    },
    badge: {
      display: 'inline-flex',
      height: '18px',
      minWidth: '18px',
      alignItems: 'center',
      justifyContent: 'center',
      borderRadius: '50%',
      backgroundColor: stylesMap.badgeBg,
      color: stylesMap.badgeColor,
      fontSize: '10px',
      fontWeight: 700,
      padding: '0 4px',
    },
    message: {
      fontSize: '12px',
      color: '#475569',
      margin: '4px 0 0 0',
      lineHeight: '1.4',
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      display: '-webkit-box',
      WebkitLineClamp: 2,
      WebkitBoxOrient: 'vertical' as const,
    },
    timestamp: {
      fontSize: '10px',
      color: '#94a3b8',
      margin: '6px 0 0 0',
      fontWeight: 500,
    },
    dismissBtn: {
      position: 'absolute' as const,
      top: '12px',
      right: '12px',
      borderRadius: '4px',
      padding: '4px',
      border: 'none',
      background: 'transparent',
      color: '#94a3b8',
      cursor: 'pointer',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      transition: 'background-color 0.2s, color 0.2s',
    },
    progressBg: {
      height: '3px',
      width: '100%',
      backgroundColor: '#f1f5f9',
    },
    progressBar: {
      height: '100%',
      backgroundColor: stylesMap.progress,
    },
    pausedBadge: {
      position: 'absolute' as const,
      right: '12px',
      bottom: '8px',
      backgroundColor: '#e2e8f0',
      borderRadius: '9999px',
      padding: '2px 6px',
      fontSize: '9px',
      fontWeight: 700,
      color: '#475569',
    }
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, x: 80, scale: 0.94 }}
      animate={{ opacity: 1, x: 0, scale: 1 }}
      exit={{ opacity: 0, x: 80, scale: 0.94 }}
      transition={{ type: 'spring', stiffness: 380, damping: 30 }}
      role={isCritical ? 'alert' : 'status'}
      aria-live={isCritical ? 'assertive' : 'polite'}
      aria-atomic="true"
      style={styles.container}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {/* Clickable body */}
      <div style={styles.body} onClick={handleClick}>
        <div style={styles.flexRow}>
          {/* Icon */}
          <div style={styles.iconWrap}>
            <Icon size={16} />
          </div>

          {/* Content */}
          <div style={styles.content}>
            <p style={styles.title}>
              {toast.title}
              {hasBatch && (
                <span style={styles.badge} aria-label={`${toast.batchCount} grouped notifications`}>
                  {toast.batchCount}
                </span>
              )}
            </p>

            <p style={styles.message}>{toast.message}</p>
            <p style={styles.timestamp}>{toast.timestamp}</p>
          </div>
        </div>

        {/* Batch expand */}
        {hasBatch && toast.batchItems && toast.batchItems.length > 1 && (
          <div style={{ marginTop: '8px' }}>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setExpanded((x) => !x);
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                fontSize: '11px',
                fontWeight: 600,
                border: 'none',
                background: 'transparent',
                color: stylesMap.title,
                cursor: 'pointer',
                padding: 0,
              }}
              onMouseEnter={(e) => e.currentTarget.style.textDecoration = 'underline'}
              onMouseLeave={(e) => e.currentTarget.style.textDecoration = 'none'}
            >
              {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              {expanded ? 'Hide' : `Show ${toast.batchItems.length} events`}
            </button>

            {expanded && (
              <ul style={{
                marginTop: '6px',
                padding: '8px 12px',
                borderRadius: '8px',
                backgroundColor: '#f8fafc',
                listStyleType: 'none',
                margin: '6px 0 0 0',
                display: 'flex',
                flexDirection: 'column',
                gap: '4px',
              }}>
                {toast.batchItems.map((item, i) => (
                  <li key={i} style={{ fontSize: '11px', color: '#475569', lineHeight: '1.4' }}>
                    <span style={{ fontWeight: 600, color: '#334155' }}>{item.title}</span>
                    {' — '}
                    {item.message}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      {/* Dismiss button */}
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onDismiss(toast.id);
        }}
        aria-label="Dismiss notification"
        style={styles.dismissBtn}
        onMouseEnter={(e) => {
          e.currentTarget.style.backgroundColor = '#f1f5f9';
          e.currentTarget.style.color = '#334155';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = 'transparent';
          e.currentTarget.style.color = '#94a3b8';
        }}
      >
        <X size={13} />
      </button>

      {/* Progress bar */}
      {hasAutoDismiss && (
        <div style={styles.progressBg}>
          <motion.div
            style={{
              ...styles.progressBar,
              width: `${progress}%`
            }}
            transition={{ ease: 'linear' }}
          />
        </div>
      )}

      {/* Paused indicator */}
      {paused && (
        <div style={styles.pausedBadge}>
          PAUSED
        </div>
      )}
    </motion.div>
  );
}
