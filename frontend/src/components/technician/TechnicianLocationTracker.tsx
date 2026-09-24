import { useEffect, useRef, useState } from "react";
import { MapPin } from "lucide-react";
import { getTechnicianJobs } from "../../services/technicianPortalService";
import { sendGPSPing } from "../../services/gpsService";
import type { AuthUser } from "../../store/authStore";

type Props = { user: AuthUser | null };

const TRACKED_STATUSES = new Set(["EN_ROUTE", "ON_SITE", "IN_PROGRESS", "ACTIVE"]);

/** Collect real browser location and send it for the signed-in technician's active jobs. */
export default function TechnicianLocationTracker({ user }: Props) {
  const [status, setStatus] = useState("Location tracking starts with an active job");
  const [position, setPosition] = useState<GeolocationPosition | null>(null);
  const [jobs, setJobs] = useState<any[]>([]);
  const lastSentAt = useRef(0);
  const sending = useRef(false);

  useEffect(() => {
    if (!user || user.role !== "technician") return;
    let stopped = false;
    const refreshJobs = async () => {
      try {
        const response = await getTechnicianJobs();
        if (!stopped) setJobs(response.data || []);
      } catch (error) {
        console.warn("Could not load assigned jobs for GPS tracking:", error);
      }
    };
    void refreshJobs();
    const jobsTimer = window.setInterval(refreshJobs, 15000);

    if (!navigator.geolocation) {
      setStatus("Location is unavailable in this browser");
      return () => {
        stopped = true;
        window.clearInterval(jobsTimer);
      };
    }

    const watchId = navigator.geolocation.watchPosition(
      (currentPosition) => {
        if (!stopped) {
          setPosition(currentPosition);
          setStatus("Location fix received");
        }
      },
      (error) => {
        if (!stopped) {
          setStatus(
            error.code === error.PERMISSION_DENIED
              ? "Allow browser location access to share GPS"
              : "Waiting for a GPS fix",
          );
        }
      },
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 },
    );

    return () => {
      stopped = true;
      window.clearInterval(jobsTimer);
      navigator.geolocation.clearWatch(watchId);
    };
  }, [user]);

  useEffect(() => {
    if (!user || !position || sending.current) return;
    const activeJob = jobs.find((job) =>
      TRACKED_STATUSES.has(String(job.status || "").toUpperCase()),
    );
    if (!activeJob) {
      setStatus("Location fix received; waiting for an active job");
      return;
    }
    if (Date.now() - lastSentAt.current < 32000) return;

    sending.current = true;
    lastSentAt.current = Date.now();
    const { latitude, longitude, accuracy, altitude } = position.coords;
    void (async () => {
      try {
        await sendGPSPing(user.tenant_id, {
          technician_id: user.id,
          job_id: String(activeJob.id),
          latitude,
          longitude,
          timestamp: new Date(position.timestamp).toISOString(),
          accuracy,
          altitude,
        });
        setStatus("Sharing live location");
      } catch (error) {
        setStatus("Could not send location; will retry");
        console.warn("Technician GPS update failed:", error);
      } finally {
        sending.current = false;
      }
    })();
  }, [jobs, position, user]);

  if (!user || user.role !== "technician") return null;
  return (
    <div
      role="status"
      aria-live="polite"
      style={{ position: "fixed", right: 16, bottom: 16, zIndex: 10000, display: "flex", alignItems: "center", gap: 6, padding: "8px 12px", borderRadius: 20, background: "#fff", boxShadow: "0 2px 10px #0002", color: "#374151", fontSize: 12 }}
    >
      <MapPin size={14} /> {status}
    </div>
  );
}
