import React, { useState, useEffect, useMemo, useCallback, useRef } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import {
  ArrowUp,
  Copy,
  Check,
  ExternalLink,
  Search,
  Loader2,
  Inbox,
  Share2,
} from "lucide-react";

import { getDispatchQueue } from "../../services/dispatchQueueService";
import type { DispatchQueueJob } from "../../types/dispatchQueue";
import AcceptanceTimer from "./AcceptanceTimer";
import StatusBadge from "./StatusBadge";
import SLARiskBadge from "./SLARiskBadge";
import EmptyState from "../ui/EmptyState";

/* ─── Helpers ──────────────────────────────────────────────────────────────── */

const getPriorityStyle = (priority: string): React.CSSProperties => {
  const p = (priority || "").toUpperCase();
  const theme = priorityColors[p] || priorityColors.DEFAULT;
  return {
    ...tableStyles.priorityBadge,
    backgroundColor: theme.bg,
    color: theme.color,
  };
};

const truncateId = (id: string): string => {
  if (id.length <= 8) return id;
  return `${id.slice(0, 4)}…${id.slice(-4)}`;
};

const getInitials = (name: string): string => {
  return name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
};

const googleMapsUrl = (address: string): string =>
  `https://maps.google.com/?q=${encodeURIComponent(address)}`;

/* ─── Copy Button ──────────────────────────────────────────────────────────── */

const CopyJobIdButton = ({ jobId }: { jobId: string }) => {
  const [copied, setCopied] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(jobId).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1000);
    });
  };

  const btnStyle = {
    ...tableStyles.copyBtn,
    backgroundColor: isHovered ? "#DDEEE5" : "transparent",
    color: copied ? "#10B981" : (isHovered ? "#2F4F3E" : "#9CA3AF"),
  };

  return (
    <button
      style={btnStyle}
      onClick={handleCopy}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      title={copied ? "Copied!" : "Copy full Job ID"}
      aria-label={`Copy Job ID ${jobId}`}
    >
      {copied ? <Check size={12} /> : <Copy size={12} />}
    </button>
  );
};

/* ─── Share Tracking Button ─────────────────────────────────────────────────── */

const ShareTrackingLinkButton = ({ jobId }: { jobId: string }) => {
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [isHovered, setIsHovered] = useState(false);

  const handleShare = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setLoading(true);
    try {
      const response = await fetch(`http://localhost:8000/api/v1/jobs/${jobId}/share`, {
        method: "POST",
        headers: {
          "X-Tenant-ID": "tenant-1",
          "Authorization": "Bearer dev-dispatcher-token"
        }
      });
      if (!response.ok) throw new Error("Failed to generate share link");
      const data = await response.json();
      await navigator.clipboard.writeText(data.share_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error(err);
      alert("Could not generate tracking link");
    } finally {
      setLoading(false);
    }
  };

  const btnStyle = {
    ...tableStyles.copyBtn,
    backgroundColor: isHovered ? "#DDEEE5" : "transparent",
    color: copied ? "#10B981" : loading ? "#9CA3AF" : (isHovered ? "#2F4F3E" : "#7AAE8A"),
    marginLeft: "4px"
  };

  return (
    <button
      style={btnStyle}
      disabled={loading}
      onClick={handleShare}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      title={copied ? "Tracking link copied!" : "Copy customer shareable tracking link"}
      aria-label={`Share tracking link for Job ${jobId}`}
    >
      {copied ? (
        <Check size={12} />
      ) : loading ? (
        <Loader2 size={12} className="animate-spin" />
      ) : (
        <Share2 size={12} />
      )}
    </button>
  );
};

/* ─── Skeleton ─────────────────────────────────────────────────────────────── */

