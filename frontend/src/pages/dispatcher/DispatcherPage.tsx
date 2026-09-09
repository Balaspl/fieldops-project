import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Eye, RefreshCw } from "lucide-react";
import dispatcherService, {
  Dispatcher,
} from "../../services/dispatcherService";

const PAGE_SIZE = 8;
const REFRESH_MS = 60_000;

const styles = {
  page: {
    fontFamily: "'Inter', sans-serif",
    background: "#EEF4F1",
    height: "100%",
    maxHeight: "100%",
    padding: "14px",
    color: "#1F2933",
    display: "flex",
    flexDirection: "column",
    gap: "14px",
    boxSizing: "border-box",
    overflow: "hidden",
  } as React.CSSProperties,

  tableCard: {
    background: "#FFFFFF",
    border: "1px solid #E3ECE7",
    borderRadius: "12px",
    boxShadow: "0 1px 4px rgba(47,79,62,.07)",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    flex: 1,
    boxSizing: "border-box",
  } as React.CSSProperties,

  cardHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    flexWrap: "wrap",
    gap: "10px",
    padding: "10px 16px",
    borderBottom: "1px solid #E3ECE7",
    boxSizing: "border-box",
  } as React.CSSProperties,

  badge: {
    display: "inline-block",
    background: "#DDEEE5",
    color: "#2F4F3E",
    fontSize: "9px",
    fontWeight: 700,
    padding: "2px 6px",
    borderRadius: "20px",
    letterSpacing: ".05em",
    textTransform: "uppercase",
    marginBottom: "4px",
  } as React.CSSProperties,

  subtitle: {
    fontSize: "11px",
    color: "#6B7280",
    marginTop: "3px",
    marginBottom: 0,
  } as React.CSSProperties,

  headerRight: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    flexWrap: "wrap",
  } as React.CSSProperties,

  refreshInfo: {
    display: "flex",
    alignItems: "center",
    gap: "7px",
    fontSize: "10.5px",
    color: "#6B7280",
    fontWeight: 500,
  } as React.CSSProperties,

  refreshButton: {
    background: "#FFFFFF",
    border: "1.5px solid #E3ECE7",
    color: "#2F4F3E",
    padding: "6px 12px",
    borderRadius: "8px",
    fontSize: "10px",
    fontWeight: 600,
    fontFamily: "'Inter', sans-serif",
    cursor: "pointer",
    display: "flex",
    alignItems: "center",
    gap: "6px",
  } as React.CSSProperties,

  filterBar: {
    background: "transparent",
    borderBottom: "1px solid #E3ECE7",
    padding: "10px 16px",
    display: "flex",
    alignItems: "flex-end",
    gap: "12px",
    flexWrap: "wrap",
    boxSizing: "border-box",
  } as React.CSSProperties,

  filterGroup: {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
    minWidth: "160px",
  } as React.CSSProperties,

  searchGroup: {
    flex: 1,
    minWidth: "220px",
  } as React.CSSProperties,

  filterLabel: {
    fontSize: "9px",
    fontWeight: 700,
    color: "#6B7280",
    textTransform: "uppercase",
    letterSpacing: ".05em",
  } as React.CSSProperties,

  searchInput: {
    width: "100%",
    padding: "8px 10px 8px 30px",
    border: "1.5px solid #E3ECE7",
    borderRadius: "8px",
    fontSize: "11px",
    fontFamily: "'Inter', sans-serif",
    color: "#1F2933",
    background: "#FFFFFF",
    outline: "none",
    boxSizing: "border-box",
  } as React.CSSProperties,

  select: {
    padding: "8px 10px",
    border: "1.5px solid #E3ECE7",
    borderRadius: "8px",
    fontSize: "11px",
    fontFamily: "'Inter', sans-serif",
    color: "#1F2933",
    background: "#FFFFFF",
    outline: "none",
    cursor: "pointer",
    width: "100%",
    boxSizing: "border-box",
  } as React.CSSProperties,

  clearButton: {
    padding: "8px 14px",
    background: "#F6FAF8",
    border: "1.5px solid #E3ECE7",
    borderRadius: "8px",
    fontSize: "10px",
    fontWeight: 600,
    color: "#6B7280",
    cursor: "pointer",
    whiteSpace: "nowrap",
  } as React.CSSProperties,

  meta: {
    padding: "14px 20px 0",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    flexWrap: "wrap",
  } as React.CSSProperties,

  resultCount: {
    fontSize: "10px",
    color: "#6B7280",
    fontWeight: 500,
    margin: 0,
  } as React.CSSProperties,

  tableWrap: {
    overflowX: "auto",
    overflowY: "auto",
    flex: 1,
    minHeight: 0,
  } as React.CSSProperties,

  table: {
    width: "100%",
    borderCollapse: "collapse",
    minWidth: "750px",
  } as React.CSSProperties,

  th: {
    padding: "7px 12px",
    textAlign: "left",
    fontSize: "9px",
    fontWeight: 700,
    color: "#6B7280",
    textTransform: "uppercase",
    letterSpacing: ".05em",
    whiteSpace: "nowrap",
    background: "#F8FBF9",
    borderBottom: "2px solid #E3ECE7",
  } as React.CSSProperties,

  td: {
    padding: "7px 12px",
    fontSize: "11px",
    color: "#1F2933",
    verticalAlign: "middle",
    borderBottom: "1px solid #F0F4F2",
  } as React.CSSProperties,

  nameCell: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
  } as React.CSSProperties,

  avatar: {
    width: "34px",
    height: "34px",
    minWidth: "34px",
    borderRadius: "50%",
    background: "linear-gradient(135deg, #7AAE8A, #5C9470)",
    color: "#FFFFFF",
    fontSize: "12px",
    fontWeight: 700,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  } as React.CSSProperties,

  nameInfo: {
    display: "flex",
    flexDirection: "column",
  } as React.CSSProperties,

  name: {
    fontWeight: 600,
    color: "#1F2933",
    fontSize: "12px",
  } as React.CSSProperties,

  secondary: {
    fontSize: "9px",
    color: "#6B7280",
    marginTop: "2px",
  } as React.CSSProperties,

  statusActive: {
    display: "inline-flex",
    alignItems: "center",
    gap: "5px",
    padding: "4px 9px",
    borderRadius: "20px",
    background: "#DDEEE5",
    color: "#2F4F3E",
    fontSize: "9px",
    fontWeight: 700,
  } as React.CSSProperties,

  statusInactive: {
    display: "inline-flex",
    alignItems: "center",
    gap: "5px",
    padding: "4px 9px",
    borderRadius: "20px",
    background: "#F0F4F2",
    color: "#6B7280",
    fontSize: "9px",
    fontWeight: 700,
  } as React.CSSProperties,

  dutyOn: {
    color: "#2F7A3A",
    fontWeight: 600,
    fontSize: "10px",
  } as React.CSSProperties,

  dutyOff: {
    color: "#9B3A3A",
    fontWeight: 600,
    fontSize: "10px",
  } as React.CSSProperties,

  actionButton: {
    background: "none",
    border: "none",
    cursor: "pointer",
    padding: "4px",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#16a34a",
  } as React.CSSProperties,

  stateCell: {
    textAlign: "center",
    padding: "40px 20px",
    color: "#6B7280",
    fontSize: "12px",
  } as React.CSSProperties,

  pagination: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "6px 12px",
    borderTop: "1px solid #E3ECE7",
    flexWrap: "wrap",
    gap: "6px",
    background: "#FFFFFF",
  } as React.CSSProperties,

  pageInfo: {
    fontSize: "11px",
    color: "#6B7280",
    fontWeight: 500,
  } as React.CSSProperties,

  pageControls: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
  } as React.CSSProperties,

  pageButton: {
    padding: "3px 8px",
    background: "#FFFFFF",
    border: "1.5px solid #E3ECE7",
    borderRadius: "6px",
    fontSize: "10px",
    fontWeight: 600,
    color: "#2F4F3E",
    cursor: "pointer",
  } as React.CSSProperties,

  activePage: {
    background: "#7AAE8A",
    borderColor: "#7AAE8A",
    color: "#FFFFFF",
  } as React.CSSProperties,

  sidebarOverlay: {
    position: "fixed",
    inset: 0,
    background: "rgba(31,41,51,.3)",
    backdropFilter: "blur(2px)",
    zIndex: 999,
  } as React.CSSProperties,

  sidebar: {
    position: "fixed",
    top: 0,
    right: 0,
    width: "440px",
    height: "100vh",
    background: "#FFFFFF",
    boxShadow: "-4px 0 32px rgba(47,79,62,.12)",
    zIndex: 1000,
    display: "flex",
    flexDirection: "column",
  } as React.CSSProperties,

  sidebarHeader: {
    padding: "22px 24px",
    borderBottom: "1px solid #E3ECE7",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    background: "#F8FBF9",
  } as React.CSSProperties,

  sidebarTitle: {
    fontSize: "14.5px",
    fontWeight: 700,
    color: "#2F4F3E",
    margin: 0,
  } as React.CSSProperties,

  closeButton: {
    background: "none",
    border: "none",
    fontSize: "22px",
    color: "#6B7280",
    cursor: "pointer",
    width: "32px",
    height: "32px",
  } as React.CSSProperties,

  sidebarBody: {
    flex: 1,
    padding: "24px",
    overflowY: "auto",
  } as React.CSSProperties,

  detailHero: {
    display: "flex",
    alignItems: "center",
    gap: "14px",
    padding: "18px",
    background: "#F6FAF8",
    borderRadius: "10px",
    border: "1px solid #E3ECE7",
    marginBottom: "20px",
  } as React.CSSProperties,

  detailAvatar: {
    width: "52px",
    height: "52px",
    borderRadius: "50%",
    background: "linear-gradient(135deg, #7AAE8A, #5C9470)",
    color: "#FFFFFF",
    fontSize: "18px",
    fontWeight: 700,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  } as React.CSSProperties,

  detailName: {
    fontSize: "13.5px",
    fontWeight: 700,
    color: "#2F4F3E",
  } as React.CSSProperties,

  detailMeta: {
    fontSize: "10px",
    color: "#6B7280",
    marginTop: "3px",
  } as React.CSSProperties,

  sectionTitle: {
    fontSize: "9px",
    fontWeight: 700,
    color: "#6B7280",
    textTransform: "uppercase",
    letterSpacing: ".05em",
    marginBottom: "10px",
  } as React.CSSProperties,

  detailRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "9px 0",
    borderBottom: "1px solid #F0F4F2",
    fontSize: "10.5px",
  } as React.CSSProperties,

  detailLabel: {
    color: "#6B7280",
    fontWeight: 500,
  } as React.CSSProperties,

  detailValue: {
    color: "#1F2933",
    fontWeight: 600,
    textAlign: "right",
    maxWidth: "60%",
    wordBreak: "break-word",
  } as React.CSSProperties,
};

