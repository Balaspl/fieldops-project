/**
 * ToastContainer.tsx
 * Portal-rendered fixed stack, top-right of the screen.
 * Renders up to MAX_TOASTS toasts with AnimatePresence.
 * Also exposes a sound toggle button.
 */

import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { Volume2, VolumeX } from 'lucide-react';
import { useToast } from '../../hooks/useToast';
import ToastNotification from './ToastNotification';

interface ToastContainerProps {
  /** Called when user clicks a toast body to navigate to a job */
  onNavigate?: (jobId: string | number) => void;
}

export default function ToastContainer({ onNavigate }: ToastContainerProps) {
  const { toasts, dismissToast, pauseToast, resumeToast, soundEnabled, setSoundEnabled } =
    useToast();

  const container = (
    <div
      aria-label="Notifications"
      role="region"
      style={{
        position: 'fixed',
        right: '20px',
        top: '20px',
        zIndex: 99999,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-end',
        gap: '12px',
        pointerEvents: 'none',
        maxWidth: '360px',
        width: 'calc(100% - 40px)',
        fontFamily: "'Inter', sans-serif"
      }}
    >
      {/* Sound toggle — always visible when there are toasts */}
      <AnimatePresence>
        {toasts.length > 0 && (
          <motion.button
            key="sound-toggle"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.8 }}
            type="button"
            onClick={() => setSoundEnabled(!soundEnabled)}
            aria-label={soundEnabled ? 'Mute toast sounds' : 'Enable toast sounds'}
            title={soundEnabled ? 'Mute sounds' : 'Enable sounds'}
            style={{
              pointerEvents: 'auto',
              display: 'flex',
              height: '32px',
              width: '32px',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: '50%',
              backgroundColor: '#ffffff',
              boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
              border: '1px solid #e2e8f0',
              color: '#64748b',
              cursor: 'pointer',
              transition: 'background-color 0.2s, color 0.2s',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = '#f8fafc';
              e.currentTarget.style.color = '#334155';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = '#ffffff';
              e.currentTarget.style.color = '#64748b';
            }}
          >
            {soundEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}
          </motion.button>
        )}
      </AnimatePresence>

      {/* Toast stack */}
      <AnimatePresence initial={false} mode="popLayout">
        {toasts.map((toast) => (
          <div key={toast.id} style={{ pointerEvents: 'auto', width: '100%' }}>
            <ToastNotification
              toast={toast}
              onDismiss={dismissToast}
              onPause={pauseToast}
              onResume={resumeToast}
              onNavigate={onNavigate}
            />
          </div>
        ))}
      </AnimatePresence>
    </div>
  );

  // Render via portal so it floats above all page content
  return createPortal(container, document.body);
}
