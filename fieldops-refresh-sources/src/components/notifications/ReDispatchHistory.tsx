import React, { useEffect, useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  useReactTable, 
  getCoreRowModel, 
  getFilteredRowModel, 
  getSortedRowModel, 
  flexRender, 
  createColumnHelper 
} from "@tanstack/react-table";
import { 
  X, 
  Download, 
  Filter, 
  AlertTriangle, 
  AlertOctagon, 
  Clock, 
  TrendingUp, 
  RefreshCw, 
  History,
  FileText,
  Truck,
  Layers,
  Shield,
  Info,
  ChevronDown,
  UserCheck,
  AlertCircle,
  Copy,
  Check
} from "lucide-react";
import { io, Socket } from "socket.io-client";
import api from "../../services/api";

interface RedispatchAttempt {
  id: number;
  job_id: number;
  attempt_number: number;
  technician_id?: number | null;
  technician_name?: string | null;
  event_type: string; // rejection, timeout, offline, pending
  reason?: string | null;
  queue_position: number;
  next_dispatch_eta?: string | null;
  created_at: string;
}

import ForceAssignButton from "./ForceAssignButton";
import { getJob } from "../../services/planningService";
import { useToast } from "../../hooks/useToast";
import EmptyState from "../ui/EmptyState";

interface ReDispatchHistoryProps {
  jobId: number;
  jobTitle: string;
  onClose: () => void;
  onManualAssign?: (jobId: number, techId: number) => Promise<void>;
  technicians?: Array<{ technician_id: number; technician_name: string; technician_skill: string }>;
  onForceAssignClick?: (jobId: number, jobTitle: string) => void;
  currentUserRole?: string;
}

const columnHelper = createColumnHelper<RedispatchAttempt>();

