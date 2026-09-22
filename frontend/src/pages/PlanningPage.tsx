import React, {
  useEffect,
  useState,
  useMemo,
  useRef,
} from "react";
import {
  GoogleMap,
  DirectionsRenderer,
  MarkerF,
  useLoadScript,
} from "@react-google-maps/api";
import { io, Socket } from "socket.io-client";
import {
  getTechnicians,
  getAvailableTechnicians,
  getPendingJobs,
  getPlannedAssignments,
  assignJob,
  assignJobsBulk,
  cancelJobsBulk,
  manualAssign,
  getOverrideHistory,
  getJobPlan,
  getAuditOverrides,
  assignJobDirect,
} from "../services/planningService";
import { getTechnicianETA } from "../services/etaService";
import LoadingSpinner from "../components/ui/LoadingSpinner";
import { Eye, Trash2, History, Search, ChevronDown, Share2, Loader2, Check, MapPin } from "lucide-react";
import EmptyState from "../components/ui/EmptyState";
import OverrideModal from "../components/notifications/OverrideModal";
import OverrideHistory from "../components/notifications/OverrideHistory";
import OverrideWarning from "../components/notifications/OverrideWarning";
import MetricsCards from "../components/dispatch/MetricsCards";
import DispatchQueueTable from "../components/dispatch/DispatchQueueTable";

import { getDispatchQueue } from "../services/dispatchQueueService";
import {
  extendSLA,
  cancelEscalatedJob,
  forceAssignEscalation,
} from "../services/escalationService";
import { CompactScorePanel } from "../components/assignment/ScoreDisplay";
import RankedTechTable from "../components/assignment/RankedTechTable";
import TopThreeHighlight, { RankedTechnician } from "../components/assignment/TopThreeHighlight";
import ReDispatchHistory from "../components/notifications/ReDispatchHistory";
import AlertBanner from "../components/notifications/AlertBanner";
import { getDeclinedJobs, reassignDeclinedJob } from "../services/customerPortalService";

const PAGE_SIZE = 8;

const normalizeStatus = (s: string) => (s || "").toLowerCase();

type DispatchRealtimeEvent = {
  job_id?: string | number;
  tenant_id?: string | number;
  old_status?: string | null;
  new_status?: string | null;
  timestamp?: string;
  technician?: {
    tech_id?: string | number;
    name?: string;
  };
};

type DispatchSocketStatus =
  | "connecting"
  | "connected"
  | "reconnecting"
  | "error"
  | "disabled";
  
const escapeCsvValue = (value: unknown): string => {
  const text = value == null ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
};

const getDispatchCorrelationId = (error: any): string | null => {
  const headers = error?.response?.headers;

  if (!headers) {
    return null;
  }

  const correlationId =
    typeof headers.get === "function"
      ? headers.get("X-Correlation-ID")
      : headers["x-correlation-id"] ||
        headers["X-Correlation-ID"];

  return typeof correlationId === "string" && correlationId.trim()
    ? correlationId.trim()
    : null;
};

const getDispatchBackendDetail = (error: any): string | null => {
  const detail =
    error?.response?.data?.detail ??
    error?.response?.data?.message ??
    error?.response?.data?.error;

  if (typeof detail === "string" && detail.trim()) {
    return detail.trim();
  }

  if (
    detail &&
    typeof detail === "object" &&
    typeof detail.message === "string" &&
    detail.message.trim()
  ) {
    return detail.message.trim();
  }

  return null;
};

const formatDispatchFailure = (
  error: any,
  action: string,
  fallback: string
): string => {
  const status = error?.response?.status;
  const detail = getDispatchBackendDetail(error);

  let message: string;

  switch (status) {
    case 400:
    case 422:
      message = detail
        ? `${action} was rejected by backend validation: ${detail}`
        : `${action} could not be completed because the request failed backend validation.`;
      break;

    case 403:
      message =
        `You do not have permission to perform ${action.toLowerCase()}.`;
      break;

    case 404:
      message =
        `The job or technician required for ${action.toLowerCase()} ` +
        `could not be found or is no longer available.`;
      break;

    case 409:
      message = detail
        ? `${action} could not be completed because of a dispatch conflict: ${detail}`
        : `${action} could not be completed because the job state has changed.`;
      break;

    case 429:
      message =
        `The dispatch service is temporarily rate-limited. ` +
        `Please wait and try ${action.toLowerCase()} again.`;
      break;

    default:
      if (!error?.response) {
        message =
          `The dispatch service could not be reached while attempting ` +
          `${action.toLowerCase()}. Please check the connection and try again.`;
      } else if (status >= 500) {
        message =
          `The dispatch service could not complete ${action.toLowerCase()} ` +
          `because of a server error. Please try again.`;
      } else {
        message = detail || fallback;
      }
  }

  const correlationId = getDispatchCorrelationId(error);

  return correlationId
    ? `${message} Reference ID: ${correlationId}`
    : message;
};

type DispatchConfirmationAction =
  | "ASSIGN"
  | "CANCEL"
  | "REASSIGN"
  | "OVERRIDE";

interface DispatchConfirmationState {
  action: DispatchConfirmationAction;
  jobIds: number[];
  technicianName?: string;
  technicianId?: number | string;
  reason?: string;
}

const getDispatchActionLabel = (
  action: DispatchConfirmationAction
): string => {
  switch (action) {
    case "ASSIGN":
      return "Assignment";
    case "CANCEL":
      return "Cancellation";
    case "REASSIGN":
      return "Reassignment";
    case "OVERRIDE":
      return "Manual Override";
    default:
      return "Dispatch Action";
  }
};

const getPriorityStyle = (priority: string): React.CSSProperties => {
  const p = (priority || "").toUpperCase();
  const base: React.CSSProperties = {
    fontSize: "10px",
    fontWeight: 700,
    padding: "3px 8px",
    borderRadius: "20px",
    textTransform: "uppercase",
    letterSpacing: "0.03em",
    display: "inline-block",
  };
  if (p === "CRITICAL" || p === "P1") return { ...base, background: "#FAE5E5", color: "#7A2020" };
  if (p === "HIGH" || p === "P2") return { ...base, background: "#FEF0D6", color: "#7A5120" };
  if (p === "MEDIUM" || p === "P3") return { ...base, background: "#FDFBDC", color: "#706020" };
  if (p === "LOW" || p === "P4" || p === "P5") return { ...base, background: "#DDEEE5", color: "#2F4F3E" };
  return { ...base, background: "#F0F4F2", color: "#6B7280" };
};

const isSkillMatching = (techSkill: string, jobRequiredSkill?: string, jobServiceType?: string): boolean => {
  if (!techSkill) return true;
  const tSkill = techSkill.trim().toUpperCase().replace(/_/g, " ");
  const jSkill = jobRequiredSkill ? jobRequiredSkill.trim().toUpperCase().replace(/_/g, " ") : "";
  const jType = jobServiceType ? jobServiceType.trim().toUpperCase().replace(/_/g, " ") : "";

  if (jSkill && (tSkill === jSkill || tSkill.includes(jSkill) || jSkill.includes(tSkill))) return true;
  if (jType && (tSkill === jType || tSkill.includes(jType) || jType.includes(tSkill))) return true;

  const isPlumbJob = jSkill.includes("PLUMB") || jSkill.includes("PLUMP") || jType.includes("PLUMB") || jType.includes("PLUMP");
  const isPlumbTech = tSkill.includes("PLUMB") || tSkill.includes("PLUMP");

  const isElecJob = jSkill.includes("ELEC") || jType.includes("ELEC");
  const isElecTech = tSkill.includes("ELEC");

  const isHvacJob = jSkill.includes("HVAC") || jSkill.includes("AC") || jType.includes("HVAC") || jType.includes("AC");
  const isHvacTech = tSkill.includes("HVAC") || tSkill.includes("AC");

  if (isPlumbJob && isPlumbTech) return true;
  if (isElecJob && isElecTech) return true;
  if (isHvacJob && isHvacTech) return true;

  return true;
};

interface PendingJob {
  id: number;
  customer_name: string;
  location?: string;
  priority?: string;
  service_type?: string;
  required_skill?: string;
  issue_description?: string;
  redispatched?: boolean;
  job_status?: string;
  status?: string;
  sla_deadline?: string;
  attempt_count?: number;
}

interface PlannedAssignment {
  job_id: number;
  technician: string;
  skill?: string;
  customer: string;
  location?: string;
  priority?: string;
  status?: string;
  current_jobs: number;
  max_jobs: number;
}

interface Technician {
  technician_id: number;
  tech_id?: string;
  technician_name: string;
  technician_skill: string;
  technician_status: string;
  technician_location?: string;
  current_jobs?: number;
  max_jobs?: number;
}

interface ScoreData {
  composite_score: number;
  proximity_score: number;
  skill_score: number;
  workload_score: number;
  distance_km: number;
  active_jobs: number;
  max_capacity: number;
  is_top_3: boolean;
}

interface ForceAssignJobItem {
  id: number;
  title: string;
  location?: string;
}

interface OverrideHistoryItem {
  id: number;
  title: string;
}

const styles = {
  planningDashboard: {
    fontFamily: "'Inter', sans-serif",
    background: "#EEF4F1",
    height: "100%",
    maxHeight: "100%",
    padding: "10px 14px",
    color: "#1F2933",
    display: "flex",
    flexDirection: "column",
    gap: "8px",
    boxSizing: "border-box",
    overflow: "hidden",
  } as React.CSSProperties,

  refreshIconBtn: {
    background: "#FFFFFF",
    border: "1px solid #E3ECE7",
    color: "#2F4F3E",
    padding: "7px 14px",
    borderRadius: "8px",
    fontWeight: 600,
    fontSize: "12px",
    cursor: "pointer",
    transition: "all .2s",
    boxShadow: "0 1px 3px rgba(47, 79, 62, .06)",
  } as React.CSSProperties,

  planningTabs: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "8px",
    background: "#FFFFFF",
    border: "1px solid #E2E8F0",
    borderRadius: "10px",
    boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
    padding: "0 12px",
    boxSizing: "border-box",
    minHeight: "48px",
  } as React.CSSProperties,

  planningTab: {
    flex: "none",
    display: "flex",
    alignItems: "center",
    gap: "7px",
    padding: "0 4px",
    border: "none",
    borderRadius: 0,
    background: "transparent",
    color: "#94A3B8",
    fontSize: "13px",
    fontWeight: 600,
    cursor: "pointer",
    transition: "color 0.18s ease, border-color 0.18s ease",
    position: "relative",
    whiteSpace: "nowrap",
    height: "48px",
    letterSpacing: "0.01em",
    boxShadow: "none",
    outline: "none",
  } as React.CSSProperties,

  planningTabActive: {
    background: "transparent",
    color: "#16A34A",
    borderBottom: "2.5px solid #16A34A",
    fontWeight: 700,
  } as React.CSSProperties,

  planningTabCount: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    minWidth: "20px",
    height: "20px",
    padding: "0 6px",
    borderRadius: "6px",
    fontSize: "11px",
    fontWeight: 700,
    lineHeight: 1,
    background: "#F1F5F9",
    color: "#64748B",
    transition: "all 0.25s ease",
  } as React.CSSProperties,

  planningTabCountActive: {
    background: "#DCFCE7",
    color: "#15803D",
  } as React.CSSProperties,

  planningTabDot: {
    width: "7px",
    height: "7px",
    borderRadius: "50%",
    transition: "transform 0.2s ease",
    flexShrink: 0,
  } as React.CSSProperties,

  dashboardSection: {
    background: "#FFFFFF",
    borderRadius: "12px",
    boxShadow: "0 1px 4px rgba(47, 79, 62, 0.07)",
    border: "1px solid #E3ECE7",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    boxSizing: "border-box",
    flex: 1,
  } as React.CSSProperties,

  topThreeWrapper: {
    padding: "10px 14px 0",
    boxSizing: "border-box",
    maxHeight: "280px",
    overflowY: "auto",
    borderBottom: "1px solid #E3ECE7",
    background: "#FAFDFB",
  } as React.CSSProperties,

  sectionContent: {
    flex: 1,
    minHeight: "200px",
    display: "flex",
    flexDirection: "column",
    overflow: "visible",
  } as React.CSSProperties,
  tableContainer: {
    overflowX: "auto",
    overflowY: "auto",
    flex: 1,
    minHeight: 0,
  } as React.CSSProperties,

  dashboardTable: {
    width: "100%",
    borderCollapse: "collapse",
  } as React.CSSProperties,

  dashboardTableTh: {
    background: "#F6FAF8",
    padding: "4px 8px",
    textAlign: "left",
    fontSize: "9.5px",
    fontWeight: 700,
    color: "#6B7280",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    borderBottom: "1px solid #E3ECE7",
  } as React.CSSProperties,

  dashboardTableTd: {
    padding: "4px 8px",
    fontSize: "11.5px",
    color: "#1F2933",
    borderBottom: "1px solid #F0F6F2",
    verticalAlign: "middle",
  } as React.CSSProperties,

  jobIdCell: {
    fontWeight: 700,
    color: "#5C9470",
  } as React.CSSProperties,

  customerCell: {
    fontWeight: 600,
    color: "#2F4F3E",
  } as React.CSSProperties,

  issueSub: {
    display: "block",
    fontSize: "11.5px",
    color: "#6B7280",
    fontWeight: 400,
    marginTop: "2px",
  } as React.CSSProperties,

  assignmentActionCell: {
    width: "330px",
    minWidth: "330px",
  } as React.CSSProperties,

  assignmentUi: {
    display: "flex",
    gap: "8px",
    alignItems: "center",
    width: "100%",
  } as React.CSSProperties,

  techSelect: {
    height: "34px",
    padding: "0 10px",
    borderRadius: "6px",
    border: "1.5px solid #E3ECE7",
    fontSize: "12px",
    color: "#1F2933",
    outline: "none",
    background: "#FFFFFF",
    width: "100%",
    maxWidth: "170px",
    boxSizing: "border-box",
    transition: "border-color .2s",
  } as React.CSSProperties,

  assignBtn: {
    height: "34px",
    padding: "0 14px",
    background: "#7AAE8A",
    color: "#fff",
    border: "none",
    borderRadius: "6px",
    fontSize: "12px",
    fontWeight: 700,
    cursor: "pointer",
    whiteSpace: "nowrap",
    boxSizing: "border-box",
    transition: "all 0.2s ease",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
  } as React.CSSProperties,

  planningPagination: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "6px 10px",
    borderTop: "1px solid #E3ECE7",
    flexWrap: "wrap",
    gap: "6px",
    background: "#FAFCFB",
    boxSizing: "border-box",
  } as React.CSSProperties,

  planningPageInfo: {
    fontSize: "11px",
    color: "#6B7280",
    fontWeight: 500,
  } as React.CSSProperties,

  planningPageControls: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
  } as React.CSSProperties,

  planningPageBtn: {
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

  planningPageNumbers: {
    display: "flex",
    gap: "4px",
  } as React.CSSProperties,

  planningPageNum: {
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

  planningPageNumActive: {
    background: "#7AAE8A",
    borderColor: "#7AAE8A",
    color: "#fff",
  } as React.CSSProperties,

  techCell: {
    display: "flex",
    flexDirection: "column",
  } as React.CSSProperties,

  skillSub: {
    display: "block",
    fontString: "11.5px",
    color: "#6B7280",
    fontWeight: 400,
    marginTop: "2px",
  } as React.CSSProperties,

  statusBadge: {
    fontSize: "10px",
    fontWeight: 700,
    padding: "3px 9px",
    borderRadius: "20px",
    textTransform: "uppercase",
    display: "inline-block",
  } as React.CSSProperties,

  statusAssigned: {
    background: "#DDEEE5",
    color: "#2F4F3E",
    border: "1px solid #C3DDC9",
  } as React.CSSProperties,

  workloadInfo: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    minWidth: "110px",
  } as React.CSSProperties,

  workloadBar: {
    flex: 1,
    height: "5px",
    background: "#E3ECE7",
    borderRadius: "3px",
    overflow: "hidden",
  } as React.CSSProperties,

  workloadFill: {
    height: "100%",
    background: "#7AAE8A",
    borderRadius: "3px",
    transition: "width 0.3s",
  } as React.CSSProperties,

  workloadText: {
    fontSize: "11px",
    fontWeight: 600,
    color: "#6B7280",
    whiteSpace: "nowrap",
  } as React.CSSProperties,

  jobItemActions: {
    display: "flex",
    gap: "8px",
    alignItems: "center",
  } as React.CSSProperties,

  iconActionBtn: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    width: "28px",
    height: "28px",
    border: "none",
    borderRadius: 0,
    background: "none",
    padding: 0,
    cursor: "pointer",
    outline: "none",
  } as React.CSSProperties,

  popupOverlay: {
    position: "fixed",
    inset: 0,
    background: "#EEF4F1",
    zIndex: 2000,
    display: "flex",
    flexDirection: "column",
  } as React.CSSProperties,

  centeredModalOverlay: {
    position: "fixed",
    inset: 0,
    background: "rgba(15, 23, 42, 0.5)",
    backdropFilter: "blur(4px)",
    zIndex: 2000,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
  } as React.CSSProperties,

  viewJobModal: {
    background: "#FFFFFF",
    borderRadius: "16px",
    padding: 0,
    maxWidth: "460px",
    width: "94%",
    boxShadow: "0 20px 50px rgba(47,79,62,.18)",
    overflow: "hidden",
    boxSizing: "border-box",
  } as React.CSSProperties,

  viewModalHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "18px 22px 14px",
    borderBottom: "1px solid #E3ECE7",
    background: "#F6FAF8",
    boxSizing: "border-box",
  } as React.CSSProperties,

  viewModalHeaderH3: {
    fontSize: "15px",
    fontWeight: 700,
    color: "#2F4F3E",
    margin: 0,
  } as React.CSSProperties,

  viewModalBody: {
    padding: "18px 22px 22px",
    display: "flex",
    flexDirection: "column",
    gap: "10px",
    boxSizing: "border-box",
  } as React.CSSProperties,

  viewDetailRow: {
    display: "flex",
    alignItems: "flex-start",
    gap: "10px",
  } as React.CSSProperties,

  viewLabel: {
    minWidth: "110px",
    fontSize: "11px",
    fontWeight: 600,
    color: "#9CA3AF",
    textTransform: "uppercase",
    letterSpacing: ".03em",
    paddingTop: "2px",
  } as React.CSSProperties,

  viewValue: {
    fontSize: "13px",
    color: "#1F2937",
    fontWeight: 500,
    flex: 1,
  } as React.CSSProperties,

  metricFilterBanner: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: "10px",
    marginBottom: "14px",
    padding: "10px 14px",
    border: "1px solid #dbeafe",
    background: "linear-gradient(180deg, #f8fbff 0%, #eef6ff 100%)",
    borderRadius: "12px",
    boxSizing: "border-box",
  } as React.CSSProperties,

  metricFilterLeft: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
  } as React.CSSProperties,

  metricFilterIcon: {
    width: "36px",
    height: "36px",
    borderRadius: "10px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "#e0f2fe",
    color: "#2563eb",
    fontSize: "16px",
    boxShadow: "0 6px 16px rgba(37, 99, 235, 0.12)",
  } as React.CSSProperties,

  metricFilterTextWrap: {
    display: "flex",
    flexDirection: "column",
  } as React.CSSProperties,

  metricFilterLabel: {
    margin: 0,
    fontSize: "10px",
    color: "#64748b",
    fontWeight: 600,
  } as React.CSSProperties,

  metricFilterValue: {
    margin: "2px 0 0",
    fontSize: "16px",
    color: "#1d4ed8",
    fontWeight: 700,
    textTransform: "capitalize",
  } as React.CSSProperties,

  metricClearBtn: {
    border: "1px solid #bfdbfe",
    background: "#ffffff",
    color: "#2563eb",
    fontWeight: 600,
    borderRadius: "10px",
    padding: "8px 14px",
    fontSize: "13px",
    cursor: "pointer",
    transition: "all 0.2s ease",
  } as React.CSSProperties,

  planningHeaderSearchWrap: {
    position: "relative",
    maxWidth: "300px",
    width: "200px",
    transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
  } as React.CSSProperties,

  planningSearchIcon: {
    position: "absolute",
    left: "10px",
    top: "50%",
    transform: "translateY(-50%)",
    color: "#64748B",
    display: "flex",
    alignItems: "center",
    pointerEvents: "none",
    zIndex: 10,
    transition: "color 0.2s ease",
  } as React.CSSProperties,

  planningSearchInput: {
    width: "100%",
    padding: "6px 12px 6px 30px",
    fontSize: "12px",
    fontWeight: 600,
    color: "#1E293B",
    background: "#FFFFFF",
    border: "1.5px solid #CBD5E1",
    borderRadius: "8px",
    outline: "none",
    boxShadow: "0 2px 4px rgba(0, 0, 0, 0.02)",
    transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
    boxSizing: "border-box",
  } as React.CSSProperties,

  alertError: {
    background: "#FDF2F2",
    border: "1px solid #F5C6C6",
    color: "#9B3A3A",
  } as React.CSSProperties,

  alertSuccess: {
    background: "#EDFAF1",
    border: "1px solid #B0D4BC",
    color: "#2F4F3E",
    fontWeight: 500,
  } as React.CSSProperties,

  candidateModal: {
    background: "#EEF4F1",
    borderRadius: 0,
    padding: 0,
    width: "100%",
    height: "100%",
    maxWidth: "100%",
    maxHeight: "100vh",
    boxShadow: "none",
    overflow: "hidden",
    boxSizing: "border-box",
    display: "flex",
    flexDirection: "column",
  } as React.CSSProperties,

  candidateModalHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "20px 24px",
    borderBottom: "1px solid #E3ECE7",
    background: "#FFFFFF",
    boxSizing: "border-box",
  } as React.CSSProperties,
};

