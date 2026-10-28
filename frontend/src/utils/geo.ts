export interface Coordinates {
  latitude: number;
  longitude: number;
}

export const parseCoordinates = (
  latitude: unknown,
  longitude: unknown,
): Coordinates | null => {
  if (
    latitude === null ||
    latitude === undefined ||
    longitude === null ||
    longitude === undefined ||
    (typeof latitude === "string" && latitude.trim() === "") ||
    (typeof longitude === "string" && longitude.trim() === "")
  ) {
    return null;
  }

  const parsedLatitude = Number(latitude);
  const parsedLongitude = Number(longitude);

  if (
    !Number.isFinite(parsedLatitude) ||
    parsedLatitude < -90 ||
    parsedLatitude > 90 ||
    !Number.isFinite(parsedLongitude) ||
    parsedLongitude < -180 ||
    parsedLongitude > 180
  ) {
    return null;
  }

  return {
    latitude: parsedLatitude,
    longitude: parsedLongitude,
  };
};

export const haversineDistanceKm = (
  from: Coordinates,
  to: Coordinates,
): number | null => {
  const validFrom = parseCoordinates(from.latitude, from.longitude);
  const validTo = parseCoordinates(to.latitude, to.longitude);

  if (!validFrom || !validTo) return null;

  const toRadians = (degrees: number) => (degrees * Math.PI) / 180;
  const latitudeDelta = toRadians(
    validTo.latitude - validFrom.latitude,
  );
  const longitudeDelta = toRadians(
    validTo.longitude - validFrom.longitude,
  );
  const haversine =
    Math.sin(latitudeDelta / 2) ** 2 +
    Math.cos(toRadians(validFrom.latitude)) *
      Math.cos(toRadians(validTo.latitude)) *
      Math.sin(longitudeDelta / 2) ** 2;
  const boundedHaversine = Math.min(1, Math.max(0, haversine));

  return (
    6371 *
    2 *
    Math.atan2(
      Math.sqrt(boundedHaversine),
      Math.sqrt(1 - boundedHaversine),
    )
  );
};
