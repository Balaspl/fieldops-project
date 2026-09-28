import {
  describe,
  expect,
  it,
  vi,
  beforeEach,
  afterEach,
} from "vitest";

import {
  render,
  screen,
  waitFor,
  fireEvent,
} from "@testing-library/react";

import TechnicianJobsPage from "../TechnicianJobsPage";

import {
  getTechnicianJobs,
  acceptTechnicianJob,
  rejectTechnicianJob,
  startTechnicianJob,
  onSiteTechnicianJob,
  completeTechnicianJob,
} from "../../../services/technicianPortalService";

vi.mock(
  "../../../services/technicianPortalService",
  () => ({
    getTechnicianJobs: vi.fn(),
    acceptTechnicianJob: vi.fn(),
    rejectTechnicianJob: vi.fn(),
    startTechnicianJob: vi.fn(),
    onSiteTechnicianJob: vi.fn(),
    pauseTechnicianJob: vi.fn(),
    resumeTechnicianJob: vi.fn(),
    completeTechnicianJob: vi.fn(),
  }),
);

vi.mock(
  "../../../components/jobs/JobClosureModal",
  () => ({
    JobClosureModal: ({
      jobId,
      onClose,
      onSuccess,
    }: {
      jobId: number;
      onClose: () => void;
      onSuccess: () => void;
    }) => (
      <div data-testid="job-closure-modal">
        <span>Closure Job #{jobId}</span>

        <button
          type="button"
          onClick={onClose}
        >
          Close Closure
        </button>

        <button
          type="button"
          onClick={onSuccess}
        >
          Complete Closure
        </button>
      </div>
    ),
  }),
);

vi.mock(
  "../../../components/jobs/CustomerSignatureModal",
  () => ({
    default: ({
      jobId,
      onClose,
      onSuccess,
    }: {
      jobId: number;
      onClose: () => void;
      onSuccess?: () => void;
    }) => (
      <div data-testid="customer-signature-modal">
        <span>
          Signature Job #{jobId}
        </span>

        <button
          type="button"
          onClick={onClose}
        >
          Close Signature
        </button>

        <button
          type="button"
          onClick={() => onSuccess?.()}
        >
          Save Customer Signature
        </button>
      </div>
    ),
  }),
);

const mockedGetTechnicianJobs =
  vi.mocked(getTechnicianJobs);

const mockedAcceptTechnicianJob =
  vi.mocked(acceptTechnicianJob);

const mockedRejectTechnicianJob =
  vi.mocked(rejectTechnicianJob);

const mockedStartTechnicianJob =
  vi.mocked(startTechnicianJob);

const mockedOnSiteTechnicianJob =
  vi.mocked(onSiteTechnicianJob);

const mockedCompleteTechnicianJob =
  vi.mocked(completeTechnicianJob);

type JobsResponse = Awaited<
  ReturnType<typeof getTechnicianJobs>
>;

const createJobsResponse = (
  jobs: unknown[] = [],
): JobsResponse =>
  ({
    data: jobs,
  }) as JobsResponse;

const representativeJob = {
  id: 101,
  service_type: "HVAC Repair",
  status: "ASSIGNED",
  priority: "HIGH",
  location: "Chennai",
  contact_number: "9876543210",
  preferred_service_date: "2026-09-26",
  preferred_service_time: "10:30 AM",
  issue_description:
    "Air conditioner is not cooling.",
  customer_name: "Test Customer",
};

