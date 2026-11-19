import React, { useEffect, useState } from 'react';
import { GeofenceAlert, useNotificationStore } from '../../store/notificationStore';

export const GeofenceAlertToast: React.FC<{ alert: GeofenceAlert }> = ({ alert }) => {
  const { autoDismiss, dismissToast, markAsRead } = useNotificationStore();
  const [hovered, setHovered] = useState(false);
  const [timeLeft, setTimeLeft] = useState(30);

  useEffect(() => {
    if (!autoDismiss) return;
    if (hovered) return;

    const timer = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          dismissToast(alert.id);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [autoDismiss, hovered, alert.id, dismissToast]);

  const handleClick = () => {
    markAsRead(alert.id);
    dismissToast(alert.id);
  };

  const isEntry = alert.eventType === 'ENTRY';
  const borderClass = isEntry 
    ? 'border-emerald-500 bg-emerald-50/95 text-emerald-900 shadow-emerald-100/50' 
    : 'border-amber-500 bg-amber-50/95 text-amber-900 shadow-amber-100/50';
  const icon = isEntry ? '📍' : '🚪';
  const message = isEntry
    ? `${alert.techName} arrived at ${alert.jobTitle} - ${alert.jobLocation}`
    : `${alert.techName} left ${alert.jobTitle} - ${alert.jobLocation}`;

  return (
    <div
      className={`flex items-center justify-between p-4 mb-2 rounded-xl border-2 shadow-xl max-w-sm w-full cursor-pointer transition-all duration-300 transform hover:scale-[1.02] pointer-events-auto backdrop-blur-sm ${borderClass}`}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onClick={handleClick}
      role="alert"
      aria-live="assertive"
      data-testid={`geofence-toast-${alert.id}`}
    >
      <div className="flex items-start space-x-3 pr-2">
        <span className="text-xl flex-shrink-0" role="img" aria-label={isEntry ? 'arrival' : 'departure'}>{icon}</span>
        <div className="flex flex-col">
          <p className="text-xs font-semibold leading-relaxed">{message}</p>
          {autoDismiss && (
            <span className="text-[10px] mt-1 opacity-60 font-medium">
              Auto-dismissing in {timeLeft}s {hovered && '(paused)'}
            </span>
          )}
        </div>
      </div>
      <button
        onClick={(e) => {
          e.stopPropagation();
          dismissToast(alert.id);
        }}
        className="flex-shrink-0 text-gray-400 hover:text-gray-700 focus:outline-none p-1 font-bold text-sm"
        aria-label="Close alert"
      >
        ✕
      </button>
    </div>
  );
};

export const GeofenceToastContainer: React.FC = () => {
  const activeToasts = useNotificationStore((state) => state.activeToasts);

  return (
    <div
      className="fixed z-[9999] pointer-events-none flex flex-col items-end
                 bottom-4 right-4 md:bottom-6 md:right-6
                 left-4 md:left-auto"
      data-testid="geofence-toast-container"
    >
      {activeToasts.map((toast) => (
        <GeofenceAlertToast key={toast.id} alert={toast} />
      ))}
    </div>
  );
};

export default GeofenceToastContainer;
