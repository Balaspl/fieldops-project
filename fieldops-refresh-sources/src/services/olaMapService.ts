import api from './api';

export interface OlaRouteResponse {
  distance_meters: number;
  duration_seconds: number;
  duration_in_traffic_seconds: number;
  route_points: [number, number][]; // [lng, lat]
  provider: string;
  cached?: boolean;
  fallback?: boolean;
  route_calculated_at?: string;
}

export function isValidCoordinate(latitude: unknown, longitude: unknown): boolean {
  if (latitude === null || latitude === undefined || longitude === null || longitude === undefined) return false;
  if (typeof latitude === "string" && latitude.trim() === "") return false;
  if (typeof longitude === "string" && longitude.trim() === "") return false;
  const lat = Number(latitude);
  const lng = Number(longitude);
  return Number.isFinite(lat) && Number.isFinite(lng) &&
    lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180 &&
    !(lat === 0 && lng === 0);
}

export function isValidRouteResponse(value: unknown): value is OlaRouteResponse {
  if (!value || typeof value !== "object") return false;
  const route = value as Partial<OlaRouteResponse>;
  if (!Number.isFinite(route.distance_meters) || (route.distance_meters as number) < 0) return false;
  if (!Number.isFinite(route.duration_seconds) || (route.duration_seconds as number) < 0) return false;
  if (route.duration_in_traffic_seconds != null &&
      (!Number.isFinite(route.duration_in_traffic_seconds) || route.duration_in_traffic_seconds < 0)) return false;
  if (route.route_points != null) {
    if (!Array.isArray(route.route_points)) return false;
    if (!route.route_points.every((point) =>
      Array.isArray(point) && point.length >= 2 &&
      Number.isFinite(point[0]) && Number.isFinite(point[1]) &&
      point[0] >= -180 && point[0] <= 180 &&
      point[1] >= -90 && point[1] <= 90
    )) return false;
  }
  return true;
}

export function createLatestRequestTracker() {
  let latestRequestId = 0;
  return {
    next: () => ++latestRequestId,
    isLatest: (requestId: number) => requestId === latestRequestId,
    invalidate: () => ++latestRequestId,
  };
}

export async function getOlaRoute(params: {
  originLat: number;
  originLng: number;
  destinationLat: number;
  destinationLng: number;
}, signal?: AbortSignal): Promise<OlaRouteResponse> {
  if (!isValidCoordinate(params.originLat, params.originLng) ||
      !isValidCoordinate(params.destinationLat, params.destinationLng)) {
    throw new Error("Invalid route coordinates");
  }
  const response = await api.get<OlaRouteResponse>('/api/v1/gps/route', {
    params: {
      origin_lat: params.originLat,
      origin_lng: params.originLng,
      dest_lat: params.destinationLat,
      dest_lng: params.destinationLng,
    },
    signal,
  });
  if (!isValidRouteResponse(response.data)) {
    throw new Error("Invalid route response");
  }
  return response.data;
}
