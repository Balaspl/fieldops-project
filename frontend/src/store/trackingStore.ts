import { create } from 'zustand';

export interface TechGpsData {
  id: string; // tech_id (UUID)
  name: string;
  latitude: number;
  longitude: number;
  status: string; // ASSIGNED, EN_ROUTE, ON_SITE, etc.
  lastPing: string;
  accuracy?: number | null;
  altitude?: number | null;
  eta?: string | null;
  eta_duration_minutes?: number | null;
  job_id?: string | null;
  title?: string | null;
  customer?: string | null;
  location?: string | null; // customer address
  phone?: string | null;
  photoUrl?: string | null;
  assignedJobs?: string[]; // list of job IDs assigned to this technician
  jobType?: string | null; // e.g. 'HVAC', 'Plumbing', 'Electrical'
}

export interface JobData {
  job_id: string;
  title: string;
  customer: string;
  location: string;
  status: string;
  sla_deadline?: string | null;
  latitude: number;
  longitude: number;
  eta?: string | null;
  eta_duration_minutes?: number | null;
  traffic_delay_minutes?: number | null;
  first_eta_duration_minutes?: number | null;
  eta_history?: number[];
  eta_source?: string | null;
}

const PRIORITY_ORDER = ['ON_SITE', 'EN_ROUTE', 'ASSIGNED', 'CREATED'];

export const getTechnicianPrimaryStatus = (
  assignedJobs: string[] | undefined,
  jobsMap: Record<string, JobData>
): string => {
  if (!assignedJobs || assignedJobs.length === 0) {
    return 'NO_ACTIVE_JOBS';
  }

  const statuses = assignedJobs
    .map((id) => jobsMap[id]?.status?.toUpperCase())
    .filter((s) => s && PRIORITY_ORDER.includes(s));

  if (statuses.length === 0) {
    return 'NO_ACTIVE_JOBS';
  }

  for (const prio of PRIORITY_ORDER) {
    if (statuses.includes(prio)) {
      return prio;
    }
  }

  return 'NO_ACTIVE_JOBS';
};

interface TrackingState {
  technicians: Record<string, TechGpsData>;
  connectionStatus: 'connected' | 'reconnecting' | 'disconnected';
  reconnectAttempt: number;
  geofenceRadii: Record<string, number>; // jobId -> radius in meters
  notifiedStates: Record<string, 'inside' | 'outside'>; // jobId_techId -> state
  updateTechnicianLocation: (techId: string, data: Partial<TechGpsData>) => void;
  setConnectionStatus: (status: 'connected' | 'reconnecting' | 'disconnected') => void;
  setReconnectAttempt: (count: number) => void;
  setGeofenceRadius: (jobId: string, radius: number) => void;
  updateNotifiedState: (jobId: string, techId: string, state: 'inside' | 'outside') => void;
  clearTechnicians: () => void;
  
  // Job extensions
  jobs: Record<string, JobData>;
  setJobs: (jobs: Record<string, JobData>) => void;
  updateJobStatus: (jobId: string, status: string) => void;
  updateJobETA: (jobId: string, data: {
    eta?: string | null;
    duration_minutes?: number | null;
    traffic_delay_minutes?: number | null;
    source?: string | null;
  }) => void;
}

