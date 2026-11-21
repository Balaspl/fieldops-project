import React, {
  useState,
  useEffect,
  useCallback,
  useRef,
  useMemo,
} from "react";
import {
  getAllTechnicians,
  createTechnician,
  updateTechnician,
  updateTechnicianAvailability,
  getUniqueZones,
} from "../services/technicianService";
import usePageVisibility from "../hooks/usePageVisibility";
import useInterval from "../hooks/useInterval";
import StatusBadge from "../components/ui/StatusBadge";
import { Eye, Pencil, UserMinus, RotateCcw, X } from "lucide-react";
import EmptyState from "../components/ui/EmptyState";
import { SkillComboSelect } from "../components/ui/SkillComboSelect";
import ConfirmationDialog from "../components/ui/ConfirmationDialog";
import LoadingSpinner from "../components/ui/LoadingSpinner";
import { getJobs } from "../services/planningService";
import { BriefcaseBusiness, CircleCheck, PauseCircle, Play, Plus, Search } from "lucide-react";
import technicianBanner from "../assets/technician-banner.png";

const PAGE_SIZE = 8;
const REFRESH_MS = 3000;
const STALE_MS = 120_000;
const SKILLS = [
  "HVAC Repair",
  "Electrical",
  "Plumbing",
  "Network Support",
  "General Maintenance",
];

interface NormalizedTech {
  id: number | string;
  name: string;
  status: string;
  skill: string;
  location: string;
  currentJobs: number;
  maxJobs: number;
  lastPing: string | null;
  phone?: string;
  email?: string;
}

interface TechFormData {
  technician_name: string;
  technician_skill: string;
  technician_location: string;
  technician_status: string;
}

interface RefreshMetrics {
  successCount: number;
  failureCount: number;
  lastLatencyMs: number | null;
}

function normalizeStatus(s: string) {
  const l = (s || "").toLowerCase();
  if (l === "available") return "Available";
  if (l === "busy") return "Busy";
  if (l === "assigned") return "Assigned";
  if (l === "offline") return "Offline";
  if (l === "en route" || l === "en_route") return "En Route";
  if (l === "on site" || l === "on_site") return "On Site";
  if (l === "on break" || l === "on_break") return "On Break";
  if (l === "suspended") return "Suspended";
  if (l === "deactivated") return "Deactivated";
  return s || "Unknown";
}

function displayStatus(s: string) {
  return String(s || "").toLowerCase() === "available" ? "Online" : normalizeStatus(s);
}

function getInitials(n = "") {
  return n
    .trim()
    .split(/\s+/)
    .map((w) => w[0]?.toUpperCase() || "")
    .slice(0, 2)
    .join("");
}
function formatAgo(ts: string | number | Date | null) {
  if (!ts) return "—";
  try {
    const diff = Math.round((Date.now() - new Date(ts).getTime()) / 60000);
    if (diff < 1) return "just now";
    if (diff < 60) return `${diff}m ago`;
    const h = Math.round(diff / 60);
    if (h < 24) return `${h}h ago`;
    return new Date(ts).toLocaleDateString("en-GB", { day: "2-digit", month: "2-digit", year: "numeric" });
  } catch {
    return String(ts);
  }
}
function normTech(t: any): NormalizedTech {
  const maxJobs = 5;

  const firstNonEmpty = (...values: unknown[]): string => {
    const value = values.find(
      (candidate) =>
        candidate !== null &&
        candidate !== undefined &&
        String(candidate).trim() !== ""
    );

    return value == null ? "—" : String(value).trim();
  };

  return {
    id: t.technician_id ?? t.id ?? Math.random(),
    name: t.technician_name ?? t.name ?? "Unknown",
    status: t.technician_status ?? t.status ?? "Unknown",
    skill: t.technician_skill ?? t.skills ?? t.skill ?? "—",
    location: t.technician_location ?? t.zone ?? t.location ?? "—",
    currentJobs: t.current_jobs ?? t.active_jobs ?? 0,
    maxJobs,
    lastPing: t.last_ping ?? t.updated_at ?? null,

    phone: firstNonEmpty(
      t.mobile_number,
      t.phone_number,
      t.phone,
      t.technician_phone
    ),

    email: firstNonEmpty(
      t.email,
      t.technician_email
    ),
  };
}
function wPct(cur: number, max: number) {
  return max > 0 ? Math.min(Math.round((cur / max) * 100), 100) : 0;
}
function wColor(p: number) {
  return p >= 90 ? "high" : p >= 60 ? "mid" : "low";
}

