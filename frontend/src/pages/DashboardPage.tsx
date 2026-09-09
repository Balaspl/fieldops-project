import React, { useEffect, useState } from "react";
import { getDashboardStats, getJobs } from "../services/planningService";
import NotificationBell from "../components/notifications/NotificationBell";
import LoadingSpinner from "../components/ui/LoadingSpinner";
import {
  Briefcase,
  User,
  Clock,
  CheckCircle,
  AlertCircle,
  Users,
  BarChart,
  Calendar,
  Coffee,
  MinusCircle,
  Snowflake,
  Zap,
  Droplet,
  Wrench,
  MoreHorizontal,
  MoreVertical,
  TrendingUp,
  Check
} from "lucide-react";
import EmptyState from "../components/ui/EmptyState";

interface Job {
  id: string | number;
  customer_name: string;
  issue_description?: string;
  location: string;
  service_type: string;
  priority: string;
  status: string;
  preferred_service_date?: string;
}

interface DashboardStats {
  jobs: {
    pending: number;
    active: number;
    in_progress: number;
    completed: number;
    total: number;
  };
  technicians: {
    available: number;
    busy: number;
    break: number;
    offline: number;
  };
  categories: {
    hvac: number;
    electrical: number;
    plumbing: number;
    mechanical: number;
    other: number;
  };
}

