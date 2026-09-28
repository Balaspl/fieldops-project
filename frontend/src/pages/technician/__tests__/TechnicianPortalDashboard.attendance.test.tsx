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
} from "@testing-library/react";
import "@testing-library/jest-dom";

import TechnicianPortalDashboard from "../TechnicianPortalDashboard";

import {
  getTechnicianDashboard,
  getTechnicianJobs,
  updateTechnicianStatus,
} from "../../../services/technicianPortalService";

vi.mock("../../../services/technicianPortalService", () => ({
  getTechnicianDashboard: vi.fn(),
  getTechnicianJobs: vi.fn(),
  updateTechnicianStatus: vi.fn(),
}));

const mockedGetTechnicianDashboard = vi.mocked(
  getTechnicianDashboard,
);

const mockedGetTechnicianJobs = vi.mocked(
  getTechnicianJobs,
);

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

    mockedGetTechnicianJobs.mockResolvedValue({
      data: [],
    } as any);

    mockedUpdateTechnicianStatus.mockResolvedValue({
      data: {
        technician_status: "Busy",
      },
    } as any);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders the backend-authoritative attendance status", async () => {
    mockedGetTechnicianDashboard.mockResolvedValue({
      data: {
        ...dashboardResponse,
        technician_status: "Busy",
      },
    } as any);

    renderDashboard();

    await waitFor(() => {
      expect(
        screen.getByTestId(
          "technician-attendance-status",
        ),
      ).toHaveValue("Busy");
    });

    expect(
      mockedGetTechnicianDashboard,
    ).toHaveBeenCalledTimes(1);
  });

  it("maps backend snake_case attendance status to the UI label", async () => {
    mockedGetTechnicianDashboard.mockResolvedValue({
      data: {
        ...dashboardResponse,
        technician_status: "on_break",
      },
    } as any);

    renderDashboard();

    await waitFor(() => {
      expect(
        screen.getByTestId(
          "technician-attendance-status",
        ),
      ).toHaveValue("On Break");
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
        screen.getByTestId(
          "technician-attendance-status",
        ),
      ).toHaveValue("Available");
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

    const attendanceSelect =
      await screen.findByTestId(
        "technician-attendance-status",
      );

    expect(attendanceSelect).toHaveValue("Available");

    fireEvent.change(attendanceSelect, {
      target: {
        value: "Offline",
      },
    });

    // The UI must continue showing the last
    // backend-confirmed value until the request succeeds.
    expect(attendanceSelect).toHaveValue("Available");

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
      expect(attendanceSelect).toHaveValue(
        "Offline",
      );
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

    const attendanceSelect =
      await screen.findByTestId(
        "technician-attendance-status",
      );

    expect(attendanceSelect).toHaveValue(
      "Available",
    );

    fireEvent.change(attendanceSelect, {
      target: {
        value: "Busy",
      },
    });

    await waitFor(() => {
      expect(
        screen.getByRole("alert"),
      ).toHaveTextContent(
        "Unable to update attendance and availability. Please try again.",
      );
    });

    expect(attendanceSelect).toHaveValue(
      "Available",
    );
  });

  it("shows the unavailable state when the backend does not provide a valid attendance status", async () => {
    mockedGetTechnicianDashboard.mockResolvedValue({
      data: {
        ...dashboardResponse,
        technician_status: undefined,
      },
    } as any);

    renderDashboard();

    const attendanceSelect =
      await screen.findByTestId(
        "technician-attendance-status",
      );

    await waitFor(() => {
      expect(attendanceSelect).toHaveValue(
        "Not Available",
      );
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

    const attendanceSelect =
      await screen.findByTestId(
        "technician-attendance-status",
      );

    await waitFor(() => {
      expect(attendanceSelect).toHaveValue(
        "Not Available",
      );
    });

    expect(attendanceSelect).toBeDisabled();
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

    const attendanceSelect =
      await screen.findByTestId(
        "technician-attendance-status",
      );

    await waitFor(() => {
      expect(attendanceSelect).toHaveValue(
        "Available",
      );
    });

    expect(
      screen.getByText(
        /Current availability:\s*Available/i,
      ),
    ).toBeInTheDocument();

    const now = Date.now();

    vi.spyOn(Date, "now").mockReturnValue(
      now + 16000,
    );

    fireEvent.change(attendanceSelect, {
      target: {
        value: "Busy",
      },
    });

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
          technician_status: "Busy",
        },
      });
    });
  });
});