function normalizedJobStatus(status: unknown) {
  return String(status ?? "unknown").trim().toUpperCase().replace(/[\s_-]/g, "");
}
function countAcceptedOpenJobs(jobs: any[]) {
  const openAcceptedStatuses = new Set([
    "ACCEPTED", "ENROUTE", "ONSITE", "INPROGRESS", "PAUSED",
    "ONHOLD", "HOLD", "ESCALATED",
  ]);
  return jobs.filter((job) => openAcceptedStatuses.has(normalizedJobStatus(job.status))).length;
}
function displayJobStatus(status: unknown) {
  return String(status ?? "Unknown").replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
function formatJobDate(value: unknown) {
  if (!value) return "—";
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("en-GB", { day: "2-digit", month: "2-digit", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true });
}

const styles = {
  tldPage: {
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

  tldToast: {
    position: "fixed",
    top: "80px",
    right: "24px",
    padding: "12px 20px",
    borderRadius: "10px",
    fontSize: "11.5px",
    fontWeight: 600,
    boxShadow: "0 4px 16px rgba(0,0,0,.12)",
    zIndex: 2000,
    display: "flex",
    alignItems: "center",
    gap: "8px",
    animation: "tld-slide-in .3s ease",
  } as React.CSSProperties,

  tldCountdownRail: {
    height: "2px",
    background: "#E3ECE7",
    overflow: "hidden",
    borderRadius: 0,
  } as React.CSSProperties,

  tldCountdownFill: {
    height: "100%",
    background: "#7AAE8A",
    transition: "width 1s linear",
  } as React.CSSProperties,

  tldBgErrorBanner: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    background: "#FEF0D6",
    border: "1px solid #F0D09A",
    borderRadius: "8px",
    padding: "10px 14px",
    fontSize: "11px",
    fontWeight: 500,
    color: "#7A5120",
    animation: "tld-slide-in .25s ease",
    flexWrap: "wrap",
    boxSizing: "border-box",
  } as React.CSSProperties,

  tldBgErrorRetry: {
    background: "none",
    border: "1.5px solid #D9A441",
    color: "#7A5120",
    borderRadius: "6px",
    padding: "4px 12px",
    fontSize: "10px",
    fontWeight: 700,
    cursor: "pointer",
    transition: "all .2s",
    marginLeft: "auto",
  } as React.CSSProperties,

  tldTableCard: {
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

  tldCardHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    flexWrap: "wrap",
    gap: "10px",
    padding: "10px 16px",
    borderBottom: "1px solid #E3ECE7",
    boxSizing: "border-box",
  } as React.CSSProperties,

  tldSectionBadge: {
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

  tldCardSubtitle: {
    fontSize: "11px",
    color: "#6B7280",
    marginTop: "3px",
  } as React.CSSProperties,

  tldHeaderRight: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    flexWrap: "wrap",
  } as React.CSSProperties,

  tldRefreshBar: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    fontSize: "10.5px",
    color: "#6B7280",
    fontWeight: 500,
    padding: "0 2px",
    flexWrap: "wrap",
  } as React.CSSProperties,

  tldLiveDot: {
    width: "8px",
    height: "8px",
    borderRadius: "50%",
    background: "#22C55E",
    boxShadow: "0 0 0 0 rgba(34, 197, 94, 0.45)",
    animation: "tldLivePulse 1.5s ease-in-out infinite",
    cursor: "pointer",
    flexShrink: 0,
  },

  tldRefreshSpinner: {
    width: "13px",
    height: "13px",
    border: "2px solid #D0DCDA",
    borderTopColor: "#7AAE8A",
    borderRadius: "50%",
    animation: "tld-spin .7s linear infinite",
    flexShrink: 0,
  } as React.CSSProperties,

  tldRefreshFetching: {
    color: "#5C9470",
    fontWeight: 600,
  } as React.CSSProperties,

  tldRefreshLast: {
    color: "#6B7280",
  } as React.CSSProperties,

  tldRefreshPaused: {
    display: "inline-flex",
    alignItems: "center",
    gap: "4px",
    background: "#FEF0D6",
    color: "#7A5120",
    borderRadius: "20px",
    padding: "2px 8px",
    fontSize: "9.5px",
    fontWeight: 700,
    letterSpacing: ".02em",
  } as React.CSSProperties,

  tldStaleWarning: {
    display: "inline-flex",
    alignItems: "center",
    gap: "5px",
    background: "#FDF2F2",
    border: "1px solid #F5C6C6",
    borderRadius: "6px",
    padding: "3px 10px",
    fontSize: "10px",
    fontWeight: 600,
    color: "#9B3A3A",
  } as React.CSSProperties,

  tldMetricsWrap: {
    position: "relative",
    display: "inline-flex",
    alignItems: "center",
  } as React.CSSProperties,

  tldMetricsTrigger: {
    background: "none",
    border: "1.5px solid #E3ECE7",
    borderRadius: "6px",
    padding: "2px 8px",
    fontSize: "10.5px",
    fontWeight: 600,
    color: "#6B7280",
    fontFamily: "'Inter', sans-serif",
    cursor: "pointer",
    transition: "all .15s",
    display: "flex",
    alignItems: "center",
    gap: "4px",
  } as React.CSSProperties,

  tldMetricsPanel: {
    position: "absolute",
    top: "calc(100% + 8px)",
    right: 0,
    background: "#FFFFFF",
    border: "1px solid #E3ECE7",
    borderRadius: "10px",
    padding: "14px 16px",
    boxShadow: "0 8px 24px rgba(47,79,62,.12)",
    zIndex: 300,
    minWidth: "220px",
    animation: "tld-fade-in .15s ease",
    boxSizing: "border-box",
  } as React.CSSProperties,

  tldMetricsTitle: {
    fontSize: "9px",
    fontWeight: 700,
    color: "#6B7280",
    textTransform: "uppercase",
    letterSpacing: ".06em",
    margin: "0 0 10px 0",
  } as React.CSSProperties,

  tldMetricsRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    fontSpread: "11px",
    padding: "5px 0",
    borderBottom: "1px solid #F0F4F2",
    fontSize: "11px",
  } as React.CSSProperties,

  tldMetricsLabel: {
    color: "#6B7280",
    fontWeight: 500,
  } as React.CSSProperties,

  tldMetricsValue: {
    fontWeight: 700,
    color: "#2F4F3E",
  } as React.CSSProperties,

  tldRefreshBtn: {
  background: "#FFFFFF",
  border: "1.5px solid #E3ECE7",
  color: "#2F4F3E",
  padding: "6px 12px",
  borderRadius: "8px",
  fontSize: "10px",
  fontWeight: 600,
  fontFamily: "'Inter', sans-serif",
  cursor: "pointer",
  transition: "all .2s",
  boxShadow: "0 1px 3px rgba(47,79,62,.06)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: "6px",
  width: "100px",
} as React.CSSProperties,

  tldRefreshBtnSpinner: {
    width: "12px",
    height: "12px",
    border: "2px solid #D0DCDA",
    borderTopColor: "#7AAE8A",
    borderRadius: "50%",
    animation: "tld-spin .7s linear infinite",
    flexShrink: 0,
  } as React.CSSProperties,

  tldAddBtn: {
    background: "#7AAE8A",
    color: "#fff",
    border: "none",
    padding: "6px 12px",
    borderRadius: "8px",
    fontSize: "10px",
    fontWeight: 700,
    fontFamily: "'Inter', sans-serif",
    cursor: "pointer",
    transition: "background .2s",
    boxShadow: "0 2px 6px rgba(122,174,138,.3)",
    display: "flex",
    alignItems: "center",
    gap: "6px",
  } as React.CSSProperties,

  tldFilterBar: {
    background: "transparent",
    border: "none",
    borderRadius: 0,
    padding: "10px 16px",
    display: "flex",
    alignItems: "flex-end",
    gap: "12px",
    flexWrap: "wrap",
    boxShadow: "none",
    borderBottom: "1px solid #E3ECE7",
    boxSizing: "border-box",
  } as React.CSSProperties,

  tldFilterGroup: {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
    minWidth: "160px",
  } as React.CSSProperties,

  tldFilterGroupSearch: {
    flex: 1,
    minWidth: "200px",
  } as React.CSSProperties,

  tldFilterGroupLabel: {
    fontSize: "9px",
    fontWeight: 700,
    color: "#6B7280",
    textTransform: "uppercase",
    letterSpacing: ".05em",
  } as React.CSSProperties,

  tldSearchWrap: {
    position: "relative",
  } as React.CSSProperties,

  tldSearchInput: {
    width: "100%",
    padding: "8px 10px 8px 30px",
    border: "1.5px solid #E3ECE7",
    borderRadius: "8px",
    fontSize: "11px",
    fontFamily: "'Inter', sans-serif",
    color: "#1F2933",
    background: "#FFFFFF",
    outline: "none",
    transition: "border-color .2s, box-shadow .2s",
    boxSizing: "border-box",
  } as React.CSSProperties,

  tldSelect: {
    padding: "8px 10px",
    border: "1.5px solid #E3ECE7",
    borderRadius: "8px",
    fontSize: "11px",
    fontFamily: "'Inter', sans-serif",
    color: "#1F2933",
    background: "#FFFFFF",
    outline: "none",
    cursor: "pointer",
    transition: "border-color .2s",
    width: "100%",
    boxSizing: "border-box",
  } as React.CSSProperties,

  tldFilterClear: {
    padding: "8px 14px",
    background: "#F6FAF8",
    border: "1.5px solid #E3ECE7",
    borderRadius: "8px",
    fontSize: "10px",
    fontWeight: 600,
    color: "#6B7280",
    cursor: "pointer",
    transition: "all .2s",
    whiteSpace: "nowrap",
    alignSelf: "flex-end",
  } as React.CSSProperties,

  tldTableMeta: {
    padding: "14px 20px 0",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    flexWrap: "wrap",
    gap: "8px",
    boxSizing: "border-box",
  } as React.CSSProperties,

  tldResultsCount: {
    fontSize: "10px",
    color: "#6B7280",
    fontWeight: 500,
    margin: 0,
  } as React.CSSProperties,

  tldTableWrap: {
    overflowX: "auto",
    overflowY: "auto",
    flex: 1,
    minHeight: 0,
  } as React.CSSProperties,

  tldTable: {
    width: "100%",
    borderCollapse: "collapse",
    minWidth: "700px",
  } as React.CSSProperties,

  tldTableTh: {
    padding: "4px 12px",
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

  tldTableTd: {
    padding: "4px 12px",
    fontSize: "11px",
    color: "#1F2933",
    verticalAlign: "middle",
    borderBottom: "1px solid #F0F4F2",
  } as React.CSSProperties,

  tldNameCell: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
  } as React.CSSProperties,

  tldAvatar: {
    width: "34px",
    height: "34px",
    minWidth: "34px",
    borderRadius: "50%",
    background: "linear-gradient(135deg, #7AAE8A, #5C9470)",
    color: "#fff",
    fontSize: "12px",
    fontWeight: 700,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  } as React.CSSProperties,

  tldNameInfo: {
    display: "flex",
    flexDirection: "column",
  } as React.CSSProperties,

  tldNamePrimary: {
    fontWeight: 600,
    color: "#1F2933",
    fontSize: "12px",
    lineHeight: 1.3,
  } as React.CSSProperties,

  tldNameSecondary: {
    fontSize: "9px",
    color: "#6B7280",
    marginTop: "1px",
  } as React.CSSProperties,

  tldWorkloadCell: {
    minWidth: "120px",
  } as React.CSSProperties,

  tldWorkloadNumbers: {
    fontSize: "10.5px",
    fontWeight: 600,
    color: "#2F4F3E",
    marginBottom: "4px",
  } as React.CSSProperties,

  tldWorkloadTrack: {
    background: "#E3ECE7",
    borderRadius: "4px",
    height: "5px",
    overflow: "hidden",
  } as React.CSSProperties,

  tldWorkloadFill: {
    height: "100%",
    borderRadius: "4px",
    transition: "width .4s ease",
  } as React.CSSProperties,

  tldPing: {
    fontSize: "10px",
    color: "#6B7280",
  } as React.CSSProperties,

  tldActions: {
    display: "flex",
    gap: "12px",
    alignItems: "center",
  } as React.CSSProperties,

  iconActionBtn: {
    background: "none",
    border: "none",
    cursor: "pointer",
    padding: "4px",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: "4px",
    transition: "transform .15s, opacity .15s",
    outline: "none",
  } as React.CSSProperties,

  tldStateCell: {
    textAlign: "center",
    padding: "16px 20px",
    verticalAlign: "middle",
  } as React.CSSProperties,

  tldRetryBtn: {
    padding: "8px 20px",
    background: "#7AAE8A",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    fontSize: "11.5px",
    fontWeight: 600,
    cursor: "pointer",
    transition: "background .2s",
  } as React.CSSProperties,

  tldPagination: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "6px 12px",
    borderTop: "1px solid #E3ECE7",
    flexWrap: "wrap",
    gap: "6px",
    background: "#FFFFFF",
    borderBottomLeftRadius: "12px",
    borderBottomRightRadius: "12px",
    boxSizing: "border-box",
  } as React.CSSProperties,

  tldPageInfo: {
    fontSize: "11px",
    color: "#6B7280",
    fontWeight: 500,
  } as React.CSSProperties,

  tldPageControls: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
  } as React.CSSProperties,

  tldPageBtn: {
    padding: "3px 8px",
    background: "#FFFFFF",
    border: "1.5px solid #E3ECE7",
    borderRadius: "6px",
    fontSize: "10px",
    fontWeight: 600,
    color: "#2F4F3E",
    cursor: "pointer",
    transition: "all .2s",
  } as React.CSSProperties,

  tldPageNumbers: {
    display: "flex",
    gap: "4px",
  } as React.CSSProperties,

  tldPageNum: {
    width: "22px",
    height: "22px",
    borderRadius: "6px",
    border: "1.5px solid #E3ECE7",
    background: "#FFFFFF",
    fontSize: "10px",
    fontWeight: 600,
    color: "#6B7280",
    cursor: "pointer",
    padding: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    transition: "all .2s",
  } as React.CSSProperties,

  tldPageNumActive: {
    background: "#7AAE8A",
    borderColor: "#7AAE8A",
    color: "#fff",
  } as React.CSSProperties,

  tldSidebar: {
    position: "fixed",
    top: 0,
    width: "440px",
    height: "100vh",
    background: "#FFFFFF",
    boxShadow: "-4px 0 32px rgba(47,79,62,.12)",
    zIndex: 1000,
    transition: "right .4s cubic-bezier(.4, 0, .2, 1)",
    display: "flex",
    flexDirection: "column",
    boxSizing: "border-box",
  } as React.CSSProperties,

  tldSidebarHead: {
    padding: "22px 24px",
    borderBottom: "1px solid #E3ECE7",
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    background: "#F8FBF9",
    boxSizing: "border-box",
  } as React.CSSProperties,

  tldSidebarHeadH3: {
    fontSize: "14.5px",
    fontWeight: 700,
    color: "#2F4F3E",
    margin: 0,
  } as React.CSSProperties,

  tldSidebarClose: {
    background: "none",
    border: "none",
    fontSize: "22px",
    color: "#6B7280",
    cursor: "pointer",
    width: "32px",
    height: "32px",
    borderRadius: "6px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    transition: "background .15s",
  } as React.CSSProperties,

  tldSidebarBody: {
    flex: 1,
    padding: "24px",
    overflowY: "auto",
    boxSizing: "border-box",
  } as React.CSSProperties,

  tldSidebarOverlay: {
    position: "fixed",
    top: 0,
    left: 0,
    width: "100vw",
    height: "100vh",
    background: "rgba(31,41,51,.3)",
    backdropFilter: "blur(2px)",
    zIndex: 999,
  } as React.CSSProperties,

  tldDetailHero: {
    display: "flex",
    alignItems: "center",
    gap: "14px",
    padding: "18px",
    background: "#F6FAF8",
    borderRadius: "10px",
    border: "1px solid #E3ECE7",
    marginBottom: "20px",
    boxSizing: "border-box",
  } as React.CSSProperties,

  tldDetailAvatar: {
    width: "52px",
    height: "52px",
    borderRadius: "50%",
    background: "linear-gradient(135deg, #7AAE8A, #5C9470)",
    color: "#fff",
    fontSize: "18px",
    fontWeight: 700,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  } as React.CSSProperties,

  tldDetailName: {
    fontSize: "13.5px",
    fontWeight: 700,
    color: "#2F4F3E",
  } as React.CSSProperties,

  tldDetailMeta: {
    fontSize: "10px",
    color: "#6B7280",
    marginTop: "3px",
  } as React.CSSProperties,

  tldDetailSectionTitle: {
    fontSize: "9px",
    fontWeight: 700,
    color: "#6B7280",
    textTransform: "uppercase",
    letterSpacing: ".05em",
    marginBottom: "10px",
    marginTop: 0,
  } as React.CSSProperties,

  tldDetailRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "8px 0",
    borderBottom: "1px solid #F0F4F2",
    fontSize: "10.5px",
  } as React.CSSProperties,

  tldDetailLabel: {
    color: "#6B7280",
    fontWeight: 500,
  } as React.CSSProperties,

  tldDetailValue: {
    color: "#1F2933",
    fontWeight: 600,
  } as React.CSSProperties,

  popupOverlay: {
    position: "fixed",
    inset: 0,
    background: "rgba(31, 41, 51, 0.4)",
    zIndex: 2000,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  } as React.CSSProperties,
  successPopup: {
    background: "#FFFFFF",
    borderRadius: "16px",
    padding: "32px",
    maxWidth: "380px",
    width: "90%",
    textAlign: "center",
    boxShadow: "0 20px 50px rgba(47, 79, 62, 0.15)",
  } as React.CSSProperties,
  successIcon: {
    width: "52px",
    height: "52px",
    background: "#DDEEE5",
    color: "#2F4F3E",
    borderRadius: "50%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: "24px",
    fontWeight: 800,
    margin: "0 auto 14px",
  } as React.CSSProperties,
  techNameBox: {
    background: "#F6FAF8",
    borderRadius: "6px",
    padding: "6px 14px",
    fontSize: "13px",
    color: "#2F4F3E",
    marginBottom: "10px",
    display: "inline-block",
    border: "1px solid #E3ECE7",
  } as React.CSSProperties,
  popupCloseBtn: {
    background: "#7AAE8A",
    color: "#fff",
    border: "none",
    padding: "10px 28px",
    borderRadius: "8px",
    fontWeight: 700,
    fontSize: "13px",
    cursor: "pointer",
    transition: "background .2s",
  } as React.CSSProperties,
};

