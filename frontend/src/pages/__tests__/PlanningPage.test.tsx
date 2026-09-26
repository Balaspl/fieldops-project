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
  act,
} from "@testing-library/react";

import PlanningPage from "../PlanningPage";
import {
  forceAssignEscalation,
} from "../../services/escalationService";

import {
  getDeclinedJobs,
  reassignDeclinedJob,
} from "../../services/customerPortalService";
import {
  getTechnicians,
  getAvailableTechnicians,
  getPendingJobs,
  getPlannedAssignments,
  assignJob,
  assignJobsBulk,
  cancelJobsBulk,
  manualAssign,
} from "../../services/planningService";

import { getTechnicianETA } from "../../services/etaService";
import { useLoadScript } from "@react-google-maps/api";

const {
  mockedIo,
  mockSocket,
  mockSocketHandlers,
  mockAnyHandlers,
} = vi.hoisted(() => {
  type Handler = (...args: any[]) => void;

  const socketHandlers =
    new Map<string, Set<Handler>>();

  const anyHandlers = new Set<
    (
      eventName: string,
      payload: unknown
    ) => void
  >();

  const socket: any = {
    active: true,

    on: vi.fn(
      (
        event: string,
        handler: Handler
      ) => {
        if (!socketHandlers.has(event)) {
          socketHandlers.set(
            event,
            new Set<Handler>()
          );
        }

        socketHandlers
          .get(event)!
          .add(handler);

        return socket;
      }
    ),

    off: vi.fn(
      (
        event: string,
        handler: Handler
      ) => {
        socketHandlers
          .get(event)
          ?.delete(handler);

        return socket;
      }
    ),

    onAny: vi.fn(
      (
        handler: (
          eventName: string,
          payload: unknown
        ) => void
      ) => {
        anyHandlers.add(handler);
        return socket;
      }
    ),

    offAny: vi.fn(
      (
        handler: (
          eventName: string,
          payload: unknown
        ) => void
      ) => {
        anyHandlers.delete(handler);
        return socket;
      }
    ),

    disconnect: vi.fn(() => {
      socket.active = false;
    }),
  };

  const ioMock = vi.fn(() => {
    socket.active = true;
    return socket;
  });

  return {
    mockedIo: ioMock,
    mockSocket: socket,
    mockSocketHandlers: socketHandlers,
    mockAnyHandlers: anyHandlers,
  };
});

vi.mock("socket.io-client", () => ({
  io: mockedIo,
}));

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
  getJobPlan: vi.fn().mockResolvedValue({
    ranked_technicians: [
      {
        tech_id: 7,
        name: "Technician One",
        skill: "HVAC",
        status: "AVAILABLE",
        composite_score: 100,
        proximity_score: 95,
        skill_score: 100,
        workload_score: 100,
        distance_km: 1.2,
        active_jobs: 0,
        max_capacity: 5,
      },
    ],
  }),
  getAuditOverrides: vi.fn(),
  assignJobDirect: vi.fn(),
}));

vi.mock("../../services/etaService", () => ({
  getTechnicianETA: vi.fn(),
}));

vi.mock("@react-google-maps/api", () => ({
  useLoadScript: vi.fn(() => ({
    isLoaded: true,
    loadError: null,
  })),

  GoogleMap: ({ children, ...props }: any) => (
    <div data-testid="google-map" {...props}>
      {children}
    </div>
  ),

  DirectionsRenderer: ({ directions }: any) => (
    <div
      data-testid="directions-renderer"
      data-directions={directions ? "loaded" : "empty"}
    />
  ),

  MarkerF: ({ position, title }: any) => (
    <div
      data-testid={`map-marker-${title}`}
      data-lat={String(position?.lat ?? "")}
      data-lng={String(position?.lng ?? "")}
    />
  ),
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
  default: () => (
    <div data-testid="empty-state">No jobs</div>
  ),
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
  default: ({
    candidates = [],
    onSelect,
  }: {
    candidates?: any[];
    onSelect?: (techId: number) => void | Promise<void>;
  }) => {
    const renderedCandidates =
      candidates.length > 0
        ? candidates
        : [
            {
              technician_id: 7,
              technician_name: "Technician One",
            },
          ];

    return (
      <div data-testid="ranked-tech-table">
        {renderedCandidates.map((candidate: any) => {
          const technicianId =
            candidate.technician_id ?? candidate.tech_id;

          const technicianName =
            candidate.technician_name ?? candidate.name;

          return (
            <button
              key={technicianId}
              type="button"
              onClick={() =>
                onSelect?.(Number(technicianId))
              }
            >
              {technicianName}
            </button>
          );
        })}
      </div>
    );
  },
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
const mockedGetAvailableTechnicians =
  vi.mocked(getAvailableTechnicians);
const mockedGetPendingJobs = vi.mocked(getPendingJobs);
const mockedGetPlannedAssignments =
  vi.mocked(getPlannedAssignments);
const mockedAssignJob = vi.mocked(assignJob);
const mockedAssignJobsBulk = vi.mocked(assignJobsBulk);
const mockedCancelJobsBulk = vi.mocked(cancelJobsBulk);
const mockedManualAssign = vi.mocked(manualAssign);
const mockedGetTechnicianETA = vi.mocked(getTechnicianETA);
const mockedForceAssignEscalation = vi.mocked(forceAssignEscalation);
const mockedGetDeclinedJobs = vi.mocked(getDeclinedJobs);
const mockedReassignDeclinedJob = vi.mocked(reassignDeclinedJob);

const mockedUseLoadScript = vi.mocked(useLoadScript);

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
  {
    id: 103,
    customer_name: "Escalated Customer",
    location: "Chennai",
    priority: "HIGH",
    service_type: "HVAC",
    required_skill: "HVAC",
    issue_description: "Escalated AC repair",
    job_status: "ESCALATED",
    status: "ESCALATED",
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

const emitMockSocketEvent = (
  eventName: string,
  payload: any
) => {
  mockAnyHandlers.forEach((handler) => {
    handler(eventName, payload);
  });
};

const emitMockSocketLifecycle = (
  eventName:
    | "connect"
    | "disconnect"
    | "connect_error",
  ...args: any[]
) => {
  mockSocketHandlers
    .get(eventName)
    ?.forEach((handler) => {
      handler(...args);
    });
};

const waitForPendingJobs = async () => {
  await waitFor(
    () => {
      expect(screen.getByText("#101")).toBeTruthy();
    },
    {
      timeout: 5000,
    }
  );
};

const selectTechnicianForJob = async (
  jobId: number,
  technicianName = "Technician One"
) => {
  const jobRow = screen
    .getByText(`#${jobId}`)
    .closest("tr");

  if (!jobRow) {
    throw new Error(`Job row for job ${jobId} was not found.`);
  }

  // Current PlanningPage uses a native select for technician selection.
  const technicianSelect =
    jobRow.querySelector(
      "select.tech-select-style"
    ) as HTMLSelectElement | null;

  if (technicianSelect) {
    const technician = technicians.find(
      (t) => t.technician_name === technicianName
    );

    if (!technician) {
      throw new Error(
        `Technician ${technicianName} was not found.`
      );
    }

    fireEvent.change(technicianSelect, {
      target: {
        value: String(technician.technician_id),
      },
    });

    return;
  }

  // Current PlanningPage opens the Candidate Selection modal from
  // the technician selector button. The actual selection control is
  // rendered by RankedTechTable/TopThreeHighlight.
  const technicianButton =
    jobRow.querySelector(
      "button.tech-select-style"
    ) as HTMLButtonElement | null;

  if (!technicianButton) {
    throw new Error(
      `Technician selector for job ${jobId} was not found.`
    );
  }

  fireEvent.click(technicianButton);

  // RankedTechTable is mocked in this test suite and exposes
  // the technician name itself as the accessible button name.
  const selectButton = await screen.findByRole(
    "button",
    {
      name: technicianName,
    },
    {
      timeout: 5000,
    }
  );

  fireEvent.click(selectButton);
};


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

    mockedAssignJob.mockResolvedValue({
      data: {
        status: "success",
        job_id: 101,
        technician_id: 7,
      },
    } as any);

    mockedManualAssign.mockResolvedValue({
      data: {
        status: "success",
        job_id: 101,
        technician_id: 7,
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

    mockedForceAssignEscalation.mockResolvedValue({
      data: {
        status: "success",
        job_id: 101,
        technician_id: "7",
      },
    } as any);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders pending jobs and allows multiple job selection", async () => {
    renderPlanningPage();

    await waitForPendingJobs();

    expect(screen.getByText("#102")).toBeTruthy();

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

    expect(
      screen.getByText("2 job(s) selected")
    ).toBeTruthy();
  });

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
        target: { value: "7" },
      }
    );

    expect(
      (assignButton as HTMLButtonElement).disabled
    ).toBe(false);
  });

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
        target: { value: "7" },
      }
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Assign Selected",
      })
    );

    await screen.findByRole("dialog");

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Assignment",
      })
    );

    await waitFor(
      () => {
        expect(mockedAssignJobsBulk).toHaveBeenCalledWith(
          [101, 102],
          7
        );
      },
      {
        timeout: 10000,
      }
    );
  });

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
        target: { value: "7" },
      }
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Assign Selected",
      })
    );

    await screen.findByRole("dialog");

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Assignment",
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
        target: { value: "7" },
      }
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Assign Selected",
      })
    );

    await screen.findByRole("dialog");

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Assignment",
      })
    );

    await waitFor(() => {
      expect(
        screen.getByRole("alert").textContent
      ).toContain(
        "One or more selected jobs are already assigned."
      );
    });
  });

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

  it("cancels selected jobs after explicit dialog confirmation and reason", async () => {
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

    await screen.findByRole("dialog");

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Cancellation",
      })
    );

    expect(
      await screen.findByRole("alert")
    ).toBeTruthy();

    expect(mockedCancelJobsBulk).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Reason *"), {
      target: { value: "Customer requested cancellation" },
    });

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Cancellation",
      })
    );

    await waitFor(() => {
      expect(mockedCancelJobsBulk).toHaveBeenCalledWith(
        [101],
        "Customer requested cancellation"
      );
    });
  });

  it("blocks bulk cancellation when the confirmation dialog is cancelled", async () => {
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

    await screen.findByRole("dialog");

    fireEvent.click(
      screen.getByRole("button", {
        name: "Cancel",
      })
    );

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(mockedCancelJobsBulk).not.toHaveBeenCalled();
  });

  it("shows the cancelling state while the bulk cancellation request is pending", async () => {
    let resolveRequest: (value: any) => void = () => {};

    mockedCancelJobsBulk.mockImplementation(
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

    fireEvent.click(
      screen.getByRole("button", {
        name: "Cancel Selected",
      })
    );

    await screen.findByRole("dialog");

    fireEvent.change(screen.getByLabelText("Reason *"), {
      target: { value: "Dispatcher cancellation" },
    });

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Cancellation",
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

    await screen.findByRole("dialog");

    fireEvent.change(screen.getByLabelText("Reason *"), {
      target: { value: "Dispatcher cancellation" },
    });

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Cancellation",
      })
    );

    expect(
      await screen.findAllByText(
        "Bulk cancellation was not performed because one or more selected jobs failed validation"
      )
    ).toHaveLength(2);
  });
});