const localCss = `
  .dispatcher-row:hover td {
    background-color: #EAF4EE !important;
  }

  .dispatcher-action:hover {
    transform: scale(1.2);
    opacity: .8;
  }

  .dispatcher-refresh:hover:not(:disabled) {
    background-color: #F6FAF8 !important;
    border-color: #7AAE8A !important;
  }

  .dispatcher-search:focus,
  .dispatcher-select:focus {
    border-color: #7AAE8A !important;
    box-shadow: 0 0 0 3px rgba(122,174,138,.12) !important;
  }

  .dispatcher-clear:hover {
    border-color: #7AAE8A !important;
    color: #2F4F3E !important;
    background-color: #EAF4EE !important;
  }

  @media (max-width: 768px) {
    .dispatcher-header {
      flex-direction: column !important;
      align-items: flex-start !important;
    }

    .dispatcher-header-right {
      width: 100% !important;
      justify-content: space-between !important;
    }

    .dispatcher-filter {
      flex-direction: column !important;
      align-items: stretch !important;
    }

    .dispatcher-filter-group {
      width: 100% !important;
    }

    .dispatcher-table-wrap {
      overflow-x: visible !important;
    }

    .dispatcher-table thead {
      display: none !important;
    }

    .dispatcher-table tbody tr {
      display: flex !important;
      flex-direction: column !important;
      padding: 16px !important;
      border: 1px solid #E3ECE7 !important;
      border-radius: 10px !important;
      margin-bottom: 12px !important;
      background: #FFFFFF !important;
    }

    .dispatcher-table tbody td {
      display: flex !important;
      justify-content: space-between !important;
      align-items: center !important;
      padding: 8px 0 !important;
      border: none !important;
    }

    .dispatcher-table tbody td::before {
      content: attr(data-label);
      font-size: 11px;
      font-weight: 700;
      color: #6B7280;
      text-transform: uppercase;
    }

    .dispatcher-table tbody td:first-child::before,
    .dispatcher-table tbody td:last-child::before {
      display: none !important;
    }
  }

  @media (max-width: 560px) {
    .dispatcher-sidebar {
      width: 100% !important;
    }
  }
`;

