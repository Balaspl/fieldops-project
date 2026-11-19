export interface GeolocationFixOptions {
  timeoutMs?: number;
  maximumAgeMs?: number;
  maxAccuracyMeters?: number;
}

export class GeolocationAcquisitionError extends Error {
  readonly code: number | "unsupported";
  readonly reason?: "missing_location" | "invalid_coordinates" | "stale_location" | "poor_accuracy";

  constructor(code: number | "unsupported", message: string, reason?: GeolocationAcquisitionError["reason"]) {
    super(message);
    this.name = "GeolocationAcquisitionError";
    this.code = code;
    this.reason = reason;
  }
}

// Configure per deployment with VITE_GPS_AVAILABILITY_MAX_ACCURACY_METERS to
// match backend GPS_AVAILABILITY_MAX_ACCURACY_METERS. 150 m is a configurable value,
// not a replacement for downstream dispatch eligibility checks.
const configuredAccuracy = Number(import.meta.env.VITE_GPS_AVAILABILITY_MAX_ACCURACY_METERS);
export const GPS_AVAILABILITY_MAX_ACCURACY_METERS = Number.isFinite(configuredAccuracy) && configuredAccuracy > 0
  ? configuredAccuracy
  : 150;

const DEFAULT_OPTIONS: Required<GeolocationFixOptions> = {
  timeoutMs: 30_000,
  maximumAgeMs: 15_000,
  maxAccuracyMeters: GPS_AVAILABILITY_MAX_ACCURACY_METERS,
};

const errorMessage = (code: number): string => {
  switch (code) {
    case 1:
      return "Location permission is blocked. Allow location access in your browser settings, then retry.";
    case 2:
      return "Your device could not determine a location. Check location services and network access, then retry.";
    case 3:
      return "Location lookup timed out. Move near a window or enable device location services, then retry.";
    default:
      return "Unable to determine your location. Check location services and retry.";
  }
};

const validFix = (
  position: GeolocationPosition,
  maxAgeMs: number,
  maxAccuracyMeters: number,
): boolean => {
  const ageMs = Date.now() - position.timestamp;
  return (
    ageMs >= -30_000 &&
    ageMs <= maxAgeMs &&
    Number.isFinite(position.coords.latitude) &&
    position.coords.latitude >= -90 &&
    position.coords.latitude <= 90 &&
    Number.isFinite(position.coords.longitude) &&
    position.coords.longitude >= -180 &&
    position.coords.longitude <= 180 &&
    Number.isFinite(position.coords.accuracy) &&
    position.coords.accuracy > 0 &&
    position.coords.accuracy <= maxAccuracyMeters
  );
};

const invalidFixReason = (
  position: GeolocationPosition,
  maxAgeMs: number,
  maxAccuracyMeters: number,
): NonNullable<GeolocationAcquisitionError["reason"]> | null => {
  const { latitude, longitude, accuracy } = position.coords;
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return "missing_location";
  if (latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) return "invalid_coordinates";
  const ageMs = Date.now() - position.timestamp;
  if (ageMs < -30_000 || ageMs > maxAgeMs) return "stale_location";
  if (!Number.isFinite(accuracy) || accuracy <= 0 || accuracy > maxAccuracyMeters) return "poor_accuracy";
  return null;
};

const fixError = (reason: NonNullable<GeolocationAcquisitionError["reason"]>) => {
  const messages = {
    missing_location: "Your device did not provide coordinates. Check location services and retry.",
    invalid_coordinates: "Your device returned invalid coordinates. Check location services and retry.",
    stale_location: "The location fix is out of date. Request a fresh location and retry.",
    poor_accuracy: "Your location is too imprecise for dispatch. Move to an area with a clearer GPS signal and retry.",
  };
  return new GeolocationAcquisitionError(2, messages[reason], reason);
};

const acquire = (
  geolocation: Geolocation,
  enableHighAccuracy: boolean,
  timeout: number,
  maximumAge: number,
): Promise<GeolocationPosition> =>
  new Promise((resolve, reject) => {
    geolocation.getCurrentPosition(
      resolve,
      (error) => reject(new GeolocationAcquisitionError(error.code, errorMessage(error.code))),
      { enableHighAccuracy, timeout, maximumAge },
    );
  });

/** Get a fresh, sufficiently accurate GPS fix. Accuracy values are meters. */
export const getTechnicianLocation = async (
  options: GeolocationFixOptions = {},
): Promise<GeolocationPosition> => {
  const config = { ...DEFAULT_OPTIONS, ...options };
  if (typeof navigator === "undefined" || !navigator.geolocation) {
    throw new GeolocationAcquisitionError(
      "unsupported",
      "This browser does not support location services. Use a supported browser or device to go online.",
    );
  }

  let firstFix: GeolocationPosition | undefined;
  let firstError: GeolocationAcquisitionError | undefined;
  try {
    firstFix = await acquire(
      navigator.geolocation,
      true,
      config.timeoutMs,
      0,
    );
    const ageMs = Date.now() - firstFix.timestamp;
    const reason = invalidFixReason(firstFix, config.maximumAgeMs, config.maxAccuracyMeters);
    console.info("[technician-location] fix validation", {
      accuracyMeters: firstFix.coords.accuracy,
      coordinatesAvailable: Number.isFinite(firstFix.coords.latitude) && Number.isFinite(firstFix.coords.longitude),
      timestamp: new Date(firstFix.timestamp).toISOString(),
      ageMs,
      thresholdMeters: config.maxAccuracyMeters,
      rejectionReason: reason,
    });
    if (validFix(firstFix, config.maximumAgeMs, config.maxAccuracyMeters)) {
      return firstFix;
    }
  } catch (error) {
    firstError = error as GeolocationAcquisitionError;
    if (firstError.code === 1 || firstError.code === "unsupported") {
      throw firstError;
    }
  }

  // A coarse or unavailable fix gets one deliberate high-accuracy attempt.
  try {
    const preciseFix = await acquire(
      navigator.geolocation,
      true,
      config.timeoutMs,
      0,
    );
    if (validFix(preciseFix, config.maximumAgeMs, config.maxAccuracyMeters)) {
      return preciseFix;
    }
    throw fixError(invalidFixReason(preciseFix, config.maximumAgeMs, config.maxAccuracyMeters)!);
  } catch (error) {
    const acquisitionError = error as GeolocationAcquisitionError;
    if (firstFix && acquisitionError.code === 2) throw acquisitionError;
    throw acquisitionError || firstError;
  }
};
