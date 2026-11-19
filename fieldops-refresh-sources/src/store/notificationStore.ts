import { create } from 'zustand';

export interface GeofenceAlert {
  id: string;
  techId: string;
  techName: string;
  jobId: string;
  jobTitle: string;
  jobLocation: string;
  eventType: 'ENTRY' | 'EXIT';
  timestamp: string;
  isRead: boolean;
}

interface NotificationState {
  alerts: GeofenceAlert[];
  soundEnabled: boolean;
  autoDismiss: boolean;
  isPanelOpen: boolean;
  activeAnimations: Record<string, number>; // jobId -> timestamp of trigger
  activeToasts: GeofenceAlert[];
  addAlert: (alert: Omit<GeofenceAlert, 'id' | 'isRead'>) => void;
  markAsRead: (alertId: string) => void;
  markAllAsRead: () => void;
  clearAlerts: () => void;
  setSoundEnabled: (enabled: boolean) => void;
  setAutoDismiss: (enabled: boolean) => void;
  setPanelOpen: (open: boolean) => void;
  triggerGeofenceAnimation: (jobId: string) => void;
  dismissToast: (alertId: string) => void;
}

// Web Audio API notification chime sound helper
const playChime = () => {
  try {
    const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
    if (!AudioContextClass) return;
    
    const audioCtx = new AudioContextClass();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();

    osc.connect(gain);
    gain.connect(audioCtx.destination);

    // Subtle 0.3s arrival chime (sine wave transition D5 -> A5)
    osc.type = 'sine';
    osc.frequency.setValueAtTime(587.33, audioCtx.currentTime); // D5
    osc.frequency.setValueAtTime(880.00, audioCtx.currentTime + 0.1); // A5

    gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.3);

    osc.start(audioCtx.currentTime);
    osc.stop(audioCtx.currentTime + 0.3);
  } catch (err) {
    console.warn('Web Audio Playback failed or was blocked by browser policy:', err);
  }
};

export const useNotificationStore = create<NotificationState>((set, get) => {
  // Safe localStorage getters
  const getStoredAlerts = (): GeofenceAlert[] => {
    try {
      const data = localStorage.getItem('geofence_alerts');
      return data ? JSON.parse(data) : [];
    } catch (_) {
      return [];
    }
  };

  const getStoredPref = (key: string, defaultValue: boolean): boolean => {
    try {
      const data = localStorage.getItem(key);
      return data !== null ? data === 'true' : defaultValue;
    } catch (_) {
      return defaultValue;
    }
  };

  return {
    alerts: getStoredAlerts(),
    soundEnabled: getStoredPref('alert_sound_enabled', true),
    autoDismiss: getStoredPref('alert_auto_dismiss', true),
    isPanelOpen: false,
    activeToasts: [],
    activeAnimations: {},

    addAlert: (alertData) => {
      const newAlert: GeofenceAlert = {
        ...alertData,
        id: `alert-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        isRead: false,
      };

      // Play sound chime only on entry when sound preference is active
      if (newAlert.eventType === 'ENTRY' && get().soundEnabled) {
        playChime();
      }

      // Trigger map animation
      get().triggerGeofenceAnimation(newAlert.jobId);

      set((state) => {
        // Limit to max 100 alerts
        const updatedAlerts = [newAlert, ...state.alerts].slice(0, 100);
        try {
          localStorage.setItem('geofence_alerts', JSON.stringify(updatedAlerts));
        } catch (_) {}
        return { 
          alerts: updatedAlerts,
          activeToasts: [...state.activeToasts, newAlert]
        };
      });
    },

    markAsRead: (alertId) => {
      set((state) => {
        const updatedAlerts = state.alerts.map((a) =>
          a.id === alertId ? { ...a, isRead: true } : a
        );
        try {
          localStorage.setItem('geofence_alerts', JSON.stringify(updatedAlerts));
        } catch (_) {}
        return { alerts: updatedAlerts };
      });
    },

    markAllAsRead: () => {
      set((state) => {
        const updatedAlerts = state.alerts.map((a) => ({ ...a, isRead: true }));
        try {
          localStorage.setItem('geofence_alerts', JSON.stringify(updatedAlerts));
        } catch (_) {}
        return { alerts: updatedAlerts };
      });
    },

    clearAlerts: () => {
      set(() => {
        try {
          localStorage.setItem('geofence_alerts', JSON.stringify([]));
        } catch (_) {}
        return { alerts: [] };
      });
    },

    setSoundEnabled: (enabled) => {
      try {
        localStorage.setItem('alert_sound_enabled', String(enabled));
      } catch (_) {}
      set({ soundEnabled: enabled });
    },

    setAutoDismiss: (enabled) => {
      try {
        localStorage.setItem('alert_auto_dismiss', String(enabled));
      } catch (_) {}
      set({ autoDismiss: enabled });
    },

    setPanelOpen: (open) => {
      set({ isPanelOpen: open });
    },

    triggerGeofenceAnimation: (jobId) => {
      const key = String(jobId);
      set((state) => ({
        activeAnimations: {
          ...state.activeAnimations,
          [key]: Date.now(),
        },
      }));

      // Automatically remove from activeAnimations after 2 seconds
      setTimeout(() => {
        set((state) => {
          const updated = { ...state.activeAnimations };
          delete updated[key];
          return { activeAnimations: updated };
        });
      }, 2000);
    },

    dismissToast: (alertId) => {
      set((state) => ({
        activeToasts: state.activeToasts.filter((t) => t.id !== alertId),
      }));
    },
  };
});