function getInitials(name = "") {
  return name
    .trim()
    .split(/\s+/)
    .map((word) => word[0]?.toUpperCase() || "")
    .slice(0, 2)
    .join("");
}

function formatLastLogin(value: string | null) {
  if (!value) return "Never";

  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export default function DispatcherPage() {
  const [dispatchers, setDispatchers] = useState<Dispatcher[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [dutyFilter, setDutyFilter] = useState("ALL");

  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Dispatcher | null>(null);

  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const [countdown, setCountdown] = useState(100);

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchDispatchers = useCallback(async (silent = false) => {
    try {
      if (silent) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      setError("");

      const data = await dispatcherService.getDispatchers();

      setDispatchers(data);
      setLastUpdated(Date.now());
      setCountdown(0);
    } catch (err: any) {
      console.error("Failed to load dispatchers:", err);

      const message =
        err?.response?.data?.detail ||
        err?.response?.data?.error ||
        "Failed to load dispatchers";

      setError(message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchDispatchers(false);
  }, [fetchDispatchers]);

  useEffect(() => {
    intervalRef.current = setInterval(() => {
      if (lastUpdated) {
        const elapsed = Date.now() - lastUpdated;
        const percentage = Math.min(
          100,
          Math.round((elapsed / REFRESH_MS) * 100),
        );

        setCountdown(percentage);
      }
    }, 1000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [lastUpdated]);

  useEffect(() => {
    const timer = setInterval(() => {
      fetchDispatchers(true);
    }, REFRESH_MS);

    return () => clearInterval(timer);
  }, [fetchDispatchers]);

  useEffect(() => {
    setPage(1);
  }, [search, statusFilter, dutyFilter]);

  const filteredDispatchers = useMemo(() => {
    const query = search.trim().toLowerCase();

    return dispatchers.filter((dispatcher) => {
      const matchesSearch =
        !query ||
        dispatcher.name?.toLowerCase().includes(query) ||
        dispatcher.email?.toLowerCase().includes(query) ||
        dispatcher.phone_number?.toLowerCase().includes(query) ||
        dispatcher.organization_name?.toLowerCase().includes(query);

      const matchesStatus =
        statusFilter === "ALL" ||
        (statusFilter === "ACTIVE" && dispatcher.is_active) ||
        (statusFilter === "INACTIVE" && !dispatcher.is_active);

      const matchesDuty =
        dutyFilter === "ALL" ||
        (dutyFilter === "ON_DUTY" && dispatcher.is_on_duty) ||
        (dutyFilter === "OFF_DUTY" && !dispatcher.is_on_duty);

      return matchesSearch && matchesStatus && matchesDuty;
    });
  }, [dispatchers, search, statusFilter, dutyFilter]);

  const totalPages = Math.max(
    1,
    Math.ceil(filteredDispatchers.length / PAGE_SIZE),
  );

  const safePage = Math.min(page, totalPages);

  const pageSlice = filteredDispatchers.slice(
    (safePage - 1) * PAGE_SIZE,
    safePage * PAGE_SIZE,
  );

  function clearFilters() {
    setSearch("");
    setStatusFilter("ALL");
    setDutyFilter("ALL");
    setPage(1);
  }

  const hasFilters = search || statusFilter !== "ALL" || dutyFilter !== "ALL";

  function getPageNumbers() {
    const numbers: number[] = [];
    const delta = 2;

    for (
      let i = Math.max(1, safePage - delta);
      i <= Math.min(totalPages, safePage + delta);
      i++
    ) {
      numbers.push(i);
    }

    return numbers;
  }

  function handleManualRefresh() {
    fetchDispatchers(true);
    setCountdown(0);
  }

  function openSidebar(dispatcher: Dispatcher) {
    setSelected(dispatcher);
  }

  function closeSidebar() {
    setSelected(null);
  }

  return (
    <div style={styles.page}>
      <style>{localCss}</style>

      <div style={styles.tableCard}>
        {/* HEADER */}
        <div className="dispatcher-header" style={styles.cardHeader}>
          <div>
            <span style={styles.badge}>Dashboard</span>

            <p style={styles.subtitle}>
              Monitor registered dispatchers and organization access
            </p>
          </div>

          <div className="dispatcher-header-right" style={styles.headerRight}>
            <div style={styles.refreshInfo}>
              {refreshing ? (
                <>
                  <RefreshCw
                    size={12}
                    style={{ animation: "spin 1s linear infinite" }}
                  />
                  <span style={{ color: "#5C9470", fontWeight: 600 }}>
                    Refreshing…
                  </span>
                </>
              ) : (
                <span>
                  Updated{" "}
                  {lastUpdated
                    ? new Date(lastUpdated).toLocaleTimeString()
                    : "—"}
                </span>
              )}
            </div>

            <button
              className="dispatcher-refresh"
              style={styles.refreshButton}
              onClick={handleManualRefresh}
              disabled={loading || refreshing}
            >
              <RefreshCw size={12} />
              {refreshing ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        </div>

        {/* COUNTDOWN */}
        {!loading && dispatchers.length > 0 && !refreshing && (
          <div
            style={{
              width: "100%",
              height: "3px",
              background: "#E3ECE7",
            }}
          >
            <div
              style={{
                height: "100%",
                width: `${countdown}%`,
                background: "#7AAE8A",
                transition: "width 1s linear",
              }}
            />
          </div>
        )}

        {/* FILTERS */}
        <div className="dispatcher-filter" style={styles.filterBar}>
          <div
            className="dispatcher-filter-group"
            style={{ ...styles.filterGroup, ...styles.searchGroup }}
          >
            <label style={styles.filterLabel}>Search</label>

            <div style={{ position: "relative" }}>
              <span
                style={{
                  position: "absolute",
                  left: "10px",
                  top: "50%",
                  transform: "translateY(-50%)",
                  color: "#A0B5A8",
                  fontSize: "13px",
                }}
              >
                🔍
              </span>

              <input
                className="dispatcher-search"
                style={styles.searchInput}
                placeholder="Name, email, phone, organization…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>

          <div className="dispatcher-filter-group" style={styles.filterGroup}>
            <label style={styles.filterLabel}>Status</label>

            <select
              className="dispatcher-select"
              style={styles.select}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="ALL">All Statuses</option>
              <option value="ACTIVE">Active</option>
              <option value="INACTIVE">Inactive</option>
            </select>
          </div>

          <div className="dispatcher-filter-group" style={styles.filterGroup}>
            <label style={styles.filterLabel}>Duty</label>

            <select
              className="dispatcher-select"
              style={styles.select}
              value={dutyFilter}
              onChange={(e) => setDutyFilter(e.target.value)}
            >
              <option value="ALL">All Duty Status</option>
              <option value="ON_DUTY">On Duty</option>
              <option value="OFF_DUTY">Off Duty</option>
            </select>
          </div>

          {hasFilters && (
            <button
              className="dispatcher-clear"
              style={styles.clearButton}
              onClick={clearFilters}
            >
              Clear
            </button>
          )}
        </div>

        {/* META */}
        <div style={styles.meta}>
          <p style={styles.resultCount}>
            Showing <strong>{pageSlice.length}</strong> of{" "}
            <strong>{filteredDispatchers.length}</strong> dispatcher
            {filteredDispatchers.length !== 1 ? "s" : ""}
          </p>
        </div>

        {/* TABLE */}
        <div className="dispatcher-table-wrap" style={styles.tableWrap}>
          <table className="dispatcher-table" style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Dispatcher</th>
                <th style={styles.th}>Email</th>
                <th style={styles.th}>Organization</th>
                <th style={styles.th}>Status</th>
                <th style={styles.th}>Duty</th>
                <th style={styles.th}>Actions</th>
              </tr>
            </thead>

            <tbody>
              {loading && (
                <tr>
                  <td colSpan={6} style={styles.stateCell}>
                    Loading dispatchers...
                  </td>
                </tr>
              )}

              {!loading && error && (
                <tr>
                  <td colSpan={6} style={styles.stateCell}>
                    <div style={{ marginBottom: "10px" }}>{error}</div>

                    <button
                      style={{
                        ...styles.refreshButton,
                        margin: "0 auto",
                      }}
                      onClick={() => fetchDispatchers(false)}
                    >
                      Retry
                    </button>
                  </td>
                </tr>
              )}

              {!loading && !error && pageSlice.length === 0 && (
                <tr>
                  <td colSpan={6} style={styles.stateCell}>
                    {hasFilters
                      ? "No dispatchers match your filters."
                      : "No dispatchers found."}
                  </td>
                </tr>
              )}

              {!loading &&
                !error &&
                pageSlice.map((dispatcher) => (
                  <tr
                    key={dispatcher.id}
                    className="dispatcher-row"
                    onClick={() => openSidebar(dispatcher)}
                    style={{ cursor: "pointer" }}
                  >
                    <td data-label="Dispatcher" style={styles.td}>
                      <div style={styles.nameCell}>
                        <div style={styles.avatar}>
                          {getInitials(dispatcher.name)}
                        </div>

                        <div style={styles.nameInfo}>
                          <span style={styles.name}>{dispatcher.name}</span>

                          <span style={styles.secondary}>
                            ID: {dispatcher.id}
                          </span>
                        </div>
                      </div>
                    </td>

                    <td data-label="Email" style={styles.td}>
                      {dispatcher.email}
                    </td>

                    <td data-label="Organization" style={styles.td}>
                      <span
                        style={{
                          color: "#475569",
                          fontWeight: 500,
                        }}
                      >
                        {dispatcher.organization_name || "—"}
                      </span>
                    </td>

                    <td data-label="Status" style={styles.td}>
                      <span
                        style={
                          dispatcher.is_active
                            ? styles.statusActive
                            : styles.statusInactive
                        }
                      >
                        ● {dispatcher.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>

                    <td data-label="Duty" style={styles.td}>
                      <span
                        style={
                          dispatcher.is_on_duty ? styles.dutyOn : styles.dutyOff
                        }
                      >
                        {dispatcher.is_on_duty ? "On Duty" : "Off Duty"}
                      </span>
                    </td>

                    <td
                      data-label="Actions"
                      style={styles.td}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <button
                        className="dispatcher-action"
                        style={styles.actionButton}
                        onClick={() => openSidebar(dispatcher)}
                        title="View dispatcher"
                        aria-label="View dispatcher"
                      >
                        <Eye size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>

        {/* PAGINATION */}
        {!loading && !error && (
          <div style={styles.pagination}>
            <span style={styles.pageInfo}>
              Page <strong>{safePage}</strong> of <strong>{totalPages}</strong>{" "}
              · {filteredDispatchers.length} results
            </span>

            <div style={styles.pageControls}>
              <button
                style={styles.pageButton}
                onClick={() => setPage(1)}
                disabled={safePage === 1}
              >
                «
              </button>

              <button
                style={styles.pageButton}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={safePage === 1}
              >
                ‹ Prev
              </button>

              {getPageNumbers().map((number) => (
                <button
                  key={number}
                  style={{
                    ...styles.pageButton,
                    ...(number === safePage ? styles.activePage : {}),
                  }}
                  onClick={() => setPage(number)}
                >
                  {number}
                </button>
              ))}

              <button
                style={styles.pageButton}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={safePage === totalPages}
              >
                Next ›
              </button>

              <button
                style={styles.pageButton}
                onClick={() => setPage(totalPages)}
                disabled={safePage === totalPages}
              >
                »
              </button>
            </div>
          </div>
        )}
      </div>

      {/* DETAIL SIDEBAR */}
      {selected && <div style={styles.sidebarOverlay} onClick={closeSidebar} />}

      {selected && (
        <div className="dispatcher-sidebar" style={styles.sidebar}>
          <div style={styles.sidebarHeader}>
            <h3 style={styles.sidebarTitle}>Dispatcher Details</h3>

            <button style={styles.closeButton} onClick={closeSidebar}>
              ×
            </button>
          </div>

          <div style={styles.sidebarBody}>
            <div style={styles.detailHero}>
              <div style={styles.detailAvatar}>
                {getInitials(selected.name)}
              </div>

              <div>
                <div style={styles.detailName}>{selected.name}</div>

                <div style={styles.detailMeta}>
                  {selected.is_active
                    ? "Active Dispatcher"
                    : "Inactive Dispatcher"}
                </div>
              </div>
            </div>

            <p style={styles.sectionTitle}>Dispatcher Information</p>

            {[
              ["ID", selected.id],
              ["Email", selected.email],
              ["Phone", selected.phone_number || "—"],
              ["Organization", selected.organization_name || "—"],
              ["Tenant ID", selected.tenant_id],
              ["Status", selected.is_active ? "Active" : "Inactive"],
              ["Duty Status", selected.is_on_duty ? "On Duty" : "Off Duty"],
              ["Last Login", formatLastLogin(selected.last_login)],
            ].map(([label, value]) => (
              <div key={label} style={styles.detailRow}>
                <span style={styles.detailLabel}>{label}</span>

                <span style={styles.detailValue}>{value}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
