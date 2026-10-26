import { afterEach, describe, expect, it, vi } from "vitest";
import { HEARTBEAT_INTERVAL_MS, startHeartbeatLoop, stopHeartbeatLoop } from "../heartbeatService";
import api from "../api";

vi.mock("../api", () => ({
  default: { post: vi.fn().mockResolvedValue({ status: 200, data: {} }) },
}));

describe("technician heartbeat cadence", () => {
  afterEach(() => {
    stopHeartbeatLoop();
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("leaves headroom after the backend heartbeat rate-limit TTL", () => {
    vi.useFakeTimers();
    startHeartbeatLoop("tech-17");
    expect(HEARTBEAT_INTERVAL_MS).toBe(35_000);
    expect(vi.getTimerCount()).toBe(1);
  });
});
