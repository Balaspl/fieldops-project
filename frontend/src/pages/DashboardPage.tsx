import React, { useEffect, useState } from "react";
import useAuthStore from "../store/authStore";
import dashboardBanner from "../assets/dashboard-banner.jpeg";
import { getDashboardStats, getJobs } from "../services/planningService";
import LoadingSpinner from "../components/ui/LoadingSpinner";
import {
  Briefcase,
  Search,
  LayoutDashboard,
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
  Check,
  Wifi,
  Hammer,
  ShieldCheck,
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
  sla_deadline?: string;
  is_breached?: boolean;
}

interface DashboardStats {
  job_cards: {
    total: number;
    unassigned: number;
    accepted: number;
    rejected: number;
    en_route: number;
    in_progress: number;
    completed: number;
  };

  service_technicians: Record<string, number>;

  jobs: {
    pending: number;
    active: number;
    in_progress: number;
    completed: number;
    cancelled: number;
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
    padding: "16px",
    display: "flex",
    flexDirection: "column",
    gap: "18px",
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
    gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
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
  gridTemplateColumns: "1fr",
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
    fontSize: "12px",
    fontWeight: 700,
    color: "#334155",
    letterSpacing: "0.04em",
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
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
  gap: "12px",
  width: "100%",
} as React.CSSProperties,

  categoryBarRow: {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  fontSize: "12px",
  width: "100%",
  minWidth: 0,
  padding: "12px",
  background: "#F8FAFC",
  border: "1px solid #E5E7EB",
  borderRadius: "10px",
  boxSizing: "border-box",
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
    height: "100px",
    display: "flex",
    alignItems: "center",
    cursor: "pointer",
    background: "#FFFFFF",
    border: "1px solid #E2E8F0",
    borderRadius: "12px",
    boxShadow: "0 2px 8px rgba(15, 23, 42, 0.06)",
    overflow: "hidden",
    padding: "12px 14px",
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
    width: "46px",
    height: "46px",
    borderRadius: "10px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    boxShadow: "0 3px 8px rgba(0, 0, 0, 0.10)",
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
  fontSize: "11px",
  fontWeight: 600,
  color: "#64748B",
  letterSpacing: "0.5px",
  lineHeight: 1.4,
} as React.CSSProperties,

  metricValNew: {
  margin: 0,
  fontSize: "25px",
  fontWeight: 700,
  color: "#111827",
  lineHeight: 1.3,
} as React.CSSProperties,

