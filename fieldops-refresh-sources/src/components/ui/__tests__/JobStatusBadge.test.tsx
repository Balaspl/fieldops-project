import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import React from "react";
import JobStatusBadge, { STATUS_CONFIG } from "../JobStatusBadge";
import { useThemeStore } from "../../../store/themeStore";

describe("JobStatusBadge Component", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useThemeStore.getState().setDarkMode(false);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  describe("Status Rendering & Configuration", () => {
    const statuses = [
      "CREATED",
      "ASSIGNED",
      "EN_ROUTE",
      "ON_SITE",
      "COMPLETED",
      "CANCELLED",
      "CLOSED",
    ] as const;

    statuses.forEach((status) => {
      it(`renders status label correctly for: ${status}`, () => {
        render(<JobStatusBadge status={status} />);
        const label = STATUS_CONFIG[status].label;
        expect(screen.getByText(label)).toBeDefined();
      });

      it(`maps correct icon and attributes for: ${status}`, () => {
        render(<JobStatusBadge status={status} />);
        const icon = screen.getByTestId("status-badge-icon");
        expect(icon).toBeDefined();
      });
    });
  });

  describe("Active Status Pulse Indicators", () => {
    const activeStatuses = ["ASSIGNED", "EN_ROUTE", "ON_SITE"] as const;
    const inactiveStatuses = ["CREATED", "COMPLETED", "CANCELLED", "CLOSED"] as const;

    activeStatuses.forEach((status) => {
      it(`renders pulsing dot for active status: ${status}`, () => {
        render(<JobStatusBadge status={status} />);
        const dot = screen.getByTestId("status-pulse-dot");
        expect(dot).toBeDefined();
        expect(dot.className).toContain("animate-pulse");
      });
    });

    inactiveStatuses.forEach((status) => {
      it(`does NOT render pulsing dot for inactive status: ${status}`, () => {
        render(<JobStatusBadge status={status} />);
        expect(screen.queryByTestId("status-pulse-dot")).toBeNull();
      });
    });
  });

  describe("Size Variants & Classes", () => {
    it("renders small size classes correctly", () => {
      render(<JobStatusBadge status="CREATED" size="sm" />);
      const badge = screen.getByTestId("job-status-badge");
      expect(badge.className).toContain("text-[10px]");
      expect(badge.className).toContain("px-2");
      expect(badge.className).toContain("py-0.5");
    });

    it("renders medium (default) size classes correctly", () => {
      render(<JobStatusBadge status="CREATED" size="md" />);
      const badge = screen.getByTestId("job-status-badge");
      expect(badge.className).toContain("text-xs");
      expect(badge.className).toContain("px-2.5");
      expect(badge.className).toContain("py-1");
    });

    it("renders large size classes correctly", () => {
      render(<JobStatusBadge status="CREATED" size="lg" />);
      const badge = screen.getByTestId("job-status-badge");
      expect(badge.className).toContain("text-sm");
      expect(badge.className).toContain("px-3");
      expect(badge.className).toContain("py-1.5");
    });
  });

  describe("Shape/Shape Variants", () => {
    it("renders pill shape class (rounded-full)", () => {
      render(<JobStatusBadge status="CREATED" variant="pill" />);
      const badge = screen.getByTestId("job-status-badge");
      expect(badge.className).toContain("rounded-full");
    });

    it("renders rounded-square shape class (rounded-md)", () => {
      render(<JobStatusBadge status="CREATED" variant="rounded-square" />);
      const badge = screen.getByTestId("job-status-badge");
      expect(badge.className).toContain("rounded-md");
    });
  });

  describe("Interactive Tooltip & Hover Delay", () => {
    it("displays tooltip only after 200ms hover delay", () => {
      render(<JobStatusBadge status="CREATED" />);
      const badge = screen.getByTestId("job-status-badge");

      // Before mouse enter, tooltip is hidden
      expect(screen.queryByTestId("status-tooltip")).toBeNull();

      // Trigger hover
      fireEvent.mouseEnter(badge);

      // Immediately after hover, tooltip should still be hidden (delay has not elapsed)
      expect(screen.queryByTestId("status-tooltip")).toBeNull();

      // Advance timer by 190ms
      act(() => {
        vi.advanceTimersByTime(190);
      });
      expect(screen.queryByTestId("status-tooltip")).toBeNull();

      // Advance remaining 10ms to hit 200ms
      act(() => {
        vi.advanceTimersByTime(10);
      });
      
      const tooltip = screen.getByTestId("status-tooltip");
      expect(tooltip).toBeDefined();
      expect(screen.getByText(STATUS_CONFIG.CREATED.description)).toBeDefined();

      // Mouse leaves, tooltip should hide immediately
      fireEvent.mouseLeave(badge);
      expect(screen.queryByTestId("status-tooltip")).toBeNull();
    });
  });

  describe("Dark Mode Adaptation", () => {
    it("applies dark mode classes when Zustand store toggles theme", () => {
      const { rerender } = render(<JobStatusBadge status="ASSIGNED" />);
      let badge = screen.getByTestId("job-status-badge");
      expect(badge.className.split(" ")).not.toContain("dark");

      // Set store theme to dark
      act(() => {
        useThemeStore.getState().setDarkMode(true);
      });

      // Rerender component to receive context updates
      rerender(<JobStatusBadge status="ASSIGNED" />);
      badge = screen.getByTestId("job-status-badge");
      expect(badge.className.split(" ")).toContain("dark");
    });
  });
});
