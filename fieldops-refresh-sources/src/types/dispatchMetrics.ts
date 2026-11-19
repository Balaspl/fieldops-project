export type DispatchMetricKey =
  | "dispatched"
  | "pending"
  | "expired"
  | "redispatched";

export interface DispatchTrend {
  yesterday: number;
  change_pct: number | null;
}

export interface DispatchMetricsResponse {
  jobs_dispatched: number;
  jobs_pending: number;
  jobs_expired: number;
  jobs_redispatched: number;

  trends: {
    dispatched: DispatchTrend;
    pending: DispatchTrend;
    expired: DispatchTrend;
    redispatched: DispatchTrend;
  };

  sparklines: {
    dispatched: number[];
    pending: number[];
    expired: number[];
    redispatched: number[];
  };
}

export interface MetricCardData {
  key: DispatchMetricKey;
  label: string;
  value: number;
  yesterday: number;
  changePct: number | null;
  sparkline: number[];
  color: "blue" | "yellow" | "red" | "orange";
  filter: string;
}