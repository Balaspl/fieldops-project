import { afterEach, describe, expect, it, vi } from "vitest";
import {
  GeolocationAcquisitionError,
  getTechnicianLocation,
} from "../geolocationService";

const position = (accuracy = 30, timestamp = Date.now()) => ({
  timestamp,
  coords: {
    latitude: 37.5,
    longitude: -122.2,
    accuracy,
    altitude: null,
    altitudeAccuracy: null,
    heading: null,
    speed: null,
  },
}) as GeolocationPosition;

const installGeolocation = (value: Geolocation) => {
  Object.defineProperty(navigator, "geolocation", {
    configurable: true,
    value,
  });
};

describe("getTechnicianLocation", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    Object.defineProperty(navigator, "geolocation", {
      configurable: true,
      value: undefined,
    });
  });

  it("requests a fresh high-accuracy fix and accepts valid accuracy in meters", async () => {
    const getCurrentPosition = vi.fn((success: PositionCallback, _error: PositionErrorCallback, _options?: PositionOptions) => {
      success(position() as GeolocationPosition);
    });
    installGeolocation({ getCurrentPosition } as unknown as Geolocation);

    await expect(getTechnicianLocation()).resolves.toMatchObject({
      coords: { accuracy: 30 },
    });
    expect(getCurrentPosition).toHaveBeenCalledWith(
      expect.any(Function),
      expect.any(Function),
      { enableHighAccuracy: true, timeout: 30_000, maximumAge: 0 },
    );
  });

  it("uses one high-accuracy attempt when the first fix is too imprecise", async () => {
    const getCurrentPosition = vi.fn((success: PositionCallback, _error: PositionErrorCallback, _options?: PositionOptions) => {
      success(position(getCurrentPosition.mock.calls.length === 1 ? 250 : 20));
    });
    installGeolocation({ getCurrentPosition } as unknown as Geolocation);

    await expect(getTechnicianLocation()).resolves.toMatchObject({
      coords: { accuracy: 20 },
    });
    expect(getCurrentPosition).toHaveBeenCalledTimes(2);
    expect(getCurrentPosition.mock.calls[1][2]).toMatchObject({
      enableHighAccuracy: true,
      maximumAge: 0,
    });
  });

  it("retries a timed-out coarse request with high accuracy", async () => {
    const getCurrentPosition = vi.fn((success: PositionCallback, error: PositionErrorCallback) => {
      if (getCurrentPosition.mock.calls.length === 1) {
        error({ code: 3, message: "Timeout expired" } as GeolocationPositionError);
      } else {
        success(position());
      }
    });
    installGeolocation({ getCurrentPosition } as unknown as Geolocation);

    await expect(getTechnicianLocation()).resolves.toMatchObject({
      coords: { accuracy: 30 },
    });
    expect(getCurrentPosition).toHaveBeenCalledTimes(2);
  });

  it("does not retry a denied permission and returns an actionable message", async () => {
    const getCurrentPosition = vi.fn((_: PositionCallback, error: PositionErrorCallback) => {
      error({ code: 1, message: "Permission denied" } as GeolocationPositionError);
    });
    installGeolocation({ getCurrentPosition } as unknown as Geolocation);

    await expect(getTechnicianLocation()).rejects.toMatchObject({
      code: 1,
      message: expect.stringContaining("Allow location access"),
    });
    expect(getCurrentPosition).toHaveBeenCalledTimes(1);
  });

  it("retries poor accuracy once and rejects a still-poor fix", async () => {
    const getCurrentPosition = vi.fn((success: PositionCallback) => {
      success(position(140));
    });
    installGeolocation({ getCurrentPosition } as unknown as Geolocation);
    await expect(getTechnicianLocation({ maxAccuracyMeters: 100 })).rejects.toMatchObject({
      message: expect.stringContaining("too imprecise"),
    });
    expect(getCurrentPosition).toHaveBeenCalledTimes(2);
  });

  it.each([100, 119, 150])("accepts %s m accuracy with a configured 150 m limit", async (accuracy) => {
    const getCurrentPosition = vi.fn((success: PositionCallback) => success(position(accuracy)));
    installGeolocation({ getCurrentPosition } as unknown as Geolocation);
    await expect(getTechnicianLocation({ maxAccuracyMeters: 150 })).resolves.toMatchObject({
      coords: { accuracy },
    });
    expect(getCurrentPosition).toHaveBeenCalledTimes(1);
  });

  it("rejects accuracy above the configured 150 m limit", async () => {
    const getCurrentPosition = vi.fn((success: PositionCallback) => success(position(151)));
    installGeolocation({ getCurrentPosition } as unknown as Geolocation);
    await expect(getTechnicianLocation({ maxAccuracyMeters: 150 })).rejects.toMatchObject({
      reason: "poor_accuracy",
      message: expect.stringContaining("too imprecise"),
    });
  });

  it("rejects invalid coordinates and stale fixes", async () => {
    const invalid = position();
    Object.defineProperty(invalid.coords, "latitude", { value: 91 });
    const getCurrentPosition = vi.fn((success: PositionCallback) => success(invalid));
    installGeolocation({ getCurrentPosition } as unknown as Geolocation);
    await expect(getTechnicianLocation()).rejects.toMatchObject({ code: 2 });

    const stale = position(20, Date.now() - 60_000);
    getCurrentPosition.mockImplementation((success: PositionCallback) => success(stale));
    await expect(getTechnicianLocation()).rejects.toMatchObject({ code: 2 });
  });

  it("classifies a geolocation timeout separately", async () => {
    const getCurrentPosition = vi.fn((_: PositionCallback, error: PositionErrorCallback) => {
      error({ code: 3, message: "Timeout expired" } as GeolocationPositionError);
    });
    installGeolocation({ getCurrentPosition } as unknown as Geolocation);
    await expect(getTechnicianLocation()).rejects.toMatchObject({
      code: 3,
      message: expect.stringContaining("timed out"),
    });
  });

  it("rejects browsers without geolocation support", async () => {
    installGeolocation(undefined as unknown as Geolocation);
    await expect(getTechnicianLocation()).rejects.toBeInstanceOf(GeolocationAcquisitionError);
  });
});