describe(
  "PlanningPage - Task 5 Technician Route Display",
  () => {
    const plannedAssignment = {
      job_id: 301,
      technician: "Route Technician",
      skill: "HVAC",
      customer: "Route Customer",
      location: "13.0827,80.2707",
      priority: "HIGH",
      status: "ASSIGNED",
      current_jobs: 2,
      max_jobs: 5,
    };

    const routeTechnician = {
      technician_id: 31,
      tech_id: "tech-route-31",
      technician_name: "Route Technician",
      technician_skill: "HVAC",
      technician_status: "AVAILABLE",
      technician_location: "13.0674,80.2376",
      current_jobs: 2,
      max_jobs: 5,
    };

    const etaResponse = {
      eta: "18 min",
      duration_minutes: 18,
      distance_meters: 7200,
      origin: {
        lat: 13.0674,
        lng: 80.2376,
      },
      destination: {
        lat: 13.0827,
        lng: 80.2707,
      },
    };

    beforeEach(() => {
      vi.clearAllMocks();

      mockedUseLoadScript.mockReturnValue({
        isLoaded: true,
        loadError: null,
      } as any);

      mockedGetTechnicians.mockResolvedValue({
        data: [routeTechnician],
      } as any);

      mockedGetAvailableTechnicians.mockResolvedValue({
        data: [routeTechnician],
      } as any);

      mockedGetPendingJobs.mockResolvedValue({
        data: pendingJobs,
        headers: {
          "x-total-count": String(
            pendingJobs.length
          ),
        },
      } as any);

      mockedGetPlannedAssignments.mockResolvedValue({
        data: [plannedAssignment],
        headers: {
          "x-total-count": "1",
        },
      } as any);

      mockedGetTechnicianETA.mockResolvedValue(
        etaResponse as any
      );

      (globalThis as any).google = {
        maps: {
          TravelMode: {
            DRIVING: "DRIVING",
          },
          DirectionsStatus: {
            OK: "OK",
          },
          DirectionsService: class {
            route(
              _request: any,
              callback: (
                result: any,
                status: string
              ) => void
            ) {
              callback(
                {
                  routes: [
                    {
                      legs: [],
                    },
                  ],
                },
                "OK"
              );
            }
          },
        },
      };
    });

    afterEach(() => {
      cleanup();
      vi.clearAllMocks();
      delete (globalThis as any).google;
    });

    const openPlannedAssignments =
      async () => {
        renderPlanningPage();

        const plannedAssignmentsButton =
          await screen.findByRole("button", {
            name: /Planned Assignments/i,
          });

        fireEvent.click(
          plannedAssignmentsButton
        );

        await waitFor(() => {
          expect(
            screen.getByText("#301")
          ).toBeTruthy();
        });

        await waitFor(() => {
          expect(
            screen.getByRole("button", {
              name: "View technician route",
            })
          ).toBeTruthy();
        });
      };

    it(
      "renders the route action for a planned technician assignment",
      async () => {
        await openPlannedAssignments();

        expect(
          screen.getByRole("button", {
            name: "View technician route",
          })
        ).toBeTruthy();
      }
    );

    it(
      "requests ETA using the backend technician identifier and job ID",
      async () => {
        await openPlannedAssignments();

        fireEvent.click(
          screen.getByRole("button", {
            name: "View technician route",
          })
        );

        await waitFor(() => {
          expect(
            mockedGetTechnicianETA
          ).toHaveBeenCalledWith(
            "tech-route-31",
            301
          );
        });
      }
    );

    it(
      "renders the authoritative ETA and route after a successful response",
      async () => {
        await openPlannedAssignments();

        fireEvent.click(
          screen.getByRole("button", {
            name: "View technician route",
          })
        );

        expect(
          await screen.findByText(
            "Technician Route"
          )
        ).toBeTruthy();

        await waitFor(() => {
          expect(
            screen.getAllByText("18 min")
              .length
          ).toBeGreaterThan(0);
        });

        expect(
          await screen.findByText("7.2 km")
        ).toBeTruthy();

        expect(
          screen.getByTestId(
            "technician-job-route-map"
          )
        ).toBeTruthy();

        expect(
          screen.getByTestId("google-map")
        ).toBeTruthy();

        expect(
          screen.getByTestId(
            "directions-renderer"
          )
        ).toBeTruthy();
      }
    );

    it(
      "shows the route loading state while ETA is pending",
      async () => {
        let resolveEta: (value: any) => void =
          () => {};

        mockedGetTechnicianETA.mockImplementation(
          () =>
            new Promise((resolve) => {
              resolveEta = resolve;
            }) as any
        );

        await openPlannedAssignments();

        fireEvent.click(
          screen.getByRole("button", {
            name: "View technician route",
          })
        );

        expect(
          await screen.findByText(
            /loading technician route/i
          )
        ).toBeTruthy();

        expect(
          screen.queryByTestId(
            "technician-job-route-map"
          )
        ).toBeNull();

        resolveEta(etaResponse);

        await waitFor(() => {
          expect(
            screen.getByTestId(
              "technician-job-route-map"
            )
          ).toBeTruthy();
        });
      }
    );

    it(
      "shows an actionable error when ETA API fails",
      async () => {
        mockedGetTechnicianETA.mockRejectedValueOnce(
          new Error(
            "Unable to load route information"
          )
        );

        await openPlannedAssignments();

        fireEvent.click(
          screen.getByRole("button", {
            name: "View technician route",
          })
        );

        expect(
          await screen.findByText(
            "Route unavailable"
          )
        ).toBeTruthy();

        expect(
          screen.getByText(
            /Unable to load route information/i
          )
        ).toBeTruthy();
      }
    );

    it(
      "handles missing technician location without requesting ETA",
      async () => {
        mockedGetTechnicians.mockResolvedValue({
          data: [
            {
              ...routeTechnician,
              technician_location: "",
            },
          ],
        } as any);

        await openPlannedAssignments();

        fireEvent.click(
          screen.getByRole("button", {
            name: "View technician route",
          })
        );

        expect(
          await screen.findByText(
            /Technician location is missing or invalid/i
          )
        ).toBeTruthy();

        expect(
          mockedGetTechnicianETA
        ).not.toHaveBeenCalled();
      }
    );

    it(
      "handles invalid job location without requesting ETA",
      async () => {
        mockedGetPlannedAssignments.mockResolvedValue({
          data: [
            {
              ...plannedAssignment,
              location: "invalid-location",
            },
          ],
          headers: {
            "x-total-count": "1",
          },
        } as any);

        await openPlannedAssignments();

        fireEvent.click(
          screen.getByRole("button", {
            name: "View technician route",
          })
        );

        expect(
          await screen.findByText(
            /Job location is missing or invalid/i
          )
        ).toBeTruthy();

        expect(
          mockedGetTechnicianETA
        ).not.toHaveBeenCalled();
      }
    );

    it(
      "handles an unavailable Google Maps configuration",
      async () => {
        mockedUseLoadScript.mockReturnValue({
          isLoaded: false,
          loadError: new Error(
            "Google Maps unavailable"
          ),
        } as any);

        await openPlannedAssignments();

        fireEvent.click(
          screen.getByRole("button", {
            name: "View technician route",
          })
        );

        expect(
          await screen.findByText(
            /Google Maps is not ready yet/i
          )
        ).toBeTruthy();

        expect(
          mockedGetTechnicianETA
        ).not.toHaveBeenCalled();
      }
    );
  }
);