const localCss = `
  .tld-metrics-trigger-style:hover {
    border-color: #7AAE8A !important;
    color: #2F4F3E !important;
    background-color: #F6FAF8 !important;
  }
  .tld-refresh-btn-style:hover:not(:disabled) {
    background-color: #F6FAF8 !important;
    border-color: #7AAE8A !important;
  }
  .tld-add-btn-style:hover {
    background-color: #5C9470 !important;
  }
  .tld-search-input-style:focus {
    border-color: #7AAE8A !important;
    box-shadow: 0 0 0 3px rgba(122,174,138,.12) !important;
  }
  .tld-select-style:focus {
    border-color: #7AAE8A !important;
    box-shadow: 0 0 0 3px rgba(122,174,138,.12) !important;
  }
  .tld-filter-clear-style:hover {
    border-color: #7AAE8A !important;
    color: #2F4F3E !important;
    background-color: #EAF4EE !important;
  }
  .tld-page-btn:hover:not(:disabled) {
    background-color: #EAF4EE !important;
    border-color: #7AAE8A !important;
  }
  .tld-page-num:hover {
    border-color: #7AAE8A !important;
    color: #2F4F3E !important;
  }
  .tld-table th.sortable-style:hover {
    color: #2F4F3E !important;
  }
  tr.tld-row-style {
    cursor: pointer !important;
  }
  tr.tld-row-style:hover td {
    background-color: #EAF4EE !important;
  }
  .tech-profile-technician-option {
    transition: transform .16s ease, box-shadow .16s ease !important;
  }
  .tech-profile-technician-option:hover,
  .tech-profile-technician-option:focus-visible {
    transform: translateY(-2px) scale(1.01) !important;
    box-shadow: 0 7px 16px rgba(25,75,51,.12) !important;
    background-color: #eaf8ef !important;
  }
  .tech-list-card {
    transition: transform .16s ease, box-shadow .16s ease, border-color .16s ease !important;
  }
  .tech-list-card:hover,
  .tech-list-card:focus-within {
    transform: translateY(-2px) scale(1.01) !important;
    box-shadow: 0 7px 16px rgba(25,75,51,.12) !important;
    border-color: #91c3a2 !important;
    background-color: #eaf8ef !important;
  }
  .icon-action-btn-style {
    transition: transform .15s, opacity .15s !important;
  }
  .icon-action-btn-style:hover {
    transform: scale(1.2) !important;
    opacity: .8 !important;
  }
  .icon-action-btn-style:active {
    transform: scale(0.9) !important;
  }
  .tld-sidebar-close-style:hover {
    background-color: #EAF4EE !important;
    color: #2F4F3E !important;
  }
  .tld-status-select-style:focus {
    border-color: #7AAE8A !important;
  }
  .tld-save-btn-style:hover:not(:disabled) {
    background-color: #5C9470 !important;
  }
  .tld-retry-btn-style:hover {
    background-color: #5C9470 !important;
  }
  
  .tld-skeleton-bar-style {
    border-radius: 6px !important;
    background: linear-gradient(90deg, #E8F0EC 25%, #F4F8F5 50%, #E8F0EC 75%) !important;
    background-size: 200% 100% !important;
    animation: tld-shimmer 1.5s infinite !important;
    height: 14px !important;
  }
  .tld-skeleton-avatar-style {
    width: 34px !important;
    height: 34px !important;
    border-radius: 50% !important;
    background: linear-gradient(90deg, #E8F0EC 25%, #F4F8F5 50%, #E8F0EC 75%) !important;
    background-size: 200% 100% !important;
    animation: tld-shimmer 1.5s infinite !important;
  }
  @keyframes tld-shimmer {
    0%   { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }
  @keyframes tld-spin {
    to { transform: rotate(360deg); }
  }
  @keyframes tld-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.35; }
  }
  .tld-live-loading-dot {
  width: 10px;
  height: 10px;
  display: inline-block;
  flex-shrink: 0;
  border-radius: 50%;
  background: #16A34A;
  box-shadow: 0 0 0 3px rgba(22, 163, 74, 0.12);
  animation: tld-pulse 2.2s ease-in-out infinite;
  } 

  @media (max-width: 768px) {
    .tld-header-responsive {
      flex-direction: column !important;
      align-items: flex-start !important;
      gap: 12px !important;
    }
    .tld-header-right-responsive {
      width: 100% !important;
      justify-content: space-between !important;
    }
    .tld-filter-bar-responsive {
      padding: 14px 16px !important;
      flex-direction: column !important;
      align-items: stretch !important;
    }
    .tld-filter-group-responsive {
      width: 100% !important;
    }
    .tld-search-input-style, .tld-select-style {
      width: 100% !important;
    }
    .tld-table-wrap-responsive {
      overflow-x: visible !important;
    }
    .tld-table-responsive thead {
      display: none !important;
    }
    .tld-table-responsive tbody tr {
      display: flex !important;
      flex-direction: column !important;
      padding: 16px !important;
      border: 1px solid #E3ECE7 !important;
      border-radius: 10px !important;
      margin-bottom: 12px !important;
      background: #FFFFFF !important;
      box-shadow: 0 1px 3px rgba(47,79,62,.04) !important;
    }
    .tld-table-responsive tbody td {
      display: flex !important;
      justify-content: space-between !important;
      align-items: center !important;
      padding: 8px 0 !important;
      border: none !important;
    }
    .tld-table-responsive tbody td:first-child {
      padding-top: 0 !important;
      border-bottom: 1px solid #F0F4F2 !important;
      margin-bottom: 8px !important;
      padding-bottom: 12px !important;
    }
    .tld-table-responsive tbody td:last-child {
      padding-bottom: 0 !important;
      margin-top: 8px !important;
      justify-content: flex-end !important;
    }
    .tld-table-responsive tbody td::before {
      content: attr(data-label) !important;
      font-size: 11px !important;
      font-weight: 700 !important;
      color: #6B7280 !important;
      text-transform: uppercase !important;
      display: block !important;
    }
    .tld-table-responsive tbody td:first-child::before,
    .tld-table-responsive tbody td:last-child::before {
      display: none !important;
    }
    .tld-sidebar-responsive {
      width: 100% !important;
      right: -100% !important;
    }
    .tld-sidebar-responsive.open {
      right: 0 !important;
    }
    .tld-metrics-panel-responsive {
      right: auto !important;
      left: 0 !important;
    }
  }
  @media (max-width: 560px) {
    .tld-filter-group-responsive {
      min-width: 100% !important;
    }
  }
  @media (max-width: 900px) {
    .tech-profile-layout { flex-direction: column !important; overflow-y: auto !important; }
    .tech-profile-sidebar { width: auto !important; min-width: 0 !important; max-height: 230px; }
    .tech-profile-counts { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
  }
  @media (max-width: 1100px) {
    .tech-profile-hero-details { margin-left: 0 !important; }
  }
  @media (max-width: 560px) {
    .tech-profile-hero { padding: 4px 8px !important; gap: 5px !important; flex-wrap: nowrap !important; min-height: 84px !important; }
    .tech-profile-hero-avatar { width: 36px !important; height: 36px !important; font-size: 14px !important; border-width: 2px !important; }
    .tech-profile-hero-divider { display: block !important; max-height: 52px !important; }
    .tech-profile-hero > div:nth-child(3) { min-width: 0 !important; flex: 0 1 82px !important; }
    .tech-profile-hero h1 { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px !important; margin-bottom: 3px !important; }
    .tech-profile-hero > div:nth-child(3) > div { gap: 4px !important; font-size: 7px !important; }
    .tech-profile-hero > div:nth-child(3) span:nth-child(2) { padding: 2px 4px !important; font-size: 7px !important; }
    .tech-profile-hero-details { flex: 0 1 40% !important; max-width: none !important; min-width: 0 !important; margin-left: 0 !important; grid-template-columns: repeat(2, minmax(0, 1fr)) !important; gap: 4px 7px !important; padding: 5px 7px !important; border-radius: 8px !important; }
    .tech-profile-hero-details strong { font-size: 7px !important; }
    .tech-profile-hero-details span { font-size: 6px !important; margin-bottom: 1px !important; }
  }

  @keyframes tldFadeInRow {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .tld-table-body tr {
    animation: tldFadeInRow 0.25s ease-out forwards !important;
  }
`;

function SkeletonRows({ n = 8 }) {
  return (
    <>
      {Array.from({ length: n }, (_, i) => (
        <tr key={i} className="tld-skeleton-row">
          <td style={styles.tldTableTd}>
            <div className="tld-name-cell">
              <div className="tld-skeleton-avatar-style" />
              <div className="tld-skeleton-name-wrap">
                <div
                  className="tld-skeleton-bar-style"
                  style={{ width: 120 }}
                />
                <div
                  className="tld-skeleton-bar-style"
                  style={{ width: 80, marginTop: 4, height: 10 }}
                />
              </div>
            </div>
          </td>
          <td style={styles.tldTableTd}>
            <div className="tld-skeleton-bar-style" style={{ width: 70 }} />
          </td>
          <td style={styles.tldTableTd}>
            <div className="tld-skeleton-bar-style" style={{ width: 90 }} />
          </td>
          <td style={styles.tldTableTd}>
            <div className="tld-skeleton-bar-style" style={{ width: 60 }} />
          </td>
          <td style={styles.tldTableTd}>
            <div className="tld-skeleton-bar-style" style={{ width: 100 }} />
          </td>
        </tr>
      ))}
    </>
  );
}

interface SortIconProps {
  col: string;
  sortKey: string;
  sortDir: string;
}

function SortIcon({ col, sortKey, sortDir }: SortIconProps) {
  if (sortKey !== col) return <span className="sort-icon">⇅</span>;
  return (
    <span className="sort-icon active">{sortDir === "asc" ? "↑" : "↓"}</span>
  );
}

interface MetricsPanelProps {
  metrics: RefreshMetrics;
  lastSuccessAt: number | null;
}

function MetricsPanel({ metrics, lastSuccessAt }: MetricsPanelProps) {
  const rate =
    metrics.successCount + metrics.failureCount === 0
      ? "—"
      : `${Math.round((metrics.successCount / (metrics.successCount + metrics.failureCount)) * 100)}%`;
  return (
    <div
      className="tld-metrics-panel-responsive"
      style={styles.tldMetricsPanel}
    >
      <p style={styles.tldMetricsTitle}>Refresh Metrics</p>
      <div style={styles.tldMetricsRow}>
        <span style={styles.tldMetricsLabel}>Success</span>
        <span style={{ ...styles.tldMetricsValue, color: "#2F7A3A" }}>
          {metrics.successCount}
        </span>
      </div>
      <div style={styles.tldMetricsRow}>
        <span style={styles.tldMetricsLabel}>Failures</span>
        <span
          style={{
            ...styles.tldMetricsValue,
            color: metrics.failureCount > 0 ? "#9B3A3A" : "#2F7A3A",
          }}
        >
          {metrics.failureCount}
        </span>
      </div>
      <div style={styles.tldMetricsRow}>
        <span style={styles.tldMetricsLabel}>Success rate</span>
        <span style={styles.tldMetricsValue}>{rate}</span>
      </div>
      <div style={styles.tldMetricsRow}>
        <span style={styles.tldMetricsLabel}>Last latency</span>
        <span style={styles.tldMetricsValue}>
          {metrics.lastLatencyMs != null ? `${metrics.lastLatencyMs}ms` : "—"}
        </span>
      </div>
      <div style={styles.tldMetricsRow}>
        <span style={styles.tldMetricsLabel}>Last success</span>
        <span style={styles.tldMetricsValue}>{formatAgo(lastSuccessAt)}</span>
      </div>
    </div>
  );
}

