import React, { useEffect, useState, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, AlertOctagon, X } from "lucide-react";
import { io, Socket } from "socket.io-client";
import { getAlerts, acknowledgeAlert } from "../../services/alertService";
import ForceAssignButton from "./ForceAssignButton";

export interface RedispatchAlert {
  alert_id: string;
  job_id: number;
  title: string;
  customer_name?: string;
  attempt_count: number;
  status?: string;
}

interface AlertBannerProps {
  onViewHistory: (jobId: number, jobTitle: string) => void;
  onManualAssignClick: (jobId: number, jobTitle: string) => void;
  currentUserRole?: string;
}

export default function AlertBanner({
  onViewHistory,
  onManualAssignClick,
  currentUserRole = "dispatcher"
}: AlertBannerProps) {
  const [alerts, setAlerts] = useState<RedispatchAlert[]>([]);
  const isFirstLoad = useRef(true);

  // Fetch current active alerts from backend
  const fetchAlerts = async () => {
    try {
      const data = await getAlerts();
      if (data) {
        // Map backend DispatcherAlertResponse to local RedispatchAlert shape
        const mapped: RedispatchAlert[] = data
          .filter((a: any) => !a.acknowledged && a.attempt_count >= 3)
          .map((a: any) => ({
            alert_id: a.alert_id,
            job_id: parseInt(a.job_id, 10),
            title: a.job_title || `Job ${a.job_id}`,
            customer_name: undefined,
            attempt_count: a.attempt_count || 0,
            status: a.severity
          }));
        setAlerts(mapped);
      }
    } catch (err) {
      console.warn("Failed to fetch redispatch alerts from backend", err);
    }
  };


  // Synthesize warning/alarm sounds using Web Audio API
  const playAlertSound = (severity: "warning" | "critical") => {
    try {
      const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
      if (severity === "critical") {
        // Play dual tone siren alarm
        const playSirenCycle = (delay: number) => {
          const osc1 = audioCtx.createOscillator();
          const osc2 = audioCtx.createOscillator();
          const gainNode = audioCtx.createGain();
          osc1.connect(gainNode);
          osc2.connect(gainNode);
          gainNode.connect(audioCtx.destination);

          osc1.type = "sawtooth";
          osc2.type = "square";
          osc1.frequency.setValueAtTime(600, audioCtx.currentTime + delay);
          osc2.frequency.setValueAtTime(650, audioCtx.currentTime + delay);
          gainNode.gain.setValueAtTime(0.08, audioCtx.currentTime + delay);

          // Siren pitch bending
          osc1.frequency.linearRampToValueAtTime(800, audioCtx.currentTime + delay + 0.25);
          osc2.frequency.linearRampToValueAtTime(850, audioCtx.currentTime + delay + 0.25);
          osc1.frequency.linearRampToValueAtTime(600, audioCtx.currentTime + delay + 0.5);
          osc2.frequency.linearRampToValueAtTime(650, audioCtx.currentTime + delay + 0.5);

          gainNode.gain.exponentialRampToValueAtTime(0.00001, audioCtx.currentTime + delay + 0.5);
          osc1.start(audioCtx.currentTime + delay);
          osc2.start(audioCtx.currentTime + delay);
          osc1.stop(audioCtx.currentTime + delay + 0.5);
          osc2.stop(audioCtx.currentTime + delay + 0.5);
        };

        // Play 2 cycles
        playSirenCycle(0);
        playSirenCycle(0.6);
      } else {
        // Simple double warning beep
        const playBeep = (time: number) => {
          const osc = audioCtx.createOscillator();
          const gain = audioCtx.createGain();
          osc.connect(gain);
          gain.connect(audioCtx.destination);
          osc.type = "sine";
          osc.frequency.setValueAtTime(880, audioCtx.currentTime + time); // High A
          gain.gain.setValueAtTime(0.08, audioCtx.currentTime + time);
          gain.gain.exponentialRampToValueAtTime(0.00001, audioCtx.currentTime + time + 0.15);
          osc.start(audioCtx.currentTime + time);
          osc.stop(audioCtx.currentTime + time + 0.15);
        };
        playBeep(0);
        playBeep(0.2);
      }
    } catch (e) {
      console.warn("Could not play synthesized alarm sound", e);
    }
  };

  useEffect(() => {
    fetchAlerts().then(() => {
      isFirstLoad.current = false;
    });

    // Guard: don't connect socket if URL is not configured
    const socketUrl = import.meta.env.VITE_SOCKET_URL;
    if (!socketUrl) {
      console.warn("AlertBanner: VITE_SOCKET_URL not configured, skipping WebSocket connection.");
      return;
    }

    // Connect to WebSocket client with limited reconnection to prevent browser freeze
    let socket: Socket;
    try {
      socket = io(socketUrl, {
        transports: ["websocket", "polling"],
        reconnectionAttempts: 5,
        reconnectionDelay: 2000,
        timeout: 10000,
      });
    } catch (err) {
      console.warn("AlertBanner: Failed to create socket connection", err);
      return;
    }

    socket.on("connect_error", (err) => {
      console.warn("AlertBanner: Socket connection error:", err.message);
    });

    socket.on("redispatch:alert", (data: any) => {
      const count = data.attempt_number;
      // Only trigger alerts and sound if it reaches threshold of 3 or more attempts
      if (count >= 3) {
        playAlertSound(count >= 5 ? "critical" : "warning");
      }

      // Append or update the alert
      setAlerts(prev => {
        const existingIdx = prev.findIndex(a => a.job_id === data.job_id);

        if (count >= 3) {
          const newAlert: RedispatchAlert = {
            alert_id: data.alert_id,
            job_id: data.job_id,
            title: data.title,
            customer_name: data.customer_name,
            attempt_count: count
          };

          if (existingIdx >= 0) {
            const updated = [...prev];
            updated[existingIdx] = newAlert;
            return updated;
          } else {
            return [newAlert, ...prev];
          }
        } else {
          // If count is less than 3, filter out if it was there
          return prev.filter(a => a.job_id !== data.job_id);
        }
      });
    });

    socket.on("redispatch:dismiss", (data: any) => {
      // Remove alert if dismissed or manually assigned
      setAlerts(prev => prev.filter(a => a.job_id !== data.job_id));
    });

    return () => {
      socket.disconnect();
    };
  }, []);

  const handleAcknowledgeAlert = async (alertId: string, jobId: number) => {
    try {
      if (alertId) {
        await acknowledgeAlert(alertId);
      }
      setAlerts(prev => prev.filter(a => a.job_id !== jobId));
    } catch (err) {
      console.error("Failed to acknowledge alert in backend", err);
      // Fallback: dismiss locally anyway
      setAlerts(prev => prev.filter(a => a.job_id !== jobId));
    }
  };


  // Limit displaying up to 3 banners visible at the same time
  const visibleAlerts = alerts.slice(0, 3);

  if (alerts.length === 0) return null;

  return (
    <div className="w-full flex flex-col gap-2 mb-4">
      <AnimatePresence initial={false}>
        {visibleAlerts.map(alert => {
          const isCritical = alert.attempt_count >= 5;
          return (
            <motion.div
              key={alert.alert_id}
              initial={{ opacity: 0, y: -20, height: 0 }}
              animate={{ opacity: 1, y: 0, height: "auto" }}
              exit={{ opacity: 0, y: -20, height: 0 }}
              transition={{ type: "spring", stiffness: 400, damping: 30 }}
              className={`overflow-hidden rounded-xl border shadow-sm ${isCritical
                  ? "bg-rose-50 border-rose-200 text-rose-800"
                  : "bg-amber-50 border-amber-200 text-amber-800"
                }`}
              style={{ fontFamily: "'Inter', sans-serif" }}
            >
              <div className="p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className={`p-2 rounded-lg shrink-0 ${isCritical ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-700"
                    }`}>
                    {isCritical ? <AlertOctagon size={20} className="animate-bounce" /> : <AlertTriangle size={20} />}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-white border shrink-0">
                        {isCritical ? "Critical Alert" : "Attention Required"}
                      </span>
                      <span className="text-xs font-semibold text-slate-500">ID: #{alert.job_id}</span>
                    </div>
                    <h4 className="text-sm font-bold mt-1 text-slate-900 leading-tight">
                      Job re-dispatched <span className="underline">{alert.attempt_count} times</span>: {alert.title}
                    </h4>
                  </div>
                </div>

                <div className="flex items-center gap-3 w-full sm:w-auto shrink-0 justify-end">
                  <button
                    onClick={() => onViewHistory(alert.job_id, alert.title)}
                    className="text-xs font-semibold hover:underline bg-white border border-slate-200 px-3 py-1.5 rounded-lg text-slate-700 transition"
                  >
                    View History
                  </button>
                  <ForceAssignButton
                    onClick={() => onManualAssignClick(alert.job_id, alert.title)}
                    currentUserRole={currentUserRole}
                    className={isCritical ? "bg-rose-600 hover:bg-rose-700" : "bg-amber-600 hover:bg-amber-700"}
                    label={isCritical ? "Manual Assign + Escalate" : "Manual Assign"}
                  />
                  <button
                    onClick={() => handleAcknowledgeAlert(alert.alert_id, alert.job_id)}
                    className="p-1 rounded-full hover:bg-black/5 text-slate-400 hover:text-slate-700 transition shrink-0"
                    aria-label="Dismiss alert"
                  >
                    <X size={16} />
                  </button>
                </div>
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
