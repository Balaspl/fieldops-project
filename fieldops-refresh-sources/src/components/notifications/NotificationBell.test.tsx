import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import "@testing-library/jest-dom";

import NotificationBell from "./NotificationBell";

describe("NotificationBell unread badge", () => {
  it("shows the unread number in a red badge", () => {
    render(
      <NotificationBell
        unreadCount={3}
        onClick={vi.fn()}
        isAnimated={false}
        showSound={false}
      />,
    );

    expect(
      screen.getByRole("button", { name: "Notifications, 3 unread" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button")).toHaveStyle({ color: "rgb(220, 38, 38)" });
    const badge = screen.getByText("3");
    expect(badge).toHaveStyle({ backgroundColor: "rgb(220, 38, 38)" });
    expect(badge.previousElementSibling?.querySelector("svg")).toHaveAttribute("fill", "currentColor");
  });

  it("shows the bell and zero badge in green when there are no unread notifications", () => {
    render(
      <NotificationBell
        unreadCount={0}
        onClick={vi.fn()}
        isAnimated={false}
        showSound={false}
      />,
    );

    expect(screen.getByRole("button", { name: "Notifications, 0 unread" })).toHaveStyle({
      color: "rgb(22, 163, 74)",
    });
    expect(screen.getByText("0")).toHaveStyle({ backgroundColor: "rgb(22, 163, 74)" });
  });
});