const styles = {
  opsDashboard: {
    fontFamily: "'Inter', sans-serif",
    padding: "14px",
    display: "flex",
    flexDirection: "column",
    gap: "14px",
    color: "#1F2937",
    background: "#F9FAFB",
    minHeight: "100vh",
    boxSizing: "border-box",
    flexShrink: 0,
  } as React.CSSProperties,

  dashboardHeaderCard: {
    background: "#FFFFFF",
    borderRadius: "10px",
    padding: "10px 16px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    border: "1px solid #E3ECE7",
    boxShadow: "0 1px 4px rgba(47, 79, 62, 0.05)",
    boxSizing: "border-box",
  } as React.CSSProperties,

  headerGreetingArea: {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
  } as React.CSSProperties,

  headerWelcomeTitle: {
    fontSize: "16px",
    fontWeight: 800,
    color: "#111827",
    margin: 0,
  } as React.CSSProperties,

  headerWelcomeSubtitle: {
    fontSize: "11px",
    color: "#4B5563",
    margin: 0,
  } as React.CSSProperties,

  headerControlsArea: {
    display: "flex",
    alignItems: "center",
    gap: "16px",
  } as React.CSSProperties,

  dropdownCalendarWrap: {
    position: "relative",
    display: "flex",
    alignItems: "center",
  } as React.CSSProperties,

  dropdownCalendarIcon: {
    position: "absolute",
    left: "10px",
    color: "#374151",
    pointerEvents: "none",
  } as React.CSSProperties,

  dropdownThisWeek: {
    height: "32px",
    padding: "0 28px 0 26px",
    borderRadius: "8px",
    border: "1px solid #E2E8F0",
    fontSize: "12px",
    fontWeight: 600,
    color: "#374151",
    background: "#FFFFFF",
    cursor: "pointer",
    outline: "none",
    transition: "border-color 0.2s",
    appearance: "none",
    backgroundImage: `url("data:image/svg+xml;charset=UTF-8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23374151' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E")`,
    backgroundRepeat: "no-repeat",
    backgroundPosition: "right 8px center",
    backgroundSize: "10px",
  } as React.CSSProperties,

  dashboardSearchBar: {
    position: "relative",
    width: "240px",
  } as React.CSSProperties,

  dashboardSearchIcon: {
    position: "absolute",
    left: "10px",
    top: "50%",
    transform: "translateY(-50%)",
    fontSize: "12px",
    color: "#9CA3AF",
    pointerEvents: "none",
  } as React.CSSProperties,

  dashboardSearchInput: {
    width: "100%",
    padding: "8px 12px 8px 28px",
    borderRadius: "8px",
    border: "1px solid #E3ECE7",
    fontSize: "12.5px",
    color: "#1F2937",
    outline: "none",
    background: "#F9FAFB",
    transition: "all 0.2s",
    boxSizing: "border-box",
  } as React.CSSProperties,

  metricsCardsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(5, 1fr)",
    gap: "16px",
  } as React.CSSProperties,

  metricSlantedCard: {
    position: "relative",
    height: "70px",
    display: "flex",
    alignItems: "center",
    cursor: "pointer",
    transition: "transform 0.2s ease",
    background: "transparent",
    border: "none",
    boxShadow: "none",
    overflow: "visible",
    padding: 0,
    width: "100%",
    textAlign: "left",
  } as React.CSSProperties,

  metricCardBgSvg: {
    position: "absolute",
    top: 0,
    left: 0,
    width: "100%",
    height: "100%",
    zIndex: 1,
    pointerEvents: "none",
    filter: "drop-shadow(0 2px 4px rgba(47, 79, 62, 0.05))",
    transition: "filter 0.2s ease",
  } as React.CSSProperties,

  metricCardContent: {
    position: "relative",
    zIndex: 2,
    display: "flex",
    alignItems: "center",
    gap: "12px",
    width: "100%",
    height: "100%",
    boxSizing: "border-box",
  } as React.CSSProperties,

  padCardFirst: {
    padding: "12px 18px 12px 18px",
  } as React.CSSProperties,

  padCardMiddle: {
    padding: "12px 18px 12px 24px",
  } as React.CSSProperties,

  padCardLast: {
    padding: "12px 16px 12px 24px",
  } as React.CSSProperties,

  metricIconWrap: {
    width: "28px",
    height: "28px",
    borderRadius: "6px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    minWidth: "28px",
  } as React.CSSProperties,

  metricDetails: {
    display: "flex",
    flexDirection: "column",
    gap: "1px",
    flex: 1,
    minWidth: 0,
  } as React.CSSProperties,

  metricLabel: {
    fontSize: "9px",
    fontWeight: 700,
    color: "#6B7280",
    textTransform: "uppercase",
    letterSpacing: "0.03em",
    whiteSpace: "nowrap",
  } as React.CSSProperties,

  metricVal: {
    fontSize: "16px",
    fontWeight: 800,
    color: "#111827",
    margin: 0,
    lineHeight: 1.25,
  } as React.CSSProperties,

  metricStatRow: {
    display: "flex",
    alignItems: "center",
    gap: "4px",
    fontSize: "10px",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textStyle: "ellipsis",
  } as React.CSSProperties,

  statCompare: {
    color: "#9CA3AF",
    whiteSpace: "nowrap",
  } as React.CSSProperties,

  contentCardsGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: "20px",
  } as React.CSSProperties,

  opsCard: {
    background: "#FFFFFF",
    borderRadius: "12px",
    border: "1px solid #E3ECE7",
    boxShadow: "0 2px 6px rgba(47, 79, 62, 0.03)",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    height: "285px",
    boxSizing: "border-box",
  } as React.CSSProperties,

  opsCardHeader: {
    padding: "16px 20px",
    borderBottom: "1px solid #F3F4F6",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    boxSizing: "border-box",
  } as React.CSSProperties,

  opsCardHeaderH3: {
    fontSize: "11px",
    fontWeight: 700,
    color: "#334155",
    letterSpacing: "0.05em",
    margin: 0,
    textTransform: "uppercase",
    whiteSpace: "nowrap",
  } as React.CSSProperties,

  dropdownSmall: {
    padding: "5px 22px 5px 10px",
    borderRadius: "6px",
    border: "1px solid #E2E8F0",
    fontSize: "11.5px",
    fontFamily: "'Inter', sans-serif",
    fontWeight: 600,
    color: "#334155",
    background: "#FFFFFF",
    cursor: "pointer",
    outline: "none",
    appearance: "none",
    backgroundImage: `url("data:image/svg+xml;charset=UTF-8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23475569' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E")`,
    backgroundRepeat: "no-repeat",
    backgroundPosition: "right 8px center",
    backgroundSize: "10px",
  } as React.CSSProperties,

  opsCardBody: {
    padding: "12px 16px",
    flex: 1,
    display: "flex",
    alignItems: "center",
    boxSizing: "border-box",
  } as React.CSSProperties,

  opsCardFooter: {
    padding: "8px 16px",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    height: "52px",
    boxSizing: "border-box",
  } as React.CSSProperties,

  footerStat: {
    fontSize: "12px",
    fontWeight: 600,
    display: "flex",
    alignItems: "center",
    gap: "6px",
  } as React.CSSProperties,

  footerLinkBtn: {
    background: "none",
    border: "none",
    fontSize: "12px",
    fontWeight: 700,
    cursor: "pointer",
    padding: 0,
    transition: "transform 0.2s ease",
  } as React.CSSProperties,

  bodyJobsOverview: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: "24px",
    padding: "8px 16px 12px 20px",
    boxSizing: "border-box",
    width: "100%",
  } as React.CSSProperties,

  jobsOverviewLabels: {
    display: "flex",
    flexDirection: "column",
    gap: "12px",
    flex: 1,
  } as React.CSSProperties,

  overviewRow: {
    display: "grid",
    gridTemplateColumns: "22px 75px 15px auto",
    alignItems: "center",
    gap: "8px",
  } as React.CSSProperties,

  overviewLbl: {
    color: "#374151",
    fontSize: "12px",
    fontWeight: 600,
  } as React.CSSProperties,

  overviewNum: {
    fontSize: "12px",
    fontWeight: 700,
    color: "#111827",
    textAlign: "right",
  } as React.CSSProperties,

  overviewPct: {
    fontSize: "11.5px",
    fontWeight: 500,
    color: "#64748B",
    marginLeft: "2px",
  } as React.CSSProperties,

  jobsOverviewDiagram: {
    width: "100%",
    maxWidth: "170px",
    height: "150px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flex: 1.4,
  } as React.CSSProperties,

  bodyTechAvailability: {
    justifyContent: "center",
    padding: "12px 10px",
    boxSizing: "border-box",
    width: "100%",
  } as React.CSSProperties,

  gaugesFlexRow: {
    display: "flex",
    justifyContent: "space-between",
    width: "100%",
    gap: "8px",
  } as React.CSSProperties,

  gaugeItem: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "6px",
    flex: 1,
    minWidth: 0,
  } as React.CSSProperties,

  gaugeCircleWrap: {
    width: "52px",
    height: "52px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    position: "relative",
  } as React.CSSProperties,

  gaugePercentText: {
    fontFamily: "'Inter', sans-serif",
    fill: "#111827",
  } as React.CSSProperties,

  gaugeName: {
    fontSize: "9px",
    color: "#4B5563",
    textAlign: "center",
    whiteSpace: "nowrap",
  } as React.CSSProperties,

  gaugeCount: {
    fontSize: "12px",
    fontWeight: 800,
    color: "#111827",
  } as React.CSSProperties,

  bodyServiceSplit: {
    alignItems: "flex-start",
    paddingTop: "14px",
    boxSizing: "border-box",
    width: "100%",
  } as React.CSSProperties,

  categoryBarsList: {
    display: "flex",
    flexDirection: "column",
    gap: "10px",
    width: "100%",
  } as React.CSSProperties,

  categoryBarRow: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    fontSize: "12px",
    width: "100%",
  } as React.CSSProperties,

  categoryTagBadge: {
    width: "22px",
    height: "22px",
    borderRadius: "6px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: "11px",
    color: "#FFFFFF",
    flexShrink: 0,
  } as React.CSSProperties,

  categoryLabel: {
    width: "72px",
    fontWeight: 500,
    color: "#374151",
  } as React.CSSProperties,

  categoryBarTrack: {
    flex: 1,
    height: "6px",
    background: "#E5E7EB",
    borderRadius: "3px",
    overflow: "hidden",
  } as React.CSSProperties,

  categoryBarFill: {
    height: "100%",
    borderRadius: "3px",
  } as React.CSSProperties,

  categoryValue: {
    width: "82px",
    textAlign: "right",
    color: "#111827",
    fontWeight: 700,
  } as React.CSSProperties,

  indicatorBadge: {
    width: "22px",
    height: "22px",
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    marginRight: 0,
    flexShrink: 0,
    color: "#FFFFFF",
  } as React.CSSProperties,

  gaugeSubIcon: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    marginTop: "6px",
    marginBottom: "2px",
  } as React.CSSProperties,

  footerIconGreen: {
    color: "#15803D",
    marginRight: "4px",
    verticalAlign: "middle",
  } as React.CSSProperties,

  footerIconBlue: {
    color: "#2563EB",
    verticalAlign: "middle",
  } as React.CSSProperties,

  footerIconPurple: {
    color: "#7C3AED",
    verticalAlign: "middle",
  } as React.CSSProperties,

  footerStatContainer: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  } as React.CSSProperties,

  footerStatTextWrap: {
    display: "flex",
    flexDirection: "column",
    lineHeight: 1.25,
    textAlign: "left",
  } as React.CSSProperties,

  footerStatPrimary: {
    fontSize: "12px",
    fontWeight: 700,
    color: "#2563EB",
  } as React.CSSProperties,

  footerStatPrimaryPurple: {
    fontSize: "12px",
    fontWeight: 700,
    color: "#7C3AED",
  } as React.CSSProperties,

  footerStatSecondary: {
    fontSize: "10.5px",
    color: "#475569",
    fontWeight: 500,
  } as React.CSSProperties,

  cardRecentJobs: {
    background: "#FFFFFF",
    borderRadius: "12px",
    border: "1px solid #E3ECE7",
    boxShadow: "0 2px 6px rgba(47, 79, 62, 0.03)",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    boxSizing: "border-box",
  } as React.CSSProperties,

  recentJobsTableContainer: {
    padding: "8px 16px",
    overflowX: "auto",
    boxSizing: "border-box",
  } as React.CSSProperties,

  recentJobsTable: {
    width: "100%",
    borderCollapse: "collapse",
    textAlign: "left",
  } as React.CSSProperties,

  recentJobsTableTh: {
    padding: "10px 12px",
    fontSize: "10px",
    fontWeight: 700,
    color: "#475569",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    borderBottom: "1px solid #E2E8F0",
  } as React.CSSProperties,

  recentJobsTableTd: {
    padding: "12px",
    fontSize: "12px",
    color: "#334155",
    borderBottom: "1px solid #F1F5F9",
    verticalAlign: "middle",
  } as React.CSSProperties,

  jobIdPill: {
    fontWeight: 700,
    color: "#5C9470",
  } as React.CSSProperties,

  priorityBadge: {
    fontSize: "9.5px",
    fontWeight: 700,
    padding: "3px 8px",
    borderRadius: "20px",
    textTransform: "uppercase",
    letterSpacing: "0.03em",
    display: "inline-block",
  } as React.CSSProperties,

  statusBadge: {
    fontSize: "9.5px",
    fontWeight: 600,
    padding: "2.5px 9px",
    borderRadius: "20px",
    textTransform: "capitalize",
    display: "inline-block",
  } as React.CSSProperties,

  segmentedBarTrack: {
    display: "flex",
    gap: "3px",
    flex: 1,
    alignItems: "center",
  } as React.CSSProperties,

  segmentedBarDot: {
    flex: 1,
    height: "8px",
    borderRadius: "2px",
    transition: "all 0.2s ease",
  } as React.CSSProperties,

  metricCardNew: {
    position: "relative",
    height: "68px",
    display: "flex",
    alignItems: "center",
    cursor: "pointer",
    background: "#FFFFFF",
    border: "1px solid #E2E8F0",
    borderRadius: "10px",
    boxShadow: "0 1px 2px rgba(0, 0, 0, 0.04)",
    overflow: "hidden",
    padding: "6px 12px",
    width: "100%",
    boxSizing: "border-box",
    textAlign: "left",
    gap: "10px",
  } as React.CSSProperties,

  metricCardContentNew: {
    display: "flex",
    alignItems: "center",
    width: "100%",
    height: "100%",
    gap: "10px",
  } as React.CSSProperties,

  iconContainer: {
    width: "36px",
    height: "36px",
    borderRadius: "8px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    boxShadow: "0 1px 2px rgba(0, 0, 0, 0.02)",
  } as React.CSSProperties,

  metricDetailsNew: {
    display: "flex",
    flexDirection: "column",
    flex: 1,
    minWidth: 0,
    justifyContent: "center",
    gap: "1px",
  } as React.CSSProperties,

  metricLabelRowNew: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    width: "100%",
    lineHeight: 1,
  } as React.CSSProperties,

  metricLabelNew: {
    fontSize: "9px",
    fontWeight: 700,
    color: "#64748B",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    whiteSpace: "nowrap",
  } as React.CSSProperties,

  metricValNew: {
    fontSize: "18px",
    fontWeight: 800,
    color: "#0F172A",
    margin: 0,
    lineHeight: 1.1,
  } as React.CSSProperties,

  metricSubtextNew: {
    fontSize: "9.5px",
    color: "#64748B",
    fontWeight: 500,
    whiteSpace: "nowrap",
  } as React.CSSProperties,

  moreIconNew: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    cursor: "pointer",
    color: "#94A3B8",
    opacity: 0.8,
    padding: "2px",
    marginRight: "-2px",
  } as React.CSSProperties,
};

