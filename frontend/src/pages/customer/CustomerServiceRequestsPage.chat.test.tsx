import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import CustomerServiceRequestsPage from "./CustomerServiceRequestsPage";

const mocks = vi.hoisted(() => ({
  getServiceRequests: vi.fn(),
}));

vi.mock("../../services/customerPortalService", () => ({
  getServiceRequests: mocks.getServiceRequests,
  createServiceRequest: vi.fn(),
  cancelServiceRequest: vi.fn(),
  getCustomerInvoice: vi.fn(),
}));

vi.mock("../../services/api", () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock("olamaps-web-sdk", () => ({ OlaMaps: class {} }));
vi.mock("../../components/customer-tracking/AnimatedJobProgress", () => ({ default: () => null }));
vi.mock("../../components/customer-tracking/JobLiveTrackingMap", () => ({ default: () => null }));
vi.mock("../../components/customer/CustomerNewRequestMarketplace", () => ({ default: () => null }));
vi.mock("../../store/trackingStore", () => ({ useTrackingStore: Object.assign(() => null, { getState: () => ({}) }) }));
vi.mock("../../components/customer-tracking/JobMessagePanel", () => ({
  default: ({ jobId }: { jobId: number }) => <div data-testid="job-message-panel" data-job-id={jobId} />,
}));

describe("My Requests chat action", () => {
  beforeEach(() => {
    mocks.getServiceRequests.mockResolvedValue({
      data: [{
        id: 7,
        linked_job_id: 42,
        status: "ACCEPTED",
        title: "Electrical repair",
        priority: "MEDIUM",
        preferred_visit_date: null,
        // The service request response does not include assigned_technician_id.
      }],
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("opens the existing chat panel for the linked job after acceptance", async () => {
    render(<CustomerServiceRequestsPage />);

    const chatButton = await screen.findByRole("button", { name: "Chat" });
    fireEvent.click(chatButton);

    await waitFor(() => {
      expect(screen.getByTestId("job-message-panel").getAttribute("data-job-id")).toBe("42");
    });
  });
});