export default function TechnicianListPage({
  onAddTechnician,
}: {
  onAddTechnician?: () => void;
}) {
  const [technicians, setTechnicians] = useState<NormalizedTech[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(false);
  const [initError, setInitError] = useState("");
  const [bgError, setBgError] = useState("");

  const [search, setSearch] = useState("");
  const [debSearch, setDebSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [skillFilter, setSkillFilter] = useState("ALL");
  const [zoneFilter, setZoneFilter] = useState("ALL");
  const [sortKey, setSortKey] = useState("name");
  const [sortDir, setSortDir] = useState("asc");
  const [page, setPage] = useState(1);
  const [totalTechCount, setTotalTechCount] = useState(0);
  const [uniqueZones, setUniqueZones] = useState<string[]>([]);

  const [selected, setSelected] = useState<NormalizedTech | null>(null);
  const [techToDelete, setTechToDelete] = useState<NormalizedTech | null>(null);
  const [deleteTechBusy, setDeleteTechBusy] = useState(false);
  const [availabilityUpdatingId, setAvailabilityUpdatingId] = useState<string | null>(null);
  const [assignedJobs, setAssignedJobs] = useState<any[]>([]);
  const [loadedJobsTechnicianId, setLoadedJobsTechnicianId] = useState<number | string | null>(null);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [jobsError, setJobsError] = useState("");
  const [jobStatusFilter, setJobStatusFilter] = useState("ALL");
  const [technicianSearch, setTechnicianSearch] = useState("");
  const [showDeactivatedTechnicians, setShowDeactivatedTechnicians] = useState(false);
  const [profileTab, setProfileTab] = useState<"overview" | "jobs" | "activity">("jobs");

  const [isFormOpen, setIsFormOpen] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editingTechId, setEditingTechId] = useState<number | string | null>(
    null,
  );
  const [formLoading, setFormLoading] = useState(false);
  const [formErrors, setFormErrors] = useState<
    Partial<Record<keyof TechFormData, string>>
  >({});
  const [techFormData, setTechFormData] = useState<TechFormData>({
    technician_name: "",
    technician_skill: "",
    technician_location: "",
    technician_status: "Offline",
  });

  const openAddForm = () => {
    setIsEditing(false);
    setEditingTechId(null);
    setTechFormData({
      technician_name: "",
      technician_skill: "",
      technician_location: "",
      technician_status: "Offline",
    });
    setFormErrors({});
    setIsFormOpen(true);
  };

  const openEditForm = (tech: NormalizedTech) => {
    setIsEditing(true);
    setEditingTechId(tech.id);
    setTechFormData({
      technician_name: tech.name,
      technician_skill: tech.skill,
      technician_location: tech.location,
      technician_status: normalizeStatus(tech.status),
    });
    setFormErrors({});
    setIsFormOpen(true);
  };

  const closeForm = () => {
    setIsFormOpen(false);
  };

  const handleFormChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>,
  ) => {
    const { name, value } = e.target;
    setTechFormData((prev) => ({ ...prev, [name]: value }));
    setFormErrors((prev) => ({ ...prev, [name]: "" }));
  };

  const validateForm = () => {
    const errors: Partial<Record<keyof TechFormData, string>> = {};
    if (!techFormData.technician_name.trim())
      errors.technician_name = "Name is required";
    if (!techFormData.technician_skill.trim())
      errors.technician_skill = "Skill is required";
    if (!techFormData.technician_location.trim())
      errors.technician_location = "Location is required";
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleFormSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateForm()) return;
    setFormLoading(true);
    try {
      if (isEditing && editingTechId !== null) {
        await updateTechnician(editingTechId, techFormData);
        setPopup({
          show: true,
          title: "Technician Updated Successfully",
          message: "The technician details have been updated successfully.",
          name: techFormData.technician_name,
        });
      } else {
        await createTechnician(techFormData);
        setPopup({
          show: true,
          title: "Technician Created Successfully",
          message: "Your new technician has been registered successfully.",
          name: techFormData.technician_name,
        });
      }
      setIsFormOpen(false);
      fetchData(technicians.length > 0);
    } catch (err: any) {
      const msg =
        err.response?.data?.error ||
        err.response?.data?.detail ||
        "Failed to save technician.";
      showToast(msg, "error");
    } finally {
      setFormLoading(false);
    }
  };

  const [popup, setPopup] = useState<{
    show: boolean;
    title: string;
    message: string;
    name?: string;
  }>({
    show: false,
    title: "",
    message: "",
    name: "",
  });
  const [hoveredBtn, setHoveredBtn] = useState<string | null>(null);
  const closePopup = () => setPopup((prev) => ({ ...prev, show: false }));

  const [toast, setToast] = useState({ msg: "", type: "" });
  const toastTimer = useRef<any>(null);

  const [lastSuccessAt, setLastSuccessAt] = useState<number | null>(null);
  const [countdown, setCountdown] = useState(100);
  const [showMetrics, setShowMetrics] = useState(false);
  const [metrics, setMetrics] = useState<RefreshMetrics>({
    successCount: 0,
    failureCount: 0,
    lastLatencyMs: null,
  });

  const isTabActive = usePageVisibility();
  const metricsRef = useRef<HTMLDivElement>(null);

  const isStale = lastSuccessAt && Date.now() - lastSuccessAt > STALE_MS;

  const fetchAssignedJobs = useCallback(async (silent = false) => {
    if (!selected) {
      setAssignedJobs([]);
      return;
    }
    if (!silent) setJobsLoading(true);
    setJobsError("");
    try {
      const response = await getJobs({ technician_id: Number(selected.id) });
      const rows = Array.isArray(response?.data) ? response.data : [];
      setAssignedJobs(rows);
      setLoadedJobsTechnicianId(selected.id);
    } catch (error: any) {
      setJobsError(error?.response?.data?.detail || error?.response?.data?.error || "Unable to load this technician's jobs.");
      setLoadedJobsTechnicianId(selected.id);
    } finally {
      if (!silent) setJobsLoading(false);
    }
  }, [selected?.id]);

  useEffect(() => {
    setJobStatusFilter("ALL");
    setProfileTab("jobs");
    if (selected) fetchAssignedJobs(false);
    else setAssignedJobs([]);
  }, [selected?.id, fetchAssignedJobs]);

  useInterval(() => {
    if (selected && isTabActive) fetchAssignedJobs(true);
  }, selected && isTabActive ? REFRESH_MS : null);

  const jobCounts = useMemo(() => {
    const counts = { all: assignedJobs.length, active: 0, completed: 0, onHold: 0 };
    const activeStatuses = new Set([
      "ACCEPTED", "ENROUTE", "ONSITE", "INPROGRESS",
      "ESCALATED", "PAUSED", "ONHOLD", "HOLD",
    ]);
    for (const job of assignedJobs) {
      const status = normalizedJobStatus(job.status);
      if (["COMPLETED", "CLOSED"].includes(status)) counts.completed += 1;
      else {
        if (["PAUSED", "ONHOLD", "HOLD"].includes(status)) counts.onHold += 1;
        if (activeStatuses.has(status)) counts.active += 1;
      }
    }
    return counts;
  }, [assignedJobs]);

  const acceptedOpenJobs = jobCounts.active;

  function showJobsForStatus(status: string) {
    setJobStatusFilter(status);
    setProfileTab("jobs");
  }

  const visibleJobs = useMemo(() => assignedJobs.filter((job) => {
    const status = normalizedJobStatus(job.status);
    if (jobStatusFilter === "ALL") return true;
    if (jobStatusFilter === "ACTIVE_ONLY") return ["ACCEPTED", "ENROUTE", "ONSITE", "INPROGRESS", "ESCALATED", "PAUSED", "ONHOLD", "HOLD"].includes(status);
    if (jobStatusFilter === "COMPLETED_ONLY") return ["COMPLETED", "CLOSED"].includes(status);
    if (jobStatusFilter === "ONHOLD_ONLY") return ["PAUSED", "ONHOLD", "HOLD"].includes(status);
    return status === jobStatusFilter;
  }), [assignedJobs, jobStatusFilter]);

  useEffect(() => {
    const t = setTimeout(() => setDebSearch(search), 300);
    return () => clearTimeout(t);
  }, [search]);
  useEffect(
    () => setPage(1),
    [debSearch, statusFilter, skillFilter, zoneFilter],
  );

  const fetchData = useCallback(
    async (silent = false) => {
      if (silent) {
        setFetching(true);
        setBgError("");
      } else {
        setLoading(true);
        setInitError("");
      }
      const t0 = Date.now();
      try {
        const res = await getAllTechnicians({
          search: debSearch || undefined,
          status: showDeactivatedTechnicians
            ? "DEACTIVATED"
            : statusFilter !== "ALL" ? statusFilter : undefined,
          zone: zoneFilter !== "ALL" ? zoneFilter : undefined,
          skill: skillFilter !== "ALL" ? skillFilter : undefined,
          page: page,
          limit: PAGE_SIZE,
        });
        const normalizedTechnicians: NormalizedTech[] = (
          Array.isArray(res.data) ? res.data : []
        ).map(normTech);
        setSelected((current) => current
          ? normalizedTechnicians.find((tech) => String(tech.id) === String(current.id)) || null
          : null);
        const techniciansWithCurrentWorkload = await Promise.all(
          normalizedTechnicians.map(async (tech) => {
            try {
              const jobsResponse = await getJobs({ technician_id: Number(tech.id) });
              const jobs = Array.isArray(jobsResponse?.data) ? jobsResponse.data : [];
              return { ...tech, currentJobs: countAcceptedOpenJobs(jobs) };
            } catch {
              // Keep the API workload if this technician's jobs cannot be fetched.
              return tech;
            }
          }),
        );
        setTechnicians(techniciansWithCurrentWorkload);
        setSelected((current) => current
          ? techniciansWithCurrentWorkload.find((tech) => String(tech.id) === String(current.id)) || null
          : null);
        const totalHeader =
          res.headers["x-total-count"] || res.headers["X-Total-Count"];
        setTotalTechCount(
          totalHeader ? parseInt(totalHeader, 10) : (res.data || []).length,
        );

        const zonesRes = await getUniqueZones();
        setUniqueZones(zonesRes.data || []);

        const latency = Date.now() - t0;
        setLastSuccessAt(Date.now());
        setMetrics((m) => ({
          ...m,
          successCount: m.successCount + 1,
          lastLatencyMs: latency,
        }));
        setBgError("");
      } catch (err: any) {
        const msg =
          err.response?.data?.error ||
          err.response?.data?.detail ||
          "Unable to reach backend.";
        if (silent) {
          setBgError(msg);
          setMetrics((m) => ({ ...m, failureCount: m.failureCount + 1 }));
        } else {
          setInitError(msg);
        }
      } finally {
        if (silent) setFetching(false);
        else setLoading(false);
      }
    },
    [debSearch, statusFilter, zoneFilter, skillFilter, page, showDeactivatedTechnicians],
  );

  useEffect(() => {
    fetchData(false);
  }, [fetchData]);

  useInterval(() => {
    if (!lastSuccessAt || !isTabActive) return;
    const elapsed = Date.now() - lastSuccessAt;
    const pct = Math.max(
      0,
      Math.min(100, Math.round((elapsed / REFRESH_MS) * 100)),
    );
    setCountdown(pct);
  }, 1000);

  useInterval(
    () => {
      fetchData(true);
      setCountdown(0);
    },
    isTabActive ? REFRESH_MS : null,
  );

  useEffect(() => {
    if (!showMetrics) return;
    const handler = (e: MouseEvent) => {
      if (metricsRef.current && !metricsRef.current.contains(e.target as Node))
        setShowMetrics(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showMetrics]);

  const filtered = useMemo(() => {
    return [...technicians].sort((a, b) => {
      let av: any, bv: any;
      if (sortKey === "name") {
        av = a.name.toLowerCase();
        bv = b.name.toLowerCase();
      } else if (sortKey === "status") {
        av = normalizeStatus(a.status);
        bv = normalizeStatus(b.status);
      } else if (sortKey === "jobs") {
        av = a.currentJobs;
        bv = b.currentJobs;
      } else if (sortKey === "ping") {
        av = a.lastPing ? new Date(a.lastPing).getTime() : 0;
        bv = b.lastPing ? new Date(b.lastPing).getTime() : 0;
      } else {
        av = a.id;
        bv = b.id;
      }
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
  }, [technicians, sortKey, sortDir]);

  useEffect(() => {
    const total = Math.max(1, Math.ceil(totalTechCount / PAGE_SIZE));
    if (page > total) {
      setPage(total);
    }
  }, [totalTechCount, page]);

  const totalPages = Math.max(1, Math.ceil(totalTechCount / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageSlice = filtered;
  const visibleTechnicians = useMemo(
    () => pageSlice
      .filter((tech) => `${tech.name} ${tech.skill} ${tech.location}`.toLowerCase().includes(technicianSearch.toLowerCase())),
    [pageSlice, technicianSearch],
  );

  function handleSort(key: string) {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(key);
      setSortDir("asc");
    }
    setPage(1);
  }
  function showToast(msg: string, type = "success") {
    clearTimeout(toastTimer.current);
    setToast({ msg, type });
    toastTimer.current = setTimeout(
      () => setToast({ msg: "", type: "" }),
      3500,
    );
  }
  function openSidebar(tech: NormalizedTech) {
    // Clear the previous technician's data before React paints the new profile.
    setAssignedJobs([]);
    setLoadedJobsTechnicianId(null);
    setJobsLoading(true);
    setJobsError("");
    setJobStatusFilter("ALL");
    setProfileTab("jobs");
    setSelected(tech);
  }
  function closeSidebar() {
    setSelected(null);
  }
  function clearFilters() {
    setSearch("");
    setStatusFilter("ALL");
    setSkillFilter("ALL");
    setZoneFilter("ALL");
    setPage(1);
  }
  const hasFilters =
    search ||
    statusFilter !== "ALL" ||
    skillFilter !== "ALL" ||
    zoneFilter !== "ALL";

  function handleManualRefresh() {
    fetchData(technicians.length > 0);
    setCountdown(0);
  }

  async function toggleTechnicianAvailability(tech: NormalizedTech) {
    const id = String(tech.id);
    const nextStatus = tech.status.toLowerCase() === "available" ? "Offline" : "Available";
    setAvailabilityUpdatingId(id);
    try {
      await updateTechnicianAvailability(tech.id, nextStatus);
      setTechnicians((current) => current.map((row) => String(row.id) === id ? { ...row, status: nextStatus } : row));
      setSelected((current) => current && String(current.id) === id ? { ...current, status: nextStatus } : current);
      showToast(`${tech.name} is now ${nextStatus === "Available" ? "Online" : "Offline"}`);
    } catch (err: any) {
      showToast(err.response?.data?.detail || "Could not update technician availability.", "error");
    } finally {
      setAvailabilityUpdatingId(null);
    }
  }

  function handleDeleteTech(tech: NormalizedTech) {
    setTechToDelete(tech);
  }

  async function confirmDeleteTech() {
    if (!techToDelete) return;
    const tech = techToDelete;
    setDeleteTechBusy(true);
    try {
      await updateTechnicianAvailability(tech.id, "Deactivated");
      showToast(`${tech.name} deactivated and moved to Deactivated Technicians`);
      if (String(selected?.id) === String(tech.id)) closeSidebar();
      setTechToDelete(null);
      fetchData(technicians.length > 0);
    } catch (err: any) {
      const msg =
        err.response?.data?.error ||
        err.response?.data?.detail ||
        "Failed to deactivate technician.";
      showToast(msg, "error");
    } finally {
      setDeleteTechBusy(false);
    }
  }

  async function restoreTechnician(tech: NormalizedTech) {
    try {
      await updateTechnicianAvailability(tech.id, "Offline");
      showToast(`${tech.name} reactivated with Offline status`);
      if (String(selected?.id) === String(tech.id)) closeSidebar();
      fetchData(true);
    } catch (err: any) {
      const msg = err.response?.data?.detail || "Failed to reactivate technician.";
      showToast(msg, "error");
    }
  }

  function handleEditTech(tech: NormalizedTech) {
    openEditForm(tech);
  }

  function getPageNums() {
    const nums: number[] = [];
    const delta = 2;
    for (
      let i = Math.max(1, safePage - delta);
      i <= Math.min(totalPages, safePage + delta);
      i++
    )
      nums.push(i);
    return nums;
  }

  return (
    <div style={styles.tldPage}>
      <style>{localCss}</style>

      {/* Success Popup */}
      {popup.show && (
        <div style={styles.popupOverlay}>
          <div style={styles.successPopup}>
            <div style={styles.successIcon}>✓</div>
            <h3
              style={{
                margin: "0 0 10px 0",
                color: "#2F4F3E",
                fontSize: "18px",
                fontWeight: 700,
              }}
            >
              {popup.title}
            </h3>
            {popup.name && (
              <div style={styles.techNameBox}>
                Technician: <strong>{popup.name}</strong>
              </div>
            )}
            <p
              style={{
                margin: "0 0 20px 0",
                color: "#6B7280",
                fontSize: "13px",
              }}
            >
              {popup.message}
            </p>
            <button
              type="button"
              style={
                hoveredBtn === "popupClose"
                  ? { ...styles.popupCloseBtn, background: "#5C9470" }
                  : styles.popupCloseBtn
              }
              onMouseEnter={() => setHoveredBtn("popupClose")}
              onMouseLeave={() => setHoveredBtn(null)}
              onClick={closePopup}
            >
              OK
            </button>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast.msg && (
        <div
          className={`tld-toast ${toast.type}`}
          style={{
            ...styles.tldToast,
            background: toast.type === "success" ? "#DDEEE5" : "#FDF2F2",
            color: toast.type === "success" ? "#2F4F3E" : "#9B3A3A",
            border:
              toast.type === "success"
                ? "1px solid #C3DDC9"
                : "1px solid #F5C6C6",
          }}
        >
          {toast.msg}
        </div>
      )}

      {/* Countdown progress rail moved inside card header */}

      {/* Background error banner */}
      {bgError && (
        <div style={styles.tldBgErrorBanner}>
          <strong>Refresh failed.</strong> Showing last available data. —{" "}
          {bgError}
          <button
            className="tld-bg-error-retry"
            onClick={handleManualRefresh}
            style={styles.tldBgErrorRetry}
          >
            Retry
          </button>
        </div>
      )}

      {selected && String(loadedJobsTechnicianId) !== String(selected.id) && (
        <section style={{ flex: 1, minHeight: 0, display: "grid", placeItems: "center", background: "#fff", border: "1px solid #dce9e2", borderRadius: 18 }}>
          <LoadingSpinner message={`Loading ${selected.name}…`} />
        </section>
      )}

      {selected && String(loadedJobsTechnicianId) === String(selected.id) && (
    <section className="tech-profile-layout" style={{ display: "flex", flex: 1, minHeight: 0, gap: 16, color: "#16352b" }}>
          <aside className="tech-profile-sidebar" style={{ width: 260, minWidth: 220, display: "flex", flexDirection: "column", minHeight: 0, background: "#fff", border: "1px solid #dce9e2", borderRadius: 16, padding: 14, boxShadow: "0 8px 24px rgba(25,75,51,.06)" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
              <div><h2 style={{ margin: 0, fontSize: 16 }}>Technicians ({totalTechCount})</h2><p style={{ margin: "4px 0 0", color: "#64748b", fontSize: 11 }}>Select a technician to view assigned jobs</p></div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 7, margin: "12px 0", padding: "0 9px", border: "1px solid #dbe7e1", borderRadius: 9 }}><Search size={14} color="#58806c" /><input value={technicianSearch} onChange={(e) => setTechnicianSearch(e.target.value)} placeholder="Search technicians…" style={{ border: 0, outline: 0, padding: "8px 0", width: "100%", background: "transparent", fontSize: 13 }} /></div>
            <div style={{ overflowY: "auto", display: "grid", alignContent: "start", gap: 8 }}>
              {visibleTechnicians.map((tech) => (
                <button key={tech.id} className="tech-profile-technician-option" onClick={() => openSidebar(tech)} style={{ display: "flex", alignItems: "center", gap: 9, textAlign: "left", padding: 9, border: `1px solid ${String(tech.id) === String(selected.id) ? "#13804c" : "#e3ece7"}`, borderRadius: 11, background: String(tech.id) === String(selected.id) ? "#eff9f3" : "#fff", cursor: "pointer" }}>
                  <span style={{ width: 36, height: 36, flexShrink: 0, borderRadius: 10, display: "grid", placeItems: "center", background: "linear-gradient(145deg,#77bb83,#17633d)", color: "white", fontSize: 13, fontWeight: 800 }}>{getInitials(tech.name)}</span>
                  <span style={{ minWidth: 0, flex: 1 }}><strong style={{ display: "block", color: "#183b2d", fontSize: 14 }}>{tech.name}</strong><small style={{ display: "block", color: "#64748b", marginTop: 2, fontSize: 11 }}>{tech.skill}</small><span style={{ display: "block", marginTop: 4 }}><small style={{ color: "#64748b", marginRight: 6, fontSize: 11 }}>{displayStatus(tech.status)}</small><span style={{ display: "inline-block", padding: "2px 6px", borderRadius: 999, background: "#d8f3e3", color: "#075b36", fontSize: 10, fontWeight: 800, lineHeight: 1.3 }}>Workload {Math.min(String(tech.id) === String(selected.id) ? acceptedOpenJobs : tech.currentJobs, 5)}/5</span></span></span>
                  <span style={{ width: 8, height: 8, flexShrink: 0, borderRadius: "50%", background: /online|available|busy|assigned/i.test(tech.status) ? "#16a34a" : "#94a3b8" }} />
                </button>
              ))}
              {visibleTechnicians.length === 0 && <p style={{ color: "#64748b", fontSize: 13 }}>No technicians match this search.</p>}
            </div>
          </aside>

          <article style={{ flex: 1, minWidth: 0, minHeight: 0, display: "flex", flexDirection: "column", background: "#fff", border: "1px solid #dce9e2", borderRadius: 18, overflow: "hidden", boxShadow: "0 8px 24px rgba(25,75,51,.06)" }}>
            <div className="tech-profile-hero" style={{ position: "relative", overflow: "hidden", padding: "7px 12px", height: 150, minHeight: 150, boxSizing: "border-box", display: "flex", alignItems: "center", gap: 10, color: "white", backgroundImage: `url(${technicianBanner})`, backgroundSize: "107% auto", backgroundPosition: "left center", backgroundRepeat: "no-repeat" }}>
              <button type="button" onClick={closeSidebar} aria-label="Back to technician list" title="Back to technician list" style={{ position: "absolute", top: 9, right: 10, zIndex: 3, width: 30, height: 30, display: "grid", placeItems: "center", border: "1px solid rgba(255,255,255,.58)", borderRadius: "50%", background: "rgba(0,45,27,.72)", color: "#fff", cursor: "pointer" }}>
                <X size={17} />
              </button>
              <div className="tech-profile-hero-avatar" style={{ width: 50, height: 50, flexShrink: 0, borderRadius: "50%", display: "grid", placeItems: "center", border: "2px solid rgba(255,255,255,.92)", background: "rgba(220,255,226,.22)", color: "#f3fff5", fontSize: 17, fontWeight: 800 }}>{getInitials(selected.name)}</div>
              <div className="tech-profile-hero-divider" style={{ width: 1, alignSelf: "stretch", maxHeight: 70, background: "rgba(255,255,255,.5)" }} />
              <div style={{ position: "relative", zIndex: 1, minWidth: 0, flex: "0 1 155px" }}><h1 style={{ margin: "0 0 4px", fontSize: 18, fontWeight: 750 }}>{selected.name}</h1><div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", fontSize: 11 }}><span>Technician</span><span style={{ padding: "3px 7px", color: "#075b36", background: "#e7fff0", borderRadius: 24, fontSize: 9, fontWeight: 700 }}>● {displayStatus(selected.status)}</span></div></div>
              <div className="tech-profile-hero-details" style={{ position: "relative", zIndex: 1, flex: "0 1 43%", maxWidth: 520, minWidth: 0, marginLeft: 0, display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "9px 14px", padding: "11px 14px", border: "1px solid rgba(215,255,228,.24)", borderRadius: 9, background: "rgba(0,42,25,.64)", backdropFilter: "blur(5px)", boxShadow: "0 5px 14px rgba(0,0,0,.16)" }}>
                {[
                  ["Phone", selected.phone || "—"],
                  ["Email", selected.email || "—"],
                  ["Skills", selected.skill || "—"],
                  ["Workload", `${Math.min(acceptedOpenJobs, 5)}/5`],
                ].map(([label, value]) => <div key={label} style={{ minWidth: 0 }}><span style={{ display: "block", marginBottom: 2, color: "#b8e8cb", fontSize: 8, fontWeight: 700, textTransform: "uppercase", letterSpacing: ".04em" }}>{label}</span><strong title={value} style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "#fff", fontSize: 10, fontWeight: 650, lineHeight: 1.15 }}>{value}</strong></div>)}
              </div>
            </div>
            <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: 12 }}>
              <div className="tech-profile-counts" style={{ display: "grid", gridTemplateColumns: "repeat(4,minmax(120px,1fr))", gap: 8, marginBottom: 12 }}>
                {[
                  { label: "All Jobs", value: jobCounts.all, color: "#087348", background: "#eaf8ef", icon: <BriefcaseBusiness size={20} />, filter: "ALL" },
                  { label: "Active", value: jobCounts.active, color: "#2670d8", background: "#edf4ff", icon: <Play size={20} />, filter: "ACTIVE_ONLY" },
                  { label: "Completed", value: jobCounts.completed, color: "#14935f", background: "#eaf8ef", icon: <CircleCheck size={20} />, filter: "COMPLETED_ONLY" },
                  { label: "On Hold", value: jobCounts.onHold, color: "#d08713", background: "#fff6e5", icon: <PauseCircle size={20} />, filter: "ONHOLD_ONLY" },
                ].map((card) => <button type="button" key={card.label} onClick={() => showJobsForStatus(card.filter)} aria-label={`Show ${card.label.toLowerCase()} jobs`} style={{ minHeight: 56, display: "flex", alignItems: "center", gap: 8, padding: "8px 10px", border: `1px solid ${card.color}20`, borderRadius: 10, background: card.background, textAlign: "left", cursor: "pointer" }}><span style={{ width: 32, height: 32, flexShrink: 0, borderRadius: "50%", display: "grid", placeItems: "center", color: card.color, background: "rgba(255,255,255,.74)" }}>{card.icon}</span><span><span style={{ display: "block", color: "#526276", fontSize: 11 }}>{card.label}</span><strong style={{ display: "block", color: "#122b22", fontSize: 19, lineHeight: 1.1, marginTop: 1 }}>{jobsLoading && assignedJobs.length === 0 ? "…" : card.value}</strong></span></button>)}
              </div>
              {profileTab === "overview" && <>
                <div style={{ border: "1px solid #e0ebe5", borderRadius: 14, padding: 18 }}><h3 style={{ margin: "0 0 14px", fontSize: 17 }}>Technician Details</h3>{[["Technician ID", `#${selected.id}`], ["Skill", selected.skill], ["Phone", selected.phone || "—"], ["Location / Zone", selected.location], ["Current workload", `${Math.min(acceptedOpenJobs, 5)} / 5`], ["Last active", formatAgo(selected.lastPing)]].map(([label, value]) => <div key={label} style={{ display: "grid", gridTemplateColumns: "minmax(130px, 1fr) 2fr", gap: 12, padding: "12px 4px", borderTop: "1px solid #edf2ef", fontSize: 14 }}><span style={{ color: "#64748b" }}>{label}</span><strong style={{ overflowWrap: "anywhere" }}>{value}</strong></div>)}</div>
                <button onClick={() => setProfileTab("jobs")} style={{ marginTop: 16, border: 0, borderRadius: 10, background: "#087244", color: "white", padding: "11px 16px", fontWeight: 700, cursor: "pointer" }}><BriefcaseBusiness size={15} style={{ verticalAlign: "-3px", marginRight: 7 }} />View all {jobCounts.all} assigned jobs</button>
              </>}
              {profileTab === "jobs" && <>
                {jobsError && <div style={{ marginBottom: 12, padding: 12, background: "#fff7ed", border: "1px solid #fed7aa", borderRadius: 9, color: "#9a3412" }}>{jobsError} <button onClick={() => fetchAssignedJobs(false)} style={{ marginLeft: 8, cursor: "pointer" }}>Retry</button></div>}
                {jobsLoading && assignedJobs.length === 0 ? <LoadingSpinner message="Loading assigned jobs…" /> : visibleJobs.length === 0 ? <div style={{ padding: 28, textAlign: "center", color: "#64748b" }}>{assignedJobs.length ? "No jobs match this status." : "No jobs are assigned to this technician."}</div> : <div style={{ overflowX: "auto", border: "1px solid #e4ede8", borderRadius: 10 }}><table style={{ width: "100%", minWidth: 820, borderCollapse: "collapse", fontSize: 12 }}><thead><tr style={{ background: "#f1f4f7", color: "#25323d", textAlign: "left" }}>{["Job", "Customer / Location", "Service", "Priority", "Status", "Updated"].map((heading) => <th key={heading} style={{ padding: "10px 10px", whiteSpace: "nowrap", borderBottom: "1px solid #e4ede8" }}>{heading}</th>)}</tr></thead><tbody>{visibleJobs.map((job, index) => <tr key={job.job_id ?? job.id ?? `${job.customer_name}-${index}`} style={{ borderBottom: "1px solid #edf2ef" }}><td style={{ padding: 10, minWidth: 180 }}><strong style={{ display: "block", color: "#087348", fontSize: 14 }}>#{job.job_id ?? job.id ?? "—"}</strong><span style={{ display: "block", color: "#465463", marginTop: 3, maxWidth: 240 }}>{job.issue_description || "—"}</span></td><td style={{ padding: 10, minWidth: 170 }}><strong style={{ display: "block" }}>{job.customer_name || "—"}</strong><span style={{ display: "block", color: "#64748b", marginTop: 3, maxWidth: 240 }}>{job.location || "—"}</span></td><td style={{ padding: 10, whiteSpace: "nowrap" }}>{job.service_type || job.required_skill || "—"}</td><td style={{ padding: 10, whiteSpace: "nowrap" }}><span style={{ display: "inline-block", padding: "4px 8px", borderRadius: 18, background: /critical|high|p1|p2/i.test(job.priority) ? "#fff0f0" : /medium|p3/i.test(job.priority) ? "#fff6e5" : "#eaf8ef", color: /critical|high|p1|p2/i.test(job.priority) ? "#b42318" : /medium|p3/i.test(job.priority) ? "#9a6700" : "#087244", fontWeight: 700 }}>{displayJobStatus(job.priority || "—")}</span></td><td style={{ padding: 10, whiteSpace: "nowrap" }}><span style={{ display: "inline-block", padding: "4px 8px", borderRadius: 18, background: /complete|closed/i.test(job.status) ? "#e8f8ee" : /hold|paused/i.test(job.status) ? "#fff5df" : /cancel|reject/i.test(job.status) ? "#fff0f0" : "#edf4ff", color: /complete|closed/i.test(job.status) ? "#087244" : /hold|paused/i.test(job.status) ? "#9a6700" : /cancel|reject/i.test(job.status) ? "#b42318" : "#245ca6", fontWeight: 700 }}>{displayJobStatus(job.status)}</span></td><td style={{ padding: 10, minWidth: 130, whiteSpace: "nowrap" }}>{formatJobDate(job.updated_at || job.completed_at || job.closed_at || job.created_at)}<small style={{ display: "block", color: "#64748b", marginTop: 3 }}>Scheduled: {formatJobDate(job.preferred_service_date)}</small></td></tr>)}</tbody></table></div>}
                <p style={{ color: "#64748b", fontSize: 11, margin: "12px 0 0" }}>Showing {visibleJobs.length} of {assignedJobs.length} assigned jobs · refreshes automatically while this page is open.</p>
              </>}
              {profileTab === "activity" && <div style={{ display: "grid", gap: 10 }}><h2 style={{ margin: "0 0 4px", fontSize: 21 }}>Recent Job Activity</h2><p style={{ margin: "0 0 8px", color: "#64748b", fontSize: 13 }}>Latest job updates based on the current assigned job records.</p>{[...assignedJobs].sort((a, b) => new Date(b.updated_at || b.completed_at || b.created_at || 0).getTime() - new Date(a.updated_at || a.completed_at || a.created_at || 0).getTime()).map((job) => <div key={job.id} style={{ display: "flex", gap: 12, alignItems: "center", padding: 14, border: "1px solid #e4ede8", borderRadius: 12 }}><span style={{ width: 36, height: 36, borderRadius: "50%", display: "grid", placeItems: "center", color: "#087348", background: "#eaf8ef" }}><BriefcaseBusiness size={17} /></span><div style={{ flex: 1 }}><strong>Job #{job.id} · {displayJobStatus(job.status)}</strong><div style={{ color: "#64748b", fontSize: 12 }}>{job.customer_name || "Customer"} · {job.issue_description || job.service_type || "Job updated"}</div></div><span style={{ color: "#64748b", fontSize: 12 }}>{formatJobDate(job.updated_at || job.completed_at || job.created_at)}</span></div>)}</div>}
            </div>
          </article>
        </section>
      )}

      {!selected && !loading && (
        <section style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: 20, background: "#fff", border: "1px solid #dce9e2", borderRadius: 18, boxShadow: "0 8px 24px rgba(25,75,51,.06)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12, marginBottom: 16 }}>
            <div>
              <h1 style={{ margin: 0, color: "#183b2d", fontSize: 21 }}>{showDeactivatedTechnicians ? "Deactivated Technicians" : "Technicians"} ({totalTechCount})</h1>
              <p style={{ margin: "4px 0 0", color: "#64748b", fontSize: 13 }}>{showDeactivatedTechnicians ? "These technicians are inactive and can be reactivated." : "Select a technician to view assigned jobs"}</p>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <button type="button" onClick={() => { setShowDeactivatedTechnicians((current) => !current); clearFilters(); setTechnicianSearch(""); }} style={{ minHeight: 36, padding: "0 12px", border: "1px solid #dce9e2", borderRadius: 9, background: showDeactivatedTechnicians ? "#e9f5ed" : "#fff", color: "#315840", fontWeight: 700, cursor: "pointer" }}>{showDeactivatedTechnicians ? "Active Technicians" : "Deactivated Technicians"}</button>
              <button type="button" onClick={onAddTechnician || openAddForm} style={{ minHeight: 36, display: "inline-flex", alignItems: "center", gap: 6, padding: "0 13px", border: 0, borderRadius: 9, background: "#087244", color: "#fff", fontWeight: 700, cursor: "pointer" }}><Plus size={15} /> Add Technician</button>
            </div>
          </div>

          <label style={{ display: "flex", alignItems: "center", gap: 8, maxWidth: 420, marginBottom: 16, padding: "0 11px", border: "1px solid #dbe7e1", borderRadius: 9, background: "#fff" }}>
            <Search size={15} color="#58806c" />
            <input value={technicianSearch} onChange={(event) => setTechnicianSearch(event.target.value)} placeholder="Search technicians…" aria-label="Search technicians" style={{ width: "100%", height: 38, border: 0, outline: 0, background: "transparent", fontSize: 13 }} />
          </label>

          {visibleTechnicians.length === 0 ? (
            <div style={{ padding: 28, textAlign: "center", color: "#64748b" }}>No technicians match this search.</div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 270px), 1fr))", gap: 12, alignItems: "start" }}>
              {visibleTechnicians.map((tech) => (
                <article key={tech.id} className="tech-list-card" style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0, padding: 12, border: "1px solid #e3ece7", borderRadius: 12, background: "#fff" }}>
                  <button type="button" onClick={() => openSidebar(tech)} title={`View ${tech.name}`} style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, minWidth: 0, padding: 0, border: 0, background: "transparent", textAlign: "left", cursor: "pointer" }}>
                    <span style={{ width: 42, height: 42, flexShrink: 0, borderRadius: 11, display: "grid", placeItems: "center", background: "linear-gradient(145deg,#77bb83,#17633d)", color: "white", fontSize: 14, fontWeight: 800 }}>{getInitials(tech.name)}</span>
                    <span style={{ display: "block", minWidth: 0, flex: 1 }}>
                      <strong style={{ display: "block", color: "#183b2d", fontSize: 14 }}>{tech.name}</strong>
                      <span style={{ display: "block", overflow: "hidden", marginTop: 3, color: "#64748b", fontSize: 11, textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{tech.skill || "No skill listed"}</span>
                      <span style={{ display: "block", overflow: "hidden", marginTop: 2, color: "#64748b", fontSize: 11, textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{tech.location || "Location not listed"}</span>
                      <span style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 7 }}><small style={{ color: "#64748b", fontSize: 10 }}>{displayStatus(tech.status)}</small><small style={{ padding: "2px 7px", borderRadius: 999, background: "#d8f3e3", color: "#075b36", fontSize: 10, fontWeight: 800 }}>Workload {Math.min(tech.currentJobs, 5)}/5</small></span>
                    </span>
                  </button>
                  <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                    {showDeactivatedTechnicians ? (
                      <button type="button" onClick={() => void restoreTechnician(tech)} title={`Reactivate ${tech.name}`} aria-label={`Reactivate ${tech.name}`} style={{ width: 30, height: 30, display: "grid", placeItems: "center", border: "1px solid #d5ecdd", borderRadius: 8, background: "#fff", color: "#087244", cursor: "pointer" }}><RotateCcw size={14} /></button>
                    ) : <>
                      <button type="button" onClick={() => handleEditTech(tech)} title={`Edit ${tech.name}`} aria-label={`Edit ${tech.name}`} style={{ width: 30, height: 30, display: "grid", placeItems: "center", border: "1px solid #e3ece7", borderRadius: 8, background: "#fff", color: "#a16a08", cursor: "pointer" }}><Pencil size={14} /></button>
                      <button type="button" onClick={() => handleDeleteTech(tech)} title={`Deactivate ${tech.name}`} aria-label={`Deactivate ${tech.name}`} style={{ width: 30, height: 30, display: "grid", placeItems: "center", border: "1px solid #fee2e2", borderRadius: 8, background: "#fff", color: "#dc2626", cursor: "pointer" }}><UserMinus size={14} /></button>
                    </>}
                  </div>
                </article>
              ))}
            </div>
          )}

          {totalPages > 1 && (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12, marginTop: 18 }}>
              <button type="button" disabled={safePage <= 1} onClick={() => setPage((current) => Math.max(1, current - 1))} style={{ minHeight: 34, padding: "0 12px", border: "1px solid #dce9e2", borderRadius: 8, background: "#fff", color: "#315840", cursor: safePage <= 1 ? "not-allowed" : "pointer", opacity: safePage <= 1 ? 0.55 : 1 }}>Previous</button>
              <span style={{ color: "#64748b", fontSize: 12 }}>Page {safePage} of {totalPages}</span>
              <button type="button" disabled={safePage >= totalPages} onClick={() => setPage((current) => Math.min(totalPages, current + 1))} style={{ minHeight: 34, padding: "0 12px", border: "1px solid #dce9e2", borderRadius: 8, background: "#fff", color: "#315840", cursor: safePage >= totalPages ? "not-allowed" : "pointer", opacity: safePage >= totalPages ? 0.55 : 1 }}>Next</button>
            </div>
          )}
        </section>
      )}

      {!selected && loading && (
        <section style={{ flex: 1, minHeight: 0, display: "grid", placeItems: "center", background: "#fff", border: "1px solid #dce9e2", borderRadius: 18 }}>
          <LoadingSpinner message="Loading technicians…" />
        </section>
      )}

      {/* Table Card */}
      <div style={{ ...styles.tldTableCard, display: "none" }}>
        <div className="tld-header-responsive" style={styles.tldCardHeader}>
          <div>
            <span style={styles.tldSectionBadge}>Dashboard</span>
            <p style={styles.tldCardSubtitle}>
              Monitor registered technicians, real-time workload, and latency
              metrics
            </p>
          </div>
          <div
            className="tld-header-right-responsive"
            style={{
              ...styles.tldHeaderRight,
              flexDirection: "column",
              alignItems: "flex-end",
              gap: "6px",
            }}
          >
            {/* Top row containing refresh indicator, Metrics, Refresh button and Add button */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                flexWrap: "wrap",
              }}
            >
              {/* Refresh indicator */}
              <div style={styles.tldRefreshBar}>
                <div
                  className="tld-live-loading-dot"
                  title={
                    fetching
                      ? "Refreshing…"
                      : !isTabActive
                        ? "Paused"
                        : `Updated ${formatAgo(lastSuccessAt)}`
                  }
                />

                {/* Metrics popover */}
                <div style={styles.tldMetricsWrap} ref={metricsRef}>
                  <button
                    className="tld-metrics-trigger-style"
                    style={styles.tldMetricsTrigger}
                    onClick={() => setShowMetrics((v) => !v)}
                  >
                    Metrics
                  </button>
                  {showMetrics && (
                    <MetricsPanel
                      metrics={metrics}
                      lastSuccessAt={lastSuccessAt}
                    />
                  )}
                </div>
              </div>

              <button
                className="tld-refresh-btn-style"
                style={styles.tldRefreshBtn}
                onClick={handleManualRefresh}
                disabled={fetching || loading}
                title="Refresh now"
              >
                {fetching || loading ? (
                  <>
                    <div style={styles.tldRefreshBtnSpinner} />
                    Refreshing…
                  </>
                ) : (
                  <>Refresh</>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Filter Bar */}
        <div className="tld-filter-bar-responsive" style={styles.tldFilterBar}>
          <div
            className="tld-filter-group-responsive"
            style={{ ...styles.tldFilterGroup, ...styles.tldFilterGroupSearch }}
          >
            <label style={styles.tldFilterGroupLabel}>Search</label>
            <div style={styles.tldSearchWrap}>
              <span
                style={{
                  position: "absolute",
                  left: "10px",
                  top: "50%",
                  transform: "translateY(-50%)",
                  color: "#A0B5A8",
                  fontSize: "13px",
                  pointerEvents: "none",
                }}
              >
                🔍
              </span>
              <input
                id="tech-search"
                type="text"
                className="tld-search-input-style"
                style={styles.tldSearchInput}
                placeholder="Name, skill, location…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>
          <div
            className="tld-filter-group-responsive"
            style={styles.tldFilterGroup}
          >
            <label style={styles.tldFilterGroupLabel}>Status</label>
            <select
              id="tech-status-filter"
              className="tld-select-style"
              style={styles.tldSelect}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="ALL">All Statuses</option>
              <option value="Available">Available</option>
              <option value="Busy">Busy</option>
              <option value="Assigned">Assigned</option>
              <option value="Offline">Offline</option>
              <option value="En Route">En Route</option>
              <option value="On Site">On Site</option>
              <option value="On Break">On Break</option>
              <option value="Suspended">Suspended</option>
            </select>
          </div>
          <div
            className="tld-filter-group-responsive"
            style={styles.tldFilterGroup}
          >
            <label style={styles.tldFilterGroupLabel}>Zone</label>
            <select
              id="tech-zone-filter"
              className="tld-select-style"
              style={styles.tldSelect}
              value={zoneFilter}
              onChange={(e) => setZoneFilter(e.target.value)}
            >
              <option value="ALL">All Zones</option>
              {uniqueZones.map((z) => (
                <option key={z} value={z}>
                  {z}
                </option>
              ))}
            </select>
          </div>
          <div
            className="tld-filter-group-responsive"
            style={styles.tldFilterGroup}
          >
            <label style={styles.tldFilterGroupLabel}>Skill</label>
            <select
              id="tech-skill-filter"
              className="tld-select-style"
              style={styles.tldSelect}
              value={skillFilter}
              onChange={(e) => setSkillFilter(e.target.value)}
            >
              <option value="ALL">All Skills</option>
              {SKILLS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          {hasFilters && (
            <button
              className="tld-filter-clear-style"
              style={styles.tldFilterClear}
              onClick={clearFilters}
            >
              Clear
            </button>
          )}
        </div>

        <div style={styles.tldTableMeta}>
          <p style={styles.tldResultsCount}>
            Showing <strong>{pageSlice.length}</strong> of{" "}
            <strong>{totalTechCount}</strong> technician
            {totalTechCount !== 1 ? "s" : ""}
          </p>
        </div>
        <div className="tld-table-wrap-responsive" style={styles.tldTableWrap}>
          <table className="tld-table-responsive" style={styles.tldTable}>
            <thead>
              <tr>
                <th
                  className={`sortable-style ${sortKey === "name" ? "sort-active" : ""}`}
                  style={styles.tldTableTh}
                  onClick={() => handleSort("name")}
                >
                  Technician Name{" "}
                  <SortIcon col="name" sortKey={sortKey} sortDir={sortDir} />
                </th>
                <th
                  className={`sortable-style ${sortKey === "skill" ? "sort-active" : ""}`}
                  style={styles.tldTableTh}
                  onClick={() => handleSort("skill")}
                >
                  Skill{" "}
                  <SortIcon col="skill" sortKey={sortKey} sortDir={sortDir} />
                </th>
                <th
                  className={`sortable-style ${sortKey === "location" ? "sort-active" : ""}`}
                  style={styles.tldTableTh}
                  onClick={() => handleSort("location")}
                >
                  Location{" "}
                  <SortIcon
                    col="location"
                    sortKey={sortKey}
                    sortDir={sortDir}
                  />
                </th>
                <th
                  className={`sortable-style ${sortKey === "status" ? "sort-active" : ""}`}
                  style={{ ...styles.tldTableTh, textAlign: "center" }}
                  onClick={() => handleSort("status")}
                >
                  Status{" "}
                  <SortIcon col="status" sortKey={sortKey} sortDir={sortDir} />
                </th>
                <th
                  className={`sortable-style ${sortKey === "jobs" ? "sort-active" : ""}`}
                  style={styles.tldTableTh}
                  onClick={() => handleSort("jobs")}
                >
                  Workload{" "}
                  <SortIcon col="jobs" sortKey={sortKey} sortDir={sortDir} />
                </th>
                <th
                  className={`sortable-style ${sortKey === "ping" ? "sort-active" : ""}`}
                  style={styles.tldTableTh}
                  onClick={() => handleSort("ping")}
                >
                  Last Ping{" "}
                  <SortIcon col="ping" sortKey={sortKey} sortDir={sortDir} />
                </th>
                <th style={styles.tldTableTh}>Actions</th>
              </tr>
            </thead>
            <tbody key={safePage} className="tld-table-body">
              {loading && (
  <tr>
    <td colSpan={7} style={styles.tldStateCell}>
      <LoadingSpinner message="Loading technicians..." />
    </td>
  </tr>
)}
              {!loading && initError && (
                <tr>
                  <td colSpan={7}>
                    <EmptyState
                      title="Failed to load technicians"
                      description={initError}
                      action={
                        <button
                          className="tld-retry-btn-style"
                          style={styles.tldRetryBtn}
                          onClick={() => fetchData(false)}
                        >
                          Retry
                        </button>
                      }
                    />
                  </td>
                </tr>
              )}

              {!loading && !initError && filtered.length === 0 && (
                <tr>
                  <td colSpan={7}>
                    <EmptyState
                      title={
                        hasFilters
                          ? "No technicians match your filters"
                          : "No technicians found"
                      }
                      description={
                        hasFilters
                          ? "Try adjusting filters."
                          : "Add technicians to get started."
                      }
                      action={
                        hasFilters ? (
                          <button
                            className="tld-retry-btn-style"
                            style={styles.tldRetryBtn}
                            onClick={clearFilters}
                          >
                            Clear Filters
                          </button>
                        ) : null
                      }
                    />
                  </td>
                </tr>
              )}

              {!loading &&
                !initError &&
                pageSlice.map((tech) => {
                  const pct = wPct(tech.currentJobs, tech.maxJobs);
                  return (
                    <tr
                      key={tech.id}
                      className="tld-row-style"
                      onClick={() => openSidebar(tech)}
                      title={`View ${tech.name}`}
                    >
                      <td data-label="Name" style={styles.tldTableTd}>
                        <div style={styles.tldNameCell}>
                          <div style={styles.tldAvatar}>
                            {getInitials(tech.name)}
                          </div>
                          <div style={styles.tldNameInfo}>
                            <span style={styles.tldNamePrimary}>
                              {tech.name}
                            </span>
                          </div>
                        </div>
                      </td>
                      <td data-label="Skill" style={styles.tldTableTd}>
                        <span style={{ color: "#475569", fontWeight: 500 }}>
                          {tech.skill}
                        </span>
                      </td>
                      <td data-label="Location" style={styles.tldTableTd}>
                        <span style={{ color: "#6B7280" }}>
                          {tech.location}
                        </span>
                      </td>
                      <td
                        data-label="Status"
                        style={{
                          ...styles.tldTableTd,
                          textAlign: "center",
                          position: "relative",
                        }}
                      >
                        <StatusBadge status={(tech.status.toLowerCase() === "available" ? "ONLINE" : tech.status.toUpperCase().replace(/[ -]/g, "_")) as any} size="sm" />
                      </td>
                      <td data-label="Workload" style={styles.tldTableTd}>
                        <div style={styles.tldWorkloadCell}>
                          <div style={styles.tldWorkloadNumbers}>
                            {tech.currentJobs} / {tech.maxJobs}
                          </div>
                          <div style={styles.tldWorkloadTrack}>
                            <div
                              className={`tld-workload-fill ${wColor(pct)}`}
                              style={{
                                ...styles.tldWorkloadFill,
                                width: `${pct}%`,
                                background:
                                  pct >= 90
                                    ? "#D96C6C"
                                    : pct >= 60
                                      ? "#D9A441"
                                      : "#6FAF7A",
                              }}
                            />
                          </div>
                        </div>
                      </td>
                      <td data-label="Last Ping" style={styles.tldTableTd}>
                        <span style={styles.tldPing}>
                          {formatAgo(tech.lastPing)}
                        </span>
                      </td>
                      <td data-label="Actions" style={styles.tldTableTd}>
                        <div
                          style={styles.tldActions}
                          onClick={(e) => e.stopPropagation()}
                        >
                          {!showDeactivatedTechnicians && <button
                            className="icon-action-btn-style"
                            style={{ ...styles.iconActionBtn, color: tech.status.toLowerCase() === "available" ? "#475569" : "#16a34a", width: "auto", padding: "0 8px", fontSize: 10, fontWeight: 700 }}
                            disabled={availabilityUpdatingId === String(tech.id)}
                            onClick={() => void toggleTechnicianAvailability(tech)}
                            title={tech.status.toLowerCase() === "available" ? "Set technician offline" : "Set technician online"}
                          >{availabilityUpdatingId === String(tech.id) ? "Updating…" : tech.status.toLowerCase() === "available" ? "Set Offline" : "Set Online"}</button>}
                          {showDeactivatedTechnicians ? (
                            <button
                              className="icon-action-btn-style"
                              style={{ ...styles.iconActionBtn, color: "#16a34a" }}
                              onClick={() => void restoreTechnician(tech)}
                              title="Reactivate technician"
                              aria-label="Reactivate technician"
                            >
                              <RotateCcw size={15} />
                            </button>
                          ) : <>
                          <button
                            className="icon-action-btn-style"
                            style={{
                              ...styles.iconActionBtn,
                              color: "#16a34a",
                            }}
                            onClick={() => openSidebar(tech)}
                            title="View technician"
                            aria-label="View technician"
                          >
                            <Eye size={15} />
                          </button>
                          <button
                            className="icon-action-btn-style"
                            style={{
                              ...styles.iconActionBtn,
                              color: "#ca8a04",
                            }}
                            onClick={() => handleEditTech(tech)}
                            title="Edit technician"
                            aria-label="Edit technician"
                          >
                            <Pencil size={15} />
                          </button>
                          <button
                            className="icon-action-btn-style"
                            style={{
                              ...styles.iconActionBtn,
                              color: "#dc2626",
                            }}
                            onClick={() => handleDeleteTech(tech)}
                            title="Deactivate technician"
                            aria-label="Deactivate technician"
                          >
                            <UserMinus size={15} />
                          </button>
                          </>}
                        </div>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {!loading && !initError && (
          <div style={styles.tldPagination}>
            <span style={styles.tldPageInfo}>
              Page <strong>{safePage}</strong> of <strong>{totalPages}</strong>{" "}
              · {totalTechCount} results
            </span>
            <div style={styles.tldPageControls}>
              <button
                className="tld-page-btn"
                style={styles.tldPageBtn}
                onClick={() => setPage(1)}
                disabled={safePage === 1}
              >
                «
              </button>
              <button
                className="tld-page-btn"
                style={styles.tldPageBtn}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={safePage === 1}
              >
                ‹ Prev
              </button>
              <div style={styles.tldPageNumbers}>
                {getPageNums().map((n) => (
                  <button
                    key={n}
                    className={`tld-page-num${n === safePage ? " active" : ""}`}
                    style={{
                      ...styles.tldPageNum,
                      ...(n === safePage ? styles.tldPageNumActive : {}),
                    }}
                    onClick={() => setPage(n)}
                  >
                    {n}
                  </button>
                ))}
              </div>
              <button
                className="tld-page-btn"
                style={styles.tldPageBtn}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={safePage === totalPages}
              >
                Next ›
              </button>
              <button
                className="tld-page-btn"
                style={styles.tldPageBtn}
                onClick={() => setPage(totalPages)}
                disabled={safePage === totalPages}
              >
                »
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Detail Sidebar */}
      <div
        className="tld-sidebar-responsive"
        style={{
          ...styles.tldSidebar,
          right: "-440px",
        }}
      >
        <div style={styles.tldSidebarHead}>
          <h3 style={styles.tldSidebarHeadH3}>Technician Details</h3>
          <button
            className="tld-sidebar-close-style"
            style={styles.tldSidebarClose}
            onClick={closeSidebar}
          >
            ×
          </button>
        </div>
        {selected && (
          <div style={styles.tldSidebarBody}>
            <div style={styles.tldDetailHero}>
              <div style={styles.tldDetailAvatar}>
                {getInitials(selected.name)}
              </div>
              <div>
                <div style={styles.tldDetailName}>{selected.name}</div>
                <div style={styles.tldDetailMeta}>
                  <StatusBadge status={selected.status as any} />
                </div>
              </div>
            </div>
            <p style={styles.tldDetailSectionTitle}>Technician Info</p>
            {[
              ["ID", `#${selected.id}`],
              ["Skill", selected.skill],
              ["Mobile / Phone", selected.phone || "—"],
              ["Zone / Location", selected.location],
              ["Current Jobs", `${selected.currentJobs} / ${selected.maxJobs}`],
              ["Last Active", formatAgo(selected.lastPing)],
            ].map(([label, val]) => (
              <div key={label} style={styles.tldDetailRow}>
                <span style={styles.tldDetailLabel}>{label}</span>
                <span style={styles.tldDetailValue}>{val}</span>
              </div>
            ))}
            <p style={{ color: "#64748b", fontSize: 12 }}>
              Availability is controlled by the technician from Go Online / Go Offline.
            </p>
          </div>
        )}
      </div>

      {/* Form Sidebar for Add/Edit */}
      {isFormOpen && (
        <div style={styles.tldSidebarOverlay} onClick={closeForm} />
      )}
      <div
        className="tld-sidebar-responsive"
        style={{
          ...styles.tldSidebar,
          right: isFormOpen ? "0" : "-440px",
        }}
      >
        <div style={styles.tldSidebarHead}>
          <h3 style={styles.tldSidebarHeadH3}>
            {isEditing ? "Edit Technician" : "Add New Technician"}
          </h3>
          <button
            className="tld-sidebar-close-style"
            style={styles.tldSidebarClose}
            onClick={closeForm}
          >
            ×
          </button>
        </div>
        <form style={styles.tldSidebarBody} onSubmit={handleFormSubmit}>
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label
              style={{
                fontSize: "11px",
                fontWeight: "bold",
                color: "#475569",
                textTransform: "uppercase",
              }}
            >
              Technician ID
            </label>
            <div
              style={{
                padding: "8px 12px",
                background: "#F8FAFC",
                border: "1px solid #E2E8F0",
                borderRadius: "6px",
                fontSize: "13px",
                fontWeight: 700,
                color: "#0F172A",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <span>
                {isEditing
                  ? editingTechId
                    ? `TECH-${editingTechId}`
                    : "TECH-101"
                  : `TECH-${technicians.length + 101}`}
              </span>
              <span
                style={{
                  fontSize: "10px",
                  background: "#DCFCE7",
                  color: "#15803D",
                  padding: "2px 8px",
                  borderRadius: "10px",
                  fontWeight: 800,
                }}
              >
                AUTO-ASSIGNED
              </span>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label
              style={{
                fontSize: "11px",
                fontWeight: "bold",
                color: "#475569",
                textTransform: "uppercase",
              }}
            >
              Full Name <span style={{ color: "#ef4444" }}>*</span>
            </label>
            <input
              type="text"
              name="technician_name"
              value={techFormData.technician_name}
              onChange={handleFormChange}
              placeholder="e.g. Rajesh Kumar"
              className="tld-search-input-style"
              style={{
                width: "100%",
                padding: "8px 12px",
                border: formErrors.technician_name
                  ? "1px solid #f87171"
                  : "1px solid #e2e8f0",
                borderRadius: "6px",
                fontSize: "13px",
                boxSizing: "border-box",
              }}
            />
            {formErrors.technician_name && (
              <span
                style={{
                  fontSize: "11px",
                  color: "#ef4444",
                  fontWeight: "bold",
                }}
              >
                {formErrors.technician_name}
              </span>
            )}
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label
              style={{
                fontSize: "11px",
                fontWeight: "bold",
                color: "#475569",
                textTransform: "uppercase",
              }}
            >
              Skill <span style={{ color: "#ef4444" }}>*</span>
            </label>
            <SkillComboSelect
              name="technician_skill"
              value={techFormData.technician_skill}
              onChange={(val) => {
                setTechFormData((prev) => ({ ...prev, technician_skill: val }));
                if (formErrors.technician_skill) {
                  setFormErrors((prev) => ({ ...prev, technician_skill: "" }));
                }
              }}
              placeholder="e.g. Electrical, HVAC"
              className="tld-search-input-style"
              hasError={!!formErrors.technician_skill}
              inputStyle={{
                width: "100%",
                padding: "8px 12px",
                border: formErrors.technician_skill
                  ? "1px solid #f87171"
                  : "1px solid #e2e8f0",
                borderRadius: "6px",
                fontSize: "13px",
                boxSizing: "border-box",
              }}
            />
            {formErrors.technician_skill && (
              <span
                style={{
                  fontSize: "11px",
                  color: "#ef4444",
                  fontWeight: "bold",
                }}
              >
                {formErrors.technician_skill}
              </span>
            )}
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label
              style={{
                fontSize: "11px",
                fontWeight: "bold",
                color: "#475569",
                textTransform: "uppercase",
              }}
            >
              Location / Zone <span style={{ color: "#ef4444" }}>*</span>
            </label>
            <input
              type="text"
              name="technician_location"
              value={techFormData.technician_location}
              onChange={handleFormChange}
              placeholder="e.g. 13.0827,80.2707"
              className="tld-search-input-style"
              style={{
                width: "100%",
                padding: "8px 12px",
                border: formErrors.technician_location
                  ? "1px solid #f87171"
                  : "1px solid #e2e8f0",
                borderRadius: "6px",
                fontSize: "13px",
                boxSizing: "border-box",
              }}
            />
            {formErrors.technician_location && (
              <span
                style={{
                  fontSize: "11px",
                  color: "#ef4444",
                  fontWeight: "bold",
                }}
              >
                {formErrors.technician_location}
              </span>
            )}
          </div>

          <div style={{ color: "#64748b", fontSize: 12 }}>
            New technicians start Offline. Technicians manage availability from their portal.
          </div>

          <div style={{ display: "flex", gap: "10px", marginTop: "10px" }}>
            <button
              type="submit"
              className="btn-primary-style"
              disabled={formLoading}
              style={{
                flex: 1,
                padding: "10px",
                background: "#2F4F3E",
                color: "#fff",
                border: "none",
                borderRadius: "6px",
                fontSize: "13px",
                fontWeight: "bold",
                cursor: "pointer",
              }}
            >
              {formLoading
                ? "Saving..."
                : isEditing
                  ? "Update Technician"
                  : "Add Technician"}
            </button>
            <button
              type="button"
              className="btn-secondary-style"
              onClick={closeForm}
              style={{
                padding: "10px 16px",
                background: "#fff",
                color: "#475569",
                border: "1px solid #cbd5e1",
                borderRadius: "6px",
                fontSize: "13px",
                fontWeight: "bold",
                cursor: "pointer",
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
      <ConfirmationDialog
        open={techToDelete !== null}
        title="Deactivate technician?"
        message={techToDelete ? `Deactivate “${techToDelete.name}”? Their record and job history will be kept. You can reactivate them from Deactivated Technicians.` : ""}
        confirmLabel="Deactivate"
        busyLabel="Deactivating…"
        busy={deleteTechBusy}
        onConfirm={confirmDeleteTech}
        onCancel={() => setTechToDelete(null)}
      />
    </div>
  );
}
