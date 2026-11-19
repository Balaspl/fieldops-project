import React from "react";
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import CustomerTrackingPage from "../customer/CustomerTrackingPage";

import {
  getCustomerJobs,
} from "../../services/customerPortalService";

vi.mock(
  "../../services/customerPortalService",
  () => ({
    getCustomerJobs: vi.fn(),
  })
);

vi.mock(
  "../../components/customer-tracking/JobLiveTrackingMap",
  () => ({
    default: () => (
      <div data-testid="job-live-tracking-map">
        Mock Live Tracking Map
      </div>
    ),
  })
);

const mockedGetCustomerJobs =
  vi.mocked(getCustomerJobs);

const activeJob = {
  id: 101,
  status: "EN_ROUTE",
  service_type: "HVAC_REPAIR",
  location: "Chennai",
  site_address: "Chennai Service Address",
  site_latitude: 13.0827,
  site_longitude: 80.2707,
  created_at: "2026-09-24T10:00:00Z",
  completed_at: null,
  assigned_technician_id: "7",
  assigned_technician_name: "Technician One",
  assigned_technician_phone: "9876543210",
  assigned_technician_photo: null,
  assigned_technician_skills: ["HVAC", "Electrical"],
  assigned_technician_experience: "7 years",
  assigned_technician_certifications: ["EPA", "NATE"],
  technician_latitude: 13.075,
  technician_longitude: 80.265,
  tracking_tenant_id: "provider-tenant",
  estimated_arrival: "2026-09-30T17:05:00Z",
  eta_status: "calculated",
  eta_source: "calculated",
  eta_confidence: "high",
  eta_duration_minutes: 18,
  eta_distance_km: 7.2,
  eta_traffic_delay_minutes: 4,
  eta_message: "Live ETA",
  eta_updated_at: "2026-09-30T16:47:00Z",
};

const completedJob = {
  id: 102,
  status: "COMPLETED",
  service_type: "ELECTRICAL_SERVICE",
  location: "Coimbatore",
  site_address: "Coimbatore Service Address",
  site_latitude: 11.0168,
  site_longitude: 76.9558,
  created_at: "2026-09-20T10:00:00Z",
  completed_at: "2026-09-21T15:30:00Z",
  assigned_technician_id: "8",
  assigned_technician_name: "Technician Two",
  assigned_technician_phone: "9123456780",
  assigned_technician_photo: null,
  assigned_technician_skills: ["Electrical"],
  assigned_technician_experience: "5 years",
  assigned_technician_certifications: ["IEC Certified"],
  technician_latitude: null,
  technician_longitude: null,
  tracking_tenant_id: "provider-tenant",
};

const cancelledJob = {
  id: 103,
  status: "CANCELLED",
  service_type: "PLUMBING_SERVICE",
  location: "Bangalore",
  site_address: "Bangalore Service Address",
  site_latitude: 12.9716,
  site_longitude: 77.5946,
  created_at: "2026-09-18T09:00:00Z",
  completed_at: null,
  assigned_technician_id: null,
  assigned_technician_name: null,
  assigned_technician_phone: null,
  assigned_technician_photo: null,
  technician_latitude: null,
  technician_longitude: null,
  tracking_tenant_id: "provider-tenant",
};

