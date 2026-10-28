import { describe, expect, it } from "vitest";
import {
  haversineDistanceKm,
  parseCoordinates,
} from "../geo";

describe("geographic distance helpers", () => {
  it("calculates a straight-line distance in kilometers with Haversine", () => {
    const distance = haversineDistanceKm(
      { latitude: 12.9716, longitude: 77.5946 },
      { latitude: 12.9816, longitude: 77.5946 },
    );

    expect(distance).toBeCloseTo(1.112, 2);
  });

  it("returns no coordinates when either customer coordinate is missing", () => {
    expect(parseCoordinates(null, 77.5946)).toBeNull();
    expect(parseCoordinates(12.9716, "")).toBeNull();
  });

  it("rejects coordinates outside valid latitude and longitude ranges", () => {
    expect(parseCoordinates(91, 77.5946)).toBeNull();
    expect(parseCoordinates(12.9716, -181)).toBeNull();
    expect(
      haversineDistanceKm(
        { latitude: 12.9716, longitude: 77.5946 },
        { latitude: 91, longitude: 77.5946 },
      ),
    ).toBeNull();
  });
});
