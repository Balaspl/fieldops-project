
import { useState, type ReactNode } from "react";
import {
  Search,
  MapPin,
  Filter,
  RotateCcw,
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

const pillStyle = (selected: boolean) => ({
  minHeight: "37px",
  padding: "7px 17px",
  border: selected
    ? "1px solid #129957"
    : "1px solid #E0E7EC",
  borderRadius: "999px",
  background: selected
    ? "linear-gradient(180deg, #16A765 0%, #098B50 100%)"
    : "#F5F7F9",
  color: selected ? "#FFFFFF" : "#46566A",
  fontSize: "12px",
  fontWeight: selected ? 700 : 500,
  whiteSpace: "nowrap" as const,
  cursor: "pointer",
  transition: "all 0.16s ease",
  boxShadow: selected
    ? "0 2px 5px rgba(16, 153, 87, 0.16)"
    : "none",
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
    onFiltersChange?.(next);
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
    options: { label: string; value: string }[],
  ) => (
    <div style={{ minWidth: 0 }}>
      <div style={labelStyle}>{label}</div>
      <div style={groupStyle}>
        {options.map((option) => {
          const selected = filters[key] === option.value;

          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={selected}
              onClick={() => updateFilter(key, option.value)}
              style={pillStyle(selected)}
            >
              {option.label}
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
          { label: "All Services", value: "ALL" },
          { label: "HVAC Repair", value: "HVAC_REPAIR" },
          { label: "Electrical Service", value: "ELECTRICAL_SERVICE" },
          { label: "Plumbing Service", value: "PLUMBING_SERVICE" },
          { label: "Network Support", value: "NETWORK_SUPPORT" },
          { label: "General Maintenance", value: "GENERAL_MAINTENANCE" },
          { label: "Appliance Repair", value: "APPLIANCE_REPAIR" },
          { label: "Roofing & Carpentry", value: "ROOFING_CARPENTRY" },
          { label: "CCTV & Security", value: "CCTV_SECURITY" },
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
          { label: "All Statuses", value: "ALL" },
          { label: "Unassigned", value: "CREATED" },
          { label: "Assigned", value: "ASSIGNED" },
          { label: "En Route", value: "EN_ROUTE" },
          { label: "In Progress", value: "IN_PROGRESS" },
          { label: "Completed", value: "COMPLETED" },
          { label: "Cancelled", value: "CANCELLED" },
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
          { label: "All", value: "ALL" },
          { label: "Critical", value: "CRITICAL" },
          { label: "High", value: "HIGH" },
          { label: "Medium", value: "MEDIUM" },
          { label: "Low", value: "LOW" },
        ])}

        {renderPills("SLA", "sla", [
          { label: "All SLA", value: "ALL" },
          { label: "Within SLA", value: "WITHIN_SLA" },
          { label: "Approaching Breach", value: "APPROACHING_BREACH" },
          { label: "Breached", value: "BREACHED" },
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
