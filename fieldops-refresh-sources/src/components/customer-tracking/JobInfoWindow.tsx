import React from 'react';
import { InfoWindowF } from '@react-google-maps/api';
import { useTrackingStore, type TechGpsData } from '../../store/trackingStore';
import SLACountdown from './SLACountdown';
import { MapPin, Users, Compass, Circle } from 'lucide-react';

interface JobInfoWindowProps {
  job: {
    job_id: string;
    title: string;
    customer: string;
    location: string;
    status: string;
    sla_deadline: string | null;
    latitude: number;
    longitude: number;
  };
  techniciansInside: TechGpsData[];
  onClose: () => void;
}

export const JobInfoWindow: React.FC<JobInfoWindowProps> = ({
  job,
  techniciansInside,
  onClose,
}) => {
  const { geofenceRadii, setGeofenceRadius } = useTrackingStore();
  const radius = geofenceRadii[job.job_id] ?? 100; // Default 100m

  const getStatusBadgeClass = (status: string) => {
    const s = (status || '').toUpperCase();
    if (s === 'QUEUED') return 'bg-slate-100 text-slate-700 border-slate-200';
    if (s === 'ASSIGNED') return 'bg-blue-100 text-blue-700 border-blue-200';
    if (s === 'EN_ROUTE') return 'bg-green-100 text-green-700 border-green-200';
    if (s === 'ON_SITE') return 'bg-amber-100 text-amber-700 border-amber-200';
    return 'bg-slate-100 text-slate-700 border-slate-200';
  };

  return (
    <InfoWindowF
      position={{ lat: job.latitude, lng: job.longitude }}
      onCloseClick={onClose}
    >
      <div className="p-3 select-none min-w-[280px] max-w-[320px] font-sans text-slate-800">
        {/* Header */}
        <div className="pb-2.5 border-b border-slate-100">
          <div className="flex justify-between items-start gap-2">
            <h4 className="font-bold text-slate-900 text-sm leading-tight">{job.title}</h4>
            <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full border uppercase shrink-0 ${getStatusBadgeClass(job.status)}`}>
              {job.status}
            </span>
          </div>
          <p className="text-slate-500 text-xs mt-1 font-semibold">
            Customer: <span className="text-slate-900 font-bold">{job.customer}</span>
          </p>
        </div>

        {/* Info Grid */}
        <div className="py-2.5 space-y-3">
          {/* Address */}
          <div className="flex gap-2 items-start text-xs text-slate-600 font-medium">
            <MapPin size={13} className="text-slate-400 shrink-0 mt-0.5" />
            <span>{job.location}</span>
          </div>

          {/* SLA Countdown */}
          <div className="flex justify-between items-center text-xs">
            <span className="text-slate-400 font-bold uppercase text-[9px] tracking-wider">SLA Deadline</span>
            <SLACountdown deadline={job.sla_deadline} />
          </div>

          {/* Geofence Configuration Slider */}
          <div className="bg-slate-50 border border-slate-100 rounded-xl p-2.5 space-y-2">
            <div className="flex justify-between items-center text-xs font-bold text-slate-700">
              <span className="flex items-center gap-1.5 text-slate-500">
                <Circle size={12} className="text-blue-500" />
                Geofence Radius
              </span>
              <span className="text-blue-600 bg-blue-50 px-2 py-0.5 rounded-md text-[11px] font-black">
                {radius}m
              </span>
            </div>
            <input
              type="range"
              min="50"
              max="500"
              step="10"
              value={radius}
              onChange={(e) => setGeofenceRadius(job.job_id, Number(e.target.value))}
              className="w-full h-1 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-blue-600 focus:outline-none"
            />
            <div className="flex justify-between text-[10px] text-slate-400 font-medium px-0.5">
              <span>50m</span>
              <span>500m</span>
            </div>
          </div>

          {/* Live Technicians Inside list */}
          <div className="space-y-1.5">
            <p className="flex items-center gap-1.5 font-bold text-[9px] text-slate-400 uppercase tracking-wider">
              <Users size={11} className="text-slate-400" />
              Live Techs Inside ({techniciansInside.length})
            </p>
            {techniciansInside.length === 0 ? (
              <p className="text-[10px] text-slate-400 italic bg-slate-50 border border-dashed border-slate-200 rounded-lg py-2 text-center">
                No technicians in geofence
              </p>
            ) : (
              <div className="max-h-[90px] overflow-y-auto space-y-1.5 pr-0.5">
                {techniciansInside.map((tech) => (
                  <div
                    key={tech.id}
                    className="flex justify-between items-center bg-emerald-50 border border-emerald-100 rounded-lg p-1.5 text-xs text-emerald-950 font-medium"
                  >
                    <span>{tech.name}</span>
                    <span className="text-[9px] bg-emerald-100 text-emerald-800 font-bold px-1.5 py-0.5 rounded uppercase">
                      {tech.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </InfoWindowF>
  );
};

export default JobInfoWindow;
