
import { useState, type ReactNode } from "react";
import {
  Search,
  MapPin,
  Filter,
  RotateCcw,
  Grid2X2,
  Snowflake,
  Zap,
  Droplet,
  Wifi,
  Wrench,
  Briefcase,
  Hammer,
  ShieldCheck,
  Layers,
  CircleMinus,
  UserRound,
  Navigation,
  LoaderCircle,
  CheckCircle2,
  CircleX,
  AlertCircle,
  ArrowUp,
  Equal,
  ArrowDown,
  Clock3,
  Check,
  AlertTriangle,
  type LucideIcon,
} from "lucide-react";

export interface PlanningJobFilterValues {
  search: string;
  location: string;
  priority: string;
  serviceType: string;
  status: string;
  technician: string;
  sla: string;
}

interface TechnicianOption {
  technician_id: string | number;
  technician_name: string;
}

interface PlanningJobFiltersProps {
  technicians?: TechnicianOption[];
  resultCount?: number;
  onFiltersChange?: (filters: PlanningJobFilterValues) => void;
  onRefresh?: () => void;
}

const initialFilters: PlanningJobFilterValues = {
  search: "",
  location: "",
  priority: "ALL",
  serviceType: "ALL",
  status: "ALL",
  technician: "ALL",
  sla: "ALL",
};

const inputStyle = {
  width: "100%",
  height: "39px",
  padding: "0 12px",
  border: "1px solid #DDE7E1",
  borderRadius: "9px",
  background: "#FFFFFF",
  color: "#26382E",
  fontSize: "13px",
  boxSizing: "border-box" as const,
  outlineColor: "#159957",
};

const labelStyle = {
  display: "block",
  marginBottom: "8px",
  color: "#405749",
  fontSize: "12px",
  fontWeight: 700,
  textTransform: "uppercase" as const,
  letterSpacing: "0.025em",
};

const groupStyle = {
  display: "flex",
  flexWrap: "wrap" as const,
  gap: "8px",
  alignItems: "center",
};

type FilterTone = {
  bg: string;
  text: string;
  border: string;
  active: string;
};

const filterTones: Record<string, FilterTone> = {
  green: {
    bg: "#E9F8EF",
    text: "#087B50",
    border: "#BFE8D2",
    active: "#07965B",
  },
  sky: {
    bg: "#EAF7FF",
    text: "#0369A1",
    border: "#BAE6FD",
    active: "#0284C7",
  },
  amber: {
    bg: "#FFF7E2",
    text: "#92400E",
    border: "#FDE68A",
    active: "#D97706",
  },
  blue: {
    bg: "#EDF4FF",
    text: "#1D4ED8",
    border: "#BFDBFE",
    active: "#2563EB",
  },
  purple: {
    bg: "#F4EEFF",
    text: "#6B21A8",
    border: "#DDD6FE",
    active: "#7C3AED",
  },
  indigo: {
    bg: "#EEF2FF",
    text: "#3730A3",
    border: "#C7D2FE",
    active: "#4F46E5",
  },
  pink: {
    bg: "#FFF0F7",
    text: "#BE185D",
    border: "#FBCFE8",
    active: "#DB2777",
  },
  orange: {
    bg: "#FFF3E8",
    text: "#C2410C",
    border: "#FED7AA",
    active: "#EA580C",
  },
  teal: {
    bg: "#E7F9F6",
    text: "#0F766E",
    border: "#99F6E4",
    active: "#0F766E",
  },
  slate: {
    bg: "#F1F5F9",
    text: "#475569",
    border: "#CBD5E1",
    active: "#64748B",
  },
  red: {
    bg: "#FFF0F0",
    text: "#B91C1C",
    border: "#FECACA",
    active: "#DC2626",
  },
  mint: {
    bg: "#E9FBF3",
    text: "#047857",
    border: "#A7F3D0",
    active: "#059669",
  },
};

const pillStyle = (
  selected: boolean,
  tone: FilterTone,
) => ({
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  gap: "7px",
  minHeight: "37px",
  padding: "7px 13px",
  border: `1px solid ${
    selected ? tone.active : tone.border
  }`,
  borderRadius: "999px",
  background: selected ? tone.active : tone.bg,
  color: selected ? "#FFFFFF" : tone.text,
  fontSize: "12px",
  fontWeight: 700,
  whiteSpace: "nowrap" as const,
  cursor: "pointer",
  transition: "all 0.16s ease",
  boxShadow: selected
    ? "0 3px 7px rgba(16, 153, 87, 0.16)"
    : "0 1px 3px rgba(15, 23, 42, 0.035)",
});

