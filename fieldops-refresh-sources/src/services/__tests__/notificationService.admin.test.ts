import { beforeEach, describe, expect, it, vi } from "vitest";

import api from "../api";
import {
  connectNotificationSocket,
  fetchNotifications,
} from "../notificationService";

const { socketHandlers, mockSocket, mockIo } = vi.hoisted(() => {
  const handlers = new Map<string, (payload: any) => void>();
  const socket = {
    on: (event: string, handler: (payload: any) => void) => {
      handlers.set(event, handler);
      return socket;
    },
    removeAllListeners: vi.fn(),
    disconnect: vi.fn(),
  };
  return { socketHandlers: handlers, mockSocket: socket, mockIo: vi.fn() };
});

vi.mock("../api", () => ({
  default: {
    get: vi.fn(),
  },
}));

vi.mock("socket.io-client", () => ({ io: mockIo }));

const mockedApi = vi.mocked(api);

describe("notificationService audience routing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("loads admin notifications from the authenticated admin feed", async () => {
    mockedApi.get.mockResolvedValueOnce({
      data: { notifications: [], unread_count: 0, total: 0 },
    } as any);

    await expect(fetchNotifications("user-1", "admin")).resolves.toEqual({
      notifications: [],
      unreadCount: 0,
      total: 0,
    });
    expect(mockedApi.get).toHaveBeenCalledWith("/admin/notifications");
  });

  it("keeps technician notification requests on their own endpoint", async () => {
    mockedApi.get.mockResolvedValueOnce({
      data: { notifications: [], unread_count: 0, total: 0 },
    } as any);

    await fetchNotifications("tech-1", "technician");

    expect(mockedApi.get).toHaveBeenCalledWith(
      "/technicians/tech-1/notifications",
    );
  });

  it("propagates endpoint errors instead of treating 404 as an empty feed", async () => {
    const notFound = { response: { status: 404 } };
    mockedApi.get.mockRejectedValueOnce(notFound);

    await expect(fetchNotifications("user-1", "admin")).rejects.toBe(notFound);
  });

  it("receives Communication Agent admin events on the notification socket event", () => {
    mockIo.mockReturnValueOnce(mockSocket);
    const onNewNotification = vi.fn();

    connectNotificationSocket("access-token", { onNewNotification });
    socketHandlers.get("notification")?.({
      id: "notif-1",
      type: "en_route",
      title: "Job #44 technician en route",
      body: "Repair · Technician One",
      job_id: "44",
      status: "UNREAD",
      event_version: 3,
    });

    expect(onNewNotification).toHaveBeenCalledWith(
      expect.objectContaining({
        id: "notif-1",
        title: "Job #44 technician en route",
        jobId: "44",
        eventVersion: 3,
      }),
    );
  });
});
