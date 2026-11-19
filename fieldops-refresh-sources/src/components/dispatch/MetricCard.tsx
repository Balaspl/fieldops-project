import { motion } from "framer-motion";
import {
  ArrowDown,
  ArrowUp,
  Clock,
  RefreshCw,
  Send,
  XCircle,
} from "lucide-react";
import type { DispatchMetricKey } from "../../types/dispatchMetrics";
import { formatMetricNumber } from "../../utils/formatNumber";

interface MetricCardProps {
  metricKey: DispatchMetricKey;
  label: string;
  value: number;
  yesterday: number;
  changePct: number | null;
  sparkline: number[];
  color: "blue" | "yellow" | "red" | "orange";
  filter: string;
  onClick?: (filter: string, metricKey: DispatchMetricKey) => void;
}

const colorClasses = {
  blue: {
    card: "border-blue-200 hover:border-blue-400",
    iconBg: "bg-blue-50 text-blue-600 border border-blue-100/50",
    line: "#2563eb",
    number: "text-blue-700",
  },
  yellow: {
    card: "border-amber-200 hover:border-amber-400",
    iconBg: "bg-amber-50 text-amber-600 border border-amber-100/50",
    line: "#ca8a04",
    number: "text-amber-700",
  },
  red: {
    card: "border-red-200 hover:border-red-400",
    iconBg: "bg-red-50 text-red-600 border border-red-100/50",
    line: "#dc2626",
    number: "text-red-700",
  },
  orange: {
    card: "border-orange-200 hover:border-orange-400",
    iconBg: "bg-orange-50 text-orange-600 border border-orange-100/50",
    line: "#ea580c",
    number: "text-orange-700",
  },
};

const iconMap = {
  dispatched: Send,
  pending: Clock,
  expired: XCircle,
  redispatched: RefreshCw,
};

const buildSparklinePoints = (values: number[], width = 72, height = 40) => {
  if (!values || values.length === 0) return "";

  const max = Math.max(...values);
  const min = Math.min(...values);

  if (max === min) {
    return values
      .map((_, index) => {
        const x = 4 + (index / (values.length - 1 || 1)) * (width - 8);
        const y = height / 2;
        return `${x},${y}`;
      })
      .join(" ");
  }

  const range = max - min;
  return values
    .map((v, index) => {
      const x = 4 + (index / (values.length - 1 || 1)) * (width - 8);
      const y = 4 + (height - 8) - ((v - min) / range) * (height - 8);
      return `${x},${y}`;
    })
    .join(" ");
};

const MetricCard = ({
  metricKey,
  label,
  value,
  yesterday,
  changePct,
  sparkline,
  color,
  filter,
  onClick,
}: MetricCardProps) => {
  const Icon = iconMap[metricKey];
  const classes = colorClasses[color];

  const isTrendUp = changePct !== null && changePct >= 0;
  const TrendIcon = isTrendUp ? ArrowUp : ArrowDown;
  const points = buildSparklinePoints(sparkline, 72, 40);

  return (
    <motion.button
      type="button"
      onClick={() => onClick?.(filter, metricKey)}
      whileHover={{ scale: 1.01 }}
      whileTap={{ scale: 0.99 }}
      aria-label={`${label}. Current value ${value}. Click to filter dispatch queue.`}
      className={`w-full overflow-hidden flex items-center gap-2 rounded-2xl border bg-white px-2.5 py-2 text-left shadow-sm transition-all hover:shadow-md focus:outline-none focus:ring-2 focus:ring-blue-500 ${classes.card}`}
    >
      {/* Left section: Icon + Label & Trend — shrinks to fit available space */}
      <div className="flex items-center gap-2 min-w-0 flex-1">
        <div
          className={`flex h-8 w-8 flex-none items-center justify-center rounded-xl ${classes.iconBg}`}
        >
          <Icon size={14} />
        </div>

        <div className="flex flex-col min-w-0">
          <p className="text-[11.5px] font-bold text-gray-900 truncate leading-tight">{label}</p>
          <div className="mt-0.5 flex items-center gap-0.5">
            {changePct !== null ? (
              <span
                className={`inline-flex items-center gap-0.5 text-[9.5px] font-semibold whitespace-nowrap ${
                  isTrendUp ? "text-green-600" : "text-red-600"
                }`}
              >
                <TrendIcon size={10} className="flex-none stroke-[2.5]" />
                {Math.abs(changePct).toFixed(1)}%
              </span>
            ) : (
              <span className="text-[9.5px] font-semibold text-gray-500 whitespace-nowrap">No trend</span>
            )}
          </div>
        </div>
      </div>

      {/* Divider */}
      <div className="h-6 w-px bg-gray-200 flex-none" />

      {/* Right section: Number + Sparkline — fixed size, never shrinks */}
      <div className="flex items-center gap-2 flex-none">
        <h3 className={`text-lg font-bold tracking-tight leading-none ${classes.number}`}>
          {formatMetricNumber(value)}
        </h3>

        {/* Sparkline — medium compact box with rounded corners and tinted bg */}
        <div
          className={`h-8 w-14 flex-none overflow-hidden rounded-xl ${
            color === "blue" ? "bg-blue-50/60" :
            color === "yellow" ? "bg-amber-50/60" :
            color === "red" ? "bg-red-50/60" :
            "bg-orange-50/60"
          }`}
        >
          <svg
            viewBox="0 0 72 40"
            preserveAspectRatio="none"
            className="h-full w-full"
            role="img"
            aria-label={`${label} trend chart`}
          >
            <polyline
              points={points}
              fill="none"
              stroke={classes.line}
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
      </div>
    </motion.button>
  );
};

export default MetricCard;