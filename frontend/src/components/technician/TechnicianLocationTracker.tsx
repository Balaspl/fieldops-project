import {
  useEffect,
  useRef,
  useState,
} from "react";

import { MapPin } from "lucide-react";

import {
  getTechnicianJobs,
} from "../../services/technicianPortalService";

import {
  sendGPSPing,
} from "../../services/gpsService";

import type { AuthUser } from "../../store/authStore";

type Props = {
  user: AuthUser | null;
};

const TRACKED_STATUSES = new Set([
  "EN_ROUTE",
  "ON_SITE",
  "IN_PROGRESS",
  "ACTIVE",
]);

export default function TechnicianLocationTracker({
  user,
}: Props) {
  // =========================================================
  // STATE
  // =========================================================

  const [status, setStatus] =
    useState(
      "Location tracking starts with an active job",
    );

  const [position, setPosition] =
    useState<GeolocationPosition | null>(
      null,
    );

  const [jobs, setJobs] =
    useState<any[]>([]);

  // =========================================================
  // SEND CONTROL
  // =========================================================

  const lastSentAt =
    useRef(0);

  const sending =
    useRef(false);

  // =========================================================
  // LOAD JOBS + START REAL GPS
  // =========================================================

  useEffect(() => {
    if (
      !user ||
      user.role !== "technician"
    ) {
      return;
    }

    let stopped = false;

    // =======================================================
    // LOAD TECHNICIAN JOBS
    // =======================================================

    const refreshJobs =
      async () => {
        try {
          const response =
            await getTechnicianJobs();

          if (!stopped) {
            const technicianJobs =
              response.data || [];

            setJobs(
              technicianJobs,
            );
          }
        } catch (error) {
          if (!stopped) {
            setStatus(
              "Unable to load technician jobs",
            );
          }
        }
      };

    void refreshJobs();

    /*
     * Refresh jobs every 15 seconds.
     */
    const jobsTimer =
      window.setInterval(
        refreshJobs,
        15000,
      );

    // =======================================================
    // CHECK BROWSER GPS
    // =======================================================

    if (
      !navigator.geolocation
    ) {
      setStatus(
        "Location is unavailable in this browser",
      );

      return () => {
        stopped = true;

        window.clearInterval(
          jobsTimer,
        );
      };
    }

    // =======================================================
    // START BROWSER GPS
    // =======================================================

    const watchId =
      navigator.geolocation.watchPosition(
        (
          currentPosition,
        ) => {

          if (stopped) {
            return;
          }

          /*
           * THIS IS THE REAL TECHNICIAN
           * CURRENT LOCATION.
           */
          setPosition(
            currentPosition,
          );

          const accuracy =
            currentPosition
              .coords
              .accuracy;

          if (
            accuracy != null &&
            accuracy <= 50
          ) {
            setStatus(
              `Good GPS accuracy: ${accuracy.toFixed(1)}m`,
            );
          } else if (
            accuracy != null &&
            accuracy <= 100
          ) {
            setStatus(
              `GPS accuracy: ${accuracy.toFixed(1)}m`,
            );
          } else if (
            accuracy != null
          ) {
            setStatus(
              `GPS accuracy: ${accuracy.toFixed(1)}m`,
            );
          } else {
            setStatus(
              "Location fix received",
            );
          }
        },

        (error) => {
          if (stopped) {
            return;
          }

          setStatus(
            error.code ===
              error.PERMISSION_DENIED
              ? "Allow browser location access to share GPS"
              : error.code ===
                  error.TIMEOUT
                ? "GPS timeout; waiting for a new fix"
                : "Waiting for a GPS fix",
          );
        },

        {
          enableHighAccuracy:
            true,

          maximumAge:
            0,

          timeout:
            8000,
        },
      );

    // =======================================================
    // CLEANUP
    // =======================================================

    return () => {
      stopped = true;

      window.clearInterval(
        jobsTimer,
      );

      navigator.geolocation.clearWatch(
        watchId,
      );
    };
  }, [user]);

  // =========================================================
  // REAL GPS → BACKEND
  // =========================================================

  useEffect(() => {
    if (
      !user ||
      user.role !== "technician" ||
      !position ||
      sending.current
    ) {
      return;
    }

    // =======================================================
    // FIND ACTIVE JOB
    // =======================================================

    const activeJob =
      jobs.find((job) =>
        TRACKED_STATUSES.has(
          String(
            job.status || "",
          ).toUpperCase(),
        ),
      );

    // =======================================================
    // NO ACTIVE JOB
    // =======================================================

    if (!activeJob) {
      setStatus(
        "Location fix received; waiting for an active job",
      );

      return;
    }

    // =======================================================
    // JOB STATUS
    // =======================================================

    const jobStatus =
      String(
        activeJob.status || "",
      ).toUpperCase();

    const isLiveTracking =
    TRACKED_STATUSES.has(jobStatus);

    // =======================================================
    // SENDING FREQUENCY
    // =======================================================

    const minimumClientInterval =
      isLiveTracking
        ? 2000
        : 30000;

    if (
      Date.now() -
        lastSentAt.current <
      minimumClientInterval
    ) {
      return;
    }

    // =======================================================
    // PREVENT CONCURRENT REQUESTS
    // =======================================================

    sending.current =
      true;

    const {
      latitude,
      longitude,
      accuracy,
      altitude,
    } =
      position.coords;

    // =======================================================
    // SEND
    // =======================================================

    void (async () => {
      try {
        await sendGPSPing(
          user.tenant_id,
          {
            technician_id:
              user.id,

            job_id:
              String(
                activeJob.id,
              ),

            latitude,

            longitude,

            timestamp:
              new Date(
                position.timestamp,
              ).toISOString(),

            accuracy,

            altitude,
          },
          {
            liveTracking:
              isLiveTracking,
          },
        );

        lastSentAt.current =
          Date.now();

        setStatus(
          isLiveTracking
            ? "Sharing live location"
            : "Location recorded",
        );
      } catch (error: any) {
        console.error(
          "[TechnicianLocationTracker] GPS ping failed:",
          error,
        );

        console.error(
          "[TechnicianLocationTracker] Response status:",
          error?.response?.status,
        );

        console.error(
          "[TechnicianLocationTracker] Response data:",
          error?.response?.data,
        );

        setStatus(
          "Could not send location; will retry",
        );
      } finally {
        sending.current =
          false;
      }
    })();
  }, [
    jobs,
    position,
    user,
  ]);

  // =========================================================
  // NON-TECHNICIAN
  // =========================================================

  if (
    !user ||
    user.role !== "technician"
  ) {
    return null;
  }

  // =========================================================
  // STATUS UI
  // =========================================================

  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        position: "fixed",
        right: 16,
        bottom: 16,
        zIndex: 10000,

        display: "flex",
        alignItems: "center",

        gap: 6,

        padding:
          "8px 12px",

        borderRadius: 20,

        background: "#fff",

        boxShadow:
          "0 2px 10px #0002",

        color: "#374151",

        fontSize: 12,
      }}
    >
      <MapPin size={14} />

      {status}
    </div>
  );
}