const styles = {
  backdrop: {
    position: "fixed",
    inset: 0,
    zIndex: 300,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(15, 23, 42, 0.6)",
    backdropFilter: "blur(4px)",
    padding: "16px",
  } as React.CSSProperties,

  modalContainer: {
    width: "92vw",
    maxWidth: "1200px",
    height: "86vh",
    maxHeight: "86vh",
    backgroundColor: "#ffffff",
    borderRadius: "22px",
    boxShadow: "0 20px 25px -5px rgba(15, 23, 42, 0.08), 0 10px 10px -5px rgba(15, 23, 42, 0.04)",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    border: "1px solid #e2e8f0",
  } as React.CSSProperties,

  modalContainerMobile: {
    height: "auto",
    maxHeight: "90vh",
    width: "95vw",
  } as React.CSSProperties,

  header: {
    height: "72px",
    padding: "0 24px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    borderBottom: "1px solid #f1f5f9",
    backgroundColor: "#ffffff",
    flexShrink: 0,
  } as React.CSSProperties,

  headerIconBox: {
    width: "44px",
    height: "44px",
    backgroundColor: "#eff6ff",
    borderRadius: "12px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#2563eb",
  } as React.CSSProperties,

  headerTitle: {
    fontSize: "22px",
    fontWeight: 800,
    color: "#0f172a",
    letterSpacing: "-0.025em",
    lineHeight: 1.2,
    margin: 0,
  } as React.CSSProperties,

  headerSubtitle: {
    fontSize: "12px",
    color: "#64748b",
    fontWeight: 500,
    margin: "2px 0 0 0",
  } as React.CSSProperties,

  closeBtn: {
    width: "32px",
    height: "32px",
    borderRadius: "50%",
    backgroundColor: "#f1f5f9",
    color: "#64748b",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    transition: "all 0.2s ease",
    border: "none",
    cursor: "pointer",
    padding: 0,
  } as React.CSSProperties,

  body: {
    flex: 1,
    backgroundColor: "#f8fafc",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
  } as React.CSSProperties,

  bodyMobile: {
    overflowY: "auto",
  } as React.CSSProperties,

  bodyInner: {
    padding: "12px 16px",
    flex: 1,
    display: "flex",
    flexDirection: "column",
    gap: "12px",
    overflow: "hidden",
    minHeight: 0,
  } as React.CSSProperties,

  bodyInnerMobile: {
    overflow: "visible",
    height: "auto",
    flex: "none",
    padding: "16px",
  } as React.CSSProperties,

  summaryRow: {
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: "12px",
    flexShrink: 0,
  } as React.CSSProperties,

  summaryRowMobile: {
    gridTemplateColumns: "1fr",
    gap: "12px",
  } as React.CSSProperties,

  summaryCard: {
    height: "72px",
    padding: "8px 12px",
    backgroundColor: "#ffffff",
    border: "1px solid #e2e8f0",
    borderRadius: "16px",
    boxShadow: "0 2px 4px rgba(15, 23, 42, 0.02)",
    display: "flex",
    alignItems: "center",
    gap: "10px",
    textAlign: "left",
    transition: "transform 0.2s ease, box-shadow 0.2s ease",
  } as React.CSSProperties,

  summaryCardMobile: {
    height: "auto",
    minHeight: "72px",
    padding: "12px",
  } as React.CSSProperties,

  summaryIconBox: {
    width: "32px",
    height: "32px",
    borderRadius: "8px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  } as React.CSSProperties,

  summaryLabel: {
    fontSize: "9px",
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    color: "#94a3b8",
    lineHeight: 1,
  } as React.CSSProperties,

  summaryValue: {
    fontSize: "13px",
    fontWeight: 800,
    color: "#0f172a",
    marginTop: "2px",
    lineHeight: 1.2,
  } as React.CSSProperties,

  summarySubtitle: {
    fontSize: "10px",
    color: "#64748b",
    fontWeight: 500,
    marginTop: "1px",
    lineHeight: 1.2,
  } as React.CSSProperties,

  mainLayout: {
    display: "flex",
    gap: "16px",
    flex: 1,
    overflow: "hidden",
    minHeight: 0,
  } as React.CSSProperties,

  mainLayoutMobile: {
    flexDirection: "column",
    overflow: "visible",
    height: "auto",
    gap: "16px",
  } as React.CSSProperties,

  leftColumn: {
    flex: 1,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    height: "100%",
  } as React.CSSProperties,

  leftColumnMobile: {
    height: "auto",
    overflow: "visible",
  } as React.CSSProperties,

  rightColumn: {
    width: "410px",
    flexShrink: 0,
    display: "flex",
    flexDirection: "column",
    gap: "8px",
    overflowY: "auto",
    height: "100%",
    paddingRight: "4px",
  } as React.CSSProperties,

  rightColumnMobile: {
    width: "100%",
    height: "auto",
    overflow: "visible",
    paddingRight: 0,
  } as React.CSSProperties,

  eventHistoryCard: {
    backgroundColor: "#ffffff",
    borderRadius: "16px",
    border: "1px solid #e2e8f0",
    boxShadow: "0 4px 6px -1px rgba(15, 23, 42, 0.03)",
    display: "flex",
    flexDirection: "column",
    height: "100%",
    overflow: "hidden",
  } as React.CSSProperties,

  eventHistoryCardMobile: {
    minHeight: "300px",
    height: "auto",
  } as React.CSSProperties,

  eventHistoryHeader: {
    padding: "10px 16px",
    borderBottom: "1px solid #f1f5f9",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    flexShrink: 0,
  } as React.CSSProperties,

  eventHistoryTitle: {
    fontSize: "12px",
    fontWeight: 800,
    color: "#475569",
    textTransform: "uppercase",
    letterSpacing: "0.08em",
    margin: 0,
  } as React.CSSProperties,

  eventHistoryFilterBar: {
    padding: "8px 16px",
    borderBottom: "1px solid #f1f5f9",
    display: "flex",
    alignItems: "center",
    justifyContent: "flex-start",
    flexShrink: 0,
  } as React.CSSProperties,

  tableContainer: {
    flex: 1,
    overflowY: "auto",
    minHeight: 0,
  } as React.CSSProperties,

  bottomInfo: {
    padding: "8px 16px",
    backgroundColor: "#eff6ff",
    borderTop: "1px solid #dbeafe",
    fontSize: "10px",
    fontWeight: 500,
    color: "#1e40af",
    display: "flex",
    alignItems: "center",
    gap: "6px",
    flexShrink: 0,
  } as React.CSSProperties,

  detailsCard: {
    backgroundColor: "#ffffff",
    borderRadius: "16px",
    border: "1px solid #e2e8f0",
    boxShadow: "0 2px 4px rgba(15, 23, 42, 0.01)",
    padding: "10px 12px",
    textAlign: "left",
  } as React.CSSProperties,

  detailsCardHeader: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: "8px",
    cursor: "pointer",
    userSelect: "none",
  } as React.CSSProperties,

  detailsCardTitle: {
    fontSize: "12px",
    fontWeight: 800,
    color: "#475569",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    margin: 0,
  } as React.CSSProperties,

  detailGrid: {
    display: "flex",
    flexDirection: "column",
  } as React.CSSProperties,

  detailRow: {
    display: "grid",
    gridTemplateColumns: "130px 1fr",
    gap: "8px",
    alignItems: "center",
    fontSize: "12px",
    padding: "5px 0",
    borderBottom: "1px solid #f1f5f9",
    lineHeight: 1.3,
  } as React.CSSProperties,

  detailLabel: {
    color: "#64748b",
    fontWeight: 500,
    textAlign: "left",
  } as React.CSSProperties,

  detailValue: {
    color: "#0f172a",
    fontWeight: 700,
    textAlign: "left",
    display: "inline-flex",
    justifyContent: "flex-start",
    alignItems: "center",
    gap: "6px",
    wordBreak: "break-word",
    overflowWrap: "break-word",
    minWidth: 0,
  } as React.CSSProperties,

  manualCard: {
    backgroundColor: "#fffbeb",
    border: "1px solid #fde68a",
    borderRadius: "16px",
    padding: "12px",
    textAlign: "left",
  } as React.CSSProperties,

  manualTitle: {
    fontSize: "12px",
    fontWeight: 800,
    color: "#78350f",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
    margin: 0,
  } as React.CSSProperties,

  manualText: {
    fontSize: "10px",
    color: "#92400e",
    lineHeight: 1.3,
    marginTop: "3px",
  } as React.CSSProperties,

  manualBtn: {
    width: "100%",
    height: "34px",
    background: "#d97706",
    color: "#ffffff",
    borderRadius: "8px",
    fontSize: "12px",
    fontWeight: 700,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "6px",
    cursor: "pointer",
    transition: "background 0.2s",
    border: "none",
  } as React.CSSProperties,
};