describe(
  "PlanningPage - Task 6 Map-Based Job View",
  () => {
    const mappableJobs = [
      {
        id: 201,
        customer_name: "Map Customer One",
        location: "13.0827,80.2707",
        priority: "HIGH",
        service_type: "HVAC",
        required_skill: "HVAC",
        issue_description: "AC repair",
        job_status: "UNASSIGNED",
        status: "UNASSIGNED",
      },
      {
        id: 202,
        customer_name: "Map Customer Two",
        location: "invalid-location",
        priority: "MEDIUM",
        service_type: "Electrical",
        required_skill: "Electrical",
        issue_description: "Electrical repair",
        job_status: "UNASSIGNED",
        status: "UNASSIGNED",
      },
    ];

    beforeEach(() => {
      vi.clearAllMocks();

      mockedUseLoadScript.mockReturnValue({
        isLoaded: true,
        loadError: null,
      } as any);

      mockedGetTechnicians.mockResolvedValue({
        data: technicians,
      } as any);

      mockedGetAvailableTechnicians.mockResolvedValue({
        data: technicians,
      } as any);

      mockedGetPendingJobs.mockResolvedValue({
        data: mappableJobs,
        headers: {
          "x-total-count": String(
            mappableJobs.length
          ),
        },
      } as any);

      mockedGetPlannedAssignments.mockResolvedValue({
        data: [],
        headers: {
          "x-total-count": "0",
        },
      } as any);
    });

    afterEach(() => {
      cleanup();
      vi.restoreAllMocks();
    });

    const openJobMap = async () => {
      renderPlanningPage();

      await waitFor(
        () => {
          expect(screen.getByText("#201")).toBeTruthy();
        },
        {
          timeout: 3000,
        }
      );

      const mapButton =
        screen.getByRole("button", {
          name: "Open job map",
        });

      expect(
        (mapButton as HTMLButtonElement).disabled
      ).toBe(false);

      fireEvent.click(mapButton);

      await waitFor(() => {
        expect(
          screen.getByText("Eligible Jobs Map")
        ).toBeTruthy();
      });
    };

    it(
      "renders the map view action in the dispatcher dashboard",
      async () => {
        renderPlanningPage();

        await waitFor(() => {
          expect(
            screen.getByRole("button", {
              name: "Open job map",
            })
          ).toBeTruthy();
        });
      }
    );

    it(
      "uses the existing tenant-scoped pending-jobs API contract",
      async () => {
        renderPlanningPage();

        await waitFor(() => {
          expect(
            mockedGetPendingJobs
          ).toHaveBeenCalled();
        });

        expect(
          mockedGetPendingJobs
        ).toHaveBeenCalledWith(
          expect.objectContaining({
            page: 1,
            limit: 8,
          })
        );
      }
    );

    it(
      "plots only eligible jobs with valid backend coordinates",
      async () => {
        await openJobMap();

        await waitFor(() => {
          expect(
            screen.getByTestId(
              "dispatcher-job-map"
            )
          ).toBeTruthy();
        });

        expect(
          screen.getByTestId(
            "job-map-item-201"
          )
        ).toBeTruthy();

        expect(
          screen.queryByTestId(
            "job-map-item-202"
          )
        ).toBeNull();

        expect(
          screen.getByTestId(
            "map-marker-Job #201"
          )
        ).toBeTruthy();

        expect(
          screen.queryByTestId(
            "map-marker-Job #202"
          )
        ).toBeNull();
      }
    );

    it(
      "maps backend coordinate values without frontend geocoding",
      async () => {
        await openJobMap();

        const marker =
          await screen.findByTestId(
            "map-marker-Job #201"
          );

        expect(
          marker.getAttribute("data-lat")
        ).toBe("13.0827");

        expect(
          marker.getAttribute("data-lng")
        ).toBe("80.2707");
      }
    );

    it(
      "keeps the map action disabled while Google Maps is loading",
      async () => {
        mockedUseLoadScript.mockReturnValue({
          isLoaded: false,
          loadError: null,
        } as any);

        renderPlanningPage();

        await waitFor(() => {
          expect(
            screen.getByRole("button", {
              name: "Open job map",
            })
          ).toBeTruthy();
        });

        const mapButton =
          screen.getByRole("button", {
            name: "Open job map",
          });

        expect(
          (mapButton as HTMLButtonElement).disabled
        ).toBe(true);

        expect(
          screen.queryByText(
            "Eligible Jobs Map"
          )
        ).toBeNull();
      }
    );

    it(
      "shows a Google Maps configuration error instead of plotting jobs",
      async () => {
        mockedUseLoadScript.mockReturnValue({
          isLoaded: false,
          loadError: new Error(
            "Google Maps unavailable"
          ),
        } as any);

        renderPlanningPage();

        await waitFor(() => {
          expect(
            screen.getByRole("button", {
              name: "Open job map",
            })
          ).toBeTruthy();
        });

        const mapButton =
          screen.getByRole("button", {
            name: "Open job map",
          });

        expect(
          (mapButton as HTMLButtonElement).disabled
        ).toBe(false);

        fireEvent.click(mapButton);

        const alert =
          await screen.findByRole("alert");

        expect(alert.textContent).toContain(
          "Google Maps is unavailable"
        );
      }
    );

    it(
      "handles an empty map result when no jobs contain valid coordinates",
      async () => {
        mockedGetPendingJobs.mockResolvedValue({
          data: [
            {
              ...mappableJobs[0],
              location: "Chennai",
            },
            {
              ...mappableJobs[1],
              location: "Bangalore",
            },
          ],
          headers: {
            "x-total-count": "2",
          },
        } as any);

        renderPlanningPage();

        await waitFor(() => {
          expect(
            screen.getByRole("button", {
              name: "Open job map",
            })
          ).toBeTruthy();
        });

        fireEvent.click(
          screen.getByRole("button", {
            name: "Open job map",
          })
        );

        expect(
          await screen.findByTestId(
            "job-map-empty"
          )
        ).toBeTruthy();

        expect(
          screen.queryByTestId(
            "dispatcher-job-map"
          )
        ).toBeNull();
      }
    );

    it(
      "does not issue another jobs API request when opening the map",
      async () => {
        renderPlanningPage();

        await waitFor(() => {
          expect(
            screen.getByRole("button", {
              name: "Open job map",
            })
          ).toBeTruthy();
        });

        const callsBeforeMapOpen =
          mockedGetPendingJobs.mock.calls.length;

        fireEvent.click(
          screen.getByRole("button", {
            name: "Open job map",
          })
        );

        await waitFor(() => {
          expect(
            screen.getByText(
              "Eligible Jobs Map"
            )
          ).toBeTruthy();
        });

        expect(
          mockedGetPendingJobs.mock.calls.length
        ).toBe(callsBeforeMapOpen);
      }
    );

    it(
      "handles pending-job API failure without rendering stale map markers",
      async () => {
        mockedGetPendingJobs.mockRejectedValue(
          new Error("Jobs API unavailable")
        );

        renderPlanningPage();

        expect(
          await screen.findByText(
            "Failed to load unassigned jobs. Please try again."
          )
        ).toBeTruthy();

        fireEvent.click(
          screen.getByRole("button", {
            name: "Open job map",
          })
        );

        expect(
          await screen.findByText(
            "Eligible Jobs Map"
          )
        ).toBeTruthy();

        expect(
          await screen.findByTestId(
            "job-map-empty"
          )
        ).toBeTruthy();

        expect(
          screen.queryByTestId(
            "dispatcher-job-map"
          )
        ).toBeNull();

        expect(
          screen.queryByTestId(
            "map-marker-Job #201"
          )
        ).toBeNull();
      }
    );
  }
);