const localCss = `
  .metric-new-card-style {
    transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease !important;
  }
  .metric-new-card-style:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 14px rgba(0, 0, 0, 0.05) !important;
    border-color: #CBD5E1 !important;
  }
  .metric-accent-bar {
    transform: scaleX(0.18);
    transform-origin: left;
    transition: transform 0.35s cubic-bezier(0.4, 0, 0.2, 1) !important;
  }
  .metric-new-card-style:hover .metric-accent-bar {
    transform: scaleX(1) !important;
  }
  .footer-link-btn-style:hover {
    transform: translateX(3px) !important;
  }
  .recent-jobs-table-row:hover td {
    background-color: #F8FAFC !important;
  }
  .dropdown-this-week-style:hover {
    border-color: #7AAE8A !important;
  }
  .dashboard-search-input-style:focus {
    border-color: #7AAE8A !important;
    background-color: #FFFFFF !important;
    box-shadow: 0 0 0 3px rgba(122, 174, 138, 0.15) !important;
  }
  .diagram-group-style {
    transition: filter 0.25s ease !important;
  }
  .diagram-group-style:hover {
    filter: brightness(1.08) !important;
  }
  .gauge-circle-progress-style {
    transform-origin: 18px 18px !important;
    animation: rotate-progress 1s cubic-bezier(0.4, 0, 0.2, 1) forwards !important;
  }
  @keyframes rotate-progress {
    from {
      transform: rotate(-90deg);
    }
    to {
      transform: rotate(0deg);
    }
  }
  
  @media (max-width: 1024px) {
    .metrics-cards-grid-responsive {
      grid-template-columns: repeat(3, 1fr) !important;
    }
    .content-cards-grid-responsive {
      grid-template-columns: 1fr !important;
    }
  }
  @media (max-width: 768px) {
    .metrics-cards-grid-responsive {
      grid-template-columns: repeat(2, 1fr) !important;
    }
    .dashboard-header-responsive {
      flex-direction: column !important;
      align-items: flex-start !important;
      gap: 12px !important;
    }
    .header-controls-responsive {
      width: 100% !important;
      justify-content: space-between !important;
      flex-wrap: wrap !important;
    }
  }
  @media (max-width: 500px) {
    .metrics-cards-grid-responsive {
      grid-template-columns: 1fr !important;
    }
    .gauges-flex-row-responsive {
      flex-direction: column !important;
      gap: 14px !important;
    }
    .body-jobs-overview-responsive {
      flex-direction: column !important;
      align-items: flex-start !important;
    }
  }
`;