const localCss = `
  .planning-tab-btn-group {
    display: flex !important;
    gap: 0 !important;
    overflow-x: auto !important;
    white-space: nowrap !important;
    scrollbar-width: none !important;
    border-bottom: none !important;
    width: 100% !important;
    align-items: center !important;
  }
  .planning-tab-btn-group::-webkit-scrollbar {
    display: none !important;
  }
  .planning-tab-divider {
    width: 1px;
    height: 20px;
    background: #E2E8F0;
    flex-shrink: 0;
    margin: 0 2px;
  }
  .planning-tab-style {
    transition: color 0.18s ease, border-color 0.18s ease !important;
  }
  .planning-tab-style:hover:not(.active-tab-style) {
    color: #475569 !important;
    border-bottom-color: transparent !important;
  }
  .planning-tab-style:hover .planning-tab-dot-style {
    transform: scale(1.2) !important;
  }
  .planning-page-btn-style:hover:not(:disabled) {
    background-color: #EAF4EE !important;
    border-color: #7AAE8A !important;
  }
  .planning-page-num-style:hover {
    border-color: #7AAE8A !important;
    color: #2F4F3E !important;
  }
  .planning-refresh-btn-style:hover:not(:disabled) {
    background-color: #F6FAF8 !important;
    border-color: #7AAE8A !important;
  }
  .planning-header-search-wrap-style:focus-within {
    width: 260px !important;
    max-width: 300px !important;
  }
  .planning-header-search-wrap-style:focus-within .planning-search-icon-style {
    color: #2F4F3E !important;
  }
  .planning-search-input-style:focus {
    border-color: #2F4F3E !important;
    background-color: #FFFFFF !important;
    box-shadow: 0 4px 12px rgba(47, 79, 62, 0.08), 0 0 0 3px rgba(47, 79, 62, 0.12) !important;
  }
  .planning-search-input-style:hover:not(:focus) {
    border-color: #94A3B8 !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04) !important;
  }
  .tech-select-style:focus {
    border-color: #7AAE8A !important;
    box-shadow: 0 0 0 2px rgba(122, 174, 138, .12) !important;
  }
  .assign-btn-style:hover:not(:disabled) {
    background-color: #5C9470 !important;
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
  .metric-clear-btn-style:hover {
    background-color: #eff6ff !important;
    transform: translateY(-1px) !important;
  }
  .dashboard-table-row:hover td {
    background-color: #F8FBF9 !important;
  }
  .dashboard-table-row.selected-row-style td {
    background-color: #FFF8E7 !important;
    border-left: 3px solid #F59E0B !important;
  }
  .dashboard-table-row.selected-row-style:hover td {
    background-color: #FFF3D0 !important;
  }

  .alert-style-base {
    position: fixed;
    bottom: 24px;
    right: 24px;
    z-index: 3000;
    max-width: 380px;
    padding: 12px 16px;
    border-radius: 8px;
    font-size: 13px;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -4px rgba(0, 0, 0, 0.05);
    animation: slideUp 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  
  .alert-close-btn-style {
    background: none;
    border: none;
    color: currentColor;
    font-size: 20px;
    line-height: 1;
    padding: 0 4px;
    cursor: pointer;
    opacity: 0.65;
    transition: opacity 0.2s ease;
    flex-shrink: 0;
  }
  .alert-close-btn-style:hover {
    opacity: 1;
  }

  @keyframes slideUp {
    from {
      opacity: 0;
      transform: translateY(16px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  @media (max-width: 768px) {
    .planning-header-responsive {
      flex-direction: column !important;
      align-items: flex-start !important;
      gap: 12px !important;
    }
    .planning-header-controls-responsive {
      width: 100% !important;
      justify-content: space-between !important;
    }
    .metric-filter-banner-responsive {
      flex-direction: column !important;
      align-items: flex-start !important;
    }
    .metric-clear-btn-style {
      width: 100% !important;
    }
    .planning-tabs-responsive {
      flex-direction: column !important;
      align-items: stretch !important;
      gap: 0 !important;
      padding: 8px 12px !important;
    }
    .planning-tab-btn-group {
      width: 100% !important;
      border-bottom: none !important;
      padding-bottom: 0 !important;
    }
    .planning-tab-divider {
      display: none !important;
    }
    .planning-search-row-responsive {
      width: 100% !important;
      justify-content: flex-start !important;
      margin-bottom: 0 !important;
    }
    .planning-search-row-responsive .planning-header-search-wrap-style {
      width: 100% !important;
      max-width: none !important;
    }
    .alert-style-base {
      right: 16px !important;
      left: 16px !important;
      bottom: 74px !important;
      max-width: none !important;
    }
  }
  @media (max-width: 640px) {
    .planning-tabs-responsive {
      padding: 6px 10px 8px !important;
    }
    .planning-tab-style {
      padding-left: 8px !important;
      padding-right: 8px !important;
      font-size: 11.5px !important;
      gap: 5px !important;
    }
    .planning-tab-divider {
      display: none !important;
    }
  }

  @keyframes planningFadeInRow {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .planning-table-body tr {
    animation: planningFadeInRow 0.25s ease-out forwards !important;
  }
`;

const ShareTrackingLinkButton = ({ jobId }: { jobId: string | number }) => {
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);

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

  return (
    <button
      onClick={handleShare}
      disabled={loading}
      title={copied ? "Link Copied!" : "Share customer tracking link"}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: "28px",
        height: "28px",
        border: "none",
        borderRadius: 0,
        background: "none",
        padding: 0,
        cursor: "pointer",
        outline: "none",
        color: copied ? "#10B981" : "#3b82f6"
      }}
      className="icon-action-btn-style"
      aria-label={`Share tracking link for Job ${jobId}`}
    >
      {copied ? (
        <Check size={15} />
      ) : loading ? (
        <Loader2 size={15} className="animate-spin" />
      ) : (
        <Share2 size={15} />
      )}
    </button>
  );
};