describe("PlanningPage - Task 7 Dispatch Confirmation Dialog", () => {
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

    mockedGetDeclinedJobs.mockResolvedValue({
      data: [],
    } as any);

    mockedAssignJob.mockResolvedValue({
      data: {
        status: "success",
        job_id: 101,
        technician_id: 7,
      },
    } as any);

    mockedReassignDeclinedJob.mockResolvedValue({
      data: {
        status: "success",
        job_id: 501,
        technician_id: 7,
      },
    } as any);

    mockedForceAssignEscalation.mockResolvedValue({
      data: {
        status: "success",
        job_id: 103,
        technician_id: "7",
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
        ],
        total_requested: 1,
        total_assigned: 1,
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

  it("shows confirmation dialog before single job assignment", async () => {
    renderPlanningPage();

    await waitForPendingJobs();

    await selectTechnicianForJob(101);

    fireEvent.click(
      screen
        .getByText("#101")
        .closest("tr")!
        .querySelector("button.assign-btn-style.active") as HTMLButtonElement
    );

    expect(
      await screen.findByRole("dialog")
    ).toBeTruthy();

    expect(
      screen.getByText("Confirm Dispatch Action")
    ).toBeTruthy();

    expect(
      screen.getByText("Assign Job")
    ).toBeTruthy();

    expect(
      screen.getByText("Job #101")
    ).toBeTruthy();

    expect(
      screen.getByRole("dialog").textContent
    ).toContain("Technician One");

    expect(
      screen.getByRole("button", {
        name: "Confirm Assignment",
      })
    ).toBeTruthy();

    expect(mockedAssignJobsBulk).not.toHaveBeenCalled();
  });

  it("executes single assignment only after confirmation", async () => {
    renderPlanningPage();

    await waitForPendingJobs();

    await selectTechnicianForJob(101);

    fireEvent.click(
      screen
        .getByText("#101")
        .closest("tr")!
        .querySelector("button.assign-btn-style.active") as HTMLButtonElement
    );

    await screen.findByRole("dialog");

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Assignment",
      })
    );

    await waitFor(() => {
      expect(mockedAssignJob).toHaveBeenCalledWith(
        101,
        7
      );
    });
  });

  it("shows confirmation dialog before bulk assignment", async () => {
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
        target: { value: "7" },
      }
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Assign Selected",
      })
    );

    expect(
      await screen.findByRole("dialog")
    ).toBeTruthy();

    expect(
      screen.getByText("Bulk Job Assignment")
    ).toBeTruthy();

    expect(
      screen.getByText("Job #101")
    ).toBeTruthy();

    expect(
      screen.getByRole("dialog").textContent
    ).toContain("Technician One");

    expect(mockedAssignJobsBulk).not.toHaveBeenCalled();
  });

  it("executes bulk assignment only after confirmation", async () => {
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
        target: { value: "7" },
      }
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Assign Selected",
      })
    );

    await screen.findByRole("dialog");

    expect(mockedAssignJobsBulk).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Assignment",
      })
    );

    await waitFor(() => {
      expect(mockedAssignJobsBulk).toHaveBeenCalledWith(
        [101, 102],
        7
      );
    });
  });

  it("closes confirmation without executing the action", async () => {
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
        target: { value: "7" },
      }
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Assign Selected",
      })
    );

    await screen.findByRole("dialog");

    fireEvent.click(
      screen.getByRole("button", {
        name: "Cancel",
      })
    );

    expect(
      screen.queryByRole("dialog")
    ).toBeNull();

    expect(
      mockedAssignJobsBulk
    ).not.toHaveBeenCalled();
  });

  it("shows cancellation confirmation with affected jobs and reason field", async () => {
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
      await screen.findByRole("dialog")
    ).toBeTruthy();

    expect(
      screen.getByText("Bulk Job Cancellation")
    ).toBeTruthy();

    expect(
      screen.getByText("Job #101")
    ).toBeTruthy();

    expect(
      screen.getByLabelText("Reason *")
    ).toBeTruthy();

    expect(
      screen.getByRole("button", {
        name: "Confirm Cancellation",
      })
    ).toBeTruthy();

    expect(
      mockedCancelJobsBulk
    ).not.toHaveBeenCalled();
  });

  it("does not cancel until a reason is provided and confirmed", async () => {
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

    await screen.findByRole("dialog");

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Cancellation",
      })
    );

    expect(
      (await screen.findByRole("alert")).textContent
    ).toContain(
      "A reason is required before confirming this action."
    );

    expect(
      mockedCancelJobsBulk
    ).not.toHaveBeenCalled();

    fireEvent.change(
      screen.getByLabelText("Reason *"),
      {
        target: {
          value: "Dispatcher cancellation",
        },
      }
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Cancellation",
      })
    );

    await waitFor(() => {
      expect(mockedCancelJobsBulk).toHaveBeenCalledWith(
        [101],
        "Dispatcher cancellation"
      );
    });
  });

  it("shows processing state while confirmation action is pending", async () => {
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
        target: { value: "7" },
      }
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Assign Selected",
      })
    );

    await screen.findByRole("dialog");

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Assignment",
      })
    );

    expect(
      await screen.findByRole("button", {
        name: "Processing...",
      })
    ).toBeTruthy();

    expect(
      (
        screen.getByRole("button", {
          name: "Processing...",
        }) as HTMLButtonElement
      ).disabled
    ).toBe(true);

    resolveRequest({
      data: {
        results: [],
        total_requested: 1,
        total_assigned: 1,
      },
    });

    await waitFor(() => {
      expect(
        screen.queryByRole("button", {
          name: "Processing...",
        })
      ).toBeNull();
    });
  });

  it("keeps backend validation failure visible in the confirmation dialog", async () => {
    mockedAssignJobsBulk.mockRejectedValue({
      response: {
        data: {
          detail: {
            message:
              "One or more selected jobs are already assigned.",
          },
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
        target: { value: "7" },
      }
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Assign Selected",
      })
    );

    await screen.findByRole("dialog");

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Assignment",
      })
    );

    await waitFor(() => {
      expect(
        screen.getByRole("alert").textContent
      ).toContain(
        "One or more selected jobs are already assigned."
      );
    });
  });

  it("requires confirmation before manual override", async () => {
    mockedForceAssignEscalation.mockResolvedValue({
      data: {
        status: "success",
        job_id: 103,
        technician_id: "7",
      },
    } as any);

    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("button", {
        name: /SLA Escalations/i,
      })
    );

    await waitFor(() => {
      expect(screen.getByText("#103")).toBeTruthy();
    });

    await selectTechnicianForJob(103);

    const forceAssignButton = screen.getByRole("button", {
      name: "Force Assign",
    });

    fireEvent.click(forceAssignButton);

    expect(
      await screen.findByRole("dialog")
    ).toBeTruthy();

    expect(
      screen.getByText("Confirm Dispatch Action")
    ).toBeTruthy();

    expect(
      screen.getByText("Manual Override")
    ).toBeTruthy();

    expect(
      screen.getByText("Job #103")
    ).toBeTruthy();

    expect(
      screen.getByRole("dialog").textContent
    ).toContain("Technician One");

    expect(
      screen.getByLabelText(
        "Reason *"
      )
    ).toBeTruthy();

    expect(
      mockedForceAssignEscalation
    ).not.toHaveBeenCalled();
  });

  it("executes manual override only after confirmation and justification", async () => {
    mockedForceAssignEscalation.mockResolvedValue({
      data: {
        status: "success",
        job_id: 103,
        technician_id: "7",
      },
    } as any);

    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("button", {
        name: /SLA Escalations/i,
      })
    );

    await waitFor(() => {
      expect(screen.getByText("#103")).toBeTruthy();
    });

    await selectTechnicianForJob(103);

    fireEvent.click(
      screen.getByRole("button", {
        name: "Force Assign",
      })
    );

    await screen.findByRole("dialog");

    fireEvent.change(
      screen.getByLabelText("Reason *"),
      {
        target: {
          value: "Manager escalation override",
        },
      }
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Manual Override",
      })
    );

    await waitFor(() => {
      expect(
        mockedForceAssignEscalation
      ).toHaveBeenCalledWith(
        103,
        "7",
        "Manager escalation override"
      );
    });
  });

  it("does not execute manual override when justification is missing", async () => {
    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("button", {
        name: /SLA Escalations/i,
      })
    );

    await waitFor(() => {
      expect(screen.getByText("#103")).toBeTruthy();
    });

    await selectTechnicianForJob(103);

    fireEvent.click(
      screen.getByRole("button", {
        name: "Force Assign",
      })
    );

    await screen.findByRole("dialog");

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Manual Override",
      })
    );

    expect(
      (await screen.findByRole("alert")).textContent
    ).toContain(
      "A reason is required before confirming this action."
    );

    expect(
      mockedForceAssignEscalation
    ).not.toHaveBeenCalled();
  });
});

