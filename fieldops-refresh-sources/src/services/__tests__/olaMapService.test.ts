import { beforeEach, describe, expect, it, vi } from "vitest";
import api from "../api";
import {
  createLatestRequestTracker,
  getOlaRoute,
  isValidCoordinate,
  isValidRouteResponse,
} from "../olaMapService";

vi.mock("../api", () => ({ default: { get: vi.fn() } }));

const validRoute = {
  distance_meters: 4321,
  duration_seconds: 321,
  duration_in_traffic_seconds: 321,
  route_points: [[80.2101, 13.085], [80.2707, 13.0827]],
  provider: "ola_maps",
};

describe("Ola route request validation", () => {
  beforeEach(() => vi.clearAllMocks());

  it("accepts real coordinates while rejecting missing, invalid and 0,0 coordinates", () => {
    expect(isValidCoordinate(13.085, 80.2101)).toBe(true);
    expect(isValidCoordinate(0, 80.2)).toBe(true);
    expect(isValidCoordinate(null, 80.2)).toBe(false);
    expect(isValidCoordinate(undefined, 80.2)).toBe(false);
    expect(isValidCoordinate(Number.NaN, 80.2)).toBe(false);
    expect(isValidCoordinate(91, 80.2)).toBe(false);
    expect(isValidCoordinate(0, 0)).toBe(false);
  });

  it("uses the selected coordinates on the first route request", async () => {
    vi.mocked(api.get).mockResolvedValue({ data: validRoute });

    const route = await getOlaRoute({
      originLat: 13.085,
      originLng: 80.2101,
      destinationLat: 13.0827,
      destinationLng: 80.2707,
    });

    expect(api.get).toHaveBeenCalledTimes(1);
    expect(api.get).toHaveBeenCalledWith("/api/v1/gps/route", expect.objectContaining({
      params: {
        origin_lat: 13.085,
        origin_lng: 80.2101,
        dest_lat: 13.0827,
        dest_lng: 80.2707,
      },
    }));
    expect(route.distance_meters).toBe(4321);
  });

  it("does not send missing or zero-zero coordinate pairs", async () => {
    await expect(getOlaRoute({
      originLat: Number.NaN,
      originLng: 80.2101,
      destinationLat: 13.0827,
      destinationLng: 80.2707,
    })).rejects.toThrow("Invalid route coordinates");
    await expect(getOlaRoute({
      originLat: 0,
      originLng: 0,
      destinationLat: 13.0827,
      destinationLng: 80.2707,
    })).rejects.toThrow("Invalid route coordinates");
    expect(api.get).not.toHaveBeenCalled();
  });

  it("rejects invalid Ola measurements and route coordinates", () => {
    expect(isValidRouteResponse(validRoute)).toBe(true);
    expect(isValidRouteResponse({ ...validRoute, distance_meters: Number.NaN })).toBe(false);
    expect(isValidRouteResponse({ ...validRoute, distance_meters: -1 })).toBe(false);
    expect(isValidRouteResponse({ ...validRoute, duration_seconds: -1 })).toBe(false);
    expect(isValidRouteResponse({ ...validRoute, route_points: [[181, 13.085]] })).toBe(false);
  });

  it("passes cancellation through and rejects an invalid server response", async () => {
    const controller = new AbortController();
    vi.mocked(api.get).mockResolvedValueOnce({ data: validRoute });
    await getOlaRoute({ originLat: 13.085, originLng: 80.2101, destinationLat: 13.0827, destinationLng: 80.2707 }, controller.signal);
    expect(vi.mocked(api.get).mock.calls[0][1]?.signal).toBe(controller.signal);

    vi.mocked(api.get).mockResolvedValueOnce({ data: { ...validRoute, distance_meters: 50000, route_points: [[181, 0]] } });
    await expect(getOlaRoute({ originLat: 13.085, originLng: 80.2101, destinationLat: 13.0827, destinationLng: 80.2707 }))
      .rejects.toThrow("Invalid route response");
  });

  it("only allows the newest rapid-location request to update route state", () => {
    const tracker = createLatestRequestTracker();
    const oldRequest = tracker.next();
    const newRequest = tracker.next();

    expect(tracker.isLatest(oldRequest)).toBe(false);
    expect(tracker.isLatest(newRequest)).toBe(true);
  });
});
