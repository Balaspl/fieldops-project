import React from "react";
import {
  describe,
  expect,
  it,
  beforeEach,
  afterEach,
  vi,
} from "vitest";
import {
  render,
  screen,
  waitFor,
  fireEvent,
  act,
  within,
} from "@testing-library/react";
import "@testing-library/jest-dom";

import TechnicianPortalDashboard from "../TechnicianPortalDashboard";
import useAuthStore from "../../../store/authStore";
import * as geolocationService from "../../../services/geolocationService";
import * as gpsService from "../../../services/gpsService";

import {
  acceptTechnicianJob,
  getTechnicianDashboard,
  getTechnicianPerformanceReport,
  getTechnicianJobs,
  rejectTechnicianJob,
  updateTechnicianStatus,
} from "../../../services/technicianPortalService";

vi.mock("../../../services/technicianPortalService", () => ({
  acceptTechnicianJob: vi.fn(),
  getTechnicianDashboard: vi.fn(),
  getTechnicianPerformanceReport: vi.fn(),
  getTechnicianJobs: vi.fn(),
  rejectTechnicianJob: vi.fn(),
  updateTechnicianStatus: vi.fn(),
}));

const mockedAcceptTechnicianJob = vi.mocked(acceptTechnicianJob);

const mockedGetTechnicianDashboard = vi.mocked(
  getTechnicianDashboard,
);

const mockedGetTechnicianPerformanceReport = vi.mocked(
  getTechnicianPerformanceReport,
);

const mockedGetTechnicianJobs = vi.mocked(
  getTechnicianJobs,
);

const mockedRejectTechnicianJob = vi.mocked(rejectTechnicianJob);

const mockedUpdateTechnicianStatus = vi.mocked(
  updateTechnicianStatus,
);

const renderDashboard = () =>
  render(
    <TechnicianPortalDashboard
      onNavigate={vi.fn()}
    />,
  );

const dashboardResponse = {
  profile_completed: true,
  technician_status: "Available",
  active_jobs: 2,
  pending_acceptance: 1,
  rejected_jobs: 0,
  total_completed: 8,
};

