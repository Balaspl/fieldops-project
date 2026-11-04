import React, { useEffect, useState } from "react";
import dashboardBanner from "../assets/dashboard-banner.jpeg";
import { getDashboardStats, getJobs, getTechnicians } from "../services/planningService";
import LoadingSpinner from "../components/ui/LoadingSpinner";
import {
  Briefcase,
  CreditCard,
  Search,
  LayoutDashboard,
  User,
  Clock,
  CheckCircle,
  AlertCircle,
  Users,
  BarChart,
  Calendar,
  CalendarDays,
  ChevronDown,
  Check,
  Coffee,
  MinusCircle,
  Snowflake,
  Zap,
  Droplet,
  Wrench,
  MoreHorizontal,
  MoreVertical,
  TrendingUp,
  Wifi,
  Hammer,
  ShieldCheck,
  Activity,
  Award,
  CalendarCheck,
  ChartColumnIncreasing,
  ChevronRight,
  Gauge,
  Timer,
  Layers,
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
  created_at?: string;
  updated_at?: string;
  assigned_at?: string;
  completed_at?: string;
  assigned_technician_id?: number | null;
  required_skill?: string;
  sla_deadline?: string;
  is_breached?: boolean;
}

interface DashboardTechnician {
  technician_id: number;
  technician_name: string;
  technician_skill?: string;
  technician_status?: string;
  current_jobs?: number;
}