export const useTrackingStore = create<TrackingState>((set) => ({
  technicians: {},
  connectionStatus: 'disconnected',
  reconnectAttempt: 0,
  geofenceRadii: {},
  notifiedStates: {},
  jobs: {},

  updateTechnicianLocation: (techId: string, data: Partial<TechGpsData>) => {
    set((state) => {
      const idStr = String(techId);
      const existing = state.technicians[idStr] || {
        id: idStr,
        name: `Technician #${idStr.slice(0, 4)}`,
        status: 'Available',
      };
      
      const merged = {
        ...existing,
        ...data,
        lastPing: data.lastPing || (
          data.latitude != null && data.longitude != null
            ? new Date().toISOString()
            : existing.lastPing
        ),
      };

      // Recalculate status if assigned jobs changes or status is updated, provided jobs are loaded
      if ((data.assignedJobs || data.job_id) && Object.keys(state.jobs).length > 0) {
        const assigned = data.assignedJobs || (merged.job_id ? [merged.job_id] : []);
        merged.status = getTechnicianPrimaryStatus(assigned, state.jobs);
      }

      return {
        technicians: {
          ...state.technicians,
          [idStr]: merged,
        },
      };
    });
  },

  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),
  setReconnectAttempt: (reconnectAttempt) => set({ reconnectAttempt }),
  
  setGeofenceRadius: (jobId, radius) => set((state) => ({
    geofenceRadii: { ...state.geofenceRadii, [jobId]: radius }
  })),

  updateNotifiedState: (jobId, techId, state) => set((state) => ({
    notifiedStates: { ...state.notifiedStates, [`${jobId}_${techId}`]: state }
  })),

  clearTechnicians: () => set({ technicians: {}, notifiedStates: {} }),

  setJobs: (jobs) => set((state) => {
    if (Object.keys(jobs).length === 0) {
      return { jobs };
    }
    const updatedTechs = { ...state.technicians };
    Object.keys(updatedTechs).forEach((techId) => {
      const tech = updatedTechs[techId];
      const assigned = tech.assignedJobs || (tech.job_id ? [tech.job_id] : []);
      updatedTechs[techId] = {
        ...tech,
        status: getTechnicianPrimaryStatus(assigned, jobs),
      };
    });
    return { jobs, technicians: updatedTechs };
  }),

  updateJobStatus: (jobId, status) => set((state) => {
    const jobKey = String(jobId);
    if (!state.jobs[jobKey]) return {};

    const updatedJobs = {
      ...state.jobs,
      [jobKey]: {
        ...state.jobs[jobKey],
        status,
      },
    };

    // Recalculate primary status for affected technicians
    const updatedTechs = { ...state.technicians };
    Object.keys(updatedTechs).forEach((techId) => {
      const tech = updatedTechs[techId];
      const assigned = tech.assignedJobs || (tech.job_id ? [tech.job_id] : []);
      if (assigned.includes(jobKey)) {
        updatedTechs[techId] = {
          ...tech,
          status: getTechnicianPrimaryStatus(assigned, updatedJobs),
        };
      }
    });

    return {
      jobs: updatedJobs,
      technicians: updatedTechs,
    };
  }),

  updateJobETA: (jobId, data) => set((state) => {
    const jobKey = String(jobId);
    const existingJob = state.jobs[jobKey] || {
      job_id: jobKey,
      title: `Job #${jobKey}`,
      customer: 'Customer',
      location: 'Location',
      status: 'ASSIGNED',
      latitude: 0,
      longitude: 0,
    };

    const currentDuration = data.duration_minutes ?? existingJob.eta_duration_minutes ?? null;
    const firstDuration = existingJob.first_eta_duration_minutes ?? currentDuration;

    // Append to history and keep last 5 points
    let history = [...(existingJob.eta_history || [])];
    if (currentDuration !== null) {
      if (history.length === 0 || history[history.length - 1] !== currentDuration) {
        history.push(currentDuration);
      }
      if (history.length > 5) {
        history = history.slice(-5);
      }
    }

    const updatedJobs = {
      ...state.jobs,
      [jobKey]: {
        ...existingJob,
        eta: data.eta ?? existingJob.eta,
        eta_duration_minutes: currentDuration,
        traffic_delay_minutes: data.traffic_delay_minutes ?? existingJob.traffic_delay_minutes ?? null,
        first_eta_duration_minutes: firstDuration,
        eta_history: history,
        eta_source: data.source ?? existingJob.eta_source ?? 'calculating',
      },
    };

    return {
      jobs: updatedJobs,
    };
  }),
}));