const getPriorityStyle = (priority: string): React.CSSProperties => {
  const p = (priority || "").toUpperCase();
  if (p === "CRITICAL" || p === "P1") {
    return { ...styles.priorityBadge, background: "#FAE5E5", color: "#7A2020" };
  }
  if (p === "HIGH" || p === "P2") {
    return { ...styles.priorityBadge, background: "#FEF0D6", color: "#7A5120" };
  }
  if (p === "MEDIUM" || p === "P3") {
    return { ...styles.priorityBadge, background: "#FDFBDC", color: "#706020" };
  }
  if (p === "LOW" || p === "P4" || p === "P5") {
    return { ...styles.priorityBadge, background: "#DDEEE5", color: "#2F4F3E" };
  }
  return { ...styles.priorityBadge, background: "#F0F4F2", color: "#6B7280" };
};

const getStatusStyle = (status: string): React.CSSProperties => {
  const s = (status || "").toLowerCase().trim().replace(" ", "-");
  if (s === "inprogress" || s === "in-progress") {
    return { ...styles.statusBadge, background: "#FEF3DC", color: "#7A5120" };
  }
  if (s === "canceled" || s === "cancelled") {
    return { ...styles.statusBadge, background: "#FAE5E5", color: "#7A2020" };
  }
  if (s === "completed") {
    return { ...styles.statusBadge, background: "#E8F0FE", color: "#2F5090" };
  }
  return { ...styles.statusBadge, background: "#DDEEE5", color: "#2F4F3E" }; // active/available default
};

const formatStatus = (status: string): string => {
  const s = (status || "active").toLowerCase().trim();
  if (s === "inprogress" || s === "in progress") return "In Progress";
  if (s === "canceled" || s === "cancelled") return "Cancelled";
  return s.charAt(0).toUpperCase() + s.slice(1);
};

interface SegmentedProgressBarProps {
  percentage: number;
  colorClass: string;
}

const SegmentedProgressBar: React.FC<SegmentedProgressBarProps> = ({ percentage, colorClass }) => {
  const activeCount = Math.round(percentage / 10);

  // Color mappings
  const getDotStyle = (isActive: boolean, type: string): React.CSSProperties => {
    let activeColor = "#828282";
    let inactiveColor = "rgba(130, 130, 130, 0.15)";

    if (type === "fill-hvac") {
      activeColor = "#02B075";
      inactiveColor = "rgba(2, 176, 117, 0.15)";
    } else if (type === "fill-elec") {
      activeColor = "#2F80ED";
      inactiveColor = "rgba(47, 128, 237, 0.15)";
    } else if (type === "fill-plumb") {
      activeColor = "#F2994A";
      inactiveColor = "rgba(242, 153, 74, 0.15)";
    } else if (type === "fill-mech") {
      activeColor = "#9B51E0";
      inactiveColor = "rgba(155, 81, 224, 0.15)";
    }

    return {
      ...styles.segmentedBarDot,
      background: isActive ? activeColor : inactiveColor
    };
  };

  return (
    <div style={styles.segmentedBarTrack}>
      {Array.from({ length: 10 }).map((_, idx) => {
        const isActive = idx < activeCount;
        return (
          <div
            key={idx}
            style={getDotStyle(isActive, colorClass)}
          />
        );
      })}
    </div>
  );
};

interface AnimatedGaugeProps {
  percentage: number;
  count: number;
  label: string;
  icon: React.ComponentType<any>;
  color: string;
  textColor: string;
}

