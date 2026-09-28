import { useEffect, useRef, useState } from "react";
import {
  sendTechnicianAvailabilityLocation,
} from "../../services/gpsService";

interface TechnicianAvailabilityLocationProps {
  technicianId: string;
  tenantId: string;
  enabled?: boolean;
}

/**
 * Keeps the technician's latest device location available
 * before a job is assigned.
 *
 * This is separate from TechnicianLocationTracker:
 * - This component: pre-assignment location for Planning Agent
 * - TechnicianLocationTracker: job/live tracking after START
 */
const TechnicianAvailabilityLocation = ({
  technicianId,
  tenantId,
  enabled = true,
}: TechnicianAvailabilityLocationProps) => {
  const [locationStatus, setLocationStatus] = useState<
    "starting" | "active" | "denied" | "error"
  >("starting");

  const watchIdRef = useRef<number | null>(null);
  const lastSentAtRef = useRef<number>(0);
  const sendingRef = useRef(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    if (!enabled) {
      setLocationStatus("starting");
      return;
    }

    if (!technicianId || !tenantId) {
      console.warn(
        "[TechnicianAvailabilityLocation] Missing technicianId or tenantId",
      );
      return;
    }

    if (!navigator.geolocation) {
      console.error(
        "[TechnicianAvailabilityLocation] Geolocation is not supported",
      );

      setLocationStatus("error");
      return;
    }

    const sendLocation = async (
      position: GeolocationPosition,
    ) => {
      if (!mountedRef.current) {
        return;
      }

      /*
       * Do not send every browser GPS event.
       *
       * Redis location has a 120-second TTL on the backend,
       * so send a fresh location every 30 seconds.
       */
      const now = Date.now();

      if (now - lastSentAtRef.current < 30_000) {
        return;
      }

      if (sendingRef.current) {
        return;
      }

      const {
        latitude,
        longitude,
        accuracy,
        altitude,
      } = position.coords;

      /*
       * Ignore very inaccurate GPS readings.
       */
      if (
        accuracy != null &&
        accuracy > 100
      ) {
        console.warn(
          "[TechnicianAvailabilityLocation] GPS accuracy too low:",
          accuracy,
        );

        return;
      }

      sendingRef.current = true;

      try {
        console.log(
          "[TechnicianAvailabilityLocation] Sending location:",
          {
            technicianId,
            latitude,
            longitude,
            accuracy,
          },
        );

        await sendTechnicianAvailabilityLocation(
          tenantId,
          {
            latitude,
            longitude,
            accuracy:
              accuracy ?? null,
            altitude:
              altitude ?? null,
            timestamp:
              new Date(
                position.timestamp,
              ).toISOString(),
          },
        );

        lastSentAtRef.current =
          Date.now();

        if (mountedRef.current) {
          setLocationStatus("active");
        }

        console.log(
          "[TechnicianAvailabilityLocation] Location updated successfully",
        );
      } catch (error) {
        console.error(
          "[TechnicianAvailabilityLocation] Failed to send location:",
          error,
        );

        if (mountedRef.current) {
          setLocationStatus("error");
        }
      } finally {
        sendingRef.current = false;
      }
    };

    const handlePosition = (
      position: GeolocationPosition,
    ) => {
      if (!mountedRef.current) {
        return;
      }

      console.log(
        "[TechnicianAvailabilityLocation] GPS position:",
        {
          latitude:
            position.coords.latitude,
          longitude:
            position.coords.longitude,
          accuracy:
            position.coords.accuracy,
        },
      );

      /*
       * We have successfully obtained GPS.
       */
      setLocationStatus("active");

      void sendLocation(position);
    };

    const handleError = (
      error: GeolocationPositionError,
    ) => {
      if (!mountedRef.current) {
        return;
      }

      console.error(
        "[TechnicianAvailabilityLocation] GPS error:",
        {
          code: error.code,
          message: error.message,
        },
      );

      switch (error.code) {
        case error.PERMISSION_DENIED:
          setLocationStatus("denied");
          break;

        case error.POSITION_UNAVAILABLE:
        case error.TIMEOUT:
        default:
          setLocationStatus("error");
          break;
      }
    };

    /*
     * START GPS immediately when the technician page mounts.
     *
     * This does NOT depend on START button.
     * This does NOT require a job.
     */
    watchIdRef.current =
      navigator.geolocation.watchPosition(
        handlePosition,
        handleError,
        {
          enableHighAccuracy: true,
          maximumAge: 5_000,
          timeout: 15_000,
        },
      );

    console.log(
      "[TechnicianAvailabilityLocation] GPS watcher started",
    );

    /*
     * Cleanup when technician leaves the page.
     */
    return () => {
      mountedRef.current = false;

      if (
        watchIdRef.current !== null
      ) {
        navigator.geolocation.clearWatch(
          watchIdRef.current,
        );

        watchIdRef.current = null;
      }

      console.log(
        "[TechnicianAvailabilityLocation] GPS watcher stopped",
      );
    };
  }, [
    technicianId,
    tenantId,
    enabled,
  ]);

  /*
   * This component does not need to render anything visible.
   *
   * GPS runs in the background while the technician page is open.
   */
  return null;
};

export default TechnicianAvailabilityLocation;