interface DashboardStats {
  payment_summary?: {
    total_recorded: number;
    cash_total: number;
    upi_total: number;
    payment_count: number;
  };

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
    background: "linear-gradient(145deg, #F4FAF7 0%, #F7FAFC 52%, #EEF7F2 100%)",
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
    background: "linear-gradient(145deg, #FFFFFF 0%, #FBFEFC 62%, #F2FAF6 100%)",
    border: "1px solid #DCEDE4",
    borderRadius: "16px",
    boxShadow: "0 10px 22px rgba(15, 46, 32, 0.07), 0 2px 5px rgba(15, 46, 32, 0.04), inset 0 1px 0 rgba(255,255,255,0.95)",
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
    borderRadius: "13px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    boxShadow: "0 8px 14px rgba(15, 23, 42, 0.15), inset 0 1px 0 rgba(255,255,255,0.26)",
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
  .dashboard-analytics-top-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.48fr) minmax(270px, 0.92fr) minmax(300px, 1.18fr);
  gap: 16px;
  width: 100%;
  align-items: stretch;
}
.dashboard-analytics-bottom-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.55fr) minmax(320px, 1fr);
  gap: 16px;
  width: 100%;
  align-items: stretch;
}
.dashboard-category-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.dashboard-chart-range button:hover,
.dashboard-category-tile:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 18px rgba(15, 46, 32, 0.09);
}
.dashboard-analytics-card {
  background: linear-gradient(145deg, #FFFFFF 0%, #FCFEFD 58%, #F5FBF8 100%);
  border: 1px solid #DCEDE4;
  border-radius: 18px;
  box-shadow: 0 12px 26px rgba(15, 46, 32, 0.07), 0 3px 7px rgba(15, 46, 32, 0.035), inset 0 1px 0 rgba(255,255,255,0.98);
  overflow: hidden;
  min-width: 0;
}
@media (max-width: 1350px) {
  .dashboard-analytics-top-grid {
    grid-template-columns: minmax(0, 1.3fr) minmax(260px, 0.9fr);
  }
  .dashboard-technician-card {
    grid-column: 1 / -1;
  }
}
@media (max-width: 1050px) {
  .dashboard-analytics-top-grid,
  .dashboard-analytics-bottom-grid {
    grid-template-columns: minmax(0, 1fr);
  }
  .dashboard-technician-card {
    grid-column: auto;
  }
}
@media (max-width: 700px) {
  .dashboard-category-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 420px) {
  .dashboard-category-grid {
    grid-template-columns: minmax(0, 1fr);
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
  @media (max-width: 820px) {
    .dashboard-date-filter-bar {
      align-items: stretch !important;
      gap: 10px !important;
    }
    .dashboard-date-filter-actions {
      width: 100% !important;
      display: grid !important;
      grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
    }
    .dashboard-date-filter-actions > button,
    .dashboard-date-filter-actions > div,
    .dashboard-date-filter-actions > div > button {
      width: 100% !important;
    }
    .dashboard-date-filter-separator {
      display: none !important;
    }
    .dashboard-date-filter-summary {
      width: 100% !important;
      margin-left: 0 !important;
      box-sizing: border-box !important;
    }
  }
  @media (max-width: 420px) {
    .dashboard-date-filter-actions {
      grid-template-columns: minmax(0, 1fr) !important;
    }
    .dashboard-custom-date-popover {
      left: auto !important;
      right: 0 !important;
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

type DashboardDateRange = {
  start_date: string;
  end_date: string;
};

type DashboardFilterMode = "today" | "week" | "month" | "custom" | "all";

const toDateInputValue = (date: Date): string => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

const parseDateInputValue = (value: string): Date => {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
};

const getCalendarWeekRange = (date = new Date()): DashboardDateRange => {
  const start = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  start.setDate(start.getDate() - start.getDay());
  const end = new Date(start);
  end.setDate(start.getDate() + 6);
  return { start_date: toDateInputValue(start), end_date: toDateInputValue(end) };
};

const getCalendarMonthRange = (monthValue: string): DashboardDateRange => {
  const [year, month] = monthValue.split("-").map(Number);
  const start = new Date(year, month - 1, 1);
  const end = new Date(year, month, 0);
  return { start_date: toDateInputValue(start), end_date: toDateInputValue(end) };
};

const formatDateRangeLabel = (range: DashboardDateRange): string => {
  const start = parseDateInputValue(range.start_date);
  const end = parseDateInputValue(range.end_date);

  const formatDate = (date: Date) =>
    date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });

  const monthDifference =
    (end.getFullYear() - start.getFullYear()) * 12 +
    (end.getMonth() - start.getMonth());

  // Check whether the selected dates represent an exact calendar-month range.
  const expectedEnd = new Date(
    start.getFullYear(),
    start.getMonth() + monthDifference,
    1,
  );

  const lastDay = new Date(
    expectedEnd.getFullYear(),
    expectedEnd.getMonth() + 1,
    0,
  ).getDate();

  expectedEnd.setDate(Math.min(start.getDate(), lastDay));

  let durationLabel: string;

  if (
    monthDifference > 0 &&
    toDateInputValue(expectedEnd) === range.end_date
  ) {
    if (monthDifference % 12 === 0) {
      const years = monthDifference / 12;
      durationLabel = `${years} ${years === 1 ? "year" : "years"}`;
    } else {
      durationLabel = `${monthDifference} months`;
    }
  } else {
    const days =
      Math.round(
        (
          Date.UTC(end.getFullYear(), end.getMonth(), end.getDate()) -
          Date.UTC(start.getFullYear(), start.getMonth(), start.getDate())
        ) / 86400000,
      ) + 1;

    durationLabel = `${days} ${days === 1 ? "day" : "days"}`;
  }

  return `${formatDate(start)} – ${formatDate(end)} (${durationLabel})`;
};

interface DashboardProps {
  onViewTab: (tab: string) => void;
  timeRange: string;
  onTimeRangeChange: (value: string) => void;
  dateRange?: DashboardDateRange | null;
  onDateRangeChange?: (value: DashboardDateRange | null) => void;
  unreadCount: number;
  isBellAnimated: boolean;
  onOpenBellDrawer: () => void;
}

  const Dashboard: React.FC<DashboardProps> = ({
  onViewTab,
  timeRange = "week",
  onTimeRangeChange = () => undefined,
  dateRange = null,
  onDateRangeChange = () => undefined,
}) => {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentJobs, setRecentJobs] = useState<Job[]>([]);
  const [technicians, setTechnicians] = useState<DashboardTechnician[]>([]);
  const [loading, setLoading] = useState(true);
  const [statsError, setStatsError] = useState(false);
  const [filterMode, setFilterMode] = useState<DashboardFilterMode>(
    (timeRange as DashboardFilterMode) || "week",
  );
  const [selectedMonth, setSelectedMonth] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  });
  const [isMonthPickerOpen, setIsMonthPickerOpen] = useState(false);
  const [monthPickerYear, setMonthPickerYear] = useState(() => new Date().getFullYear());
  const [isCustomDateOpen, setIsCustomDateOpen] = useState(false);
  const [draftStartDate, setDraftStartDate] = useState(() => getCalendarWeekRange().start_date);
  const [draftEndDate, setDraftEndDate] = useState(() => getCalendarWeekRange().end_date);
  const [dateRangeError, setDateRangeError] = useState("");
  const currentHour = new Date().getHours();

  const greeting =
    currentHour < 12
      ? "Good morning!"
      : currentHour < 17
        ? "Good afternoon!"
        : "Good evening!";

    useEffect(() => {
    let isMounted = true;

    // Load the dashboard data when the page opens
    // or when the selected date range changes.
    const fetchData = async () => {
      try {
        setLoading(true);
        setStatsError(false);

        const [statsRes, jobsRes, techniciansRes] = await Promise.all([
          getDashboardStats(timeRange, dateRange),
          getJobs(),
          getTechnicians().catch((error) => {
            console.warn("Dashboard technician list unavailable:", error);
            return { data: [] };
          }),
        ]);

        if (!isMounted) return;

        if (statsRes?.data) {
          setStats(statsRes.data);
        }

        if (Array.isArray(jobsRes?.data)) {
          setRecentJobs(jobsRes.data);
        }
        if (Array.isArray(techniciansRes?.data)) {
          setTechnicians(techniciansRes.data);
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
    let refreshInFlight = false;
    const refreshStats = async () => {
      if (refreshInFlight || document.visibilityState !== "visible" || !document.hasFocus()) return;
      refreshInFlight = true;
      try {
        const [statsRes, jobsRes] = await Promise.all([
          getDashboardStats(timeRange),
          getJobs(),
        ]);

        if (isMounted && statsRes?.data) {
          setStats(statsRes.data);
          setStatsError(false);
        }
        if (isMounted && jobsRes?.data) {
          setRecentJobs(jobsRes.data.slice(0, 5));
        }
      } catch (err) {
        console.error("Dashboard refresh failed:", err);
      } finally {
        refreshInFlight = false;
      }
    };

    void fetchData();

    const intervalId = window.setInterval(() => {
      void refreshStats();
    }, 3000);

    const handleWindowFocus = () => {
      void refreshStats();
    };

    window.addEventListener("focus", handleWindowFocus);

    return () => {
      isMounted = false;
      window.clearInterval(intervalId);
      window.removeEventListener("focus", handleWindowFocus);
    };
  }, [timeRange, dateRange?.start_date, dateRange?.end_date]);

  useEffect(() => {
    if (timeRange === "today" || timeRange === "week" || timeRange === "month" || timeRange === "custom" || timeRange === "all") {
      setFilterMode(timeRange as DashboardFilterMode);
    }
  }, [timeRange]);

  useEffect(() => {
    if (dateRange?.start_date) {
      const [year, month] = dateRange.start_date.split("-");
      setSelectedMonth(`${year}-${month}`);
      setMonthPickerYear(Number(year));
    }
  }, [dateRange?.start_date]);

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
                getDashboardStats(timeRange, dateRange),
                getJobs(),
                getTechnicians().catch(() => ({ data: [] })),
              ])
                .then(([statsRes, jobsRes, techniciansRes]) => {
                  if (statsRes && statsRes.data) {
                    setStats(statsRes.data);
                  }

                  if (jobsRes && Array.isArray(jobsRes.data)) {
                    setRecentJobs(jobsRes.data);
                  }
                  if (techniciansRes && Array.isArray(techniciansRes.data)) {
                    setTechnicians(techniciansRes.data);
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

  const normalizeJobStatus = (status: string | undefined): string =>
    (status || "").toUpperCase().replace(/[^A-Z]/g, "");
  const isCompletedJob = (job: Job): boolean =>
    ["COMPLETED", "CLOSED"].includes(normalizeJobStatus(job.status));
  const isTerminalJob = (job: Job): boolean =>
    ["COMPLETED", "CLOSED", "CANCELLED", "CANCELED", "REJECTEDBYTECHNICIAN"].includes(
      normalizeJobStatus(job.status),
    );
  const jobCreatedDateKey = (job: Job): string => {
    const sourceDate = job.created_at || job.preferred_service_date;
    if (!sourceDate) return "";
    const parsed = new Date(sourceDate);
    return Number.isNaN(parsed.getTime()) ? String(sourceDate).slice(0, 10) : toDateInputValue(parsed);
  };

  const effectiveDateRange = dateRange || (
    filterMode === "today"
      ? { start_date: toDateInputValue(new Date()), end_date: toDateInputValue(new Date()) }
      : filterMode === "week"
        ? getCalendarWeekRange()
        : filterMode === "month"
          ? getCalendarMonthRange(selectedMonth)
          : null
  );

  const selectedJobs = recentJobs.filter((job) => {
    if (!effectiveDateRange) return true;
    const dateKey = jobCreatedDateKey(job);
    if (!dateKey) return false;
    return dateKey >= effectiveDateRange.start_date && dateKey <= effectiveDateRange.end_date;
  });

  // Automatically group Job Performance using the main dashboard date range.
  const getActivityDateKey = (value?: string): string => {
    if (!value) return "";

    const parsed = new Date(value);

    return Number.isNaN(parsed.getTime())
      ? value.slice(0, 10)
      : toDateInputValue(parsed);
  };

  const chartToday = new Date();
  chartToday.setHours(0, 0, 0, 0);

  // For All Time, use the earliest available job creation date.
  const availableCreatedDates = recentJobs
    .map((job) => getActivityDateKey(job.created_at))
    .filter(Boolean)
    .sort();

  const chartRangeStart = effectiveDateRange
    ? parseDateInputValue(effectiveDateRange.start_date)
    : availableCreatedDates.length > 0
      ? parseDateInputValue(availableCreatedDates[0])
      : chartToday;

  const chartRangeEnd = effectiveDateRange
    ? parseDateInputValue(effectiveDateRange.end_date)
    : chartToday;

  chartRangeStart.setHours(0, 0, 0, 0);
  chartRangeEnd.setHours(0, 0, 0, 0);

  const chartRangeDays = Math.max(
    1,
    Math.floor(
      (
        Date.UTC(
          chartRangeEnd.getFullYear(),
          chartRangeEnd.getMonth(),
          chartRangeEnd.getDate(),
        ) -
        Date.UTC(
          chartRangeStart.getFullYear(),
          chartRangeStart.getMonth(),
          chartRangeStart.getDate(),
        )
      ) / 86400000,
    ) + 1,
  );

  // Choose chart grouping automatically.
  const performanceGrouping =
    filterMode === "week"
      ? "weekly"
      : filterMode === "today"
        ? "daily"
        : filterMode === "custom" && chartRangeDays <= 31
          ? "daily"
          : "monthly";

  const performanceGroupingLabel =
    performanceGrouping === "daily"
      ? "Daily View"
      : performanceGrouping === "weekly"
        ? "Weekly View"
        : "Monthly View";

  const performanceBuckets: {
    label: string;
    created: number;
    completed: number;
  }[] = [];

  // Add one bucket and count both activities using their own timestamps.
  const addPerformanceBucket = (
    bucketStart: Date,
    bucketEnd: Date,
    label: string,
  ) => {
    const startKey = toDateInputValue(bucketStart);
    const endKey = toDateInputValue(bucketEnd);

    const isInsideSelectedRange = (key: string) => {
      if (!key || key < startKey || key >= endKey) {
        return false;
      }

      if (!effectiveDateRange) return true;

      return (
        key >= effectiveDateRange.start_date &&
        key <= effectiveDateRange.end_date
      );
    };

    const created = recentJobs.filter((job) =>
      isInsideSelectedRange(getActivityDateKey(job.created_at)),
    ).length;

    const completed = recentJobs.filter((job) =>
      isInsideSelectedRange(getActivityDateKey(job.completed_at)),
    ).length;

    performanceBuckets.push({
      label,
      created,
      completed,
    });
  };

  const formatChartDate = (date: Date) =>
    date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });

  const addMonthsFromAnchor = (
    anchor: Date,
    months: number,
  ): Date => {
    const target = new Date(
      anchor.getFullYear(),
      anchor.getMonth() + months,
      1,
    );

    const lastDay = new Date(
      target.getFullYear(),
      target.getMonth() + 1,
      0,
    ).getDate();

    target.setDate(Math.min(anchor.getDate(), lastDay));

    return target;
  };

  const chartEndExclusive = new Date(chartRangeEnd);
  chartEndExclusive.setDate(chartEndExclusive.getDate() + 1);

  if (performanceGrouping === "daily") {
    // Daily chart: one group per day.
    const cursor = new Date(chartRangeStart);

    while (cursor <= chartRangeEnd) {
      const bucketStart = new Date(cursor);
      const bucketEnd = new Date(cursor);

      bucketEnd.setDate(bucketEnd.getDate() + 1);

      addPerformanceBucket(
        bucketStart,
        bucketEnd,
        formatChartDate(bucketStart),
      );

      cursor.setDate(cursor.getDate() + 1);
    }
  } else if (performanceGrouping === "weekly") {
    // This Week: one combined weekly group.
    addPerformanceBucket(
      chartRangeStart,
      chartEndExclusive,
      `${formatChartDate(chartRangeStart)} – ${formatChartDate(chartRangeEnd)}`,
    );
  } else {
    // Monthly view: periods anchored to the selected From date.
    let cursor = new Date(chartRangeStart);
    let periodIndex = 0;

    while (cursor < chartEndExclusive) {
      const nextMonth = addMonthsFromAnchor(
        chartRangeStart,
        periodIndex + 1,
      );

      const bucketEnd =
        nextMonth >= chartRangeEnd
          ? chartEndExclusive
          : nextMonth;

      const lastIncludedDate = new Date(bucketEnd);
      lastIncludedDate.setDate(lastIncludedDate.getDate() - 1);

      const label = chartRangeDays <= 210
        ? `${formatChartDate(cursor)} – ${formatChartDate(lastIncludedDate)}`
        : cursor.toLocaleDateString("en-US", {
            month: "short",
            year: "2-digit",
          });

      addPerformanceBucket(
        cursor,
        bucketEnd,
        label,
      );

      cursor = new Date(bucketEnd);
      periodIndex += 1;
    }
  }

  const performanceMax = Math.max(
    1,
    ...performanceBuckets.flatMap((bucket) => [
      bucket.created,
      bucket.completed,
    ]),
  );

  const statusSegments = [
    { label: "Completed", value: stats.job_cards.completed, color: "#10B981" },
    { label: "Accepted", value: stats.job_cards.accepted, color: "#2387F5" },
    { label: "In Progress", value: stats.job_cards.in_progress, color: "#F59E0B" },
    { label: "En Route", value: stats.job_cards.en_route, color: "#8B5CF6" },
    { label: "Unassigned", value: stats.job_cards.unassigned, color: "#EF4444" },
    { label: "Rejected", value: stats.job_cards.rejected, color: "#F97316" },
    { label: "Cancelled", value: stats.jobs.cancelled, color: "#64748B" },
  ];
  const statusTotal = statusSegments.reduce((sum, item) => sum + item.value, 0);
  let statusOffset = 0;
  const statusGradient = statusTotal > 0
    ? `conic-gradient(${statusSegments.map((item) => {
        const start = statusOffset;
        statusOffset += (item.value / statusTotal) * 100;
        return `${item.color} ${start}% ${statusOffset}%`;
      }).join(", ")})`
    : "conic-gradient(#E8EEF0 0% 100%)";

  const technicianPerformance = technicians
    .map((technician) => {
      const technicianJobs = selectedJobs.filter(
        (job) => Number(job.assigned_technician_id) === Number(technician.technician_id),
      );
      const completed = technicianJobs.filter(isCompletedJob).length;
      const total = technicianJobs.length;
      return {
        ...technician,
        total,
        completed,
        completionRate: total > 0 ? Math.round((completed / total) * 100) : 0,
      };
    })
    .filter((technician) => technician.total > 0)
    .sort((a, b) => b.completed - a.completed || b.total - a.total)
    .slice(0, 4);

  const categoryDefinitions = [
    { name: "HVAC Repair", match: ["hvac", "hvac repair"], icon: Snowflake, color: "#0AA779", tint: "#EAFBF4" },
    { name: "Electrical", match: ["electrical", "electrician"], icon: Zap, color: "#E99A13", tint: "#FFF8E8" },
    { name: "Plumbing", match: ["plumbing", "plumber"], icon: Droplet, color: "#EF4444", tint: "#FFF0F1" },
    { name: "Network Support", match: ["network", "network support", "it support"], icon: Wifi, color: "#0EA5E9", tint: "#EDF8FF" },
    { name: "General Maintenance", match: ["general maintenance", "maintenance"], icon: Wrench, color: "#64748B", tint: "#F2F5F8" },
    { name: "Appliance Repair", match: ["appliance", "appliance repair"], icon: Briefcase, color: "#DB4C9B", tint: "#FFF0F8" },
    { name: "Roofing & Carpentry", match: ["roofing", "carpentry", "roofing carpentry"], icon: Hammer, color: "#607D8B", tint: "#F0F5F7" },
    { name: "CCTV & Security", match: ["cctv", "security", "cctv security"], icon: ShieldCheck, color: "#059669", tint: "#EAFBF4" },
  ];
  const categoryPerformance = categoryDefinitions.map((category) => {
    const count = selectedJobs.filter((job) => {
      const raw = (job.service_type || job.required_skill || "").toLowerCase().replace(/[_-]/g, " ").trim();
      return category.match.some((term) => raw === term || raw.includes(term));
    }).length;
    return { ...category, count };
  });
  const maxCategoryCount = Math.max(1, ...categoryPerformance.map((item) => item.count));

  const activeJobsWithSla = selectedJobs.filter((job) => {
    if (!job.sla_deadline || isTerminalJob(job)) return false;
    return !Number.isNaN(new Date(job.sla_deadline).getTime());
  });
  const nowForSla = new Date();
  const withinSlaCount = activeJobsWithSla.filter(
    (job) => new Date(job.sla_deadline as string).getTime() >= nowForSla.getTime(),
  ).length;
  const overdueSlaCount = activeJobsWithSla.length - withinSlaCount;
  const atRiskSlaCount = activeJobsWithSla.filter((job) => {
    const remaining = new Date(job.sla_deadline as string).getTime() - nowForSla.getTime();
    return remaining >= 0 && remaining <= 60 * 60 * 1000;
  }).length;
  const slaCompliance = activeJobsWithSla.length > 0
    ? Math.round((withinSlaCount / activeJobsWithSla.length) * 100)
    : null;
  const assignmentDurations = selectedJobs
    .filter((job) => job.created_at && job.assigned_at)
    .map((job) => (new Date(job.assigned_at as string).getTime() - new Date(job.created_at as string).getTime()) / 60000)
    .filter((minutes) => Number.isFinite(minutes) && minutes >= 0);
  const averageAssignmentMinutes = assignmentDurations.length > 0
    ? Math.round(assignmentDurations.reduce((sum, value) => sum + value, 0) / assignmentDurations.length)
    : null;

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
            Welcome to FieldOps Commander
          </h1>

          <p
            style={{
              margin: "8px 0 0",
              fontSize: "clamp(12px, 1.1vw, 14px)",
              color: "rgba(255,255,255,0.9)",
            }}
          >
            Manage jobs, technicians, planning and service operations in one place.
          </p>
        </div>

        {/* Existing Date Selector and Notification Bell */}


      </div>

      {/* Dashboard date filters */}
      <div
        className="dashboard-date-filter-bar"
        style={{
          position: "relative",
          zIndex: 5,
          display: "flex",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "12px",
          width: "100%",
          minHeight: "58px",
          padding: "7px 10px",
          background: "linear-gradient(135deg, #F0FBF5 0%, #FFFFFF 50%, #F0F8FF 100%)",
          border: "1px solid #A9E3C8",
          borderRadius: "13px",
          boxShadow: "0 5px 14px rgba(21, 128, 74, 0.07), inset 0 1px 0 rgba(255,255,255,0.9)",
        }}
      >
        <div
          className="dashboard-date-filter-actions"
          style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: "10px" }}
        >
          {[
            {
              value: "today" as const,
              label: "Today",
              subtitle: "",
              width: "142px",
              accent: "#079B65",
              soft: "#E8F8F0",
              border: "#B9E8D1",
              text: "#087B52",
              dark: "#087D50",
            },
            {
              value: "week" as const,
              label: "This Week",
              subtitle: "Sun – Sat",
              width: "160px",
              accent: "#3985DB",
              soft: "#EDF5FF",
              border: "#C9DFFF",
              text: "#2867AE",
              dark: "#2867AE",
            },
          ].map((option) => {
            const active = filterMode === option.value;
            return (
              <button
                key={option.value}
                type="button"
                aria-pressed={active}
                onClick={() => {
                  setFilterMode(option.value);
                  setIsCustomDateOpen(false);
                  setIsMonthPickerOpen(false);
                  if (option.value === "today") {
                    const todayValue = toDateInputValue(new Date());
                    onDateRangeChange({ start_date: todayValue, end_date: todayValue });
                  } else {
                    onDateRangeChange(getCalendarWeekRange());
                  }
                  onTimeRangeChange(option.value);
                }}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "10px",
                  width: option.width,
                  minHeight: "42px",
                  padding: "5px 11px",
                  border: `1px solid ${option.border}`,
                  borderRadius: "10px",
                  background: active
                    ? `linear-gradient(145deg, ${option.accent}, ${option.dark})`
                    : `linear-gradient(145deg, ${option.soft}, #FFFFFF)`,
                  color: active ? "#FFFFFF" : option.text,
                  boxShadow: active
                    ? `0 4px 9px ${option.accent}40, inset 0 1px 0 rgba(255,255,255,0.25)`
                    : "0 2px 5px rgba(15,23,42,0.05), inset 0 1px 0 #FFFFFF",
                }}
              >
                <CalendarDays size={19} strokeWidth={1.9} />
                <span style={{ display: "flex", flexDirection: "column", alignItems: option.subtitle ? "flex-start" : "center", gap: "1px" }}>
                  <strong style={{ fontSize: "13px", lineHeight: 1.25 }}>{option.label}</strong>
                  {option.subtitle && <span style={{ fontSize: "10px", opacity: 0.88 }}>{option.subtitle}</span>}
                </span>
                {active && <Check size={17} style={{ marginLeft: "auto" }} strokeWidth={2.7} />}
              </button>
            );
          })}

          <div style={{ position: "relative" }}>
            <button
              type="button"
              aria-label="Choose month"
              aria-expanded={isMonthPickerOpen}
              aria-pressed={filterMode === "month"}
              onClick={() => {
                const shouldOpen = !isMonthPickerOpen;
                const now = new Date();
                const currentMonthValue = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
                const monthValue = filterMode === "month" ? selectedMonth : currentMonthValue;
                setSelectedMonth(monthValue);
                setMonthPickerYear(Number(monthValue.slice(0, 4)));
                setFilterMode("month");
                setIsMonthPickerOpen(shouldOpen);
                setIsCustomDateOpen(false);
                onTimeRangeChange("month");
                if (shouldOpen) onDateRangeChange(getCalendarMonthRange(monthValue));
              }}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "10px",
                width: "190px",
                minHeight: "42px",
                padding: "5px 11px",
                border: "1px solid #D9D0FA",
                borderRadius: "10px",
                background: filterMode === "month"
                  ? "linear-gradient(145deg, #EDE7FF, #F8F5FF)"
                  : "linear-gradient(145deg, #F5F1FF, #FFFFFF)",
                color: "#6143B5",
                boxShadow: filterMode === "month"
                  ? "0 3px 8px rgba(124, 87, 194, 0.12)"
                  : "0 2px 5px rgba(15,23,42,0.05)",
                cursor: "pointer",
                fontFamily: "inherit",
                textAlign: "left",
              }}
            >
              <CalendarDays size={19} strokeWidth={1.9} />
              <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: "1px", flex: 1, minWidth: 0 }}>
                <strong style={{ fontSize: "13px", lineHeight: 1.25, whiteSpace: "nowrap" }}>
                  {selectedMonth === `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, "0")}`
                    ? "This Month"
                    : parseDateInputValue(`${selectedMonth}-01`).toLocaleDateString("en-US", { month: "long", year: "numeric" })}
                </strong>
                <span style={{ fontSize: "10px", color: "#64748B" }}>Monthly overview</span>
              </span>
              <ChevronDown size={16} />
            </button>

            {isMonthPickerOpen && (
              <div
                style={{
                  position: "absolute",
                  top: "calc(100% + 10px)",
                  left: 0,
                  width: "296px",
                  padding: "16px",
                  background: "#FFFFFF",
                  border: "1px solid #E2E8F0",
                  borderRadius: "16px",
                  boxShadow: "0 18px 45px rgba(15, 23, 42, 0.16)",
                  zIndex: 30,
                  boxSizing: "border-box",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "16px" }}>
                  <div>
                    <div style={{ fontSize: "10px", fontWeight: 800, letterSpacing: "1px", color: "#07884E", marginBottom: "4px" }}>MONTHLY FILTER</div>
                    <strong style={{ fontSize: "15px", color: "#172033" }}>Choose a month</strong>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "5px", padding: "4px", background: "#F3F6F8", borderRadius: "10px" }}>
                    <button
                      type="button"
                      aria-label="Previous year"
                      onClick={() => setMonthPickerYear((year) => year - 1)}
                      style={{ width: "28px", height: "28px", border: "none", borderRadius: "7px", background: "#FFFFFF", cursor: "pointer", color: "#475569", display: "flex", alignItems: "center", justifyContent: "center" }}
                    >
                      <ChevronDown size={15} style={{ transform: "rotate(90deg)" }} />
                    </button>
                    <strong style={{ minWidth: "43px", textAlign: "center", fontSize: "13px", color: "#172033" }}>{monthPickerYear}</strong>
                    <button
                      type="button"
                      aria-label="Next year"
                      disabled={monthPickerYear >= new Date().getFullYear()}
                      onClick={() => setMonthPickerYear((year) => year + 1)}
                      style={{ width: "28px", height: "28px", border: "none", borderRadius: "7px", background: "#FFFFFF", cursor: monthPickerYear >= new Date().getFullYear() ? "not-allowed" : "pointer", color: "#475569", opacity: monthPickerYear >= new Date().getFullYear() ? 0.35 : 1, display: "flex", alignItems: "center", justifyContent: "center" }}
                    >
                      <ChevronDown size={15} style={{ transform: "rotate(-90deg)" }} />
                    </button>
                  </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: "8px" }}>
                  {Array.from({ length: 12 }, (_, index) => {
                    const monthDate = new Date(monthPickerYear, index, 1);
                    const monthValue = `${monthPickerYear}-${String(index + 1).padStart(2, "0")}`;
                    const currentDate = new Date();
                    const currentMonth = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1);
                    const isSelected = selectedMonth === monthValue;
                    const isCurrent = monthValue === `${currentDate.getFullYear()}-${String(currentDate.getMonth() + 1).padStart(2, "0")}`;
                    const isFuture = monthDate > currentMonth;
                    return (
                      <button
                        key={monthValue}
                        type="button"
                        disabled={isFuture}
                        aria-label={`Select dashboard month ${monthDate.toLocaleDateString("en-US", { month: "long", year: "numeric" })}`}
                        aria-pressed={isSelected}
                        onClick={() => {
                          const range = getCalendarMonthRange(monthValue);
                          setSelectedMonth(monthValue);
                          setFilterMode("month");
                          setIsMonthPickerOpen(false);
                          onTimeRangeChange("month");
                          onDateRangeChange(range);
                        }}
                        style={{
                          minHeight: "42px",
                          border: isSelected ? "1px solid #07884E" : isCurrent ? "1px solid #A7DCC5" : "1px solid #E8EDF2",
                          borderRadius: "10px",
                          background: isSelected ? "#07884E" : isCurrent ? "#ECFDF5" : "#FFFFFF",
                          color: isSelected ? "#FFFFFF" : isFuture ? "#CBD5E1" : "#334155",
                          fontSize: "12px",
                          fontWeight: 700,
                          cursor: isFuture ? "not-allowed" : "pointer",
                          opacity: isFuture ? 0.5 : 1,
                          boxShadow: isSelected ? "0 3px 8px rgba(7, 136, 78, 0.2)" : "none",
                          transition: "all 150ms ease",
                        }}
                      >
                        {monthDate.toLocaleDateString("en-US", { month: "short" })}
                      </button>
                    );
                  })}
                </div>

                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderTop: "1px solid #EDF1F5", marginTop: "14px", paddingTop: "12px" }}>
                  <span style={{ fontSize: "10px", color: "#94A3B8" }}>Select a month to apply</span>
                  <button
                    type="button"
                    onClick={() => {
                      const now = new Date();
                      const value = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
                      setSelectedMonth(value);
                      setMonthPickerYear(now.getFullYear());
                      setFilterMode("month");
                      setIsMonthPickerOpen(false);
                      onTimeRangeChange("month");
                      onDateRangeChange(getCalendarMonthRange(value));
                    }}
                    style={{ border: "none", background: "transparent", color: "#07884E", fontSize: "11px", fontWeight: 700, cursor: "pointer", padding: "5px" }}
                  >
                    Current month
                  </button>
                </div>
              </div>
            )}
          </div>

          <div style={{ position: "relative" }}>
            <button
              type="button"
              aria-label="Custom Date"
              aria-expanded={isCustomDateOpen}
              aria-pressed={filterMode === "custom"}
              onClick={() => {
                setDraftStartDate(dateRange?.start_date || getCalendarWeekRange().start_date);
                setDraftEndDate(dateRange?.end_date || getCalendarWeekRange().end_date);
                setDateRangeError("");
                setIsCustomDateOpen((open) => !open);
                setIsMonthPickerOpen(false);
              }}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "10px",
                width: "160px",
                minHeight: "42px",
                padding: "5px 11px",
                border: "1px solid #F3D9B8",
                borderRadius: "10px",
                background: "linear-gradient(145deg, #FFF4E7, #FFFAF3)",
                color: "#B96A18",
                boxShadow: "0 2px 5px rgba(180, 110, 30, 0.07)",
                cursor: "pointer",
                fontFamily: "inherit",
                fontSize: "13px",
                fontWeight: 700,
                whiteSpace: "nowrap",
              }}
            >
              <CalendarDays size={19} strokeWidth={1.9} />
              Custom Date
            </button>
            {isCustomDateOpen && (
              <div
                className="dashboard-custom-date-popover"
                style={{
                  position: "absolute",
                  top: "calc(100% + 8px)",
                  left: 0,
                  width: "336px",
                  maxWidth: "calc(100vw - 36px)",
                  padding: "14px",
                  background: "#FFFFFF",
                  border: "1px solid #A7DCC5",
                  borderRadius: "10px",
                  boxShadow: "0 8px 24px rgba(15, 23, 42, 0.14)",
                  zIndex: 25,
                  boxSizing: "border-box",
                }}
              >
                {/* Quick Date Range Presets */}
                <div style={{ marginBottom: "14px" }}>
                  <div
                    style={{
                      fontSize: "11px",
                      fontWeight: 800,
                      color: "#475569",
                      marginBottom: "9px",
                    }}
                  >
                    Quick Date Ranges
                  </div>

                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                      gap: "8px",
                    }}
                  >
                    {[
                      { label: "Last 1 Year", months: 12 },
                      { label: "Last 9 Months", months: 9 },
                      { label: "Last 6 Months", months: 6 },
                      { label: "Last 3 Months", months: 3 },
                    ].map((preset) => (
                      <button
                        key={preset.months}
                        type="button"
                        onClick={() => {
                          const endDate = new Date();
                          endDate.setHours(0, 0, 0, 0);

                          const startDate = new Date(endDate);
                          const originalDay = startDate.getDate();

                          startDate.setDate(1);
                          startDate.setMonth(
                            startDate.getMonth() - preset.months
                          );

                          const lastDayOfMonth = new Date(
                            startDate.getFullYear(),
                            startDate.getMonth() + 1,
                            0
                          ).getDate();

                          startDate.setDate(
                            Math.min(originalDay, lastDayOfMonth)
                          );

                          const selectedRange = {
                            start_date: toDateInputValue(startDate),
                            end_date: toDateInputValue(endDate),
                          };

                          // Update the date fields.
                          setDraftStartDate(selectedRange.start_date);
                          setDraftEndDate(selectedRange.end_date);
                          setDateRangeError("");

                          // Apply the selected date range immediately.
                          setFilterMode("custom");
                          setIsCustomDateOpen(false);
                          onTimeRangeChange("custom");
                          onDateRangeChange(selectedRange);
                        }}
                        style={{
                          minHeight: "38px",
                          border: "1px solid #CDEBDD",
                          borderRadius: "9px",
                          background:
                            "linear-gradient(145deg, #EAF8F0, #FFFFFF)",
                          color: "#087B50",
                          fontSize: "11px",
                          fontWeight: 750,
                          cursor: "pointer",
                          boxShadow:
                            "0 2px 5px rgba(7,123,77,0.06)",
                          transition: "all 0.2s ease",
                        }}
                      >
                        {preset.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px" }}>
                  <label style={{ display: "flex", flexDirection: "column", gap: "6px", color: "#334155", fontSize: "11px", fontWeight: 700 }}>
                    From
                    <input
                      type="date"
                      aria-label="From date"
                      value={draftStartDate}
                      max={draftEndDate || undefined}
                      onChange={(event) => setDraftStartDate(event.target.value)}
                      style={{ width: "100%", minWidth: 0, height: "36px", padding: "0 8px", border: "1px solid #CBD5E1", borderRadius: "7px", color: "#1F2937", fontSize: "11px", boxSizing: "border-box" }}
                    />
                  </label>
                  <label style={{ display: "flex", flexDirection: "column", gap: "6px", color: "#334155", fontSize: "11px", fontWeight: 700 }}>
                    To
                    <input
                      type="date"
                      aria-label="To date"
                      value={draftEndDate}
                      min={draftStartDate || undefined}
                      onChange={(event) => setDraftEndDate(event.target.value)}
                      style={{ width: "100%", minWidth: 0, height: "36px", padding: "0 8px", border: "1px solid #CBD5E1", borderRadius: "7px", color: "#1F2937", fontSize: "11px", boxSizing: "border-box" }}
                    />
                  </label>
                </div>
                {dateRangeError && <p role="alert" style={{ margin: "8px 0 0", color: "#B91C1C", fontSize: "11px" }}>{dateRangeError}</p>}
                <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "12px" }}>
                  <button
                    type="button"
                    onClick={() => {
                      const weekRange = getCalendarWeekRange();
                      setDraftStartDate(weekRange.start_date);
                      setDraftEndDate(weekRange.end_date);
                      setDateRangeError("");
                      setFilterMode("week");
                      setIsCustomDateOpen(false);
                      onDateRangeChange(weekRange);
                      onTimeRangeChange("week");
                    }}
                    style={{ minWidth: "72px", height: "32px", padding: "0 12px", border: "1px solid #CBD5E1", borderRadius: "7px", background: "#FFFFFF", color: "#334155", fontSize: "11px", fontWeight: 700, cursor: "pointer" }}
                  >
                    Clear
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (!draftStartDate || !draftEndDate || draftStartDate > draftEndDate) {
                        setDateRangeError("Choose a valid start and end date.");
                        return;
                      }
                      setDateRangeError("");
                      setFilterMode("custom");
                      setIsCustomDateOpen(false);
                      onTimeRangeChange("custom");
                      onDateRangeChange({ start_date: draftStartDate, end_date: draftEndDate });
                    }}
                    style={{ minWidth: "72px", height: "32px", padding: "0 14px", border: "1px solid #07884E", borderRadius: "7px", background: "#07884E", color: "#FFFFFF", fontSize: "11px", fontWeight: 700, cursor: "pointer" }}
                  >
                    Apply
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        <div
          className="dashboard-date-filter-separator"
          aria-hidden="true"
          style={{ width: "1px", height: "38px", background: "#B7E5D1", margin: "0 8px", flexShrink: 0 }}
        />
        <div
          className="dashboard-date-filter-summary"
          aria-live="polite"
          style={{ marginLeft: "auto", display: "flex", alignItems: "center", justifyContent: "center", gap: "10px", minWidth: "205px", minHeight: "40px", padding: "0 12px", borderRadius: "10px", background: "linear-gradient(145deg, #DFF5E9, #EDF9F2)", color: "#1F2937", fontSize: "13px", fontWeight: 700, whiteSpace: "nowrap" }}
        >
          <CalendarDays size={20} color="#07884E" />
          {(() => {
            const range = dateRange || (filterMode === "today"
              ? { start_date: toDateInputValue(new Date()), end_date: toDateInputValue(new Date()) }
              : filterMode === "month"
                ? getCalendarMonthRange(selectedMonth)
                : getCalendarWeekRange());
            return filterMode === "all" ? "All time" : formatDateRangeLabel(range);
          })()}
        </div>
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
          {
            key: "payments",
            label: "Payments Collected",
            value: new Intl.NumberFormat("en-IN", {
              style: "currency",
              currency: "INR",
              maximumFractionDigits: 0,
            }).format(stats.payment_summary?.total_recorded ?? 0),
            subtext: `Cash ${new Intl.NumberFormat("en-IN").format(stats.payment_summary?.cash_total ?? 0)} · UPI ${new Intl.NumberFormat("en-IN").format(stats.payment_summary?.upi_total ?? 0)}`,
            color: "#0D9488",
            icon: CreditCard,
            trend: "M2 27 L12 21 L22 23 L32 13 L42 18 L52 9 L62 13 L72 3",
            onClick: undefined,
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

      {/* ── Operations Analytics Command Center ── */}
      <div className="dashboard-analytics-top-grid">
        {/* Job performance */}
        <section className="dashboard-analytics-card" aria-labelledby="job-performance-title">
          <div style={{ padding: "18px 20px 14px", borderBottom: "1px solid #EAF1ED", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px", flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", minWidth: 0 }}>
              <div style={{ width: "34px", height: "34px", borderRadius: "11px", background: "linear-gradient(145deg,#D8F7E8,#A5E8C7)", color: "#059669", display: "grid", placeItems: "center", boxShadow: "0 5px 10px rgba(5,150,105,0.14), inset 0 1px 0 rgba(255,255,255,.9)" }}>
                <ChartColumnIncreasing size={19} />
              </div>
              <div>
                <h3 id="job-performance-title" style={{ margin: 0, color: "#142238", fontSize: "15px", fontWeight: 800 }}>Job Performance</h3>
                <p style={{ margin: "3px 0 0", color: "#718096", fontSize: "11px" }}>Created jobs and their current completion status</p>
              </div>
            </div>
            <div
              aria-live="polite"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                padding: "8px 13px",
                borderRadius: "10px",
                background: "linear-gradient(145deg, #E8F8EF, #F5FBF7)",
                border: "1px solid #CDEBDD",
                boxShadow: "0 2px 5px rgba(7,123,77,.06)",
              }}
            >
              <CalendarDays size={15} color="#078653" />

              <span
                style={{
                  fontSize: "11px",
                  fontWeight: 800,
                  color: "#087B50",
                }}
              >
                {performanceGroupingLabel}
              </span>

              <span
                style={{
                  fontSize: "9px",
                  color: "#799487",
                }}
              >
                Auto
              </span>
            </div>
          </div>

          <div style={{ padding: "16px 20px 18px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "18px", marginBottom: "12px", flexWrap: "wrap" }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontSize: "10px", fontWeight: 700, color: "#526174" }}><span style={{ width: "9px", height: "9px", borderRadius: "3px", background: "#119B65" }} /> Jobs Created</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: "6px", fontSize: "10px", fontWeight: 700, color: "#526174" }}><span style={{ width: "9px", height: "9px", borderRadius: "3px", background: "#9AE6C3" }} /> Jobs Completed</span>
            </div>

            {/* Modern Job Performance Chart */}
            <div
              style={{
                position: "relative",
                height: "245px",
                marginTop: "8px",
                padding: "14px 14px 34px",
                border: "1px solid #E4EFE8",
                borderRadius: "15px",
                background: "linear-gradient(145deg, #FCFFFD 0%, #F4FAF6 100%)",
                boxShadow: "inset 0 1px 0 rgba(255,255,255,0.95)",
                boxSizing: "border-box",
                overflow: "hidden",
              }}
            >
              {/* Horizontal chart grid */}
              <div
                style={{
                  position: "absolute",
                  top: "14px",
                  left: "14px",
                  right: "14px",
                  bottom: "34px",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                  pointerEvents: "none",
                }}
              >
                {[0, 1, 2, 3, 4].map((line) => (
                  <div
                    key={line}
                    style={{
                      width: "100%",
                      borderTop: line === 4
                        ? "1px solid #D5E4DA"
                        : "1px dashed #E4EDE7",
                    }}
                  />
                ))}
              </div>

              {/* Chart bars */}
              <div
                style={{
                  position: "relative",
                  zIndex: 1,
                  height: "100%",
                  display: "grid",
                  gridTemplateColumns: `repeat(${performanceBuckets.length}, minmax(0, 1fr))`,
                  gap: performanceGrouping === "daily" ? "3px" : performanceGrouping === "weekly" ? "8px" : "12px",
                  minWidth:
                    performanceGrouping === "monthly" && performanceBuckets.length > 24
                      ? `${performanceBuckets.length * 24}px`
                      : "100%",
                }}
              >
                {performanceBuckets.map((bucket, index) => {
                  // Reserve space above bars so count labels are never clipped.
                  const createdHeight = bucket.created > 0
                    ? Math.max(3, (bucket.created / performanceMax) * 82)
                    : 0;

                  const completedHeight = bucket.completed > 0
                    ? Math.max(3, (bucket.completed / performanceMax) * 82)
                    : 0;

                  return (
                    <div
                      key={`${bucket.label}-${index}`}
                      style={{
                        minWidth: 0,
                        height: "100%",
                        display: "grid",
                        gridTemplateRows: "minmax(0, 1fr) 22px",
                        alignItems: "end",
                      }}
                    >
                      {/* Individual bar group */}
                      <div
                        style={{
                          height: "100%",
                          display: "flex",
                          alignItems: "flex-end",
                          justifyContent: "center",
                          gap: performanceGrouping === "daily" ? "2px" : "6px",
                          padding: "0 2px",
                        }}
                      >
                        {/* Jobs Created */}
                        <div
                          style={{
                            width: performanceGrouping === "daily"
                              ? "42%"
                              : "min(34%, 30px)",
                            maxWidth: performanceGrouping === "daily"
                              ? "12px"
                              : "30px",
                            height: "100%",
                            position: "relative",
                            display: "flex",
                            alignItems: "flex-end",
                            justifyContent: "center",
                          }}
                        >
                          {bucket.created > 0 && (
                            <span
                              style={{
                                position: "absolute",
                                bottom: `calc(${createdHeight}% + 7px)`,
                                left: "50%",
                                transform: "translateX(-50%)",
                                color: "#087C50",
                                fontSize: "10px",
                                fontWeight: 800,
                                whiteSpace: "nowrap",
                              }}
                            >
                              {bucket.created}
                            </span>
                          )}

                          <div
                            title={`${bucket.created} jobs created`}
                            style={{
                              width: "100%",
                              height: `${createdHeight}%`,
                              minHeight: bucket.created > 0 ? "5px" : 0,
                              borderRadius: "7px 7px 2px 2px",
                              background: "linear-gradient(180deg, #48D49B 0%, #12A66C 45%, #078653 100%)",
                              borderTop: "1px solid rgba(255,255,255,0.7)",
                              boxShadow: "0 5px 10px rgba(7,138,88,0.19), inset 1px 0 0 rgba(255,255,255,0.24), inset -1px 0 0 rgba(0,0,0,0.04)",
                              transition: "height 350ms ease",
                            }}
                          />
                        </div>

                        {/* Jobs Completed */}
                        <div
                          style={{
                            width: performanceGrouping === "daily"
                              ? "42%"
                              : "min(34%, 30px)",
                            maxWidth: performanceGrouping === "daily"
                              ? "12px"
                              : "30px",
                            height: "100%",
                            position: "relative",
                            display: "flex",
                            alignItems: "flex-end",
                            justifyContent: "center",
                          }}
                        >
                          {bucket.completed > 0 && (
                            <span
                              style={{
                                position: "absolute",
                                bottom: `calc(${completedHeight}% + 7px)`,
                                left: "50%",
                                transform: "translateX(-50%)",
                                color: "#50A77E",
                                fontSize: "10px",
                                fontWeight: 800,
                                whiteSpace: "nowrap",
                              }}
                            >
                              {bucket.completed}
                            </span>
                          )}

                          <div
                            title={`${bucket.completed} completed`}
                            style={{
                              width: "100%",
                              height: `${completedHeight}%`,
                              minHeight: bucket.completed > 0 ? "5px" : 0,
                              borderRadius: "7px 7px 2px 2px",
                              background: "linear-gradient(180deg, #D0F8E5 0%, #98E8C4 48%, #65D5A2 100%)",
                              borderTop: "1px solid rgba(255,255,255,0.9)",
                              boxShadow: "0 4px 8px rgba(16,185,129,0.12), inset 1px 0 0 rgba(255,255,255,0.65), inset -1px 0 0 rgba(0,0,0,0.03)",
                              transition: "height 350ms ease",
                            }}
                          />
                        </div>
                      </div>

                      {/* Date label */}
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          borderTop: "1px solid #DCE9E1",
                          paddingTop: "6px",
                          color: "#64788A",
                          fontSize: performanceGrouping === "daily" ? "8px" : "9px",
                          fontWeight: 750,
                          whiteSpace: "nowrap",
                        }}
                      >
                        {bucket.label}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Chart explanation */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                flexWrap: "wrap",
                gap: "8px",
                marginTop: "12px",
              }}
            >
              <span
                style={{
                  color: "#8998A6",
                  fontSize: "9px",
                  lineHeight: 1.5,
                }}
              >
                Jobs Created and Jobs Completed are grouped by their respective dates.
              </span>

              <span
                style={{
                  color: "#078653",
                  background: "#EAF8F0",
                  border: "1px solid #D8EFE2",
                  padding: "5px 9px",
                  borderRadius: "20px",
                  fontSize: "9px",
                  fontWeight: 750,
                }}
              >
                Live dashboard data
              </span>
            </div>
          </div>
        </section>

        {/* Job status distribution */}
        <section className="dashboard-analytics-card" aria-labelledby="job-status-title">
          <div style={{ padding: "18px 18px 14px", borderBottom: "1px solid #EAF1ED", display: "flex", alignItems: "center", gap: "10px" }}>
            <div style={{ width: "34px", height: "34px", borderRadius: "11px", background: "linear-gradient(145deg,#D9F7E8,#A9E9CC)", color: "#059669", display: "grid", placeItems: "center", boxShadow: "0 5px 10px rgba(5,150,105,.14)" }}><Activity size={19} /></div>
            <div>
              <h3 id="job-status-title" style={{ margin: 0, color: "#142238", fontSize: "15px", fontWeight: 800 }}>Job Status Distribution</h3>
              <p style={{ margin: "3px 0 0", color: "#718096", fontSize: "11px" }}>Selected date range</p>
            </div>
          </div>
          <div style={{ padding: "18px 16px", display: "flex", alignItems: "center", justifyContent: "center", gap: "18px", flex: 1, minHeight: "250px" }}>
            <div style={{ width: "152px", height: "152px", flex: "0 0 152px", position: "relative", borderRadius: "50%", background: statusGradient, boxShadow: "0 12px 22px rgba(18,72,49,.17), inset 0 2px 5px rgba(255,255,255,.36)", display: "grid", placeItems: "center" }}>
              <div style={{ width: "94px", height: "94px", borderRadius: "50%", background: "linear-gradient(145deg,#FFFFFF,#F3F8F5)", boxShadow: "inset 0 3px 8px rgba(15,46,32,.08), 0 2px 4px rgba(255,255,255,.95)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
                <strong style={{ color: "#142238", fontSize: "25px", lineHeight: 1.1 }}>{stats.job_cards.total}</strong>
                <span style={{ marginTop: "3px", color: "#708092", fontSize: "10px", fontWeight: 700 }}>Total Jobs</span>
              </div>
            </div>
            <div style={{ minWidth: 0, flex: 1, display: "flex", flexDirection: "column", gap: "11px" }}>
              {statusSegments.map((item) => (
                <div key={item.label} style={{ display: "grid", gridTemplateColumns: "10px minmax(0,1fr) auto", gap: "7px", alignItems: "center" }}>
                  <span style={{ width: "9px", height: "9px", borderRadius: "50%", background: item.color, boxShadow: `0 2px 5px ${item.color}55` }} />
                  <span style={{ minWidth: 0, color: "#435267", fontSize: "10px", fontWeight: 650 }}>{item.label}</span>
                  <strong style={{ color: "#25364D", fontSize: "10px", fontWeight: 800 }}>{item.value}</strong>
                </div>
              ))}
            </div>
          </div>
        </section>
        {/* Technician performance */}
        <section className="dashboard-analytics-card dashboard-technician-card" aria-labelledby="technician-performance-title">
          <div style={{ padding: "18px 20px 14px", borderBottom: "1px solid #EAF1ED", display: "flex", alignItems: "center", gap: "10px" }}>
            <div style={{ width: "34px", height: "34px", borderRadius: "11px", background: "linear-gradient(145deg,#D9F7E8,#A9E9CC)", color: "#059669", display: "grid", placeItems: "center", boxShadow: "0 5px 10px rgba(5,150,105,.14)" }}><Award size={19} /></div>
            <div>
              <h3 id="technician-performance-title" style={{ margin: 0, color: "#142238", fontSize: "15px", fontWeight: 800 }}>Technician Performance</h3>
              <p style={{ margin: "3px 0 0", color: "#718096", fontSize: "11px" }}>Top technicians by completed jobs</p>
            </div>
          </div>
          <div style={{ padding: "12px 18px 16px", flex: 1 }}>
            <div style={{ display: "grid", gridTemplateColumns: "minmax(105px,1fr) minmax(90px,1.25fr) 52px 44px", gap: "8px", padding: "0 0 9px", color: "#8391A1", fontSize: "9px", fontWeight: 800, textTransform: "uppercase", letterSpacing: ".05em" }}>
              <span>Technician</span><span>Completion</span><span style={{ textAlign: "right" }}>Done</span><span style={{ textAlign: "right" }}>Jobs</span>
            </div>
            {technicianPerformance.length === 0 ? (
              <div style={{ minHeight: "190px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", textAlign: "center", color: "#7B8A99", gap: "7px" }}>
                <Users size={25} color="#A2B4AA" />
                <strong style={{ color: "#536477", fontSize: "12px" }}>No technician job history</strong>
                <span style={{ fontSize: "10px" }}>Assigned jobs will appear here for the selected dates.</span>
              </div>
            ) : technicianPerformance.map((technician, index) => {
              const initials = technician.technician_name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
              const avatarBackgrounds = ["linear-gradient(145deg,#C8F5DF,#8BE0B8)", "linear-gradient(145deg,#D8EDFF,#9ACBFA)", "linear-gradient(145deg,#F0D9FF,#D7ACF7)", "linear-gradient(145deg,#FFE5D3,#FFC092)"];
              return (
                <div key={technician.technician_id} style={{ display: "grid", gridTemplateColumns: "minmax(105px,1fr) minmax(90px,1.25fr) 52px 44px", gap: "8px", alignItems: "center", padding: "10px 0", borderBottom: index === technicianPerformance.length - 1 ? "none" : "1px solid #EEF3F0" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", minWidth: 0 }}>
                    <div style={{ width: "30px", height: "30px", flex: "0 0 30px", borderRadius: "50%", background: avatarBackgrounds[index % avatarBackgrounds.length], color: "#176348", display: "grid", placeItems: "center", fontSize: "9px", fontWeight: 900, boxShadow: "0 3px 7px rgba(15,46,32,.10), inset 0 1px 0 rgba(255,255,255,.8)" }}>{initials || "T"}</div>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ color: "#23344A", fontSize: "10px", fontWeight: 800, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{technician.technician_name}</div>
                      <div style={{ color: "#94A3B8", fontSize: "9px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{technician.technician_skill || "Field technician"}</div>
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "7px", minWidth: 0 }}>
                    <div style={{ height: "8px", flex: 1, borderRadius: "20px", background: "#E8F0EC", overflow: "hidden", boxShadow: "inset 0 1px 2px rgba(15,46,32,.08)" }}><div style={{ width: `${technician.completionRate}%`, height: "100%", borderRadius: "20px", background: "linear-gradient(90deg,#07965B,#55D39A)", boxShadow: "0 2px 5px rgba(7,150,91,.22)" }} /></div>
                    <strong style={{ width: "30px", color: "#2D7659", fontSize: "10px", textAlign: "right" }}>{technician.completionRate}%</strong>
                  </div>
                  <strong style={{ color: "#1E344B", fontSize: "11px", textAlign: "right" }}>{technician.completed}</strong>
                  <span style={{ color: "#64748B", fontSize: "10px", textAlign: "right" }}>{technician.total}</span>
                </div>
              );
            })}
          </div>
          <div style={{ margin: "0 18px 14px", padding: "9px 11px", borderRadius: "10px", background: "linear-gradient(90deg,#EFFAF4,#F7FBF9)", color: "#668074", fontSize: "9px", display: "flex", alignItems: "center", gap: "6px" }}>
            <CalendarCheck size={13} color="#07965B" /> Completion rate is based on assigned jobs in the selected date range.
          </div>
        </section>
      </div>

      {/* Service category breakdown + SLA health */}
      <div className="dashboard-analytics-bottom-grid">
        <section className="dashboard-analytics-card" aria-labelledby="service-category-title">
          <div style={{ padding: "18px 20px 14px", borderBottom: "1px solid #EAF1ED", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "10px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <div style={{ width: "34px", height: "34px", borderRadius: "11px", background: "linear-gradient(145deg,#D9F7E8,#A9E9CC)", color: "#059669", display: "grid", placeItems: "center", boxShadow: "0 5px 10px rgba(5,150,105,.14)" }}><Layers size={19} /></div>
              <div>
                <h3 id="service-category-title" style={{ margin: 0, color: "#142238", fontSize: "15px", fontWeight: 800 }}>Service Category Breakdown</h3>
                <p style={{ margin: "3px 0 0", color: "#718096", fontSize: "11px" }}>Jobs by service type in the selected range</p>
              </div>
            </div>
            <span style={{ borderRadius: "20px", padding: "6px 10px", color: "#17825A", background: "#EAF8F0", fontSize: "10px", fontWeight: 800 }}>{selectedJobs.length} jobs</span>
          </div>
          <div
            className="dashboard-category-grid"
            style={{
              padding: "16px 12px",
              boxSizing: "border-box",
              alignItems: "center",
              justifyItems: "center",
              gap: "12px",
            }}
          >
            {categoryPerformance.map((category) => {
              const CategoryIcon = category.icon;

              return (
                <div
                  key={category.name}
                  className="dashboard-category-tile"
                  style={{
                    width: "100%",
                    maxWidth: "128px",
                    aspectRatio: "1 / 1",
                    justifySelf: "center",
                    borderRadius: "50%",
                    padding: "9px",
                    background: `radial-gradient(circle at 30% 22%, #FFFFFF 0%, ${category.tint} 58%, #F8FCFA 100%)`,
                    border: `1px solid ${category.color}45`,
                    boxShadow: "0 10px 20px rgba(15,46,32,0.08), 0 3px 6px rgba(15,46,32,0.04), inset 0 2px 5px rgba(255,255,255,0.95), inset 0 -3px 7px rgba(15,46,32,0.035)",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    textAlign: "center",
                    gap: "8px",
                    transition: "all 0.2s ease",
                    minWidth: 0,
                    boxSizing: "border-box",
                  }}
                >
                  {/* Circular service icon */}
                  <div
                    style={{
                      width: "36px",
                      height: "36px",
                      flexShrink: 0,
                      borderRadius: "50%",
                      color: "#FFFFFF",
                      background: `linear-gradient(145deg, ${category.color}, ${category.color}D9)`,
                      display: "grid",
                      placeItems: "center",
                      boxShadow: `0 5px 12px ${category.color}45, inset 0 2px 3px rgba(255,255,255,0.3), inset 0 -2px 3px rgba(0,0,0,0.08)`,
                    }}
                  >
                    <CategoryIcon size={18} />
                  </div>

                  {/* Service name */}
                  <strong
                    style={{
                      color: "#27394E",
                      fontSize: "9px",
                      fontWeight: 750,
                      lineHeight: 1.3,
                      maxWidth: "105px",
                      minHeight: "22px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    {category.name}
                  </strong>

                  {/* Job count */}
                  <div
                    style={{
                      display: "flex",
                      alignItems: "baseline",
                      justifyContent: "center",
                      gap: "5px",
                    }}
                  >
                    <strong
                      style={{
                        color: "#142238",
                        fontSize: "21px",
                        fontWeight: 800,
                        lineHeight: 1,
                      }}
                    >
                      {category.count}
                    </strong>

                    <span
                      style={{
                        color: "#748497",
                        fontSize: "9px",
                        fontWeight: 650,
                      }}
                    >
                      jobs
                    </span>
                  </div>

                  {/* Category count indicator */}
                  <div
                    style={{
                      width: "65%",
                      height: "4px",
                      borderRadius: "10px",
                      background: "rgba(148,163,184,0.17)",
                      overflowX: "auto",
                overflowY: "hidden",
                    }}
                  >
                    <div
                      style={{
                        width: `${(category.count / maxCategoryCount) * 100}%`,
                        height: "100%",
                        borderRadius: "10px",
                        background: `linear-gradient(90deg, ${category.color}, ${category.color}99)`,
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </section>
        <section className="dashboard-analytics-card" aria-labelledby="sla-health-title">
          <div style={{ padding: "18px 20px 14px", borderBottom: "1px solid #EAF1ED", display: "flex", alignItems: "center", gap: "10px" }}>
            <div style={{ width: "34px", height: "34px", borderRadius: "11px", background: "linear-gradient(145deg,#D9F7E8,#A9E9CC)", color: "#059669", display: "grid", placeItems: "center", boxShadow: "0 5px 10px rgba(5,150,105,.14)" }}><Gauge size={19} /></div>
            <div>
              <h3 id="sla-health-title" style={{ margin: 0, color: "#142238", fontSize: "15px", fontWeight: 800 }}>SLA &amp; Response Health</h3>
              <p style={{ margin: "3px 0 0", color: "#718096", fontSize: "11px" }}>Live deadline and assignment indicators</p>
            </div>
          </div>
          <div style={{ padding: "18px 20px 12px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "18px", flex: 1 }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minWidth: 0 }}>
              <svg viewBox="0 0 160 100" width="100%" style={{ maxWidth: "170px", overflow: "visible" }} role="img" aria-label={slaCompliance === null ? "SLA compliance unavailable" : `${slaCompliance}% of active jobs are within SLA`}>
                <path d="M15 82 A65 65 0 0 1 145 82" fill="none" stroke="#E4EEE8" strokeWidth="13" strokeLinecap="round" />
                {slaCompliance !== null && <path d="M15 82 A65 65 0 0 1 145 82" fill="none" stroke="url(#slaGaugeGradient)" strokeWidth="13" strokeLinecap="round" strokeDasharray={`${(slaCompliance / 100) * 204.2} 204.2`} />}
                <defs><linearGradient id="slaGaugeGradient" x1="0" y1="0" x2="1" y2="0"><stop offset="0%" stopColor="#0A9A60" /><stop offset="100%" stopColor="#5BD99D" /></linearGradient></defs>
                <text x="80" y="72" textAnchor="middle" fontSize="25" fontWeight="800" fill="#15263D">{slaCompliance === null ? "—" : `${slaCompliance}%`}</text>
              </svg>
              <strong style={{ marginTop: "-3px", color: "#263B50", fontSize: "11px" }}>Within SLA</strong>
              <span style={{ marginTop: "4px", color: "#8A98A6", fontSize: "9px", textAlign: "center" }}>{activeJobsWithSla.length} active jobs tracked</span>
            </div>
            <div style={{ borderLeft: "1px solid #E6EEE9", paddingLeft: "16px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minWidth: 0 }}>
              <div style={{ width: "92px", height: "92px", borderRadius: "50%", background: "conic-gradient(from 220deg,#0C9860 0deg,#6ADCA6 260deg,#E8F2EC 260deg 360deg)", padding: "8px", boxSizing: "border-box", boxShadow: "0 8px 15px rgba(5,150,105,.12), inset 0 1px 0 rgba(255,255,255,.9)" }}>
                <div style={{ width: "100%", height: "100%", borderRadius: "50%", background: "linear-gradient(145deg,#FFFFFF,#F3F8F5)", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", boxShadow: "inset 0 2px 5px rgba(15,46,32,.08)" }}>
                  <Timer size={17} color="#07965B" />
                  <strong style={{ marginTop: "3px", color: "#15263D", fontSize: "20px", lineHeight: 1 }}>{averageAssignmentMinutes === null ? "—" : `${averageAssignmentMinutes}`}</strong>
                  <span style={{ marginTop: "2px", color: "#81908F", fontSize: "9px", fontWeight: 700 }}>{averageAssignmentMinutes === null ? "minutes" : "minutes"}</span>
                </div>
              </div>
              <strong style={{ marginTop: "8px", color: "#263B50", fontSize: "11px" }}>Avg. Assignment Time</strong>
              <span style={{ marginTop: "4px", color: "#8A98A6", fontSize: "9px", textAlign: "center" }}>{assignmentDurations.length} timed assignments</span>
            </div>
          </div>
          <div style={{ display: "flex", gap: "8px", padding: "0 18px 16px", flexWrap: "wrap" }}>
            <div style={{ flex: 1, minWidth: "110px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px", padding: "9px 11px", borderRadius: "10px", background: "#FFF3F1", border: "1px solid #FCE1DC" }}>
              <span style={{ color: "#A45A50", fontSize: "9px", fontWeight: 750 }}>Overdue</span><strong style={{ color: "#D34B40", fontSize: "13px" }}>{overdueSlaCount}</strong>
            </div>
            <div style={{ flex: 1, minWidth: "110px", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px", padding: "9px 11px", borderRadius: "10px", background: "#FFF8E9", border: "1px solid #F6E9C9" }}>
              <span style={{ color: "#9A7429", fontSize: "9px", fontWeight: 750 }}>Due in 1 hour</span><strong style={{ color: "#C58A12", fontSize: "13px" }}>{atRiskSlaCount}</strong>
            </div>
          </div>
          {averageAssignmentMinutes === null && (
            <p style={{ margin: "0 18px 14px", color: "#98A4AE", fontSize: "9px", lineHeight: 1.4 }}>Assignment time will appear when the jobs API provides assignment timestamps.</p>
          )}
        </section>
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