import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React from "react";
import "@testing-library/jest-dom";
import PermissionRequest from "./PermissionRequest";

// Helper to create localStorage mock
const createLocalStorageMock = () => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] || null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value.toString();
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
    clear: vi.fn(() => {
      store = {};
    }),
    key: vi.fn((index: number) => Object.keys(store)[index] || null),
    get length() {
      return Object.keys(store).length;
    }
  };
};

const mockLocalStorage = createLocalStorageMock();

describe("PermissionRequest Component", () => {
  let mockPermission = "default";
  let requestPermissionMock = vi.fn().mockImplementation(() => Promise.resolve(mockPermission));

  beforeEach(() => {
    // Reset localstorage & mock states
    mockLocalStorage.clear();
    mockPermission = "default";
    requestPermissionMock = vi.fn().mockImplementation(() => Promise.resolve(mockPermission));

    // Stub global localStorage
    vi.stubGlobal("localStorage", mockLocalStorage);
    Object.defineProperty(window, "localStorage", {
      value: mockLocalStorage,
      configurable: true,
      writable: true
    });

    // Stub Notification API
    vi.stubGlobal("Notification", {
      get permission() {
        return mockPermission;
      },
      requestPermission: requestPermissionMock
    });

    // Mock matchMedia (defaults to non-standalone/desktop)
    window.matchMedia = vi.fn().mockImplementation((query) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    // Mock window.navigator properties (defaults to desktop Chrome)
    vi.spyOn(window.navigator, "userAgent", "get").mockReturnValue(
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    );

    Object.defineProperty(window.navigator, "standalone", {
      value: false,
      configurable: true,
      writable: true
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders educational prompt when permission is default", () => {
    render(<PermissionRequest />);
    expect(screen.getByText(/Enable Push Notifications/i)).toBeInTheDocument();
    expect(screen.getByText("Get instant alerts for new jobs. Never miss an assignment.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enable Notifications" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Maybe Later" })).toBeInTheDocument();
  });

  it("handles granted permission flow and stores FCM token", async () => {
    const onPermissionChange = vi.fn();
    mockPermission = "default";
    requestPermissionMock.mockResolvedValue("granted");

    render(<PermissionRequest onPermissionChange={onPermissionChange} />);

    const enableBtn = screen.getByRole("button", { name: "Enable Notifications" });
    mockPermission = "granted"; // when queried by the component after request
    fireEvent.click(enableBtn);

    await waitFor(() => {
      expect(screen.getByText(/Push Notifications Enabled/i)).toBeInTheDocument();
    });

    expect(mockLocalStorage.getItem("push_permission_status")).toBe("granted");
    expect(mockLocalStorage.getItem("push_fcm_token")).not.toBeNull();
    expect(mockLocalStorage.getItem("push_fcm_token")).toContain("mock_fcm_token_");
    expect(onPermissionChange).toHaveBeenCalledWith("granted");
  });

  it("handles denied permission flow, shows fallbacks, and stores denial timestamp", async () => {
    const onPermissionChange = vi.fn();
    mockPermission = "default";
    requestPermissionMock.mockResolvedValue("denied");

    render(<PermissionRequest onPermissionChange={onPermissionChange} />);

    const enableBtn = screen.getByRole("button", { name: "Enable Notifications" });
    mockPermission = "denied";
    fireEvent.click(enableBtn);

    await waitFor(() => {
      expect(screen.getByText(/Push Notifications Blocked/i)).toBeInTheDocument();
    });

    expect(mockLocalStorage.getItem("push_permission_status")).toBe("denied");
    expect(mockLocalStorage.getItem("push_permission_denied_at")).not.toBeNull();
    expect(onPermissionChange).toHaveBeenCalledWith("denied");

    // Check fallback items are visible
    expect(screen.getByText("SMS notifications")).toBeInTheDocument();
    expect(screen.getByText("In-app notifications")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enable in Settings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use SMS Instead" })).toBeInTheDocument();
  });

  it("can subscribe to SMS fallback when permission is blocked", async () => {
    mockPermission = "denied";
    mockLocalStorage.setItem("push_permission_status", "denied");
    mockLocalStorage.setItem("push_permission_denied_at", new Date().toISOString());

    render(<PermissionRequest />);

    // Click "Use SMS Instead" to open the form
    const smsBtn = screen.getByRole("button", { name: "Use SMS Instead" });
    fireEvent.click(smsBtn);

    // Form should render input and subscribe button
    const input = screen.getByPlaceholderText("+91 98765-43210");
    const subscribeBtn = screen.getByRole("button", { name: "Subscribe" });

    fireEvent.change(input, { target: { value: "+91 9876543210" } });
    fireEvent.submit(subscribeBtn);

    await waitFor(() => {
      expect(mockLocalStorage.getItem("sms_notification_phone")).toBe("+91 9876543210");
    });
  });

  it("does not allow re-request and stays in blocked state if denied less than 7 days ago", () => {
    mockPermission = "denied";
    // Denied 3 days ago
    const threeDaysAgo = new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString();
    mockLocalStorage.setItem("push_permission_status", "denied");
    mockLocalStorage.setItem("push_permission_denied_at", threeDaysAgo);

    render(<PermissionRequest />);

    // Shows blocked state, not prompt
    expect(screen.getByText(/Push Notifications Blocked/i)).toBeInTheDocument();
  });

  it("allows re-request and reverts to default state if last denial was more than 7 days ago", () => {
    mockPermission = "denied";
    // Denied 8 days ago
    const eightDaysAgo = new Date(Date.now() - 8 * 24 * 60 * 60 * 1000).toISOString();
    mockLocalStorage.setItem("push_permission_status", "denied");
    mockLocalStorage.setItem("push_permission_denied_at", eightDaysAgo);

    render(<PermissionRequest />);

    // Cooldown passed: UI shows educational prompt (default state)
    expect(screen.getByText(/Enable Push Notifications/i)).toBeInTheDocument();
    expect(mockLocalStorage.getItem("push_permission_status")).toBe("default");
    expect(mockLocalStorage.getItem("push_permission_denied_at")).toBeNull();
  });

  it("respects status persistence across renders", () => {
    mockLocalStorage.setItem("push_permission_status", "granted");
    mockLocalStorage.setItem("push_fcm_token", "fcm_xyz");

    const { rerender } = render(<PermissionRequest />);
    expect(screen.getByText(/Push Notifications Enabled/i)).toBeInTheDocument();

    // Change localStorage to denied
    mockLocalStorage.setItem("push_permission_status", "denied");
    mockLocalStorage.setItem("push_permission_denied_at", new Date().toISOString());

    rerender(<PermissionRequest />);
  });

  it("shows iOS Safari banner when on non-standalone iOS device and status is default", () => {
    // Mock iOS user agent
    vi.spyOn(window.navigator, "userAgent", "get").mockReturnValue(
      "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1"
    );
    // Standalone is false
    Object.defineProperty(window.navigator, "standalone", {
      value: false,
      configurable: true,
      writable: true
    });

    render(<PermissionRequest />);

    expect(screen.getByText("📱 iOS Notification Requirements")).toBeInTheDocument();
    expect(screen.getByText(/Add to Home Screen/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Maybe Later" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Use SMS Fallback" })).toBeInTheDocument();
  });

  it("handles the disable flow properly", async () => {
    const onPermissionChange = vi.fn();
    mockLocalStorage.setItem("push_permission_status", "granted");
    mockLocalStorage.setItem("push_fcm_token", "token-to-delete");

    render(<PermissionRequest onPermissionChange={onPermissionChange} />);

    expect(screen.getByText(/Push Notifications Enabled/i)).toBeInTheDocument();

    const disableBtn = screen.getByRole("button", { name: "Disable" });
    mockPermission = "default";
    fireEvent.click(disableBtn);

    await waitFor(() => {
      expect(screen.getByText(/Enable Push Notifications/i)).toBeInTheDocument();
    });

    expect(mockLocalStorage.getItem("push_permission_status")).toBeNull();
    expect(mockLocalStorage.getItem("push_fcm_token")).toBeNull();
    expect(onPermissionChange).toHaveBeenCalledWith("default");
  });
});
