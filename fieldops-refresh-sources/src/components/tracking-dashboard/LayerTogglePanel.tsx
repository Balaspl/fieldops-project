import React from 'react';
import { useTrackingDashboardStore } from '../../store/trackingDashboardStore';
import { MapPin, Route } from 'lucide-react';

/**
 * LayerTogglePanel — floating toggle switches for Show/Hide Job Sites and Routes.
 */
export const LayerTogglePanel: React.FC = () => {
  const { showJobSites, showRoutes, toggleJobSites, toggleRoutes } = useTrackingDashboardStore();

  return (
    <div
      className="flex flex-col gap-1.5 bg-white/95 backdrop-blur-md shadow-lg rounded-xl border border-slate-200/80 p-2 select-none"
      data-testid="layer-toggle-panel"
    >
      {/* Job Sites Toggle */}
      <button
        onClick={toggleJobSites}
        className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
          showJobSites
            ? 'bg-blue-50 text-blue-700 border border-blue-200'
            : 'bg-slate-50 text-slate-500 border border-slate-100 hover:bg-slate-100'
        }`}
        aria-label={showJobSites ? 'Hide Job Sites' : 'Show Job Sites'}
        aria-pressed={showJobSites}
        data-testid="toggle-job-sites"
      >
        <MapPin size={13} />
        <span>Job Sites</span>
        <span
          className={`ml-auto w-7 h-4 rounded-full flex items-center p-0.5 transition-colors duration-200 ${
            showJobSites ? 'bg-blue-500 justify-end' : 'bg-slate-300 justify-start'
          }`}
        >
          <span className="w-3 h-3 bg-white rounded-full shadow" />
        </span>
      </button>
 
      {/* Routes Toggle */}
      <button
        onClick={toggleRoutes}
        className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
          showRoutes
            ? 'bg-purple-50 text-purple-700 border border-purple-200'
            : 'bg-slate-50 text-slate-500 border border-slate-100 hover:bg-slate-100'
        }`}
        aria-label={showRoutes ? 'Hide Routes' : 'Show Routes'}
        aria-pressed={showRoutes}
        data-testid="toggle-routes"
      >
        <Route size={13} />
        <span>Routes</span>
        <span
          className={`ml-auto w-7 h-4 rounded-full flex items-center p-0.5 transition-colors duration-200 ${
            showRoutes ? 'bg-purple-500 justify-end' : 'bg-slate-300 justify-start'
          }`}
        >
          <span className="w-3 h-3 bg-white rounded-full shadow" />
        </span>
      </button>
    </div>
  );
};

export default LayerTogglePanel;
