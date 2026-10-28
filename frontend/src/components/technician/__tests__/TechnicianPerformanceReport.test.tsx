import { fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import { describe, expect, it, vi } from "vitest";
import TechnicianPerformanceReport from "../TechnicianPerformanceReport";

describe("TechnicianPerformanceReport", () => {
  it("renders backend performance values and changes the selected period", () => {
    const onPeriodChange = vi.fn();
    render(
      <TechnicianPerformanceReport
        data={{
          period_completed_jobs: 12,
          average_completion_minutes: 260,
          customer_rating: 4.8,
          total_distance_km: 24.6,
          completion_trend: [
            { label: "Mon", count: 2 },
            { label: "Tue", count: 3 },
          ],
          status_distribution: [
            { status: "completed", count: 12 },
            { status: "active", count: 2 },
          ],
        }}
        period="week"
        onPeriodChange={onPeriodChange}
      />,
    );

    expect(screen.getAllByText("12")).not.toHaveLength(0);
    expect(screen.getByText("4h 20m")).toBeInTheDocument();
    expect(screen.getByText("4.8/5")).toBeInTheDocument();
    expect(screen.getByText("24.6 km")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /completed jobs trend/i })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /job status distribution for 14 jobs/i })).toBeInTheDocument();

    fireEvent.change(screen.getByRole("combobox", { name: "Performance report period" }), {
      target: { value: "month" },
    });
    expect(onPeriodChange).toHaveBeenCalledWith("month");
  });

  it("shows unavailable values instead of inventing report data", () => {
    render(
      <TechnicianPerformanceReport
        data={null}
        period="week"
        onPeriodChange={vi.fn()}
      />,
    );

    expect(screen.getByText("No completion trend data available.")).toBeInTheDocument();
    expect(screen.getByText("No job status data available.")).toBeInTheDocument();
    expect(screen.queryByText("24.6 km")).not.toBeInTheDocument();
  });
});
