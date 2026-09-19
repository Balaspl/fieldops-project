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
  cleanup,
} from "@testing-library/react";

import PlanningPage from "../PlanningPage";

import {
  getTechnicians,
  getAvailableTechnicians,
  getPendingJobs,
  getPlannedAssignments,
  assignJobsBulk,
  cancelJobsBulk,
} from "../../services/planningService";

/* -------------------------------------------------------------------------- */
/*                               Service Mocks                                */
/* -------------------------------------------------------------------------- */

vi.mock("../../services/planningService", () => ({
  getTechnicians: vi.fn(),
  getAvailableTechnicians: vi.fn(),
  getPendingJobs: vi.fn(),
  getPlannedAssignments: vi.fn(),
  assignJob: vi.fn(),
  assignJobsBulk: vi.fn(),
  cancelJobsBulk: vi.fn(),
  manualAssign: vi.fn(),
  getOverrideHistory: vi.fn(),
  getJobPlan: vi.fn(),
  getAuditOverrides: vi.fn(),
  assignJobDirect: vi.fn(),
}));

vi.mock("../../services/dispatchQueueService", () => ({
  getDispatchQueue: vi.fn().mockResolvedValue({
    data: [],
  }),
}));

vi.mock("../../services/escalationService", () => ({
  extendSLA: vi.fn(),
  cancelEscalatedJob: vi.fn(),
  forceAssignEscalation: vi.fn(),
}));

vi.mock("../../services/customerPortalService", () => ({
  getDeclinedJobs: vi.fn().mockResolvedValue({
    data: [],
  }),
  reassignDeclinedJob: vi.fn(),
}));

/* -------------------------------------------------------------------------- */
/*                              Component Mocks                               */
/* -------------------------------------------------------------------------- */

vi.mock("../../components/ui/LoadingSpinner", () => ({
  default: ({ message }: { message: string }) => (
    <div data-testid="loading-spinner">{message}</div>
  ),
}));

vi.mock("../../components/ui/EmptyState", () => ({
  default: () => <div data-testid="empty-state">No jobs</div>,
}));

vi.mock("../../components/notifications/NotificationBell", () => ({
  default: () => <div data-testid="notification-bell" />,
}));

vi.mock("../../components/notifications/OverrideModal", () => ({
  default: () => null,
}));

vi.mock("../../components/notifications/OverrideHistory", () => ({
  default: () => null,
}));

vi.mock("../../components/notifications/OverrideWarning", () => ({
  default: () => null,
}));

vi.mock("../../components/dispatch/MetricsCards", () => ({
  default: () => <div data-testid="metrics-cards" />,
}));

vi.mock("../../components/dispatch/DispatchQueueTable", () => ({
  default: () => <div data-testid="dispatch-queue-table" />,
}));

vi.mock("../../components/assignment/ScoreDisplay", () => ({
  CompactScorePanel: () => (
    <div data-testid="compact-score-panel" />
  ),
}));

vi.mock("../../components/assignment/RankedTechTable", () => ({
  default: () => <div data-testid="ranked-tech-table" />,
}));

vi.mock("../../components/assignment/TopThreeHighlight", () => ({
  default: () => <div data-testid="top-three-highlight" />,
}));

vi.mock("../../components/notifications/ReDispatchHistory", () => ({
  default: () => <div data-testid="redispatch-history" />,
}));

vi.mock("../../components/notifications/AlertBanner", () => ({
  default: () => <div data-testid="alert-banner" />,
}));

/* -------------------------------------------------------------------------- */
/*                              Mocked Services                               */
/* -------------------------------------------------------------------------- */

const mockedGetTechnicians = vi.mocked(getTechnicians);
const mockedGetAvailableTechnicians = vi.mocked(getAvailableTechnicians);
const mockedGetPendingJobs = vi.mocked(getPendingJobs);
const mockedGetPlannedAssignments = vi.mocked(getPlannedAssignments);
const mockedAssignJobsBulk = vi.mocked(assignJobsBulk);
const mockedCancelJobsBulk = vi.mocked(cancelJobsBulk);