describe(
  "TechnicianJobsPage - Assigned Job List",
  () => {
    beforeEach(() => {
      mockedGetTechnicianJobs.mockResolvedValue(
        createJobsResponse([
          representativeJob,
        ]),
      );

      mockedAcceptTechnicianJob.mockResolvedValue(
        { data: {} } as Awaited<
          ReturnType<typeof acceptTechnicianJob>
        >,
      );

      mockedRejectTechnicianJob.mockResolvedValue(
        { data: {} } as Awaited<
          ReturnType<typeof rejectTechnicianJob>
        >,
      );

      mockedStartTechnicianJob.mockResolvedValue(
        { data: {} } as Awaited<
          ReturnType<typeof startTechnicianJob>
        >,
      );

      mockedOnSiteTechnicianJob.mockResolvedValue(
        { data: {} } as Awaited<
          ReturnType<typeof onSiteTechnicianJob>
        >,
      );

      mockedCompleteTechnicianJob.mockResolvedValue(
        { data: {} } as Awaited<
          ReturnType<typeof completeTechnicianJob>
        >,
      );
    });

    afterEach(() => {
      vi.clearAllMocks();
    });

    it(
      "shows the loading state before the assigned-jobs API resolves",
      async () => {
        let resolveJobs:
          | ((value: JobsResponse) => void)
          | undefined;

        mockedGetTechnicianJobs.mockImplementation(
          () =>
            new Promise((resolve) => {
              resolveJobs = resolve;
            }),
        );

        render(<TechnicianJobsPage />);

        expect(
          screen.getByText(
            "Loading assigned jobs...",
          ),
        ).toBeTruthy();

        resolveJobs?.(
          createJobsResponse([
            representativeJob,
          ]),
        );

        await waitFor(() => {
          expect(
            screen.getByText(
              "Assigned Jobs",
            ),
          ).toBeTruthy();
        });
      },
    );

    it(
      "renders backend-authoritative assigned job data",
      async () => {
        render(<TechnicianJobsPage />);

        expect(
          (
            await screen.findAllByText(
              "HVAC Repair",
            )
          ).length,
        ).toBeGreaterThan(0);

        expect(
          screen.getByText("JOB #101"),
        ).toBeTruthy();

        expect(
          screen.getAllByText("HIGH").length,
        ).toBeGreaterThan(0);

        expect(
          screen.getAllByText(
            "AWAITING ACCEPTANCE",
          ).length,
        ).toBeGreaterThan(0);

        expect(
          screen.getAllByText("Chennai").length,
        ).toBeGreaterThan(0);

        expect(
          screen.getAllByText("9876543210").length,
        ).toBeGreaterThan(0);

        expect(
          screen.getAllByText(
            "2026-09-26 10:30 AM",
          ).length,
        ).toBeGreaterThan(0);

        expect(
          screen.getAllByText(
            "Air conditioner is not cooling.",
          ).length,
        ).toBeGreaterThan(0);
      },
    );

    it(
      "maps accepted, en-route and in-progress backend statuses",
      async () => {
        mockedGetTechnicianJobs.mockResolvedValue(
          createJobsResponse([
            {
              ...representativeJob,
              id: 201,
              status: "ACCEPTED",
            },
            {
              ...representativeJob,
              id: 202,
              status: "EN_ROUTE",
            },
            {
              ...representativeJob,
              id: 203,
              status: "IN_PROGRESS",
            },
          ]),
        );

        render(<TechnicianJobsPage />);

        expect(
          await screen.findByText("JOB #201"),
        ).toBeTruthy();

        expect(
          screen.getAllByText("ACCEPTED").length,
        ).toBeGreaterThan(0);

        expect(
          screen.getAllByText("EN ROUTE").length,
        ).toBeGreaterThan(0);

        expect(
          screen.getAllByText("IN PROGRESS").length,
        ).toBeGreaterThan(0);
      },
    );

    it(
      "maps schedule fields from the backend response",
      async () => {
        mockedGetTechnicianJobs.mockResolvedValue(
          createJobsResponse([
            {
              ...representativeJob,
              id: 301,
              preferred_service_date:
                "2026-10-01",
              preferred_service_time:
                "02:00 PM",
            },
          ]),
        );

        render(<TechnicianJobsPage />);

        expect(
          (
            await screen.findAllByText(
              "2026-10-01 02:00 PM",
            )
          ).length,
        ).toBeGreaterThan(0);
      },
    );

    it(
      "renders the explicit empty state when no assigned jobs are returned",
      async () => {
        mockedGetTechnicianJobs.mockResolvedValue(
          createJobsResponse([]),
        );

        render(<TechnicianJobsPage />);

        expect(
          await screen.findByText(
            "No active jobs assigned to you",
          ),
        ).toBeTruthy();

        expect(
          screen.getByText("0 job(s)"),
        ).toBeTruthy();
      },
    );

    it(
      "renders the explicit API error state",
      async () => {
        mockedGetTechnicianJobs.mockRejectedValue(
          new Error(
            "Technician jobs API unavailable",
          ),
        );

        const consoleError = vi
          .spyOn(console, "error")
          .mockImplementation(() => {});

        render(<TechnicianJobsPage />);

        expect(
          await screen.findByText(
            "Unable to load your assigned jobs. Please try again.",
          ),
        ).toBeTruthy();

        expect(
          screen.getByText(
            "Assigned jobs are currently unavailable.",
          ),
        ).toBeTruthy();

        consoleError.mockRestore();
      },
    );

    it(
      "handles an unavailable or non-array backend payload safely",
      async () => {
        mockedGetTechnicianJobs.mockResolvedValue(
          ({
            data: null,
          } as unknown) as JobsResponse,
        );

        render(<TechnicianJobsPage />);

        expect(
          await screen.findByText(
            "No active jobs assigned to you",
          ),
        ).toBeTruthy();

        expect(
          screen.getByText("0 job(s)"),
        ).toBeTruthy();
      },
    );

    it(
      "calls the existing authoritative accept API",
      async () => {
        mockedGetTechnicianJobs
          .mockResolvedValueOnce(
            createJobsResponse([
              representativeJob,
            ]),
          )
          .mockResolvedValueOnce(
            createJobsResponse([]),
          );

        render(<TechnicianJobsPage />);

        const acceptButtons =
          await screen.findAllByRole(
            "button",
            {
              name: "Accept",
            },
          );

        fireEvent.click(
          acceptButtons[0],
        );

        await waitFor(() => {
          expect(
            mockedAcceptTechnicianJob,
          ).toHaveBeenCalledWith(101);
        });

        await waitFor(() => {
          expect(
            mockedGetTechnicianJobs,
          ).toHaveBeenCalledTimes(2);
        });
      },
    );

    it(
      "opens the rejection flow and calls the backend rejection API",
      async () => {
        render(<TechnicianJobsPage />);

        const rejectButtons =
          await screen.findAllByRole(
            "button",
            {
              name: "Reject",
            },
          );

        fireEvent.click(
          rejectButtons[0],
        );

        expect(
          screen.getByText(
            "Reject Job #101",
          ),
        ).toBeTruthy();

        const textarea =
          screen.getByPlaceholderText(
            "Explain why you're rejecting this job...",
          );

        fireEvent.change(
          textarea,
          {
            target: {
              value:
                "Technician unavailable for this scheduled job.",
            },
          },
        );

        fireEvent.click(
          screen.getByRole(
            "button",
            {
              name: "Confirm Reject",
            },
          ),
        );

        await waitFor(() => {
          expect(
            mockedRejectTechnicianJob,
          ).toHaveBeenCalledWith(
            101,
            "Technician unavailable for this scheduled job.",
          );
        });
      },
    );

    it(
      "uses the existing status transition API for accepted jobs",
      async () => {
        mockedGetTechnicianJobs.mockResolvedValue(
          createJobsResponse([
            {
              ...representativeJob,
              id: 401,
              status: "ACCEPTED",
            },
          ]),
        );

        render(<TechnicianJobsPage />);

        const startButton =
          await screen.findByRole(
            "button",
            {
              name: "Start",
            },
          );

        fireEvent.click(startButton);

        await waitFor(() => {
          expect(
            mockedStartTechnicianJob,
          ).toHaveBeenCalledWith(401);
        });
      },
    );

    it(
      "exposes the en-route start action only for accepted jobs",
      async () => {
        mockedGetTechnicianJobs.mockResolvedValue(
          createJobsResponse([
            {
              ...representativeJob,
              id: 411,
              status: "ASSIGNED",
            },
            {
              ...representativeJob,
              id: 412,
              status: "EN_ROUTE",
            },
            {
              ...representativeJob,
              id: 413,
              status: "ACCEPTED",
            },
          ]),
        );

        render(<TechnicianJobsPage />);

        expect(
          await screen.findByText("JOB #411"),
        ).toBeTruthy();

        expect(
          screen.getAllByRole(
            "button",
            { name: "Start" },
          ).length,
        ).toBe(1);

        expect(
          screen.getAllByRole(
            "button",
            { name: "On Site" },
          ).length,
        ).toBe(1);

        expect(
          mockedStartTechnicianJob,
        ).not.toHaveBeenCalled();
      },
    );

    it(
      "refreshes the authoritative job state after starting an accepted job",
      async () => {
        mockedGetTechnicianJobs
          .mockResolvedValueOnce(
            createJobsResponse([
              {
                ...representativeJob,
                id: 421,
                status: "ACCEPTED",
              },
            ]),
          )
          .mockResolvedValueOnce(
            createJobsResponse([
              {
                ...representativeJob,
                id: 421,
                status: "EN_ROUTE",
              },
            ]),
          );

        render(<TechnicianJobsPage />);

        const startButton =
          await screen.findByRole(
            "button",
            { name: "Start" },
          );

        fireEvent.click(startButton);

        await waitFor(() => {
          expect(
            mockedStartTechnicianJob,
          ).toHaveBeenCalledWith(421);
        });

        await waitFor(() => {
          expect(
            mockedGetTechnicianJobs,
          ).toHaveBeenCalledTimes(2);
        });

        expect(
          await screen.findByRole(
            "button",
            { name: "On Site" },
          ),
        ).toBeTruthy();

        expect(
          screen.queryByRole(
            "button",
            { name: "Start" },
          ),
        ).toBeNull();
      },
    );

    it(
      "keeps the start action locked while the en-route transition is pending",
      async () => {
        let resolveStart:
          | ((value: Awaited<
              ReturnType<typeof startTechnicianJob>
            >) => void)
          | undefined;

        mockedGetTechnicianJobs.mockResolvedValue(
          createJobsResponse([
            {
              ...representativeJob,
              id: 431,
              status: "ACCEPTED",
            },
          ]),
        );

        mockedStartTechnicianJob.mockImplementation(
          () =>
            new Promise((resolve) => {
              resolveStart = resolve;
            }),
        );

        render(<TechnicianJobsPage />);

        const startButton =
          await screen.findByRole(
            "button",
            { name: "Start" },
          );

        fireEvent.click(startButton);

        await waitFor(() => {
          expect(
            mockedStartTechnicianJob,
          ).toHaveBeenCalledTimes(1);
        });

        expect(
          (
            screen.getByRole(
              "button",
              { name: "Start" },
            ) as HTMLButtonElement
          ).disabled,
        ).toBe(true);

        expect(
          screen.getByText("Starting..."),
        ).toBeTruthy();

        resolveStart?.(
          { data: {} } as Awaited<
            ReturnType<typeof startTechnicianJob>
          >,
        );

        await waitFor(() => {
          expect(
            mockedGetTechnicianJobs,
          ).toHaveBeenCalledTimes(2);
        });
      },
    );

    it(
      "uses the existing on-site API for en-route jobs",
      async () => {
        mockedGetTechnicianJobs.mockResolvedValue(
          createJobsResponse([
            {
              ...representativeJob,
              id: 501,
              status: "EN_ROUTE",
            },
          ]),
        );

        render(<TechnicianJobsPage />);

        const onSiteButton =
          await screen.findByRole(
            "button",
            {
              name: "On Site",
            },
          );

        fireEvent.click(onSiteButton);

        await waitFor(() => {
          expect(
            mockedOnSiteTechnicianJob,
          ).toHaveBeenCalledWith(501);
        });
      },
    );

    it(
      "exposes the on-site action only for en-route jobs",
      async () => {
        mockedGetTechnicianJobs.mockResolvedValue(
          createJobsResponse([
            {
              ...representativeJob,
              id: 701,
              status: "ACCEPTED",
            },
            {
              ...representativeJob,
              id: 702,
              status: "EN_ROUTE",
            },
            {
              ...representativeJob,
              id: 703,
              status: "IN_PROGRESS",
            },
          ]),
        );

        render(<TechnicianJobsPage />);

        expect(
          await screen.findByText("JOB #701"),
        ).toBeTruthy();

        expect(
          screen.getAllByRole(
            "button",
            { name: "On Site" },
          ).length,
        ).toBe(1);

        expect(
          mockedOnSiteTechnicianJob,
        ).not.toHaveBeenCalled();
      },
    );

    it(
      "refreshes the authoritative job state after marking an en-route job on site",
      async () => {
        mockedGetTechnicianJobs
          .mockResolvedValueOnce(
            createJobsResponse([
              {
                ...representativeJob,
                id: 711,
                status: "EN_ROUTE",
              },
            ]),
          )
          .mockResolvedValueOnce(
            createJobsResponse([
              {
                ...representativeJob,
                id: 711,
                status: "IN_PROGRESS",
              },
            ]),
          );

        render(<TechnicianJobsPage />);

        const onSiteButton =
          await screen.findByRole(
            "button",
            { name: "On Site" },
          );

        fireEvent.click(onSiteButton);

        await waitFor(() => {
          expect(
            mockedOnSiteTechnicianJob,
          ).toHaveBeenCalledWith(711);
        });

        await waitFor(() => {
          expect(
            mockedGetTechnicianJobs,
          ).toHaveBeenCalledTimes(2);
        });

        expect(
          await screen.findByRole(
            "button",
            { name: "Complete" },
          ),
        ).toBeTruthy();

        expect(
          screen.queryByRole(
            "button",
            { name: "On Site" },
          ),
        ).toBeNull();
      },
    );

    it(
      "keeps the on-site action locked while the transition is pending",
      async () => {
        let resolveOnSite:
          | ((value: Awaited<
              ReturnType<typeof onSiteTechnicianJob>
            >) => void)
          | undefined;

        mockedGetTechnicianJobs.mockResolvedValue(
          createJobsResponse([
            {
              ...representativeJob,
              id: 721,
              status: "EN_ROUTE",
            },
          ]),
        );

        mockedOnSiteTechnicianJob.mockImplementation(
          () =>
            new Promise((resolve) => {
              resolveOnSite = resolve;
            }),
        );

        render(<TechnicianJobsPage />);

        const onSiteButton =
          await screen.findByRole(
            "button",
            { name: "On Site" },
          );

        fireEvent.click(onSiteButton);
        fireEvent.click(onSiteButton);

        await waitFor(() => {
          expect(
            mockedOnSiteTechnicianJob,
          ).toHaveBeenCalledTimes(1);
        });

        expect(
          (
            screen.getByRole(
              "button",
              { name: "On Site" },
            ) as HTMLButtonElement
          ).disabled,
        ).toBe(true);

        expect(
          screen.getByText("Updating..."),
        ).toBeTruthy();

        resolveOnSite?.(
          { data: {} } as Awaited<
            ReturnType<typeof onSiteTechnicianJob>
          >,
        );

        await waitFor(() => {
          expect(
            mockedGetTechnicianJobs,
          ).toHaveBeenCalledTimes(2);
        });
      },
    );

    it(
      "surfaces a backend on-site validation or permission failure and refreshes state",
      async () => {
        mockedGetTechnicianJobs.mockResolvedValue(
          createJobsResponse([
            {
              ...representativeJob,
              id: 731,
              status: "EN_ROUTE",
            },
          ]),
        );

        mockedOnSiteTechnicianJob.mockRejectedValue({
          response: {
            data: {
              detail:
                "GPS must be active before marking the job on site.",
            },
          },
        });

        const alertMock = vi
          .spyOn(window, "alert")
          .mockImplementation(() => {});

        render(<TechnicianJobsPage />);

        const onSiteButton =
          await screen.findByRole(
            "button",
            { name: "On Site" },
          );

        fireEvent.click(onSiteButton);

        await waitFor(() => {
          expect(
            alertMock,
          ).toHaveBeenCalledWith(
            "GPS must be active before marking the job on site.",
          );
        });

        await waitFor(() => {
          expect(
            mockedGetTechnicianJobs,
          ).toHaveBeenCalledTimes(2);
        });

        alertMock.mockRestore();
      },
    );

    it(
      "surfaces a generic on-site API failure without inventing client-side state",
      async () => {
        mockedGetTechnicianJobs.mockResolvedValue(
          createJobsResponse([
            {
              ...representativeJob,
              id: 741,
              status: "EN_ROUTE",
            },
          ]),
        );

        mockedOnSiteTechnicianJob.mockRejectedValue(
          new Error("On-site API unavailable"),
        );

        const alertMock = vi
          .spyOn(window, "alert")
          .mockImplementation(() => {});

        render(<TechnicianJobsPage />);

        const onSiteButton =
          await screen.findByRole(
            "button",
            { name: "On Site" },
          );

        fireEvent.click(onSiteButton);

        await waitFor(() => {
          expect(
            alertMock,
          ).toHaveBeenCalledWith(
            "Unable to mark this job as on site. Please try again.",
          );
        });

        await waitFor(() => {
          expect(
            mockedGetTechnicianJobs,
          ).toHaveBeenCalledTimes(2);
        });

        expect(
          screen.getByText("EN ROUTE"),
        ).toBeTruthy();

        alertMock.mockRestore();
      },
    );

    it(
      "opens the existing completion workflow only for an eligible in-progress job",
      async () => {
        mockedGetTechnicianJobs.mockResolvedValue(
          createJobsResponse([
            {
              ...representativeJob,
              id: 601,
              status: "IN_PROGRESS",
            },
            {
              ...representativeJob,
              id: 602,
              status: "EN_ROUTE",
            },
            {
              ...representativeJob,
              id: 603,
              status: "ACCEPTED",
            },
          ]),
        );

        render(<TechnicianJobsPage />);

        expect(
          await screen.findByText("JOB #601"),
        ).toBeTruthy();

        expect(
          screen.getAllByRole(
            "button",
            { name: "Complete" },
          ).length,
        ).toBe(1);

        const completeButton =
          screen.getByRole(
            "button",
            { name: "Complete" },
          );

        fireEvent.click(completeButton);

        expect(
          screen.getByTestId(
            "job-closure-modal",
          ),
        ).toBeTruthy();

        expect(
          screen.getByText(
            "Closure Job #601",
          ),
        ).toBeTruthy();

        expect(
          mockedCompleteTechnicianJob,
        ).not.toHaveBeenCalled();
      },
    );

    it(
      "does not expose completion for an invalid current state",
      async () => {
        mockedGetTechnicianJobs.mockResolvedValue(
          createJobsResponse([
            {
              ...representativeJob,
              id: 611,
              status: "EN_ROUTE",
            },
          ]),
        );

        render(<TechnicianJobsPage />);

        expect(
          await screen.findByText("JOB #611"),
        ).toBeTruthy();

        expect(
          screen.queryByRole(
            "button",
            { name: "Complete" },
          ),
        ).toBeNull();

        expect(
          screen.queryByTestId(
            "job-closure-modal",
          ),
        ).toBeNull();

        expect(
          mockedCompleteTechnicianJob,
        ).not.toHaveBeenCalled();
      },
    );

    it(
      "refreshes the authoritative job state after the completion workflow succeeds",
      async () => {
        mockedGetTechnicianJobs
          .mockResolvedValueOnce(
            createJobsResponse([
              {
                ...representativeJob,
                id: 621,
                status: "IN_PROGRESS",
              },
            ]),
          )
          .mockResolvedValueOnce(
            createJobsResponse([
              {
                ...representativeJob,
                id: 621,
                status: "COMPLETED",
              },
            ]),
          );

        const refreshEventListener =
          vi.fn();

        window.addEventListener(
          "technician-dashboard-refresh",
          refreshEventListener,
        );

        render(<TechnicianJobsPage />);

        const completeButton =
          await screen.findByRole(
            "button",
            { name: "Complete" },
          );

        fireEvent.click(completeButton);

        fireEvent.click(
          screen.getByRole(
            "button",
            { name: "Complete Closure" },
          ),
        );

        await waitFor(() => {
          expect(
            mockedGetTechnicianJobs,
          ).toHaveBeenCalledTimes(2);
        });

        expect(
          screen.queryByTestId(
            "job-closure-modal",
          ),
        ).toBeNull();

        expect(
          refreshEventListener,
        ).toHaveBeenCalledTimes(1);

        window.removeEventListener(
          "technician-dashboard-refresh",
          refreshEventListener,
        );
      },
    );

    it(
      "does not submit completion directly from the page",
      async () => {
        mockedGetTechnicianJobs.mockResolvedValue(
          createJobsResponse([
            {
              ...representativeJob,
              id: 631,
              status: "PAUSED",
            },
          ]),
        );

        render(<TechnicianJobsPage />);

        const completeButton =
          await screen.findByRole(
            "button",
            { name: "Complete" },
          );

        fireEvent.click(completeButton);

        expect(
          screen.getByTestId(
            "job-closure-modal",
          ),
        ).toBeTruthy();

        expect(
          mockedCompleteTechnicianJob,
        ).not.toHaveBeenCalled();
      },
    );
    it(
      "opens the customer signature screen after authoritative job completion",
      async () => {
        mockedGetTechnicianJobs.mockResolvedValue(
          createJobsResponse([
            {
              ...representativeJob,
              id: 801,
              status: "IN_PROGRESS",
            },
          ]),
        );

        render(<TechnicianJobsPage />);

        fireEvent.click(
          await screen.findByRole(
            "button",
            {
              name: "Complete",
            },
          ),
        );

        expect(
          screen.getByTestId(
            "job-closure-modal",
          ),
        ).toBeTruthy();

        fireEvent.click(
          screen.getByRole(
            "button",
            {
              name: "Complete Closure",
            },
          ),
        );

        expect(
          await screen.findByTestId(
            "customer-signature-modal",
          ),
        ).toBeTruthy();

        expect(
          screen.getByText(
            "Signature Job #801",
          ),
        ).toBeTruthy();
      },
    );

    it(
      "closes the customer signature screen and reconciles jobs after signature success",
      async () => {
        mockedGetTechnicianJobs.mockResolvedValue(
          createJobsResponse([
            {
              ...representativeJob,
              id: 811,
              status: "IN_PROGRESS",
            },
          ]),
        );

        render(<TechnicianJobsPage />);

        fireEvent.click(
          await screen.findByRole(
            "button",
            {
              name: "Complete",
            },
          ),
        );

        fireEvent.click(
          screen.getByRole(
            "button",
            {
              name: "Complete Closure",
            },
          ),
        );

        await screen.findByTestId(
          "customer-signature-modal",
        );

        const callsBeforeSignature =
          mockedGetTechnicianJobs.mock.calls.length;

        fireEvent.click(
          screen.getByRole(
            "button",
            {
              name: "Save Customer Signature",
            },
          ),
        );

        await waitFor(() => {
          expect(
            screen.queryByTestId(
              "customer-signature-modal",
            ),
          ).toBeNull();

          expect(
            mockedGetTechnicianJobs.mock.calls.length,
          ).toBeGreaterThan(
            callsBeforeSignature,
          );
        });
      },
    );
  },
);