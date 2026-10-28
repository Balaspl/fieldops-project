import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  formatAcceptanceCountdown,
  getRemainingAcceptanceSeconds,
  useAcceptanceCountdowns,
} from "../useAcceptanceCountdown";

describe("useAcceptanceCountdown", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-28T08:00:00.000Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("calculates a deadline from assigned_at and formats a padded countdown", () => {
    expect(
      getRemainingAcceptanceSeconds(
        {
          id: 1,
          status: "ASSIGNED",
          assigned_at: "2026-10-28T07:58:00.000Z",
        },
        Date.now(),
      ),
    ).toBe(180);
    expect(formatAcceptanceCountdown(272)).toBe("04:32");
  });

  it("uses an explicit deadline when available and hides timers for ineligible jobs", () => {
    expect(
      getRemainingAcceptanceSeconds(
        {
          id: 1,
          status: "AWAITING_ACCEPTANCE",
          assigned_at: "2026-10-28T07:55:00.000Z",
          acceptance_expires_at: "2026-10-28T08:02:00.000Z",
        },
        Date.now(),
      ),
    ).toBe(120);
    expect(
      getRemainingAcceptanceSeconds({
        id: 2,
        status: "REJECTED_BY_TECHNICIAN",
        assigned_at: "2026-10-28T07:59:00.000Z",
      }),
    ).toBeNull();
    expect(
      getRemainingAcceptanceSeconds({
        id: 3,
        status: "PENDING",
      }),
    ).toBeNull();
  });

  it("updates multiple absolute deadlines without restarting on refresh and cleans up", () => {
    const jobs = [
      {
        id: 11,
        status: "ASSIGNED",
        assigned_at: "2026-10-28T07:59:00.000Z",
      },
      {
        id: 12,
        status: "AWAITING_ACCEPTANCE",
        assigned_at: "2026-10-28T07:58:00.000Z",
      },
    ];
    const { result, rerender, unmount } = renderHook(
      ({ currentJobs }) => useAcceptanceCountdowns(currentJobs),
      { initialProps: { currentJobs: jobs } },
    );

    expect(result.current).toEqual({ "11": 240, "12": 180 });
    expect(vi.getTimerCount()).toBe(1);

    rerender({ currentJobs: jobs.map((job) => ({ ...job })) });
    expect(vi.getTimerCount()).toBe(1);

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current).toEqual({ "11": 239, "12": 179 });

    rerender({
      currentJobs: jobs.map((job) => ({ ...job, status: "ACCEPTED" })),
    });
    expect(result.current).toEqual({ "11": null, "12": null });
    expect(vi.getTimerCount()).toBe(0);

    unmount();
  });

  it("keeps an expired pending job at zero without assigning or extending it", () => {
    const job = {
      id: 21,
      status: "PENDING",
      assigned_at: "2026-10-28T07:55:00.000Z",
    };
    const { result } = renderHook(() => useAcceptanceCountdowns([job]));

    expect(result.current["21"]).toBe(0);
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(result.current["21"]).toBe(0);
  });
});
