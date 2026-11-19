/**
 * useToast.tsx
 * Global toast state via React Context.
 *
 * Features:
 * - Max 5 visible toasts (oldest auto-removed on overflow)
 * - 5-second batch window for identical eventTypes
 * - pauseToast / resumeToast for hover interaction
 * - Sound alerts via toastSoundService
 */

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useRef,
  useEffect,
  type ReactNode,
} from 'react';
import type { ToastItem, ToastContextValue, DispatchEventType } from '../types/notifications';
import {
  isSoundEnabled,
  setSoundEnabled as setSoundEnabledInService,
  playBeep,
  playAlarm,
} from '../services/toastSoundService';

const MAX_TOASTS = 5;
const BATCH_WINDOW_MS = 5000;

// ─── Context ──────────────────────────────────────────────────────────

const ToastContext = createContext<ToastContextValue | null>(null);

// ─── Helpers ──────────────────────────────────────────────────────────

function makeId(): string {
  return `toast-${Math.random().toString(36).slice(2, 10)}`;
}

function formatTimestamp(): string {
  return new Date().toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

function triggerSound(priority: string, eventType?: DispatchEventType): void {
  if (eventType === 'job.expired') playAlarm();
  else if (eventType === 'job.rejected' || priority === 'critical') playBeep();
}

// ─── Provider ─────────────────────────────────────────────────────────

interface ToastProviderProps {
  children: ReactNode;
}

export function ToastProvider({ children }: ToastProviderProps) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const [soundEnabled, setSoundEnabledState] = useState(isSoundEnabled);

  // Batch tracking: eventType → { toastId, items[], timer }
  const batchRef = useRef<
    Map<DispatchEventType, { id: string; items: Array<{ title: string; message: string }>; timer: ReturnType<typeof setTimeout> }>
  >(new Map());

  // Paused set: toastIds that are currently hover-paused
  const pausedRef = useRef<Set<string>>(new Set());

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    pausedRef.current.delete(id);
  }, []);

  const pauseToast = useCallback((id: string) => {
    pausedRef.current.add(id);
  }, []);

  const resumeToast = useCallback((id: string) => {
    pausedRef.current.delete(id);
  }, []);

  const setSoundEnabled = useCallback((enabled: boolean) => {
    setSoundEnabledState(enabled);
    setSoundEnabledInService(enabled);
  }, []);

  const addToast = useCallback(
    (incoming: Omit<ToastItem, 'id' | 'timestamp'> | string, maybeType?: ToastType): string => {
      let toastPayload: Omit<ToastItem, 'id' | 'timestamp'>;

      if (typeof incoming === 'string') {
        const typeStr = maybeType || 'info';
        const validTypes = ['success', 'warning', 'error', 'info'] as const;
        const normalizedType = validTypes.includes(typeStr as any) ? (typeStr as ToastType) : 'info';
        toastPayload = {
          type: normalizedType,
          title: normalizedType === 'error' ? 'Error' : normalizedType === 'success' ? 'Success' : 'Notice',
          message: incoming,
          priority: normalizedType === 'error' ? 'critical' : 'normal',
          autoDismiss: 4000,
        };
      } else if (incoming && typeof incoming === 'object') {
        toastPayload = {
          ...incoming,
          type: incoming.type || 'info',
          title: incoming.title || (incoming.type === 'error' ? 'Error' : 'Notice'),
          message: incoming.message || '',
          priority: incoming.priority || (incoming.type === 'error' ? 'critical' : 'normal'),
          autoDismiss: incoming.autoDismiss ?? 4000,
        };
      } else {
        toastPayload = {
          type: 'info',
          title: 'Notice',
          message: String(incoming || ''),
          priority: 'normal',
          autoDismiss: 4000,
        };
      }

      const { eventType } = toastPayload;

      // ── Batch check ──────────────────────────────────────────────
      if (eventType) {
        const existing = batchRef.current.get(eventType);
        if (existing) {
          const newItem = { title: toastPayload.title, message: toastPayload.message };
          existing.items.push(newItem);
          setToasts((prev) =>
            prev.map((t) =>
              t.id === existing.id
                ? {
                    ...t,
                    batchCount: existing.items.length,
                    batchItems: [...existing.items],
                    timestamp: formatTimestamp(),
                  }
                : t
            )
          );
          return existing.id;
        }
      }

      // ── New toast ────────────────────────────────────────────────
      const id = makeId();
      const timestamp = formatTimestamp();
      const toast: ToastItem = { ...toastPayload, id, timestamp };

      triggerSound(toastPayload.priority, eventType);

      setToasts((prev) => {
        const next = [toast, ...prev];
        return next.slice(0, MAX_TOASTS);
      });

      // ── Register batch window ────────────────────────────────────
      if (eventType) {
        const timer = setTimeout(() => {
          batchRef.current.delete(eventType);
        }, BATCH_WINDOW_MS);
        batchRef.current.set(eventType, {
          id,
          items: [{ title: toastPayload.title, message: toastPayload.message }],
          timer,
        });
      }

      return id;
    },
    []
  );

  // Individual auto-dismiss timers — fire per new toast at index 0
  useEffect(() => {
    if (toasts.length === 0) return;
    const newest = toasts[0];
    if (!newest || newest.autoDismiss === 0) return;

    const timerId = setTimeout(() => {
      if (!pausedRef.current.has(newest.id)) {
        dismissToast(newest.id);
      }
    }, newest.autoDismiss);

    return () => clearTimeout(timerId);
  }, [toasts[0]?.id, dismissToast]); // eslint-disable-line react-hooks/exhaustive-deps

  // Cleanup batch timers on unmount
  useEffect(() => {
    return () => {
      batchRef.current.forEach(({ timer }) => clearTimeout(timer));
    };
  }, []);

  return (
    <ToastContext.Provider
      value={{
        toasts,
        addToast,
        dismissToast,
        pauseToast,
        resumeToast,
        soundEnabled,
        setSoundEnabled,
      }}
    >
      {children}
    </ToastContext.Provider>
  );
}

// ─── Hook ─────────────────────────────────────────────────────────────

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used inside <ToastProvider>');
  }
  return ctx;
}
