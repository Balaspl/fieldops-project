import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import "@testing-library/jest-dom";
import OverrideHistory from "./OverrideHistory";
import * as planningService from "../../services/planningService";

// Mock planning service APIs
vi.mock("../../services/planningService", () => ({
  getOverrideHistory: vi.fn(),
}));

// Mock socket.io-client
const mockSocketOn = vi.fn();
const mockSocketDisconnect = vi.fn();
const mockSocket = {
  on: mockSocketOn,
  disconnect: mockSocketDisconnect,
};

vi.mock("socket.io-client", () => ({
  io: vi.fn().mockImplementation(() => mockSocket),
}));

// Mock list of manual overrides
const mockOverrides = [
  {
    id: 1,
    job_id: 101,
    actor_name: "Manager Priya",
    actor_role: "manager",
    justification: "Customer specifically requested Rajesh for HVAC maintenance.",
    previous_technician_id: null,
    previous_technician_name: "Unassigned",
    new_technician_id: 2,
    new_technician_name: "Rajesh Kumar",
    created_at: "2026-05-25T14:30:00Z"
  },
  {
    id: 2,
    job_id: 101,
    actor_name: "Dispatcher John",
    actor_role: "dispatcher",
    justification: "Initial assignment for scheduling.",
    previous_technician_id: null,
    previous_technician_name: null,
    new_technician_id: 3,
    new_technician_name: "Suresh Nair",
    created_at: "2026-05-25T14:15:00Z"
  },
  {
    id: 3,
    job_id: 101,
    actor_name: "Admin Alex",
    actor_role: "admin",
    justification: "Emergency priority update.",
    previous_technician_id: 4,
    previous_technician_name: "Amit Patel",
    new_technician_id: 5,
    new_technician_name: "Vijay Iyer",
    created_at: "2026-05-25T14:45:00Z"
  }
];