function PlanningDashboard() {
  const [pendingJobs, setPendingJobs] = useState<PendingJob[]>([]);
  const [plannedAssignments, setPlannedAssignments] = useState<PlannedAssignment[]>([]);
  const [allTechsList, setAllTechsList] = useState<Technician[]>([]);
  const [totalPendingCount, setTotalPendingCount] = useState(0);
  const [totalPlannedCount, setTotalPlannedCount] = useState(0);

  const [jobsLoading, setJobsLoading] = useState(false);
  const [assignmentsLoading, setAssignmentsLoading] = useState(false);

  const [selectedTechs, setSelectedTechs] = useState<Record<number, string>>({});
  const [assigningJobId, setAssigningJobId] = useState<number | null>(null);
  const [manualOverrideJobId, setManualOverrideJobId] = useState<number | null>(null);
  const [selectedJobIds, setSelectedJobIds] = useState<number[]>([]);
  const [bulkAssigning, setBulkAssigning] = useState(false);
  const [bulkTechnicianId, setBulkTechnicianId] = useState<string>("");
  const [bulkCancelling, setBulkCancelling] = useState(false);

  const [selectedJobForRanking, setSelectedJobForRanking] = useState<PendingJob | null>(null);
  const [rankedCandidates, setRankedCandidates] = useState<RankedTechnician[]>([]);
  const [candidatesLoading, setCandidatesLoading] = useState(false);

  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");
  const [assignSuccessMsg, setAssignSuccessMsg] = useState("");

  const [showHistoryJobId, setShowHistoryJobId] = useState<number | null>(null);
  const [showHistoryJobTitle, setShowHistoryJobTitle] = useState("");
  const [forceAssignJob, setForceAssignJob] = useState<ForceAssignJobItem | null>(null);
  const [showOverrideHistoryForJob, setShowOverrideHistoryForJob] = useState<OverrideHistoryItem | null>(null);
  const [viewAssignmentOverride, setViewAssignmentOverride] = useState<any>(null);
  const [showOverrideHistoryForView, setShowOverrideHistoryForView] = useState(false);
  const {
    isLoaded: isRouteMapLoaded,
    loadError: routeMapLoadError,
  } = useLoadScript({
    googleMapsApiKey: import.meta.env.VITE_GOOGLE_MAPS_API_KEY || "",
  });

  const handleManualAssign = async (
    jobId: number,
    techId: number
  ) => {
    try {
      await manualAssign(jobId, techId);
      showAssignSuccess(
        "Job assigned manually successfully!"
      );
      fetchAllData();
    } catch (err: any) {
      const msg =
        err?.response?.data?.detail ||
        err?.response?.data?.error ||
        "Failed to manually assign job.";

      setError(msg);
      throw err;
    }
  };

  const [activeTab, setActiveTab] = useState("pending");

  const [pendingPage, setPendingPage] = useState(1);
  const [plannedPage, setPlannedPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState("");
  const [debSearchQuery, setDebSearchQuery] = useState("");
  const [exporting, setExporting] = useState(false);
  const [dispatchSocketStatus, setDispatchSocketStatus] =
    useState<DispatchSocketStatus>("connecting");

  const [dispatchSocketError, setDispatchSocketError] =
    useState("");

  const dispatchSocketRef = useRef<Socket | null>(null);

  const dispatchRefreshTimerRef =
    useRef<number | null>(null);

  const seenDispatchEventsRef =
    useRef<Set<string>>(new Set());

  const latestDispatchTimestampRef =
    useRef<Map<string, number>>(new Map());

  const refreshDashboardFromRealtimeRef =
    useRef<() => void>(() => {});

  const scheduleRealtimeRefreshRef =
    useRef<() => void>(() => {});
  const [viewAssignment, setViewAssignment] = useState<PlannedAssignment | null>(null);
  const [routeAssignment, setRouteAssignment] =
    useState<PlannedAssignment | null>(null);

  const [routeLoading, setRouteLoading] = useState(false);

  const [routeError, setRouteError] = useState("");

  const [routeEta, setRouteEta] = useState<{
    eta: string;
    duration_minutes: number;
    distance_meters: number;
    origin: { lat: number; lng: number };
    destination: { lat: number; lng: number };
  } | null>(null);

  const [routeDirections, setRouteDirections] = useState<any>(null);
  const [showJobMap, setShowJobMap] = useState(false);
  const [activeMetricFilter, setActiveMetricFilter] = useState("all");
  
  const [dispatchQueueCount, setDispatchQueueCount] = useState(0);

  const [declinedJobsList, setDeclinedJobsList] = useState<any[]>([]);
  const [declinedLoading, setDeclinedLoading] = useState(false);
  const [reassignModalJob, setReassignModalJob] = useState<any>(null);
  const [selectedReassignTechId, setSelectedReassignTechId] = useState<number | null>(null);
  const [reassigning, setReassigning] = useState(false);
  const eligibleReassignTechnicians = useMemo(
    () =>
      allTechsList.filter((tech) => {
        const status = normalizeStatus(
          tech.technician_status || ""
        );

        const currentJobs = Number(tech.current_jobs ?? 0);
        const maxJobs = Number(tech.max_jobs ?? 5);

        return (
          status === "available" &&
          currentJobs < maxJobs
        );
      }),
    [allTechsList]
  );

  type DispatchConfirmation = {
  action: string;
  jobIds: number[];
  technician?: string;
  technicianId?: number | string;
  details?: string;
  reasonRequired?: boolean;
  reasonPlaceholder?: string;
  confirmLabel: string;
  execute: (reason?: string) => Promise<void>;
};

  const [dispatchConfirmation, setDispatchConfirmation] =
    useState<DispatchConfirmation | null>(null);

  const [dispatchConfirmationReason, setDispatchConfirmationReason] =
    useState("");

  const [dispatchConfirmationLoading, setDispatchConfirmationLoading] =
    useState(false);

  const [dispatchConfirmationError, setDispatchConfirmationError] =
    useState("");

  const openDispatchConfirmation = (
    confirmation: DispatchConfirmation
  ) => {
    if (!confirmation.jobIds.length) {
      setError("At least one job must be selected for this dispatch action.");
      return;
    }

    setDispatchConfirmationReason("");
    setDispatchConfirmationError("");
    setDispatchConfirmation(confirmation);
  };

  const closeDispatchConfirmation = () => {
    if (dispatchConfirmationLoading) return;

    setDispatchConfirmation(null);
    setDispatchConfirmationReason("");
    setDispatchConfirmationError("");
  };

  const confirmDispatchAction = async () => {
    if (!dispatchConfirmation || dispatchConfirmationLoading) {
      return;
    }

    const reason = dispatchConfirmationReason.trim();

    if (dispatchConfirmation.reasonRequired && !reason) {
      setDispatchConfirmationError(
        "A reason is required before confirming this action."
      );
      return;
    }

    try {
      setDispatchConfirmationLoading(true);
      setDispatchConfirmationError("");
      setError("");

      await dispatchConfirmation.execute(
        dispatchConfirmation.reasonRequired ? reason : undefined
      );

      closeDispatchConfirmation();
    } catch (err: any) {
      const message = formatDispatchFailure(
        err,
        dispatchConfirmation.action,
        "The dispatch action could not be completed."
      );

      setDispatchConfirmationError(message);
    }
  };

  const fetchDeclinedJobsList = async () => {
    try {
      setDeclinedLoading(true);
      const res = await getDeclinedJobs();
      setDeclinedJobsList(res.data || []);
    } catch (err) {
      console.error(err);
    } finally {
      setDeclinedLoading(false);
    }
  };

  useEffect(() => {
    fetchDeclinedJobsList();
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebSearchQuery(searchQuery);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const handleMetricFilterChange = (filter: string, metricKey: string) => {
    console.log("Metric card clicked:", metricKey, filter);
    setActiveMetricFilter(metricKey);
    // Dispatched jobs have an assigned technician → they live in Planned Assignments
    if (metricKey === "dispatched") {
      setActiveTab("planned");
    } else {
      setActiveTab("pending");
    }
    setPendingPage(1);
  };

  const getMetricEmptyTitle = () => {
    if (activeMetricFilter === "dispatched") {
      return "No dispatched jobs found";
    }
    if (activeMetricFilter === "expired") {
      return "No expired jobs found";
    }
    if (activeMetricFilter === "redispatched") {
      return "No re-dispatched jobs found";
    }
    if (activeMetricFilter === "pending") {
      return "No unassigned jobs found";
    }
    return searchQuery.trim() ? "No jobs match your search" : "No unassigned jobs";
  };

  const getMetricEmptyDescription = () => {
    if (activeMetricFilter === "dispatched") {
      return "Dispatched jobs (with an assigned technician) are shown in the Planned Assignments tab.";
    }
    if (activeMetricFilter === "expired") {
      return "There are no jobs with an expired SLA in the current unassigned queue.";
    }
    if (activeMetricFilter === "redispatched") {
      return "There are no re-dispatched jobs (re-attempted more than once) in the current queue.";
    }
    if (activeMetricFilter === "pending") {
      return "There are no queued, assigned, or pending jobs available right now.";
    }
    return searchQuery.trim()
      ? "Try adjusting your search terms."
      : "All jobs are either assigned or completed.";
  };

  const fetchPendingJobs = async (search?: string) => {
    try {
      setJobsLoading(true);
      const [res] = await Promise.all([
        getPendingJobs({
          search: search || undefined,
          page: pendingPage,
          limit: PAGE_SIZE,
          active_filter: activeMetricFilter !== "all" && activeMetricFilter !== "dispatched" && activeMetricFilter !== "pending" ? activeMetricFilter : undefined
        }),
        new Promise(resolve => setTimeout(resolve, 1000))
      ]);
      setPendingJobs(res.data);
      const totalHeader = res.headers["x-total-count"] || res.headers["X-Total-Count"];
      setTotalPendingCount(totalHeader ? parseInt(totalHeader, 10) : res.data.length);
    } catch {
      setError("Failed to load unassigned jobs. Please try again.");
    } finally {
      setJobsLoading(false);
    }
  };

  const fetchPlannedAssignments = async (search?: string) => {
    try {
      setAssignmentsLoading(true);
      const [res] = await Promise.all([
        getPlannedAssignments({
          search: search || undefined,
          page: plannedPage,
          limit: PAGE_SIZE
        }),
        new Promise(resolve => setTimeout(resolve, 1000))
      ]);
      setPlannedAssignments(res.data);
      const totalHeader = res.headers["x-total-count"] || res.headers["X-Total-Count"];
      setTotalPlannedCount(totalHeader ? parseInt(totalHeader, 10) : res.data.length);
    } catch {
      setError("Failed to load planned assignments. Please try again.");
    } finally {
      setAssignmentsLoading(false);
    }
  };

  const fetchTechniciansList = async () => {
    try {
      const res = await getTechnicians();
      setAllTechsList(res.data);
    } catch {
      console.error("Could not fetch technicians list for dropdown.");
    }
  };

  const fetchDispatchQueueCount = async () => {
    try {
      const res = await getDispatchQueue({ limit: 100 });
      if (res && res.data) {
        setDispatchQueueCount(res.data.length);
      }
    } catch {
      console.warn("Could not fetch dispatch queue count");
    }
  };

  const fetchAllData = () => {
    setError("");
    setSuccessMsg("");
    fetchPendingJobs(debSearchQuery);
    fetchPlannedAssignments(debSearchQuery);
    fetchTechniciansList();
    fetchDispatchQueueCount();
    fetchDeclinedJobsList();
  };

  const refreshDashboardFromRealtime = () => {
    fetchPendingJobs(debSearchQuery);
    fetchPlannedAssignments(debSearchQuery);
    fetchTechniciansList();
    fetchDispatchQueueCount();
    fetchDeclinedJobsList();
  };

  refreshDashboardFromRealtimeRef.current =
    refreshDashboardFromRealtime;

  const scheduleRealtimeRefresh = () => {
    if (dispatchRefreshTimerRef.current !== null) {
      return;
    }

    dispatchRefreshTimerRef.current =
      window.setTimeout(() => {
        dispatchRefreshTimerRef.current = null;
        refreshDashboardFromRealtimeRef.current();
      }, 250);
  };

  scheduleRealtimeRefreshRef.current =
    scheduleRealtimeRefresh;

  const parseCoordinates = (
    value?: string
  ): { lat: number; lng: number } | null => {
    if (!value || typeof value !== "string") {
      return null;
    }
    const parts = value.split(",").map((part) => part.trim());

    if (parts.length !== 2) {
      return null;
    }

    const lat = Number(parts[0]);
    const lng = Number(parts[1]);

    if (
      !Number.isFinite(lat) ||
      !Number.isFinite(lng) ||
      lat < -90 ||
      lat > 90 ||
      lng < -180 ||
      lng > 180
    ) {
      return null;
    }

    return { lat, lng };
  };

  const handleViewRoute = async (assignment: PlannedAssignment) => {
    setRouteAssignment(assignment);
    setRouteLoading(true);
    setRouteError("");
    setRouteEta(null);
    setRouteDirections(null);

    try {
      const technician = allTechsList.find(
        (tech) =>
          String(tech.technician_name).trim().toLowerCase() ===
          String(assignment.technician).trim().toLowerCase()
      );

      if (!technician) {
        throw new Error(
          "Technician details are unavailable. Please refresh the technician data and try again."
        );
      }

      const technicianIdentifier =
        technician.tech_id || String(technician.technician_id);

      if (!technicianIdentifier) {
        throw new Error(
          "Technician route identifier is unavailable."
        );
      }

      const origin = parseCoordinates(technician.technician_location);
      const destination = parseCoordinates(assignment.location);

      if (!origin) {
        throw new Error(
          "Technician location is missing or invalid. The route cannot be displayed."
        );
      }

      if (!destination) {
        throw new Error(
          "Job location is missing or invalid. The route cannot be displayed."
        );
      }

      if (!isRouteMapLoaded) {
        throw new Error(
          "Google Maps is not ready yet. Please try again in a moment."
        );
      }

      if (typeof google === "undefined" || !google.maps) {
        throw new Error(
          "Google Maps is unavailable. Please verify the Maps configuration."
        );
      }

      const etaResult = await getTechnicianETA(
        String(technicianIdentifier),
        Number(assignment.job_id)
      );

      const etaData: any =
        (etaResult as any)?.data ??
        (etaResult as any) ??
        {};

      const rawDuration = Number(
        etaData?.duration_minutes ??
        etaData?.duration ??
        etaData?.eta_minutes ??
        0
      );

      const durationMinutes =
        rawDuration > 0
          ? rawDuration > 300
            ? Math.ceil(rawDuration / 60)
            : Math.ceil(rawDuration)
          : 0;

      const etaText =
        typeof etaData?.eta === "string" && etaData.eta.trim()
          ? etaData.eta
          : durationMinutes > 0
          ? `${durationMinutes} min`
          : "ETA unavailable";

      setRouteEta({
        eta: etaText,
        duration_minutes: durationMinutes,
        distance_meters: Number(etaData?.distance_meters ?? 0),
        origin,
        destination,
      });

      const directionsService = new google.maps.DirectionsService();

      directionsService.route(
        {
          origin,
          destination,
          travelMode: google.maps.TravelMode.DRIVING,
        },
        (result, status) => {
          if (
            status !== google.maps.DirectionsStatus.OK ||
            !result
          ) {
            setRouteDirections(null);
            setRouteError(
              "Google Maps could not calculate a route for these locations."
            );
            return;
          }

          setRouteDirections(result);
        }
      );
    } catch (err: any) {
      console.error("Failed to load technician route:", err);

      setRouteEta(null);
      setRouteDirections(null);

      const detail =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        err?.message;

      setRouteError(
        detail ||
          "Failed to load route information. Please try again."
      );
    } finally {
      setRouteLoading(false);
    }
  };

  useEffect(() => {
    fetchTechniciansList();
    fetchDispatchQueueCount();
  }, []);

  useEffect(() => {
    setPendingPage(1);
    setPlannedPage(1);
  }, [debSearchQuery, activeMetricFilter]);

  useEffect(() => {
    fetchPendingJobs(debSearchQuery);
  }, [debSearchQuery, pendingPage, activeMetricFilter]);

  useEffect(() => {
    fetchPlannedAssignments(debSearchQuery);
  }, [debSearchQuery, plannedPage]);

  useEffect(() => {
    const tenantId =
      (typeof window !== "undefined"
        ? window.localStorage.getItem("tenant_id")
        : null) ||
      import.meta.env.VITE_TENANT_ID ||
      "";

    if (!tenantId) {
      setDispatchSocketStatus("disabled");
      setDispatchSocketError(
        "Live dashboard updates are unavailable because no tenant context is available."
      );
      return;
    }

    const socketBaseUrl = (
      import.meta.env.VITE_DISPATCH_SOCKET_URL ||
      "http://localhost:4000"
    ).replace(/\/$/, "");

    const socket = io(
      `${socketBaseUrl}/dispatch-dashboard`,
      {
        auth: {
          tenant_id: tenantId,
        },
        transports: ["websocket", "polling"],
        reconnection: true,
        reconnectionAttempts: Infinity,
        reconnectionDelay: 1000,
        reconnectionDelayMax: 10000,
        timeout: 10000,
      }
    );

    dispatchSocketRef.current = socket;

    setDispatchSocketStatus("connecting");
    setDispatchSocketError("");

    const onConnect = () => {
      setDispatchSocketStatus("connected");
      setDispatchSocketError("");
    };

    const onDisconnect = (reason?: string) => {
      if (reason === "io client disconnect") {
        return;
      }

      setDispatchSocketStatus("reconnecting");
    };

    const onConnectError = (socketError: Error) => {
      setDispatchSocketStatus("error");
      setDispatchSocketError(
        socketError?.message ||
          "Unable to connect to live dashboard updates."
      );
    };

    const onDispatchEvent = (
      eventName: string,
      rawPayload: unknown
    ) => {
      if (
        !rawPayload ||
        typeof rawPayload !== "object" ||
        Array.isArray(rawPayload)
      ) {
        return;
      }

      const payload =
        rawPayload as DispatchRealtimeEvent;

      const jobId = payload.job_id;
      const eventTenantId = payload.tenant_id;

      if (
        jobId === undefined ||
        jobId === null ||
        eventTenantId === undefined ||
        eventTenantId === null
      ) {
        return;
      }

      if (
        String(eventTenantId) !== String(tenantId)
      ) {
        return;
      }

      const jobKey = String(jobId);

      const timestampMs = payload.timestamp
        ? Date.parse(payload.timestamp)
        : Number.NaN;

      if (Number.isFinite(timestampMs)) {
        const latestTimestamp =
          latestDispatchTimestampRef.current.get(
            jobKey
          );

        if (
          latestTimestamp !== undefined &&
          timestampMs < latestTimestamp
        ) {
          return;
        }

        latestDispatchTimestampRef.current.set(
          jobKey,
          timestampMs
        );
      }

      const eventKey = [
        eventName,
        jobKey,
        payload.timestamp || "",
        payload.old_status || "",
        payload.new_status || "",
        payload.technician?.tech_id ?? "",
      ].join("|");

      if (
        seenDispatchEventsRef.current.has(eventKey)
      ) {
        return;
      }

      seenDispatchEventsRef.current.add(eventKey);

      if (
        seenDispatchEventsRef.current.size > 500
      ) {
        const oldestKey =
          seenDispatchEventsRef.current
            .values()
            .next()
            .value;

        if (oldestKey !== undefined) {
          seenDispatchEventsRef.current.delete(
            oldestKey
          );
        }
      }

      if (
        latestDispatchTimestampRef.current.size > 500
      ) {
        const oldestJobId =
          latestDispatchTimestampRef.current
            .keys()
            .next()
            .value;

        if (oldestJobId !== undefined) {
          latestDispatchTimestampRef.current.delete(
            oldestJobId
          );
        }
      }

      scheduleRealtimeRefreshRef.current();
    };

    socket.on("connect", onConnect);
    socket.on("disconnect", onDisconnect);
    socket.on("connect_error", onConnectError);
    socket.onAny(onDispatchEvent);

    return () => {
      if (
        dispatchRefreshTimerRef.current !== null
      ) {
        window.clearTimeout(
          dispatchRefreshTimerRef.current
        );

        dispatchRefreshTimerRef.current = null;
      }

      socket.off("connect", onConnect);
      socket.off("disconnect", onDisconnect);
      socket.off(
        "connect_error",
        onConnectError
      );
      socket.offAny(onDispatchEvent);

      socket.disconnect();

      if (
        dispatchSocketRef.current === socket
      ) {
        dispatchSocketRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (viewAssignment) {
      getOverrideHistory(viewAssignment.job_id)
        .then(res => {
          if (res && res.data && res.data.length > 0) {
            setViewAssignmentOverride(res.data[0]);
          } else {
            setViewAssignmentOverride(null);
          }
        })
        .catch(err => {
          console.warn("Failed to fetch override history for view modal", err);
          setViewAssignmentOverride(null);
        });
    } else {
      setViewAssignmentOverride(null);
    }
  }, [viewAssignment]);

  const generateRankedCandidates = (job: PendingJob, techsOverride?: Technician[]): RankedTechnician[] => {
    const techs = techsOverride || allTechsList;
    if (!techs || techs.length === 0) return [];

    const sType = (job.service_type || "").toLowerCase().trim();
    const reqSkill = (job.required_skill || "").toLowerCase().trim();

    return techs
      .map((t, index) => {
        const status = normalizeStatus(t.technician_status);
        const isAvailable = status === "available" || status === "assigned";
        
        const rawTechSkill = (t.technician_skill || "").toLowerCase().trim();

        // Skill category checks
        const isPlumbJob = sType.includes("plumb") || sType.includes("plump") || reqSkill.includes("plumb") || reqSkill.includes("plump");
        const isPlumbTech = rawTechSkill.includes("plumb") || rawTechSkill.includes("plump");

        const isElecJob = sType.includes("elec") || reqSkill.includes("elec");
        const isElecTech = rawTechSkill.includes("elec");

        const isHvacJob = sType.includes("hvac") || sType.includes("ac") || reqSkill.includes("hvac") || reqSkill.includes("ac");
        const isHvacTech = rawTechSkill.includes("hvac") || rawTechSkill.includes("ac");

        let hasSkillMatch = false;
        if (isPlumbJob && isPlumbTech) {
          hasSkillMatch = true;
        } else if (isElecJob && isElecTech) {
          hasSkillMatch = true;
        } else if (isHvacJob && isHvacTech) {
          hasSkillMatch = true;
        } else if (sType && (rawTechSkill.includes(sType) || sType.includes(rawTechSkill))) {
          hasSkillMatch = true;
        } else if (reqSkill && (rawTechSkill.includes(reqSkill) || reqSkill.includes(rawTechSkill))) {
          hasSkillMatch = true;
        }

        const skillScore = hasSkillMatch ? 100.0 : 50.0;
        const proximityScore = Math.max(50, 95 - index * 8);
        const workloadScore = Math.max(40, 100 - (t.current_jobs || 0) * 15);
        
        // Composite score
        const statusMultiplier = isAvailable ? 1.0 : 0.65;
        const composite = Math.round(
          (skillScore * 0.45 + proximityScore * 0.3 + workloadScore * 0.25) * statusMultiplier
        );

        return {
          technician_id: t.technician_id,
          technician_name: t.technician_name,
          technician_skill: t.technician_skill || "General",
          technician_status: t.technician_status || "Available",
          composite_score: composite,
          proximity_score: proximityScore,
          skill_score: skillScore,
          workload_score: workloadScore,
          distance_km: parseFloat(((index * 2.4 + 1.2)).toFixed(1)),
          active_jobs: t.current_jobs ?? 0,
          max_capacity: t.max_jobs ?? 5,
        };
      })
      .sort((a, b) => b.composite_score - a.composite_score);
  };

  const handleJobRowClick = async (job: PendingJob) => {
    if (selectedJobForRanking?.id === job.id) {
      setSelectedJobForRanking(null);
      setRankedCandidates([]);
      return;
    }
    setSelectedJobForRanking(job);
    setCandidatesLoading(true);
    setRankedCandidates([]);

    // Ensure technicians list is loaded for fallback ranking
    let techs = allTechsList;
    if (!techs || techs.length === 0) {
      try {
        const techRes = await getTechnicians();
        techs = techRes.data;
        setAllTechsList(techs);
      } catch {
        console.warn("Could not fetch technicians for candidate generation");
      }
    }

    try {
      const [res] = await Promise.all([
        getJobPlan(job.id),
        new Promise(resolve => setTimeout(resolve, 1000))
      ]);
      if (res && res.ranked_technicians && res.ranked_technicians.length > 0) {
        const mapped: RankedTechnician[] = res.ranked_technicians.map((rt: any) => {
          const matched = techs.find(
            (t) => t.technician_id === rt.tech_id || String(t.technician_id) === String(rt.tech_id)
          );
          return {
            technician_id: matched ? matched.technician_id : (parseInt(String(rt.tech_id).replace(/\D/g, ''), 10) || 1),
            technician_name: rt.name,
            technician_skill: rt.skill || 'HVAC',
            technician_status: rt.status || 'Available',
            composite_score: rt.composite_score || 0,
            proximity_score: rt.proximity_score || 0,
            skill_score: rt.skill_score || 0,
            workload_score: rt.workload_score || 0,
            distance_km: rt.distance_km || 0,
            active_jobs: rt.active_jobs || 0,
            max_capacity: rt.max_capacity || 5
          };
        });
        const fallback = generateRankedCandidates(job, techs);
        const mappedIds = new Set(mapped.map(m => m.technician_id));
        const combined = [...mapped, ...fallback.filter(f => !mappedIds.has(f.technician_id))];
        setRankedCandidates(combined);
      } else {
        setRankedCandidates(generateRankedCandidates(job, techs));
      }
    } catch (err) {
      console.warn("Failed to fetch AI plan from backend, falling back to mock ranking", err);
      await new Promise(resolve => setTimeout(resolve, 1000));
      setRankedCandidates(generateRankedCandidates(job, techs));
    } finally {
      setCandidatesLoading(false);
    }
  };

  const handleTopThreeClose = () => {
    setSelectedJobForRanking(null);
    setRankedCandidates([]);
  };

  const handleTechSelect = (jobId: number, techId: string) => {
    setSelectedTechs((prev) => ({ ...prev, [jobId]: techId }));
  };

  const handleAssignJob = async (jobId: number, techIdOverride?: string) => {
    const techId = techIdOverride || selectedTechs[jobId];
    if (!techId) return;
    const tech = allTechsList.find(
      (t) => t.technician_id === parseInt(techId, 10)
    );
    if (tech && normalizeStatus(tech.technician_status) !== "available" && normalizeStatus(tech.technician_status) !== "assigned") {
      setError(
        `Cannot assign: ${tech.technician_name} is currently ${tech.technician_status}. Please select an Available or Assigned technician.`
      );
      return;
    }
    try {
      setAssigningJobId(jobId);
      setError("");
      await assignJob(jobId, parseInt(techId, 10));
      setSelectedTechs((prev) => {
        const next = { ...prev };
        delete next[jobId];
        return next;
      });
      if (selectedJobForRanking?.id === jobId) {
        setSelectedJobForRanking(null);
        setRankedCandidates([]);
      }
      const techName = tech ? tech.technician_name : "Technician";
      showAssignSuccess(`${techName} has been assigned to this work.`);
      fetchAllData();
    } catch (err: any) {
      const message = formatDispatchFailure(
        err,
        "Job assignment",
        "Failed to assign technician."
      );

      setError(message);
      throw err;
    } finally {
      setAssigningJobId(null);
    }
  };


  const requestAssignJob = (jobId: number) => {
    const techId = selectedTechs[jobId];

    if (!techId) return;

    const technicianId = parseInt(techId, 10);

    if (Number.isNaN(technicianId)) {
      setError("Please select a valid technician.");
      return;
    }

    const tech = allTechsList.find(
      (t) => t.technician_id === technicianId
    );

    if (!tech) {
      setError("Selected technician is no longer available.");
      return;
    }

    openDispatchConfirmation({
      action: "Assign Job",
      jobIds: [jobId],
      technician: tech.technician_name,
      technicianId,
      details:
        `Job #${jobId} will be assigned to ${tech.technician_name}. ` +
        "The existing backend assignment API will perform the final validation.",
      confirmLabel: "Confirm Assignment",
      execute: async () => {
        await handleAssignJob(jobId);
      },
    });
  };

  const requestBulkAssign = () => {
    if (selectedJobIds.length === 0 || !bulkTechnicianId) return;

    const technicianId = parseInt(bulkTechnicianId, 10);

    if (Number.isNaN(technicianId)) {
      setError("Please select a valid technician.");
      return;
    }

    const technician = allTechsList.find(
      (t) => t.technician_id === technicianId
    );

    if (!technician) {
      setError("Selected technician is no longer available.");
      return;
    }

    openDispatchConfirmation({
      action: "Bulk Job Assignment",
      jobIds: [...selectedJobIds],
      technician: technician.technician_name,
      technicianId,
      details:
        `${selectedJobIds.length} selected job(s) will be assigned to ` +
        `${technician.technician_name}. The existing backend assignment API ` +
        "will perform the final validation.",
      confirmLabel: "Confirm Assignment",
      execute: async () => {
        await handleBulkAssign();
      },
    });
  };


  const handleBulkAssign = async () => {
    if (selectedJobIds.length === 0 || !bulkTechnicianId) return;

    const technicianId = parseInt(bulkTechnicianId, 10);

    if (Number.isNaN(technicianId)) {
      setError("Please select a valid technician.");
      return;
    }

    try {
      setBulkAssigning(true);
      setError("");

      await assignJobsBulk(selectedJobIds, technicianId);

      const tech = allTechsList.find(
        (t) => t.technician_id === technicianId
      );

      showAssignSuccess(
        `${tech?.technician_name || "Technician"} has been assigned to ${selectedJobIds.length} selected job(s).`
      );

      setSelectedJobIds([]);
      setBulkTechnicianId("");

      fetchAllData();
    } catch (err: any) {
      const message = formatDispatchFailure(
        err,
        "Bulk job assignment",
        "Failed to assign selected jobs."
      );

      setError(message);
      throw err;
    } finally {
      setBulkAssigning(false);
    }
  };


  const executeBulkCancel = async (reason: string) => {
    try {
      setBulkCancelling(true);
      setError("");

      await cancelJobsBulk(selectedJobIds, reason.trim());

      showSuccess(
        `${selectedJobIds.length} selected job(s) cancelled successfully.`
      );

      setSelectedJobIds([]);
      fetchAllData();
    } catch (err: any) {
      const message = formatDispatchFailure(
        err,
        "Bulk job cancellation",
        "Failed to cancel selected jobs."
      );

      setError(message);
      throw err;
    } finally {
      setBulkCancelling(false);
    }
  };

  const handleBulkCancel = () => {
    if (selectedJobIds.length === 0) return;

    openDispatchConfirmation({
      action: "Bulk Job Cancellation",
      jobIds: [...selectedJobIds],
      details:
        `${selectedJobIds.length} selected job(s) will be cancelled. ` +
        "The existing backend cancellation API will perform the final validation.",
      reasonRequired: true,
      reasonPlaceholder: "Enter cancellation reason",
      confirmLabel: "Confirm Cancellation",
      execute: async (reason) => {
        if (!reason?.trim()) {
          setError("Cancellation reason is required.");
          return;
        }

        await executeBulkCancel(reason);
      },
    });
  };

  const requestForceAssignEscalation = (
    jobId: number,
    techId: string | number
  ) => {
    if (manualOverrideJobId !== null) {
      return;
    }
    const technician = allTechsList.find(
      (t) => String(t.technician_id) === String(techId)
    );

    openDispatchConfirmation({
      action: "Manual Override",
      jobIds: [jobId],
      technician:
        technician?.technician_name ||
        `Technician #${techId}`,
      details:
        `Job #${jobId} will be force-assigned to ${
          technician?.technician_name || `Technician #${techId}`
        }. The existing backend override API will validate and persist this action.`,
      reasonRequired: true,
      reasonPlaceholder: "Enter force-assignment justification",
      confirmLabel: "Confirm Manual Override",
      execute: async (reason) => {
        if (!reason?.trim()) {
          setError("Force-assignment justification is required.");
          return;
        }

        try {
          setManualOverrideJobId(jobId);

          await forceAssignEscalation(
            jobId,
            String(technician?.technician_id || techId),
            reason.trim()
          );

          showSuccess(
            `Job #${jobId} force-assigned to ${
              technician?.technician_name || techId
            }.`
          );

          setSelectedTechs((prev) => {
            const next = { ...prev };
            delete next[jobId];
            return next;
          });

          fetchAllData();
        } catch (err: any) {
          const message = formatDispatchFailure(
            err,
            "Manual Override",
            "Manual override failed."
          );

          setError(message);
          throw err;
        } finally {
          setManualOverrideJobId(null);
        }
      },
    });
  };


  const handleJobSelection = (jobId: number, checked: boolean) => {
    setSelectedJobIds((prev) => {
      if (checked) {
        return prev.includes(jobId) ? prev : [...prev, jobId];
      }

      return prev.filter((id) => id !== jobId);
    });
  };

  const handleSelectAllJobs = (checked: boolean) => {
    if (checked) {
      setSelectedJobIds(pendingJobs.map((job) => job.id));
    } else {
      setSelectedJobIds([]);
    }
  };


  const showSuccess = (msg: string) => {
    setSuccessMsg(msg);
    setTimeout(() => setSuccessMsg(""), 3500);
  };

  const showAssignSuccess = (msg: string) => {
    setAssignSuccessMsg(msg);
    setTimeout(() => setAssignSuccessMsg(""), 4500);
  };

  const isGlobalLoading = jobsLoading || assignmentsLoading;

  const escalatedJobs = useMemo(() => {
    return pendingJobs.filter(job => {
      const status = String(job.status || job.job_status || "").toUpperCase();
      return status === "ESCALATED" || status === "ESCALATED_TO_CTO";
    });
  }, [pendingJobs]);

  const normalPendingJobs = useMemo(() => {
    return pendingJobs.filter(job => {
      const status = String(job.status || job.job_status || "").toUpperCase();
      return status !== "ESCALATED" && status !== "ESCALATED_TO_CTO";
    });
  }, [pendingJobs]);

  const mapEligibleJobs = useMemo(() => {
    return normalPendingJobs
      .map((job) => {
        const coordinates = parseCoordinates(job.location);

        if (!coordinates) {
          return null;
        }

        return {
          job,
          coordinates,
        };
      })
      .filter(
        (
          item
        ): item is {
          job: PendingJob;
          coordinates: { lat: number; lng: number };
        } => item !== null
      );
  }, [normalPendingJobs]);

  const filteredPendingJobs = normalPendingJobs;

  const metricFilteredPendingJobs = useMemo(() => {
    if (activeMetricFilter === "dispatched") {
      return [];
    }
    return filteredPendingJobs;
  }, [filteredPendingJobs, activeMetricFilter]);

  const filteredPlannedAssignments = plannedAssignments;

  // Page reset is handled by the debSearchQuery and activeMetricFilter effect.

  // Page clamping is handled by safePendingPage/safePlannedPage below via Math.min,
  // so no useEffect is needed here (avoids potential re-render loops).

  const pendingTotalPages = Math.max(1, Math.ceil(totalPendingCount / PAGE_SIZE));
  const safePendingPage = Math.min(pendingPage, pendingTotalPages);
  const paginatedPendingJobs = metricFilteredPendingJobs;

  const plannedTotalPages = Math.max(1, Math.ceil(totalPlannedCount / PAGE_SIZE));
  const safePlannedPage = Math.min(plannedPage, plannedTotalPages);
  const paginatedPlannedAssignments = filteredPlannedAssignments;

  const handleExport = () => {
    if (exporting) return;

    const rows =
      activeTab === "pending"
        ? paginatedPendingJobs
        : activeTab === "planned"
          ? paginatedPlannedAssignments
          : [];

    if (rows.length === 0) {
      setError("There is no visible data available to export.");
      return;
    }

    setExporting(true);
    setError("");

    try {
      let headers: string[];
      let data: unknown[][];

      if (activeTab === "pending") {
        headers = [
          "Job ID",
          "Customer",
          "Location",
          "Priority",
          "Service Type",
          "Required Skill",
          "Issue Description",
          "Status",
          "SLA Deadline",
          "Attempt Count",
        ];

        data = paginatedPendingJobs.map((job) => [
          job.id,
          job.customer_name,
          job.location,
          job.priority,
          job.service_type,
          job.required_skill,
          job.issue_description,
          job.job_status || job.status,
          job.sla_deadline,
          job.attempt_count,
        ]);
      } else {
        headers = [
          "Job ID",
          "Technician",
          "Skill",
          "Customer",
          "Location",
          "Priority",
          "Status",
          "Current Jobs",
          "Max Jobs",
        ];

        data = paginatedPlannedAssignments.map((assignment) => [
          assignment.job_id,
          assignment.technician,
          assignment.skill,
          assignment.customer,
          assignment.location,
          assignment.priority,
          assignment.status,
          assignment.current_jobs,
          assignment.max_jobs,
        ]);
      }

      const csv = [
        headers.map(escapeCsvValue).join(","),
        ...data.map((row) => row.map(escapeCsvValue).join(",")),
      ].join("\r\n");

      const blob = new Blob(["\uFEFF" + csv], {
        type: "text/csv;charset=utf-8;",
      });

      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");

      link.href = url;
      link.download =
        activeTab === "pending"
          ? "dispatcher-unassigned-jobs.csv"
          : "dispatcher-planned-assignments.csv";

      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch {
      setError("Failed to export the visible dispatcher data. Please try again.");
    } finally {
      setExporting(false);
    }
  };

  const getPageNums = (currentPage: number, totalPages: number) => {
    const nums: number[] = [];
    const delta = 2;
    for (let i = Math.max(1, currentPage - delta); i <= Math.min(totalPages, currentPage + delta); i++) {
      nums.push(i);
    }
    return nums;
  };

  return (
    <div style={styles.planningDashboard}>
      <style>{localCss}</style>
      <div style={{ marginBottom: "10px" }}>
        <MetricsCards onFilterChange={handleMetricFilterChange} />
      </div>

      <AlertBanner
        onViewHistory={(jobId: number, jobTitle: string) => {
          setShowHistoryJobId(jobId);
          setShowHistoryJobTitle(jobTitle);
        }}
        onManualAssignClick={(jobId: number, jobTitle: string) => {
          openDispatchConfirmation({
            action: "Manual Override",
            jobIds: [jobId],
            details:
              `${jobTitle} will enter the authorized manual override workflow. The backend will remain responsible for validation and persistence.`,
            confirmLabel: "Continue to Manual Override",
            execute: async () => {
              setForceAssignJob({
                id: jobId,
                title: jobTitle,
              });
            },
          });
        }}
        currentUserRole="dispatcher"
      />

      {/* ── Candidate Selection Pop-up Modal ── */}
      {selectedJobForRanking && (
        <div style={styles.popupOverlay} onClick={handleTopThreeClose}>
          <div style={styles.candidateModal} onClick={(e) => e.stopPropagation()}>
            <div style={styles.candidateModalHeader}>
              <div style={{ maxWidth: "1200px", margin: "0 auto", width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <h3 style={{ fontSize: "18px", fontWeight: 800, color: "#1E293B", margin: 0 }}>
                        Candidate Selection
                      </h3>
                      <span style={{
                        fontSize: "11px",
                        fontWeight: 700,
                        color: "#64748B",
                        background: "#F1F5F9",
                        padding: "2px 8px",
                        borderRadius: "6px"
                      }}>
                        Job #{selectedJobForRanking.id}
                      </span>
                    </div>
                    <p style={{ fontSize: "13px", color: "#64748B", margin: "4px 0 0 0", fontWeight: 500 }}>
                      Assigning technician for <strong style={{ color: "#1E293B" }}>{selectedJobForRanking.customer_name}</strong> · {selectedJobForRanking.location}
                    </p>
                  </div>
                </div>
                <button
                  onClick={handleTopThreeClose}
                  style={{
                    background: "none",
                    border: "none",
                    fontSize: "24px",
                    cursor: "pointer",
                    color: "#94A3B8",
                    padding: "4px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center"
                  }}
                >
                  ×
                </button>
              </div>
            </div>
            <div style={{ padding: "20px 24px", overflowY: "auto", flex: 1 }}>
              <div style={{ maxWidth: "1200px", margin: "0 auto", width: "100%" }}>
                {candidatesLoading ? (
                  <LoadingSpinner message="Evaluating technicians against strict routing constraints..." />
                ) : (
                  <RankedTechTable
                    job={{
                      id: selectedJobForRanking.id,
                      customer_name: selectedJobForRanking.customer_name,
                      priority: selectedJobForRanking.priority,
                      location: selectedJobForRanking.location,
                      issue_description: selectedJobForRanking.issue_description,
                      service_type: selectedJobForRanking.service_type,
                      required_skill: selectedJobForRanking.required_skill,
                    }}
                    candidates={rankedCandidates}
                    selectedTechId={selectedTechs[selectedJobForRanking.id] ? parseInt(selectedTechs[selectedJobForRanking.id], 10) : undefined}
                    onSelect={async (techId) => {
                      const jobToAssign = selectedJobForRanking;
                      const tech = allTechsList.find(
                        (t) => t.technician_id === techId
                      );
                      if (
                        tech &&
                        normalizeStatus(tech.technician_status) !== "available" &&
                        normalizeStatus(tech.technician_status) !== "assigned"
                      ) {
                        setError(
                          `Cannot assign: ${tech.technician_name} is currently ${tech.technician_status}. Please select an Available or Assigned technician.`
                        );
                        return;
                      }
                      handleTechSelect(jobToAssign.id, String(techId));

                      const technician = allTechsList.find(
                        (t) => t.technician_id === techId
                      );

                      handleTopThreeClose();

                      openDispatchConfirmation({
                        action: "Assign Job",
                        jobIds: [jobToAssign.id],
                        technician:
                          technician?.technician_name ||
                          `Technician #${techId}`,
                        details:
                          "The selected technician will be assigned to this job through the existing backend assignment workflow.",
                        confirmLabel: "Confirm Assignment",
                        execute: async () => {
                          await handleAssignJob(
                            jobToAssign.id,
                            String(techId)
                          );
                        },
                      });
                    }}
                    onClose={handleTopThreeClose}
                    hideHeader={true}
                  />
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Global messages */}
      {error && (
        <div className="alert-style-base" style={styles.alertError}>
          <span>{error}</span>
          <button
            onClick={() => setError("")}
            className="alert-close-btn-style"
            aria-label="Dismiss error"
          >
            &times;
          </button>
        </div>
      )}
      {successMsg && (
        <div className="alert-style-base" style={styles.alertSuccess}>
          <span>{successMsg}</span>
          <button
            onClick={() => setSuccessMsg("")}
            className="alert-close-btn-style"
            aria-label="Dismiss success message"
          >
            &times;
          </button>
        </div>
      )}
      {assignSuccessMsg && (
        <div className="alert-style-base" style={{ ...styles.alertSuccess, right: "auto", left: "24px" }}>
          <span>{assignSuccessMsg}</span>
          <button
            onClick={() => setAssignSuccessMsg("")}
            className="alert-close-btn-style"
            aria-label="Dismiss success message"
          >
            &times;
          </button>
        </div>
      )}

      {/* ── Tab Navigation ── */}
      <div className="planning-tabs-responsive" style={styles.planningTabs}>
        <div className="planning-tab-btn-group" style={{ display: "flex", overflowX: "auto", flexWrap: "nowrap", flex: 1 }}>
          <button
            className={`planning-tab-style ${activeTab === 'pending' ? 'active-tab-style' : ''}`}
            style={{
              ...styles.planningTab,
              ...(activeTab === 'pending' ? styles.planningTabActive : {}),
              paddingLeft: "10px",
              paddingRight: "16px",
            }}
            onClick={() => setActiveTab('pending')}
          >
            <span
              className="planning-tab-dot-style"
              style={{
                ...styles.planningTabDot,
                backgroundColor: "#EF4444",
                boxShadow: "0 0 0 2px rgba(239,68,68,0.15)",
              }}
            />
            <span>Unassigned Jobs</span>
            <span style={{
              ...styles.planningTabCount,
              ...(activeTab === 'pending' ? styles.planningTabCountActive : {})
            }}>{totalPendingCount}</span>
          </button>
          <div className="planning-tab-divider" />
          <button
            className={`planning-tab-style ${activeTab === 'planned' ? 'active-tab-style' : ''}`}
            style={{
              ...styles.planningTab,
              ...(activeTab === 'planned' ? styles.planningTabActive : {}),
              paddingLeft: "16px",
              paddingRight: "16px",
            }}
            onClick={() => setActiveTab('planned')}
          >
            <span
              className="planning-tab-dot-style"
              style={{
                ...styles.planningTabDot,
                backgroundColor: "#10B981",
                boxShadow: "0 0 0 2px rgba(16,185,129,0.15)",
              }}
            />
            <span>Planned Assignments</span>
            <span style={{
              ...styles.planningTabCount,
              ...(activeTab === 'planned' ? styles.planningTabCountActive : {})
            }}>{totalPlannedCount}</span>
          </button>
          <div className="planning-tab-divider" />
          <button
            className={`planning-tab-style ${activeTab === 'dispatch' ? 'active-tab-style' : ''}`}
            style={{
              ...styles.planningTab,
              ...(activeTab === 'dispatch' ? styles.planningTabActive : {}),
              paddingLeft: "16px",
              paddingRight: "16px",
            }}
            onClick={() => setActiveTab('dispatch')}
          >
            <span
              className="planning-tab-dot-style"
              style={{
                ...styles.planningTabDot,
                backgroundColor: "#3B82F6",
                boxShadow: "0 0 0 2px rgba(59,130,246,0.15)",
              }}
            />
            <span>Dispatch Queue</span>
            <span style={{
              ...styles.planningTabCount,
              ...(activeTab === 'dispatch' ? styles.planningTabCountActive : {})
            }}>{dispatchQueueCount}</span>
          </button>
          <div className="planning-tab-divider" />
          <button
            className={`planning-tab-style ${activeTab === 'escalated' ? 'active-tab-style' : ''}`}
            style={{
              ...styles.planningTab,
              ...(activeTab === 'escalated' ? styles.planningTabActive : {}),
              paddingLeft: "16px",
              paddingRight: "16px",
            }}
            onClick={() => setActiveTab('escalated')}
          >
            <span
              className="planning-tab-dot-style"
              style={{
                ...styles.planningTabDot,
                backgroundColor: "#F59E0B",
                boxShadow: "0 0 0 2px rgba(245,158,11,0.15)",
              }}
            />
            <span>SLA Escalations</span>
            <span style={{
              ...styles.planningTabCount,
              ...(activeTab === 'escalated' ? styles.planningTabCountActive : {})
            }}>{escalatedJobs.length}</span>
          </button>
          <div className="planning-tab-divider" />
          <button
            className={`planning-tab-style ${activeTab === 'declined' ? 'active-tab-style' : ''}`}
            style={{
              ...styles.planningTab,
              ...(activeTab === 'declined' ? styles.planningTabActive : {}),
              paddingLeft: "16px",
              paddingRight: "16px",
            }}
            onClick={() => {
              setActiveTab('declined');
              fetchDeclinedJobsList();
            }}
          >
            <span
              className="planning-tab-dot-style"
              style={{
                ...styles.planningTabDot,
                backgroundColor: "#DC2626",
                boxShadow: "0 0 0 2px rgba(220,38,38,0.15)",
              }}
            />
            <span>Technician Declined Jobs</span>
            <span style={{
              ...styles.planningTabCount,
              ...(activeTab === 'declined' ? styles.planningTabCountActive : {})
            }}>{declinedJobsList.length}</span>
          </button>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            marginLeft: "10px",
            flexShrink: 0,
          }}
        >
          <div
            role="status"
            aria-live="polite"
            aria-label={`Live dashboard updates: ${
              dispatchSocketStatus === "connected"
                ? "Connected"
                : dispatchSocketStatus === "connecting"
                  ? "Connecting"
                  : dispatchSocketStatus === "reconnecting"
                    ? "Reconnecting"
                    : "Unavailable"
            }`}
            title={
              dispatchSocketError ||
              "Dashboard data is refreshed from the authoritative backend after realtime events."
            }
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              padding: "7px 10px",
              borderRadius: "8px",
              border: "1px solid #E3ECE7",
              background: "#FFFFFF",
              color: "#475569",
              fontSize: "11px",
              fontWeight: 600,
              whiteSpace: "nowrap",
            }}
          >
            <span
              aria-hidden="true"
              style={{
                width: "7px",
                height: "7px",
                borderRadius: "50%",
                background:
                  dispatchSocketStatus === "connected"
                    ? "#10B981"
                    : dispatchSocketStatus === "connecting" ||
                        dispatchSocketStatus === "reconnecting"
                      ? "#F59E0B"
                      : "#EF4444",
              }}
            />

            {dispatchSocketStatus === "connected"
              ? "Live"
              : dispatchSocketStatus === "connecting"
                ? "Connecting..."
                : dispatchSocketStatus === "reconnecting"
                  ? "Reconnecting..."
                  : "Live unavailable"}
          </div>

          <button
            type="button"
            onClick={handleExport}
            disabled={
              exporting ||
              !["pending", "planned"].includes(activeTab) ||
              (activeTab === "pending"
                ? paginatedPendingJobs.length === 0
                : paginatedPlannedAssignments.length === 0)
            }
            style={{
              ...styles.refreshIconBtn,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "6px",
              opacity:
                exporting ||
                !["pending", "planned"].includes(activeTab) ||
                (activeTab === "pending"
                  ? paginatedPendingJobs.length === 0
                  : paginatedPlannedAssignments.length === 0)
                  ? 0.6
                  : 1,
              cursor:
                exporting ||
                !["pending", "planned"].includes(activeTab) ||
                (activeTab === "pending"
                  ? paginatedPendingJobs.length === 0
                  : paginatedPlannedAssignments.length === 0)
                  ? "not-allowed"
                  : "pointer",
              whiteSpace: "nowrap",
            }}
            aria-label="Export visible dispatcher data"
            title={
              !["pending", "planned"].includes(activeTab)
                ? "Export is available for job and assignment tables"
                : "Export currently visible filtered data"
            }
          >
            <span aria-hidden="true">↓</span>
            {exporting ? "Exporting..." : "Export"}
          </button>
          <button
            type="button"
            onClick={() => setShowJobMap(true)}
            disabled={!isRouteMapLoaded && !routeMapLoadError}
            style={{
              ...styles.refreshIconBtn,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "6px",
              opacity:
                isRouteMapLoaded || routeMapLoadError ? 1 : 0.6,
              cursor:
                isRouteMapLoaded || routeMapLoadError
                  ? "pointer"
                  : "not-allowed",
              whiteSpace: "nowrap",
            }}
            aria-label="Open job map"
            title={
              isRouteMapLoaded
                ? "View eligible jobs on map"
                : routeMapLoadError
                ? "Google Maps configuration error"
                : "Loading Google Maps"
            }
          >
            <MapPin size={15} />
            Map View
          </button>
        </div>
      </div>

      {/* ── Tab Content ── */}

      {/* UNASSIGNED JOBS TAB */}
      {activeTab === 'pending' && (
        <section style={styles.dashboardSection}>


          <div style={styles.sectionContent}>
            {activeMetricFilter !== "all" && (
              <div className="metric-filter-banner-responsive" style={styles.metricFilterBanner}>
                <div style={styles.metricFilterLeft}>
                  <div style={styles.metricFilterIcon} aria-hidden="true">
                    🔎
                  </div>
                  <div style={styles.metricFilterTextWrap}>
                    <p style={styles.metricFilterLabel}>Active metric filter</p>
                    <h4 style={styles.metricFilterValue}>{activeMetricFilter === "pending" ? "unassigned" : activeMetricFilter}</h4>
                  </div>
                </div>
                <button
                  type="button"
                  className="metric-clear-btn-style"
                  style={styles.metricClearBtn}
                  onClick={() => {
                    setActiveMetricFilter("all");
                    setPendingPage(1);
                  }}
                >
                  ✕ Clear Filter
                </button>
              </div>
            )}

            {jobsLoading ? (
              <LoadingSpinner message="Loading pending jobs..." />
            ) : (
              <>
                <div style={styles.tableContainer}>
                  {metricFilteredPendingJobs.length === 0 ? (
                    <EmptyState
                      title={getMetricEmptyTitle()}
                      description={getMetricEmptyDescription()}
                      action={
                        searchQuery.trim() || activeMetricFilter !== "all" ? (
                          <button
                            className="planning-refresh-btn-style"
                            style={styles.refreshIconBtn}
                            onClick={() => {
                              setSearchQuery("");
                              setActiveMetricFilter("all");
                            }}
                          >
                            Clear Filters
                          </button>
                        ) : undefined
                      }
                    />
                  ) : (
                    <>
                      {selectedJobIds.length > 0 && (
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "10px",
                            padding: "10px 12px",
                            background: "#F6FAF8",
                            borderBottom: "1px solid #E3ECE7",
                            flexWrap: "wrap",
                          }}
                        >
                          <span
                            style={{
                              fontSize: "12px",
                              fontWeight: 700,
                              color: "#2F4F3E",
                            }}
                          >
                            {selectedJobIds.length} job(s) selected
                          </span>

                          <select
                            value={bulkTechnicianId}
                            onChange={(e) => setBulkTechnicianId(e.target.value)}
                            disabled={bulkAssigning}
                            style={{
                              ...styles.techSelect,
                              maxWidth: "220px",
                            }}
                            aria-label="Select technician for bulk assignment"
                          >
                            <option value="">Select technician</option>

                            {allTechsList
                              .filter((tech) => {
                                const status = normalizeStatus(
                                  tech.technician_status || ""
                                );

                                return status === "available";
                              })
                              .map((tech) => (
                              <option
                                key={tech.technician_id}
                                value={tech.technician_id}
                              >
                                {tech.technician_name} — {tech.technician_status}
                              </option>
                            ))}
                          </select>

                          <button
                            type="button"
                            onClick={requestBulkAssign}
                            disabled={bulkAssigning || bulkCancelling || !bulkTechnicianId}
                            style={{
                              ...styles.assignBtn,
                              opacity:
                                bulkAssigning || bulkCancelling || !bulkTechnicianId
                                  ? 0.6
                                  : 1,
                              cursor:
                                bulkAssigning || bulkCancelling || !bulkTechnicianId
                                  ? "not-allowed"
                                  : "pointer",
                            }}
                          >
                            {bulkAssigning ? "Assigning..." : "Assign Selected"}
                          </button>
                          <button
                            type="button"
                            onClick={handleBulkCancel}
                            disabled={bulkAssigning || bulkCancelling}
                            style={{
                              ...styles.assignBtn,
                              background: "#EF4444",
                              color: "#FFFFFF",
                              opacity: bulkAssigning || bulkCancelling ? 0.6 : 1,
                              cursor:
                                bulkAssigning || bulkCancelling
                                  ? "not-allowed"
                                  : "pointer",
                            }}
                          >
                            {bulkCancelling ? "Cancelling..." : "Cancel Selected"}
                          </button>
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedJobIds([]);
                              setBulkTechnicianId("");
                            }}
                            disabled={bulkAssigning}
                            style={{
                              height: "34px",
                              padding: "0 12px",
                              background: "#FFFFFF",
                              color: "#6B7280",
                              border: "1px solid #E3ECE7",
                              borderRadius: "6px",
                              fontSize: "12px",
                              fontWeight: 600,
                              cursor: bulkAssigning ? "not-allowed" : "pointer",
                            }}
                          >
                            Clear
                          </button>
                        </div>
                      )}

                      <table style={styles.dashboardTable}>
                      <thead>
                      <tr>
                        <th style={{ ...styles.dashboardTableTh, width: "45px", textAlign: "center" }}>
                          <input
                            type="checkbox"
                            checked={
                              paginatedPendingJobs.length > 0 &&
                              paginatedPendingJobs.every((job) =>
                                selectedJobIds.includes(job.id)
                              )
                            }
                            onChange={(e) => {
                              if (e.target.checked) {
                                setSelectedJobIds((prev) => [
                                  ...prev,
                                  ...paginatedPendingJobs
                                    .map((job) => job.id)
                                    .filter((id) => !prev.includes(id)),
                                ]);
                              } else {
                                setSelectedJobIds((prev) =>
                                  prev.filter(
                                    (id) =>
                                      !paginatedPendingJobs.some(
                                        (job) => job.id === id
                                      )
                                  )
                                );
                              }
                            }}
                            aria-label="Select all visible jobs"
                          />
                        </th>

                        <th style={styles.dashboardTableTh}>ID</th>
                        <th style={styles.dashboardTableTh}>Customer</th>
                        <th style={styles.dashboardTableTh}>Location</th>
                        <th style={styles.dashboardTableTh}>Priority</th>
                        <th style={{ ...styles.dashboardTableTh, ...styles.assignmentActionCell }}>
                          Assign Technician
                        </th>
                      </tr>
                    </thead>
                      <tbody key={safePendingPage} className="planning-table-body">
                        {paginatedPendingJobs.map((job) => (
                          <tr
                            key={job.id}
                            onClick={() => handleJobRowClick(job)}
                            className={`dashboard-table-row ${selectedJobForRanking?.id === job.id ? 'selected-row-style' : ''}`}
                            style={{ cursor: 'pointer' }}
                            title="Click to see top recommended technicians"
                          >
                            {/* Bulk selection checkbox */}
                            <td
                              style={{ ...styles.dashboardTableTd, textAlign: 'center' }}
                              onClick={(e) => e.stopPropagation()}
                            >
                              <input
                                type="checkbox"
                                checked={selectedJobIds.includes(job.id)}
                                onChange={(e) =>
                                  handleJobSelection(job.id, e.target.checked)
                                }
                                aria-label={`Select job ${job.id}`}
                              />
                            </td>

                            <td style={{ ...styles.dashboardTableTd, ...styles.jobIdCell }}>#{job.id}</td>
                            <td style={{ ...styles.dashboardTableTd, ...styles.customerCell }}>
                              <div>{job.customer_name}</div>
                              {job.issue_description && (
                                <div style={styles.issueSub}>{job.issue_description}</div>
                              )}
                            </td>
                            <td style={styles.dashboardTableTd}>{job.location}</td>
                            <td style={styles.dashboardTableTd}>
                              <span style={getPriorityStyle(job.priority || "")}>
                                {job.priority || "UNKNOWN"}
                              </span>
                            </td>
                            <td
                              style={{ ...styles.dashboardTableTd, ...styles.assignmentActionCell }}
                              onClick={(e) => e.stopPropagation()}
                            >
                              <div style={styles.assignmentUi}>
                                <button
                                  className="tech-select-style"
                                  style={{
                                    ...styles.techSelect,
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'space-between',
                                    cursor: 'pointer',
                                    backgroundColor: selectedTechs[job.id] ? '#f0fdf4' : '#fff',
                                    borderColor: selectedTechs[job.id] ? '#86efac' : '#cbd5e1',
                                    color: selectedTechs[job.id] ? '#166534' : '#64748b',
                                    fontWeight: selectedTechs[job.id] ? 600 : 400,
                                    textAlign: 'left' as const,
                                    gap: '6px',
                                  }}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleJobRowClick(job);
                                  }}
                                  disabled={assigningJobId === job.id}
                                  title="Click to open Candidate Selection"
                                >
                                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
                                    {selectedTechs[job.id]
                                      ? (() => {
                                        const t = allTechsList.find(t => t.technician_id === parseInt(selectedTechs[job.id], 10));
                                        return t ? t.technician_name : 'Selected';
                                      })()
                                      : 'Select Technician'
                                    }
                                  </span>
                                  <ChevronDown size={14} style={{ flexShrink: 0, opacity: 0.5 }} />
                                </button>

                                <button
                                  className={`assign-btn-style ${selectedTechs[job.id] ? 'active' : 'disabled'}`}
                                  style={{
                                    ...styles.assignBtn,
                                    backgroundColor: selectedTechs[job.id] ? '#10B981' : '#f1f5f9',
                                    color: selectedTechs[job.id] ? '#ffffff' : '#94a3b8',
                                    border: selectedTechs[job.id] ? 'none' : '1px solid #cbd5e1',
                                    opacity: selectedTechs[job.id] ? 1 : 0.7,
                                    cursor: selectedTechs[job.id] ? 'pointer' : 'not-allowed',
                                    boxShadow: selectedTechs[job.id] ? '0 2px 6px rgba(16, 185, 129, 0.25)' : 'none',
                                    fontWeight: 600,
                                  }}
                                  onMouseEnter={(e) => {
                                    if (selectedTechs[job.id] && assigningJobId !== job.id) {
                                      e.currentTarget.style.backgroundColor = '#059669';
                                    }
                                  }}
                                  onMouseLeave={(e) => {
                                    if (selectedTechs[job.id] && assigningJobId !== job.id) {
                                      e.currentTarget.style.backgroundColor = '#10B981';
                                    }
                                  }}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    if (selectedTechs[job.id]) {
                                      requestAssignJob(job.id);
                                    }
                                  }}
                                  disabled={!selectedTechs[job.id] || assigningJobId === job.id}
                                >
                                  {assigningJobId === job.id
                                    ? "Assigning…"
                                    : "Assign"}
                                </button>
                                <button
                                  className="history-action-btn-style"
                                  style={{
                                    height: '34px',
                                    width: '34px',
                                    minWidth: '34px',
                                    background: 'transparent',
                                    border: '1.5px solid #cbd5e1',
                                    color: '#64748b',
                                    borderRadius: '6px',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    cursor: 'pointer',
                                    transition: 'all 0.2s ease',
                                    boxSizing: 'border-box',
                                  }}
                                  onMouseEnter={(e) => {
                                    e.currentTarget.style.backgroundColor = '#f8fafc';
                                    e.currentTarget.style.borderColor = '#94a3b8';
                                    e.currentTarget.style.color = '#334155';
                                  }}
                                  onMouseLeave={(e) => {
                                    e.currentTarget.style.backgroundColor = 'transparent';
                                    e.currentTarget.style.borderColor = '#cbd5e1';
                                    e.currentTarget.style.color = '#64748b';
                                  }}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setShowHistoryJobId(job.id);
                                    setShowHistoryJobTitle(`${job.service_type || "Job"} - ${job.location || ""}`);
                                  }}
                                  title="View Re-Dispatch History"
                                >
                                  <History size={15} />
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    </>
                  )}
                </div>
                <div style={styles.planningPagination}>
                  <span style={styles.planningPageInfo}>
                    Page <strong style={{ color: "#2F4F3E" }}>{safePendingPage}</strong> of <strong style={{ color: "#2F4F3E" }}>{pendingTotalPages}</strong> · {totalPendingCount} results
                  </span>
                  <div style={styles.planningPageControls}>
                    <button className="planning-page-btn-style" style={styles.planningPageBtn} onClick={() => setPendingPage(1)} disabled={safePendingPage === 1}>«</button>
                    <button className="planning-page-btn-style" style={styles.planningPageBtn} onClick={() => setPendingPage(p => Math.max(1, p - 1))} disabled={safePendingPage === 1}>‹ Prev</button>
                    <div style={styles.planningPageNumbers}>
                      {getPageNums(safePendingPage, pendingTotalPages).map(n => (
                        <button
                          key={n}
                          className={`planning-page-num-style ${n === safePendingPage ? "active" : ""}`}
                          style={{
                            ...styles.planningPageNum,
                            ...(n === safePendingPage ? styles.planningPageNumActive : {})
                          }}
                          onClick={() => setPendingPage(n)}
                        >
                          {n}
                        </button>
                      ))}
                    </div>
                    <button className="planning-page-btn-style" style={styles.planningPageBtn} onClick={() => setPendingPage(p => Math.min(pendingTotalPages, p + 1))} disabled={safePendingPage === pendingTotalPages}>Next ›</button>
                    <button className="planning-page-btn-style" style={styles.planningPageBtn} onClick={() => setPendingPage(pendingTotalPages)} disabled={safePendingPage === pendingTotalPages}>»</button>
                  </div>
                </div>
              </>
            )}
          </div>
        </section>
      )}

      {/* SLA ESCALATIONS TAB */}
      {activeTab === 'escalated' && (
        <section style={{ ...styles.dashboardSection, marginBottom: "8px" }}>
          <div style={styles.sectionContent}>
            {jobsLoading ? (
              <LoadingSpinner message="Loading escalations..." />
            ) : escalatedJobs.length === 0 ? (
              <EmptyState
                title="No active SLA escalations"
                description="Hooray! No jobs are currently in SLA risk state or escalated."
              />
            ) : (
              <div style={styles.tableContainer}>
                <table style={styles.dashboardTable}>
                  <thead>
                    <tr>
                      <th style={styles.dashboardTableTh}>Job ID</th>
                      <th style={styles.dashboardTableTh}>Customer & Description</th>
                      <th style={styles.dashboardTableTh}>Location</th>
                      <th style={styles.dashboardTableTh}>Priority</th>
                      <th style={styles.dashboardTableTh}>Escalation Level</th>
                      <th style={{ ...styles.dashboardTableTh, minWidth: "480px" }}>Escalation Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {escalatedJobs.map((job) => {
                      const isCTO = String(job.status || job.job_status || "").toUpperCase() === "ESCALATED_TO_CTO";
                      return (
                        <tr key={job.id} className="dashboard-table-row">
                          <td style={{ ...styles.dashboardTableTd, ...styles.jobIdCell }}>#{job.id}</td>
                          <td style={{ ...styles.dashboardTableTd, ...styles.customerCell }}>
                            <div>{job.customer_name}</div>
                            {job.issue_description && (
                              <div style={styles.issueSub}>{job.issue_description}</div>
                            )}
                          </td>
                          <td style={styles.dashboardTableTd}>{job.location}</td>
                          <td style={styles.dashboardTableTd}>
                            <span style={getPriorityStyle(job.priority || "")}>
                              {job.priority || "UNKNOWN"}
                            </span>
                          </td>
                          <td style={styles.dashboardTableTd}>
                            <span style={{
                              fontSize: "10px",
                              fontWeight: 700,
                              padding: "3px 9px",
                              borderRadius: "20px",
                              backgroundColor: isCTO ? "#fee2e2" : "#fef3c7",
                              color: isCTO ? "#991b1b" : "#92400e",
                              border: `1px solid ${isCTO ? '#fca5a5' : '#fde047'}`
                            }}>
                              {isCTO ? "CTO ESCALATED" : "MANAGER ESCALATED"}
                            </span>
                          </td>
                          <td style={{ ...styles.dashboardTableTd, minWidth: "480px" }}>
                            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
                              <button
                                className="assign-btn-style"
                                style={{
                                  ...styles.assignBtn,
                                  backgroundColor: "#10B981"
                                }}
                                onMouseEnter={(e) => {
                                  e.currentTarget.style.backgroundColor = '#059669';
                                }}
                                onMouseLeave={(e) => {
                                  e.currentTarget.style.backgroundColor = '#10B981';
                                }}
                                onClick={async () => {
                                  const minsStr = prompt("Enter SLA extension time in minutes:", "30");
                                  if (!minsStr) return;
                                  const mins = parseInt(minsStr, 10);
                                  if (isNaN(mins) || mins <= 0) {
                                    alert("Please enter a valid positive number.");
                                    return;
                                  }
                                  try {
                                    await extendSLA(job.id, mins);
                                    showSuccess(`SLA deadline extended by ${mins} minutes.`);
                                    fetchAllData();
                                  } catch (err: any) {
                                    alert(err.response?.data?.detail || "Failed to extend SLA");
                                  }
                                }}
                              >
                                Extend SLA
                              </button>
                              <button
                                className="assign-btn-style"
                                style={{
                                  ...styles.assignBtn,
                                  backgroundColor: "#EF4444"
                                }}
                                onMouseEnter={(e) => {
                                  e.currentTarget.style.backgroundColor = '#dc2626';
                                }}
                                onMouseLeave={(e) => {
                                  e.currentTarget.style.backgroundColor = '#EF4444';
                                }}
                                onClick={() => {
                                  openDispatchConfirmation({
                                    action: "Cancel Escalated Job",
                                    jobIds: [job.id],
                                    details:
                                      `${job.customer_name || "This job"} will be cancelled through the existing backend escalation cancellation workflow. The backend will perform the final validation.`,
                                    reasonRequired: true,
                                    reasonPlaceholder: "Enter cancellation reason",
                                    confirmLabel: "Confirm Cancellation",
                                    execute: async (reason) => {
                                      if (!reason?.trim()) {
                                        throw new Error("Cancellation reason is required.");
                                      }

                                      await cancelEscalatedJob(job.id, reason.trim());

                                      showSuccess(`Job #${job.id} cancelled successfully.`);
                                      fetchAllData();
                                    },
                                  });
                                }}
                              >
                                Cancel Job
                              </button>

                              <div style={{ display: "flex", gap: "4px", alignItems: "center" }}>
                                <select
                                  className="tech-select-style"
                                  style={{
                                    ...styles.techSelect,
                                    margin: 0,
                                    padding: "0 8px",
                                    height: "34px",
                                    lineHeight: "34px",
                                    boxSizing: "border-box"
                                  }}
                                  value={selectedTechs[job.id] || ""}
                                  onChange={(e) => setSelectedTechs(prev => ({ ...prev, [job.id]: e.target.value }))}
                                >
                                  <option value="" disabled>Select Tech</option>
                                  {allTechsList.map(t => {
                                    const isUnavailable = ["busy", "offline"].includes((t.technician_status || "").toLowerCase().trim());
                                    return (
                                      <option key={t.technician_id} value={t.technician_id} disabled={isUnavailable}>
                                        {t.technician_name} {isUnavailable ? `(${t.technician_status})` : ""}
                                      </option>
                                    );
                                  })}
                                </select>
                                <button
                                  className={`assign-btn-style ${selectedTechs[job.id] ? 'active' : 'disabled'}`}
                                  style={{
                                    ...styles.assignBtn,
                                    backgroundColor: selectedTechs[job.id] ? '#F59E0B' : '#f1f5f9',
                                    color: selectedTechs[job.id] ? '#ffffff' : '#94a3b8',
                                    border: selectedTechs[job.id] ? 'none' : '1px solid #cbd5e1',
                                    opacity: selectedTechs[job.id] ? 1 : 0.7,
                                    cursor: selectedTechs[job.id] ? 'pointer' : 'not-allowed',
                                    boxShadow: selectedTechs[job.id] ? '0 2px 6px rgba(245, 158, 11, 0.25)' : 'none',
                                    fontWeight: 600,
                                  }}
                                  onMouseEnter={(e) => {
                                    if (selectedTechs[job.id]) {
                                      e.currentTarget.style.backgroundColor = '#d97706';
                                    }
                                  }}
                                  onMouseLeave={(e) => {
                                    if (selectedTechs[job.id]) {
                                      e.currentTarget.style.backgroundColor = '#F59E0B';
                                    }
                                  }}
                                  disabled={!selectedTechs[job.id]}
                                  onClick={() => {
                                    const techId = selectedTechs[job.id];

                                    if (!techId) {
                                      setError(
                                        "Please select a technician before using Force Assign."
                                      );
                                      return;
                                    }

                                    const tech = allTechsList.find(
                                      (t) =>
                                        String(t.technician_id) ===
                                        String(techId)
                                    );

                                    openDispatchConfirmation({
                                      action: "Manual Override",
                                      jobIds: [job.id],
                                      technician:
                                        tech?.technician_name ||
                                        `Technician #${techId}`,
                                      details:
                                        `${job.customer_name || "Customer job"} will be force-assigned through the manual override workflow. ` +
                                        "This is a dispatcher decision separate from AI technician recommendations. " +
                                        "The existing backend override API will perform authorization, validation, audit recording, and persistence.",
                                      reasonRequired: true,
                                      reasonPlaceholder:
                                        "Enter force-assignment justification",
                                      confirmLabel:
                                        "Confirm Manual Override",
                                      execute: async (reason) => {
                                        if (!reason?.trim()) {
                                          throw new Error(
                                            "A reason is required before confirming this action."
                                          );
                                        }

                                        try {
                                          await forceAssignEscalation(
                                            job.id,
                                            String(
                                              tech?.technician_id || techId
                                            ),
                                            reason.trim()
                                          );

                                          showSuccess(
                                            `Job #${job.id} force-assigned to ${
                                              tech?.technician_name || techId
                                            }.`
                                          );

                                          setSelectedTechs((prev) => {
                                            const next = { ...prev };
                                            delete next[job.id];
                                            return next;
                                          });

                                          fetchAllData();
                                        } catch (err: any) {
                                          throw err;
                                        }
                                      },
                                    });
                                  }}
                                >
                                  Force Assign
                                </button>
                              </div>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
      )}

      {/* DISPATCH QUEUE TAB */}
      {activeTab === 'dispatch' && (
        <DispatchQueueTable onCountChange={setDispatchQueueCount} />
      )}

      {/* PLANNED ASSIGNMENTS TAB */}
      {activeTab === 'planned' && (
        <section style={{ ...styles.dashboardSection, marginBottom: "8px" }}>
          <div style={styles.sectionContent}>
            {assignmentsLoading ? (
              <LoadingSpinner message="Loading assignments..." />
            ) : (
              <>
                <div style={styles.tableContainer}>
                  {filteredPlannedAssignments.length === 0 ? (
                    <EmptyState
                      title={searchQuery.trim() ? "No assignments match your search" : "No planned assignments"}
                      description={searchQuery.trim() ? "Try adjusting your search terms." : "No jobs have been assigned to technicians yet."}
                      action={
                        searchQuery.trim() ? (
                          <button
                            className="planning-refresh-btn-style"
                            style={styles.refreshIconBtn}
                            onClick={() => setSearchQuery("")}
                          >
                            Clear Search
                          </button>
                        ) : undefined
                      }
                    />
                  ) : (
                    <table style={styles.dashboardTable}>
                      <thead>
                        <tr>
                          <th style={styles.dashboardTableTh}>Job ID</th>
                          <th style={styles.dashboardTableTh}>Technician</th>
                          <th style={styles.dashboardTableTh}>Customer</th>
                          <th style={styles.dashboardTableTh}>Location</th>
                          <th style={styles.dashboardTableTh}>Priority</th>
                          <th style={styles.dashboardTableTh}>Status</th>
                          <th style={styles.dashboardTableTh}>Workload</th>
                          <th style={styles.dashboardTableTh}>Actions</th>
                        </tr>
                      </thead>
                      <tbody key={safePlannedPage} className="planning-table-body">
                        {paginatedPlannedAssignments.map((item) => (
                          <tr key={item.job_id} className="dashboard-table-row">
                            <td style={{ ...styles.dashboardTableTd, ...styles.jobIdCell }}>#{item.job_id}</td>
                            <td style={{ ...styles.dashboardTableTd, ...styles.techCell }}>
                              <strong>{item.technician}</strong>
                              <span style={styles.skillSub}>{item.skill}</span>
                            </td>
                            <td style={{ ...styles.dashboardTableTd, ...styles.customerCell }}>{item.customer}</td>
                            <td style={styles.dashboardTableTd}>{item.location}</td>
                            <td style={styles.dashboardTableTd}>
                              <span style={getPriorityStyle(item.priority || "")}>
                                {item.priority || "UNKNOWN"}
                              </span>
                            </td>
                            <td style={styles.dashboardTableTd}>
                              <span style={{
                                ...styles.statusBadge,
                                ...((item.status || "").toUpperCase() === "EN_ROUTE"
                                  ? { background: "#EDE9FE", color: "#5B21B6", border: "1px solid #DDD6FE" }
                                  : (item.status || "").toUpperCase() === "IN_PROGRESS"
                                  ? { background: "#D1FAE5", color: "#065F46", border: "1px solid #A7F3D0" }
                                  : { background: "#FEF3C7", color: "#92400E", border: "1px solid #FDE68A" })
                              }}>
                                {(item.status || "").toUpperCase() === "EN_ROUTE"
                                  ? "EN ROUTE"
                                  : (item.status || "").toUpperCase() === "IN_PROGRESS"
                                  ? "IN PROGRESS"
                                  : "WAITING FOR ACCEPT"}
                              </span>
                            </td>
                            <td style={styles.dashboardTableTd}>
                              <div style={styles.workloadInfo}>
                                <div style={styles.workloadBar}>
                                  <div
                                    style={{
                                      ...styles.workloadFill,
                                      width: `${Math.min(
                                        (item.current_jobs / (item.max_jobs || 5)) * 100,
                                        100
                                      )}%`,
                                    }}
                                  />
                                </div>
                                <span style={styles.workloadText}>
                                  {item.current_jobs}/{item.max_jobs}
                                </span>
                              </div>
                            </td>
                            <td style={styles.dashboardTableTd}>
                              <div style={styles.jobItemActions}>
                                <button
                                  className="icon-action-btn-style"
                                  style={{ ...styles.iconActionBtn, color: '#16a34a' }}
                                  onClick={() => setViewAssignment(item)}
                                  title="View assignment"
                                  aria-label="View assignment"
                                >
                                  <Eye size={15} />
                                </button>
                                <button
                                  className="icon-action-btn-style"
                                  style={{ ...styles.iconActionBtn, color: '#2563eb' }}
                                  onClick={() => handleViewRoute(item)}
                                  disabled={
                                    routeLoading &&
                                    routeAssignment?.job_id === item.job_id
                                  }
                                  title="View technician route"
                                  aria-label="View technician route"
                                >
                                  {routeLoading &&
                                  routeAssignment?.job_id === item.job_id ? (
                                    <Loader2 size={15} className="animate-spin" />
                                  ) : (
                                    <MapPin size={15} />
                                  )}
                                </button>
                                <ShareTrackingLinkButton jobId={item.job_id} />
                                <button
                                  className="icon-action-btn-style"
                                  style={{ ...styles.iconActionBtn, color: '#475569' }}
                                  onClick={() => {
                                    setShowOverrideHistoryForJob({ id: item.job_id, title: `${item.customer}'s Job` });
                                  }}
                                  title="View Override History"
                                  aria-label="View Override History"
                                >
                                  <History size={15} />
                                </button>
                                <button
                                  className="icon-action-btn-style"
                                  style={{ ...styles.iconActionBtn, color: '#dc2626' }}
                                  onClick={() => {
                                    if (window.confirm(`Are you sure you want to delete assignment for "${item.technician}" → "${item.customer}" (Job #${item.job_id})?`)) {
                                      showSuccess(`Assignment for Job #${item.job_id} removed (connect API for persistence).`);
                                    }
                                  }}
                                  title="Delete assignment"
                                  aria-label="Delete assignment"
                                >
                                  <Trash2 size={15} />
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
                {/* Pagination */}
                <div style={styles.planningPagination}>
                  <span style={styles.planningPageInfo}>
                    Page <strong>{safePlannedPage}</strong> of <strong>{plannedTotalPages}</strong> · {totalPlannedCount} results
                  </span>
                  <div style={styles.planningPageControls}>
                    <button className="planning-page-btn-style" style={styles.planningPageBtn} onClick={() => setPlannedPage(1)} disabled={safePlannedPage === 1}>«</button>
                    <button className="planning-page-btn-style" style={styles.planningPageBtn} onClick={() => setPlannedPage(p => Math.max(1, p - 1))} disabled={safePlannedPage === 1}>‹ Prev</button>
                    <div style={styles.planningPageNumbers}>
                      {getPageNums(safePlannedPage, plannedTotalPages).map(n => (
                        <button
                          key={n}
                          className={`planning-page-num-style ${n === safePlannedPage ? "active" : ""}`}
                          style={{
                            ...styles.planningPageNum,
                            ...(n === safePlannedPage ? styles.planningPageNumActive : {})
                          }}
                          onClick={() => setPlannedPage(n)}
                        >
                          {n}
                        </button>
                      ))}
                    </div>
                    <button className="planning-page-btn-style" style={styles.planningPageBtn} onClick={() => setPlannedPage(p => Math.min(plannedTotalPages, p + 1))} disabled={safePlannedPage === plannedTotalPages}>Next ›</button>
                    <button className="planning-page-btn-style" style={styles.planningPageBtn} onClick={() => setPlannedPage(plannedTotalPages)} disabled={safePlannedPage === plannedTotalPages}>»</button>
                  </div>
                </div>
              </>
            )}
          </div>
        </section>
      )}

      {/* TECHNICIAN DECLINED JOBS TAB */}
      {activeTab === 'declined' && (
        <section style={styles.dashboardSection}>
          <div style={styles.sectionContent}>
            {declinedLoading ? (
              <LoadingSpinner message="Loading declined jobs..." />
            ) : declinedJobsList.length === 0 ? (
              <EmptyState
                title="No Technician Declined Jobs"
                description="There are currently no jobs that have been rejected by technicians."
              />
            ) : (
              <div style={styles.tableContainer}>
                <table style={styles.dashboardTable}>
                  <thead>
                    <tr>
                      <th style={styles.dashboardTableTh}>Job ID</th>
                      <th style={styles.dashboardTableTh}>Customer</th>
                      <th style={styles.dashboardTableTh}>Service Type</th>
                      <th style={styles.dashboardTableTh}>Declining Technician</th>
                      <th style={styles.dashboardTableTh}>Rejection Reason</th>
                      <th style={styles.dashboardTableTh}>Rejected At</th>
                      <th style={styles.dashboardTableTh}>Action</th>
                    </tr>
                  </thead>
                  <tbody className="planning-table-body">
                    {declinedJobsList.map((job) => (
                      <tr key={job.id} className="dashboard-table-row">
                        <td style={{ ...styles.dashboardTableTd, ...styles.jobIdCell }}>#{job.id}</td>
                        <td style={{ ...styles.dashboardTableTd, ...styles.customerCell }}>{job.customer_name}</td>
                        <td style={styles.dashboardTableTd}>{job.service_type || "N/A"}</td>
                        <td style={styles.dashboardTableTd}>
                          <span style={{ fontWeight: 600, color: "#DC2626" }}>{job.technician_name || "Unknown Tech"}</span>
                        </td>
                        <td style={{ ...styles.dashboardTableTd, maxWidth: "250px" }}>
                          <div style={{ fontSize: "12px", color: "#4B5563", background: "#FEF2F2", padding: "6px 10px", borderRadius: "6px", border: "1px solid #FECACA" }}>
                            {job.rejection_reason || "No reason given"}
                          </div>
                        </td>
                        <td style={styles.dashboardTableTd}>
                          {job.rejected_at ? new Date(job.rejected_at).toLocaleString() : "N/A"}
                        </td>
                        <td style={styles.dashboardTableTd}>
                          <button
                            style={{
                              padding: "6px 14px",
                              background: "#7AAE8A",
                              color: "#fff",
                              border: "none",
                              borderRadius: "6px",
                              fontSize: "12px",
                              fontWeight: 700,
                              cursor: "pointer",
                            }}
                            onClick={() => {
                              setReassignModalJob(job);
                              setSelectedReassignTechId(null);
                            }}
                          >
                            Reassign Job
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Reassign Declined Job Modal */}
      {reassignModalJob && (
        <div style={styles.centeredModalOverlay} onClick={() => setReassignModalJob(null)}>
          <div style={{ ...styles.viewJobModal, maxWidth: "440px", padding: "24px" }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ fontSize: "18px", fontWeight: 700, color: "#1F2933", marginBottom: "8px" }}>
              Reassign Job #{reassignModalJob.id}
            </h3>
            <p style={{ fontSize: "13px", color: "#6B7280", marginBottom: "16px" }}>
              Select a new technician to reassign this declined job ({reassignModalJob.customer_name} - {reassignModalJob.service_type}).
            </p>
            <div style={{ marginBottom: "16px" }}>
              <label style={{ fontSize: "12px", fontWeight: 600, color: "#374151", marginBottom: "6px", display: "block" }}>
                Select Technician *
              </label>
              <select
                style={{ ...styles.techSelect, maxWidth: "100%", width: "100%", height: "38px" }}
                value={selectedReassignTechId || ""}
                onChange={(e) => setSelectedReassignTechId(Number(e.target.value))}
              >
                <option value="">-- Choose a Technician --</option>

                {eligibleReassignTechnicians.map((t) => (
                  <option
                    key={t.technician_id}
                    value={t.technician_id}
                  >
                    {t.technician_name} ({t.technician_skill}) -{" "}
                    {t.technician_status} ({t.current_jobs ?? 0}/{t.max_jobs ?? 5})
                  </option>
                ))}
              </select>

              {eligibleReassignTechnicians.length === 0 && (
                <div
                  style={{
                    marginTop: "8px",
                    padding: "10px 12px",
                    borderRadius: "6px",
                    background: "#FEF2F2",
                    border: "1px solid #FECACA",
                    color: "#991B1B",
                    fontSize: "12px",
                  }}
                >
                  No eligible technicians are currently available for reassignment.
                </div>
              )}
            </div>
            <div style={{ display: "flex", gap: "10px", justifyContent: "flex-end" }}>
              <button
                style={{ padding: "8px 16px", border: "1px solid #D1D5DB", borderRadius: "6px", background: "#fff", cursor: "pointer", fontSize: "13px" }}
                onClick={() => setReassignModalJob(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                style={{
                  padding: "8px 16px",
                  border: "none",
                  borderRadius: "6px",
                  background: "#7AAE8A",
                  color: "#fff",
                  fontWeight: 700,
                  fontSize: "13px",
                  cursor:
                    !selectedReassignTechId ||
                    !eligibleReassignTechnicians.some(
                      (tech) => tech.technician_id === selectedReassignTechId
                    ) ||
                    reassigning
                      ? "not-allowed"
                      : "pointer",
                  opacity:
                    !selectedReassignTechId ||
                    !eligibleReassignTechnicians.some(
                      (tech) => tech.technician_id === selectedReassignTechId
                    ) ||
                    reassigning
                      ? 0.6
                      : 1,
                  }}
                  disabled={
                  !selectedReassignTechId ||
                  !eligibleReassignTechnicians.some(
                    (tech) => tech.technician_id === selectedReassignTechId
                  ) ||
                  reassigning
                }
                onClick={() => {
                  if (!selectedReassignTechId) return;

                  const technician = eligibleReassignTechnicians.find(
                    (t) =>
                      t.technician_id === selectedReassignTechId
                  );

                  if (!technician) {
                    setError(
                      "The selected technician is no longer eligible for reassignment. Please refresh and try again."
                    );
                    setSelectedReassignTechId(null);
                    return;
                  }

                  openDispatchConfirmation({
                    action: "Reassign Job",
                    jobIds: [reassignModalJob.id],
                    technician:
                      technician?.technician_name ||
                      `Technician #${selectedReassignTechId}`,
                    technicianId: selectedReassignTechId,
                    details:
                      `Job #${reassignModalJob.id} (${reassignModalJob.customer_name || "Customer job"}) ` +
                      `will be reassigned to ${
                        technician?.technician_name ||
                        `Technician #${selectedReassignTechId}`
                      }. The existing backend reassignment API will perform the final validation.`,
                    confirmLabel: "Confirm Reassignment",
                    execute: async () => {
                      setReassigning(true);

                      try {
                        await reassignDeclinedJob(
                          reassignModalJob.id,
                          selectedReassignTechId
                        );

                        setSuccessMsg(
                          `Job #${reassignModalJob.id} reassigned successfully!`
                        );

                        setReassignModalJob(null);
                        fetchDeclinedJobsList();
                        fetchAllData();
                      } catch (err: any) {
                        const message = formatDispatchFailure(
                          err,
                          "Job reassignment",
                          "Reassignment failed."
                        );

                        setError(message);
                        throw err;
                      } finally {
                        setReassigning(false);
                      }
                    },
                  });
                }}
              >
                {reassigning
                  ? "Reassigning..."
                  : "Confirm Reassign"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Route Display Modal */}
      {routeAssignment && (
        <div
          style={styles.centeredModalOverlay}
          onClick={() => {
            if (!routeLoading) {
              setRouteAssignment(null);
              setRouteError("");
              setRouteEta(null);
              setRouteDirections(null);
            }
          }}
        >
          <div
            style={{
              ...styles.viewJobModal,
              width: "min(900px, 95vw)",
              maxWidth: "900px",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={styles.viewModalHeader}>
              <div>
                <h3 style={styles.viewModalHeaderH3}>
                  Technician Route
                </h3>
                <p
                  style={{
                    margin: "4px 0 0",
                    fontSize: "11px",
                    color: "#6B7280",
                  }}
                >
                  {routeAssignment.technician} → Job #
                  {routeAssignment.job_id}
                </p>
              </div>

              <button
                type="button"
                onClick={() => {
                  if (!routeLoading) {
                    setRouteAssignment(null);
                    setRouteError("");
                    setRouteEta(null);
                    setRouteDirections(null);
                  }
                }}
                disabled={routeLoading}
                style={{
                  background: "none",
                  border: "none",
                  fontSize: 22,
                  cursor: routeLoading ? "not-allowed" : "pointer",
                  color: "#6b7280",
                }}
                aria-label="Close route"
              >
                ×
              </button>
            </div>

            <div style={{ padding: "16px" }}>
              {routeLoading && (
                <div
                  style={{
                    minHeight: "360px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    background: "#F8FAFC",
                    borderRadius: "10px",
                  }}
                >
                  <LoadingSpinner message="Loading technician route..." />
                </div>
              )}

              {!routeLoading && routeError && (
                <div
                  role="alert"
                  style={{
                    minHeight: "180px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexDirection: "column",
                    gap: "8px",
                    padding: "24px",
                    background: "#FEF2F2",
                    border: "1px solid #FECACA",
                    borderRadius: "10px",
                    textAlign: "center",
                  }}
                >
                  <MapPin size={24} color="#DC2626" />

                  <strong
                    style={{
                      color: "#991B1B",
                      fontSize: "14px",
                    }}
                  >
                    Route unavailable
                  </strong>

                  <span
                    style={{
                      color: "#7F1D1D",
                      fontSize: "12px",
                    }}
                  >
                    {routeError}
                  </span>
                </div>
              )}

              {!routeLoading &&
                !routeError &&
                routeMapLoadError && (
                  <div
                    role="alert"
                    style={{
                      padding: "18px",
                      background: "#FEF2F2",
                      border: "1px solid #FECACA",
                      borderRadius: "10px",
                      color: "#991B1B",
                      fontSize: "13px",
                    }}
                  >
                    Google Maps could not be loaded. Please verify the
                    Maps API configuration.
                  </div>
                )}

              {!routeLoading &&
                !routeError &&
                !routeMapLoadError &&
                routeEta &&
                isRouteMapLoaded && (
                  <>
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns:
                          "repeat(auto-fit, minmax(140px, 1fr))",
                        gap: "10px",
                        marginBottom: "12px",
                      }}
                    >
                      <div
                        style={{
                          padding: "10px 12px",
                          background: "#F8FAFC",
                          border: "1px solid #E2E8F0",
                          borderRadius: "8px",
                        }}
                      >
                        <div
                          style={{
                            fontSize: "10px",
                            color: "#64748B",
                            fontWeight: 600,
                          }}
                        >
                          ETA
                        </div>
                        <div
                          style={{
                            marginTop: "3px",
                            fontSize: "14px",
                            fontWeight: 700,
                            color: "#1F2937",
                          }}
                        >
                          {routeEta.eta}
                        </div>
                      </div>

                      <div
                        style={{
                          padding: "10px 12px",
                          background: "#F8FAFC",
                          border: "1px solid #E2E8F0",
                          borderRadius: "8px",
                        }}
                      >
                        <div
                          style={{
                            fontSize: "10px",
                            color: "#64748B",
                            fontWeight: 600,
                          }}
                        >
                          Duration
                        </div>
                        <div
                          style={{
                            marginTop: "3px",
                            fontSize: "14px",
                            fontWeight: 700,
                            color: "#1F2937",
                          }}
                        >
                          {routeEta.duration_minutes > 0
                            ? `${routeEta.duration_minutes} min`
                            : "Unavailable"}
                        </div>
                      </div>

                      {routeEta.distance_meters > 0 && (
                        <div
                          style={{
                            padding: "10px 12px",
                            background: "#F8FAFC",
                            border: "1px solid #E2E8F0",
                            borderRadius: "8px",
                          }}
                        >
                          <div
                            style={{
                              fontSize: "10px",
                              color: "#64748B",
                              fontWeight: 600,
                            }}
                          >
                            Distance
                          </div>
                          <div
                            style={{
                              marginTop: "3px",
                              fontSize: "14px",
                              fontWeight: 700,
                              color: "#1F2937",
                            }}
                          >
                            {(
                              routeEta.distance_meters / 1000
                            ).toFixed(1)}{" "}
                            km
                          </div>
                        </div>
                      )}
                    </div>

                    <div
                      data-testid="technician-job-route-map"
                      style={{
                        width: "100%",
                        height: "460px",
                        borderRadius: "10px",
                        overflow: "hidden",
                        border: "1px solid #E2E8F0",
                      }}
                    >
                      <GoogleMap
                        mapContainerStyle={{
                          width: "100%",
                          height: "100%",
                        }}
                        center={routeEta.origin}
                        zoom={12}
                        options={{
                          fullscreenControl: false,
                          streetViewControl: false,
                          mapTypeControl: false,
                        }}
                      >
                        {routeDirections && (
                          <DirectionsRenderer
                            directions={routeDirections}
                            options={{
                              suppressMarkers: false,
                              preserveViewport: false,
                              polylineOptions: {
                                strokeColor: "#2563EB",
                                strokeOpacity: 0.85,
                                strokeWeight: 5,
                              },
                            }}
                          />
                        )}
                      </GoogleMap>
                    </div>
                  </>
                )}
            </div>
          </div>
        </div>
      )}

      {/* Job Map View Modal */}
      {showJobMap && (
        <div
          style={styles.centeredModalOverlay}
          onClick={() => setShowJobMap(false)}
        >
          <div
            style={{
              ...styles.viewJobModal,
              width: "94%",
              maxWidth: "1100px",
              maxHeight: "90vh",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={styles.viewModalHeader}>
              <div>
                <h3 style={styles.viewModalHeaderH3}>
                  Eligible Jobs Map
                </h3>
                <div
                  style={{
                    fontSize: "11px",
                    color: "#64748B",
                    marginTop: "3px",
                  }}
                >
                  {mapEligibleJobs.length} job(s) with valid coordinates
                </div>
              </div>

              <button
                type="button"
                onClick={() => setShowJobMap(false)}
                style={{
                  background: "none",
                  border: "none",
                  fontSize: 22,
                  cursor: "pointer",
                  color: "#6B7280",
                }}
                aria-label="Close job map"
              >
                ×
              </button>
            </div>

            <div
              style={{
                padding: "16px",
                display: "flex",
                flexDirection: "column",
                gap: "12px",
              }}
            >
              {routeMapLoadError ? (
                <div
                  role="alert"
                  style={{
                    padding: "14px",
                    borderRadius: "8px",
                    background: "#FEF2F2",
                    border: "1px solid #FECACA",
                    color: "#991B1B",
                    fontSize: "13px",
                  }}
                >
                  Google Maps is unavailable. Please verify the Maps
                  configuration and try again.
                </div>
              ) : !isRouteMapLoaded ? (
                <div
                  style={{
                    minHeight: "460px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <LoadingSpinner message="Loading job map..." />
                </div>
              ) : mapEligibleJobs.length === 0 ? (
                <div
                  data-testid="job-map-empty"
                  style={{
                    minHeight: "160px",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    padding: "20px",
                  }}
                >
                  <EmptyState
                    title="No mappable jobs"
                    description="There are no eligible jobs with valid coordinate data available for the map."
                  />
                </div>
              ) : (
                <>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: "10px",
                      flexWrap: "wrap",
                    }}
                  >
                    <div
                      style={{
                        fontSize: "12px",
                        color: "#475569",
                        fontWeight: 600,
                      }}
                    >
                      Showing eligible jobs from the current backend job data.
                    </div>

                    <div
                      style={{
                        fontSize: "11px",
                        color: "#64748B",
                      }}
                    >
                      Jobs without valid coordinates are not plotted.
                    </div>
                  </div>

                  <div
                    data-testid="dispatcher-job-map"
                    style={{
                      width: "100%",
                      height: "520px",
                      borderRadius: "10px",
                      overflow: "hidden",
                      border: "1px solid #E2E8F0",
                    }}
                  >
                    <GoogleMap
                      mapContainerStyle={{
                        width: "100%",
                        height: "100%",
                      }}
                      center={mapEligibleJobs[0].coordinates}
                      zoom={11}
                      options={{
                        fullscreenControl: false,
                        streetViewControl: false,
                        mapTypeControl: false,
                      }}
                    >
                      {mapEligibleJobs.map(({ job, coordinates }) => (
                        <MarkerF
                          key={job.id}
                          position={coordinates}
                          title={`Job #${job.id}`}
                        />
                      ))}
                    </GoogleMap>
                  </div>

                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "8px",
                    }}
                  >
                    {mapEligibleJobs.map(({ job }) => (
                      <div
                        key={job.id}
                        data-testid={`job-map-item-${job.id}`}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "6px",
                          padding: "5px 9px",
                          borderRadius: "7px",
                          background: "#F8FAFC",
                          border: "1px solid #E2E8F0",
                          fontSize: "11px",
                          color: "#475569",
                          fontWeight: 600,
                        }}
                      >
                        <MapPin size={12} />
                        Job #{job.id}
                        {job.priority ? ` · ${job.priority}` : ""}
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Dispatch Confirmation Dialog */}
      {dispatchConfirmation && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="dispatch-confirmation-title"
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 5000,
            background: "rgba(15, 23, 42, 0.55)",
            backdropFilter: "blur(4px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "20px",
            boxSizing: "border-box",
          }}
          onClick={closeDispatchConfirmation}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "min(520px, 95vw)",
              maxHeight: "90vh",
              overflowY: "auto",
              background: "#FFFFFF",
              borderRadius: "14px",
              boxShadow: "0 24px 60px rgba(15, 23, 42, 0.22)",
              border: "1px solid #E2E8F0",
            }}
          >
            <div
              style={{
                padding: "18px 20px",
                borderBottom: "1px solid #E2E8F0",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "12px",
              }}
            >
              <div>
                <h3
                  id="dispatch-confirmation-title"
                  style={{
                    margin: 0,
                    fontSize: "16px",
                    fontWeight: 700,
                    color: "#1F2937",
                  }}
                >
                  Confirm Dispatch Action
                </h3>

                <p
                  style={{
                    margin: "4px 0 0",
                    fontSize: "11px",
                    color: "#64748B",
                  }}
                >
                  Review the action before submitting it.
                </p>
              </div>

              <button
                type="button"
                onClick={closeDispatchConfirmation}
                disabled={dispatchConfirmationLoading}
                aria-label="Close dispatch confirmation"
                style={{
                  border: "none",
                  background: "transparent",
                  color: "#64748B",
                  fontSize: "22px",
                  cursor: dispatchConfirmationLoading
                    ? "not-allowed"
                    : "pointer",
                  padding: "2px 6px",
                  opacity: dispatchConfirmationLoading ? 0.5 : 1,
                }}
              >
                ×
              </button>
            </div>

            <div
              style={{
                padding: "20px",
                display: "flex",
                flexDirection: "column",
                gap: "14px",
              }}
            >
              <div
                style={{
                  padding: "12px",
                  borderRadius: "9px",
                  background: "#F8FAFC",
                  border: "1px solid #E2E8F0",
                }}
              >
                <div
                  style={{
                    fontSize: "10px",
                    color: "#64748B",
                    fontWeight: 700,
                    textTransform: "uppercase",
                    marginBottom: "5px",
                  }}
                >
                  Intended Action
                </div>

                <div
                  style={{
                    fontSize: "14px",
                    color: "#1F2937",
                    fontWeight: 700,
                  }}
                >
                  {dispatchConfirmation.action}
                </div>
              </div>

              <div>
                <div
                  style={{
                    fontSize: "11px",
                    color: "#64748B",
                    fontWeight: 700,
                    marginBottom: "7px",
                  }}
                >
                  Affected Job{dispatchConfirmation.jobIds.length > 1 ? "s" : ""}
                </div>

                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: "6px",
                  }}
                >
                  {dispatchConfirmation.jobIds.map((jobId) => (
                    <span
                      key={jobId}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        padding: "5px 9px",
                        borderRadius: "6px",
                        background: "#EEF6F1",
                        border: "1px solid #CFE2D5",
                        color: "#2F4F3E",
                        fontSize: "11px",
                        fontWeight: 700,
                      }}
                    >
                      Job #{jobId}
                    </span>
                  ))}
                </div>
              </div>

              {dispatchConfirmation.technician && (
                <div>
                  <div
                    style={{
                      fontSize: "11px",
                      color: "#64748B",
                      fontWeight: 700,
                      marginBottom: "5px",
                    }}
                  >
                    Technician
                  </div>

                  <div
                    style={{
                      fontSize: "13px",
                      color: "#1F2937",
                      fontWeight: 600,
                    }}
                  >
                    {dispatchConfirmation.technician}
                  </div>
                </div>
              )}

              {dispatchConfirmation.action === "Manual Override" && (
                <div
                  role="note"
                  aria-label="Manual override notice"
                  style={{
                    padding: "10px 12px",
                    borderRadius: "8px",
                    background: "#FFF7ED",
                    border: "1px solid #FED7AA",
                    color: "#9A3412",
                    fontSize: "11px",
                    lineHeight: 1.5,
                    fontWeight: 600,
                  }}
                >
                  Manual dispatcher decision. This action is separate from AI technician
                  recommendations and requires justification. Authorization, validation,
                  audit recording, and persistence are enforced by the backend.
                </div>
              )}

              {dispatchConfirmation.reasonRequired && (
                <div>
                  <label
                    htmlFor="dispatch-confirmation-reason"
                    style={{
                      display: "block",
                      fontSize: "11px",
                      fontWeight: 700,
                      color: "#475569",
                      marginBottom: "6px",
                    }}
                  >
                    Reason *
                  </label>

                  <textarea
                    id="dispatch-confirmation-reason"
                    value={dispatchConfirmationReason}
                    onChange={(e) => {
                      setDispatchConfirmationReason(e.target.value);
                      setDispatchConfirmationError("");
                    }}
                    placeholder={
                      dispatchConfirmation.reasonPlaceholder ||
                      "Enter reason"
                    }
                    disabled={dispatchConfirmationLoading}
                    rows={3}
                    style={{
                      width: "100%",
                      boxSizing: "border-box",
                      resize: "vertical",
                      border: "1px solid #CBD5E1",
                      borderRadius: "7px",
                      padding: "9px 10px",
                      fontSize: "12px",
                      color: "#1F2937",
                      outline: "none",
                    }}
                  />
                </div>
              )}

              {dispatchConfirmationError && (
                <div
                  role="alert"
                  style={{
                    padding: "10px 12px",
                    borderRadius: "7px",
                    background: "#FEF2F2",
                    border: "1px solid #FECACA",
                    color: "#B91C1C",
                    fontSize: "12px",
                    lineHeight: 1.4,
                  }}
                >
                  {dispatchConfirmationError}
                </div>
              )}
            </div>

            <div
              style={{
                padding: "14px 20px 18px",
                borderTop: "1px solid #E2E8F0",
                display: "flex",
                justifyContent: "flex-end",
                gap: "8px",
              }}
            >
              <button
                type="button"
                onClick={closeDispatchConfirmation}
                disabled={dispatchConfirmationLoading}
                style={{
                  height: "36px",
                  padding: "0 14px",
                  border: "1px solid #CBD5E1",
                  borderRadius: "7px",
                  background: "#FFFFFF",
                  color: "#475569",
                  fontSize: "12px",
                  fontWeight: 600,
                  cursor: dispatchConfirmationLoading
                    ? "not-allowed"
                    : "pointer",
                  opacity: dispatchConfirmationLoading ? 0.6 : 1,
                }}
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={confirmDispatchAction}
                disabled={dispatchConfirmationLoading}
                style={{
                  height: "36px",
                  padding: "0 16px",
                  border: "none",
                  borderRadius: "7px",
                  background: "#2F6F44",
                  color: "#FFFFFF",
                  fontSize: "12px",
                  fontWeight: 700,
                  cursor: dispatchConfirmationLoading
                    ? "not-allowed"
                    : "pointer",
                  opacity: dispatchConfirmationLoading ? 0.65 : 1,
                }}
              >
                {dispatchConfirmationLoading
                  ? "Processing..."
                  : dispatchConfirmation.confirmLabel}
              </button>
            </div>
          </div>
        </div>
      )}

      {viewAssignment && (
        <div
          style={styles.centeredModalOverlay}
          onClick={() => setViewAssignment(null)}
        >
          <div style={styles.viewJobModal} onClick={e => e.stopPropagation()}>
            <div style={styles.viewModalHeader}>
              <h3 style={styles.viewModalHeaderH3}>Assignment Details</h3>
              <button onClick={() => setViewAssignment(null)} style={{ background: 'none', border: 'none', fontSize: 22, cursor: 'pointer', color: '#6b7280' }}>×</button>
            </div>
            <div style={styles.viewModalBody}>
              {viewAssignmentOverride && (
                <div style={{ marginBottom: "16px" }}>
                  <OverrideWarning
                    actorName={viewAssignmentOverride.actor_name}
                    actorRole={viewAssignmentOverride.actor_role}
                    assignedAt={viewAssignmentOverride.created_at}
                    reason={viewAssignmentOverride.justification}
                    onViewHistory={() => setShowOverrideHistoryForView(true)}
                  />
                </div>
              )}
              <div style={styles.viewDetailRow}><span style={styles.viewLabel}>Job ID</span><span style={styles.viewValue}>#{viewAssignment.job_id}</span></div>
              <div style={styles.viewDetailRow}><span style={styles.viewLabel}>Technician</span><span style={styles.viewValue}>{viewAssignment.technician}</span></div>
              <div style={styles.viewDetailRow}><span style={styles.viewLabel}>Skill</span><span style={styles.viewValue}>{viewAssignment.skill}</span></div>
              <div style={styles.viewDetailRow}><span style={styles.viewLabel}>Customer</span><span style={styles.viewValue}>{viewAssignment.customer}</span></div>
              <div style={styles.viewDetailRow}><span style={styles.viewLabel}>Location</span><span style={styles.viewValue}>{viewAssignment.location}</span></div>
              <div style={styles.viewDetailRow}><span style={styles.viewLabel}>Priority</span><span style={getPriorityStyle(viewAssignment.priority || "")}>{viewAssignment.priority || 'UNKNOWN'}</span></div>
              <div style={styles.viewDetailRow}><span style={styles.viewLabel}>Status</span><span style={{ ...styles.statusBadge, ...styles.statusAssigned }}>ASSIGNED</span></div>
              <div style={styles.viewDetailRow}><span style={styles.viewLabel}>Workload</span><span style={styles.viewValue}>{viewAssignment.current_jobs}/{viewAssignment.max_jobs}</span></div>
            </div>
          </div>
        </div>
      )}

      {showHistoryJobId && (
        <ReDispatchHistory
          jobId={showHistoryJobId}
          jobTitle={showHistoryJobTitle}
          onClose={() => {
            setShowHistoryJobId(null);
            setShowHistoryJobTitle("");
          }}
          onManualAssign={async (jobId, techId) => {
            const technician = allTechsList.find(
              (t) => t.technician_id === techId
            );

            openDispatchConfirmation({
              action: "Manual Assignment",
              jobIds: [jobId],
              technician:
                technician?.technician_name ||
                `Technician #${techId}`,
              details:
                "This manual assignment will be submitted through the existing backend assignment workflow.",
              confirmLabel: "Confirm Manual Assignment",
              execute: async () => {
                await handleManualAssign(jobId, techId);
              },
            });
          }}
          technicians={allTechsList}
          onForceAssignClick={(jobId, jobTitle) => {
            const selectedTechId = selectedTechs[jobId];

            const technician = allTechsList.find(
              (t) =>
                String(t.technician_id) ===
                String(selectedTechId)
            );

            openDispatchConfirmation({
              action: "Manual Override",
              jobIds: [jobId],
              technician:
                technician?.technician_name ||
                (selectedTechId
                  ? `Technician #${selectedTechId}`
                  : undefined),
              details:
                `${jobTitle} will be submitted to the existing backend manual override workflow. The backend remains responsible for authorization, validation and persistence.`,
              reasonRequired: true,
              reasonPlaceholder:
                "Enter manual override justification",
              confirmLabel: "Confirm Manual Override",
              execute: async (reason) => {
                if (!reason?.trim()) {
                  throw new Error(
                    "A reason is required before confirming this action."
                  );
                }

                if (!selectedTechId) {
                  throw new Error(
                    "Please select a technician before performing a manual override."
                  );
                }

                try {
                  await forceAssignEscalation(
                    jobId,
                    String(
                      technician?.technician_id ||
                        selectedTechId
                    ),
                    reason.trim()
                  );

                  showSuccess(
                    `Job #${jobId} force-assigned to ${
                      technician?.technician_name ||
                      selectedTechId
                    }.`
                  );

                  setSelectedTechs((prev) => {
                    const next = { ...prev };
                    delete next[jobId];
                    return next;
                  });

                  fetchAllData();
                } catch (err: any) {
                  throw err;
                }
              },
            });
          }}
          currentUserRole="dispatcher"
        />
      )}

      {showOverrideHistoryForJob && (
        <OverrideHistory
          jobId={showOverrideHistoryForJob.id}
          jobTitle={showOverrideHistoryForJob.title}
          onClose={() => setShowOverrideHistoryForJob(null)}
        />
      )}

      {showOverrideHistoryForView && viewAssignment && (
        <OverrideHistory
          jobId={viewAssignment.job_id}
          jobTitle={`${viewAssignment.customer}'s Job`}
          onClose={() => setShowOverrideHistoryForView(false)}
        />
      )}
    </div>
  );
}

export default PlanningDashboard;