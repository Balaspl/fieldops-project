import React from 'react';
import { useTrackingStore } from '../../store/trackingStore';
import { RefreshCw } from 'lucide-react';

interface ConnectionStatusIndicatorProps {
  reconnect: () => void;
}

/**
 * ConnectionStatusIndicator — compact floating badge showing WebSocket health.
 * Green = Connected, Amber = Reconnecting, Red = Disconnected.
 * Includes a Refresh button for manual WebSocket reconnection.
 */
export const ConnectionStatusIndicator: React.FC<ConnectionStatusIndicatorProps> = ({ reconnect }) => {
  const { connectionStatus, reconnectAttempt } = useTrackingStore();

  const statusConfig = {
    connected: {
      dotClass: 'bg-emerald-500',
      pingClass: 'bg-emerald-400',
      label: 'Connected',
      labelClass: 'text-emerald-700',
      bgClass: 'border-emerald-100',
    },
    reconnecting: {
      dotClass: 'bg-amber-500',
      pingClass: 'bg-amber-400',
      label: `Reconnecting (${reconnectAttempt}/5)`,
      labelClass: 'text-amber-700',
      bgClass: 'border-amber-100',
    },
    disconnected: {
      dotClass: 'bg-red-500',
      pingClass: '',
      label: 'Disconnected',
      labelClass: 'text-red-700',
      bgClass: 'border-red-100',
    },
  };

  const config = statusConfig[connectionStatus];

  return (
    <div
      className={`flex items-center gap-2 bg-white/95 backdrop-blur-md shadow-lg px-3 py-2 rounded-xl border ${config.bgClass} select-none`}
      data-testid="connection-status"
      role="status"
      aria-label={`Connection status: ${config.label}`}
    >
      {/* Status dot */}
      <span className="relative flex h-2.5 w-2.5 shrink-0">
        {connectionStatus !== 'disconnected' && (
          <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${config.pingClass} opacity-75`} />
        )}
        <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${config.dotClass}`} />
      </span>

      {/* Label */}
      <span className={`text-xs font-bold ${config.labelClass}`} data-testid="connection-label">
        {config.label}
      </span>

      {/* Refresh button */}
      <button
        onClick={reconnect}
        className="ml-1 p-1 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer text-slate-500 hover:text-slate-700"
        title="Reconnect WebSocket"
        aria-label="Reconnect"
        data-testid="reconnect-button"
      >
        <RefreshCw size={13} />
      </button>
    </div>
  );
};

export default ConnectionStatusIndicator;