const localCss = `
  .rdh-close-btn-hover:hover {
    background-color: #e2e8f0 !important;
    color: #0f172a !important;
  }
  .rdh-summary-card-hover:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 6px rgba(15, 23, 42, 0.04) !important;
  }
  .rdh-manual-btn-hover:hover {
    background: #b45309 !important;
  }
  .rdh-refresh-btn-hover:hover {
    background-color: #f8fafc !important;
    color: #334155 !important;
  }
  .rdh-csv-btn-hover:hover {
    background-color: #f8fafc !important;
  }
  .rdh-select-focus:focus {
    outline: none !important;
    border-color: #3b82f6 !important;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2) !important;
  }
  .rdh-tr-hover:hover {
    background-color: rgba(248, 250, 252, 0.6) !important;
  }
  .text-slate-hover:hover {
    color: #475569 !important;
  }
  .rdh-manual-submit-hover:hover:not(:disabled) {
    background-color: #1e293b !important;
  }

  /* Scrollbar styling - Hidden completely to satisfy no visible scrollbar track/button request */
  .scrollbar-thin {
    scrollbar-width: none; /* Firefox */
    -ms-overflow-style: none; /* IE and Edge */
  }
  .scrollbar-thin::-webkit-scrollbar {
    display: none;
    width: 0;
    height: 0;
  }
  .scrollbar-thin::-webkit-scrollbar-track {
    background: transparent;
  }
  .scrollbar-thin::-webkit-scrollbar-thumb {
    background-color: transparent;
  }
  .scrollbar-thin::-webkit-scrollbar-button {
    display: none;
    width: 0;
    height: 0;
  }
`;

