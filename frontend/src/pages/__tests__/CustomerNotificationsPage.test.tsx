import { beforeEach, describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import CustomerNotificationsPage from "../customer/CustomerNotificationsPage";
import {
  getCustomerNotifications,
  getCustomerJobs,
  markAllCustomerNotificationsRead,
  markCustomerNotificationRead,
} from "../../services/customerPortalService";

const socketMocks = vi.hoisted(() => ({
  handlers: new Map<string, (payload?: any) => void>(),
  on: vi.fn((event: string, handler: (payload?: any) => void) => {
    socketMocks.handlers.set(event, handler);
  }),
  off: vi.fn(),
  disconnect: vi.fn(),
  removeAllListeners: vi.fn(),
}));

vi.mock("socket.io-client", () => ({
  io: vi.fn(() => socketMocks),
}));

vi.mock("../../services/customerPortalService", () => ({
  getCustomerNotifications: vi.fn(),
  getCustomerJobs: vi.fn(),
  markCustomerNotificationRead: vi.fn(),
  markAllCustomerNotificationsRead: vi.fn(),
}));

const initial = {
  id: "card-1",
  title: "Maya is on the way",
  body: "Your repair technician has started the trip.",
  status: "UNREAD",
  created_at: new Date(Date.now() - 5 * 60_000).toISOString(),
  job_id: 81,
  group_key: "job_81",
  event_version: 1,
  type: "en_route",
  metadata: { steps: ["Booked", "Accepted", "On the way"], step: 2 },
};

const response = (notifications: any[] = [initial]) => ({
  data: { notifications, unread_count: notifications.length },
});

describe("CustomerNotificationsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    socketMocks.handlers.clear();
    vi.mocked(getCustomerNotifications).mockResolvedValue(response() as any);
    vi.mocked(getCustomerJobs).mockResolvedValue({ data: [] } as any);
    vi.mocked(markCustomerNotificationRead).mockResolvedValue({} as any);
    vi.mocked(markAllCustomerNotificationsRead).mockResolvedValue({} as any);
  });

  it("renders event-specific icon, relative time, progress and read action", async () => {
    render(<CustomerNotificationsPage />);
    expect(await screen.findByText("Maya is on the way")).toBeTruthy();
    expect(screen.getByText("5 minutes ago")).toBeTruthy();
    expect(screen.getByTestId("job-progress-81")).toHaveAttribute("data-stage", "2");
    expect(screen.getByText("Job #81")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Mark as read" }));
    await waitFor(() => expect(markCustomerNotificationRead).toHaveBeenCalledWith("card-1"));
    expect(await screen.findByText("Read")).toBeTruthy();
  });

  it("marks all loaded customer cards read", async () => {
    render(<CustomerNotificationsPage />);
    fireEvent.click(await screen.findByRole("button", { name: /mark all as read/i }));
    await waitFor(() => expect(markAllCustomerNotificationsRead).toHaveBeenCalledOnce());
    expect(await screen.findByText("Read")).toBeTruthy();
  });

  it("replaces a job card from a newer live event and ignores a stale version", async () => {
    render(<CustomerNotificationsPage />);
    await screen.findByText("Maya is on the way");
    const indicator = screen.getByTestId("job-progress-indicator-81");
    expect(indicator).toHaveStyle({ left: "41.5%" });
    const live = socketMocks.handlers.get("new_notification");
    expect(live).toBeDefined();
    act(() => {
      live?.({ ...initial, title: "Maya has arrived", body: "At your door.", event_version: 2, type: undefined, event: "on_site" });
    });
    expect(await screen.findByText("Maya has arrived")).toBeTruthy();
    expect(screen.getByTestId("job-progress-81")).toHaveAttribute("data-stage", "3");
    expect(indicator).toHaveStyle({ left: "58.5%" });
    act(() => {
      live?.({ ...initial, id: "card-old", title: "Old trip update", event_version: 1 });
    });
    expect(screen.queryByText("Old trip update")).toBeNull();
    expect(screen.getAllByRole("article")).toHaveLength(1);
  });

  it("uses customer job status and real ETA data, updating ETA without advancing stage", async () => {
    vi.mocked(getCustomerJobs).mockResolvedValue({
      data: [{
        id: 81,
        status: "EN_ROUTE",
        estimated_arrival: "2026-10-16T13:30:00.000Z",
        eta_duration_minutes: 15,
        eta_distance_km: 5,
        eta_traffic_delay_minutes: 0,
        eta_status: "calculated",
        eta_updated_at: "2026-10-16T13:10:00.000Z",
        eta_message: null,
        on_site_at: null,
        work_started_at: null,
        completed_at: null,
        assigned_technician_name: "Maya",
      }],
    } as any);
    render(<CustomerNotificationsPage />);

    expect(await screen.findByText("About 15 min away")).toBeTruthy();
    expect(screen.getByTestId("job-progress-81")).toHaveAttribute("data-stage", "2");

    vi.mocked(getCustomerJobs).mockResolvedValue({
      data: [{
        id: 81,
        status: "EN_ROUTE",
        estimated_arrival: "2026-10-16T13:35:00.000Z",
        eta_duration_minutes: 20,
        eta_distance_km: 6,
        eta_traffic_delay_minutes: 0,
        eta_status: "calculated",
        eta_updated_at: "2026-10-16T13:15:00.000Z",
        eta_message: null,
        on_site_at: null,
        work_started_at: null,
        completed_at: null,
        assigned_technician_name: "Maya",
      }],
    } as any);
    act(() => {
      socketMocks.handlers.get("connect")?.();
    });

    expect(await screen.findByText("About 20 min away")).toBeTruthy();
    expect(screen.getByTestId("job-progress-81")).toHaveAttribute("data-stage", "2");
  });

  it.each([
    ["completed", "COMPLETED", 5, "job-progress-82"],
    ["cancelled", "CANCELLED", 0, "job-progress-83"],
  ])("renders %s notification state", async (type, status, stage, testId) => {
    vi.mocked(getCustomerNotifications).mockResolvedValue(response([{
      ...initial,
      id: `card-${type}`,
      job_id: Number(testId.slice(-2)),
      type,
      event_version: 3,
      metadata: { state: type === "cancelled" ? "cancelled" : "active" },
    }]) as any);
    vi.mocked(getCustomerJobs).mockResolvedValue({
      data: [{ id: Number(testId.slice(-2)), status, completed_at: "2026-10-16T13:20:00Z" }],
    } as any);
    render(<CustomerNotificationsPage />);

    expect(await screen.findByTestId(testId)).toHaveAttribute("data-stage", String(stage));
    if (type === "cancelled") {
      expect(screen.getByText("This job was cancelled")).toBeTruthy();
    } else {
      expect(screen.getByText("Your job is complete")).toBeTruthy();
    }
  });
});
