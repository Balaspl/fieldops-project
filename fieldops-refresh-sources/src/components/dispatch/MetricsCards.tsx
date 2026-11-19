import { useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import MetricCard from "./MetricCard";
import { getDispatchMetrics } from "../../services/dispatchMetricsService";
import type {
  DispatchMetricKey,
  DispatchMetricsResponse,
  MetricCardData,
} from "../../types/dispatchMetrics";

interface MetricsCardsProps {
  onFilterChange?: (filter: string, metricKey: DispatchMetricKey) => void;
}

const mapMetricsResponse = (
  data: DispatchMetricsResponse
): MetricCardData[] => {
  return [
    {
      key: "dispatched",
      label: "Dispatched Today",
      value: data.jobs_dispatched,
      yesterday: data.trends.dispatched.yesterday,
      changePct: data.trends.dispatched.change_pct,
      sparkline: data.sparklines.dispatched,
      color: "blue",
      filter: "status=all",
    },
    {
      key: "pending",
      label: "Unassigned Jobs",
      value: data.jobs_pending,
      yesterday: data.trends.pending.yesterday,
      changePct: data.trends.pending.change_pct,
      sparkline: data.sparklines.pending,
      color: "yellow",
      filter: "status=queued,assigned",
    },
    {
      key: "expired",
      label: "Jobs Expired",
      value: data.jobs_expired,
      yesterday: data.trends.expired.yesterday,
      changePct: data.trends.expired.change_pct,
      sparkline: data.sparklines.expired,
      color: "red",
      filter: "status=expired",
    },
    {
      key: "redispatched",
      label: "Re-Dispatched",
      value: data.jobs_redispatched,
      yesterday: data.trends.redispatched.yesterday,
      changePct: data.trends.redispatched.change_pct,
      sparkline: data.sparklines.redispatched,
      color: "orange",
      filter: "redispatched=true",
    },
  ];
};

const MetricsSkeleton = () => {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-1.5 w-full">  
      {[1, 2, 3, 4].map((item) => (
        <div key={item} className="w-full">
          <div
            className="flex items-center gap-2 rounded-2xl border border-gray-100 bg-white px-2.5 py-2 shadow-sm"
          >
            <div className="h-8 w-8 flex-shrink-0 animate-pulse rounded-xl bg-gray-200" />
            <div className="flex-1 min-w-0">
              <div className="h-3 w-16 animate-pulse rounded bg-gray-200" />
              <div className="mt-0.5 flex items-center gap-0.5">
                <div className="h-2.5 w-8 animate-pulse rounded bg-gray-100" />
              </div>
            </div>
            <div className="h-6 w-px bg-gray-100" />
            <div className="h-8 w-14 flex-shrink-0 animate-pulse rounded-xl bg-gray-50" />
          </div>
        </div>
      ))}
    </div>
  );
};

const MetricsCards = ({ onFilterChange }: MetricsCardsProps) => {
  const [metrics, setMetrics] = useState<DispatchMetricsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchMetrics = async (isAutoRefresh = false) => {
    try {
      if (isAutoRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      setError(null);

      const response = await getDispatchMetrics("today");
      setMetrics(response);
    } catch (err) {
      console.error("Failed to fetch dispatch metrics:", err);
      setError("Unable to load dispatch metrics. Please try again.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();

    const fetchInitial = async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await getDispatchMetrics("today");
        if (!controller.signal.aborted) {
          setMetrics(response);
        }
      } catch (err: any) {
        if (!controller.signal.aborted) {
          console.error("Failed to fetch dispatch metrics:", err);
          setError("Unable to load dispatch metrics. Please try again.");
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    };

    fetchInitial();

    const intervalId = window.setInterval(() => {
      fetchMetrics(true);
    }, 60000);

    return () => {
      controller.abort();
      window.clearInterval(intervalId);
    };
  }, []);

  const cards = useMemo(() => {
    if (!metrics) return [];
    return mapMetricsResponse(metrics);
  }, [metrics]);

  if (loading) {
    return <MetricsSkeleton />;
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-red-100 bg-red-50 p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h3 className="text-sm font-bold text-red-700">
              Dispatch metrics failed to load
            </h3>
            <p className="mt-1 text-sm text-red-600">{error}</p>
          </div>

          <button
            type="button"
            onClick={() => fetchMetrics(false)}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-red-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-red-700"
          >
            <RefreshCw size={16} />
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <section aria-label="Dispatch metrics" className="space-y-1.5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold text-gray-700">Dispatch Metrics</h2>
        </div>

        {refreshing && (
          <div className="inline-flex items-center gap-2 rounded-full bg-blue-50 px-3 py-1 text-xs font-semibold text-blue-700">
            <RefreshCw size={13} className="animate-spin" />
            Refreshing
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-1.5 w-full">
        {cards.map((card) => (
          <div key={card.key} className="w-full">
            <MetricCard
              metricKey={card.key}
              label={card.label}
              value={card.value}
              yesterday={card.yesterday}
              changePct={card.changePct}
              sparkline={card.sparkline}
              color={card.color}
              filter={card.filter}
              onClick={onFilterChange}
            />
          </div>
        ))}
      </div>
    </section>
  );
};

export default MetricsCards;