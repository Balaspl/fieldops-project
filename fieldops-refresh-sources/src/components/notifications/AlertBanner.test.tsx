import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import "@testing-library/jest-dom";
import AlertBanner from "./AlertBanner";

const mockAlerts = [
  {
    job_id: 101,
    job_title: "AC Repair - Anna Nagar",
    title: "AC Repair - Anna Nagar",
    attempt_count: 3,
    status: "active"
  },
  {
    job_id: 102,
    job_title: "Electrical Sparking - Adyar",
    title: "Electrical Sparking - Adyar",
    attempt_count: 5,
    status: "active"
  }
];

vi.mock("../../services/api", () => ({
  default: {
    get: vi.fn().mockImplementation((url) => {
      if (url.includes("/alerts")) {
        return Promise.resolve({ data: mockAlerts });
      }
      return Promise.resolve({ data: [] });
    }),
    post: vi.fn().mockResolvedValue({ data: {} }),
  }
}));

describe("AlertBanner Component", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(mockAlerts)
      })
    ));

    vi.stubGlobal("AudioContext", vi.fn().mockImplementation(() => ({
      createOscillator: () => ({
        connect: () => {},
        frequency: { setValueAtTime: () => {}, linearRampToValueAtTime: () => {} },
        type: "",
        start: () => {},
        stop: () => {}
      }),
      createGain: () => ({
        connect: () => {},
        gain: { setValueAtTime: () => {}, exponentialRampToValueAtTime: () => {} }
      }),
      destination: {},
      currentTime: 0
    })));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders alerts and distinguishes warning (3 attempts) and critical (5 attempts) severities", async () => {
    render(
      <AlertBanner
        onViewHistory={vi.fn()}
        onManualAssignClick={vi.fn()}
      />
    );

    // Warning
    await waitFor(() => {
      expect(screen.getByText(/AC Repair - Anna Nagar/i)).toBeInTheDocument();
      expect(screen.getByText("Attention Required")).toBeInTheDocument();
    });

    // Critical
    expect(screen.getByText(/Electrical Sparking - Adyar/i)).toBeInTheDocument();
    expect(screen.getByText("Critical Alert")).toBeInTheDocument();
  });

  it("fires View History callback when clicked", async () => {
    const handleViewHistory = vi.fn();
    render(
      <AlertBanner
        onViewHistory={handleViewHistory}
        onManualAssignClick={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/AC Repair - Anna Nagar/i)).toBeInTheDocument();
    });

    const viewBtns = screen.getAllByRole("button", { name: "View History" });
    fireEvent.click(viewBtns[0]); // first one is warning (101)

    expect(handleViewHistory).toHaveBeenCalledWith(101, "AC Repair - Anna Nagar");
  });

  it("fires Manual Assign callback when clicked", async () => {
    const handleManualAssign = vi.fn();
    render(
      <AlertBanner
        onViewHistory={vi.fn()}
        onManualAssignClick={handleManualAssign}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/Electrical Sparking - Adyar/i)).toBeInTheDocument();
    });

    const assignBtns = screen.getAllByRole("button", { name: "Manual Assign + Escalate" });
    fireEvent.click(assignBtns[0]); // critical escalate button

    expect(handleManualAssign).toHaveBeenCalledWith(102, "Electrical Sparking - Adyar");
  });

  it("removes banner locally when close button is clicked", async () => {
    render(
      <AlertBanner
        onViewHistory={vi.fn()}
        onManualAssignClick={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/AC Repair - Anna Nagar/i)).toBeInTheDocument();
    });

    const closeBtns = screen.getAllByLabelText("Dismiss alert");
    fireEvent.click(closeBtns[0]); // close warning alert

    await waitFor(() => {
      expect(screen.queryByText(/AC Repair - Anna Nagar/i)).not.toBeInTheDocument();
    });
    // Critical alert should still be visible
    expect(screen.getByText(/Electrical Sparking - Adyar/i)).toBeInTheDocument();
  });
});