describe("PlanningPage - Task 8 Dispatch Failure Messages", () => {
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

    mockedGetDeclinedJobs.mockResolvedValue({
      data: [],
    } as any);

    mockedAssignJobsBulk.mockResolvedValue({
      data: {
        status: "assigned",
        message: "Job assigned successfully",
        total_assigned: 1,
      },
    } as any);
  });

  it("translates backend validation failure and preserves correlation ID", async () => {
    mockedAssignJobsBulk.mockRejectedValue({
      response: {
        status: 400,
        data: {
          detail: "One or more selected jobs are already assigned.",
        },
        headers: {
          "x-correlation-id": "corr-task8-validation-001",
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
        target: { value: "7" },
      }
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Assign Selected",
      })
    );

    await screen.findByRole("dialog");

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Assignment",
      })
    );

    const alert = await screen.findByRole("alert");

    expect(alert.textContent).toContain(
      "Bulk Job Assignment was rejected by backend validation"
    );

    expect(alert.textContent).toContain(
      "One or more selected jobs are already assigned."
    );

    expect(alert.textContent).toContain(
      "Reference ID: corr-task8-validation-001"
    );
  });

  it("shows a permission message for backend 403 failures", async () => {
    mockedAssignJobsBulk.mockRejectedValue({
      response: {
        status: 403,
        data: {
          detail: "Access denied",
        },
        headers: {
          "x-correlation-id": "corr-task8-permission-001",
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
        target: { value: "7" },
      }
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Assign Selected",
      })
    );

    await screen.findByRole("dialog");

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Assignment",
      })
    );

    const alert = await screen.findByRole("alert");

    expect(alert.textContent).toContain(
      "You do not have permission to perform bulk job assignment."
    );

    expect(alert.textContent).toContain(
      "Reference ID: corr-task8-permission-001"
    );
  });

  it("shows a conflict message for backend 409 failures", async () => {
    mockedAssignJobsBulk.mockRejectedValue({
      response: {
        status: 409,
        data: {
          detail: "Job state changed before assignment.",
        },
        headers: {
          "x-correlation-id": "corr-task8-conflict-001",
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
        target: { value: "7" },
      }
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Assign Selected",
      })
    );

    await screen.findByRole("dialog");

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Assignment",
      })
    );

    const alert = await screen.findByRole("alert");

    expect(alert.textContent).toContain(
      "Bulk Job Assignment could not be completed because of a dispatch conflict"
    );

    expect(alert.textContent).toContain(
      "Job state changed before assignment."
    );

    expect(alert.textContent).toContain(
      "Reference ID: corr-task8-conflict-001"
    );
  });

  it("shows a server failure message without exposing internal server details", async () => {
    mockedAssignJobsBulk.mockRejectedValue({
      response: {
        status: 500,
        data: {
          detail: "psycopg2 internal database exception details",
        },
        headers: {
          "x-correlation-id": "corr-task8-server-001",
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
        target: { value: "7" },
      }
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Assign Selected",
      })
    );

    await screen.findByRole("dialog");

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Assignment",
      })
    );

    const alert = await screen.findByRole("alert");

    expect(alert.textContent).toContain(
      "The dispatch service could not complete bulk job assignment because of a server error."
    );

    expect(alert.textContent).toContain(
      "Reference ID: corr-task8-server-001"
    );

    expect(alert.textContent).not.toContain(
      "psycopg2 internal database exception details"
    );
  });
});

describe(
  "PlanningPage - Task 9 Reassignment Eligibility and Failure Handling",
  () => {
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

      mockedGetDeclinedJobs.mockResolvedValue({
        data: [
          {
            id: 501,
            customer_name: "Declined Customer",
            service_type: "HVAC",
            status: "DECLINED",
          },
        ],
      } as any);

      mockedReassignDeclinedJob.mockResolvedValue({
        data: {
          status: "success",
          job_id: 501,
          technician_id: 7,
        },
      } as any);
    });

    afterEach(() => {
      cleanup();
    });

    const openDeclinedJobs = async () => {
      fireEvent.click(
        screen.getByRole("button", {
          name: /Technician Declined Jobs/i,
        })
      );

      await waitFor(() => {
        expect(
          screen.getByRole("button", {
            name: "Reassign Job",
          })
        ).toBeTruthy();
      });
    };

    const openReassignmentModal = async () => {
      fireEvent.click(
        screen.getByRole("button", {
          name: "Reassign Job",
        })
      );

      await waitFor(() => {
        expect(
          screen.getByRole("button", {
            name: "Confirm Reassign",
          })
        ).toBeTruthy();
      });
    };

    const selectReassignmentTechnician = (technicianId: number) => {
      const comboboxes = screen.getAllByRole("combobox");
      const reassignmentSelect =
        comboboxes[comboboxes.length - 1] as HTMLSelectElement;

      fireEvent.change(reassignmentSelect, {
        target: {
          value: String(technicianId),
        },
      });
    };

    it("shows confirmation dialog before reassignment", async () => {
      renderPlanningPage();

      await openDeclinedJobs();
      await openReassignmentModal();

      selectReassignmentTechnician(7);

      fireEvent.click(
        screen.getByRole("button", {
          name: "Confirm Reassign",
        })
      );

      expect(
        await screen.findByRole("dialog")
      ).toBeTruthy();

      expect(
        screen.getByRole("dialog").textContent
      ).toContain("Technician One");

      expect(
        screen.getByText("Job #501")
      ).toBeTruthy();

      expect(
        screen.getByRole("button", {
          name: "Confirm Reassignment",
        })
      ).toBeTruthy();

      expect(
        mockedReassignDeclinedJob
      ).not.toHaveBeenCalled();
    });

    it("executes reassignment only after explicit confirmation", async () => {
      mockedGetDeclinedJobs.mockResolvedValue({
        data: [
          {
            id: 502,
            customer_name: "Reassignment Customer",
            service_type: "Electrical",
            status: "DECLINED",
          },
        ],
      } as any);

      mockedReassignDeclinedJob.mockResolvedValue({
        data: {
          status: "success",
          job_id: 502,
          technician_id: 7,
        },
      } as any);

      renderPlanningPage();

      await openDeclinedJobs();
      await openReassignmentModal();

      selectReassignmentTechnician(7);

      fireEvent.click(
        screen.getByRole("button", {
          name: "Confirm Reassign",
        })
      );

      await screen.findByRole("dialog");

      expect(
        mockedReassignDeclinedJob
      ).not.toHaveBeenCalled();

      fireEvent.click(
        screen.getByRole("button", {
          name: "Confirm Reassignment",
        })
      );

      await waitFor(() => {
        expect(
          mockedReassignDeclinedJob
        ).toHaveBeenCalledWith(502, 7);
      });
    });

    it("shows only eligible technicians in the reassignment dropdown", async () => {
      mockedGetTechnicians.mockResolvedValue({
        data: [
          {
            technician_id: 7,
            technician_name: "Available Tech",
            technician_status: "AVAILABLE",
            current_jobs: 0,
            max_jobs: 5,
          },
          {
            technician_id: 8,
            technician_name: "Offline Tech",
            technician_status: "OFFLINE",
            current_jobs: 0,
            max_jobs: 5,
          },
        ],
      } as any);

      renderPlanningPage();

      await openDeclinedJobs();
      await openReassignmentModal();

      expect(
        screen.getByRole("option", {
          name: /Available Tech/i,
        })
      ).toBeTruthy();

      expect(
        screen.queryByRole("option", {
          name: /Offline Tech/i,
        })
      ).toBeNull();
    });

    it("blocks reassignment when no eligible technicians exist", async () => {
      mockedGetTechnicians.mockResolvedValue({
        data: [
          {
            technician_id: 8,
            technician_name: "Offline Tech",
            technician_status: "OFFLINE",
            current_jobs: 0,
            max_jobs: 5,
          },
        ],
      } as any);

      renderPlanningPage();

      await openDeclinedJobs();
      await openReassignmentModal();

      expect(
        screen.getByText(
          "No eligible technicians are currently available for reassignment."
        )
      ).toBeTruthy();

      const confirmButton = screen.getByRole("button", {
        name: /Confirm Reassign/i,
      }) as HTMLButtonElement;

      expect(confirmButton.disabled).toBeTruthy();
    });

    it("calls backend reassignment with selected technician", async () => {
      mockedReassignDeclinedJob.mockResolvedValue({
        data: {
          status: "success",
          job_id: 501,
          technician_id: 7,
        },
      } as any);

      renderPlanningPage();

      await openDeclinedJobs();
      await openReassignmentModal();

      selectReassignmentTechnician(7);

      fireEvent.click(
        screen.getByRole("button", {
          name: "Confirm Reassign",
        })
      );

      await screen.findByRole("dialog");

      fireEvent.click(
        screen.getByRole("button", {
          name: "Confirm Reassignment",
        })
      );

      await waitFor(() => {
        expect(
          mockedReassignDeclinedJob
        ).toHaveBeenCalledWith(501, 7);
      });
    });

    it("shows backend validation failure during reassignment", async () => {
      mockedReassignDeclinedJob.mockRejectedValue({
        response: {
          status: 409,
          data: {
            detail: "Job already reassigned.",
          },
          headers: {
            "x-correlation-id": "task9-409",
          },
        },
      });

      renderPlanningPage();

      await openDeclinedJobs();
      await openReassignmentModal();

      selectReassignmentTechnician(7);

      fireEvent.click(
        screen.getByRole("button", {
          name: "Confirm Reassign",
        })
      );

      await screen.findByRole("dialog");

      fireEvent.click(
        screen.getByRole("button", {
          name: "Confirm Reassignment",
        })
      );

      const alert = await screen.findByRole("alert");

      expect(alert.textContent).toContain("dispatch conflict");
      expect(alert.textContent).toContain(
        "Reference ID: task9-409"
      );
    });
  });
 