const AnimatedGauge: React.FC<AnimatedGaugeProps> = ({ percentage, count, label, icon: Icon, color, textColor }) => {
  const [displayPct, setDisplayPct] = useState(0);

  useEffect(() => {
    const start = 0;
    const end = Math.round(percentage);
    if (start === end) {
      setDisplayPct(end);
      return;
    }

    const duration = 1000;
    const startTime = performance.now();

    let animationFrameId: number;

    const animate = (currentTime: number) => {
      const elapsedTime = currentTime - startTime;
      const progress = Math.min(elapsedTime / duration, 1);

      const easeProgress = progress * (2 - progress);

      const currentVal = Math.round(easeProgress * end);
      setDisplayPct(currentVal);

      if (progress < 1) {
        animationFrameId = requestAnimationFrame(animate);
      }
    };

    animationFrameId = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, [percentage]);

  return (
    <div style={styles.gaugeItem}>
      <div style={styles.gaugeCircleWrap}>
        <svg width="100%" height="100%" viewBox="0 0 36 36">
          <path
            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
            fill="none"
            stroke="#F3F4F6"
            strokeWidth="2.5"
          />
          <path
            className="gauge-circle-progress-style"
            strokeDasharray={`${displayPct}, 100`}
            d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
            fill="none"
            stroke={color}
            strokeWidth="2.5"
            strokeLinecap="round"
          />
          <text x="18" y="20.35" style={styles.gaugePercentText} textAnchor="middle" fontSize="6.5" fontWeight="700" fill={color}>
            {displayPct}%
          </text>
        </svg>
      </div>
      <span style={{ ...styles.gaugeSubIcon, color: textColor }}><Icon size={16} /></span>
      <span style={styles.gaugeName}>{label}</span>
      <strong style={styles.gaugeCount}>{count}</strong>
    </div>
  );
};

interface DashboardProps {
  onViewTab: (tab: string) => void;
  unreadCount: number;
  isBellAnimated: boolean;
  onOpenBellDrawer: () => void;
}

const Dashboard: React.FC<DashboardProps> = ({ onViewTab, unreadCount, isBellAnimated, onOpenBellDrawer }) => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentJobs, setRecentJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [statsError, setStatsError] = useState(false);
  const [timeRange, setTimeRange] = useState("week");

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        setStatsError(false);
        const [statsRes, jobsRes] = await Promise.all([
          getDashboardStats(timeRange),
          getJobs()
        ]);
        if (statsRes && statsRes.data) {
          setStats(statsRes.data);
        }
        if (jobsRes && jobsRes.data) {
          setRecentJobs(jobsRes.data.slice(0, 5));
        }
      } catch (err) {
        console.error("Dashboard error loading data:", err);
        setStatsError(true);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [timeRange]);

  if (statsError) {
    return (
      <div style={styles.opsDashboard}>
        <div style={{ padding: "2rem", textAlign: "center", color: "#ef4444" }}>
          <strong>Failed to load dashboard data.</strong> Please ensure the backend server is running and refresh the page.
        </div>
      </div>
    );
  }

  if (loading || stats === null) {
    return <LoadingSpinner message="Assembling Operations Center Dashboard..." fullPage={true} />;
  }

  const pendingCount = stats.jobs.pending;
  const activeCount = stats.jobs.active;
  const inProgressCount = stats.jobs.in_progress;
  const completedCount = stats.jobs.completed;
  const totalJobsCount = stats.jobs.total;

  const activePct = totalJobsCount > 0 ? parseFloat(((activeCount / totalJobsCount) * 100).toFixed(1)) : 0;
  const inProgressPct = totalJobsCount > 0 ? parseFloat(((inProgressCount / totalJobsCount) * 100).toFixed(1)) : 0;
  const completedPct = totalJobsCount > 0 ? parseFloat(((completedCount / totalJobsCount) * 100).toFixed(1)) : 0;
  const pendingPct = totalJobsCount > 0 ? parseFloat(((pendingCount / totalJobsCount) * 100).toFixed(1)) : 0;

  const techAvailable = stats.technicians.available;
  const techBusy = stats.technicians.busy;
  const techBreak = stats.technicians.break;
  const techOffline = stats.technicians.offline;
  const totalTechs = techAvailable + techBusy + techBreak + techOffline;

  const availablePct = totalTechs > 0 ? parseFloat(((techAvailable / totalTechs) * 100).toFixed(1)) : 0;
  const busyPct = totalTechs > 0 ? parseFloat(((techBusy / totalTechs) * 100).toFixed(1)) : 0;
  const breakPct = totalTechs > 0 ? parseFloat(((techBreak / totalTechs) * 100).toFixed(1)) : 0;
  const offlinePct = totalTechs > 0 ? parseFloat(((techOffline / totalTechs) * 100).toFixed(1)) : 0;

  const hvacCount = stats.categories.hvac;
  const electricalCount = stats.categories.electrical;
  const plumbingCount = stats.categories.plumbing;
  const mechanicalCount = stats.categories.mechanical;
  const otherCount = stats.categories.other;
  const totalCategories = hvacCount + electricalCount + plumbingCount + mechanicalCount + otherCount;

  const hvacPct = totalCategories > 0 ? parseFloat(((hvacCount / totalCategories) * 100).toFixed(1)) : 0;
  const electricalPct = totalCategories > 0 ? parseFloat(((electricalCount / totalCategories) * 100).toFixed(1)) : 0;
  const plumbingPct = totalCategories > 0 ? parseFloat(((plumbingCount / totalCategories) * 100).toFixed(1)) : 0;
  const mechanicalPct = totalCategories > 0 ? parseFloat(((mechanicalCount / totalCategories) * 100).toFixed(1)) : 0;
  const otherPct = totalCategories > 0 ? parseFloat(((otherCount / totalCategories) * 100).toFixed(1)) : 0;

  return (
    <div style={styles.opsDashboard}>
      <style>{localCss}</style>

      {/* ── Header ── */}
      <header className="dashboard-header-responsive" style={styles.dashboardHeaderCard}>
        <div style={styles.headerGreetingArea}>
          <h1 style={styles.headerWelcomeTitle}>Welcome back! </h1>
          <p style={styles.headerWelcomeSubtitle}>Here's what's happening with your field operations today.</p>
        </div>

        <div className="header-controls-responsive" style={styles.headerControlsArea}>
          <div style={styles.dropdownCalendarWrap}>
            <Calendar size={14} style={styles.dropdownCalendarIcon} />
            <select
              className="dropdown-this-week-style"
              style={styles.dropdownThisWeek}
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value)}
            >
              <option value="week">This Week</option>
              <option value="month">This Month</option>
              <option value="all">All Time</option>
            </select>
          </div>

          <NotificationBell
            unreadCount={unreadCount}
            onClick={onOpenBellDrawer}
            isAnimated={isBellAnimated}
          />
        </div>
      </header>

      {/* ── Metrics Cards Row ── */}
      <div className="metrics-cards-grid-responsive" style={styles.metricsCardsGrid}>
        {/* Card 1: Total Jobs */}
        <div
          role="button"
          tabIndex={0}
          className="metric-new-card-style"
          style={styles.metricCardNew}
          onClick={() => onViewTab("jobs")}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              onViewTab("jobs");
            }
          }}
        >
          {/* Base track line */}
          <div style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: "3px",
            background: "#F1F5F9",
            borderTopLeftRadius: "10px",
            borderTopRightRadius: "10px"
          }} />
          {/* Colored accent line with left-to-right hover scale animation */}
          <div className="metric-accent-bar" style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: "3px",
            borderTopLeftRadius: "10px",
            borderTopRightRadius: "10px",
            background: "#10B981"
          }} />
          <div style={styles.metricCardContentNew}>
            <div style={{ ...styles.iconContainer, background: "#10B981" }}>
              <Briefcase size={16} color="#FFFFFF" />
            </div>
            <div style={styles.metricDetailsNew}>
              <span style={styles.metricLabelNew}>TOTAL JOBS</span>
              <h2 style={styles.metricValNew}>{totalJobsCount}</h2>
              <span style={styles.metricSubtextNew}>{activeCount} active • {completedCount} done</span>
            </div>
          </div>
        </div>

        {/* Card 2: Active Jobs */}
        <div
          role="button"
          tabIndex={0}
          className="metric-new-card-style"
          style={styles.metricCardNew}
          onClick={() => onViewTab("planning")}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              onViewTab("planning");
            }
          }}
        >
          {/* Base track line */}
          <div style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: "3px",
            background: "#F1F5F9",
            borderTopLeftRadius: "10px",
            borderTopRightRadius: "10px"
          }} />
          {/* Colored accent line with left-to-right hover scale animation */}
          <div className="metric-accent-bar" style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: "3px",
            borderTopLeftRadius: "10px",
            borderTopRightRadius: "10px",
            background: "#3B82F6"
          }} />
          <div style={styles.metricCardContentNew}>
            <div style={{ ...styles.iconContainer, background: "#3B82F6" }}>
              <User size={16} color="#FFFFFF" />
            </div>
            <div style={styles.metricDetailsNew}>
              <span style={styles.metricLabelNew}>ACTIVE JOBS</span>
              <h2 style={styles.metricValNew}>{activeCount}</h2>
              <span style={styles.metricSubtextNew}>{activePct}% of total</span>
            </div>
          </div>
        </div>

        {/* Card 3: In Progress */}
        <div
          role="button"
          tabIndex={0}
          className="metric-new-card-style"
          style={styles.metricCardNew}
          onClick={() => onViewTab("planning")}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              onViewTab("planning");
            }
          }}
        >
          {/* Base track line */}
          <div style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: "3px",
            background: "#F1F5F9",
            borderTopLeftRadius: "10px",
            borderTopRightRadius: "10px"
          }} />
          {/* Colored accent line with left-to-right hover scale animation */}
          <div className="metric-accent-bar" style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: "3px",
            borderTopLeftRadius: "10px",
            borderTopRightRadius: "10px",
            background: "#F59E0B"
          }} />
          <div style={styles.metricCardContentNew}>
            <div style={{ ...styles.iconContainer, background: "#F59E0B" }}>
              <Clock size={16} color="#FFFFFF" />
            </div>
            <div style={styles.metricDetailsNew}>
              <span style={styles.metricLabelNew}>IN PROGRESS</span>
              <h2 style={styles.metricValNew}>{inProgressCount}</h2>
              <span style={styles.metricSubtextNew}>{inProgressPct}% of total</span>
            </div>
          </div>
        </div>

        {/* Card 4: Completed */}
        <div
          role="button"
          tabIndex={0}
          className="metric-new-card-style"
          style={styles.metricCardNew}
          onClick={() => onViewTab("techboard")}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              onViewTab("techboard");
            }
          }}
        >
          {/* Base track line */}
          <div style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: "3px",
            background: "#F1F5F9",
            borderTopLeftRadius: "10px",
            borderTopRightRadius: "10px"
          }} />
          {/* Colored accent line with left-to-right hover scale animation */}
          <div className="metric-accent-bar" style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: "3px",
            borderTopLeftRadius: "10px",
            borderTopRightRadius: "10px",
            background: "#8B5CF6"
          }} />
          <div style={styles.metricCardContentNew}>
            <div style={{ ...styles.iconContainer, background: "#8B5CF6" }}>
              <CheckCircle size={16} color="#FFFFFF" />
            </div>
            <div style={styles.metricDetailsNew}>
              <span style={styles.metricLabelNew}>COMPLETED</span>
              <h2 style={styles.metricValNew}>{completedCount}</h2>
              <span style={styles.metricSubtextNew}>{completedPct}% of total</span>
            </div>
          </div>
        </div>

        {/* Card 5: Pending */}
        <div
          role="button"
          tabIndex={0}
          className="metric-new-card-style"
          style={styles.metricCardNew}
          onClick={() => onViewTab("planning")}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              onViewTab("planning");
            }
          }}
        >
          {/* Base track line */}
          <div style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: "3px",
            background: "#F1F5F9",
            borderTopLeftRadius: "10px",
            borderTopRightRadius: "10px"
          }} />
          {/* Colored accent line with left-to-right hover scale animation */}
          <div className="metric-accent-bar" style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: "3px",
            borderTopLeftRadius: "10px",
            borderTopRightRadius: "10px",
            background: "#06B6D4"
          }} />
          <div style={styles.metricCardContentNew}>
            <div style={{ ...styles.iconContainer, background: "#06B6D4" }}>
              <AlertCircle size={16} color="#FFFFFF" />
            </div>
            <div style={styles.metricDetailsNew}>
              <span style={styles.metricLabelNew}>UNASSIGNED</span>
              <h2 style={styles.metricValNew}>{pendingCount}</h2>
              <span style={styles.metricSubtextNew}>{pendingPct}% of total</span>
            </div>
          </div>
        </div>
      </div>

      {/* ── Main Content Cards ── */}
      <div className="content-cards-grid-responsive" style={styles.contentCardsGrid}>
        {/* Card A: Jobs Overview */}
        <div style={styles.opsCard}>
          <div style={styles.opsCardHeader}>
            <h3 style={styles.opsCardHeaderH3}>JOBS OVERVIEW</h3>
            <div style={styles.dropdownCalendarWrap}>
              <select
                style={styles.dropdownSmall}
                value={timeRange}
                onChange={(e) => setTimeRange(e.target.value)}
              >
                <option value="week">This Week</option>
                <option value="month">This Month</option>
                <option value="all">All Time</option>
              </select>
            </div>
          </div>
          <div className="body-jobs-overview-responsive" style={styles.bodyJobsOverview}>
            <div style={styles.jobsOverviewLabels}>
              <div style={styles.overviewRow}>
                <span style={{ ...styles.indicatorBadge, background: "#10B981" }}><User size={14} strokeWidth={2.5} /></span>
                <span style={styles.overviewLbl}>Active</span>
                <span style={styles.overviewNum}>{activeCount}</span>
                <span style={styles.overviewPct}>({activePct}%)</span>
              </div>
              <div style={styles.overviewRow}>
                <span style={{ ...styles.indicatorBadge, background: "#F97316" }}><Wrench size={14} strokeWidth={2.5} /></span>
                <span style={styles.overviewLbl}>In Progress</span>
                <span style={styles.overviewNum}>{inProgressCount}</span>
                <span style={styles.overviewPct}>({inProgressPct}%)</span>
              </div>
              <div style={{ ...styles.overviewRow, ...styles.overviewRow }}>
                <span style={{ ...styles.indicatorBadge, background: "#3B82F6" }}><Check size={14} strokeWidth={3} /></span>
                <span style={styles.overviewLbl}>Completed</span>
                <span style={styles.overviewNum}>{completedCount}</span>
                <span style={styles.overviewPct}>({completedPct}%)</span>
              </div>
              <div style={styles.overviewRow}>
                <span style={{ ...styles.indicatorBadge, background: "#64748B" }}><Clock size={14} strokeWidth={2.5} /></span>
                <span style={styles.overviewLbl}>Unassigned</span>
                <span style={styles.overviewNum}>{pendingCount}</span>
                <span style={styles.overviewPct}>({pendingPct}%)</span>
              </div>
            </div>

            {/* Hand-crafted 3D stacked layout layers diagram using Inline SVG */}
            <div style={styles.jobsOverviewDiagram}>
              <svg viewBox="38 8 124 168" width="100%" height="100%">
                <defs>
                  {/* Green Layer (Top) Gradients */}
                  <linearGradient id="grad-green-top" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#4CD964" />
                    <stop offset="100%" stopColor="#28C745" />
                  </linearGradient>

                  {/* Orange Layer Gradients */}
                  <linearGradient id="grad-orange-top" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#FF9F0A" />
                    <stop offset="100%" stopColor="#FF8A00" />
                  </linearGradient>

                  {/* Blue Layer Gradients */}
                  <linearGradient id="grad-blue-top" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#0084FF" />
                    <stop offset="100%" stopColor="#0062FF" />
                  </linearGradient>

                  {/* Gray Layer (Bottom) Gradients */}
                  <linearGradient id="grad-gray-top" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stopColor="#8E8E93" />
                    <stop offset="100%" stopColor="#7A7A7F" />
                  </linearGradient>
                </defs>

                {/* Layer 4: Pending (Gray/Bottom) */}
                <g className="diagram-group-style" transform="translate(0, 96)">
                  {/* Side extrusion */}
                  <path d="M 50 35 Q 40 40, 50 45 L 90 65 Q 100 70, 110 65 L 150 45 Q 160 40, 150 35 L 150 47 Q 160 52, 150 57 L 110 77 Q 100 82, 90 77 L 50 57 Q 40 52, 50 47 Z" fill="#5C5C60" />
                  {/* Top Face */}
                  <path d="M 90 15 Q 100 10, 110 15 L 150 35 Q 160 40, 150 45 L 110 65 Q 100 70, 90 65 L 50 45 Q 40 40, 50 35 Z" fill="url(#grad-gray-top)" />
                </g>

                {/* Layer 3: Completed (Blue) */}
                <g className="diagram-group-style" transform="translate(0, 64)">
                  {/* Side extrusion */}
                  <path d="M 50 35 Q 40 40, 50 45 L 90 65 Q 100 70, 110 65 L 150 45 Q 160 40, 150 35 L 150 47 Q 160 52, 150 57 L 110 77 Q 100 82, 90 77 L 50 57 Q 40 52, 50 47 Z" fill="#0051C7" />
                  {/* Top Face */}
                  <path d="M 90 15 Q 100 10, 110 15 L 150 35 Q 160 40, 150 45 L 110 65 Q 100 70, 90 65 L 50 45 Q 40 40, 50 35 Z" fill="url(#grad-blue-top)" />
                </g>

                {/* Layer 2: In Progress (Orange) */}
                <g className="diagram-group-style" transform="translate(0, 32)">
                  {/* Side extrusion */}
                  <path d="M 50 35 Q 40 40, 50 45 L 90 65 Q 100 70, 110 65 L 150 45 Q 160 40, 150 35 L 150 47 Q 160 52, 150 57 L 110 77 Q 100 82, 90 77 L 50 57 Q 40 52, 50 47 Z" fill="#D95300" />
                  {/* Top Face */}
                  <path d="M 90 15 Q 100 10, 110 15 L 150 35 Q 160 40, 150 45 L 110 65 Q 100 70, 90 65 L 50 45 Q 40 40, 50 35 Z" fill="url(#grad-orange-top)" />
                </g>

                {/* Layer 1: Active (Green/Top) */}
                <g className="diagram-group-style" transform="translate(0, 0)">
                  {/* Side extrusion */}
                  <path d="M 50 35 Q 40 40, 50 45 L 90 65 Q 100 70, 110 65 L 150 45 Q 160 40, 150 35 L 150 47 Q 160 52, 150 57 L 110 77 Q 100 82, 90 77 L 50 57 Q 40 52, 50 47 Z" fill="#21A139" />
                  {/* Top Face */}
                  <path d="M 90 15 Q 100 10, 110 15 L 150 35 Q 160 40, 150 45 L 110 65 Q 100 70, 90 65 L 50 45 Q 40 40, 50 35 Z" fill="url(#grad-green-top)" />
                </g>
              </svg>
            </div>
          </div>
          <div className="footer-green" style={styles.opsCardFooter}>
            <span style={styles.footerStat}>
              <TrendingUp size={16} style={styles.footerIconGreen} /> 12% increase in active jobs vs last week
            </span>
            <button className="footer-link-btn-style" style={{ ...styles.footerLinkBtn, color: "#15803D" }} onClick={() => onViewTab("jobs")}>View Report →</button>
          </div>
        </div>

        {/* Card B: Technician Availability */}
        <div style={styles.opsCard}>
          <div style={styles.opsCardHeader}>
            <h3 style={styles.opsCardHeaderH3}>TECHNICIAN AVAILABILITY</h3>
            <select
              style={styles.dropdownSmall}
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value)}
            >
              <option value="week">This Week</option>
              <option value="month">This Month</option>
              <option value="all">All Time</option>
            </select>
          </div>
          <div className="gauges-flex-row-responsive" style={{ ...styles.opsCardBody, ...styles.bodyTechAvailability }}>
            {/* Circle Gauges */}
            <div className="gauges-flex-row-responsive" style={styles.gaugesFlexRow}>
              <AnimatedGauge
                percentage={availablePct}
                count={techAvailable}
                label="Available"
                icon={User}
                color="#10B981"
                textColor="#10B981"
              />
              <AnimatedGauge
                percentage={busyPct}
                count={techBusy}
                label="On Job / Busy"
                icon={Users}
                color="#F97316"
                textColor="#F97316"
              />
              <AnimatedGauge
                percentage={breakPct}
                count={techBreak}
                label="Break"
                icon={Coffee}
                color="#8B5CF6"
                textColor="#8B5CF6"
              />
              <AnimatedGauge
                percentage={offlinePct}
                count={techOffline}
                label="Offline"
                icon={MinusCircle}
                color="#64748B"
                textColor="#64748B"
              />
            </div>
          </div>
          <div className="footer-blue" style={styles.opsCardFooter}>
            <div style={styles.footerStatContainer}>
              <Users size={18} style={styles.footerIconBlue} />
              <div style={styles.footerStatTextWrap}>
                <span style={styles.footerStatPrimary}>{techAvailable} technicians available</span>
                <span style={styles.footerStatSecondary}>ready to assign</span>
              </div>
            </div>
            <button className="footer-link-btn-style" style={{ ...styles.footerLinkBtn, color: "#2563EB" }} onClick={() => onViewTab("techboard")}>
              View Report →
            </button>
          </div>
        </div>

        {/* Card C: Service Category Split */}
        <div style={styles.opsCard}>
          <div style={styles.opsCardHeader}>
            <h3 style={styles.opsCardHeaderH3}>SERVICE CATEGORY SPLIT</h3>
            <select
              style={styles.dropdownSmall}
              value={timeRange}
              onChange={(e) => setTimeRange(e.target.value)}
            >
              <option value="week">This Week</option>
              <option value="month">This Month</option>
              <option value="all">All Time</option>
            </select>
          </div>
          <div style={{ ...styles.opsCardBody, ...styles.bodyServiceSplit }}>
            <div style={styles.categoryBarsList}>
              {/* Category 1: HVAC */}
              <div style={styles.categoryBarRow}>
                <span style={{ ...styles.categoryTagBadge, background: "#02B075" }}><Snowflake size={11} /></span>
                <span style={styles.categoryLabel}>HVAC</span>
                <SegmentedProgressBar percentage={hvacPct} colorClass="fill-hvac" />
                <strong style={styles.categoryValue}>{hvacCount} ({hvacPct}%)</strong>
              </div>

              {/* Category 2: Electrical */}
              <div style={styles.categoryBarRow}>
                <span style={{ ...styles.categoryTagBadge, background: "#2F80ED" }}><Zap size={11} /></span>
                <span style={styles.categoryLabel}>Electrical</span>
                <SegmentedProgressBar percentage={electricalPct} colorClass="fill-elec" />
                <strong style={styles.categoryValue}>{electricalCount} ({electricalPct}%)</strong>
              </div>

              {/* Category 3: Plumbing */}
              <div style={styles.categoryBarRow}>
                <span style={{ ...styles.categoryTagBadge, background: "#F2994A" }}><Droplet size={11} /></span>
                <span style={styles.categoryLabel}>Plumbing</span>
                <SegmentedProgressBar percentage={plumbingPct} colorClass="fill-plumb" />
                <strong style={styles.categoryValue}>{plumbingCount} ({plumbingPct}%)</strong>
              </div>

              {/* Category 4: Mechanical */}
              <div style={styles.categoryBarRow}>
                <span style={{ ...styles.categoryTagBadge, background: "#9B51E0" }}><Wrench size={11} /></span>
                <span style={styles.categoryLabel}>Mechanical</span>
                <SegmentedProgressBar percentage={mechanicalPct} colorClass="fill-mech" />
                <strong style={styles.categoryValue}>{mechanicalCount} ({mechanicalPct}%)</strong>
              </div>

              {/* Category 5: Other */}
              <div style={styles.categoryBarRow}>
                <span style={{ ...styles.categoryTagBadge, background: "#828282" }}><MoreHorizontal size={11} /></span>
                <span style={styles.categoryLabel}>Other</span>
                <SegmentedProgressBar percentage={otherPct} colorClass="fill-other" />
                <strong style={styles.categoryValue}>{otherCount} ({otherPct}%)</strong>
              </div>
            </div>
          </div>
          <div className="footer-purple" style={styles.opsCardFooter}>
            <div style={styles.footerStatContainer}>
              <BarChart size={18} style={styles.footerIconPurple} />
              <div style={styles.footerStatTextWrap}>
                <span style={styles.footerStatPrimaryPurple}>
                  {(() => {
                    const cats = [
                      { name: "HVAC", count: hvacCount },
                      { name: "Electrical", count: electricalCount },
                      { name: "Plumbing", count: plumbingCount },
                      { name: "Mechanical", count: mechanicalCount },
                      { name: "Other", count: otherCount },
                    ];
                    const top = cats.reduce((a, b) => a.count >= b.count ? a : b);
                    return `${top.name} is highest`;
                  })()}
                </span>
                <span style={styles.footerStatSecondary}>
                  {(() => {
                    const cats = [
                      { name: "HVAC", count: hvacCount, pct: hvacPct },
                      { name: "Electrical", count: electricalCount, pct: electricalPct },
                      { name: "Plumbing", count: plumbingCount, pct: plumbingPct },
                      { name: "Mechanical", count: mechanicalCount, pct: mechanicalPct },
                      { name: "Other", count: otherCount, pct: otherPct },
                    ];
                    const top = cats.reduce((a, b) => a.count >= b.count ? a : b);
                    return `${top.pct}% of total jobs`;
                  })()}
                </span>
              </div>
            </div>
            <button className="footer-link-btn-style" style={{ ...styles.footerLinkBtn, color: "#7C3AED" }} onClick={() => onViewTab("jobs")}>
              View Report →
            </button>
          </div>
        </div>
      </div>

      {/* ── Recent Jobs Card ── */}
      <div style={styles.cardRecentJobs}>
        <div style={styles.opsCardHeader}>
          <h3 style={styles.opsCardHeaderH3}>RECENT JOBS</h3>
          <button
            style={{ ...styles.dropdownSmall, padding: "5px 12px", appearance: "none", backgroundImage: "none" }}
            onClick={() => onViewTab("jobs")}
          >
            View All
          </button>
        </div>
        <div style={styles.recentJobsTableContainer}>
          <table style={styles.recentJobsTable}>
            <thead>
              <tr>
                <th style={styles.recentJobsTableTh}>ID</th>
                <th style={styles.recentJobsTableTh}>Customer / Job Name</th>
                <th style={styles.recentJobsTableTh}>Location</th>
                <th style={styles.recentJobsTableTh}>Service Type</th>
                <th style={styles.recentJobsTableTh}>Priority</th>
                <th style={styles.recentJobsTableTh}>Status</th>
                <th style={styles.recentJobsTableTh}>Preferred Date</th>
              </tr>
            </thead>
            <tbody>
              {recentJobs.length === 0 ? (
                <tr>
                  <td colSpan={7} style={styles.recentJobsTableTd}>
                    <EmptyState
                      title="No recent jobs found"
                      description="All clear! There are currently no new or unassigned jobs."
                    />
                  </td>
                </tr>
              ) : (
                recentJobs.map((job) => (
                  <tr key={job.id} className="recent-jobs-table-row">
                    <td style={{ ...styles.recentJobsTableTd, ...styles.jobIdPill }}>#{job.id}</td>
                    <td style={{ ...styles.recentJobsTableTd, fontWeight: "700", color: "#2F4F3E" }}>
                      <div>{job.customer_name}</div>
                      {job.issue_description && (
                        <div style={{ fontSize: "11px", color: "#6B7280", fontWeight: "400", marginTop: "2px" }}>
                          {job.issue_description}
                        </div>
                      )}
                    </td>
                    <td style={styles.recentJobsTableTd}>{job.location}</td>
                    <td style={styles.recentJobsTableTd}>{(job.service_type || "").replace(/_/g, " ")}</td>
                    <td style={styles.recentJobsTableTd}>
                      <span style={getPriorityStyle(job.priority)}>
                        {(job.priority || "UNKNOWN").toUpperCase()}
                      </span>
                    </td>
                    <td style={styles.recentJobsTableTd}>
                      <span style={getStatusStyle(job.status)}>
                        {formatStatus(job.status)}
                      </span>
                    </td>
                    <td style={styles.recentJobsTableTd}>{job.preferred_service_date || "—"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="footer-green" style={styles.opsCardFooter}>
          <span style={styles.footerStat}>
            <TrendingUp size={16} style={styles.footerIconGreen} /> Total pending: {stats.jobs.pending} · active: {stats.jobs.active}
          </span>
          <button className="footer-link-btn-style" style={{ ...styles.footerLinkBtn, color: "#15803D" }} onClick={() => onViewTab("jobs")}>
            Manage Jobs →
          </button>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