beforeEach(() => {
  vi.resetAllMocks();

  mockedGetCustomerJobs.mockResolvedValue({
    data: [],
  } as any);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("CustomerTrackingPage - Task 6 ETA Display", () => {
  it("loads and displays the authenticated customer's jobs", async () => {
    mockedGetCustomerJobs.mockResolvedValue({
      data: [
        activeJob,
        completedJob,
      ],
    } as any);

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await waitFor(() => {
      expect(
        screen.getByText("JOB #101")
      ).toBeTruthy();

      expect(
        screen.getByText("JOB #102")
      ).toBeTruthy();
    });

    expect(
      screen.getByText("EN ROUTE")
    ).toBeTruthy();

    expect(
      screen.getByText("COMPLETED")
    ).toBeTruthy();

    const expectedEtaTime = new Date(
      activeJob.estimated_arrival
    ).toLocaleTimeString([], {
      hour: "numeric",
      minute: "2-digit",
    });

    expect(
      screen.getByTestId("eta-card-101")
    ).toBeTruthy();
    expect(
      screen.getAllByText("Estimated Arrival").length
    ).toBeGreaterThan(0);
    expect(
      screen.getByText(expectedEtaTime)
    ).toBeTruthy();
    expect(
      screen.getByText("LIVE ETA")
    ).toBeTruthy();
    expect(
      screen.getByText("Approximate travel time: 18 min")
    ).toBeTruthy();
    expect(
      screen.getByText("Route distance: 7.2 km")
    ).toBeTruthy();
    expect(
      screen.getByText("Traffic delay: +4 min")
    ).toBeTruthy();
    expect(
      screen.getByText("Live ETA")
    ).toBeTruthy();
  });

  it("renders an estimated ETA fallback when the backend marks route data as estimated", async () => {
    mockedGetCustomerJobs.mockResolvedValue({
      data: [
        {
          ...activeJob,
          estimated_arrival: "2026-09-30T17:20:00Z",
          eta_status: "estimated",
          eta_source: "estimated",
          eta_confidence: "low",
          eta_duration_minutes: 33,
          eta_distance_km: 12.4,
          eta_traffic_delay_minutes: null,
          eta_message: "ETA is estimated because live route data is unavailable.",
          eta_updated_at: "2026-09-30T16:48:00Z",
        },
      ],
    } as any);

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await waitFor(() => {
      expect(
        screen.getByTestId("eta-card-101")
      ).toBeTruthy();
    });

    expect(
      screen.getByText("ESTIMATED")
    ).toBeTruthy();
    expect(
      screen.getByText("Approximate travel time: 33 min")
    ).toBeTruthy();
    expect(
      screen.getByText("Route distance: 12.4 km")
    ).toBeTruthy();
    expect(
      screen.getByText(
        "ETA is estimated because live route data is unavailable."
      )
    ).toBeTruthy();
  });

  it("renders an unavailable ETA state when the backend cannot provide route data", async () => {
    mockedGetCustomerJobs.mockResolvedValue({
      data: [
        {
          ...activeJob,
          estimated_arrival: null,
          eta_status: "unavailable",
          eta_source: "unavailable",
          eta_confidence: null,
          eta_duration_minutes: null,
          eta_distance_km: null,
          eta_traffic_delay_minutes: null,
          eta_message: "ETA is currently unavailable.",
          eta_updated_at: null,
        },
      ],
    } as any);

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await waitFor(() => {
      expect(
        screen.getByTestId("eta-card-101")
      ).toBeTruthy();
    });

    expect(
      screen.getByText("Estimated Arrival")
    ).toBeTruthy();
    expect(
      screen.getByText("ETA is currently unavailable.")
    ).toBeTruthy();
    expect(
      screen.queryByText("LIVE ETA")
    ).toBeNull();
    expect(
      screen.queryByText("ESTIMATED")
    ).toBeNull();
  });

  it("does not render an ETA card before a technician is assigned", async () => {
    mockedGetCustomerJobs.mockResolvedValue({
      data: [
        {
          ...activeJob,
          assigned_technician_id: null,
          assigned_technician_name: null,
          assigned_technician_phone: null,
          estimated_arrival: "2026-09-30T17:05:00Z",
          eta_status: "calculated",
          eta_message: "Live ETA",
        },
      ],
    } as any);

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await waitFor(() => {
      expect(
        screen.getByText("JOB #101")
      ).toBeTruthy();
    });

    expect(
      screen.queryByTestId("eta-card-101")
    ).toBeNull();
  });

  it("reconciles the displayed ETA after an active-job refresh", async () => {
    vi.useFakeTimers();

    mockedGetCustomerJobs
      .mockResolvedValueOnce({
        data: [
          {
            ...activeJob,
            eta_status: "calculated",
            eta_source: "calculated",
            estimated_arrival: "2026-09-30T17:05:00Z",
            eta_duration_minutes: 18,
            eta_message: "Live ETA",
          },
        ],
      } as any)
      .mockResolvedValueOnce({
        data: [
          {
            ...activeJob,
            eta_status: "estimated",
            eta_source: "estimated",
            estimated_arrival: "2026-09-30T17:25:00Z",
            eta_duration_minutes: 38,
            eta_message: "ETA refreshed from fallback route data.",
          },
        ],
      } as any);

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(
      screen.getByText("LIVE ETA")
    ).toBeTruthy();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(
      screen.getByText("ESTIMATED")
    ).toBeTruthy();

    expect(
      screen.getByText("Approximate travel time: 38 min")
    ).toBeTruthy();
    expect(
      screen.getByText("ETA refreshed from fallback route data.")
    ).toBeTruthy();
  });

  it("keeps the previous ETA visible during a transient refresh failure", async () => {
    vi.useFakeTimers();

    mockedGetCustomerJobs
      .mockResolvedValueOnce({
        data: [
          {
            ...activeJob,
            eta_status: "calculated",
            estimated_arrival: "2026-09-30T17:05:00Z",
            eta_duration_minutes: 18,
            eta_message: "Live ETA",
          },
        ],
      } as any)
      .mockRejectedValueOnce({
        response: {
          status: 500,
        },
      });

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(
      screen.getByText("LIVE ETA")
    ).toBeTruthy();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(
      screen.getByText("We couldn't refresh your job tracking data.")
    ).toBeTruthy();
    expect(
      screen.getByText("LIVE ETA")
    ).toBeTruthy();
    expect(
      screen.getByText("Approximate travel time: 18 min")
    ).toBeTruthy();
  });

  it("falls back to the unavailable state when an ETA timestamp is invalid", async () => {
    mockedGetCustomerJobs.mockResolvedValue({
      data: [
        {
          ...activeJob,
          estimated_arrival: "not-a-valid-date",
          eta_status: "calculated",
          eta_source: "calculated",
          eta_message: "ETA data is temporarily unavailable.",
        },
      ],
    } as any);

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await waitFor(() => {
      expect(
        screen.getByTestId("eta-card-101")
      ).toBeTruthy();
    });

    expect(
      screen.getByText("ETA unavailable")
    ).toBeTruthy();
    expect(
      screen.getByText("ETA data is temporarily unavailable.")
    ).toBeTruthy();
  });

  it("does not display negative ETA duration or traffic delay values", async () => {
    mockedGetCustomerJobs.mockResolvedValue({
      data: [
        {
          ...activeJob,
          estimated_arrival: "2026-09-30T17:05:00Z",
          eta_status: "calculated",
          eta_duration_minutes: -5,
          eta_distance_km: 7.2,
          eta_traffic_delay_minutes: -2,
          eta_message: "Live ETA",
        },
      ],
    } as any);

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await waitFor(() => {
      expect(
        screen.getByTestId("eta-card-101")
      ).toBeTruthy();
    });

    expect(
      screen.queryByText("Approximate travel time: -5 min")
    ).toBeNull();
    expect(
      screen.queryByText("Traffic delay: +-2 min")
    ).toBeNull();
  });

  it("formats hour-scale ETA duration returned by the backend", async () => {
    mockedGetCustomerJobs.mockResolvedValue({
      data: [
        {
          ...activeJob,
          estimated_arrival: "2026-09-30T18:35:00Z",
          eta_status: "calculated",
          eta_duration_minutes: 90,
          eta_message: "Live ETA",
        },
      ],
    } as any);

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await waitFor(() => {
      expect(
        screen.getByText("Approximate travel time: 1h 30m")
      ).toBeTruthy();
    });
  });

  it("shows Arriving now for a sub-minute ETA", async () => {
    mockedGetCustomerJobs.mockResolvedValue({
      data: [
        {
          ...activeJob,
          estimated_arrival: "2026-09-30T17:05:00Z",
          eta_status: "calculated",
          eta_duration_minutes: 0.4,
          eta_message: "Live ETA",
        },
      ],
    } as any);

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await waitFor(() => {
      expect(
        screen.getByText("Approximate travel time: Arriving now")
      ).toBeTruthy();
    });
  });

  it("renders the completed date for completed historical jobs", async () => {
    mockedGetCustomerJobs.mockResolvedValue({
      data: [
        completedJob,
      ],
    } as any);

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await waitFor(() => {
      expect(
        screen.getByText("JOB #102")
      ).toBeTruthy();
    });

    expect(
      screen.getByText(
        `Created: ${new Date(
          completedJob.created_at
        ).toLocaleDateString()}`
      )
    ).toBeTruthy();

    expect(
      screen.getByText(
        `Completed: ${new Date(
          completedJob.completed_at
        ).toLocaleDateString()}`
      )
    ).toBeTruthy();
  });

  it("renders CANCELLED as a terminal historical state", async () => {
    mockedGetCustomerJobs.mockResolvedValue({
      data: [
        cancelledJob,
      ],
    } as any);

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await waitFor(() => {
      expect(
        screen.getByText("JOB #103")
      ).toBeTruthy();
    });

    expect(
      screen.getByText("CANCELLED")
    ).toBeTruthy();

    expect(
      screen.getByText("✕ Service Cancelled")
    ).toBeTruthy();

    expect(
      screen.queryByText(
        "✓ Service Completed"
      )
    ).toBeNull();
  });

  it("shows the empty state when no jobs are returned", async () => {
    mockedGetCustomerJobs.mockResolvedValue({
      data: [],
    } as any);

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await waitFor(() => {
      expect(
        screen.getByText(
          "No active or tracked jobs found."
        )
      ).toBeTruthy();
    });
  });

  it("shows the loading state before the jobs API resolves", async () => {
    let resolveRequest!: (
      value: any
    ) => void;

    mockedGetCustomerJobs.mockReturnValue(
      new Promise((resolve) => {
        resolveRequest = resolve;
      }) as any
    );

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    expect(
      screen.getByText(
        "Loading job tracking..."
      )
    ).toBeTruthy();

    resolveRequest({
      data: [
        completedJob,
      ],
    });

    await waitFor(() => {
      expect(
        screen.getByText("JOB #102")
      ).toBeTruthy();
    });
  });

  it("shows the authorization error when the API returns 403", async () => {
    mockedGetCustomerJobs.mockRejectedValue({
      response: {
        status: 403,
      },
    });

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await waitFor(() => {
      expect(
        screen.getByText(
          "You do not have permission to view these jobs."
        )
      ).toBeTruthy();
    });
  });

  it("shows the session-expired error when the API returns 401", async () => {
    mockedGetCustomerJobs.mockRejectedValue({
      response: {
        status: 401,
      },
    });

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await waitFor(() => {
      expect(
        screen.getByText(
          "Your session has expired. Please sign in again."
        )
      ).toBeTruthy();
    });
  });

  it("shows the generic refresh error for an unexpected API failure", async () => {
    mockedGetCustomerJobs.mockRejectedValue({
      response: {
        status: 500,
      },
    });

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await waitFor(() => {
      expect(
        screen.getByText(
          "We couldn't refresh your job tracking data."
        )
      ).toBeTruthy();
    });
  });

  it("keeps previously loaded jobs visible after a transient refresh failure", async () => {
    vi.useFakeTimers();

    mockedGetCustomerJobs
      .mockResolvedValueOnce({
        data: [
          activeJob,
        ],
      } as any)
      .mockRejectedValueOnce({
        response: {
          status: 500,
        },
      });

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(
      screen.getByText("JOB #101")
    ).toBeTruthy();

    expect(
      screen.getByText("HVAC_REPAIR")
    ).toBeTruthy();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(
        5000
      );
    });

    expect(
      screen.getByText(
        "We couldn't refresh your job tracking data."
      )
    ).toBeTruthy();

    expect(
      screen.getByText("JOB #101")
    ).toBeTruthy();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Dismiss",
      })
    );

    expect(
      screen.getByText("JOB #101")
    ).toBeTruthy();
  });

  it("opens the live map only for an EN_ROUTE job", async () => {
    mockedGetCustomerJobs.mockResolvedValue({
      data: [
        activeJob,
        completedJob,
      ],
    } as any);

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await waitFor(() => {
      expect(
        screen.getByText("LIVE MAP")
      ).toBeTruthy();
    });

    expect(
      screen.queryByTestId(
        "job-live-tracking-map"
      )
    ).toBeNull();

    fireEvent.click(
      screen.getByRole("button", {
        name: "LIVE MAP",
      })
    );

    expect(
      screen.getByTestId(
        "job-live-tracking-map"
      )
    ).toBeTruthy();
  });

  it("does not show live map for completed jobs", async () => {
    mockedGetCustomerJobs.mockResolvedValue({
      data: [
        completedJob,
      ],
    } as any);

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await waitFor(() => {
      expect(
        screen.getByText("JOB #102")
      ).toBeTruthy();
    });

    expect(
      screen.queryByRole("button", {
        name: "LIVE MAP",
      })
    ).toBeNull();
  });

  it("does not show live map for cancelled jobs", async () => {
    mockedGetCustomerJobs.mockResolvedValue({
      data: [
        cancelledJob,
      ],
    } as any);

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await waitFor(() => {
      expect(
        screen.getByText("JOB #103")
      ).toBeTruthy();
    });

    expect(
      screen.queryByRole("button", {
        name: "LIVE MAP",
      })
    ).toBeNull();
  });

  it("polls again while an active job exists", async () => {
    vi.useFakeTimers();

    mockedGetCustomerJobs
      .mockResolvedValueOnce({
        data: [
          activeJob,
        ],
      } as any)
      .mockResolvedValueOnce({
        data: [
          completedJob,
        ],
      } as any);

    render(
      <CustomerTrackingPage token="customer-token"
      />
    );

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(
      mockedGetCustomerJobs
    ).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(
        5000
      );
    });

    expect(
      mockedGetCustomerJobs
    ).toHaveBeenCalledTimes(2);

    expect(
      screen.getByText("JOB #102")
    ).toBeTruthy();
  });

  it("does not continue polling after only terminal jobs remain", async () => {
    vi.useFakeTimers();

    mockedGetCustomerJobs
      .mockResolvedValueOnce({
        data: [
          activeJob,
        ],
      } as any)
      .mockResolvedValueOnce({
        data: [
          completedJob,
          cancelledJob,
        ],
      } as any);

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await vi.waitFor(() => {
      expect(
        mockedGetCustomerJobs
      ).toHaveBeenCalledTimes(1);
    });

    await vi.advanceTimersByTimeAsync(
      5000
    );

    await vi.waitFor(() => {
      expect(
        mockedGetCustomerJobs
      ).toHaveBeenCalledTimes(2);
    });

    await vi.advanceTimersByTimeAsync(
      15000
    );

    expect(
      mockedGetCustomerJobs
    ).toHaveBeenCalledTimes(2);
  });

  it("clears the live map when the selected job becomes terminal", async () => {
    vi.useFakeTimers();

    mockedGetCustomerJobs
      .mockResolvedValueOnce({
        data: [
          activeJob,
        ],
      } as any)
      .mockResolvedValueOnce({
        data: [
          completedJob,
        ],
      } as any);

    render(
      <CustomerTrackingPage token="customer-token" />
    );

    await vi.waitFor(() => {
      expect(
        screen.getByRole("button", {
          name: "LIVE MAP",
        })
      ).toBeTruthy();
    });

    fireEvent.click(
      screen.getByRole("button", {
        name: "LIVE MAP",
      })
    );

    expect(
      screen.getByTestId(
        "job-live-tracking-map"
      )
    ).toBeTruthy();

    await vi.advanceTimersByTimeAsync(
      5000
    );

    await vi.waitFor(() => {
      expect(
        mockedGetCustomerJobs
      ).toHaveBeenCalledTimes(2);
    });

    await vi.waitFor(() => {
      expect(
        screen.queryByTestId(
          "job-live-tracking-map"
        )
      ).toBeNull();
    });
  });
});