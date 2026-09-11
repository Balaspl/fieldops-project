import React, {
  useState,
  useEffect,
  useCallback,
  useRef,
  useMemo,
} from "react";
import {
  getAllTechnicians,
  updateTechnicianAvailability,
  createTechnician,
  updateTechnician,
  deleteTechnician,
  getUniqueZones,
} from "../services/technicianService";
import usePageVisibility from "../hooks/usePageVisibility";
import useInterval from "../hooks/useInterval";
import StatusBadge from "../components/ui/StatusBadge";
import { Eye, Pencil, Trash2, ChevronDown } from "lucide-react";
import EmptyState from "../components/ui/EmptyState";
import { SkillComboSelect } from "../components/ui/SkillComboSelect";

const PAGE_SIZE = 8;
const REFRESH_MS = 5_000;
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
  return s || "Unknown";
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
    return new Date(ts).toLocaleDateString();
  } catch {
    return String(ts);
  }
}
function normTech(t: any): NormalizedTech {
  return {
    id: t.technician_id ?? t.id ?? Math.random(),
    name: t.technician_name ?? t.name ?? "Unknown",
    status: t.technician_status ?? t.status ?? "Unknown",
    skill: t.technician_skill ?? t.skills ?? t.skill ?? "—",
    location: t.technician_location ?? t.zone ?? t.location ?? "—",
    currentJobs: t.current_jobs ?? t.active_jobs ?? 0,
    maxJobs: t.max_jobs ?? 5,
    lastPing: t.last_ping ?? t.updated_at ?? null,
    phone: t.phone_number ?? t.phone ?? "—",
  };
}
function wPct(cur: number, max: number) {
  return max > 0 ? Math.min(Math.round((cur / max) * 100), 100) : 0;
}
function wColor(p: number) {
  return p >= 90 ? "high" : p >= 60 ? "mid" : "low";
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
    gap: "6px",
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

  tldStatusSelectWrap: {
    marginTop: "18px",
  } as React.CSSProperties,

  tldStatusSelectWrapLabel: {
    display: "block",
    fontSize: "10px",
    fontWeight: 600,
    color: "#2F4F3E",
    marginBottom: "6px",
  } as React.CSSProperties,

  tldStatusSelect: {
    width: "100%",
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
    boxSizing: "border-box",
  } as React.CSSProperties,

  tldSaveBtn: {
    width: "100%",
    marginTop: "14px",
    padding: "10px",
    background: "#7AAE8A",
    color: "#fff",
    border: "none",
    borderRadius: "8px",
    fontSize: "11.5px",
    fontWeight: 700,
    fontFamily: "'Inter', sans-serif",
    cursor: "pointer",
    transition: "background .2s",
    boxShadow: "0 2px 6px rgba(122,174,138,.25)",
    boxSizing: "border-box",
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

  @keyframes tldFadeInRow {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .tld-table-body tr {
    animation: tldFadeInRow 0.25s ease-out forwards !important;
  }
`;

const getStatusSelectStyle = (status: string): React.CSSProperties => {
  const s = (status || "").toLowerCase().trim();
  const base: React.CSSProperties = {
    ...styles.tldStatusSelect,
  };
  if (s === "available") {
    return {
      ...base,
      background: "#DDEEE5",
      color: "#2F4F3E",
      borderColor: "#B0D4BC",
    };
  }
  if (s === "busy") {
    return {
      ...base,
      background: "#FEF0D6",
      color: "#7A5120",
      borderColor: "#F0D09A",
    };
  }
  if (s === "offline") {
    return {
      ...base,
      background: "#F0F4F2",
      color: "#6B7280",
      borderColor: "#D0DCD4",
    };
  }
  if (s === "assigned") {
    return {
      ...base,
      background: "#E0F2FE",
      color: "#0369A1",
      borderColor: "#7DD3FC",
    };
  }
  if (s === "en route" || s === "en_route") {
    return {
      ...base,
      background: "#FEF9C3",
      color: "#854D0E",
      borderColor: "#FDE68A",
    };
  }
  if (s === "on site" || s === "on_site") {
    return {
      ...base,
      background: "#EDE9FE",
      color: "#6D28D9",
      borderColor: "#DDD6FE",
    };
  }
  if (s === "on break" || s === "on_break") {
    return {
      ...base,
      background: "#FEF0D6",
      color: "#92400E",
      borderColor: "#FCD29A",
    };
  }
  if (s === "suspended") {
    return {
      ...base,
      background: "#FEE2E2",
      color: "#991B1B",
      borderColor: "#FECACA",
    };
  }
  return base;
};

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

export default function TechnicianListPage() {
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
  const [newStatus, setNewStatus] = useState("");
  const [saving, setSaving] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | number | null>(null);

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
    technician_status: "Available",
  });

  const openAddForm = () => {
    setIsEditing(false);
    setEditingTechId(null);
    setTechFormData({
      technician_name: "",
      technician_skill: "",
      technician_location: "",
      technician_status: "Available",
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
        const fetchPromise = getAllTechnicians({
          search: debSearch || undefined,
          status: statusFilter !== "ALL" ? statusFilter : undefined,
          zone: zoneFilter !== "ALL" ? zoneFilter : undefined,
          skill: skillFilter !== "ALL" ? skillFilter : undefined,
          page: page,
          limit: PAGE_SIZE,
        });
        const delayPromise = silent
          ? Promise.resolve()
          : new Promise((resolve) => setTimeout(resolve, 1000));
        const [res] = await Promise.all([fetchPromise, delayPromise]);
        setTechnicians((res.data || []).map(normTech));
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
    [debSearch, statusFilter, zoneFilter, skillFilter, page],
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
    setSelected(tech);
    setNewStatus(normalizeStatus(tech.status));
    window.location.hash = `#/technicians/${tech.id}`;
  }
  function closeSidebar() {
    setSelected(null);
    if (window.location.hash.startsWith("#/technicians/")) {
      window.location.hash = "";
    }
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

  async function handleInlineStatusChange(techId: string | number, ns: string) {
    setUpdatingId(techId);
    try {
      await updateTechnicianAvailability(techId, ns);
      setTechnicians((prev) =>
        prev.map((t) => (t.id === techId ? { ...t, status: ns } : t)),
      );
      const tech = technicians.find((t) => t.id === techId);
      showToast(`${tech?.name || "Technician"} set to ${ns}`);
    } catch (err: any) {
      showToast(
        err.response?.data?.error ||
          err.response?.data?.detail ||
          "Failed to update status",
        "error",
      );
    } finally {
      setUpdatingId(null);
    }
  }

  async function handleSaveStatus() {
    if (!selected) return;
    setSaving(true);
    try {
      await updateTechnicianAvailability(selected.id, newStatus);
      setTechnicians((prev) =>
        prev.map((t) =>
          t.id === selected.id ? { ...t, status: newStatus } : t,
        ),
      );
      showToast(`${selected.name} set to ${newStatus}`);
      closeSidebar();
    } catch (err: any) {
      showToast(
        err.response?.data?.error ||
          err.response?.data?.detail ||
          "Failed to update status",
        "error",
      );
    } finally {
      setSaving(false);
    }
  }

  function handleManualRefresh() {
    fetchData(technicians.length > 0);
    setCountdown(0);
  }

  async function handleDeleteTech(tech: NormalizedTech) {
    if (!window.confirm(`Are you sure you want to delete "${tech.name}"?`))
      return;
    try {
      await deleteTechnician(tech.id);
      showToast(`${tech.name} deleted successfully`);
      fetchData(technicians.length > 0);
    } catch (err: any) {
      const msg =
        err.response?.data?.error ||
        err.response?.data?.detail ||
        "Failed to delete technician.";
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

      {/* Table Card */}
      <div style={styles.tldTableCard}>
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
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        minHeight: "180px",
                      }}
                    >
                      <span className="tld-live-loading-dot" />
                    </div>
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
                        <div
                          style={{
                            display: "inline-block",
                            position: "relative",
                            minWidth: "110px",
                          }}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <select
                            value={normalizeStatus(tech.status)}
                            onChange={(e) =>
                              handleInlineStatusChange(tech.id, e.target.value)
                            }
                            disabled={updatingId === tech.id}
                            className="tld-status-select-style"
                            style={{
                              ...getStatusSelectStyle(tech.status),
                              width: "100%",
                              padding: "4px 20px 4px 8px",
                              fontSize: "10px",
                              borderRadius: "6px",
                              appearance: "none",
                              opacity: updatingId === tech.id ? 0.6 : 1,
                              fontWeight: 600,
                            }}
                          >
                            <option value="Available">Available</option>
                            <option value="Busy">Busy</option>
                            <option value="Assigned">Assigned</option>
                            <option value="Offline">Offline</option>
                            <option value="En Route">En Route</option>
                            <option value="On Site">On Site</option>
                            <option value="On Break">On Break</option>
                            <option value="Suspended">Suspended</option>
                          </select>
                          <div
                            style={{
                              position: "absolute",
                              right: "8px",
                              top: "50%",
                              transform: "translateY(-50%)",
                              pointerEvents: "none",
                              color: getStatusSelectStyle(tech.status)
                                .color as string,
                              opacity: 0.8,
                            }}
                          >
                            <ChevronDown size={11} />
                          </div>
                        </div>
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
                            title="Delete technician"
                            aria-label="Delete technician"
                          >
                            <Trash2 size={15} />
                          </button>
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
      {selected && (
        <div style={styles.tldSidebarOverlay} onClick={closeSidebar} />
      )}
      <div
        className="tld-sidebar-responsive"
        style={{
          ...styles.tldSidebar,
          right: selected ? "0" : "-440px",
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
            <div style={styles.tldStatusSelectWrap}>
              <label style={styles.tldStatusSelectWrapLabel}>
                Update Availability Status
              </label>
              <select
                className="tld-status-select-style"
                style={styles.tldStatusSelect}
                value={newStatus}
                onChange={(e) => setNewStatus(e.target.value)}
              >
                <option value="Available">Available</option>
                <option value="Busy">Busy</option>
                <option value="Assigned">Assigned</option>
                <option value="Offline">Offline</option>
                <option value="En Route">En Route</option>
                <option value="On Site">On Site</option>
                <option value="On Break">On Break</option>
                <option value="Suspended">Suspended</option>
              </select>
              <button
                className="tld-save-btn-style"
                style={styles.tldSaveBtn}
                onClick={handleSaveStatus}
                disabled={
                  saving || newStatus === normalizeStatus(selected.status)
                }
              >
                {saving ? "Saving…" : "Save Status"}
              </button>
            </div>
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

          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label
              style={{
                fontSize: "11px",
                fontWeight: "bold",
                color: "#475569",
                textTransform: "uppercase",
              }}
            >
              {isEditing ? "Status" : "Initial Status"}
            </label>
            <select
              name="technician_status"
              value={techFormData.technician_status}
              onChange={handleFormChange}
              className="tld-select-style"
              style={{
                width: "100%",
                padding: "8px 12px",
                border: "1px solid #e2e8f0",
                borderRadius: "6px",
                fontSize: "13px",
                background: "#fff",
                boxSizing: "border-box",
              }}
            >
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
    </div>
  );
}
