import {
  afterEach,
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

import TechnicianNotificationsPage from "../TechnicianNotificationsPage";

import {
  getTechnicianNotifications,
  markTechnicianNotificationRead,
  markAllTechnicianNotificationsRead,
  acceptTechnicianJob,
  rejectTechnicianJob,
} from "../../../services/technicianPortalService";

vi.mock(
  "../../../services/technicianPortalService",
  () => ({
    getTechnicianNotifications: vi.fn(),
    markTechnicianNotificationRead: vi.fn(),
    markAllTechnicianNotificationsRead: vi.fn(),
    acceptTechnicianJob: vi.fn(),
    rejectTechnicianJob: vi.fn(),
  }),
);

const mockedGetTechnicianNotifications = vi.mocked(
  getTechnicianNotifications,
);

const mockedMarkTechnicianNotificationRead = vi.mocked(
  markTechnicianNotificationRead,
);

const mockedMarkAllTechnicianNotificationsRead = vi.mocked(
  markAllTechnicianNotificationsRead,
);

const mockedAcceptTechnicianJob = vi.mocked(
  acceptTechnicianJob,
);

const mockedRejectTechnicianJob = vi.mocked(
  rejectTechnicianJob,
);

type NotificationsResponse = Awaited<
  ReturnType<typeof getTechnicianNotifications>
>;

const createNotificationsResponse = (
  notifications: unknown[] = [],
  unreadCount = notifications.filter(
    (notification: any) => !notification.isRead,
  ).length,
): NotificationsResponse =>
  ({
    data: {
      notifications,
      unread_count: unreadCount,
    },
  }) as NotificationsResponse;

const representativeNotifications = [
  {
    id: 101,
    type: "JOB_ASSIGNED",
    title: "New HVAC Job Assigned",
    message: "HVAC repair assigned for Chennai site.",
    isRead: false,
    createdAt: "2026-09-28T09:00:00Z",
    jobId: 501,
    jobStatus: "ASSIGNED",
  },
  {
    id: 102,
    type: "JOB_UPDATED",
    title: "Job Schedule Updated",
    message: "The customer updated the preferred service time.",
    isRead: true,
    createdAt: "2026-09-28T08:30:00Z",
    jobId: 502,
    jobStatus: "ACCEPTED",
  },
];

describe(
  "TechnicianNotificationsPage - Notification Center",
  () => {
    beforeEach(() => {
      mockedGetTechnicianNotifications.mockResolvedValue(
        createNotificationsResponse(
          representativeNotifications,
          1,
        ),
      );

      mockedMarkTechnicianNotificationRead.mockResolvedValue(
        { data: {} } as Awaited<
          ReturnType<typeof markTechnicianNotificationRead>
        >,
      );

      mockedMarkAllTechnicianNotificationsRead.mockResolvedValue(
        { data: {} } as Awaited<
          ReturnType<typeof markAllTechnicianNotificationsRead>
        >,
      );

      mockedAcceptTechnicianJob.mockResolvedValue(
        { data: {} } as Awaited<
          ReturnType<typeof acceptTechnicianJob>
        >,
      );

      mockedRejectTechnicianJob.mockResolvedValue(
        { data: {} } as Awaited<
          ReturnType<typeof rejectTechnicianJob>
        >,
      );
    });

    afterEach(() => {
      vi.clearAllMocks();
    });

    it(
      "calls the existing technician notification API on mount and maps representative backend data",
      async () => {
        render(<TechnicianNotificationsPage />);

        expect(
          await screen.findByText(
            "New HVAC Job Assigned",
          ),
        ).toBeTruthy();

        expect(
          screen.getByText(
            "HVAC repair assigned for Chennai site.",
          ),
        ).toBeTruthy();

        expect(
          screen.getByText(
            "Job Schedule Updated",
          ),
        ).toBeTruthy();

        expect(
          screen.getByText("1 Unread"),
        ).toBeTruthy();

        expect(
          screen.getByText("NEW"),
        ).toBeTruthy();

        expect(
          mockedGetTechnicianNotifications,
        ).toHaveBeenCalledTimes(1);
      },
    );

    it(
      "shows the loading state while the backend request is pending",
      async () => {
        let resolveNotifications:
          | ((value: NotificationsResponse) => void)
          | undefined;

        mockedGetTechnicianNotifications.mockImplementation(
          () =>
            new Promise((resolve) => {
              resolveNotifications = resolve;
            }),
        );

        render(<TechnicianNotificationsPage />);

        expect(
          screen.getByText(
            "Loading notifications...",
          ),
        ).toBeTruthy();

        resolveNotifications?.(
          createNotificationsResponse(
            representativeNotifications,
            1,
          ),
        );

        expect(
          await screen.findByText(
            "New HVAC Job Assigned",
          ),
        ).toBeTruthy();
      },
    );

    it(
      "renders the explicit empty state when the backend returns no notifications",
      async () => {
        mockedGetTechnicianNotifications.mockResolvedValue(
          createNotificationsResponse([], 0),
        );

        render(<TechnicianNotificationsPage />);

        expect(
          await screen.findByText(
            "No notifications found.",
          ),
        ).toBeTruthy();

        expect(
          screen.queryByText("1 Unread"),
        ).toBeNull();
      },
    );

    it(
      "renders the generic API error state with retry",
      async () => {
        mockedGetTechnicianNotifications
          .mockRejectedValueOnce(
            new Error(
              "Notification history unavailable",
            ),
          )
          .mockResolvedValueOnce(
            createNotificationsResponse(
              representativeNotifications,
              1,
            ),
          );

        const consoleError = vi
          .spyOn(console, "error")
          .mockImplementation(() => {});

        render(<TechnicianNotificationsPage />);

        expect(
          await screen.findByText(
            "Unable to load notifications. Please try again.",
          ),
        ).toBeTruthy();

        fireEvent.click(
          screen.getByRole("button", {
            name: "Refresh notifications",
          }),
        );

        expect(
          await screen.findByText(
            "New HVAC Job Assigned",
          ),
        ).toBeTruthy();

        expect(
          mockedGetTechnicianNotifications,
        ).toHaveBeenCalledTimes(2);

        consoleError.mockRestore();
      },
    );

    it(
      "shows the backend authorization message for a 403 response",
      async () => {
        mockedGetTechnicianNotifications.mockRejectedValue(
          {
            response: {
              status: 403,
            },
          },
        );

        const consoleError = vi
          .spyOn(console, "error")
          .mockImplementation(() => {});

        render(<TechnicianNotificationsPage />);

        expect(
          await screen.findByText(
            "You are not authorized to view technician notifications.",
          ),
        ).toBeTruthy();

        consoleError.mockRestore();
      },
    );

    it(
      "shows the unavailable-data message for a 404 response",
      async () => {
        mockedGetTechnicianNotifications.mockRejectedValue(
          {
            response: {
              status: 404,
            },
          },
        );

        const consoleError = vi
          .spyOn(console, "error")
          .mockImplementation(() => {});

        render(<TechnicianNotificationsPage />);

        expect(
          await screen.findByText(
            "Technician notification history is currently unavailable.",
          ),
        ).toBeTruthy();

        consoleError.mockRestore();
      },
    );

    it(
      "marks one unread notification as read through the existing backend API",
      async () => {
        render(<TechnicianNotificationsPage />);

        await screen.findByText(
          "New HVAC Job Assigned",
        );

        fireEvent.click(
          screen.getByRole("button", {
            name: "Mark notification 101 as read",
          }),
        );

        await waitFor(() => {
          expect(
            mockedMarkTechnicianNotificationRead,
          ).toHaveBeenCalledWith(101);
        });

        expect(
          screen.queryByText("NEW"),
        ).toBeNull();

        expect(
          screen.queryByText("1 Unread"),
        ).toBeNull();
      },
    );

    it(
      "marks all unread notifications as read through the existing backend API",
      async () => {
        render(<TechnicianNotificationsPage />);

        await screen.findByText(
          "New HVAC Job Assigned",
        );

        fireEvent.click(
          screen.getByRole("button", {
            name: "Mark All Read",
          }),
        );

        await waitFor(() => {
          expect(
            mockedMarkAllTechnicianNotificationsRead,
          ).toHaveBeenCalledTimes(1);
        });

        expect(
          screen.queryByText("NEW"),
        ).toBeNull();

        expect(
          screen.queryByText("1 Unread"),
        ).toBeNull();
      },
    );

    it(
      "refreshes from the same authoritative backend source when Refresh is clicked",
      async () => {
        mockedGetTechnicianNotifications
          .mockResolvedValueOnce(
            createNotificationsResponse(
              representativeNotifications,
              1,
            ),
          )
          .mockResolvedValueOnce(
            createNotificationsResponse(
              [
                {
                  ...representativeNotifications[0],
                  id: 103,
                  title: "Updated Assignment",
                  message:
                    "Updated notification from backend.",
                  isRead: false,
                  jobId: 503,
                },
              ],
              1,
            ),
          );

        render(<TechnicianNotificationsPage />);

        await screen.findByText(
          "New HVAC Job Assigned",
        );

        fireEvent.click(
          screen.getByRole("button", {
            name: "Refresh notifications",
          }),
        );

        expect(
          await screen.findByText(
            "Updated Assignment",
          ),
        ).toBeTruthy();

        expect(
          screen.getByText(
            "Updated notification from backend.",
          ),
        ).toBeTruthy();

        expect(
          mockedGetTechnicianNotifications,
        ).toHaveBeenCalledTimes(2);
      },
    );

    it(
      "reconciles the notification center after the existing technician dashboard refresh event",
      async () => {
        mockedGetTechnicianNotifications
          .mockResolvedValueOnce(
            createNotificationsResponse(
              representativeNotifications,
              1,
            ),
          )
          .mockResolvedValueOnce(
            createNotificationsResponse(
              [
                {
                  ...representativeNotifications[0],
                  id: 104,
                  title: "New Event Notification",
                  message:
                    "Backend refresh event delivered a new notification.",
                  isRead: false,
                  jobId: 504,
                },
              ],
              1,
            ),
          );

        render(<TechnicianNotificationsPage />);

        await screen.findByText(
          "New HVAC Job Assigned",
        );

        window.dispatchEvent(
          new CustomEvent(
            "technician-dashboard-refresh",
          ),
        );

        expect(
          await screen.findByText(
            "New Event Notification",
          ),
        ).toBeTruthy();

        expect(
          mockedGetTechnicianNotifications,
        ).toHaveBeenCalledTimes(2);
      },
    );

    it(
      "uses the existing technician job API and notification read API for an assigned-job accept action",
      async () => {
        mockedGetTechnicianNotifications
          .mockResolvedValueOnce(
            createNotificationsResponse(
              [
                {
                  ...representativeNotifications[0],
                  jobStatus: "ASSIGNED",
                },
              ],
              1,
            ),
          )
          .mockResolvedValueOnce(
            createNotificationsResponse([], 0),
          );

        render(<TechnicianNotificationsPage />);

        const acceptButton =
          await screen.findByRole("button", {
            name: "Accept Job #501",
          });

        fireEvent.click(acceptButton);

        await waitFor(() => {
          expect(
            mockedAcceptTechnicianJob,
          ).toHaveBeenCalledWith(501);

          expect(
            mockedMarkTechnicianNotificationRead,
          ).toHaveBeenCalledWith(101);
        });

        await waitFor(() => {
          expect(
            mockedGetTechnicianNotifications,
          ).toHaveBeenCalledTimes(2);
        });
      },
    );

    it(
      "validates the decline reason before calling the existing technician job API",
      async () => {
        render(<TechnicianNotificationsPage />);

        const declineButton =
          await screen.findByRole("button", {
            name: "Decline",
          });

        fireEvent.click(declineButton);

        expect(
          screen.getByText(
            "Decline Job #501",
          ),
        ).toBeTruthy();

        const confirmButton =
          screen.getByRole("button", {
            name: "Confirm Decline",
          });

        expect(
          (confirmButton as HTMLButtonElement).disabled,
        ).toBe(true);

        fireEvent.change(
          screen.getByPlaceholderText(
            "State your reason for declining this job...",
          ),
          {
            target: {
              value:
                "Technician unavailable for this job.",
            },
          },
        );

        expect(
          (confirmButton as HTMLButtonElement).disabled,
        ).toBe(false);

        fireEvent.click(confirmButton);

        await waitFor(() => {
          expect(
            mockedRejectTechnicianJob,
          ).toHaveBeenCalledWith(
            501,
            "Technician unavailable for this job.",
          );
        });
      },
    );
  },
);
