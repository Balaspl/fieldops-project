import {
  describe,
  it,
  expect,
  vi,
  beforeEach,
  afterEach,
} from "vitest";
import {
  render,
  screen,
  fireEvent,
  waitFor,
} from "@testing-library/react";
import React from "react";

import CustomerTrackingPage from "../../../pages/customer/CustomerTrackingPage";
import { getCustomerJobs } from "../../../services/customerPortalService";

/* -------------------------------------------------------------------------- */
/*                               Service Mocks                                */
/* -------------------------------------------------------------------------- */

vi.mock("../../../services/customerPortalService", () => ({
  getCustomerJobs: vi.fn(),
}));

/* -------------------------------------------------------------------------- */
/*                              Component Mocks                               */
/* -------------------------------------------------------------------------- */

vi.mock("../JobLiveTrackingMap", () => ({
  default: ({ jobId }: { jobId?: string | number }) => (
    <div data-testid="job-live-tracking-map">
      Live map for job {jobId ?? ""}
    </div>
  ),
}));

/* -------------------------------------------------------------------------- */
/*                                  Mocks                                     */
/* -------------------------------------------------------------------------- */

const mockedGetCustomerJobs = vi.mocked(getCustomerJobs);

/* -------------------------------------------------------------------------- */
/*                                Test Data                                   */
/* -------------------------------------------------------------------------- */

const completedJob = {
  id: 123,
  customer_name: "Alice",
  issue_description: "AC broken",
  service_type: "HVAC Repair",
  status: "COMPLETED",
  location: "123 Main St",
  site_address: "123 Main St",
  site_latitude: 13.0827,
  site_longitude: 80.2707,
  created_at: "2026-09-29T08:00:00.000Z",
  assigned_technician_id: "7",
  assigned_technician_name: "Vijay",
  assigned_technician_phone: "9876543210",
};

const activeJob = {
  id: 456,
  customer_name: "Bob",
  issue_description: "AC check",
  service_type: "HVAC Maintenance",
  status: "EN_ROUTE",
  location: "456 Main St",
  site_address: "456 Main St",
  site_latitude: 13.0827,
  site_longitude: 80.2707,
  created_at: "2026-09-29T08:30:00.000Z",
  assigned_technician_id: "7",
  assigned_technician_name: "Vijay",
  assigned_technician_phone: "9876543210",
  assigned_technician_photo: null,
  technician_latitude: 13.09,
  technician_longitude: 80.28,
};

/* -------------------------------------------------------------------------- */
/*                               Test Helpers                                 */
/* -------------------------------------------------------------------------- */

const renderPage = () =>
  render(
    <CustomerTrackingPage token="test-token" />
  );

/* -------------------------------------------------------------------------- */
/*                                   Tests                                    */
/* -------------------------------------------------------------------------- */

describe("CustomerTrackingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders loading state while customer jobs are being fetched", () => {
    mockedGetCustomerJobs.mockImplementation(
      () => new Promise(() => {})
    );

    renderPage();

    expect(
      screen.getByText("Loading job tracking...")
    ).toBeDefined();
  });

  it("renders the empty state when no customer jobs are returned", async () => {
    mockedGetCustomerJobs.mockResolvedValue({
      data: [],
    } as any);

    renderPage();

    await waitFor(() => {
      expect(
        screen.getByText(
          "No active or tracked jobs found."
        )
      ).toBeDefined();
    });

    expect(mockedGetCustomerJobs).toHaveBeenCalledTimes(1);
  });

  it("renders a completed customer job with completion state", async () => {
    mockedGetCustomerJobs.mockResolvedValue({
      data: [completedJob],
    } as any);

    renderPage();

    expect(
      await screen.findByText("JOB #123")
    ).toBeDefined();

    expect(
      screen.getByText("HVAC Repair")
    ).toBeDefined();

    expect(
      screen.getByText("✓ Service Completed")
    ).toBeDefined();

    expect(
      screen.getByText("Vijay")
    ).toBeDefined();
  });

  it("renders an en-route job and opens the live tracking map", async () => {
    mockedGetCustomerJobs.mockResolvedValue({
      data: [activeJob],
    } as any);

    renderPage();

    expect(
      await screen.findByText("JOB #456")
    ).toBeDefined();

    expect(
      screen.getByText("Real-Time Job Tracking")
    ).toBeDefined();

    expect(
      screen.getByText("EN ROUTE")
    ).toBeDefined();

    expect(
      screen.getByText("Vijay")
    ).toBeDefined();

    const liveMapButton =
      screen.getByRole("button", {
        name: "LIVE MAP",
      });

    expect(liveMapButton).toBeDefined();

    fireEvent.click(liveMapButton);

    expect(
      await screen.findByText(
        "Live Technician Tracking"
      )
    ).toBeDefined();

    expect(
      screen.getByTestId("job-live-tracking-map")
    ).toBeDefined();

    expect(
      screen.getByText(/Live map for job 456/)
    ).toBeDefined();
  });
});