describe("TechnicianPortalDashboard - Technician Attendance and Availability", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    vi.stubGlobal(
      "setInterval",
      vi.fn(() => 1),
    );

    vi.stubGlobal(
      "clearInterval",
      vi.fn(),
    );

    mockedGetTechnicianDashboard.mockResolvedValue({
      data: dashboardResponse,
    } as any);
    mockedGetTechnicianPerformanceReport.mockResolvedValue({
      data: {
        performance_period: "week",
        period_completed_jobs: 0,
        completion_trend: [],
        status_distribution: [],
      },
    } as any);

    mockedGetTechnicianJobs.mockResolvedValue({
      data: [],
    } as any);

    mockedAcceptTechnicianJob.mockResolvedValue({ data: {} } as any);
    mockedRejectTechnicianJob.mockResolvedValue({ data: {} } as any);

    mockedUpdateTechnicianStatus.mockResolvedValue({
      data: {
        technician_status: "Busy",
      },
    } as any);
  });

  afterEach(() => {
    useAuthStore.setState({ user: null });
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("goes online only after fresh location is stored, then reflects backend status", async () => {
    useAuthStore.setState({ user: { tenant_id: "tenant-1" } as any });
    const position = {
      timestamp: Date.now(),
      coords: { latitude: 37.5, longitude: -122.2, accuracy: 25 },
    } as GeolocationPosition;
    const getLocation = vi.spyOn(geolocationService, "getTechnicianLocation").mockResolvedValue(position);
    const sendLocation = vi.spyOn(gpsService, "sendTechnicianAvailabilityLocation").mockResolvedValue({} as any);
    mockedGetTechnicianDashboard.mockResolvedValue({ data: { ...dashboardResponse, technician_status: "Offline" } } as any);
    mockedUpdateTechnicianStatus.mockResolvedValue({ data: { technician_status: "Available" } } as any);

    renderDashboard();
    fireEvent.click(await screen.findByRole("button", { name: "Go Online" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Go Offline" })).toBeInTheDocument());
    expect(getLocation).toHaveBeenCalledWith(expect.objectContaining({ maxAccuracyMeters: 150 }));
    expect(sendLocation).toHaveBeenCalledWith("tenant-1", expect.objectContaining({
      latitude: 37.5, longitude: -122.2, accuracy: 25,
    }));
    expect(mockedUpdateTechnicianStatus).toHaveBeenCalledWith("Available");
  });

  it("allows retry after location submission failure without going online", async () => {
    useAuthStore.setState({ user: { tenant_id: "tenant-1" } as any });
    vi.spyOn(geolocationService, "getTechnicianLocation").mockResolvedValue({
      timestamp: Date.now(), coords: { latitude: 37.5, longitude: -122.2, accuracy: 25 },
    } as GeolocationPosition);
    const sendLocation = vi.spyOn(gpsService, "sendTechnicianAvailabilityLocation")
      .mockRejectedValueOnce({ response: { data: { detail: "GPS unavailable" } } })
      .mockResolvedValueOnce({} as any);
    mockedGetTechnicianDashboard.mockResolvedValue({ data: { ...dashboardResponse, technician_status: "Offline" } } as any);
    mockedUpdateTechnicianStatus.mockResolvedValue({ data: { technician_status: "Available" } } as any);

    renderDashboard();
    fireEvent.click(await screen.findByRole("button", { name: "Go Online" }));
    await screen.findByRole("alert");
    expect(mockedUpdateTechnicianStatus).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Go Offline" })).toBeInTheDocument());
    expect(sendLocation).toHaveBeenCalledTimes(2);
    expect(mockedUpdateTechnicianStatus).toHaveBeenCalledWith("Available");
  });

  it("renders the backend-authoritative availability control", async () => {
    mockedGetTechnicianDashboard.mockResolvedValue({
      data: {
        ...dashboardResponse,
        technician_status: "Offline",
      },
    } as any);

    renderDashboard();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Go Online" }),
      ).toBeInTheDocument();
    });

    expect(
      mockedGetTechnicianDashboard,
    ).toHaveBeenCalledTimes(1);
  });

  it("renders the rejected jobs count from the dashboard response", async () => {
    mockedGetTechnicianDashboard.mockResolvedValue({
      data: { ...dashboardResponse, rejected_jobs: 23 },
    } as any);

    renderDashboard();

    expect(await screen.findByText("Rejected Jobs")).toBeInTheDocument();
    expect(screen.getByText("23")).toBeInTheDocument();
  });

  it("shows absolute acceptance countdowns for each eligible dashboard job immediately", async () => {
    const now = Date.now();
    mockedGetTechnicianJobs.mockResolvedValue({
      data: [
        {
          id: 81,
          status: "ASSIGNED",
          service_type: "Electrical",
          assigned_at: new Date(now).toISOString(),
        },
        {
          id: 82,
          status: "PENDING",
          service_type: "Plumbing",
          assigned_at: new Date(now - 120_000).toISOString(),
        },
        {
          id: 83,
          status: "ASSIGNED",
          assigned_at: new Date(now - 360_000).toISOString(),
        },
        {
          id: 84,
          status: "REJECTED_BY_TECHNICIAN",
          assigned_at: new Date(now).toISOString(),
        },
      ],
    } as any);

    renderDashboard();

    const countdowns = await screen.findAllByTestId(
      "dashboard-acceptance-countdown",
    );
    const countdownFor = (jobId: number) =>
      countdowns.filter(
        (element) => element.getAttribute("data-job-id") === String(jobId),
      );
    expect(countdownFor(81).length).toBeGreaterThan(0);
    expect(countdownFor(81)[0]).toHaveTextContent(
      /^Time left to accept: 04:5\d$/,
    );
    expect(countdownFor(82)[0]).toHaveTextContent(
      /^Time left to accept: 02:5\d$/,
    );
    expect(countdownFor(83)[0]).toHaveTextContent(
      "Acceptance deadline reached",
    );
    expect(countdownFor(84)).toHaveLength(0);
  });

  it("opens the assignment popup as soon as the dashboard loads an offered job", async () => {
    mockedGetTechnicianJobs.mockResolvedValue({
      data: [
        {
          id: 186,
          status: "ASSIGNED",
          service_type: "Electrical",
          customer_name: "Dashboard Customer",
          assigned_at: new Date().toISOString(),
        },
      ],
    } as any);

    renderDashboard();

    expect(
      await screen.findByRole("dialog", { name: "Job Assigned" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Job ID: #186")).toBeInTheDocument();
    expect(
      within(
        screen.getByRole("dialog", { name: "Job Assigned" }),
      ).getByTestId("assignment-countdown"),
    ).toHaveTextContent(/^\d{2}:\d{2}$/);
    expect(mockedGetTechnicianJobs).toHaveBeenCalledTimes(1);
  });

  it("accepts a dashboard assignment through the existing API and closes the popup", async () => {
    mockedGetTechnicianJobs
      .mockResolvedValueOnce({
        data: [
          {
            id: 187,
            status: "ASSIGNED",
            assigned_at: new Date().toISOString(),
          },
        ],
      } as any)
      .mockResolvedValueOnce({ data: [] } as any);

    renderDashboard();
    const popup = await screen.findByRole("dialog", {
      name: "Job Assigned",
    });
    fireEvent.click(
      within(popup).getByRole("button", { name: "Accept Job" }),
    );

    await waitFor(() => {
      expect(mockedAcceptTechnicianJob).toHaveBeenCalledWith(187);
      expect(
        screen.queryByRole("dialog", { name: "Job Assigned" }),
      ).not.toBeInTheDocument();
    });
  });

  it("uses the existing rejection confirmation and API from the dashboard popup", async () => {
    mockedGetTechnicianJobs
      .mockResolvedValueOnce({
        data: [
          {
            id: 188,
            status: "ASSIGNED",
            assigned_at: new Date().toISOString(),
          },
        ],
      } as any)
      .mockResolvedValueOnce({ data: [] } as any);

    renderDashboard();
    const popup = await screen.findByRole("dialog", {
      name: "Job Assigned",
    });
    fireEvent.click(within(popup).getByRole("button", { name: "Reject" }));

    fireEvent.change(
      within(popup).getByLabelText("Why are you rejecting this job?"),
      { target: { value: "No availability for this scheduled service." } },
    );
    fireEvent.click(
      within(popup).getByRole("button", { name: "Confirm Reject" }),
    );

    await waitFor(() => {
      expect(mockedRejectTechnicianJob).toHaveBeenCalledWith(
        188,
        "No availability for this scheduled service.",
      );
      expect(
        screen.queryByRole("dialog", { name: "Job Assigned" }),
      ).not.toBeInTheDocument();
    });
  });

  it("restores Online from the backend after loading", async () => {
    mockedGetTechnicianDashboard.mockResolvedValue({
      data: {
        ...dashboardResponse,
        technician_status: "Available",
      },
    } as any);

    renderDashboard();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Go Offline" }),
      ).toBeInTheDocument();
    });
  });

  it("renders the current availability and last sync information", async () => {
    mockedGetTechnicianDashboard.mockResolvedValue({
      data: {
        ...dashboardResponse,
        technician_status: "Available",
      },
    } as any);

    renderDashboard();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Go Offline" }),
      ).toBeInTheDocument();
    });

    expect(
      screen.getByText(
        /Current availability:\s*Available/i,
      ),
    ).toBeInTheDocument();

    expect(
      screen.getByText(/Last synced/i),
    ).toBeInTheDocument();
  });

  it("does not optimistically change attendance before backend confirmation", async () => {
    let resolveUpdate:
      | ((
          value: {
            data: {
              technician_status: string;
            };
          },
        ) => void)
      | undefined;

    mockedGetTechnicianDashboard.mockResolvedValue({
      data: {
        ...dashboardResponse,
        technician_status: "Available",
      },
    } as any);

    mockedUpdateTechnicianStatus.mockImplementation(
      () =>
        new Promise<any>((resolve) => {
          resolveUpdate = resolve;
        }),
    );

    renderDashboard();

    const availabilityButton = await screen.findByRole("button", { name: "Go Offline" });
    fireEvent.click(availabilityButton);

    // The UI must continue showing the last
    // backend-confirmed value until the request succeeds.
    expect(availabilityButton).toHaveAccessibleName("Go Offline");

    expect(
      mockedUpdateTechnicianStatus,
    ).toHaveBeenCalledWith("Offline");

    expect(resolveUpdate).toBeDefined();

    await act(async () => {
      resolveUpdate?.({
        data: {
          technician_status: "Offline",
        },
      });
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Go Online" })).toBeInTheDocument();
    });
  });

  it("shows an error and keeps the previous backend status when attendance update fails", async () => {
    mockedGetTechnicianDashboard.mockResolvedValue({
      data: {
        ...dashboardResponse,
        technician_status: "Available",
      },
    } as any);

    mockedUpdateTechnicianStatus.mockRejectedValue(
      new Error("Attendance update failed"),
    );

    renderDashboard();

    const availabilityButton = await screen.findByRole("button", { name: "Go Offline" });
    fireEvent.click(availabilityButton);

    await waitFor(() => {
      expect(
        screen.getByRole("alert"),
      ).toHaveTextContent(
        "Unable to update your availability. Please check your connection and try again.",
      );
    });

    expect(availabilityButton).toHaveAccessibleName("Go Offline");
  });

  it("shows the unavailable state when the backend does not provide a valid attendance status", async () => {
    mockedGetTechnicianDashboard.mockResolvedValue({
      data: {
        ...dashboardResponse,
        technician_status: undefined,
      },
    } as any);

    renderDashboard();

    const availabilityButton = await screen.findByTestId("technician-availability-toggle");

    await waitFor(() => {
      expect(availabilityButton).toHaveAccessibleName("Go Online");
    });

    expect(
      screen.getByRole("alert"),
    ).toHaveTextContent(
      "Attendance and availability status is currently unavailable.",
    );
  });

  it("disables attendance editing until the technician profile is complete", async () => {
    mockedGetTechnicianDashboard.mockResolvedValue({
      data: {
        ...dashboardResponse,
        profile_completed: false,
        technician_status: "Available",
      },
    } as any);

    renderDashboard();

    const availabilityButton = await screen.findByTestId("technician-availability-toggle");

    await waitFor(() => {
      expect(availabilityButton).toBeDisabled();
    });

  });

  it("shows the loading state before attendance and availability data is available", () => {
    mockedGetTechnicianDashboard.mockImplementation(
      () => new Promise(() => {}),
    );

    mockedGetTechnicianJobs.mockImplementation(
      () => new Promise(() => {}),
    );

    renderDashboard();

    expect(
      screen.getByText("Loading dashboard..."),
    ).toBeInTheDocument();
  });

  it("shows the availability error when the backend request fails", async () => {
    mockedGetTechnicianDashboard.mockRejectedValue(
      new Error("Dashboard request failed"),
    );

    renderDashboard();

    await waitFor(() => {
      expect(
        screen.getByRole("alert"),
      ).toHaveTextContent(
        "Unable to load your attendance and availability status.",
      );
    });
  });

  it("does not expose backend permission details when availability loading fails", async () => {
    mockedGetTechnicianDashboard.mockRejectedValue({
      response: {
        status: 403,
        data: {
          detail: "FORBIDDEN_INTERNAL_PERMISSION_DATA",
        },
      },
    });

    renderDashboard();

    await waitFor(() => {
      expect(
        screen.getByRole("alert"),
      ).toHaveTextContent(
        "Unable to load your attendance and availability status.",
      );
    });

    expect(
      screen.queryByText(
        "FORBIDDEN_INTERNAL_PERMISSION_DATA",
      ),
    ).not.toBeInTheDocument();
  });

  it("shows the stale availability state after the last successful sync becomes old", async () => {
    let resolveUpdate:
      | ((
          value: {
            data: {
              technician_status: string;
            };
          },
        ) => void)
      | undefined;

    mockedGetTechnicianDashboard.mockResolvedValue({
      data: {
        ...dashboardResponse,
        technician_status: "Available",
      },
    } as any);

    mockedUpdateTechnicianStatus.mockImplementation(
      () =>
        new Promise<any>((resolve) => {
          resolveUpdate = resolve;
        }),
    );

    renderDashboard();

    const availabilityButton = await screen.findByRole("button", { name: "Go Offline" });

    expect(
      screen.getByText(
        /Current availability:\s*Available/i,
      ),
    ).toBeInTheDocument();

    const now = Date.now();

    vi.spyOn(Date, "now").mockReturnValue(
      now + 16000,
    );

    fireEvent.click(availabilityButton);

    await waitFor(() => {
      expect(
        screen.getByText(
          /Availability data is stale/i,
        ),
      ).toBeInTheDocument();
    });

    await act(async () => {
      resolveUpdate?.({
        data: {
          technician_status: "Offline",
        },
      });
    });
  });

  it("replaces live location with the selectable performance report", async () => {
    renderDashboard();

    expect(await screen.findByRole("heading", { name: "Performance Report" })).toBeInTheDocument();
    expect(screen.queryByText(/Live Location & Route/i)).not.toBeInTheDocument();
    expect(mockedGetTechnicianPerformanceReport).toHaveBeenCalledWith("week");

    fireEvent.change(
      screen.getByRole("combobox", { name: "Performance report period" }),
      { target: { value: "month" } },
    );

    await waitFor(() => {
      expect(mockedGetTechnicianPerformanceReport).toHaveBeenLastCalledWith("month");
    });
  });
});