/* -------------------------------------------------------------------------- */
/*                                  Test Data                                 */
/* -------------------------------------------------------------------------- */

const pendingJobs = [
  {
    id: 101,
    customer_name: "Customer One",
    location: "Chennai",
    priority: "HIGH",
    service_type: "HVAC",
    required_skill: "HVAC",
    issue_description: "AC repair",
    job_status: "UNASSIGNED",
    status: "UNASSIGNED",
  },
  {
    id: 102,
    customer_name: "Customer Two",
    location: "Bangalore",
    priority: "MEDIUM",
    service_type: "Electrical",
    required_skill: "Electrical",
    issue_description: "Electrical repair",
    job_status: "UNASSIGNED",
    status: "UNASSIGNED",
  },
];

const technicians = [
  {
    technician_id: 7,
    technician_name: "Technician One",
    technician_skill: "HVAC",
    technician_status: "AVAILABLE",
    current_jobs: 0,
    max_jobs: 5,
  },
  {
    technician_id: 8,
    technician_name: "Technician Two",
    technician_skill: "Electrical",
    technician_status: "AVAILABLE",
    current_jobs: 1,
    max_jobs: 5,
  },
];

/* -------------------------------------------------------------------------- */
/*                              Render Helper                                 */
/* -------------------------------------------------------------------------- */

const renderPlanningPage = () =>
  render(<PlanningPage />);

/*
 * PlanningPage intentionally waits about 1 second before completing
 * the pending-jobs fetch. Give the test enough time for that state update.
 */
const waitForPendingJobs = async () => {
  await waitFor(
    () => {
      expect(screen.getByText("#101")).toBeTruthy();
    },
    {
      timeout: 3000,
    }
  );
};

/* -------------------------------------------------------------------------- */
/*                                  Test Suite                                */
/* -------------------------------------------------------------------------- */

