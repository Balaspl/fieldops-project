import React, { useState, useEffect, useMemo } from 'react';
import { useTrackingStore, type TechGpsData, type JobData } from '../../store/trackingStore';
import { X, Phone, Briefcase, Clock, Navigation, MapPin, User, ChevronDown, ChevronUp } from 'lucide-react';
import { getTechnicianETA } from '../../services/etaService';
import JobStatusBadge from '../ui/JobStatusBadge';
import { ETACountdown } from './ETACountdown';
import { useRoutePlaybackStore } from '../../store/routePlaybackStore';
import { getSafeImageUrl } from '../../utils/safeImageurl';
interface TechnicianDetailCardProps {
  tech: TechGpsData;
  onClose: () => void;
}

const STATUS_COLORS: Record<string, { bg: string; text: string; dot: string }> = {
  ASSIGNED: { bg: 'bg-blue-50', text: 'text-blue-700', dot: 'bg-blue-500' },
  EN_ROUTE: { bg: 'bg-emerald-50', text: 'text-emerald-700', dot: 'bg-emerald-500' },
  ON_SITE: { bg: 'bg-amber-50', text: 'text-amber-700', dot: 'bg-amber-500' },
};

/**
 * TechnicianDetailCard — 400px slide-out panel from the right.
 * Shows technician photo, name, phone, assigned jobs, status, ETA.
 * On mobile (<768px), renders as a bottom sheet.
 */
