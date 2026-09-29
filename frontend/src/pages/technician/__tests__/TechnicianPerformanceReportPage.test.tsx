import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import TechnicianPerformanceReportPage from "../TechnicianPerformanceReportPage";

import {
  getTechnicianDashboard,
} from "../../../services/technicianPortalService";

vi.mock(
  "../../../services/technicianPortalService",
  () => ({
    getTechnicianDashboard: vi.fn(),
  }),
);

const mockedGetTechnicianDashboard = vi.mocked(
  getTechnicianDashboard,
);

type DashboardResponse = Awaited<
  ReturnType<typeof getTechnicianDashboard>
>;

const createDashboardResponse = (
  data: unknown = {},
): DashboardResponse =>
  ({
    data,
  }) as DashboardResponse;

const representativePerformance = {
  total_assigned: 24,
  active_jobs: 5,
  completed_today: 3,
  total_completed: 118,
  pending_acceptance: 2,
  rejected_jobs: 1,
  technician_status: "IN_PROGRESS",
  profile_completed: true,
};

describe(
  "TechnicianPerformanceReportPage",
  () => {
    beforeEach(() => {
      mockedGetTechnicianDashboard.mockResolvedValue(
        createDashboardResponse(
          representativePerformance,
        ),
      );
    });

    afterEach(() => {
      vi.clearAllMocks();
    });

    it(
      "calls the existing technician dashboard API on mount",
      async () => {
        render(<TechnicianPerformanceReportPage />);

        await waitFor(() => {
          expect(
            mockedGetTechnicianDashboard,
          ).toHaveBeenCalledTimes(1);
        });
      },
    );

    it(
      "shows the loading state while the backend request is pending",
      async () => {
        let resolveRequest:
          | ((value: DashboardResponse) => void)
          | undefined;

        mockedGetTechnicianDashboard.mockImplementation(
          () =>
            new Promise((resolve) => {
              resolveRequest = resolve;
            }),
        );

        render(<TechnicianPerformanceReportPage />);

        expect(
          screen.getByText(
            "Loading technician performance report...",
          ),
        ).toBeTruthy();

        resolveRequest?.(
          createDashboardResponse(
            representativePerformance,
          ),
        );

        expect(
          await screen.findByText(
            "Technician Performance Report",
          ),
        ).toBeTruthy();
      },
    );

    it(
      "renders backend-authoritative performance values without recomputing them",
      async () => {
        render(<TechnicianPerformanceReportPage />);

        expect(
          await screen.findByText(
            "Technician Performance Report",
          ),
        ).toBeTruthy();

        expect(
          screen.getAllByText("24").length,
        ).toBeGreaterThan(0);
        expect(
          screen.getAllByText("5").length,
        ).toBeGreaterThan(0);
        expect(
          screen.getAllByText("3").length,
        ).toBeGreaterThan(0);
        expect(
          screen.getAllByText("118").length,
        ).toBeGreaterThan(0);
        expect(
          screen.getAllByText("2").length,
        ).toBeGreaterThan(0);
        expect(
          screen.getAllByText("1").length,
        ).toBeGreaterThan(0);

        expect(
          screen.getAllByText("In Progress").length,
        ).toBeGreaterThan(0);

        expect(
          screen.getAllByText("Yes").length,
        ).toBeGreaterThan(0);

        expect(
          screen.getByText(
            "Backend-authoritative performance metrics for the authenticated technician.",
          ),
        ).toBeTruthy();

        expect(
          screen.getByText(
            "These values are presented directly from the technician dashboard API. No authoritative KPI is recomputed in the client.",
          ),
        ).toBeTruthy();
      },
    );

    it(
      "renders the explicit empty state when the backend returns no data",
      async () => {
        mockedGetTechnicianDashboard.mockResolvedValue(
          createDashboardResponse(null),
        );

        render(<TechnicianPerformanceReportPage />);

        expect(
          await screen.findByText(
            "No technician performance data is currently available.",
          ),
        ).toBeTruthy();

        expect(
          screen.queryByText("Total Assigned"),
        ).toBeNull();
      },
    );

    it(
      "shows the no-activity message when all backend metrics are zero",
      async () => {
        mockedGetTechnicianDashboard.mockResolvedValue(
          createDashboardResponse({
            total_assigned: 0,
            active_jobs: 0,
            completed_today: 0,
            total_completed: 0,
            pending_acceptance: 0,
            rejected_jobs: 0,
            technician_status: "AVAILABLE",
            profile_completed: false,
          }),
        );

        render(<TechnicianPerformanceReportPage />);

        expect(
          await screen.findByText(
            "The backend currently reports no recorded job activity for this technician.",
          ),
        ).toBeTruthy();

        expect(
          screen.getAllByText("0").length,
        ).toBeGreaterThan(0);

        expect(
          screen.getAllByText("Available").length,
        ).toBeGreaterThan(0);

        expect(
          screen.getAllByText("No").length,
        ).toBeGreaterThan(0);
      },
    );

    it(
      "renders the generic API error state",
      async () => {
        mockedGetTechnicianDashboard.mockRejectedValue(
          new Error("Dashboard API unavailable"),
        );

        const consoleError = vi
          .spyOn(console, "error")
          .mockImplementation(() => {});

        render(<TechnicianPerformanceReportPage />);

        expect(
          await screen.findByRole("alert"),
        ).toBeTruthy();

        expect(
          screen.getByText(
            "Technician performance data is temporarily unavailable. Please try again.",
          ),
        ).toBeTruthy();

        consoleError.mockRestore();
      },
    );

    it(
      "shows the backend authorization message for a 403 response",
      async () => {
        mockedGetTechnicianDashboard.mockRejectedValue({
          response: {
            status: 403,
          },
        });

        const consoleError = vi
          .spyOn(console, "error")
          .mockImplementation(() => {});

        render(<TechnicianPerformanceReportPage />);

        expect(
          await screen.findByText(
            "You are not authorized to view your technician performance report.",
          ),
        ).toBeTruthy();

        consoleError.mockRestore();
      },
    );

    it(
      "shows the unavailable-data message for a 404 response",
      async () => {
        mockedGetTechnicianDashboard.mockRejectedValue({
          response: {
            status: 404,
          },
        });

        const consoleError = vi
          .spyOn(console, "error")
          .mockImplementation(() => {});

        render(<TechnicianPerformanceReportPage />);

        expect(
          await screen.findByText(
            "Technician performance data is not available.",
          ),
        ).toBeTruthy();

        consoleError.mockRestore();
      },
    );

    it(
      "refreshes from the same authoritative backend source",
      async () => {
        mockedGetTechnicianDashboard
          .mockResolvedValueOnce(
            createDashboardResponse({
              ...representativePerformance,
              active_jobs: 5,
            }),
          )
          .mockResolvedValueOnce(
            createDashboardResponse({
              ...representativePerformance,
              active_jobs: 7,
            }),
          );

        render(<TechnicianPerformanceReportPage />);

        expect(
          await screen.findByText("Technician Performance Report"),
        ).toBeTruthy();

        const getMetricRow = (label: string) =>
          screen.getAllByRole("row").find((row) =>
            row.textContent?.includes(label),
          );

        expect(getMetricRow("Active Jobs")?.textContent).toContain("5");

        const refreshButton =
          screen.getByRole("button", {
            name: "Refresh technician performance report",
          });

        fireEvent.click(refreshButton);

        await waitFor(() => {
          expect(
            mockedGetTechnicianDashboard,
          ).toHaveBeenCalledTimes(2);
        });

        const activeJobsRow = screen
          .getAllByRole("row")
          .find((row) => row.textContent?.includes("Active Jobs"));

        expect(activeJobsRow?.textContent).toContain("7");
      },
    );

    it(
      "normalizes missing numeric backend values to a display-safe zero",
      async () => {
        mockedGetTechnicianDashboard.mockResolvedValue(
          createDashboardResponse({
            technician_status: null,
            profile_completed: false,
          }),
        );

        render(<TechnicianPerformanceReportPage />);

        expect(
          await screen.findByText("Technician Performance Report"),
        ).toBeTruthy();

        const metricLabels = [
          "Total Assigned",
          "Active Jobs",
          "Completed Today",
          "Total Completed",
          "Pending Acceptance",
          "Rejected Jobs",
        ];

        for (const label of metricLabels) {
          const row = screen
            .getAllByRole("row")
            .find((candidate) =>
              candidate.textContent?.includes(label),
            );

          expect(row).toBeTruthy();
          expect(row?.querySelector("td:last-child")?.textContent).toBe("0");
        }

        expect(
          screen.getAllByText("Not Available").length,
        ).toBeGreaterThan(0);
      },
    );
  },
);
