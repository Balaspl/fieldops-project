import { create } from 'zustand';

export interface PublicJobDetails {
  id: string;
  customer_name: string;
  issue_description: string;
  service_type: string;
  status: string;
  site_latitude: number;
  site_longitude: number;
  site_address: string;
  scheduled_window: string;
}

export interface PublicTechnicianDetails {
  name: string;
  rating: number;
  avatar: string;
}

export interface PublicGPSPing {
  latitude: number;
  longitude: number;
  timestamp: string | null;
}

interface CustomerTrackingState {
  job: PublicJobDetails | null;
  technician: PublicTechnicianDetails | null;
  latestGps: PublicGPSPing | null;
  eta: number | null;
  expired: boolean;
  loading: boolean;
  error: string | null;
  fetchTrackingInfo: (token: string) => Promise<void>;
}

export const useCustomerTrackingStore = create<CustomerTrackingState>((set) => ({
  job: null,
  technician: null,
  latestGps: null,
  eta: null,
  expired: false,
  loading: false,
  error: null,

  fetchTrackingInfo: async (token: string) => {
    set({ loading: true, error: null });
    try {
      const response = await fetch(`http://localhost:8000/api/v1/track/${token}`);
      if (!response.ok) {
        if (response.status === 404) {
          set({ expired: true, error: 'Tracking link not found', loading: false });
          return;
        }
        throw new Error('Failed to fetch tracking details');
      }
      const data = await response.json();
      if (data.expired) {
        set({
          expired: true,
          job: data.job || null,
          error: data.message || 'Link expired',
          loading: false,
        });
      } else {
        set({
          expired: false,
          job: data.job,
          technician: data.technician,
          latestGps: data.latest_gps,
          eta: data.eta,
          loading: false,
        });
      }
    } catch (err: any) {
      set({ error: err.message || 'An error occurred', loading: false });
    }
  },
}));