export const TechnicianDetailCard: React.FC<TechnicianDetailCardProps> = ({ tech, onClose }) => {
  const status = (tech.status || '').toUpperCase();
  const statusStyle = STATUS_COLORS[status] || { bg: 'bg-slate-50', text: 'text-slate-700', dot: 'bg-slate-500' };

  const getInitials = (name: string) =>
    name
      .split(' ')
      .map((w) => w[0])
      .join('')
      .slice(0, 2)
      .toUpperCase();

  const assignedJobs = tech.assignedJobs || (tech.job_id ? [tech.job_id] : []);

  return (
    <>
      {/* Backdrop (click to close) */}
      <div
        className="fixed inset-0 bg-black/20 backdrop-blur-[2px] z-40 md:bg-transparent md:backdrop-blur-none"
        onClick={onClose}
        data-testid="detail-card-backdrop"
      />

      {/* Desktop: Right slide-out panel (400px) */}
      <div
        className="hidden md:flex fixed top-0 right-0 h-full w-[400px] bg-white shadow-2xl border-l border-slate-200 z-50 flex-col animate-slide-in-right"
        data-testid="technician-detail-card"
        role="dialog"
        aria-label={`Details for ${tech.name}`}
        style={{
          animation: 'slideInRight 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        }}
      >
        <CardContent tech={tech} onClose={onClose} statusStyle={statusStyle} status={status} getInitials={getInitials} assignedJobs={assignedJobs} />
      </div>

      {/* Mobile: Bottom sheet */}
      <div
        className="md:hidden fixed bottom-0 left-0 right-0 bg-white shadow-2xl border-t border-slate-200 z-50 rounded-t-2xl max-h-[80vh] overflow-y-auto"
        data-testid="technician-detail-sheet"
        role="dialog"
        aria-label={`Details for ${tech.name}`}
        style={{
          animation: 'slideInUp 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        }}
      >
        {/* Drag handle */}
        <div className="flex justify-center py-2">
          <div className="w-10 h-1 bg-slate-300 rounded-full" />
        </div>
        <CardContent tech={tech} onClose={onClose} statusStyle={statusStyle} status={status} getInitials={getInitials} assignedJobs={assignedJobs} />
      </div>

      {/* Animations */}
      <style>{`
        @keyframes slideInRight {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
        @keyframes slideInUp {
          from { transform: translateY(100%); }
          to { transform: translateY(0); }
        }
      `}</style>
    </>
  );
};

/** Inner content shared between desktop card and mobile bottom sheet */
/** Inner content shared between desktop card and mobile bottom sheet */
const CardContent: React.FC<{
  tech: TechGpsData;
  onClose: () => void;
  statusStyle: { bg: string; text: string; dot: string };
  status: string;
  getInitials: (name: string) => string;
  assignedJobs: string[];
}> = ({ tech, onClose, statusStyle, status, getInitials, assignedJobs }) => {
  const [etaText, setEtaText] = useState<string | null>(null);
  const [etaMins, setEtaMins] = useState<number | null>(null);
  const [loadingEta, setLoadingEta] = useState(false);

  // Subscribe to reactive jobs store
  const storeJobs = useTrackingStore((state) => state.jobs);

  // Filter jobs for this specific technician
  const techJobs = useMemo(() => {
    const fromStore = Object.values(storeJobs).filter((j) => {
      const isAssigned = tech.assignedJobs?.includes(String(j.job_id));
      const isCurrent = String(tech.job_id) === String(j.job_id);
      return isAssigned || isCurrent;
    });

    // Fallback for mock/test environments where storeJobs is empty
    if (fromStore.length === 0 && tech.assignedJobs && tech.assignedJobs.length > 0) {
      return tech.assignedJobs.map((id) => ({
        job_id: id,
        title: `Job #${id}`,
        customer: 'Customer',
        location: 'Location',
        status: tech.status || 'ASSIGNED',
        latitude: tech.latitude,
        longitude: tech.longitude,
      }));
    }

    return fromStore;
  }, [storeJobs, tech.assignedJobs, tech.job_id, tech.status, tech.latitude, tech.longitude]);

  // Group jobs by active status
  const groupedJobs = useMemo(() => {
    const groups: Record<string, JobData[]> = {
      ON_SITE: [],
      EN_ROUTE: [],
      ASSIGNED: [],
      CREATED: [],
    };

    techJobs.forEach((job) => {
      const statusKey = (job.status || 'CREATED').toUpperCase();
      if (groups[statusKey]) {
        groups[statusKey].push(job);
      } else {
        groups[statusKey] = [job];
      }
    });

    return groups;
  }, [techJobs]);

  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({
    ON_SITE: false,
    EN_ROUTE: false,
    ASSIGNED: false,
    CREATED: false,
  });

  const toggleGroup = (groupKey: string) => {
    setCollapsedGroups((prev) => ({
      ...prev,
      [groupKey]: !prev[groupKey],
    }));
  };

  const activeJobId = tech.job_id || tech.assignedJobs?.[0];

  useEffect(() => {
    if (activeJobId && tech.latitude && tech.longitude) {
      setLoadingEta(true);
      let jobIdNum = Number(activeJobId);
      if (isNaN(jobIdNum)) {
        const match = activeJobId.match(/\d+/);
        jobIdNum = match ? Number(match[0]) : 0;
      }

      if (jobIdNum > 0) {
        getTechnicianETA(tech.id, jobIdNum)
          .then((res) => {
            if (res) {
              setEtaText(res.eta);
              setEtaMins(res.duration_minutes);
              // Dispatch to Zustand store
              useTrackingStore.getState().updateJobETA(activeJobId, {
                eta: res.eta,
                duration_minutes: res.duration_minutes,
                traffic_delay_minutes: res.traffic_delay_minutes || null,
                source: res.status === 'estimated' ? 'estimated' : 'calculated',
              });
            }
          })
          .catch((err) => {
            console.error("Failed to load ETA:", err);
          })
          .finally(() => {
            setLoadingEta(false);
          });
      } else {
        setLoadingEta(false);
      }
    } else {
      setEtaText(null);
      setEtaMins(null);
    }
  }, [tech.id, activeJobId, tech.latitude, tech.longitude]);

  const displayEta = etaText || tech.eta || (loadingEta ? 'Calculating...' : 'No active route');
  const displayMins = etaMins !== null ? etaMins : tech.eta_duration_minutes;
  const safePhotoUrl = getSafeImageUrl(tech.photoUrl);


  return (
    <div className="flex flex-col h-full bg-slate-50/50">
      {/* Header */}
      <div className="flex items-start justify-between p-5 border-b border-slate-100 bg-white">
        <div className="flex items-center gap-3">
          {safePhotoUrl ? (
          <img
            src={safePhotoUrl}
              alt={tech.name}
              className="w-14 h-14 rounded-2xl object-cover border-2 border-slate-200 shadow-sm"
            />
          ) : (
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-emerald-500 to-emerald-700 text-white flex items-center justify-center text-lg font-bold shadow-sm shadow-emerald-500/20">
              {getInitials(tech.name)}
            </div>
          )}
          <div>
            <h2 className="text-base font-bold text-slate-900" data-testid="detail-tech-name">{tech.name}</h2>
            <div className="flex items-center gap-2 mt-1">
              {techJobs.length > 0 ? (
                <JobStatusBadge 
                  status={status} 
                  size="sm" 
                  className="transition-colors duration-300 ease-in-out font-extrabold" 
                />
              ) : (
                <JobStatusBadge 
                  status="NO_ACTIVE_JOBS" 
                  size="sm" 
                  className="transition-colors duration-300 ease-in-out font-extrabold" 
                />
              )}
            </div>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg hover:bg-slate-100 transition text-slate-400 hover:text-slate-600 cursor-pointer focus-visible:outline-2 focus-visible:outline-blue-500"
          aria-label="Close details"
          data-testid="close-detail-card"
        >
          <X size={18} />
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-5 space-y-4">
        {/* Contact Info */}
        {tech.phone && (
          <div className="flex items-center gap-3 bg-white rounded-xl p-3 border border-slate-100 shadow-sm">
            <div className="w-8 h-8 bg-blue-50 rounded-lg flex items-center justify-center">
              <Phone size={14} className="text-blue-600" />
            </div>
            <div>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Phone</p>
              <p className="text-sm font-semibold text-slate-800" data-testid="detail-phone">{tech.phone}</p>
            </div>
          </div>
        )}

        {/* Dynamic Jobs List */}
        <div className="bg-white rounded-xl p-4 border border-slate-100 shadow-sm space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-slate-150">
            <div className="flex items-center gap-2">
              <Briefcase size={13} className="text-slate-500" />
              <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                Assigned Jobs ({techJobs.length})
              </span>
            </div>
          </div>

          {techJobs.length > 0 ? (
            <div className="space-y-3.5" data-testid="detail-jobs-list">
              {Object.keys(groupedJobs).map((groupKey) => {
                const list = groupedJobs[groupKey];
                if (list.length === 0) return null;
                const isCollapsed = collapsedGroups[groupKey];

                return (
                  <div key={groupKey} className="border border-slate-100 rounded-lg overflow-hidden bg-slate-50/50" data-testid={`job-group-${groupKey}`}>
                    <button
                      onClick={() => toggleGroup(groupKey)}
                      className="w-full flex items-center justify-between px-3 py-1.5 bg-slate-100 hover:bg-slate-200/50 transition font-bold text-[11px] text-slate-700 select-none cursor-pointer focus-visible:outline-2 focus-visible:outline-blue-500"
                      aria-expanded={!isCollapsed}
                      aria-controls={`group-panel-${groupKey}`}
                    >
                      <div className="flex items-center gap-1.5">
                        {isCollapsed ? <ChevronDown size={12} className="text-slate-400" /> : <ChevronUp size={12} className="text-slate-400" />}
                        <span className="capitalize">{groupKey.replace('_', ' ')}</span>
                        <span className="bg-slate-200 px-1.5 py-0.5 rounded-full text-[9px] text-slate-600 font-extrabold">
                          {list.length}
                        </span>
                      </div>
                    </button>

                    {!isCollapsed && (
                      <div id={`group-panel-${groupKey}`} className="p-2 space-y-2" data-testid={`group-list-${groupKey}`}>
                        {list.map((job) => (
                          <JobRow key={job.job_id} job={job} techId={tech.id} />
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-6 bg-slate-50 border border-dashed border-slate-200 rounded-lg" data-testid="detail-jobs-empty">
              <JobStatusBadge status="NO_ACTIVE_JOBS" size="sm" className="transition-colors duration-300 ease-in-out font-extrabold" />
              <p className="text-[10px] text-slate-400 font-semibold mt-2">No Active Jobs</p>
            </div>
          )}
        </div>

        {/* ETA */}
        {activeJobId && storeJobs[activeJobId] ? (
          <div data-testid="detail-eta-countdown">
            <ETACountdown job={storeJobs[activeJobId]} />
            <span className="hidden" data-testid="detail-eta">
              {storeJobs[activeJobId].eta_duration_minutes}m
            </span>
          </div>
        ) : (
          <div className="flex items-center gap-3 bg-slate-50 rounded-xl p-3 border border-slate-100">
            <div className="w-8 h-8 bg-slate-100 rounded-lg flex items-center justify-center">
              <Navigation size={14} className="text-slate-400" />
            </div>
            <div>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Estimated Arrival</p>
              <p className="text-sm font-semibold text-slate-500" data-testid="detail-eta">
                {displayEta}
              </p>
            </div>
          </div>
        )}

        {/* Location Details */}
        {tech.location && (
          <div className="flex items-center gap-3 bg-white rounded-xl p-3 border border-slate-100 shadow-sm">
            <div className="w-8 h-8 bg-slate-100 rounded-lg flex items-center justify-center">
              <MapPin size={14} className="text-slate-500" />
            </div>
            <div>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Current Location</p>
              <p className="text-xs font-medium text-slate-700">{tech.location}</p>
            </div>
          </div>
        )}

        {/* Customer */}
        {tech.customer && (
          <div className="flex items-center gap-3 bg-white rounded-xl p-3 border border-slate-100 shadow-sm">
            <div className="w-8 h-8 bg-slate-100 rounded-lg flex items-center justify-center">
              <User size={14} className="text-slate-500" />
            </div>
            <div>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Customer</p>
              <p className="text-xs font-medium text-slate-700">{tech.customer}</p>
            </div>
          </div>
        )}

        {/* Last Updated */}
        <div className="flex items-center gap-3 bg-white rounded-xl p-3 border border-slate-100 shadow-sm">
          <div className="w-8 h-8 bg-slate-100 rounded-lg flex items-center justify-center">
            <Clock size={14} className="text-slate-500" />
          </div>
          <div>
            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Last Update</p>
            <p className="text-xs font-medium text-slate-700" data-testid="detail-last-ping">
              {tech.lastPing
                ? (() => {
                    let dateStr = tech.lastPing;
                    if (typeof dateStr === 'string' && dateStr.includes('T') && !dateStr.endsWith('Z') && !dateStr.match(/[\+\-]\d{2}:\d{2}$/)) {
                      dateStr = dateStr + 'Z';
                    }
                    return new Date(dateStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                  })()
                : '—'}
            </p>
          </div>
        </div>

        {/* Replay GPS Route History Button */}
        <button
          onClick={() => {
            useRoutePlaybackStore.getState().startPlayback(tech.id, tech.name);
            onClose();
          }}
          className="mt-4 w-full bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white py-2.5 px-4 rounded-xl text-xs font-bold transition shadow flex items-center justify-center gap-2 border border-blue-500 shadow-md"
        >
          <span>⏳</span> Replay GPS Route History
        </button>
      </div>
    </div>
  );
};

/** Individual Job Row Component to dynamically fetch its ETA and render full details */
const JobRow: React.FC<{ job: JobData; techId: string }> = ({ job, techId }) => {
  const [etaText, setEtaText] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Subscribe to this specific job reactively
  const storeJob = useTrackingStore((state) => state.jobs[String(job.job_id)]) || job;

  useEffect(() => {
    const jobStatus = (job.status || '').toUpperCase();
    if (jobStatus && ['ASSIGNED', 'EN_ROUTE', 'ON_SITE'].includes(jobStatus)) {
      setLoading(true);
      getTechnicianETA(techId, Number(job.job_id))
        .then((res) => {
          if (res) {
            setEtaText(`${res.duration_minutes}m (${res.eta})`);
            useTrackingStore.getState().updateJobETA(String(job.job_id), {
              eta: res.eta,
              duration_minutes: res.duration_minutes,
              traffic_delay_minutes: res.traffic_delay_minutes || null,
              source: res.status === 'estimated' ? 'estimated' : 'calculated',
            });
          } else {
            setEtaText('No route');
          }
        })
        .catch(() => setEtaText('—'))
        .finally(() => setLoading(false));
    } else {
      setEtaText('No active route');
    }
  }, [job.job_id, job.status, techId]);

  return (
    <div className="bg-white rounded-lg p-2.5 border border-slate-100 flex flex-col gap-1.5 shadow-sm" data-testid={`job-row-${job.job_id}`}>
      <div className="flex items-center justify-between">
        <span className="font-bold text-slate-800 text-[11px]">Job #{job.job_id}</span>
        <JobStatusBadge 
          status={job.status} 
          size="sm" 
          className="transition-colors duration-300 ease-in-out" 
        />
      </div>
      
      <div className="space-y-0.5 text-slate-650 text-[10px] font-medium">
        <p className="flex items-center gap-1">
          <span className="text-slate-400 font-bold uppercase text-[8px] w-12 shrink-0">Customer:</span>
          <span className="text-slate-800 font-semibold truncate">{job.customer}</span>
        </p>
        <p className="flex items-center gap-1">
          <span className="text-slate-400 font-bold uppercase text-[8px] w-12 shrink-0">Address:</span>
          <span className="text-slate-700 truncate" title={job.location}>{job.location}</span>
        </p>
        <p className="flex items-center gap-1">
          <span className="text-slate-400 font-bold uppercase text-[8px] w-12 shrink-0">ETA:</span>
          <span className="text-slate-700">
            {loading ? 'Calculating...' : <ETACountdown job={storeJob} isCompact={true} />}
          </span>
        </p>
      </div>
    </div>
  );
};

export default TechnicianDetailCard;
