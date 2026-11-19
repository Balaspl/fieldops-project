import React from 'react';
import { useMapViewport } from '../../hooks/useMapViewport';
import { useTrackingStore } from '../../store/trackingStore';
import { X, Target } from 'lucide-react';

export const FollowIndicator: React.FC = () => {
  const { followingTechId, exitFollow } = useMapViewport();
  const { technicians } = useTrackingStore();

  if (!followingTechId) return null;

  const tech = technicians[followingTechId];
  const techName = tech ? tech.name : `Technician #${followingTechId.slice(0, 4)}`;

  return (
    <div className="flex items-center gap-2 bg-emerald-500 text-white shadow-lg shadow-emerald-500/20 px-3.5 py-1.5 rounded-full text-xs font-bold border border-emerald-400 select-none animate-fade-in animate-pulse">
      <span className="relative flex h-2 w-2 shrink-0">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75"></span>
        <span className="relative inline-flex rounded-full h-2 w-2 bg-white"></span>
      </span>
      <span className="flex items-center gap-1">
        <Target size={12} className="shrink-0" />
        Following: <span className="font-extrabold">{techName}</span>
      </span>
      <button
        onClick={exitFollow}
        className="ml-1.5 p-0.5 hover:bg-emerald-600 rounded-full transition cursor-pointer"
        title="Exit Follow Mode"
        aria-label="Exit Follow Mode"
      >
        <X size={12} />
      </button>
    </div>
  );
};

export default FollowIndicator;