export default function ReDispatchHistory({
  jobId,
  jobTitle,
  onClose,
  onManualAssign,
  technicians = [],
  onForceAssignClick,
  currentUserRole = "dispatcher"
}: ReDispatchHistoryProps) {
  const [history, setHistory] = useState<RedispatchAttempt[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filterReason, setFilterReason] = useState<string>("all");
  const [selectedTechId, setSelectedTechId] = useState<string>("");
  const [assigning, setAssigning] = useState(false);
  const [jobDetail, setJobDetail] = useState<any>(null);
  const [isJobDetailsExpanded, setIsJobDetailsExpanded] = useState(true);
  const [isDispatchStatusExpanded, setIsDispatchStatusExpanded] = useState(true);
  const [isQueueInfoExpanded, setIsQueueInfoExpanded] = useState(true);
  const [copiedJobId, setCopiedJobId] = useState(false);
  const { addToast } = useToast();

  const [windowWidth, setWindowWidth] = useState(typeof window !== "undefined" ? window.innerWidth : 1024);

  useEffect(() => {
    const handleResize = () => setWindowWidth(window.innerWidth);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const isMobile = windowWidth <= 1024;

  useEffect(() => {
    const fetchJobDetail = async () => {
      try {
        const res = await getJob(jobId);
        if (res && res.data) {
          setJobDetail(res.data);
        }
      } catch (err) {
        console.warn("Failed to fetch job details in ReDispatchHistory", err);
      }
    };
    fetchJobDetail();
  }, [jobId]);

  // Fetch history from backend
  const fetchHistory = async () => {
    try {
      setLoading(true);
      setError("");
      const response = await api.get(`/jobs/${jobId}/redispatch-history`);
      const data = response.data;
      setHistory(data);
    } catch (err: any) {
      setError(err.message || "An error occurred");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();

    // Guard: don't connect socket if URL is not configured
    const socketUrl = import.meta.env.VITE_SOCKET_URL;
    if (!socketUrl) {
      return;
    }

    // Setup Socket.IO listener for real-time updates with limited reconnection
    let socket: Socket;
    try {
      socket = io(socketUrl, {
        transports: ["websocket", "polling"],
        reconnectionAttempts: 5,
        reconnectionDelay: 2000,
        timeout: 10000,
      });
    } catch (err) {
      console.warn("ReDispatchHistory: Failed to create socket connection", err);
      return;
    }

    socket.on("connect_error", (err) => {
      console.warn("ReDispatchHistory: Socket connection error:", err.message);
    });

    socket.on("redispatch:alert", (data: any) => {
      if (data.job_id === jobId) {
        // Play subtle beep sound when new attempt is registered
        try {
          const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
          const oscillator = audioCtx.createOscillator();
          const gainNode = audioCtx.createGain();
          oscillator.connect(gainNode);
          gainNode.connect(audioCtx.destination);
          oscillator.type = "sine";
          oscillator.frequency.setValueAtTime(440, audioCtx.currentTime); // A4
          gainNode.gain.setValueAtTime(0.1, audioCtx.currentTime);
          oscillator.start();
          gainNode.gain.exponentialRampToValueAtTime(0.00001, audioCtx.currentTime + 0.3);
          oscillator.stop(audioCtx.currentTime + 0.3);
        } catch (e) {
          console.warn("Failed to play audio notification", e);
        }

        // Fetch fresh history from server
        fetchHistory();
      }
    });

    return () => {
      socket.disconnect();
    };
  }, [jobId]);

  // Derived stats from timeline
  const attemptCount = history.length;
  const currentQueuePosition = history.length > 0 ? history[history.length - 1].queue_position : 1;
  const nextDispatchETA = history.length > 0 ? history[history.length - 1].next_dispatch_eta : null;

  // Filter history by reason type
  const filteredData = useMemo(() => {
    if (filterReason === "all") return history;
    return history.filter(item => item.event_type.toLowerCase() === filterReason.toLowerCase());
  }, [history, filterReason]);

  // Column definitions for TanStack Table
  const columns = useMemo(() => [
    columnHelper.accessor("attempt_number", {
      header: "Attempt",
      cell: info => <span style={{ fontWeight: 600, color: "#1e293b" }}>#{info.getValue()}</span>
    }),
    columnHelper.accessor("event_type", {
      header: "Type",
      cell: info => {
        const type = info.getValue().toLowerCase();
        let styleObj: React.CSSProperties = {
          fontWeight: 600,
          color: "#334155",
          backgroundColor: "#f1f5f9",
          border: "1px solid #e2e8f0"
        };
        if (type === "rejection") {
          styleObj = {
            fontWeight: 600,
            color: "#be123c",
            backgroundColor: "#ffe4e6",
            border: "1px solid #fecdd3"
          };
        }
        if (type === "timeout") {
          styleObj = {
            fontWeight: 600,
            color: "#b45309",
            backgroundColor: "#fef3c7",
            border: "1px solid #fde68a"
          };
        }
        if (type === "offline") {
          styleObj = {
            fontWeight: 600,
            color: "#334155",
            backgroundColor: "#f1f5f9",
            border: "1px solid #e2e8f0"
          };
        }
        return (
          <span style={{ 
            padding: "2px 10px", 
            borderRadius: "9999px", 
            fontSize: "12px", 
            fontWeight: 600, 
            textTransform: "uppercase", 
            letterSpacing: "0.05em",
            ...styleObj
          }}>
            {info.getValue()}
          </span>
        );
      }
    }),
    columnHelper.accessor("technician_name", {
      header: "Technician",
      cell: info => info.getValue() || <span style={{ color: "#94a3b8", fontStyle: "italic" }}>Searching...</span>
    }),
    columnHelper.accessor("reason", {
      header: "Reason",
      cell: info => <span style={{ color: "#475569", fontWeight: 500 }}>{info.getValue() || "-"}</span>
    }),
    columnHelper.accessor("created_at", {
      header: "Time",
      cell: info => new Date(info.getValue()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    })
  ], []);

  const table = useReactTable({
    data: filteredData,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel()
  });

  // CSV Export Utility
  const handleExportCSV = () => {
    if (history.length === 0) return;
    const headers = ["Attempt", "Event Type", "Technician Name", "Reason", "Queue Position", "ETA", "Timestamp"];
    const rows = history.map(item => [
      item.attempt_number,
      item.event_type,
      item.technician_name || "",
      item.reason || "",
      item.queue_position,
      item.next_dispatch_eta || "",
      item.created_at
    ]);

    const csvContent = "data:text/csv;charset=utf-8," 
      + [headers.join(","), ...rows.map(e => e.map(val => `"${val}"`).join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `job_${jobId}_redispatch_history.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleManualAssignSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedTechId || !onManualAssign) return;
    try {
      setAssigning(true);
      setError("");
      await onManualAssign(jobId, parseInt(selectedTechId));
      onClose();
    } catch (err: any) {
      setError(err.message || "Failed to manually assign job");
    } finally {
      setAssigning(false);
    }
  };

  const isCompleted = jobDetail?.status?.toLowerCase() === "completed";
  const attemptsSubtitle = attemptCount === 0 
    ? "No dispatch attempts yet" 
    : `${attemptCount} of 5 attempts made`;
  
  const queueSubtitle = isCompleted
    ? "Job completed"
    : currentQueuePosition === 1
      ? "Top priority in queue"
      : `Position #${currentQueuePosition} in queue`;

  const etaSubtitle = isCompleted
    ? "Job is completed"
    : nextDispatchETA
      ? "Automatic search scheduled"
      : "No automatic search active";

  const containerFinalStyle = isMobile 
    ? { ...styles.modalContainer, ...styles.modalContainerMobile }
    : styles.modalContainer;

  const bodyFinalStyle = isMobile
    ? { ...styles.body, ...styles.bodyMobile }
    : styles.body;

  const bodyInnerFinalStyle = isMobile
    ? { ...styles.bodyInner, ...styles.bodyInnerMobile }
    : styles.bodyInner;

  const summaryRowFinalStyle = isMobile
    ? { ...styles.summaryRow, ...styles.summaryRowMobile }
    : styles.summaryRow;

  const summaryCardFinalStyle = isMobile
    ? { ...styles.summaryCard, ...styles.summaryCardMobile }
    : styles.summaryCard;

  const mainLayoutFinalStyle = isMobile
    ? { ...styles.mainLayout, ...styles.mainLayoutMobile }
    : styles.mainLayout;

  const leftColumnFinalStyle = isMobile
    ? { ...styles.leftColumn, ...styles.leftColumnMobile }
    : styles.leftColumn;

  const rightColumnFinalStyle = isMobile
    ? { ...styles.rightColumn, ...styles.rightColumnMobile }
    : styles.rightColumn;

  const eventHistoryCardFinalStyle = isMobile
    ? { ...styles.eventHistoryCard, ...styles.eventHistoryCardMobile }
    : styles.eventHistoryCard;

  return (
    <div style={styles.backdrop}>
      <style>{localCss}</style>
      <motion.div 
        initial={{ opacity: 0, scale: 0.96, y: 16 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 16 }}
        transition={{ type: "spring", duration: 0.4, bounce: 0.15 }}
        style={{ ...containerFinalStyle, fontFamily: "'Inter', sans-serif" }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="history-dialog-title"
      >
        {/* ── Header ── */}
        <div style={styles.header}>
          <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
            <div style={styles.headerIconBox}>
              <History className="w-5 h-5" style={{ width: "20px", height: "20px", color: "#2563eb" }} />
            </div>
            <div style={{ textAlign: "left" }}>
              <h2 id="history-dialog-title" style={styles.headerTitle}>Dispatch History</h2>
              <p style={styles.headerSubtitle}>
                {jobDetail ? `${jobDetail.service_type} - ${jobDetail.customer_name}` : jobTitle} (ID: #{jobId})
              </p>
            </div>
          </div>
          <button 
            onClick={onClose}
            className="rdh-close-btn-hover"
            style={styles.closeBtn}
            aria-label="Close dialog"
          >
            <X size={15} />
          </button>
        </div>

        {/* ── Modal Body ── */}
        <div style={bodyFinalStyle}>
          <div style={bodyInnerFinalStyle}>

            {/* KPI row */}
            <div style={summaryRowFinalStyle}>
              {/* Attempts */}
              <div className="rdh-summary-card-hover" style={summaryCardFinalStyle}>
                <div style={{ ...styles.summaryIconBox, backgroundColor: "#ecfdf5", color: "#059669" }}>
                  <FileText size={18} />
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={styles.summaryLabel}>Attempts</div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: "4px", marginTop: "2px", lineHeight: 1.2 }}>
                    <span style={{ fontSize: "20px", fontWeight: 800, color: "#0f172a" }}>{attemptCount}</span>
                    <span style={{ color: "#94a3b8", fontSize: "11px", fontWeight: 600 }}>/ 5 max</span>
                  </div>
                  <div style={styles.summarySubtitle}>{attemptsSubtitle}</div>
                </div>
              </div>

              {/* Queue Position */}
              <div className="rdh-summary-card-hover" style={summaryCardFinalStyle}>
                <div style={{ ...styles.summaryIconBox, backgroundColor: "#eff6ff", color: "#2563eb" }}>
                  <TrendingUp size={18} />
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={styles.summaryLabel}>Queue Position</div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: "4px", marginTop: "2px", lineHeight: 1.2 }}>
                    <span style={{ fontSize: "20px", fontWeight: 800, color: "#0f172a" }}>#{currentQueuePosition}</span>
                    <span style={{ color: "#94a3b8", fontSize: "11px", fontWeight: 600 }}>in line</span>
                  </div>
                  <div style={styles.summarySubtitle}>{queueSubtitle}</div>
                </div>
              </div>

              {/* Next Dispatch ETA */}
              <div className="rdh-summary-card-hover" style={summaryCardFinalStyle}>
                <div style={{ ...styles.summaryIconBox, backgroundColor: "#f5f3ff", color: "#7c3aed" }}>
                  <Clock size={18} />
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={styles.summaryLabel}>Next Dispatch ETA</div>
                  <div style={{ fontSize: "14px", fontWeight: 700, color: "#1e293b", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", marginTop: "2px", lineHeight: 1.2 }}>
                    {nextDispatchETA
                      ? new Date(nextDispatchETA).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                      : <span style={{ color: "#334155" }}>No pending search</span>}
                  </div>
                  <div style={styles.summarySubtitle}>{etaSubtitle}</div>
                </div>
              </div>
            </div>

            {/* ── Two-column body ── */}
            <div style={mainLayoutFinalStyle}>
              {/* Left Column: Event History */}
              <div style={{ ...leftColumnFinalStyle, textAlign: "left" }}>
                <div style={eventHistoryCardFinalStyle}>
                  {/* Card header */}
                  <div style={styles.eventHistoryHeader}>
                    <h3 style={styles.eventHistoryTitle}>Event History</h3>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <button
                        onClick={fetchHistory}
                        className="rdh-refresh-btn-hover"
                        style={{
                          padding: "6px",
                          border: "1px solid #cbd5e1",
                          borderRadius: "8px",
                          color: "#64748b",
                          backgroundColor: "#ffffff",
                          cursor: "pointer",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          transition: "background-color 0.15s, color 0.15s",
                        }}
                        title="Refresh"
                        aria-label="Refresh history"
                      >
                        <RefreshCw size={13} />
                      </button>
                      <button
                        onClick={handleExportCSV}
                        disabled={history.length === 0}
                        className="rdh-csv-btn-hover"
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "6px",
                          padding: "6px 12px",
                          border: "1px solid #cbd5e1",
                          color: "#475569",
                          backgroundColor: "#ffffff",
                          borderRadius: "8px",
                          fontSize: "11px",
                          fontWeight: 700,
                          cursor: "pointer",
                          transition: "background-color 0.15s",
                          opacity: history.length === 0 ? 0.4 : 1,
                        }}
                        aria-label="Export history to CSV"
                      >
                        <Download size={12} style={{ color: "#64748b" }} />
                        Export CSV
                      </button>
                    </div>
                  </div>

                  {/* Filter row */}
                  <div style={styles.eventHistoryFilterBar}>
                    <div style={{ position: "relative", display: "inline-block" }}>
                      <select
                        value={filterReason}
                        onChange={(e) => setFilterReason(e.target.value)}
                        className="rdh-select-focus"
                        style={{
                          appearance: "none",
                          backgroundColor: "#f8fafc",
                          border: "1px solid #e2e8f0",
                          borderRadius: "8px",
                          padding: "6px 28px 6px 12px",
                          fontSize: "11px",
                          fontWeight: 700,
                          color: "#334155",
                          cursor: "pointer",
                          transition: "background-color 0.15s",
                        }}
                        aria-label="Filter events by type"
                      >
                        <option value="all">All Events</option>
                        <option value="rejection">Rejections Only</option>
                        <option value="timeout">Timeouts Only</option>
                        <option value="offline">Offline Only</option>
                      </select>
                      <ChevronDown size={11} style={{ position: "absolute", right: "10px", top: "50%", transform: "translateY(-50%)", color: "#94a3b8", pointerEvents: "none" }} />
                    </div>
                  </div>

                  {/* Error */}
                  {error && (
                    <div style={{ margin: "16px 20px 0 20px", padding: "12px", backgroundColor: "#fff5f5", color: "#e53e3e", borderRadius: "8px", border: "1px solid #fed7d7", display: "flex", alignItems: "start", gap: "8px", fontSize: "12px", fontWeight: 600 }}>
                      <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" style={{ flexShrink: 0, marginTop: "2px" }} />
                      <span>{error}</span>
                    </div>
                  )}

                  {/* Content */}
                  <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
                    {loading ? (
                      <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "64px 0" }}>
                        <div style={{
                          width: "28px",
                          height: "28px",
                          border: "4px solid #e2e8f0",
                          borderTopColor: "#3b82f6",
                          borderRadius: "50%",
                          animation: "local-spin 1s linear infinite",
                        }} />
                        <p style={{ fontSize: "11px", color: "#94a3b8", fontWeight: 600, marginTop: "12px" }}>Loading history…</p>
                      </div>
                    ) : filteredData.length === 0 ? (
                      <EmptyState
                        title="No re-dispatch history logged"
                        description={
                          jobDetail
                            ? isCompleted
                              ? "This job was completed successfully without any re-dispatch attempts."
                              : "This job is currently not completed and has no failed dispatch attempts."
                            : "This job is either freshly queued or was assigned without attempts."
                        }
                      />
                    ) : (
                      <div className="scrollbar-thin" style={styles.tableContainer}>
                        <table style={{ minWidth: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "12px" }}>
                          <thead style={{ backgroundColor: "#f8fafc", textTransform: "uppercase", letterSpacing: "0.05em", position: "sticky", top: 0, zIndex: 10 }}>
                            {table.getHeaderGroups().map(headerGroup => (
                              <tr key={headerGroup.id}>
                                {headerGroup.headers.map(header => (
                                  <th key={header.id} style={{ padding: "12px 16px", fontSize: "10px", fontWeight: 800, color: "#94a3b8", borderBottom: "1px solid #f1f5f9" }}>
                                    {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                                  </th>
                                ))}
                              </tr>
                            ))}
                          </thead>
                          <tbody style={{ color: "#334155", fontWeight: 600 }}>
                            {table.getRowModel().rows.map(row => (
                              <tr key={row.id} className="rdh-tr-hover" style={{ transition: "background-color 0.1s", borderBottom: "1px solid #f8fafc" }}>
                                {row.getVisibleCells().map(cell => (
                                  <td key={cell.id} style={{ padding: "12px 16px" }}>
                                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>

                  {/* Bottom info banner */}
                  <div style={styles.bottomInfo}>
                    <Info size={13} style={{ color: "#3b82f6", flexShrink: 0 }} />
                    <span>
                      {isCompleted
                        ? "This job is completed. Re-dispatch events are closed."
                        : "Events will appear here once re-dispatch attempts are made."
                      }
                    </span>
                  </div>
                </div>
              </div>

              {/* Right Column: Detail Cards */}
              <div className="scrollbar-thin" style={rightColumnFinalStyle}>
                {/* Card 1: Job Details */}
                <div style={styles.detailsCard}>
                  <div style={styles.detailsCardHeader} onClick={() => setIsJobDetailsExpanded(!isJobDetailsExpanded)}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <div style={{ width: "24px", height: "24px", borderRadius: "6px", backgroundColor: "#ecfdf5", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                        <FileText size={13} style={{ color: "#059669" }} />
                      </div>
                      <h4 style={styles.detailsCardTitle}>Job Details</h4>
                    </div>
                    <button className="text-slate-hover" style={{ background: "none", border: "none", padding: 0, color: "#94a3b8", cursor: "pointer", display: "flex", alignItems: "center" }} type="button" aria-label="Toggle details">
                      <ChevronDown size={14} style={{ transform: isJobDetailsExpanded ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.2s" }} />
                    </button>
                  </div>
                  {isJobDetailsExpanded && (
                    <div style={styles.detailGrid}>
                      <div style={styles.detailRow}>
                        <span style={styles.detailLabel}>Job</span>
                        <span style={styles.detailValue}>
                          {jobDetail ? `${jobDetail.service_type} - ${jobDetail.customer_name}` : jobTitle}
                        </span>
                      </div>
                      <div style={styles.detailRow}>
                        <span style={styles.detailLabel}>Job ID</span>
                        <div style={styles.detailValue}>
                          <span>#{jobId}</span>
                          <button
                            type="button"
                            onClick={() => {
                              navigator.clipboard.writeText(String(jobId));
                              setCopiedJobId(true);
                              setTimeout(() => setCopiedJobId(false), 1000);
                              addToast({
                                type: "success",
                                title: "Copied!",
                                message: `Job ID #${jobId} copied to your clipboard`,
                                autoDismiss: 4000,
                                priority: "normal",
                              });
                            }}
                            style={{
                              padding: "4px",
                              backgroundColor: "transparent",
                              border: "none",
                              borderRadius: "4px",
                              transition: "color 0.2s",
                              color: "#94a3b8",
                              cursor: "pointer",
                              display: "inline-flex",
                              alignItems: "center"
                            }}
                            className="text-slate-hover"
                            title={copiedJobId ? "Copied!" : "Copy Job ID"}
                            aria-label={`Copy Job ID ${jobId}`}
                          >
                            {copiedJobId ? <Check size={11} style={{ color: "#10b981" }} /> : <Copy size={11} />}
                          </button>
                        </div>
                      </div>
                      <div style={styles.detailRow}>
                        <span style={styles.detailLabel}>Created</span>
                        <span style={styles.detailValue}>
                          {jobDetail?.created_at ? new Date(jobDetail.created_at).toLocaleString([], { month: 'short', day: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : "—"}
                        </span>
                      </div>
                      <div style={styles.detailRow}>
                        <span style={styles.detailLabel}>Priority</span>
                        <span style={styles.detailValue}>
                          <span style={{ width: "8px", height: "8px", borderRadius: "50%", flexShrink: 0, backgroundColor: ['high','critical'].includes((jobDetail?.priority || '').toLowerCase()) ? '#f97316' : '#94a3b8' }} />
                          <span>{(jobDetail?.priority || '—').toUpperCase()}</span>
                        </span>
                      </div>
                      <div style={styles.detailRow}>
                        <span style={styles.detailLabel}>Service Line</span>
                        <span style={styles.detailValue}>{jobDetail?.service_type || "—"}</span>
                      </div>
                      <div style={styles.detailRow}>
                        <span style={styles.detailLabel}>Address</span>
                        <span style={styles.detailValue}>{jobDetail?.location || "—"}</span>
                      </div>
                    </div>
                  )}
                </div>

                {/* Card 2: Current Dispatch Status */}
                <div style={styles.detailsCard}>
                  <div style={styles.detailsCardHeader} onClick={() => setIsDispatchStatusExpanded(!isDispatchStatusExpanded)}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <div style={{ width: "24px", height: "24px", borderRadius: "6px", backgroundColor: "#eff6ff", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                        <Truck size={13} style={{ color: "#2563eb" }} />
                      </div>
                      <h4 style={styles.detailsCardTitle}>Current Dispatch Status</h4>
                    </div>
                    <button className="text-slate-hover" style={{ background: "none", border: "none", padding: 0, color: "#94a3b8", cursor: "pointer", display: "flex", alignItems: "center" }} type="button" aria-label="Toggle status">
                      <ChevronDown size={14} style={{ transform: isDispatchStatusExpanded ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.2s" }} />
                    </button>
                  </div>
                  {isDispatchStatusExpanded && (
                    <div style={styles.detailGrid}>
                      <div style={styles.detailRow}>
                        <span style={styles.detailLabel}>Status</span>
                        <div style={styles.detailValue}>
                          {(() => {
                            const s = (jobDetail?.status || 'queued').toLowerCase();
                            let customCls = {
                              backgroundColor: "#f1f5f9",
                              textColor: "#334155",
                              borderColor: "#e2e8f0"
                            };
                            if (s === "completed") customCls = { backgroundColor: "#ecfdf5", textColor: "#047857", borderColor: "#a7f3d0" };
                            else if (["assigned", "in progress", "en_route", "on_site"].includes(s)) customCls = { backgroundColor: "#eff6ff", textColor: "#1d4ed8", borderColor: "#bfdbfe" };
                            else if (["queued", "active", "pending"].includes(s)) customCls = { backgroundColor: "#fffbeb", textColor: "#b45309", borderColor: "#fde68a" };
                            else if (["failed", "expired"].includes(s)) customCls = { backgroundColor: "#fef2f2", textColor: "#b91c1c", borderColor: "#fca5a5" };

                            return (
                              <span style={{
                                display: "inline-block",
                                padding: "2px 8px",
                                borderRadius: "9999px",
                                fontSize: "10px",
                                fontWeight: 700,
                                border: `1px solid ${customCls.borderColor}`,
                                textTransform: "uppercase",
                                letterSpacing: "0.05em",
                                backgroundColor: customCls.backgroundColor,
                                color: customCls.textColor
                              }}>
                                {jobDetail?.status || 'Queued'}
                              </span>
                            );
                          })()}
                        </div>
                      </div>
                      <div style={styles.detailRow}>
                        <span style={styles.detailLabel}>Dispatch Method</span>
                        <span style={styles.detailValue}>Automatic (PlanningAgent)</span>
                      </div>
                      <div style={styles.detailRow}>
                        <span style={styles.detailLabel}>Attempts</span>
                        <span style={styles.detailValue}>{attemptCount} of 5</span>
                      </div>
                    </div>
                  )}
                </div>

                {/* Card 3: Queue Information */}
                <div style={styles.detailsCard}>
                  <div style={styles.detailsCardHeader} onClick={() => setIsQueueInfoExpanded(!isQueueInfoExpanded)}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <div style={{ width: "24px", height: "24px", borderRadius: "6px", backgroundColor: "#f5f3ff", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                        <Layers size={13} style={{ color: "#7c3aed" }} />
                      </div>
                      <h4 style={styles.detailsCardTitle}>Queue Information</h4>
                    </div>
                    <button className="text-slate-hover" style={{ background: "none", border: "none", padding: 0, color: "#94a3b8", cursor: "pointer", display: "flex", alignItems: "center" }} type="button" aria-label="Toggle queue info">
                      <ChevronDown size={14} style={{ transform: isQueueInfoExpanded ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 0.2s" }} />
                    </button>
                  </div>
                  {isQueueInfoExpanded && (
                    <div style={styles.detailGrid}>
                      <div style={styles.detailRow}>
                        <span style={styles.detailLabel}>Queue</span>
                        <span style={styles.detailValue}>{jobDetail?.service_type || "General"} Dispatch</span>
                      </div>
                      <div style={styles.detailRow}>
                        <span style={styles.detailLabel}>Queue Position</span>
                        <span style={styles.detailValue}>#{currentQueuePosition} in line</span>
                      </div>
                      <div style={styles.detailRow}>
                        <span style={styles.detailLabel}>Next ETA</span>
                        <span style={styles.detailValue}>
                          {nextDispatchETA ? new Date(nextDispatchETA).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "No pending search"}
                        </span>
                      </div>
                    </div>
                  )}
                </div>

                {/* Card 4: Manual Intervention */}
                {onForceAssignClick && (
                  <div style={styles.manualCard}>
                    <div style={{ display: "flex", alignItems: "flex-start", gap: "10px", marginBottom: "12px" }}>
                      <div style={{ width: "24px", height: "24px", borderRadius: "6px", backgroundColor: "#fef3c7", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: "2px" }}>
                        <Shield size={13} style={{ color: "#b45309" }} />
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <h4 style={styles.manualTitle}>Manual Intervention / Override</h4>
                        <p style={styles.manualText}>
                          Bypass automatic PlanningAgent rules and force-assign this job to any eligible technician with full justification.
                        </p>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => onForceAssignClick(jobId, jobTitle)}
                      className="rdh-manual-btn-hover"
                      style={styles.manualBtn}
                    >
                      <Shield size={13} />
                      Force Assign Job
                    </button>
                    <div style={{ marginTop: "10px", display: "flex", alignItems: "center", gap: "6px", fontSize: "10px", color: "#b45309", fontWeight: 600, textAlign: "left" }}>
                      <Info size={11} style={{ flexShrink: 0 }} />
                      Manual overrides are logged and require justification.
                    </div>
                  </div>
                )}

                {/* Fallback: legacy manual assign */}
                {onManualAssign && !onForceAssignClick && (
                  <div style={styles.detailsCard}>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", paddingBottom: "8px", borderBottom: "1px solid #f1f5f9", marginBottom: "12px" }}>
                      <div style={{ width: "24px", height: "24px", borderRadius: "6px", backgroundColor: "#f1f5f9", display: "flex", alignItems: "center", justifyContent: "center" }}>
                        <UserCheck size={13} style={{ color: "#475569" }} />
                      </div>
                      <h4 style={styles.detailsCardTitle}>Manual Assignment</h4>
                    </div>
                    <form onSubmit={handleManualAssignSubmit} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                      <select
                        id="tech-select"
                        value={selectedTechId}
                        onChange={(e) => setSelectedTechId(e.target.value)}
                        className="rdh-select-focus"
                        style={{
                          width: "100%",
                          backgroundColor: "#f8fafc",
                          border: "1px solid #e2e8f0",
                          borderRadius: "8px",
                          padding: "8px 12px",
                          fontSize: "12px",
                          fontWeight: 600,
                          color: "#475569",
                        }}
                        aria-label="Select Technician to Force-Assign"
                        required
                      >
                        <option value="">-- Choose a Technician --</option>
                        {technicians.map(t => (
                          <option key={t.technician_id} value={t.technician_id}>
                            {t.technician_name} ({t.technician_skill})
                          </option>
                        ))}
                      </select>
                      <button
                        type="submit"
                        disabled={assigning || !selectedTechId}
                        className="rdh-manual-submit-hover"
                        style={{
                          width: "100%",
                          padding: "8px",
                          backgroundColor: "#0f172a",
                          color: "#ffffff",
                          borderRadius: "8px",
                          fontSize: "12px",
                          fontWeight: 700,
                          border: "none",
                          cursor: "pointer",
                          transition: "background-color 0.2s",
                          opacity: (assigning || !selectedTechId) ? 0.5 : 1,
                        }}
                      >
                        {assigning ? "Assigning…" : "Manual Assign"}
                      </button>
                    </form>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

      </motion.div>
    </div>
  );
}