describe("OverrideHistory Component", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_SOCKET_URL", "http://localhost:8000");
    vi.stubGlobal("AudioContext", vi.fn().mockImplementation(function (this: any) {
      this.createOscillator = () => ({
        connect: () => {},
        frequency: { setValueAtTime: () => {} },
        type: "",
        start: () => {},
        stop: () => {}
      });
      this.createGain = () => ({
        connect: () => {},
        gain: { setValueAtTime: () => {}, exponentialRampToValueAtTime: () => {} }
      });
      this.destination = {};
      this.currentTime = 0;
    }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders all manual overrides correctly", async () => {
    vi.mocked(planningService.getOverrideHistory).mockResolvedValue({
      data: mockOverrides
    });

    render(
      <OverrideHistory
        jobId={101}
        jobTitle="AC Maintenance"
        onClose={vi.fn()}
      />
    );

    // Verify it displays the loading indicator initially
    expect(screen.getByText("Loading override records...")).toBeInTheDocument();

    // Wait for the records to load
    await waitFor(() => {
      expect(screen.getByText("Manager Priya")).toBeInTheDocument();
    });

    // Check rendering of elements
    expect(screen.getByText("Dispatcher John")).toBeInTheDocument();
    expect(screen.getByText("Admin Alex")).toBeInTheDocument();

    // Verify role badges are rendered
    expect(screen.getByText("manager")).toBeInTheDocument();
    expect(screen.getByText("dispatcher")).toBeInTheDocument();
    expect(screen.getByText("admin")).toBeInTheDocument();

    // Verify before/after technician transitions
    expect(screen.getByText("Rajesh Kumar")).toBeInTheDocument();
    expect(screen.getByText("Suresh Nair")).toBeInTheDocument();
    expect(screen.getByText("Vijay Iyer")).toBeInTheDocument();
    expect(screen.getByText("Amit Patel")).toBeInTheDocument();

    // Verify justifications
    expect(screen.getByText("Customer specifically requested Rajesh for HVAC maintenance.")).toBeInTheDocument();
    expect(screen.getByText("Initial assignment for scheduling.")).toBeInTheDocument();
  });

  it("sorts manual override log entries dynamically by timestamp", async () => {
    vi.mocked(planningService.getOverrideHistory).mockResolvedValue({
      data: mockOverrides
    });

    render(
      <OverrideHistory
        jobId={101}
        jobTitle="AC Maintenance"
        onClose={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Manager Priya")).toBeInTheDocument();
    });

    // Default sorting should be newest first (newest = Admin Alex created_at: 14:45, then Manager Priya: 14:30, then Dispatcher John: 14:15)
    let events = screen.getAllByText(/Manager Priya|Dispatcher John|Admin Alex/);
    expect(events[0].textContent).toContain("Admin Alex");
    expect(events[1].textContent).toContain("Manager Priya");
    expect(events[2].textContent).toContain("Dispatcher John");

    // Toggle sorting to oldest first
    const select = screen.getByLabelText("Sort timeline entries");
    fireEvent.change(select, { target: { value: "oldest" } });

    // Verify the sorted order changes (oldest = John: 14:15, Priya: 14:30, Alex: 14:45)
    events = screen.getAllByText(/Manager Priya|Dispatcher John|Admin Alex/);
    expect(events[0].textContent).toContain("Dispatcher John");
    expect(events[1].textContent).toContain("Manager Priya");
    expect(events[2].textContent).toContain("Admin Alex");
  });

  it("toggles justification expand/collapse state when clicked", async () => {
    vi.mocked(planningService.getOverrideHistory).mockResolvedValue({
      data: mockOverrides
    });

    render(
      <OverrideHistory
        jobId={101}
        jobTitle="AC Maintenance"
        onClose={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Manager Priya")).toBeInTheDocument();
    });

    const justificationsHeaders = screen.getAllByText("Justification");
    const testJustificationText = screen.getByText("Customer specifically requested Rajesh for HVAC maintenance.");

    // Initially, text should have line-clamp-2 class (collapsed state)
    expect(testJustificationText).toHaveClass("line-clamp-2");

    // Click to expand justification for Manager Priya (newest first → Admin Alex is index 0, Manager Priya is index 1)
    fireEvent.click(justificationsHeaders[1]);
    expect(testJustificationText).not.toHaveClass("line-clamp-2");

    // Click to collapse justification again
    fireEvent.click(justificationsHeaders[1]);
    expect(testJustificationText).toHaveClass("line-clamp-2");
  });

  it("applies the correct role color coding dynamically", async () => {
    vi.mocked(planningService.getOverrideHistory).mockResolvedValue({
      data: mockOverrides
    });

    render(
      <OverrideHistory
        jobId={101}
        jobTitle="AC Maintenance"
        onClose={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Manager Priya")).toBeInTheDocument();
    });

    const managerBadge = screen.getByText("manager");
    const adminBadge = screen.getByText("admin");
    const dispatcherBadge = screen.getByText("dispatcher");

    // Manager = bg-blue-50
    expect(managerBadge).toHaveClass("bg-blue-50");
    // Admin = bg-purple-50
    expect(adminBadge).toHaveClass("bg-purple-50");
    // Dispatcher = bg-emerald-50
    expect(dispatcherBadge).toHaveClass("bg-emerald-50");
  });

  it("triggers CSV download when CSV Export button is clicked", async () => {
    vi.mocked(planningService.getOverrideHistory).mockResolvedValue({
      data: mockOverrides
    });

    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    render(
      <OverrideHistory
        jobId={101}
        jobTitle="AC Maintenance"
        onClose={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Export history to CSV" })).toBeInTheDocument();
    });

    const exportBtn = screen.getByRole("button", { name: "Export history to CSV" });
    fireEvent.click(exportBtn);

    expect(clickSpy).toHaveBeenCalled();
  });

  it("renders empty state placeholder when no manual overrides are logged", async () => {
    vi.mocked(planningService.getOverrideHistory).mockResolvedValue({
      data: []
    });

    render(
      <OverrideHistory
        jobId={101}
        jobTitle="AC Maintenance"
        onClose={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.queryByText("Loading override records...")).not.toBeInTheDocument();
    });

    expect(screen.getByText("No manual overrides recorded for this job")).toBeInTheDocument();
    expect(screen.getByText("This job was routed via automated planning systems.")).toBeInTheDocument();
  });

  it("registers socket listener and prepends overrides in real-time", async () => {
    vi.mocked(planningService.getOverrideHistory).mockResolvedValue({
      data: [mockOverrides[0]]
    });

    // Track the handler registered for override:new event
    let newOverrideHandler: (data: any) => void = () => {};
    mockSocketOn.mockImplementation((event, handler) => {
      if (event === "override:new") {
        newOverrideHandler = handler;
      }
    });

    render(
      <OverrideHistory
        jobId={101}
        jobTitle="AC Maintenance"
        onClose={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText("Manager Priya")).toBeInTheDocument();
    });

    // Dispatcher John shouldn't be rendered yet since he is not in getOverrideHistory's resolved payload
    expect(screen.queryByText("Dispatcher John")).not.toBeInTheDocument();

    // Trigger the override:new event via socket listener with a new override for this job
    const newOverridePayload = mockOverrides[1]; // John's override
    
    await act(async () => {
      newOverrideHandler(newOverridePayload);
    });

    // John's override should now be prepended to the history layout
    await waitFor(() => {
      expect(screen.getByText("Dispatcher John")).toBeInTheDocument();
      expect(screen.getByText("Initial assignment for scheduling.")).toBeInTheDocument();
    });
  });
});
