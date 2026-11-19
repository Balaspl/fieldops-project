import React, { useEffect, useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  X, 
  Download, 
  ChevronDown, 
  ChevronUp, 
  Clock, 
  User, 
  ArrowRight, 
  Shield, 
  RefreshCw, 
  FileText 
} from "lucide-react";
import { io, Socket } from "socket.io-client";
import { getOverrideHistory } from "../../services/planningService";
import EmptyState from "../ui/EmptyState";

interface OverrideEventData {
  id: number;
  job_id: number;
  actor_name: string;
  actor_role: string;
  justification: string;
  previous_technician_id?: number | null;
  previous_technician_name?: string | null;
  new_technician_id: number;
  new_technician_name: string;
  created_at: string;
}

interface OverrideHistoryProps {
  jobId: number;
  jobTitle: string;
  onClose: () => void;
}

export default function OverrideHistory({
  jobId,
  jobTitle,
  onClose
}: OverrideHistoryProps) {
  const [history, setHistory] = useState<OverrideEventData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [sortOrder, setSortOrder] = useState<"newest" | "oldest">("newest");
  const [expandedIds, setExpandedIds] = useState<Record<number, boolean>>({});

  // Fetch history list from API
  const fetchHistory = async () => {
    try {
      setLoading(true);
      setError("");
      const res = await getOverrideHistory(jobId);
      if (res && res.data) {
        setHistory(res.data);
      }
    } catch (err: any) {
      setError("Failed to load override logs history.");
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

    // Set up Socket.IO listener for real-time updates with limited reconnection
    let socket: Socket;
    try {
      socket = io(socketUrl, {
        transports: ["websocket", "polling"],
        reconnectionAttempts: 5,
        reconnectionDelay: 2000,
        timeout: 10000,
      });
    } catch (err) {
      console.warn("OverrideHistory: Failed to create socket connection", err);
      return;
    }

    socket.on("connect_error", (err) => {
      console.warn("OverrideHistory: Socket connection error:", err.message);
    });

    socket.on("override:new", (data: any) => {
      // If the override belongs to this job, prepend to history
      if (data && (data.job_id === jobId || data.job_id === String(jobId))) {
        const newOverride = data.override || data;
        setHistory(prev => {
          // Prevent duplicates
          if (prev.some(item => item.id === newOverride.id)) return prev;
          return [newOverride, ...prev];
        });

        // Play brief notification tone
        try {
          const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
          const osc = audioCtx.createOscillator();
          const gain = audioCtx.createGain();
          osc.connect(gain);
          gain.connect(audioCtx.destination);
          osc.type = "sine";
          osc.frequency.setValueAtTime(523.25, audioCtx.currentTime); // C5
          gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
          osc.start();
          gain.gain.exponentialRampToValueAtTime(0.00001, audioCtx.currentTime + 0.2);
          osc.stop(audioCtx.currentTime + 0.2);
        } catch (e) {
          console.warn("Failed to play socket notification tone", e);
        }
      }
    });

    return () => {
      socket.disconnect();
    };
  }, [jobId]);

  // Expand / collapse toggler
  const toggleExpand = (id: number) => {
    setExpandedIds(prev => ({
      ...prev,
      [id]: !prev[id]
    }));
  };

  // Sort logs dynamically
  const sortedHistory = useMemo(() => {
    const data = [...history];
    return data.sort((a, b) => {
      const dateA = new Date(a.created_at).getTime();
      const dateB = new Date(b.created_at).getTime();
      return sortOrder === "newest" ? dateB - dateA : dateA - dateB;
    });
  }, [history, sortOrder]);

  // CSV Export Utility
  const handleExportCSV = () => {
    if (history.length === 0) return;
    const headers = ["ID", "Actor Name", "Role", "Timestamp", "Previous Technician", "New Technician", "Justification"];
    const rows = history.map(item => [
      item.id,
      item.actor_name,
      item.actor_role,
      item.created_at,
      item.previous_technician_name || "Unassigned",
      item.new_technician_name,
      item.justification
    ]);

    const csvContent = "data:text/csv;charset=utf-8," 
      + [headers.join(","), ...rows.map(e => e.map(val => `"${String(val).replace(/"/g, '""')}"`).join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `job_${jobId}_override_history.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // Get color configuration for actor roles
  const getRoleStyle = (role: string) => {
    const r = role.toLowerCase();
    if (r === "manager") {
      return "bg-blue-50 text-blue-700 border-blue-200";
    } else if (r === "admin") {
      return "bg-purple-50 text-purple-700 border-purple-200";
    } else {
      // dispatcher
      return "bg-emerald-50 text-emerald-700 border-emerald-200";
    }
  };

  return (
    <div className="fixed inset-0 z-[300] flex items-center justify-center bg-slate-950/60 backdrop-blur-sm p-4 animate-fadeIn">
      <motion.div 
        initial={{ opacity: 0, scale: 0.96, y: 15 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 15 }}
        transition={{ type: "spring", duration: 0.4 }}
        className="w-full max-w-3xl bg-white rounded-2xl shadow-2xl overflow-hidden border border-slate-100 flex flex-col max-h-[85vh]"
        style={{ fontFamily: "'Inter', sans-serif" }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="override-history-title"
      >
        {/* Header */}
        <div className="p-6 bg-slate-900 text-white flex justify-between items-center shrink-0">
          <div>
            <h2 id="override-history-title" className="text-lg font-bold tracking-tight">Manual Override History</h2>
            <p className="text-slate-400 text-xs mt-1">
              Job: <span className="font-semibold text-slate-200">{jobTitle}</span> (ID: #{jobId})
            </p>
          </div>
          <button 
            onClick={onClose}
            className="p-1.5 rounded-full hover:bg-white/10 text-slate-400 hover:text-white transition"
            aria-label="Close dialog"
          >
            <X size={20} />
          </button>
        </div>

        {/* Toolbar controls */}
        <div className="p-4 bg-slate-50 border-b border-slate-200/80 flex flex-wrap items-center justify-between gap-3 shrink-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-500">Sort By:</span>
            <select
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value as any)}
              className="bg-white border border-slate-200 rounded-lg py-1 px-2.5 text-xs font-bold text-slate-700 focus:outline-none focus:ring-1 focus:ring-slate-800"
              aria-label="Sort timeline entries"
            >
              <option value="newest">Newest First</option>
              <option value="oldest">Oldest First</option>
            </select>
          </div>

          <div className="flex gap-2">
            <button
              onClick={fetchHistory}
              className="p-1.5 border border-slate-200 rounded-lg text-slate-500 hover:bg-slate-100 transition"
              title="Refresh logs"
              aria-label="Refresh override data"
            >
              <RefreshCw size={14} />
            </button>
            <button
              onClick={handleExportCSV}
              disabled={history.length === 0}
              className="flex items-center gap-1.5 py-1.5 px-3 bg-slate-900 text-white rounded-lg text-xs font-bold hover:bg-slate-800 transition disabled:opacity-40 disabled:cursor-not-allowed"
              aria-label="Export history to CSV"
            >
              <Download size={14} />
              <span>Export CSV</span>
            </button>
          </div>
        </div>

        {/* Timeline Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {error && (
            <div className="p-3 bg-rose-50 text-rose-700 rounded-xl border border-rose-100 text-xs font-bold flex items-center gap-2">
              <Clock size={16} />
              <span>{error}</span>
            </div>
          )}

          {loading ? (
            <div className="flex flex-col items-center justify-center py-16">
              <div className="w-8 h-8 border-4 border-slate-200 border-t-slate-800 rounded-full animate-spin"></div>
              <p className="text-xs text-slate-400 font-semibold mt-3">Loading override records...</p>
            </div>
          ) : sortedHistory.length === 0 ? (
            <EmptyState
              title="No manual overrides recorded for this job"
              description="This job was routed via automated planning systems."
            />
          ) : (
            <div className="relative border-l-2 border-slate-100 pl-4 ml-3 space-y-6">
              {sortedHistory.map((item) => {
                const isExpanded = !!expandedIds[item.id];
                const dateStr = new Date(item.created_at).toLocaleString([], {
                  month: "short",
                  day: "2-digit",
                  hour: "2-digit",
                  minute: "2-digit",
                  second: "2-digit"
                });

                return (
                  <div key={item.id} className="relative">
                    {/* Timeline circle icon */}
                    <div className="absolute -left-[25px] top-1.5 w-4.5 h-4.5 rounded-full bg-white border-2 border-slate-300 flex items-center justify-center">
                      <div className="w-1.5 h-1.5 rounded-full bg-slate-800"></div>
                    </div>

                    {/* Timeline card */}
                    <div className="bg-white border border-slate-200/80 rounded-xl p-4 shadow-sm hover:border-slate-300 transition">
                      <div className="flex flex-wrap items-start justify-between gap-2 mb-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-bold text-xs text-slate-800">{item.actor_name}</span>
                          <span className={`px-2 py-0.5 rounded text-[9px] font-extrabold uppercase border ${getRoleStyle(item.actor_role)}`}>
                            {item.actor_role}
                          </span>
                        </div>
                        <span className="text-[10px] text-slate-400 font-medium">{dateStr}</span>
                      </div>

                      {/* Before / After routing */}
                      <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 bg-slate-50 border border-slate-100 rounded-lg p-2 mb-3">
                        <span className="text-[10px] uppercase font-bold text-slate-400">Assignment:</span>
                        <span className="text-slate-600 font-bold">{item.previous_technician_name || "Unassigned"}</span>
                        <ArrowRight size={12} className="text-slate-400" />
                        <span className="text-slate-900 font-bold">{item.new_technician_name}</span>
                      </div>

                      {/* Collapsible Justification Text */}
                      <div className="space-y-1">
                        <div 
                          onClick={() => toggleExpand(item.id)}
                          className="flex items-center justify-between text-xs font-bold text-slate-700 cursor-pointer select-none"
                        >
                          <span>Justification</span>
                          {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        </div>
                        
                        <p className={`text-xs text-slate-600 leading-relaxed font-medium transition-all ${
                          isExpanded ? "" : "line-clamp-2"
                        }`}>
                          {item.justification}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </motion.div>
    </div>
  );
}