  metricSubtextNew: {
  fontSize: "11px",
  color: "#64748B",
  lineHeight: 1.4,
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
  .payment-service-split-layout {
  grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
}

.service-category-tiles-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

@media (max-width: 1200px) {
  .payment-service-split-layout {
    grid-template-columns: minmax(0, 1fr) !important;
  }
}

@media (max-width: 700px) {
  .service-category-tiles-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
  }
}

@media (max-width: 420px) {
  .service-category-tiles-grid {
    grid-template-columns: minmax(0, 1fr) !important;
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

const isJobOverdue = (job: Job): boolean => {
  return job.is_breached === true;
};

const isEmergencyJob = (job: Job): boolean => {
  const priority = (job.priority || "").toUpperCase().trim();
  return priority === "CRITICAL" || priority === "P1";
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
  timeRange: string;
  onTimeRangeChange: (value: string) => void;
  unreadCount: number;
  isBellAnimated: boolean;
  onOpenBellDrawer: () => void;
}

  const Dashboard: React.FC<DashboardProps> = ({
  onViewTab,
  timeRange,
  onTimeRangeChange,
}) => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentJobs, setRecentJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [statsError, setStatsError] = useState(false);
  const user = useAuthStore((state) => state.user);
  const [paymentRange, setPaymentRange] = useState("year");
  const currentHour = new Date().getHours();

  const greeting =
    currentHour < 12
      ? "Good morning!"
      : currentHour < 17
        ? "Good afternoon!"
        : "Good evening!";

  const organizationName =
    user?.organization_name?.trim() || "your organization";
    useEffect(() => {
    let isMounted = true;

    // Load the dashboard data when the page opens
    // or when the selected date range changes.
    const fetchData = async () => {
      try {
        setLoading(true);
        setStatsError(false);

        const [statsRes, jobsRes] = await Promise.all([
          getDashboardStats(timeRange),
          getJobs(),
        ]);

        if (!isMounted) return;

        if (statsRes?.data) {
          setStats(statsRes.data);
        }

        if (jobsRes?.data) {
          setRecentJobs(jobsRes.data.slice(0, 5));
        }
      } catch (err) {
        console.error("Dashboard error loading data:", err);

        if (isMounted) {
          setStatsError(true);
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    // Refresh the job counts without showing the full-page
    // loading screen every time.
    const refreshStats = async () => {
      try {
        const statsRes = await getDashboardStats(timeRange);

        if (isMounted && statsRes?.data) {
          setStats(statsRes.data);
          setStatsError(false);
        }
      } catch (err) {
        console.error("Dashboard stats refresh failed:", err);
      }
    };

    void fetchData();

    const intervalId = window.setInterval(() => {
      void refreshStats();
    }, 15_000);

    const handleWindowFocus = () => {
      void refreshStats();
    };

    window.addEventListener("focus", handleWindowFocus);

    return () => {
      isMounted = false;
      window.clearInterval(intervalId);
      window.removeEventListener("focus", handleWindowFocus);
    };
  }, [timeRange]);

  if (statsError) {
    return (
      <div style={styles.opsDashboard}>
        <div
          style={{
            padding: "3rem 2rem",
            textAlign: "center",
            color: "#B91C1C",
            background: "#FFFFFF",
            border: "1px solid #FECACA",
            borderRadius: "12px",
            boxShadow: "0 2px 6px rgba(47, 79, 62, 0.03)",
          }}
        >
          <AlertCircle
            size={32}
            style={{ marginBottom: "10px" }}
          />

          <div
            style={{
              fontSize: "15px",
              fontWeight: 700,
              marginBottom: "6px",
            }}
          >
            Failed to load dashboard data
          </div>

          <div
            style={{
              fontSize: "12px",
              color: "#64748B",
              marginBottom: "16px",
            }}
          >
            We couldn't retrieve the latest dashboard information.
            Please try again.
          </div>

          <button
            type="button"
            onClick={() => {
              setStatsError(false);
              setLoading(true);

              Promise.all([
                getDashboardStats(timeRange),
                getJobs(),
              ])
                .then(([statsRes, jobsRes]) => {
                  if (statsRes && statsRes.data) {
                    setStats(statsRes.data);
                  }

                  if (jobsRes && jobsRes.data) {
                    setRecentJobs(jobsRes.data.slice(0, 5));
                  }
                })
                .catch((err) => {
                  console.error("Dashboard error loading data:", err);
                  setStatsError(true);
                })
                .finally(() => {
                  setLoading(false);
                });
            }}
            style={{
              padding: "8px 16px",
              border: "none",
              borderRadius: "7px",
              background: "#2F4F3E",
              color: "#FFFFFF",
              fontSize: "12px",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            Retry
          </button>
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
  const cancelledCount = stats.jobs.cancelled;
  const totalJobsCount = stats.jobs.total;

  const activePct = totalJobsCount > 0 ? parseFloat(((activeCount / totalJobsCount) * 100).toFixed(1)) : 0;
  const inProgressPct = totalJobsCount > 0 ? parseFloat(((inProgressCount / totalJobsCount) * 100).toFixed(1)) : 0;
  const completedPct = totalJobsCount > 0 ? parseFloat(((completedCount / totalJobsCount) * 100).toFixed(1)) : 0;
  const pendingPct = totalJobsCount > 0 ? parseFloat(((pendingCount / totalJobsCount) * 100).toFixed(1)) : 0;
  const cancelledPct = totalJobsCount > 0 ? parseFloat(((cancelledCount / totalJobsCount) * 100).toFixed(1)) : 0;

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
      <div
        style={{
          position: "relative",
          width: "100%",
          marginTop: "0px",
          height: "clamp(150px, 12vw, 180px)",
          borderRadius: "12px",
          overflow: "hidden",
          background: "#064E3B",
          flexShrink: 0,
        }}
      >
        <img
          src={dashboardBanner}
          alt="FieldOps technicians and service vehicle"
          style={{
            width: "100%",
            height: "100%",
            display: "block",
            objectFit: "cover",
            objectPosition: "center 55%",
          }}
        />

        {/* Dark overlay for readable text */}
        <div
          aria-hidden="true"
          style={{
            position: "absolute",
            inset: 0,
            background:
              "linear-gradient(90deg, rgba(3,35,26,0.88) 0%, rgba(3,35,26,0.55) 42%, rgba(3,35,26,0.05) 100%)",
            zIndex: 1,
          }}
        />

        {/* Greeting and Organization Name */}
        <div
          style={{
            position: "absolute",
            left: "clamp(18px, 4vw, 56px)",
            bottom: "clamp(35px, 5vw, 55px)",
            zIndex: 2,
            maxWidth: "72%",
            color: "#FFFFFF",
          }}
        >
          <p
  style={{
    margin: "0 0 8px",
    fontSize: "clamp(14px, 1.3vw, 18px)",
    fontWeight: 600,
    color: "#D1FAE5",
  }}
>
  {greeting}
</p>
          <h1
            style={{
              margin: 0,
              fontSize: "clamp(22px, 2.5vw, 32px)",
              lineHeight: 1.2,
              fontWeight: 800,
              color: "#FFFFFF",
            }}
          >
            Welcome {organizationName}
          </h1>

          <p
            style={{
              margin: "8px 0 0",
              fontSize: "clamp(12px, 1.1vw, 14px)",
              color: "rgba(255,255,255,0.9)",
            }}
          >
          </p>
        </div>

        {/* Existing Date Selector and Notification Bell */}
       
       
      </div>

      {/* ── Metrics Cards Row ── */}
      <div
        className="metrics-cards-grid-responsive"
        style={styles.metricsCardsGrid}
      >
        {[
          {
            key: "total",
            label: "Total Jobs",
            value: stats.job_cards.total,
            subtext: "All jobs in this organization",
            color: "#10B981",
            icon: Briefcase,
            trend: "M2 28 L12 22 L22 25 L32 15 L42 20 L52 9 L62 15 L72 4",
            onClick: () => onViewTab("jobs"),
          },
          {
            key: "unassigned",
            label: "Unassigned",
            value: stats.job_cards.unassigned,
            subtext: "Created but not assigned",
            color: "#EF4444",
            icon: AlertCircle,
            trend: "M2 25 L12 21 L22 26 L32 16 L42 22 L52 11 L62 16 L72 4",
            onClick: () => onViewTab("planning"),
          },
          {
            key: "accepted",
            label: "Accepted",
            value: stats.job_cards.accepted,
            subtext: "Accepted, not yet en route",
            color: "#3B82F6",
            icon: CheckCircle,
            trend: "M2 27 L12 22 L22 24 L32 15 L42 20 L52 10 L62 15 L72 4",
            onClick: undefined,
          },
          {
            key: "rejected",
            label: "Rejected",
            value: stats.job_cards.rejected,
            subtext: "Rejected by technician",
            color: "#F97316",
            icon: MinusCircle,
            trend: "M2 28 L12 22 L22 24 L32 17 L42 20 L52 13 L62 14 L72 5",
            onClick: undefined,
          },
          {
            key: "en-route",
            label: "En Route",
            value: stats.job_cards.en_route,
            subtext: "Technician travelling to customer",
            color: "#9333EA",
            icon: TrendingUp,
            trend: "M2 29 L12 23 L22 25 L32 12 L42 19 L52 8 L62 14 L72 3",
            onClick: undefined,
          },
          {
            key: "in-progress",
            label: "In Progress",
            value: stats.job_cards.in_progress,
            subtext: "On site or work ongoing",
            color: "#F59E0B",
            icon: Clock,
            trend: "M2 28 L12 21 L22 24 L32 15 L42 20 L52 8 L62 13 L72 4",
            onClick: () => onViewTab("planning"),
          },
          {
            key: "completed",
            label: "Completed",
            value: stats.job_cards.completed,
            subtext: "Work completion recorded",
            color: "#10B981",
            icon: CheckCircle,
            trend: "M2 27 L12 23 L22 25 L32 14 L42 19 L52 9 L62 14 L72 4",
            onClick: () => onViewTab("techboard"),
          },
        ].map((metric) => {
          const MetricIcon = metric.icon;

          return (
            <div
              key={metric.key}
              role={metric.onClick ? "button" : undefined}
              tabIndex={metric.onClick ? 0 : -1}
              aria-label={metric.label}
              className="metric-new-card-style"
              style={{
                ...styles.metricCardNew,
                cursor: metric.onClick ? "pointer" : "default",
              }}
              onClick={metric.onClick}
              onKeyDown={(event) => {
                if (
                  metric.onClick &&
                  (event.key === "Enter" || event.key === " ")
                ) {
                  event.preventDefault();
                  metric.onClick();
                }
              }}
            >
              {/* Base track line */}
              <div
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  right: 0,
                  height: "3px",
                  background: "#F1F5F9",
                  borderTopLeftRadius: "10px",
                  borderTopRightRadius: "10px",
                }}
              />

              {/* Colored accent line */}
              <div
                className="metric-accent-bar"
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  right: 0,
                  height: "3px",
                  background: metric.color,
                  borderTopLeftRadius: "10px",
                  borderTopRightRadius: "10px",
                }}
              />

              <div style={styles.metricCardContentNew}>
                {/* Icon */}
                <div
                  style={{
                    ...styles.iconContainer,
                    background: metric.color,
                  }}
                >
                  <MetricIcon size={20} color="#FFFFFF" />
                </div>

                {/* Label and value */}
                <div style={styles.metricDetailsNew}>
                  <span style={styles.metricLabelNew}>
                    {metric.label}
                  </span>

                  <h2 style={styles.metricValNew}>
                    {metric.value}
                  </h2>

                  <span style={styles.metricSubtextNew}>
                    {metric.subtext}
                  </span>
                </div>

                {/* Decorative trend line */}
                <svg
                  width="64"
                  height="36"
                  viewBox="0 0 76 34"
                  aria-hidden="true"
                  style={{ flexShrink: 0 }}
                >
                  <path
                    d={metric.trend}
                    fill="none"
                    stroke={metric.color}
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Main Content Cards ── */}
      <div className="content-cards-grid-responsive" style={styles.contentCardsGrid}>
        {/* Card A: Jobs Overview */}
        <div style={{ ...styles.opsCard, display: "none" }}>
          <div style={styles.opsCardHeader}>
            <h3 style={styles.opsCardHeaderH3}>JOBS OVERVIEW</h3>
            <div
  style={{
    ...styles.dropdownCalendarWrap,
    marginRight: "10px",
  }}
>
              <select
                style={styles.dropdownSmall}
                value={timeRange}
                onChange={(e) => onTimeRangeChange(e.target.value)}
              >
                <option value="week">This Week</option>
                <option value="month">This Month</option>
                <option value="all">All Time</option>
              </select>
            </div>
          </div>
          <div className="body-jobs-overview-responsive" style={styles.bodyJobsOverview}>
            {totalJobsCount === 0 ? (
              <div
                style={{
                  width: "100%",
                  minHeight: "150px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <EmptyState
                  title="No jobs available"
                  description="There are currently no jobs to display for the selected time range."
                />
              </div>
            ) : (
              <>
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

              <div style={styles.overviewRow}>
                <span style={{ ...styles.indicatorBadge, background: "#EF4444" }}>
                  <MinusCircle size={14} strokeWidth={2.5} />
                </span>
                <span style={styles.overviewLbl}>Cancelled</span>
                <span style={styles.overviewNum}>{cancelledCount}</span>
                <span style={styles.overviewPct}>({cancelledPct}%)</span>
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
            </>
            )}
          </div>
          
          <div className="footer-green" style={styles.opsCardFooter}>
            <span style={styles.footerStat}>
              <TrendingUp size={16} style={styles.footerIconGreen} /> 12% increase in active jobs vs last week
            </span>
            <button className="footer-link-btn-style" style={{ ...styles.footerLinkBtn, color: "#15803D" }} onClick={() => onViewTab("jobs")}>View Report →</button>
          </div>
        </div>

        {/* Card B: Technician Availability */}
        <div style={{ ...styles.opsCard, display: "none" }}>
          <div style={styles.opsCardHeader}>
            <h3 style={styles.opsCardHeaderH3}>TECHNICIAN AVAILABILITY</h3>
            <select
              style={styles.dropdownSmall}
              value={timeRange}
              onChange={(e) => onTimeRangeChange(e.target.value)}
            >
              <option value="week">This Week</option>
              <option value="month">This Month</option>
              <option value="all">All Time</option>
            </select>
          </div>
          <div
            className="gauges-flex-row-responsive"
            style={{ ...styles.opsCardBody, ...styles.bodyTechAvailability }}
          >
            {totalTechs === 0 ? (
              <div
                style={{
                  width: "100%",
                  minHeight: "150px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <EmptyState
                  title="No technicians available"
                  description="There are currently no technician availability data to display."
                />
              </div>
            ) : (
              <div className="gauges-flex-row-responsive" style={styles.gaugesFlexRow}>
                {/* KEEP ALL FOUR AnimatedGauge COMPONENTS EXACTLY AS THEY ARE */}
                
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
            )}
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

{/* Payment Analytics + Service Categories */}
<div
  className="payment-service-split-layout"
  style={{
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: "22px",
    width: "100%",
    alignItems: "stretch",
  }}
>
  {/* LEFT: Monthly Payment Analytics — demo UI */}
  <div
    style={{
      ...styles.opsCard,
      height: "auto",
      minHeight: "370px",
    }}
  >
    <div style={styles.opsCardHeader}>
      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
        <BarChart size={20} color="#10B981" />
        <h3 style={styles.opsCardHeaderH3}>
          MONTHLY PAYMENT ANALYTICS
        </h3>
      </div>

      <select
        style={styles.dropdownSmall}
        value={paymentRange}
        onChange={(event) => setPaymentRange(event.target.value)}
        aria-label="Payment analytics date range"
      >
        <option value="year">This Year</option>
        <option value="lastYear">Last Year</option>
        <option value="all">All Time</option>
      </select>
    </div>

    <div style={{ padding: "14px 16px 14px", flex: 1 }}>
      <div style={{ fontSize: "10px", color: "#64748B", marginBottom: "8px" }}>
        DEMO DATA · AMOUNTS IN LAKHS (₹)
      </div>

      <div style={{ display: "flex", gap: "10px", height: "225px" }}>
        {/* Y-axis */}
        <div
          style={{
            width: "34px",
            flexShrink: 0,
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            fontSize: "10px",
            color: "#64748B",
            paddingBottom: "2px",
          }}
        >
          {["₹4L", "₹3L", "₹2L", "₹1L", "₹0"].map((label) => (
            <span key={label}>{label}</span>
          ))}
        </div>

        {/* Chart bars */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              height: "202px",
              display: "grid",
              gridTemplateColumns: "repeat(12, minmax(0, 1fr))",
              gap: "5px",
              alignItems: "stretch",
              borderBottom: "1px solid #CBD5E1",
              backgroundImage:
                "linear-gradient(to top, #E2E8F0 1px, transparent 1px)",
              backgroundSize: "100% 25%",
            }}
          >
            {[
              { month: "Jan", amount: 1.2 },
              { month: "Feb", amount: 1.6 },
              { month: "Mar", amount: 2.1 },
              { month: "Apr", amount: 1.8 },
              { month: "May", amount: 2.4 },
              { month: "Jun", amount: 2.9 },
              { month: "Jul", amount: 2.3 },
              { month: "Aug", amount: 2.7 },
              { month: "Sep", amount: 2.1 },
              { month: "Oct", amount: 2.2 },
              { month: "Nov", amount: null },
              { month: "Dec", amount: null },
            ].map((item, index) => {
              const barPercent =
                item.amount !== null
                  ? (item.amount / 4) * 100
                  : index === 10
                    ? 35
                    : 50;

              return (
                <div
                  key={item.month}
                  style={{
                    position: "relative",
                    minWidth: 0,
                    height: "100%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "flex-end",
                    flexDirection: "column",
                  }}
                >
                  {item.amount !== null && (
                    <span
                      style={{
                        position: "absolute",
                        bottom: `calc(${barPercent}% + 4px)`,
                        left: "50%",
                        transform: "translateX(-50%)",
                        fontSize: "9px",
                        fontWeight: 700,
                        color: "#334155",
                        whiteSpace: "nowrap",
                      }}
                    >
                      ₹{item.amount.toFixed(1)}L
                    </span>
                  )}

                  <div
                    style={{
                      width: "68%",
                      height: `${barPercent}%`,
                      borderRadius: "5px 5px 0 0",
                      background:
                        item.amount === null
                          ? "#E5E7EB"
                          : "linear-gradient(180deg, #43BE96 0%, #8AD7B9 100%)",
                    }}
                  />
                </div>
              );
            })}
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(12, minmax(0, 1fr))",
              gap: "5px",
              marginTop: "8px",
              textAlign: "center",
              fontSize: "10px",
              color: "#64748B",
            }}
          >
            {["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"].map((month) => (
              <span key={month}>{month}</span>
            ))}
          </div>
        </div>
      </div>

      <div
        style={{
          marginTop: "12px",
          paddingTop: "10px",
          borderTop: "1px solid #F1F5F9",
          fontSize: "10px",
          color: "#64748B",
        }}
      >
        Preview only · Payment backend will be connected later
      </div>
    </div>
  </div>

  {/* RIGHT: Service Categories — demo UI */}
  <div
    style={{
      ...styles.opsCard,
      height: "auto",
      minHeight: "370px",
    }}
  >
    <div style={styles.opsCardHeader}>
      <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
        <LayoutDashboard size={20} color="#10B981" />
        <h3 style={styles.opsCardHeaderH3}>
          SERVICE CATEGORIES (8)
        </h3>
      </div>
    </div>

    <div
  className="service-category-tiles-grid"
  style={{
    display: "grid",
    gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
    gap: "12px",
    padding: "14px",
    boxSizing: "border-box",
    width: "100%",
  }}
>
  {[
    {
      name: "HVAC Repair",
      icon: Snowflake,
      color: "#10B981",
      tint: "#ECFDF5",
    },
    {
      name: "Electrical",
      icon: Zap,
      color: "#F59E0B",
      tint: "#FFFBEB",
    },
    {
      name: "Plumbing",
      icon: Droplet,
      color: "#EF4444",
      tint: "#FEF2F2",
    },
    {
      name: "Network Support",
      icon: Wifi,
      color: "#0EA5E9",
      tint: "#F0F9FF",
    },
    {
      name: "General Maintenance",
      icon: Wrench,
      color: "#64748B",
      tint: "#F8FAFC",
    },
    {
      name: "Appliance Repair",
      icon: Briefcase,
      color: "#EC4899",
      tint: "#FDF2F8",
    },
    {
      name: "Roofing & Carpentry",
      icon: Hammer,
      color: "#647D8B",
      tint: "#F1F5F9",
    },
    {
      name: "CCTV & Security",
      icon: ShieldCheck,
      color: "#059669",
      tint: "#ECFDF5",
    },
  ].map((category) => {
    const CategoryIcon = category.icon;
    const technicianCount =
      stats.service_technicians?.[category.name] ?? 0;

    return (
      <div
        key={category.name}
        title={`${category.name}: ${technicianCount} technicians`}
        style={{
          minWidth: 0,
          minHeight: "112px",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          gap: "8px",
          padding: "10px",
          borderRadius: "10px",
          background: category.tint,
          border: "1px solid rgba(148, 163, 184, 0.12)",
          boxSizing: "border-box",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <div
            style={{
              width: "32px",
              height: "32px",
              minWidth: "32px",
              borderRadius: "8px",
              background: category.color,
              color: "#FFFFFF",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <CategoryIcon size={17} />
          </div>

          <span
            style={{
              minWidth: 0,
              fontSize: "12px",
              lineHeight: 1.3,
              color: "#334155",
              fontWeight: 600,
              overflowWrap: "anywhere",
            }}
          >
            {category.name}
          </span>
        </div>

        <div style={{ paddingLeft: "2px" }}>
          <strong
            style={{
              fontSize: "20px",
              color: "#0F172A",
            }}
          >
            {technicianCount}
          </strong>

          <div
            style={{
              fontSize: "10px",
              color: "#64748B",
              marginTop: "2px",
            }}
          >
            {technicianCount === 1
              ? "1 technician"
              : `${technicianCount} technicians`}
          </div>
        </div>
      </div>
    );
  })}
</div>
  </div>
</div>
</div>

    

      {/* ── Recent Jobs Card ── */}
      <div style={{ ...styles.cardRecentJobs, display: "none" }}>
        <div style={styles.opsCardHeader}>
          <h3 style={styles.opsCardHeaderH3}>RECENT JOBS</h3>
          <button
            style={{
              ...styles.dropdownSmall,
              padding: "5px 12px",
              appearance: "none",
              backgroundImage: "none",
            }}
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
                    <td
                      style={{
                        ...styles.recentJobsTableTd,
                        ...styles.jobIdPill,
                      }}
                    >
                      #{job.id}
                    </td>

                    <td
                      style={{
                        ...styles.recentJobsTableTd,
                        fontWeight: "700",
                        color: "#2F4F3E",
                      }}
                    >
                      <div>{job.customer_name}</div>

                      {job.issue_description && (
                        <div
                          style={{
                            fontSize: "11px",
                            color: "#6B7280",
                            fontWeight: "400",
                            marginTop: "2px",
                          }}
                        >
                          {job.issue_description}
                        </div>
                      )}
                    </td>

                    <td style={styles.recentJobsTableTd}>
                      {job.location}
                    </td>

                    <td style={styles.recentJobsTableTd}>
                      {(job.service_type || "").replace(/_/g, " ")}
                    </td>

                    <td style={styles.recentJobsTableTd}>
                      <span style={getPriorityStyle(job.priority)}>
                        {(job.priority || "UNKNOWN").toUpperCase()}
                      </span>

                      {isEmergencyJob(job) && (
                        <span
                          style={{
                            ...styles.statusBadge,
                            background: "#FEE2E2",
                            color: "#B91C1C",
                            marginLeft: "6px",
                            fontWeight: 700,
                          }}
                        >
                          EMERGENCY
                        </span>
                      )}
                    </td>

                    <td style={styles.recentJobsTableTd}>
                      <span style={getStatusStyle(job.status)}>
                        {formatStatus(job.status)}
                      </span>

                      {isJobOverdue(job) && (
                        <span
                          style={{
                            ...styles.statusBadge,
                            background: "#FEE2E2",
                            color: "#B91C1C",
                            marginLeft: "6px",
                            fontWeight: 700,
                          }}
                        >
                          OVERDUE
                        </span>
                      )}
                    </td>

                    <td style={styles.recentJobsTableTd}>
                      {job.preferred_service_date || "—"}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div
          className="footer-green"
          style={styles.opsCardFooter}
        >
          <span style={styles.footerStat}>
            <TrendingUp
              size={16}
              style={styles.footerIconGreen}
            />{" "}
           Total pending: {pendingCount} · active: {activeCount}
          </span>

          <button
            className="footer-link-btn-style"
            style={{
              ...styles.footerLinkBtn,
              color: "#15803D",
            }}
            onClick={() => onViewTab("jobs")}
          >
            Manage Jobs →
          </button>
        </div>
      </div>

      </div>
        );
      }

      export default Dashboard;