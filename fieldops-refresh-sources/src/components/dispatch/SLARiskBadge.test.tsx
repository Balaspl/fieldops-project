import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import React from "react";
import "@testing-library/jest-dom";
import SLARiskBadge, { calculateRiskLevel, computeMinutesRemaining } from "./SLARiskBadge";

describe("SLARiskBadge Logic & Render", () => {
  describe("computeMinutesRemaining", () => {
    it("calculates positive remaining minutes correctly", () => {
      const fromDate = new Date("2026-06-02T12:00:00Z");
      const deadline = "2026-06-02T13:00:00Z";
      expect(computeMinutesRemaining(deadline, fromDate)).toBe(60);
    });

    it("calculates negative remaining minutes for breached deadlines correctly", () => {
      const fromDate = new Date("2026-06-02T13:10:00Z");
      const deadline = "2026-06-02T13:00:00Z";
      expect(computeMinutesRemaining(deadline, fromDate)).toBe(-10);
    });
  });

  describe("calculateRiskLevel", () => {
    it("maps >60 min remaining to LOW risk", () => {
      expect(calculateRiskLevel(61)).toBe("LOW");
    });

    it("maps 30-60 min remaining to MEDIUM risk", () => {
      expect(calculateRiskLevel(60)).toBe("MEDIUM");
      expect(calculateRiskLevel(45)).toBe("MEDIUM");
      expect(calculateRiskLevel(30)).toBe("MEDIUM");
    });

    it("maps 10-30 min remaining to HIGH risk", () => {
      expect(calculateRiskLevel(29)).toBe("HIGH");
      expect(calculateRiskLevel(15)).toBe("HIGH");
      expect(calculateRiskLevel(10)).toBe("HIGH");
    });

    it("maps <10 min remaining and breached status to CRITICAL risk", () => {
      expect(calculateRiskLevel(9)).toBe("CRITICAL");
      expect(calculateRiskLevel(0)).toBe("CRITICAL");
      expect(calculateRiskLevel(-5)).toBe("CRITICAL");
    });
  });

  describe("SLARiskBadge Component", () => {
    it("renders the badge text and displays the full ISO deadline timestamp as tooltip", () => {
      const deadline = "2026-06-02T15:30:00.000Z";
      
      render(
        <SLARiskBadge
          slaDeadline={deadline}
          showMinutes={true}
          enablePulse={false}
        />
      );

      // Check that it renders a status element
      const badge = screen.getByRole("status");
      expect(badge).toBeInTheDocument();

      // Check tooltip contains the exact ISO timestamp
      expect(badge).toHaveAttribute("title", deadline);
    });

    it("displays BREACHED if deadline is passed", () => {
      const pastDeadline = new Date(Date.now() - 5 * 60 * 1000).toISOString(); // 5 mins ago
      
      render(
        <SLARiskBadge
          slaDeadline={pastDeadline}
          showMinutes={true}
          enablePulse={false}
        />
      );

      expect(screen.getByText("BREACHED")).toBeInTheDocument();
    });
  });
});
