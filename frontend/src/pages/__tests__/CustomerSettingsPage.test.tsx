import React from "react";
import {
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import CustomerSettingsPage from "../customer/CustomerSettingsPage";
import {
  getCustomerNotificationPreferences,
  updateCustomerNotificationPreferences,
} from "../../services/customerPortalService";

vi.mock(
  "../../services/customerPortalService",
  () => ({
    changeCustomerPassword: vi.fn(),
    getCustomerNotificationPreferences: vi.fn(),
    updateCustomerNotificationPreferences: vi.fn(),
  }),
);

const mockedGetNotificationPreferences = vi.mocked(
  getCustomerNotificationPreferences,
);

const mockedUpdateNotificationPreferences = vi.mocked(
  updateCustomerNotificationPreferences,
);

const preferences = {
  profile_id: "profile-101",
  tenant_id: "tenant-101",
  customer_id: "customer-101",
  sms_enabled: true,
  email_enabled: true,
  push_enabled: false,
  portal_enabled: true,
  preferred_locale: "en",
  revision: 4,
  source: "PROFILE" as const,
  updated_at: "2026-10-02T08:00:00Z",
  updated_by: "customer-101",
};

const renderPage = () =>
  render(<CustomerSettingsPage />);

describe(
  "CustomerSettingsPage - Task 12 Notification Preferences",
  () => {
    beforeEach(() => {
      vi.clearAllMocks();
    });

    it(
      "shows the notification loading state while the backend request is pending",
      async () => {
        let resolveRequest:
          | ((value: unknown) => void)
          | undefined;

        mockedGetNotificationPreferences.mockImplementationOnce(
          () =>
            new Promise((resolve) => {
              resolveRequest = resolve;
            }) as any,
        );

        renderPage();

        expect(
          screen.getByText(
            "Loading notification preferences...",
          ),
        ).toBeTruthy();

        expect(
          mockedGetNotificationPreferences,
        ).toHaveBeenCalledTimes(1);

        resolveRequest?.({
          data: preferences,
        });

        await waitFor(() => {
          expect(
            screen.getByRole("checkbox", {
              name: "SMS Notifications",
            }),
          ).toBeTruthy();
        });
      },
    );

    it(
      "loads and maps backend-authoritative notification preferences",
      async () => {
        mockedGetNotificationPreferences.mockResolvedValueOnce({
          data: preferences,
        } as any);

        renderPage();

        await screen.findByRole("checkbox", {
          name: "SMS Notifications",
        });

        expect(
          (
            screen.getByRole("checkbox", {
              name: "SMS Notifications",
            }) as HTMLInputElement
          ).checked,
        ).toBe(true);

        expect(
          (
            screen.getByRole("checkbox", {
              name: "Email Notifications",
            }) as HTMLInputElement
          ).checked,
        ).toBe(true);

        expect(
          (
            screen.getByRole("checkbox", {
              name: "Push Notifications",
            }) as HTMLInputElement
          ).checked,
        ).toBe(false);

        expect(
          (
            screen.getByRole("checkbox", {
              name: "Portal Notifications",
            }) as HTMLInputElement
          ).checked,
        ).toBe(true);

        expect(
          screen.getByDisplayValue("en"),
        ).toBeTruthy();

        expect(
          mockedGetNotificationPreferences,
        ).toHaveBeenCalledTimes(1);
      },
    );

    it(
      "keeps save disabled until a preference changes",
      async () => {
        mockedGetNotificationPreferences.mockResolvedValueOnce({
          data: preferences,
        } as any);

        renderPage();

        await screen.findByRole("checkbox", {
          name: "SMS Notifications",
        });

        const saveButton = screen.getByRole(
          "button",
          {
            name: "Save Notification Preferences",
          },
        );

        expect(
          (saveButton as HTMLButtonElement).disabled,
        ).toBe(true);

        fireEvent.click(
          screen.getByRole("checkbox", {
            name: "SMS Notifications",
          }),
        );

        expect(
          (saveButton as HTMLButtonElement).disabled,
        ).toBe(false);
      },
    );

    it(
      "saves changed preferences and reconciles with the backend response",
      async () => {
        mockedGetNotificationPreferences.mockResolvedValueOnce({
          data: preferences,
        } as any);

        const savedPreferences = {
          ...preferences,
          sms_enabled: false,
          push_enabled: true,
          preferred_locale: "ta",
          revision: 5,
        };

        mockedUpdateNotificationPreferences.mockResolvedValueOnce({
          data: savedPreferences,
        } as any);

        renderPage();

        await screen.findByRole("checkbox", {
          name: "SMS Notifications",
        });

        fireEvent.click(
          screen.getByRole("checkbox", {
            name: "SMS Notifications",
          }),
        );

        fireEvent.click(
          screen.getByRole("checkbox", {
            name: "Push Notifications",
          }),
        );

        fireEvent.change(
          screen.getByDisplayValue("en"),
          {
            target: {
              value: "ta",
            },
          },
        );

        fireEvent.click(
          screen.getByRole("button", {
            name: "Save Notification Preferences",
          }),
        );

        await waitFor(() => {
          expect(
            mockedUpdateNotificationPreferences,
          ).toHaveBeenCalledWith({
            sms_enabled: false,
            email_enabled: true,
            push_enabled: true,
            portal_enabled: true,
            preferred_locale: "ta",
          });
        });

        expect(
          await screen.findByText(
            "Notification preferences saved successfully.",
          ),
        ).toBeTruthy();

        expect(
          (
            screen.getByRole("checkbox", {
              name: "SMS Notifications",
            }) as HTMLInputElement
          ).checked,
        ).toBe(false);

        expect(
          (
            screen.getByRole("checkbox", {
              name: "Push Notifications",
            }) as HTMLInputElement
          ).checked,
        ).toBe(true);

        expect(
          screen.getByDisplayValue("ta"),
        ).toBeTruthy();
      },
    );

    it(
      "rejects an empty preferred locale before calling the backend",
      async () => {
        mockedGetNotificationPreferences.mockResolvedValueOnce({
          data: preferences,
        } as any);

        renderPage();

        await screen.findByRole("checkbox", {
          name: "SMS Notifications",
        });

        fireEvent.change(
          screen.getByDisplayValue("en"),
          {
            target: {
              value: "   ",
            },
          },
        );

        fireEvent.click(
          screen.getByRole("button", {
            name: "Save Notification Preferences",
          }),
        );

        expect(
          await screen.findByText(
            "Preferred locale is required.",
          ),
        ).toBeTruthy();

        expect(
          mockedUpdateNotificationPreferences,
        ).not.toHaveBeenCalled();
      },
    );

    it(
      "shows a permission error when the backend returns 403",
      async () => {
        mockedGetNotificationPreferences.mockResolvedValueOnce({
          data: preferences,
        } as any);

        mockedUpdateNotificationPreferences.mockRejectedValueOnce({
          response: {
            status: 403,
          },
        });

        renderPage();

        await screen.findByRole("checkbox", {
          name: "SMS Notifications",
        });

        fireEvent.click(
          screen.getByRole("checkbox", {
            name: "SMS Notifications",
          }),
        );

        fireEvent.click(
          screen.getByRole("button", {
            name: "Save Notification Preferences",
          }),
        );

        expect(
          await screen.findByText(
            "You do not have permission to update notification preferences.",
          ),
        ).toBeTruthy();
      },
    );

    it(
      "shows a safe generic error for non-permission save failures",
      async () => {
        mockedGetNotificationPreferences.mockResolvedValueOnce({
          data: preferences,
        } as any);

        mockedUpdateNotificationPreferences.mockRejectedValueOnce(
          new Error("database credentials leaked"),
        );

        renderPage();

        await screen.findByRole("checkbox", {
          name: "SMS Notifications",
        });

        fireEvent.click(
          screen.getByRole("checkbox", {
            name: "SMS Notifications",
          }),
        );

        fireEvent.click(
          screen.getByRole("button", {
            name: "Save Notification Preferences",
          }),
        );

        expect(
          await screen.findByText(
            "Failed to save notification preferences.",
          ),
        ).toBeTruthy();

        expect(
          screen.queryByText(
            "database credentials leaked",
          ),
        ).toBeNull();
      },
    );

    it(
      "shows the backend error when loading preferences fails",
      async () => {
        mockedGetNotificationPreferences.mockRejectedValueOnce({
          response: {
            status: 500,
            data: {
              detail:
                "Preference service unavailable.",
            },
          },
        });

        renderPage();

        expect(
          await screen.findByText(
            "Preference service unavailable.",
          ),
        ).toBeTruthy();

        expect(
          mockedGetNotificationPreferences,
        ).toHaveBeenCalledTimes(1);
      },
    );
  },
);