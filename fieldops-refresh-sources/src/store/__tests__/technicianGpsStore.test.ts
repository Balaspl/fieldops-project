import { afterEach, describe, expect, it } from "vitest";
import {
  publishTechnicianGpsFix,
  useTechnicianGpsStore,
} from "../technicianGpsStore";

const position = (
  latitude: number,
  longitude: number,
  timestamp = Date.now(),
  accuracy = 10,
) =>
  ({
    timestamp,
    coords: { latitude, longitude, accuracy },
  }) as GeolocationPosition;

describe("technician GPS location store", () => {
  afterEach(() => {
    useTechnicianGpsStore.setState({ location: null });
  });

  it("accepts a valid fresh GPS fix", () => {
    expect(
      publishTechnicianGpsFix(
        "tech-1",
        "tenant-1",
        position(12.9716, 77.5946),
      ),
    ).toBe(true);

    expect(useTechnicianGpsStore.getState().location?.fix).toMatchObject({
      latitude: 12.9716,
      longitude: 77.5946,
    });
  });

  it("rejects invalid coordinates and stale GPS fixes", () => {
    expect(
      publishTechnicianGpsFix(
        "tech-1",
        "tenant-1",
        position(91, 77.5946),
      ),
    ).toBe(false);
    expect(
      publishTechnicianGpsFix(
        "tech-1",
        "tenant-1",
        position(12.9716, 77.5946, Date.now() - 121_000),
      ),
    ).toBe(false);
    expect(useTechnicianGpsStore.getState().location).toBeNull();
  });

  it("does not replace a newer GPS fix with an older one", () => {
    const timestamp = Date.now();
    publishTechnicianGpsFix(
      "tech-1",
      "tenant-1",
      position(12.9716, 77.5946, timestamp),
    );

    expect(
      publishTechnicianGpsFix(
        "tech-1",
        "tenant-1",
        position(12.9816, 77.5946, timestamp - 1),
      ),
    ).toBe(false);
    expect(
      useTechnicianGpsStore.getState().location?.fix.latitude,
    ).toBe(12.9716);
  });
});
