/**
 * dispatchMetricsService.ts
 * Service for fetching dispatch KPI metrics from the backend.
 * Primary: /planning/kpi (real all-time totals, no auth required)
 * Fallback: /dispatch/metrics (date-filtered, requires auth)
 */

import api from "./api";

export interface PlanningKpiResponse {
  jobs_dispatched: number;
  jobs_pending: number;
  jobs_expired: number;
  jobs_redispatched: number;
  trends: {
    dispatched:   { today: number; yesterday: number; change_pct: number | null };
    pending:      { today: number; yesterday: number; change_pct: number | null };
    expired:      { today: number; yesterday: number; change_pct: number | null };
    redispatched: { today: number; yesterday: number; change_pct: number | null };
  };
  sparklines: {
    dispatched:   number[];
    pending:      number[];
    expired:      number[];
    redispatched: number[];
  };
  technicians: {
    total: number;
    available: number;
    busy: number;
    offline: number;
    utilization_pct: number;
  };
}

/** Map /planning/kpi response → DispatchMetricsResponse shape expected by MetricsCards */
const mapPlanningKpi = (data: PlanningKpiResponse) => ({
  jobs_dispatched:  data.jobs_dispatched,
  jobs_pending:     data.jobs_pending,
  jobs_expired:     data.jobs_expired,
  jobs_redispatched: data.jobs_redispatched,
  trends: {
    dispatched:   { yesterday: data.trends.dispatched.yesterday,   change_pct: data.trends.dispatched.change_pct },
    pending:      { yesterday: data.trends.pending.yesterday,      change_pct: data.trends.pending.change_pct },
    expired:      { yesterday: data.trends.expired.yesterday,      change_pct: data.trends.expired.change_pct },
    redispatched: { yesterday: data.trends.redispatched.yesterday, change_pct: data.trends.redispatched.change_pct },
  },
  sparklines: data.sparklines,
  // Legacy / extra fields
  today: null,
  status_breakdown: null,
  priority_breakdown: null,
  technician_utilization: data.technicians.utilization_pct,
});

export const getDispatchMetrics = async (_timeRange: string = "today"): Promise<any> => {
  try {
    // Use the new planning KPI endpoint (no auth required, real all-time data)
    const response = await api.get("/planning/kpi");
    return mapPlanningKpi(response.data as PlanningKpiResponse);
  } catch (primaryErr) {
    // Fallback to the original dispatch/metrics endpoint
    try {
      const response = await api.get("/dispatch/metrics", {
        params: { time_range: "today" },
      });
      return response.data;
    } catch (fallbackErr) {
      console.error("Both /planning/kpi and /dispatch/metrics failed:", fallbackErr);
      throw fallbackErr;
    }
  }
};