describe("PlanningPage - Manual Override", () => {
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

    mockedForceAssignEscalation.mockResolvedValue({
      data: {
        status: "success",
        job_id: 103,
        technician_id: "7",
      },
    } as any);
  });

  it("shows manual override as a separate dispatcher action", async () => {
    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("button", {
        name: /SLA Escalations/i,
      })
    );

    await waitFor(() => {
      expect(screen.getByText("#103")).toBeTruthy();
    });

    await selectTechnicianForJob(103);

    const forceAssignButton = screen.getByRole("button", {
      name: "Force Assign",
    });

    expect(forceAssignButton).toBeTruthy();

    fireEvent.click(forceAssignButton);

    const dialog = await screen.findByRole("dialog");

    expect(dialog.textContent).toContain("Manual Override");
    expect(dialog.textContent).toContain("Job #103");
    expect(dialog.textContent).toContain("Technician One");
  });

  it("clearly distinguishes manual override from AI technician recommendations", async () => {
    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("button", {
        name: /SLA Escalations/i,
      })
    );

    await waitFor(() => {
      expect(screen.getByText("#103")).toBeTruthy();
    });

    await selectTechnicianForJob(103);

    fireEvent.click(
      screen.getByRole("button", {
        name: "Force Assign",
      })
    );

    const dialog = await screen.findByRole("dialog");

    expect(dialog.textContent).toContain("Manual Override");
    expect(dialog.textContent).toContain(
      "separate from AI technician recommendations"
    );

    expect(
      screen.getByRole("note", {
        name: "Manual override notice",
      })
    ).toBeTruthy();
  });

  it("does not call the backend before explicit confirmation", async () => {
    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("button", {
        name: /SLA Escalations/i,
      })
    );

    await waitFor(() => {
      expect(screen.getByText("#103")).toBeTruthy();
    });

    await selectTechnicianForJob(103);

    fireEvent.click(
      screen.getByRole("button", {
        name: "Force Assign",
      })
    );

    await screen.findByRole("dialog");

    expect(mockedForceAssignEscalation).not.toHaveBeenCalled();
  });

  it("requires a justification before executing manual override", async () => {
    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("button", {
        name: /SLA Escalations/i,
      })
    );

    await waitFor(() => {
      expect(screen.getByText("#103")).toBeTruthy();
    });

    await selectTechnicianForJob(103);

    fireEvent.click(
      screen.getByRole("button", {
        name: "Force Assign",
      })
    );

    await screen.findByRole("dialog");

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Manual Override",
      })
    );

    const alert = await screen.findByRole("alert");

    expect(alert.textContent).toContain(
      "A reason is required before confirming this action."
    );

    expect(mockedForceAssignEscalation).not.toHaveBeenCalled();
  });

  it("sends the selected job, technician and justification to the authoritative backend", async () => {
    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("button", {
        name: /SLA Escalations/i,
      })
    );

    await waitFor(() => {
      expect(screen.getByText("#103")).toBeTruthy();
    });

    await selectTechnicianForJob(103);

    fireEvent.click(
      screen.getByRole("button", {
        name: "Force Assign",
      })
    );

    await screen.findByRole("dialog");

    fireEvent.change(
      screen.getByLabelText("Reason *"),
      {
        target: {
          value: "Dispatcher approved emergency reassignment",
        },
      }
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Manual Override",
      })
    );

    await waitFor(() => {
      expect(mockedForceAssignEscalation).toHaveBeenCalledWith(
        103,
        "7",
        "Dispatcher approved emergency reassignment"
      );
    });
  });

  it("shows backend permission failure without treating the override as successful", async () => {
    mockedForceAssignEscalation.mockRejectedValue({
      response: {
        status: 403,
        data: {
          detail: "Manual override is not permitted for this role.",
        },
      },
    });

    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("button", {
        name: /SLA Escalations/i,
      })
    );

    await waitFor(() => {
      expect(screen.getByText("#103")).toBeTruthy();
    });

    await selectTechnicianForJob(103);

    fireEvent.click(
      screen.getByRole("button", {
        name: "Force Assign",
      })
    );

    await screen.findByRole("dialog");

    fireEvent.change(
      screen.getByLabelText("Reason *"),
      {
        target: {
          value: "Dispatcher approved emergency reassignment",
        },
      }
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Manual Override",
      })
    );

    await waitFor(() => {
      expect(
        screen.getByRole("alert").textContent
      ).toContain(
        "You do not have permission to perform manual override."
      );
    });
  });

  it("shows backend validation failure for an invalid override", async () => {
    mockedForceAssignEscalation.mockRejectedValue({
      response: {
        status: 409,
        data: {
          detail:
            "Job has already been assigned by another dispatcher.",
        },
      },
    });

    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("button", {
        name: /SLA Escalations/i,
      })
    );

    await waitFor(() => {
      expect(screen.getByText("#103")).toBeTruthy();
    });

    await selectTechnicianForJob(103);

    fireEvent.click(
      screen.getByRole("button", {
        name: "Force Assign",
      })
    );

    await screen.findByRole("dialog");

    fireEvent.change(
      screen.getByLabelText("Reason *"),
      {
        target: {
          value: "Emergency dispatcher override",
        },
      }
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Manual Override",
      })
    );

    await waitFor(() => {
      expect(
        screen.getByRole("alert").textContent
      ).toContain(
        "Manual Override could not be completed because of a dispatch conflict"
      );
    });
  });

  it("does not report success when the backend override request fails", async () => {
    mockedForceAssignEscalation.mockRejectedValue({
      response: {
        status: 500,
        data: {
          detail: "Internal server error",
        },
      },
    });

    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("button", {
        name: /SLA Escalations/i,
      })
    );

    await waitFor(() => {
      expect(screen.getByText("#103")).toBeTruthy();
    });

    await selectTechnicianForJob(103);

    fireEvent.click(
      screen.getByRole("button", {
        name: "Force Assign",
      })
    );

    await screen.findByRole("dialog");

    fireEvent.change(
      screen.getByLabelText("Reason *"),
      {
        target: {
          value: "Emergency dispatcher override",
        },
      }
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Manual Override",
      })
    );

    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toContain(
        "The dispatch service could not complete manual override because of a server error."
      );
    });

    expect(
      screen.queryByText(
        "Job #103 force-assigned to Technician One."
      )
    ).toBeNull();
  });

  it("prevents duplicate manual override submission while the backend request is processing", async () => {
    let resolveRequest: (value: any) => void = () => {};

    mockedForceAssignEscalation.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveRequest = resolve;
        }) as any
    );

    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("button", {
        name: /SLA Escalations/i,
      })
    );

    await waitFor(() => {
      expect(screen.getByText("#103")).toBeTruthy();
    });

    await selectTechnicianForJob(103);

    fireEvent.click(
      screen.getByRole("button", {
        name: "Force Assign",
      })
    );

    await screen.findByRole("dialog");

    fireEvent.change(screen.getByLabelText("Reason *"), {
      target: {
        value: "Emergency dispatcher override",
      },
    });

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Manual Override",
      })
    );

    const processingButton = await screen.findByRole("button", {
      name: "Processing...",
    });

    expect(
      (processingButton as HTMLButtonElement).disabled
    ).toBe(true);

    fireEvent.click(processingButton);

    expect(mockedForceAssignEscalation).toHaveBeenCalledTimes(1);

    resolveRequest({
      data: {
        status: "success",
        job_id: 103,
        technician_id: "7",
      },
    });

    await waitFor(() => {
      expect(
        screen.queryByRole("button", {
          name: "Processing...",
        })
      ).toBeNull();
    });
  });

  it("prevents unavailable technicians from being selected for manual override", async () => {
    const unavailableTechnicians = [
      ...technicians,
      {
        technician_id: 9,
        technician_name: "Busy Technician",
        technician_skill: "HVAC",
        technician_status: "BUSY",
        current_jobs: 4,
        max_jobs: 5,
      },
      {
        technician_id: 10,
        technician_name: "Offline Technician",
        technician_skill: "HVAC",
        technician_status: "OFFLINE",
        current_jobs: 0,
        max_jobs: 5,
      },
    ];

    mockedGetTechnicians.mockResolvedValue({
      data: unavailableTechnicians,
    } as any);

    mockedGetAvailableTechnicians.mockResolvedValue({
      data: unavailableTechnicians,
    } as any);

    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("button", {
        name: /SLA Escalations/i,
      })
    );

    await waitFor(() => {
      expect(screen.getByText("#103")).toBeTruthy();
    });

    const jobRow = screen
      .getByText("#103")
      .closest("tr");

    expect(jobRow).toBeTruthy();

    const technicianSelect = jobRow!.querySelector(
      "select.tech-select-style"
    ) as HTMLSelectElement;

    expect(technicianSelect).toBeTruthy();

    const busyOption = Array.from(
      technicianSelect.options
    ).find(
      (option) =>
        option.value === "9"
    );

    const offlineOption = Array.from(
      technicianSelect.options
    ).find(
      (option) =>
        option.value === "10"
    );

    expect(busyOption?.disabled).toBe(true);
    expect(offlineOption?.disabled).toBe(true);
  });

  it("refreshes authoritative dispatcher data after successful manual override", async () => {
    renderPlanningPage();

    await waitForPendingJobs();

    const initialPendingJobCalls =
      mockedGetPendingJobs.mock.calls.length;

    fireEvent.click(
      screen.getByRole("button", {
        name: /SLA Escalations/i,
      })
    );

    await waitFor(() => {
      expect(screen.getByText("#103")).toBeTruthy();
    });

    await selectTechnicianForJob(103);

    fireEvent.click(
      screen.getByRole("button", {
        name: "Force Assign",
      })
    );

    await screen.findByRole("dialog");

    fireEvent.change(screen.getByLabelText("Reason *"), {
      target: {
        value: "Emergency dispatcher override",
      },
    });

    fireEvent.click(
      screen.getByRole("button", {
        name: "Confirm Manual Override",
      })
    );

    await waitFor(() => {
      expect(mockedForceAssignEscalation).toHaveBeenCalledWith(
        103,
        "7",
        "Emergency dispatcher override"
      );
    });

    await waitFor(() => {
      expect(
        mockedGetPendingJobs.mock.calls.length
      ).toBeGreaterThan(initialPendingJobCalls);
    });
  });
  
});


