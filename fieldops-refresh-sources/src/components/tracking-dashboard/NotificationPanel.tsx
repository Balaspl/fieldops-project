import React, { useMemo } from 'react';
import { useNotificationStore, GeofenceAlert } from '../../store/notificationStore';

interface GroupedAlerts {
  jobId: string;
  jobTitle: string;
  jobLocation: string;
  alerts: GeofenceAlert[];
}

export const NotificationPanel: React.FC = () => {
  const {
    alerts,
    isPanelOpen,
    setPanelOpen,
    markAsRead,
    markAllAsRead,
    clearAlerts,
    soundEnabled,
    setSoundEnabled,
    autoDismiss,
    setAutoDismiss,
  } = useNotificationStore();

  // Group alerts by job, maintaining newest-first order
  const groupedList = useMemo(() => {
    const groups: Record<string, GroupedAlerts> = {};
    alerts.forEach((alert) => {
      if (!groups[alert.jobId]) {
        groups[alert.jobId] = {
          jobId: alert.jobId,
          jobTitle: alert.jobTitle,
          jobLocation: alert.jobLocation,
          alerts: [],
        };
      }
      groups[alert.jobId].alerts.push(alert);
    });

    return Object.values(groups).sort((a, b) => {
      const timeA = new Date(a.alerts[0].timestamp).getTime();
      const timeB = new Date(b.alerts[0].timestamp).getTime();
      return timeB - timeA;
    });
  }, [alerts]);

  const getRelativeTime = (isoString: string) => {
    const diffMs = Date.now() - new Date(isoString).getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    return new Date(isoString).toLocaleDateString();
  };

  const handleAlertClick = (alert: GeofenceAlert) => {
    markAsRead(alert.id);
  };

  return (
    <>
      {/* Backdrop overlay for drawer */}
      {isPanelOpen && (
        <div
          className="fixed inset-0 bg-slate-900/40 backdrop-blur-[2px] z-[999] transition-opacity duration-300"
          onClick={() => setPanelOpen(false)}
          data-testid="panel-backdrop"
        />
      )}

      {/* Sliding Drawer Container */}
      <div
        className={`fixed top-0 right-0 h-full bg-white shadow-2xl z-[1000] transition-transform duration-300 transform flex flex-col
                   w-full md:w-[380px] ${isPanelOpen ? 'translate-x-0' : 'translate-x-full'}`}
        data-testid="notification-panel"
      >
        {/* Header */}
        <div className="p-4 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-slate-800">Geofence Alerts</h2>
            <span className="text-[11px] text-slate-400 font-medium">Last 24 hours</span>
          </div>
          <button
            onClick={() => setPanelOpen(false)}
            className="p-1 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-50 transition-all font-bold text-lg"
            aria-label="Close panel"
          >
            ✕
          </button>
        </div>

        {/* User Preferences Controls */}
        <div className="p-3 bg-slate-50 border-b border-slate-100 grid grid-cols-2 gap-3 text-xs">
          <label className="flex items-center space-x-2 cursor-pointer font-medium text-slate-600">
            <input
              type="checkbox"
              checked={soundEnabled}
              onChange={(e) => setSoundEnabled(e.target.checked)}
              className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 w-3.5 h-3.5"
              data-testid="toggle-sound"
            />
            <span>Sound Chime</span>
          </label>
          <label className="flex items-center space-x-2 cursor-pointer font-medium text-slate-600">
            <input
              type="checkbox"
              checked={autoDismiss}
              onChange={(e) => setAutoDismiss(e.target.checked)}
              className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 w-3.5 h-3.5"
              data-testid="toggle-dismiss"
            />
            <span>Auto Dismiss</span>
          </label>
        </div>

        {/* Actions bar (only visible when alerts exist) */}
        {alerts.length > 0 && (
          <div className="p-2 px-4 bg-slate-50/50 border-b border-slate-100 flex items-center justify-between text-xs font-semibold text-indigo-600">
            <button
              onClick={markAllAsRead}
              className="hover:text-indigo-800 hover:underline transition-all"
              data-testid="mark-all-read"
            >
              Mark all as read
            </button>
            <button
              onClick={clearAlerts}
              className="text-slate-400 hover:text-slate-600 hover:underline transition-all"
              data-testid="clear-all"
            >
              Clear all
            </button>
          </div>
        )}

        {/* Alerts Scroll Area */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4" data-testid="alerts-list">
          {groupedList.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 text-slate-400 text-center space-y-2">
              <span className="text-3xl">📭</span>
              <p className="text-sm font-medium">No alerts in the last 24 hours</p>
            </div>
          ) : (
            groupedList.map((group) => (
              <div
                key={group.jobId}
                className="border border-slate-100 rounded-xl overflow-hidden shadow-sm"
                data-testid={`job-group-${group.jobId}`}
              >
                {/* Group Header */}
                <div className="p-3 bg-slate-50 border-b border-slate-100">
                  <h3 className="text-xs font-bold text-slate-700 truncate">{group.jobTitle}</h3>
                  <p className="text-[10px] text-slate-400 truncate mt-0.5">{group.jobLocation}</p>
                </div>

                {/* Group Alerts List */}
                <div className="divide-y divide-slate-50">
                  {group.alerts.map((alert) => {
                    const isEntry = alert.eventType === 'ENTRY';
                    const iconColor = isEntry ? 'text-emerald-500' : 'text-amber-500';
                    const textClass = alert.isRead ? 'text-slate-500' : 'text-slate-800 font-semibold';

                    return (
                      <div
                        key={alert.id}
                        onClick={() => handleAlertClick(alert)}
                        className={`p-3 flex items-start space-x-3 cursor-pointer hover:bg-slate-50/70 transition-all ${
                          alert.isRead ? 'opacity-70 bg-white' : 'bg-indigo-50/20'
                        }`}
                        data-testid={`alert-item-${alert.id}`}
                      >
                        {/* Event Indicator Icon */}
                        <span className={`text-base flex-shrink-0 mt-0.5 ${iconColor}`} role="img" aria-label={isEntry ? 'arrival' : 'departure'}>
                          {isEntry ? '📍' : '🚪'}
                        </span>

                        <div className="flex-1 min-w-0">
                          <p className={`text-xs ${textClass}`}>
                            {alert.techName} {isEntry ? 'arrived at site' : 'departed from site'}
                          </p>
                          <span className="text-[9px] text-slate-400 mt-1 block">
                            {getRelativeTime(alert.timestamp)}
                          </span>
                        </div>

                        {/* Read dot indicator */}
                        {!alert.isRead && (
                          <span
                            className="w-2 h-2 bg-indigo-600 rounded-full flex-shrink-0 mt-1.5"
                            data-testid="unread-dot"
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </>
  );
};

export default NotificationPanel;