describe("PlanningPage - Task 1 Bulk Job Assignment", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockedGetTechnicians.mockResolvedValue({
      data: technicians,
    } as any);

    mockedGetAvailableTechnicians.mockResolvedValue({
      data: technicians,
    } as any);

    mockedGetPendingJobs.mockResolvedValue({
      data: pendingJobs,
      headers: {
        "x-total-count": String(pendingJobs.length),
      },
    } as any);

    mockedGetPlannedAssignments.mockResolvedValue({
      data: [],
      headers: {
        "x-total-count": "0",
      },
    } as any);

    mockedAssignJobsBulk.mockResolvedValue({
      data: {
        results: [
          {
            job_id: 101,
            status: "assigned",
            technician_id: 7,
            message: "Job assigned successfully",
          },
          {
            job_id: 102,
            status: "assigned",
            technician_id: 7,
            message: "Job assigned successfully",
          },
        ],
        total_requested: 2,
        total_assigned: 2,
      },
    } as any);

    mockedCancelJobsBulk.mockResolvedValue({
      data: {
        status: "success",
        total_requested: 1,
        total_cancelled: 1,
        results: [
          {
            job_id: 101,
            status: "CANCELLED",
            message: "Job cancelled successfully",
          },
        ],
      },
    } as any);
  });

  afterEach(() => {
    cleanup();

    vi.restoreAllMocks();
  });

  /* ---------------------------------------------------------------------- */
  /* Test 1: Multiple Job Selection                                        */
  /* ---------------------------------------------------------------------- */

  it("renders pending jobs and allows multiple job selection", async () => {
    renderPlanningPage();

    await waitForPendingJobs();

    expect(screen.getByText("#102")).toBeTruthy();

    const job101Checkbox = screen.getByRole("checkbox", {
      name: "Select job 101",
    });

    const job102Checkbox = screen.getByRole("checkbox", {
      name: "Select job 102",
    });

    fireEvent.click(job101Checkbox);
    fireEvent.click(job102Checkbox);

    expect(
      screen.getByText("2 job(s) selected")
    ).toBeTruthy();
  });

  /* ---------------------------------------------------------------------- */
  /* Test 2: Assign Button Disabled Until Technician Selected              */
  /* ---------------------------------------------------------------------- */

  it("keeps Assign Selected disabled until a technician is selected", async () => {
    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "Select job 101",
      })
    );

    const assignButton = screen.getByRole("button", {
      name: "Assign Selected",
    });

    expect(
      (assignButton as HTMLButtonElement).disabled
    ).toBe(true);

    fireEvent.change(
      screen.getByRole("combobox", {
        name: "Select technician for bulk assignment",
      }),
      {
        target: {
          value: "7",
        },
      }
    );

    expect(
      (assignButton as HTMLButtonElement).disabled
    ).toBe(false);
  });

  /* ---------------------------------------------------------------------- */
  /* Test 3: Backend Receives Selected Jobs + Technician                  */
  /* ---------------------------------------------------------------------- */

  it("sends all selected job IDs and the selected technician to the backend", async () => {
    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "Select job 101",
      })
    );

    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "Select job 102",
      })
    );

    fireEvent.change(
      screen.getByRole("combobox", {
        name: "Select technician for bulk assignment",
      }),
      {
        target: {
          value: "7",
        },
      }
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Assign Selected",
      })
    );

    await waitFor(() => {
      expect(mockedAssignJobsBulk).toHaveBeenCalledWith(
        [101, 102],
        7
      );
    });
  });

  /* ---------------------------------------------------------------------- */
  /* Test 4: Loading State During Bulk Assignment                          */
  /* ---------------------------------------------------------------------- */

  it("shows the assigning state while the bulk API request is pending", async () => {
    let resolveRequest: (value: any) => void = () => {};

    mockedAssignJobsBulk.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveRequest = resolve;
        }) as any
    );

    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "Select job 101",
      })
    );

    fireEvent.change(
      screen.getByRole("combobox", {
        name: "Select technician for bulk assignment",
      }),
      {
        target: {
          value: "7",
        },
      }
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Assign Selected",
      })
    );

    expect(
      await screen.findByRole("button", {
        name: "Assigning...",
      })
    ).toBeTruthy();

    expect(
      (
        screen.getByRole("button", {
          name: "Assigning...",
        }) as HTMLButtonElement
      ).disabled
    ).toBe(true);

    resolveRequest({
      data: {
        results: [
          {
            job_id: 101,
            status: "assigned",
            technician_id: 7,
            message: "Job assigned successfully",
          },
        ],
        total_requested: 1,
        total_assigned: 1,
      },
    });

    await waitFor(() => {
      expect(
        screen.queryByRole("button", {
          name: "Assigning...",
        })
      ).toBeNull();
    });
  });

  /* ---------------------------------------------------------------------- */
  /* Test 5: Clear Selection                                                */
  /* ---------------------------------------------------------------------- */

  it("clears the selected jobs when Clear is clicked", async () => {
    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "Select job 101",
      })
    );

    expect(
      screen.getByText("1 job(s) selected")
    ).toBeTruthy();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Clear",
      })
    );

    expect(
      screen.queryByText("1 job(s) selected")
    ).toBeNull();

    expect(
      screen.queryByRole("button", {
        name: "Assign Selected",
      })
    ).toBeNull();
  });

  /* ---------------------------------------------------------------------- */
  /* Test 6: Backend Error                                                  */
  /* ---------------------------------------------------------------------- */

  it("shows the backend error when bulk assignment fails", async () => {
    mockedAssignJobsBulk.mockRejectedValue({
      response: {
        data: {
          detail:
            "One or more selected jobs are already assigned.",
        },
      },
    });

    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "Select job 101",
      })
    );

    fireEvent.change(
      screen.getByRole("combobox", {
        name: "Select technician for bulk assignment",
      }),
      {
        target: {
          value: "7",
        },
      }
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Assign Selected",
      })
    );

    await waitFor(() => {
      expect(
        screen.getByText(
          "One or more selected jobs are already assigned."
        )
      ).toBeTruthy();
    });
  });

  /* ---------------------------------------------------------------------- */
  /* Task 2: Bulk Job Cancellation                                          */
  /* ---------------------------------------------------------------------- */

  it("shows the bulk cancellation action when jobs are selected", async () => {
    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "Select job 101",
      })
    );

    expect(
      screen.getByRole("button", {
        name: "Cancel Selected",
      })
    ).toBeTruthy();
  });

  it("cancels selected jobs after confirmation and reason", async () => {
    mockedCancelJobsBulk.mockResolvedValue({
      data: {
        status: "success",
        total_requested: 1,
        total_cancelled: 1,
        results: [
          {
            job_id: 101,
            status: "CANCELLED",
            message: "Job cancelled successfully",
          },
        ],
      },
    } as any);

    vi.spyOn(window, "confirm").mockReturnValue(true);

    vi.spyOn(window, "prompt").mockReturnValue(
      "Customer requested cancellation"
    );

    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "Select job 101",
      })
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Cancel Selected",
      })
    );

    await waitFor(() => {
      expect(mockedCancelJobsBulk).toHaveBeenCalledWith(
        [101],
        "Customer requested cancellation"
      );
    });
  });

  it("blocks bulk cancellation when confirmation is rejected", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);

    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "Select job 101",
      })
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Cancel Selected",
      })
    );

    expect(
      mockedCancelJobsBulk
    ).not.toHaveBeenCalled();
  });

  it("requires a cancellation reason", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);

    vi.spyOn(window, "prompt").mockReturnValue("");

    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "Select job 101",
      })
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Cancel Selected",
      })
    );

    expect(
      mockedCancelJobsBulk
    ).not.toHaveBeenCalled();

    expect(
      await screen.findByText(
        "Cancellation reason is required."
      )
    ).toBeTruthy();
  });

  it("shows the cancelling state while the bulk cancellation request is pending", async () => {
    let resolveRequest: (value: any) => void = () => {};

    mockedCancelJobsBulk.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveRequest = resolve;
        }) as any
    );

    vi.spyOn(window, "confirm").mockReturnValue(true);

    vi.spyOn(window, "prompt").mockReturnValue(
      "Dispatcher cancellation"
    );

    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "Select job 101",
      })
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Cancel Selected",
      })
    );

    expect(
      await screen.findByRole("button", {
        name: "Cancelling...",
      })
    ).toBeTruthy();

    expect(
      (
        screen.getByRole("button", {
          name: "Cancelling...",
        }) as HTMLButtonElement
      ).disabled
    ).toBe(true);

    resolveRequest({
      data: {
        status: "success",
        total_requested: 1,
        total_cancelled: 1,
        results: [],
      },
    });

    await waitFor(() => {
      expect(
        screen.queryByRole("button", {
          name: "Cancelling...",
        })
      ).toBeNull();
    });
  });

  it("shows the backend validation error when bulk cancellation fails", async () => {
    mockedCancelJobsBulk.mockRejectedValue({
      response: {
        data: {
          detail: {
            message:
              "Bulk cancellation was not performed because one or more selected jobs failed validation",
          },
        },
      },
    });

    vi.spyOn(window, "confirm").mockReturnValue(true);

    vi.spyOn(window, "prompt").mockReturnValue(
      "Dispatcher cancellation"
    );

    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "Select job 101",
      })
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Cancel Selected",
      })
    );

    expect(
      await screen.findByText(
        "Bulk cancellation was not performed because one or more selected jobs failed validation"
      )
    ).toBeTruthy();
  });
});