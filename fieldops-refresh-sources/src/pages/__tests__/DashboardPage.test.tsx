import React from "react";
import { describe, expect, it, beforeEach, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import Dashboard from "../DashboardPage";

import {
  getDashboardStats,
  getJobs,
} from "../../services/planningService";

vi.mock("../../services/planningService", () => ({
  getDashboardStats: vi.fn(),
  getJobs: vi.fn(),
}));

vi.mock("../../components/notifications/NotificationBell", () => ({
  default: () => <div data-testid="notification-bell" />,
}));

vi.mock("../../components/ui/LoadingSpinner", () => ({
  default: ({ message }: { message: string }) => (
    <div data-testid="loading-spinner">{message}</div>
  ),
}));

vi.mock("../../components/ui/EmptyState", () => ({
  default: () => <div data-testid="empty-state" />,
}));

const mockedGetDashboardStats = vi.mocked(getDashboardStats);
const mockedGetJobs = vi.mocked(getJobs);

const dashboardStats = {
  jobs: {
    pending: 5,
    active: 10,
    in_progress: 8,
    completed: 20,
    cancelled: 3,
    total: 35,
  },
  technicians: {
    available: 6,
    busy: 3,
    break: 1,
    offline: 2,
  },
  categories: {
    hvac: 10,
    electrical: 8,
    plumbing: 7,
    mechanical: 5,
    other: 5,
  },
};

const renderDashboard = () =>
  render(
    <Dashboard
      onViewTab={vi.fn()}
      unreadCount={0}
      isBellAnimated={false}
      onOpenBellDrawer={vi.fn()}
    />
  );

describe("Dashboard KPI Cards - Task 7", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockedGetDashboardStats.mockResolvedValue({
      data: dashboardStats,
    } as any);

    mockedGetJobs.mockResolvedValue({
      data: [],
    } as any);
  });

  it("renders all KPI cards with authoritative API values", async () => {
    renderDashboard();

    expect(
      screen.getByTestId("loading-spinner")
    ).toBeTruthy();

    await waitFor(() => {
      expect(screen.getByText("TOTAL JOBS")).toBeTruthy();
    });

    expect(screen.getByText("ACTIVE JOBS")).toBeTruthy();
    expect(screen.getByText("IN PROGRESS")).toBeTruthy();
    expect(screen.getByText("COMPLETED")).toBeTruthy();
    expect(screen.getByText("UNASSIGNED")).toBeTruthy();
    expect(screen.getByText("Cancelled")).toBeTruthy();

    expect(screen.getByText("35")).toBeTruthy();
    expect(screen.getAllByText("10").length).toBeGreaterThan(0);
    expect(screen.getAllByText("8").length).toBeGreaterThan(0);
    expect(screen.getAllByText("20").length).toBeGreaterThan(0);
    expect(screen.getAllByText("5").length).toBeGreaterThan(0);
    expect(screen.getAllByText("3").length).toBeGreaterThan(0);
  });

  it("requests the default week time range", async () => {
    renderDashboard();

    await waitFor(() => {
      expect(mockedGetDashboardStats).toHaveBeenCalledWith("week");
    });

    expect(mockedGetJobs).toHaveBeenCalledTimes(1);
  });

  it("requests updated statistics when the time range changes", async () => {
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText("TOTAL JOBS")).toBeTruthy();
    });

    const timeRangeSelect = screen.getAllByDisplayValue("This Week")[0];

    fireEvent.change(timeRangeSelect, {
      target: { value: "month" },
    });

    await waitFor(() => {
      expect(mockedGetDashboardStats).toHaveBeenCalledWith("month");
    });
  });

  it("shows the loading state before KPI data is available", () => {
    mockedGetDashboardStats.mockImplementation(
      () => new Promise(() => {})
    );

    renderDashboard();

    expect(
      screen.getByTestId("loading-spinner").textContent
    ).toContain(
    "Assembling Operations Center Dashboard..."
    );
  });

  it("shows the dashboard error state when the API fails", async () => {
    mockedGetDashboardStats.mockRejectedValue(
      new Error("Dashboard API failure")
    );

    renderDashboard();

    await waitFor(() => {
      expect(
        screen.getByText("Failed to load dashboard data")
      ).toBeTruthy();
    });
  });

  it("handles zero KPI values without rendering invalid percentages", async () => {
    mockedGetDashboardStats.mockResolvedValue({
      data: {
        jobs: {
          pending: 0,
          active: 0,
          in_progress: 0,
          completed: 0,
          cancelled: 0,
          total: 0,
        },
        technicians: {
          available: 0,
          busy: 0,
          break: 0,
          offline: 0,
        },
        categories: {
          hvac: 0,
          electrical: 0,
          plumbing: 0,
          mechanical: 0,
          other: 0,
        },
      },
    } as any);

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText("TOTAL JOBS")).toBeTruthy();
    });

    expect(screen.getByText("UNASSIGNED")).toBeTruthy();

    expect(screen.queryByText(/NaN/)).toBeNull();
  });
});