import React from "react";
import "@testing-library/jest-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";

import AnimatedJobProgress from "../AnimatedJobProgress";
import { useTrackingStore } from "../../../store/trackingStore";

const progressProps = {
  jobId: "job-progress-test",
  estimatedArrival: "2026-10-16T12:45:00.000Z",
  etaDurationMinutes: 18,
  etaDistanceKm: 7.2,
  etaTrafficDelayMinutes: 4,
  etaStatus: "calculated",
  etaUpdatedAt: "2026-10-16T12:25:00.000Z",
  arrivedAt: "2026-10-16T12:50:00.000Z",
  workStartedAt: "2026-10-16T12:55:00.000Z",
  completedAt: "2026-10-16T13:25:00.000Z",
};

beforeEach(() => {
  useTrackingStore.setState({ jobLiveUpdates: {} });
});

afterEach(cleanup);

describe("AnimatedJobProgress", () => {
  it.each([
    ["CREATED", 0, "Your service is booked"],
    ["ASSIGNED", 0, "Your service is booked"],
    ["ACCEPTED", 1, "Your technician accepted the job"],
    ["EN_ROUTE", 2, "Your technician is on the way"],
    ["ON_SITE", 3, "Your technician has arrived"],
    ["IN_PROGRESS", 4, "Work is in progress"],
    ["COMPLETED", 5, "Your job is complete"],
  ] as const)("renders %s at the expected stage", (status, stage, title) => {
    render(<AnimatedJobProgress {...progressProps} status={status} />);

    expect(screen.getByTestId(`job-progress-${progressProps.jobId}`)).toHaveAttribute(
      "data-stage",
      String(stage),
    );
    expect(screen.getByText(title)).toBeInTheDocument();
  });

  it("moves from the previous stage on status changes without resetting", () => {
    const view = render(
      <AnimatedJobProgress {...progressProps} status="EN_ROUTE" />,
    );
    const indicator = screen.getByTestId(
      `job-progress-indicator-${progressProps.jobId}`,
    );
    expect(indicator).toHaveStyle({ left: "41.5%" });

    view.rerender(
      <AnimatedJobProgress {...progressProps} status="ON_SITE" />,
    );
    expect(indicator).toHaveStyle({ left: "58.5%" });
    expect(indicator).toHaveClass("animated-job-progress__traveler");

    view.rerender(
      <AnimatedJobProgress {...progressProps} status="ON_SITE" />,
    );
    expect(indicator).toHaveStyle({ left: "58.5%" });
  });

  it("uses live job status and ETA updates from the tracking WebSocket store", () => {
    const view = render(
      <AnimatedJobProgress {...progressProps} status="ASSIGNED" />,
    );
    act(() => {
      useTrackingStore.getState().updateJobStatus(
        progressProps.jobId,
        "EN_ROUTE",
      );
      useTrackingStore.getState().updateJobETA(
        progressProps.jobId,
        {
          eta: "2026-10-16T13:05:00.000Z",
          duration_minutes: 24,
        },
      );
    });

    expect(screen.getByText("Your technician is on the way")).toBeInTheDocument();
    expect(screen.getByText("About 24 min away")).toBeInTheDocument();
    expect(screen.getByTestId(`job-progress-${progressProps.jobId}`)).toHaveAttribute(
      "data-stage",
      "2",
    );

    view.rerender(
      <AnimatedJobProgress {...progressProps} status="EN_ROUTE" />,
    );
  });

  it("shows unavailable ETA when no valid route estimate is present", () => {
    render(
      <AnimatedJobProgress
        jobId={progressProps.jobId}
        status="EN_ROUTE"
        estimatedArrival="not-a-date"
      />,
    );

    expect(screen.getByText("Arrival estimate unavailable")).toBeInTheDocument();
  });

  it("clears a stale ETA when live route data no longer contains an estimate", () => {
    render(<AnimatedJobProgress {...progressProps} status="EN_ROUTE" />);
    expect(screen.getByText("About 18 min away")).toBeInTheDocument();

    act(() => {
      useTrackingStore.getState().updateJobETA(progressProps.jobId, {
        eta: null,
        duration_minutes: null,
      });
    });

    expect(screen.getByText("Arrival estimate unavailable")).toBeInTheDocument();
    expect(screen.queryByText("About 18 min away")).not.toBeInTheDocument();
  });

  it("uses refreshed API snapshots after a reconnect or page refresh", () => {
    const view = render(
      <AnimatedJobProgress {...progressProps} status="EN_ROUTE" />,
    );
    act(() => {
      useTrackingStore.getState().setJobTrackingSnapshot(progressProps.jobId, {
        status: "IN_PROGRESS",
        eta: null,
        duration_minutes: null,
      });
    });

    expect(screen.getByText("Work is in progress")).toBeInTheDocument();
    view.rerender(
      <AnimatedJobProgress {...progressProps} status="IN_PROGRESS" />,
    );
    expect(screen.getByTestId(`job-progress-${progressProps.jobId}`)).toHaveAttribute(
      "data-stage",
      "4",
    );
  });

  it("shows actual event times and waits for completed status before completion", () => {
    render(
      <AnimatedJobProgress
        {...progressProps}
        status="IN_PROGRESS"
      />,
    );

    expect(screen.getByText(/^Arrived /)).toBeInTheDocument();
    expect(screen.getByText(/^Work started /)).toBeInTheDocument();
    expect(screen.queryByText("Your job is complete")).not.toBeInTheDocument();
    expect(screen.getByTestId(`job-progress-${progressProps.jobId}`)).toHaveAttribute(
      "data-stage",
      "4",
    );
  });

  it("keeps the progress at Arrived until a real work-start timestamp exists", () => {
    render(
      <AnimatedJobProgress
        jobId={progressProps.jobId}
        status="IN_PROGRESS"
        arrivedAt={progressProps.arrivedAt}
      />,
    );

    expect(screen.getByText("Your technician has arrived")).toBeInTheDocument();
    expect(screen.getByTestId(`job-progress-${progressProps.jobId}`)).toHaveAttribute(
      "data-stage",
      "3",
    );
    expect(screen.queryByText(/^Work started /)).not.toBeInTheDocument();
  });

  it("shows cancellation without marking the job complete", () => {
    render(
      <AnimatedJobProgress {...progressProps} status="CANCELLED" />,
    );

    expect(screen.getByText("This job was cancelled")).toBeInTheDocument();
    expect(screen.queryByText("Your job is complete")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Job stages")).not.toBeInTheDocument();
  });
});
