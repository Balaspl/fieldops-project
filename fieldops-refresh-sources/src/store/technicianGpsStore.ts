import { create } from "zustand";
import {
  GPS_AVAILABILITY_MAX_ACCURACY_METERS,
} from "../services/geolocationService";

export const TECHNICIAN_GPS_MAX_AGE_MS = 120_000;

export interface TechnicianGpsFix {
  latitude: number;
  longitude: number;
  accuracy: number;
  timestamp: number;
}

export interface TechnicianGpsLocation {
  technicianId: string;
  tenantId: string;
  fix: TechnicianGpsFix;
}

interface TechnicianGpsState {
  location: TechnicianGpsLocation | null;
  setLocation: (location: TechnicianGpsLocation) => void;
}

export const isValidTechnicianGpsFix = (
  fix: TechnicianGpsFix,
  now = Date.now(),
): boolean => {
  const ageMs = now - fix.timestamp;

  return (
    Number.isFinite(fix.latitude) &&
    fix.latitude >= -90 &&
    fix.latitude <= 90 &&
    Number.isFinite(fix.longitude) &&
    fix.longitude >= -180 &&
    fix.longitude <= 180 &&
    Number.isFinite(fix.accuracy) &&
    fix.accuracy > 0 &&
    fix.accuracy <= GPS_AVAILABILITY_MAX_ACCURACY_METERS &&
    Number.isFinite(fix.timestamp) &&
    ageMs >= -30_000 &&
    ageMs <= TECHNICIAN_GPS_MAX_AGE_MS
  );
};

export const useTechnicianGpsStore =
  create<TechnicianGpsState>((set) => ({
    location: null,
    setLocation: (location) => set({ location }),
  }));

export const publishTechnicianGpsFix = (
  technicianId: string,
  tenantId: string,
  position: GeolocationPosition,
): boolean => {
  const fix: TechnicianGpsFix = {
    latitude: position.coords.latitude,
    longitude: position.coords.longitude,
    accuracy: position.coords.accuracy,
    timestamp: position.timestamp,
  };

  if (
    !technicianId ||
    !tenantId ||
    !isValidTechnicianGpsFix(fix)
  ) {
    return false;
  }

  const current = useTechnicianGpsStore.getState().location;
  if (
    current?.technicianId === technicianId &&
    current.tenantId === tenantId &&
    current.fix.timestamp > fix.timestamp
  ) {
    return false;
  }

  useTechnicianGpsStore.getState().setLocation({
    technicianId,
    tenantId,
    fix,
  });
  return true;
};
