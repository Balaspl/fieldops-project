import { create } from 'zustand';

export type TechStatusFilter = 'ALL' | 'ASSIGNED' | 'EN_ROUTE' | 'ON_SITE';

interface TrackingDashboardState {
  // Filter state
  statusFilter: TechStatusFilter;
  searchQuery: string;
  jobTypeFilter: string;

  // Selection state
  selectedTechId: string | null;

  // Layer visibility
  showJobSites: boolean;
  showRoutes: boolean;

  // Actions
  setStatusFilter: (filter: TechStatusFilter) => void;
  setSearchQuery: (query: string) => void;
  setJobTypeFilter: (jobType: string) => void;
  selectTechnician: (techId: string) => void;
  clearSelection: () => void;
  toggleJobSites: () => void;
  toggleRoutes: () => void;
}

export const useTrackingDashboardStore = create<TrackingDashboardState>((set) => ({
  statusFilter: 'ALL',
  searchQuery: '',
  jobTypeFilter: 'All',

  selectedTechId: null,

  showJobSites: true,
  showRoutes: false,

  setStatusFilter: (statusFilter) => set({ statusFilter }),
  setSearchQuery: (searchQuery) => set({ searchQuery }),
  setJobTypeFilter: (jobTypeFilter) => set({ jobTypeFilter }),
  selectTechnician: (selectedTechId) => set({ selectedTechId }),
  clearSelection: () => set({ selectedTechId: null }),
  toggleJobSites: () => set((state) => ({ showJobSites: !state.showJobSites })),
  toggleRoutes: () => set((state) => ({ showRoutes: !state.showRoutes })),
}));