const SkeletonRows = () => {
  const skeletonBarBase = {
    height: "12px",
    borderRadius: "6px",
    background: "linear-gradient(90deg, #E5E7EB 25%, #F3F4F6 50%, #E5E7EB 75%)",
    backgroundSize: "200% 100%",
    animation: "shimmer 1.5s ease-in-out infinite",
  };
  return (
    <>
      {Array.from({ length: 6 }).map((_, i) => (
        <tr key={i}>
          <td style={{ ...tableStyles.td, padding: "12px" }}>
            <div style={{ ...skeletonBarBase, width: "60px" }} />
          </td>
          <td style={{ ...tableStyles.td, padding: "12px" }}>
            <div style={{ ...skeletonBarBase, width: "100px" }} />
          </td>
          <td style={{ ...tableStyles.td, padding: "12px" }}>
            <div style={{ ...skeletonBarBase, width: "140px" }} />
          </td>
          <td style={{ ...tableStyles.td, padding: "12px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div style={{
                width: "28px",
                height: "28px",
                borderRadius: "50%",
                background: "linear-gradient(90deg, #E5E7EB 25%, #F3F4F6 50%, #E5E7EB 75%)",
                backgroundSize: "200% 100%",
                animation: "shimmer 1.5s ease-in-out infinite",
                flexShrink: 0
              }} />
              <div style={{ ...skeletonBarBase, width: "60px" }} />
            </div>
          </td>
          <td style={{ ...tableStyles.td, padding: "12px" }}>
            <div style={{ ...skeletonBarBase, width: "50px" }} />
          </td>
          <td style={{ ...tableStyles.td, padding: "12px" }}>
            <div style={{ ...skeletonBarBase, width: "50px" }} />
          </td>
          <td style={{ ...tableStyles.td, padding: "12px" }}>
            <div style={{ ...skeletonBarBase, width: "50px" }} />
          </td>
          <td style={{ ...tableStyles.td, padding: "12px" }}>
            <div style={{ ...skeletonBarBase, width: "50px" }} />
          </td>
        </tr>
      ))}
    </>
  );
};

/* ─── Main Component ───────────────────────────────────────────────────────── */

interface DispatchQueueTableProps {
  /** Callback when a job count changes (for tab badge) */
  onCountChange?: (count: number) => void;
}

