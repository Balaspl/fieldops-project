import { useEffect, useRef, useState } from "react";
import {
  sendTechnicianAvailabilityLocation,
} from "../../services/gpsService";

interface TechnicianAvailabilityLocationProps {
  technicianId: string;
  tenantId: string;

  /**
   * Existing technician availability/status from the dashboard.
   *
   * GPS starts only when this is "Available".
   */
  technicianStatus?: string | null;

  /**
   * Optional master switch.
   */
  enabled?: boolean;
}

type LocationStatus =
  | "idle"
  | "starting"
  | "active"
  | "denied"
  | "error";

const LOCATION_SEND_INTERVAL_MS = 30_000;

const normalizeStatus = (
  status?: string | null,
): string => {
  return (status || "")
    .trim()
    .toLowerCase()
    .replace(/_/g, " ");
};

const isAvailableStatus = (
  status?: string | null,
): boolean => {
  return normalizeStatus(status) === "available";
};

const TechnicianAvailabilityLocation = ({
  technicianId,
  tenantId,
  technicianStatus,
  enabled = true,
}: TechnicianAvailabilityLocationProps) => {
  const [locationStatus, setLocationStatus] =
    useState<LocationStatus>("idle");

  const watchIdRef =
    useRef<number | null>(null);

  const lastSentAtRef =
    useRef<number>(0);

  const sendingRef =
    useRef(false);

  const mountedRef =
    useRef(true);

  /*
   * Keep the latest values available to
   * asynchronous GPS callbacks.
   */
  const technicianIdRef =
    useRef(technicianId);

  const tenantIdRef =
    useRef(tenantId);

  const availableRef =
    useRef(
      isAvailableStatus(
        technicianStatus,
      ),
    );

  useEffect(() => {
    technicianIdRef.current =
      technicianId;
  }, [technicianId]);

  useEffect(() => {
    tenantIdRef.current =
      tenantId;
  }, [tenantId]);

  useEffect(() => {
    availableRef.current =
      isAvailableStatus(
        technicianStatus,
      );
  }, [technicianStatus]);

  useEffect(() => {
    mountedRef.current = true;

    const shouldTrackLocation =
      enabled &&
      Boolean(technicianId) &&
      Boolean(tenantId) &&
      isAvailableStatus(
        technicianStatus,
      );

    /*
     * If technician is NOT Available,
     * immediately stop any existing watcher.
     */
    if (!shouldTrackLocation) {
      availableRef.current = false;

      if (
        watchIdRef.current !== null
      ) {
        navigator.geolocation.clearWatch(
          watchIdRef.current,
        );

        watchIdRef.current = null;

        console.log(
          "[TechnicianAvailabilityLocation] GPS watcher stopped - technician is not Available",
        );
      }

      sendingRef.current = false;

      if (mountedRef.current) {
        setLocationStatus("idle");
      }

      return () => {
        mountedRef.current = false;
      };
    }

    /*
     * From this point the technician is Available.
     */
    availableRef.current = true;

    if (!navigator.geolocation) {
      console.error(
        "[TechnicianAvailabilityLocation] Geolocation is not supported",
      );

      setLocationStatus("error");

      return () => {
        mountedRef.current = false;
      };
    }

    /*
     * Avoid creating duplicate GPS watchers.
     */
    if (watchIdRef.current !== null) {
      return () => {
        mountedRef.current = false;
      };
    }

    setLocationStatus("starting");

    const sendLocation = async (
      position: GeolocationPosition,
    ) => {
      if (
        !mountedRef.current ||
        !availableRef.current
      ) {
        return;
      }

      /*
       * Don't send every browser GPS event.
       *
       * Backend location data has a TTL, so
       * refresh it every 30 seconds.
       */
      const now = Date.now();

      if (
        now -
          lastSentAtRef.current <
        LOCATION_SEND_INTERVAL_MS
      ) {
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
       * Don't store extremely inaccurate
       * location readings.
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

      const currentTechnicianId =
        technicianIdRef.current;

      const currentTenantId =
        tenantIdRef.current;

      if (
        !currentTechnicianId ||
        !currentTenantId
      ) {
        return;
      }

      sendingRef.current = true;

      try {
        console.log(
          "[TechnicianAvailabilityLocation] Sending available technician location:",
          {
            technicianId:
              currentTechnicianId,
            latitude,
            longitude,
            accuracy,
          },
        );

        await sendTechnicianAvailabilityLocation(
          currentTenantId,
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
      if (
        !mountedRef.current ||
        !availableRef.current
      ) {
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

      setLocationStatus("active");

      /*
       * This works even when there is NO job.
       *
       * It uses:
       * POST /api/v1/gps/availability
       */
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
     * START GPS ONLY WHEN:
     *
     * enabled === true
     * AND technician has a valid ID
     * AND tenant has a valid ID
     * AND technicianStatus === "Available"
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
      "[TechnicianAvailabilityLocation] GPS watcher started - technician is Available",
    );

    return () => {
      mountedRef.current = false;

      if (
        watchIdRef.current !== null
      ) {
        navigator.geolocation.clearWatch(
          watchIdRef.current,
        );

        watchIdRef.current = null;

        console.log(
          "[TechnicianAvailabilityLocation] GPS watcher stopped",
        );
      }

      sendingRef.current = false;
    };
  }, [
    technicianId,
    tenantId,
    technicianStatus,
    enabled,
  ]);

  /*
   * No visible UI required.
   */
  return null;
};

export default TechnicianAvailabilityLocation;