describe("PlanningPage - Task 11 Export Functionality", () => {
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
      data: [
        {
          job_id: 201,
          technician: "Technician One",
          skill: "HVAC",
          customer: "Customer One",
          location: "Chennai",
          priority: "HIGH",
          status: "IN_PROGRESS",
          current_jobs: 1,
          max_jobs: 5,
        },
      ],
      headers: {
        "x-total-count": "1",
      },
    } as any);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("renders the export action for the dispatcher dashboard", async () => {
    renderPlanningPage();

    await waitForPendingJobs();

    expect(
      screen.getByRole("button", {
        name: "Export visible dispatcher data",
      })
    ).toBeTruthy();
  });

  it("exports the currently visible pending jobs", async () => {
    const createObjectURL = vi
      .spyOn(URL, "createObjectURL")
      .mockReturnValue("blob:test");

    const revokeObjectURL = vi
      .spyOn(URL, "revokeObjectURL")
      .mockImplementation(() => {});

    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});

    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Export visible dispatcher data",
      })
    );

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:test");

    createObjectURL.mockRestore();
    revokeObjectURL.mockRestore();
    clickSpy.mockRestore();
  });

  it("does not export when the visible result is empty", async () => {
    mockedGetPendingJobs.mockResolvedValue({
      data: [],
      headers: {
        "x-total-count": "0",
      },
    } as any);

    const createObjectURL = vi
      .spyOn(URL, "createObjectURL")
      .mockReturnValue("blob:test");

    renderPlanningPage();

    // Wait until the empty backend result has been applied to the page.
    await screen.findByText(/0 results/, {}, { timeout: 5000 });

    const exportButton = screen.getByRole("button", {
      name: "Export visible dispatcher data",
    }) as HTMLButtonElement;

    expect(exportButton.disabled).toBe(true);

    fireEvent.click(exportButton);

    expect(createObjectURL).not.toHaveBeenCalled();

    createObjectURL.mockRestore();
  });

  it("does not export unsupported dispatcher tabs", async () => {
    renderPlanningPage();

    await waitForPendingJobs();

    fireEvent.click(
      screen.getByRole("button", {
        name: /^Dispatch Queue/,
      })
    );

    const exportButton = screen.getByRole("button", {
      name: "Export visible dispatcher data",
    }) as HTMLButtonElement;

    expect(exportButton.disabled).toBe(true);
  });
});