const DispatchQueueTable = ({ onCountChange }: DispatchQueueTableProps) => {
  // Data
  const [jobs, setJobs] = useState<DispatchQueueJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("");
  const [searchText, setSearchText] = useState("");

  // Table
  const [sorting, setSorting] = useState<SortingState>([]);

  // Auto-refresh interval
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Hover states
  const [hoveredHeader, setHoveredHeader] = useState<string | null>(null);
  const [hoveredRow, setHoveredRow] = useState<string | null>(null);
  const [hoveredMaps, setHoveredMaps] = useState<string | null>(null);
  const [focusedFilter, setFocusedFilter] = useState<string | null>(null);
  const [windowWidth, setWindowWidth] = useState(window.innerWidth);

  useEffect(() => {
    const handleResize = () => setWindowWidth(window.innerWidth);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // ── Fetch ─────────────────────────────────────────────────────────────────

  const fetchQueue = useCallback(
    async (isRefresh = false) => {
      try {
        if (isRefresh) {
          setRefreshing(true);
        } else {
          setLoading(true);
        }
        setError(null);

        const response = await getDispatchQueue({
          ...(statusFilter && { status: statusFilter }),
          ...(priorityFilter && { priority: priorityFilter }),
          limit: 50,
        });

        setJobs(response.data);
        onCountChange?.(response.data.length);
      } catch (err) {
        console.error("Dispatch queue fetch error:", err);
        setError("Failed to load dispatch queue. Please try again.");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [statusFilter, priorityFilter, onCountChange]
  );

  // Initial fetch + filter changes
  useEffect(() => {
    fetchQueue(false);
  }, [fetchQueue]);

  // Auto-refresh every 30s
  useEffect(() => {
    intervalRef.current = setInterval(() => {
      fetchQueue(true);
    }, 30000);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchQueue]);

  // ── Filtered data (client-side text search) ───────────────────────────────

  const filteredJobs = useMemo(() => {
    if (!searchText.trim()) return jobs;
    const q = searchText.toLowerCase().trim();
    return jobs.filter(
      (job) =>
        job.job_id.toLowerCase().includes(q) ||
        job.customer.toLowerCase().includes(q) ||
        job.location.toLowerCase().includes(q) ||
        job.title.toLowerCase().includes(q) ||
        (job.technician?.name || "").toLowerCase().includes(q)
    );
  }, [jobs, searchText]);

  // ── Column Definitions ────────────────────────────────────────────────────

  const columns = useMemo<ColumnDef<DispatchQueueJob>[]>(
    () => [
      {
        accessorKey: "job_id",
        header: "Job ID",
        size: 120,
        cell: ({ row }) => (
          <div style={tableStyles.jobIdCell}>
            <span style={tableStyles.jobIdText} title={row.original.job_id}>
              {truncateId(row.original.job_id)}
            </span>
            <CopyJobIdButton jobId={row.original.job_id} />
            <ShareTrackingLinkButton jobId={row.original.job_id} />
          </div>
        ),
      },
      {
        accessorKey: "customer",
        header: "Customer",
        size: 170,
        cell: ({ row }) => (
          <div>
            <div style={tableStyles.customerName}>{row.original.customer}</div>
            {row.original.title && (
              <div style={tableStyles.customerTitle}>{row.original.title}</div>
            )}
          </div>
        ),
      },
      {
        accessorKey: "location",
        header: "Location",
        size: 200,
        cell: ({ row }) => {
          const isMapHovered = hoveredMaps === row.original.job_id;
          return (
            <div style={tableStyles.locationCell}>
              <span style={tableStyles.locationText}>{row.original.location}</span>
              <a
                href={googleMapsUrl(row.original.location)}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  ...tableStyles.mapLink,
                  backgroundColor: isMapHovered ? "#EEF4F1" : "transparent",
                  color: isMapHovered ? "#5C9470" : "#9CA3AF",
                }}
                title="Open in Maps"
                onClick={(e) => e.stopPropagation()}
                onMouseEnter={() => setHoveredMaps(row.original.job_id)}
                onMouseLeave={() => setHoveredMaps(null)}
              >
                <ExternalLink size={12} />
              </a>
            </div>
          );
        },
      },
      {
        id: "technician",
        header: "Technician",
        size: 160,
        accessorFn: (row) => row.technician?.name || "",
        cell: ({ row }) => {
          const tech = row.original.technician;
          if (!tech) {
            return <span style={tableStyles.unassigned}>Unassigned</span>;
          }
          const statusClass = (tech.status || "").toLowerCase();
          const avatarBg = avatarColors[statusClass] || avatarColors.unassigned;
          return (
            <div style={tableStyles.techCell}>
              <div style={{ ...tableStyles.techAvatar, backgroundColor: avatarBg }}>
                {getInitials(tech.name)}
              </div>
              <div style={tableStyles.techInfo}>
                <span style={tableStyles.techName}>{tech.name}</span>
                <span style={tableStyles.techStatusText}>{tech.status}</span>
              </div>
            </div>
          );
        },
      },
      {
        accessorKey: "status",
        header: "Status",
        size: 110,
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
      },
      {
        accessorKey: "priority",
        header: "Priority",
        size: 90,
        cell: ({ row }) => (
          <span style={getPriorityStyle(row.original.priority)}>
            {row.original.priority || "—"}
          </span>
        ),
      },
      {
        id: "sla",
        header: "SLA Risk",
        size: 130,
        accessorFn: (row) => row.sla.minutes_remaining ?? 999999,
        cell: ({ row }) => {
          const deadline = row.original.sla.deadline;
          if (!deadline) return <span style={tableStyles.unassigned}>—</span>;
          return (
            <SLARiskBadge
              slaDeadline={deadline}
              showMinutes={true}
              enablePulse={true}
            />
          );
        },
      },
      {
        id: "timer",
        header: "Timer",
        size: 120,
        accessorFn: (row) => {
          if (row.status !== "ASSIGNED") return 999999;
          if (row.acceptance_expires_at) {
            return Math.max(
              0,
              (new Date(row.acceptance_expires_at).getTime() - Date.now()) /
                1000
            );
          }
          if (row.assigned_at) {
            const expires =
              new Date(row.assigned_at).getTime() + 10 * 60 * 1000;
            return Math.max(0, (expires - Date.now()) / 1000);
          }
          return 999999;
        },
        cell: ({ row }) => (
          <AcceptanceTimer
            assignedAt={row.original.assigned_at}
            expiresAt={row.original.acceptance_expires_at}
            status={row.original.status}
          />
        ),
      },
    ],
    [hoveredMaps]
  );

  // ── Table Instance ────────────────────────────────────────────────────────

  const table = useReactTable({
    data: filteredJobs,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  // ── Render ────────────────────────────────────────────────────────────────

  const filterBarResponsive: React.CSSProperties = {
    ...tableStyles.filterBar,
    ...(windowWidth <= 768 ? { flexDirection: "column", gap: "8px" } : {}),
  };

  const filterSelectStyle = (id: string): React.CSSProperties => ({
    ...tableStyles.filterSelect,
    ...(windowWidth <= 768 ? { width: "100%", minWidth: "unset" } : {}),
    borderColor: focusedFilter === id ? "#7AAE8A" : "#E3ECE7",
    boxShadow: focusedFilter === id ? "0 0 0 2px rgba(122, 174, 138, 0.12)" : undefined,
  });

  const searchInputStyle: React.CSSProperties = {
    ...tableStyles.filterSearch,
    ...(windowWidth <= 768 ? { width: "100%" } : {}),
    borderColor: focusedFilter === "search" ? "#7AAE8A" : "#E3ECE7",
    boxShadow: focusedFilter === "search" ? "0 0 0 2px rgba(122, 174, 138, 0.12)" : undefined,
  };

  const searchWrapStyle: React.CSSProperties = {
    ...tableStyles.filterSearchWrap,
    ...(windowWidth <= 768 ? { width: "100%", minWidth: "unset" } : {}),
  };

  const filterCountResponsive: React.CSSProperties = {
    ...tableStyles.filterCount,
    ...(windowWidth <= 768 ? { marginLeft: "0", textAlign: "center" } : {}),
  };

  return (
    <section style={tableStyles.section} aria-label="Dispatch Queue">
      <style>
        {`
          @keyframes shimmer {
            0% { background-position: 200% 0; }
            100% { background-position: -200% 0; }
          }
          @keyframes toastSlideUp {
            from { opacity: 0; transform: translateX(-50%) translateY(12px); }
            to   { opacity: 1; transform: translateX(-50%) translateY(0); }
          }
          .animate-spin {
            animation: spin-anim 1s linear infinite;
          }
          @keyframes spin-anim {
            to { transform: rotate(360deg); }
          }
        `}
      </style>

      {/* Filter Bar */}
      <div style={filterBarResponsive}>
        <select
          style={filterSelectStyle("status")}
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          onFocus={() => setFocusedFilter("status")}
          onBlur={() => setFocusedFilter(null)}
          aria-label="Filter by status"
          id="dq-status-filter"
        >
          <option value="">All Statuses</option>
          <option value="QUEUED">Queued</option>
          <option value="ASSIGNED">Assigned</option>
          <option value="EN_ROUTE">En Route</option>
          <option value="ON_SITE">On Site</option>
        </select>

        <select
          style={filterSelectStyle("priority")}
          value={priorityFilter}
          onChange={(e) => setPriorityFilter(e.target.value)}
          onFocus={() => setFocusedFilter("priority")}
          onBlur={() => setFocusedFilter(null)}
          aria-label="Filter by priority"
          id="dq-priority-filter"
        >
          <option value="">All Priorities</option>
          <option value="CRITICAL">Critical</option>
          <option value="HIGH">High</option>
          <option value="MEDIUM">Medium</option>
          <option value="LOW">Low</option>
        </select>

        <div style={searchWrapStyle}>
          <Search size={13} style={tableStyles.filterSearchIcon} />
          <input
            type="text"
            style={searchInputStyle}
            placeholder="Search jobs, customers, techs..."
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onFocus={() => setFocusedFilter("search")}
            onBlur={() => setFocusedFilter(null)}
            aria-label="Search dispatch queue"
            id="dq-search-input"
          />
        </div>

        <span style={filterCountResponsive}>
          <strong>{filteredJobs.length}</strong> of {jobs.length} jobs
          {refreshing && (
            <span style={tableStyles.refreshIndicator}>
              <Loader2 size={11} className="animate-spin" />
              Refreshing
            </span>
          )}
        </span>
      </div>

      {/* Table Content */}
      <div style={{ padding: "0 0 16px" }}>
        {error ? (
          <EmptyState
            icon={Inbox}
            title="Could not load queue"
            description={error}
            action={
              <button
                style={{
                  background: "#FFFFFF",
                  border: "1px solid #E3ECE7",
                  padding: "6px 12px",
                  borderRadius: "6px",
                  fontSize: "12px",
                  fontWeight: 600,
                  cursor: "pointer",
                  color: "#2F4F3E",
                }}
                onClick={() => fetchQueue(false)}
              >
                ⟳ Retry
              </button>
            }
          />
        ) : (
          <div style={tableStyles.tableWrap}>
            <table style={tableStyles.table} role="table">
              <thead>
                {table.getHeaderGroups().map((headerGroup) => (
                  <tr key={headerGroup.id}>
                    {headerGroup.headers.map((header) => {
                      const isSorted = header.column.getIsSorted();
                      const isHeaderHovered = hoveredHeader === header.id;
                      return (
                        <th
                          key={header.id}
                          onClick={header.column.getToggleSortingHandler()}
                          onMouseEnter={() => setHoveredHeader(header.id)}
                          onMouseLeave={() => setHoveredHeader(null)}
                          style={{
                            ...tableStyles.th,
                            width: header.getSize(),
                            backgroundColor: isHeaderHovered ? "#EEF4F1" : "#F6FAF8",
                          }}
                          aria-sort={
                            isSorted === "asc"
                              ? "ascending"
                              : isSorted === "desc"
                                ? "descending"
                                : "none"
                          }
                        >
                          <span style={tableStyles.thInner}>
                            {flexRender(
                              header.column.columnDef.header,
                              header.getContext()
                            )}
                            <ArrowUp
                              size={11}
                              style={{
                                ...tableStyles.sortIcon,
                                color: isSorted ? "#2F4F3E" : "#9CA3AF",
                                transform: isSorted === "desc" ? "rotate(180deg)" : "none",
                              }}
                            />
                          </span>
                        </th>
                      );
                    })}
                  </tr>
                ))}
              </thead>
              <tbody>
                {loading ? (
                  <SkeletonRows />
                ) : table.getRowModel().rows.length === 0 ? (
                  <tr>
                    <td colSpan={columns.length}>
                      <EmptyState
                        icon={Inbox}
                        title={
                          searchText.trim()
                             ? "No jobs match your search"
                             : "No jobs in dispatch queue"
                        }
                        description={
                          searchText.trim()
                            ? "Try adjusting your filters or search terms."
                            : "All jobs have been dispatched or completed."
                        }
                      />
                    </td>
                  </tr>
                ) : (
                  table.getRowModel().rows.map((row) => {
                    const isRowHovered = hoveredRow === row.id;
                    return (
                      <tr
                        key={row.id}
                        title="Click to view job details"
                        style={{ cursor: "pointer" }}
                        onMouseEnter={() => setHoveredRow(row.id)}
                        onMouseLeave={() => setHoveredRow(null)}
                      >
                        {row.getVisibleCells().map((cell) => (
                          <td
                            key={cell.id}
                            style={{
                              ...tableStyles.td,
                              backgroundColor: isRowHovered ? "#F4FAF6" : "transparent",
                            }}
                          >
                            {flexRender(
                              cell.column.columnDef.cell,
                              cell.getContext()
                            )}
                          </td>
                        ))}
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
};

/* ─── Styles & Design Tokens ────────────────────────────────────────── */

const tableStyles = {
  section: {
    fontFamily: "'Inter', sans-serif",
  } as React.CSSProperties,
  
  filterBar: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    padding: "12px 16px",
    background: "#F8FBF9",
    borderBottom: "1px solid #E3ECE7",
    flexWrap: "wrap",
  } as React.CSSProperties,

  filterSelect: {
    padding: "6px 10px",
    borderRadius: "8px",
    border: "1.5px solid #E3ECE7",
    fontSize: "12px",
    fontWeight: 600,
    color: "#1F2933",
    background: "#FFFFFF",
    outline: "none",
    minWidth: "130px",
    fontFamily: "'Inter', sans-serif",
    cursor: "pointer",
    transition: "border-color 0.2s, box-shadow 0.2s",
  } as React.CSSProperties,
  
  filterSearchWrap: {
    position: "relative",
    flex: 1,
    minWidth: "180px",
  } as React.CSSProperties,

  filterSearchIcon: {
    position: "absolute",
    left: "10px",
    top: "50%",
    transform: "translateY(-50%)",
    color: "#9CA3AF",
    pointerEvents: "none",
  } as React.CSSProperties,

  filterSearch: {
    width: "100%",
    padding: "6px 10px 6px 32px",
    borderRadius: "8px",
    border: "1.5px solid #E3ECE7",
    fontSize: "12px",
    color: "#1F2933",
    background: "#FFFFFF",
    outline: "none",
    transition: "border-color 0.2s, box-shadow 0.2s",
    fontFamily: "'Inter', sans-serif",
    boxSizing: "border-box",
  } as React.CSSProperties,

  filterCount: {
    fontSize: "11px",
    fontWeight: 600,
    color: "#6B7280",
    whiteSpace: "nowrap",
    marginLeft: "auto",
    display: "flex",
    alignItems: "center",
    gap: "6px",
  } as React.CSSProperties,

  refreshIndicator: {
    display: "inline-flex",
    alignItems: "center",
    gap: "5px",
    fontSize: "10px",
    fontWeight: 600,
    color: "#7AAE8A",
    padding: "3px 8px",
    background: "#EAF4EE",
    borderRadius: "12px",
    marginLeft: "8px",
  } as React.CSSProperties,

  tableWrap: {
    overflowX: "auto",
  } as React.CSSProperties,

  table: {
    width: "100%",
    borderCollapse: "collapse",
  } as React.CSSProperties,

  th: {
    padding: "8px 12px",
    textAlign: "left",
    fontSize: "10px",
    fontWeight: 700,
    color: "#6B7280",
    textTransform: "uppercase",
    letterSpacing: "0.06em",
    borderBottom: "1px solid #E3ECE7",
    whiteSpace: "nowrap",
    cursor: "pointer",
    userSelect: "none",
    transition: "background 0.15s",
  } as React.CSSProperties,

  thInner: {
    display: "flex",
    alignItems: "center",
    gap: "4px",
  } as React.CSSProperties,

  sortIcon: {
    color: "#9CA3AF",
    flexShrink: 0,
    transition: "color 0.15s, transform 0.2s",
  } as React.CSSProperties,

  td: {
    padding: "10px 12px",
    fontSize: "12px",
    color: "#1F2933",
    borderBottom: "1px solid #F0F6F2",
    verticalAlign: "middle",
    transition: "background 0.12s",
  } as React.CSSProperties,

  jobIdCell: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
  } as React.CSSProperties,

  jobIdText: {
    fontFamily: "'SF Mono', 'Fira Code', 'Cascadia Code', monospace",
    fontSize: "11.5px",
    fontWeight: 700,
    color: "#5C9470",
    letterSpacing: "-0.02em",
  } as React.CSSProperties,

  copyBtn: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    width: "22px",
    height: "22px",
    border: "none",
    borderRadius: "4px",
    cursor: "pointer",
    transition: "all 0.15s",
    flexShrink: 0,
  } as React.CSSProperties,

  customerName: {
    fontWeight: 600,
    color: "#2F4F3E",
    fontSize: "12px",
  } as React.CSSProperties,

  customerTitle: {
    fontSize: "10.5px",
    color: "#6B7280",
    marginTop: "1px",
  } as React.CSSProperties,

  locationCell: {
    display: "flex",
    alignItems: "center",
    gap: "5px",
  } as React.CSSProperties,

  locationText: {
    fontSize: "12px",
    color: "#1F2933",
  } as React.CSSProperties,

  mapLink: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    width: "20px",
    height: "20px",
    borderRadius: "4px",
    transition: "all 0.15s",
    flexShrink: 0,
  } as React.CSSProperties,

  techCell: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  } as React.CSSProperties,

  techAvatar: {
    width: "28px",
    height: "28px",
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontWeight: 700,
    color: "#FFFFFF",
    fontSize: "11px",
    flexShrink: 0,
    textTransform: "uppercase",
  } as React.CSSProperties,

  techInfo: {
    display: "flex",
    flexDirection: "column",
  } as React.CSSProperties,

  techName: {
    fontWeight: 600,
    fontSize: "12px",
    color: "#1F2933",
  } as React.CSSProperties,

  techStatusText: {
    fontSize: "10px",
    color: "#6B7280",
    textTransform: "capitalize",
  } as React.CSSProperties,

  unassigned: {
    fontSize: "11.5px",
    color: "#9CA3AF",
    fontStyle: "italic",
  } as React.CSSProperties,

  priorityBadge: {
    fontSize: "10px",
    fontWeight: 700,
    padding: "3px 8px",
    borderRadius: "20px",
    textTransform: "uppercase",
    letterSpacing: "0.03em",
    display: "inline-block",
  } as React.CSSProperties,
};

const avatarColors: Record<string, string> = {
  available: "#10B981",
  assigned: "#3B82F6",
  busy: "#F59E0B",
  offline: "#9CA3AF",
  unassigned: "#E5E7EB",
};

const priorityColors: Record<string, { bg: string; color: string }> = {
  CRITICAL: { bg: "#FAE5E5", color: "#7A2020" },
  HIGH: { bg: "#FEF0D6", color: "#7A5120" },
  MEDIUM: { bg: "#FDFBDC", color: "#706020" },
  LOW: { bg: "#DDEEE5", color: "#2F4F3E" },
  DEFAULT: { bg: "#F0F4F2", color: "#6B7280" },
};

export default DispatchQueueTable;