export default function PlanningJobFilters({
  technicians = [],
  resultCount = 0,
  onFiltersChange,
  onRefresh,
}: PlanningJobFiltersProps) {
  const [filters, setFilters] =
    useState<PlanningJobFilterValues>(initialFilters);

  const updateFilter = (
    key: keyof PlanningJobFilterValues,
    value: string,
  ) => {
    const next = { ...filters, [key]: value };
    setFilters(next);
  };

  const clearFilters = () => {
    setFilters(initialFilters);
    onFiltersChange?.({ ...initialFilters });
  };

  const field = (
    label: string,
    key: keyof PlanningJobFilterValues,
    control: ReactNode,
  ) => (
    <div style={{ minWidth: 0 }}>
      <label
        htmlFor={`planning-filter-${key}`}
        style={labelStyle}
      >
        {label}
      </label>
      {control}
    </div>
  );

    const renderPills = (
    label: string,
    key: "priority" | "serviceType" | "status" | "sla",
    options: {
      label: string;
      value: string;
      tone: FilterTone;
      icon: LucideIcon;
    }[],
  ) => (
    <div style={{ minWidth: 0 }}>
      <div style={labelStyle}>{label}</div>

      <div style={groupStyle}>
        {options.map((option) => {
          const selected = filters[key] === option.value;
          const Icon = option.icon;

          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={selected}
              onClick={() => updateFilter(key, option.value)}
              style={pillStyle(selected, option.tone)}
            >
              <Icon size={15} strokeWidth={2.4} />
              <span>{option.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );

  return (
    <section
      aria-label="Planning job filters"
      style={{
        background: "#FFFFFF",
        border: "1px solid #E0EAE4",
        borderRadius: "15px",
        padding: "15px 18px 13px",
        marginBottom: "4px",
        boxShadow: "0 3px 12px rgba(36, 73, 51, 0.045)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "12px",
          paddingBottom: "12px",
          marginBottom: "14px",
          borderBottom: "1px solid #E7EEE9",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "10px",
          }}
        >
          <div
            style={{
              width: "36px",
              height: "36px",
              borderRadius: "10px",
              background: "#E5F4EA",
              color: "#16864E",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Filter size={19} />
          </div>

          <div>
            <div
              style={{
                color: "#24382C",
                fontSize: "14px",
                fontWeight: 700,
              }}
            >
              Job Filters
            </div>
            <div
              style={{
                color: "#728176",
                fontSize: "12px",
                marginTop: "3px",
              }}
            >
              Search and narrow down jobs
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={onRefresh}
          style={{
            minHeight: "36px",
            padding: "0 15px",
            border: "1px solid #DDE8E0",
            borderRadius: "9px",
            background: "#FFFFFF",
            color: "#315840",
            fontSize: "12px",
            fontWeight: 700,
            cursor: "pointer",
            whiteSpace: "nowrap",
          }}
        >
          ↻ Refresh
        </button>
      </div>

      {/* Top row: Search, Location, Technician */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1.2fr 1fr 1.8fr",
          gap: "16px",
          marginBottom: "18px",
        }}
      >
        {field(
          "Search",
          "search",
          <div style={{ position: "relative" }}>
            <Search
              size={17}
              color="#718477"
              style={{
                position: "absolute",
                left: "12px",
                top: "11px",
              }}
            />
            <input
              id="planning-filter-search"
              aria-label="Search jobs"
              placeholder="Search name, location..."
              value={filters.search}
              onChange={(event) =>
                updateFilter("search", event.target.value)
              }
              style={{ ...inputStyle, paddingLeft: "37px" }}
            />
          </div>,
        )}

        {field(
          "Location",
          "location",
          <div style={{ position: "relative" }}>
            <MapPin
              size={17}
              color="#718477"
              style={{
                position: "absolute",
                left: "12px",
                top: "11px",
              }}
            />
            <input
              id="planning-filter-location"
              aria-label="Filter jobs by location"
              placeholder="Search location..."
              value={filters.location}
              onChange={(event) =>
                updateFilter("location", event.target.value)
              }
              style={{ ...inputStyle, paddingLeft: "37px" }}
            />
          </div>,
        )}

        {field(
          "Technician",
          "technician",
          <select
            id="planning-filter-technician"
            aria-label="Filter jobs by technician"
            value={filters.technician}
            onChange={(event) =>
              updateFilter("technician", event.target.value)
            }
            style={inputStyle}
          >
            <option value="ALL">All Technicians</option>
            {technicians.map((technician) => (
              <option
                key={technician.technician_id}
                value={String(technician.technician_id)}
              >
                {technician.technician_name}
              </option>
            ))}
          </select>,
        )}
      </div>

      {/* Service buttons */}
      <div
        style={{
          padding: "0 0 15px",
          marginBottom: "15px",
          borderBottom: "1px solid #E7EEE9",
        }}
      >
          {renderPills("Service", "serviceType", [
          {
            label: "All Services",
            value: "ALL",
            tone: filterTones.green,
            icon: Grid2X2,
          },
          {
            label: "HVAC Repair",
            value: "HVAC_REPAIR",
            tone: filterTones.sky,
            icon: Snowflake,
          },
          {
            label: "Electrical Service",
            value: "ELECTRICAL_SERVICE",
            tone: filterTones.amber,
            icon: Zap,
          },
          {
            label: "Plumbing Service",
            value: "PLUMBING_SERVICE",
            tone: filterTones.blue,
            icon: Droplet,
          },
          {
            label: "Network Support",
            value: "NETWORK_SUPPORT",
            tone: filterTones.purple,
            icon: Wifi,
          },
          {
            label: "General Maintenance",
            value: "GENERAL_MAINTENANCE",
            tone: filterTones.indigo,
            icon: Wrench,
          },
          {
            label: "Appliance Repair",
            value: "APPLIANCE_REPAIR",
            tone: filterTones.pink,
            icon: Briefcase,
          },
          {
            label: "Roofing & Carpentry",
            value: "ROOFING_CARPENTRY",
            tone: filterTones.orange,
            icon: Hammer,
          },
          {
            label: "CCTV & Security",
            value: "CCTV_SECURITY",
            tone: filterTones.teal,
            icon: ShieldCheck,
          },
        ])}
      </div>

      {/* Status buttons */}
      <div
        style={{
          paddingBottom: "15px",
          marginBottom: "15px",
          borderBottom: "1px solid #E7EEE9",
        }}
      >
                {renderPills("Status", "status", [
          {
            label: "All Statuses",
            value: "ALL",
            tone: filterTones.green,
            icon: Layers,
          },
          {
            label: "Unassigned",
            value: "UNASSIGNED",
            tone: filterTones.slate,
            icon: CircleMinus,
          },
          {
            label: "Assigned",
            value: "ASSIGNED",
            tone: filterTones.blue,
            icon: UserRound,
          },
          {
            label: "En Route",
            value: "EN_ROUTE",
            tone: filterTones.purple,
            icon: Navigation,
          },
          {
            label: "In Progress",
            value: "IN_PROGRESS",
            tone: filterTones.amber,
            icon: LoaderCircle,
          },
          {
            label: "Completed",
            value: "COMPLETED",
            tone: filterTones.mint,
            icon: CheckCircle2,
          },
          {
            label: "Cancelled",
            value: "CANCELLED",
            tone: filterTones.red,
            icon: CircleX,
          },
        ])}
      </div>

      {/* Priority and SLA: bottom row */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1.3fr",
          gap: "20px",
        }}
      >
          {renderPills("Priority", "priority", [
          {
            label: "All",
            value: "ALL",
            tone: filterTones.green,
            icon: Layers,
          },
          {
            label: "Critical",
            value: "CRITICAL",
            tone: filterTones.red,
            icon: AlertCircle,
          },
          {
            label: "High",
            value: "HIGH",
            tone: filterTones.orange,
            icon: ArrowUp,
          },
          {
            label: "Medium",
            value: "MEDIUM",
            tone: filterTones.blue,
            icon: Equal,
          },
          {
            label: "Low",
            value: "LOW",
            tone: filterTones.mint,
            icon: ArrowDown,
          },
        ])}

                {renderPills("SLA", "sla", [
          {
            label: "All SLA",
            value: "ALL",
            tone: filterTones.green,
            icon: Clock3,
          },
          {
            label: "Within SLA",
            value: "WITHIN_SLA",
            tone: filterTones.mint,
            icon: Check,
          },
          {
            label: "Approaching Breach",
            value: "APPROACHING_BREACH",
            tone: filterTones.amber,
            icon: AlertTriangle,
          },
          {
            label: "Breached",
            value: "BREACHED",
            tone: filterTones.red,
            icon: AlertCircle,
          },
        ])}
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "10px",
          marginTop: "17px",
        }}
      >
        <span
          style={{
            color: "#65766A",
            fontSize: "12px",
          }}
        >
          Showing {resultCount} job{resultCount === 1 ? "" : "s"} found
        </span>

        <div style={{ display: "flex", gap: "9px" }}>
          <button
            type="button"
            onClick={clearFilters}
            style={{
              minHeight: "39px",
              padding: "0 17px",
              border: "1px solid #DDE7E1",
              borderRadius: "9px",
              background: "#FFFFFF",
              color: "#425649",
              fontSize: "12px",
              fontWeight: 700,
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
              gap: "7px",
            }}
          >
            <RotateCcw size={14} />
            Clear
          </button>

          <button
            type="button"
            onClick={() => onFiltersChange?.({ ...filters })}
            style={{
              minHeight: "39px",
              padding: "0 19px",
              border: "1px solid #0B9252",
              borderRadius: "9px",
              background: "linear-gradient(180deg, #16A765, #098B50)",
              color: "#FFFFFF",
              fontSize: "12px",
              fontWeight: 700,
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
              boxShadow: "0 3px 7px rgba(16, 153, 87, 0.15)",
            }}
          >
            <Filter size={14} />
            Apply Filters
          </button>
        </div>
      </div>
    </section>
  );
}