describe(
  "PlanningPage - Task 12 Real-Time Dashboard Updates",
  () => {
    beforeEach(() => {
      vi.clearAllMocks();

      mockSocketHandlers.clear();
      mockAnyHandlers.clear();
      mockSocket.active = true;

      vi.stubEnv(
        "VITE_DISPATCH_SOCKET_URL",
        "http://localhost:4000"
      );

      localStorage.setItem(
        "tenant_id",
        "tenant-1"
      );

      mockedGetTechnicians.mockResolvedValue({
        data: technicians,
      } as any);

      mockedGetAvailableTechnicians.mockResolvedValue({
        data: technicians,
      } as any);

      mockedGetPendingJobs.mockResolvedValue({
        data: pendingJobs,
        headers: {
          "x-total-count": String(
            pendingJobs.length
          ),
        },
      } as any);

      mockedGetPlannedAssignments.mockResolvedValue({
        data: [],
        headers: {
          "x-total-count": "0",
        },
      } as any);

      mockedGetDeclinedJobs.mockResolvedValue({
        data: [],
      } as any);
    });

    afterEach(() => {
      cleanup();

      localStorage.removeItem(
        "tenant_id"
      );

      vi.unstubAllEnvs();

      mockSocketHandlers.clear();
      mockAnyHandlers.clear();
    });

    it(
      "connects to the tenant-scoped dispatch dashboard namespace",
      async () => {
        renderPlanningPage();

        expect(mockedIo).toHaveBeenCalledWith(
          "http://localhost:4000/dispatch-dashboard",
          expect.objectContaining({
            auth: {
              tenant_id: "tenant-1",
            },
            reconnection: true,
            transports: [
              "websocket",
              "polling",
            ],
          })
        );

        emitMockSocketLifecycle("connect");

        expect(
          await screen.findByRole("status", {
            name:
              "Live dashboard updates: Connected",
          })
        ).toBeTruthy();
      }
    );

    it(
      "refreshes authoritative dashboard data after a realtime dispatch event",
      async () => {
        renderPlanningPage();

        emitMockSocketLifecycle("connect");

        await waitForPendingJobs();

        const initialCalls =
          mockedGetPendingJobs.mock.calls.length;

        const serverAuthoritativeJobs = [
          {
            ...pendingJobs[1],
            id: 204,
            customer_name:
              "Authoritative Customer",
          },
        ];

        mockedGetPendingJobs.mockResolvedValue({
          data: serverAuthoritativeJobs,
          headers: {
            "x-total-count": "1",
          },
        } as any);

        emitMockSocketEvent(
          "JOB_ASSIGNED",
          {
            event: "JOB_ASSIGNED",
            job_id: 204,
            old_status: "UNASSIGNED",
            new_status: "ASSIGNED",
            timestamp:
              "2026-09-21T10:00:00.000Z",
            tenant_id: "tenant-1",
            technician: {
              tech_id: "7",
              name: "Technician One",
            },
          }
        );

        await waitFor(
          () => {
            expect(
              mockedGetPendingJobs.mock.calls
                .length
            ).toBeGreaterThan(
              initialCalls
            );
          },
          {
            timeout: 5000,
          }
        );

        await waitFor(
          () => {
            expect(
              screen.getByText("#204")
            ).toBeTruthy();
          },
          {
            timeout: 5000,
          }
        );

        const latestCall =
          mockedGetPendingJobs.mock.calls[
            mockedGetPendingJobs.mock.calls.length - 1
          ]?.[0];

        expect(latestCall).toEqual(
          expect.objectContaining({
            page: 1,
            limit: 8,
          })
        );
      }
    );

    it(
      "coalesces duplicate realtime events into one refresh",
      async () => {
        renderPlanningPage();

        emitMockSocketLifecycle("connect");

        await waitForPendingJobs();

        const initialCalls =
          mockedGetPendingJobs.mock.calls.length;

        const duplicateEvent = {
          event: "JOB_COMPLETED",
          job_id: 101,
          old_status: "ASSIGNED",
          new_status: "COMPLETED",
          timestamp:
            "2026-09-21T10:05:00.000Z",
          tenant_id: "tenant-1",
          technician: {
            tech_id: "7",
            name: "Technician One",
          },
        };

        emitMockSocketEvent(
          "JOB_COMPLETED",
          duplicateEvent
        );

        emitMockSocketEvent(
          "JOB_COMPLETED",
          duplicateEvent
        );

        await waitFor(
          () => {
            expect(
              mockedGetPendingJobs.mock.calls
                .length
            ).toBe(
              initialCalls + 1
            );
          },
          {
            timeout: 5000,
          }
        );
      }
    );

    it(
      "ignores out-of-order realtime events for the same job",
      async () => {
        renderPlanningPage();

        emitMockSocketLifecycle("connect");

        await waitForPendingJobs();

        const initialCalls =
          mockedGetPendingJobs.mock.calls.length;

        emitMockSocketEvent(
          "JOB_UPDATED",
          {
            event: "JOB_UPDATED",
            job_id: 101,
            old_status: "ASSIGNED",
            new_status: "IN_PROGRESS",
            timestamp:
              "2026-09-21T10:10:00.000Z",
            tenant_id: "tenant-1",
          }
        );

        emitMockSocketEvent(
          "JOB_UPDATED",
          {
            event: "JOB_UPDATED",
            job_id: 101,
            old_status: "UNASSIGNED",
            new_status: "ASSIGNED",
            timestamp:
              "2026-09-21T10:09:00.000Z",
            tenant_id: "tenant-1",
          }
        );

        await waitFor(
          () => {
            expect(
              mockedGetPendingJobs.mock.calls
                .length
            ).toBe(
              initialCalls + 1
            );
          },
          {
            timeout: 5000,
          }
        );
      }
    );

    it(
      "ignores realtime events belonging to another tenant",
      async () => {
        renderPlanningPage();

        emitMockSocketLifecycle("connect");

        await waitForPendingJobs();

        const initialCalls =
          mockedGetPendingJobs.mock.calls.length;

        emitMockSocketEvent(
          "JOB_COMPLETED",
          {
            event: "JOB_COMPLETED",
            job_id: 101,
            old_status: "ASSIGNED",
            new_status: "COMPLETED",
            timestamp:
              "2026-09-21T10:20:00.000Z",
            tenant_id: "tenant-2",
          }
        );

        await new Promise((resolve) =>
          setTimeout(resolve, 400)
        );

        expect(
          mockedGetPendingJobs.mock.calls.length
        ).toBe(initialCalls);
      }
    );

    it(
      "shows reconnecting state and recovers after reconnect",
      async () => {
        renderPlanningPage();

        await act(async () => {
          emitMockSocketLifecycle(
            "disconnect",
            "transport close"
          );
        });

        expect(
          screen.getByRole("status", {
            name:
              /Live dashboard updates:/i,
          }).textContent
        ).toContain(
          "Reconnecting..."
        );

        await act(async () => {
          emitMockSocketLifecycle(
            "connect"
          );
        });

        expect(
          screen.getByRole("status", {
            name:
              /Live dashboard updates:/i,
          }).textContent
        ).toContain("Live");
      }
    );

    it(
      "shows an explicit realtime connection failure",
      async () => {
        renderPlanningPage();

        await act(async () => {
          emitMockSocketLifecycle(
            "connect_error",
            new Error(
              "Dispatch socket unavailable"
            )
          );
        });

        const status =
          screen.getByRole("status", {
            name:
              /Live dashboard updates:/i,
          });

        expect(status.textContent).toContain(
          "Live unavailable"
        );

        expect(status.getAttribute("aria-live")).toBe("polite");
      }
    );

    it(
      "refreshes all authoritative dashboard sources from a realtime event",
      async () => {
        renderPlanningPage();

        emitMockSocketLifecycle("connect");

        await waitForPendingJobs();

        const initialPendingCalls =
          mockedGetPendingJobs.mock.calls.length;

        const initialPlannedCalls =
          mockedGetPlannedAssignments.mock.calls.length;

        const initialTechnicianCalls =
          mockedGetTechnicians.mock.calls.length;

        emitMockSocketEvent(
          "JOB_COMPLETED",
          {
            event: "JOB_COMPLETED",
            job_id: 101,
            old_status: "IN_PROGRESS",
            new_status: "COMPLETED",
            timestamp:
              "2026-09-21T10:30:00.000Z",
            tenant_id: "tenant-1",
            technician: {
              tech_id: "7",
              name: "Technician One",
            },
          }
        );

        await waitFor(
          () => {
            expect(
              mockedGetPendingJobs.mock.calls
                .length
            ).toBeGreaterThan(
              initialPendingCalls
            );

            expect(
              mockedGetPlannedAssignments
                .mock.calls.length
            ).toBeGreaterThan(
              initialPlannedCalls
            );

            expect(
              mockedGetTechnicians.mock.calls
                .length
            ).toBeGreaterThan(
              initialTechnicianCalls
            );
          },
          {
            timeout: 5000,
          }
        );
      }
    );

    it(
      "surfaces an authoritative API failure triggered by realtime refresh",
      async () => {
        renderPlanningPage();

        emitMockSocketLifecycle("connect");

        await waitForPendingJobs();

        mockedGetPendingJobs.mockRejectedValue(
          new Error(
            "Realtime refresh failed"
          )
        );

        emitMockSocketEvent(
          "JOB_UPDATED",
          {
            event: "JOB_UPDATED",
            job_id: 101,
            old_status: "ASSIGNED",
            new_status: "IN_PROGRESS",
            timestamp:
              "2026-09-21T10:40:00.000Z",
            tenant_id: "tenant-1",
          }
        );

        await waitFor(
          () => {
            expect(
              screen.getByText(
                "Failed to load unassigned jobs. Please try again."
              )
            ).toBeTruthy();
          },
          {
            timeout: 5000,
          }
        );
      }
    );
  }
);