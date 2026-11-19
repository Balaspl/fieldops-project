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

import CustomerSupportPage from "../customer/CustomerSupportPage";
import {
  createCustomerSupportRequest,
  getAdminCustomerSupportRequest,
  getAdminCustomerSupportRequests,
  getCustomerJobs,
  getCustomerSupportRequests,
  getServiceHistory,
  updateAdminCustomerSupportRequest,
} from "../../services/customerPortalService";

const authMocks = vi.hoisted(() => ({
  user: {
    id: "customer-1",
    email: "customer@example.com",
    first_name: "Test",
    last_name: "Customer",
    role: "customer",
    tenant_id: "tenant-1",
    organization_name: null,
  } as any,
}));

vi.mock("../../store/authStore", () => ({
  default: (
    selector: (state: any) => unknown,
  ) =>
    selector({
      user: authMocks.user,
    }),
}));

vi.mock("../../services/customerPortalService", () => ({
  createCustomerSupportRequest: vi.fn(),
  getAdminCustomerSupportRequest: vi.fn(),
  getAdminCustomerSupportRequests: vi.fn(),
  getCustomerJobs: vi.fn(),
  getCustomerSupportRequests: vi.fn(),
  getServiceHistory: vi.fn(),
  updateAdminCustomerSupportRequest: vi.fn(),
}));

const mockedGetCustomerSupportRequests =
  vi.mocked(
    getCustomerSupportRequests,
  );

const mockedCreateCustomerSupportRequest =
  vi.mocked(
    createCustomerSupportRequest,
  );

const mockedGetCustomerJobs =
  vi.mocked(getCustomerJobs);

const mockedGetServiceHistory =
  vi.mocked(getServiceHistory);

const mockedGetAdminCustomerSupportRequests =
  vi.mocked(
    getAdminCustomerSupportRequests,
  );

const mockedGetAdminCustomerSupportRequest =
  vi.mocked(
    getAdminCustomerSupportRequest,
  );

const mockedUpdateAdminCustomerSupportRequest =
  vi.mocked(
    updateAdminCustomerSupportRequest,
  );

const customerRequest = {
  id: 1,
  request_number: "SUP-TEST-001",
  subject: "Invoice problem",
  description:
    "Please check my invoice amount.",
  related_job_id: 101,
  status: "OPEN",
  resolution_note: null,
  resolved_at: null,
  created_at:
    "2026-10-06T10:00:00Z",
  updated_at:
    "2026-10-06T10:00:00Z",
};

const adminRequest = {
  ...customerRequest,
  customer: {
    name: "Test Customer",
    email: "customer@example.com",
    phone_number: "9876543210",
  },
  job: {
    id: 101,
    customer_name: "Test Customer",
    service_type: "HVAC Repair",
    issue_description: "Cooling issue",
    priority: "HIGH",
    status: "COMPLETED",
    location: "Chennai",
    site_address: "Chennai",
    preferred_service_date:
      "2026-10-05",
    contact_number: "9876543210",
    assigned_technician_name:
      "Technician One",
    assigned_technician_phone:
      "9000000000",
    assigned_at: null,
    en_route_at: null,
    on_site_at: null,
    completed_at:
      "2026-10-05T12:00:00Z",
    created_at:
      "2026-10-05T08:00:00Z",
    updated_at:
      "2026-10-05T12:00:00Z",
  },
};

describe(
  "CustomerSupportPage",
  () => {
    beforeEach(() => {
      vi.clearAllMocks();

      authMocks.user.role =
        "customer";

      mockedGetCustomerSupportRequests
        .mockResolvedValue({
          data: [],
        } as any);

      mockedCreateCustomerSupportRequest
        .mockResolvedValue({
          data: customerRequest,
        } as any);

      mockedGetCustomerJobs
        .mockResolvedValue({
          data: [
            {
              id: 101,
              service_type:
                "HVAC Repair",
              status: "IN_PROGRESS",
            },
          ],
        } as any);

      mockedGetServiceHistory
        .mockResolvedValue({
          data: [],
        } as any);

      mockedGetAdminCustomerSupportRequests
        .mockResolvedValue({
          data: [adminRequest],
        } as any);

      mockedGetAdminCustomerSupportRequest
        .mockResolvedValue({
          data: adminRequest,
        } as any);

      mockedUpdateAdminCustomerSupportRequest
        .mockResolvedValue({
          data: {
            ...adminRequest,
            status: "RESOLVED",
            resolution_note:
              "Invoice checked and corrected.",
            resolved_at:
              "2026-10-06T10:30:00Z",
          },
        } as any);
    });

    it(
      "lets a customer submit a support request linked to a job",
      async () => {
        render(
          <CustomerSupportPage />,
        );

        expect(
          await screen.findByRole(
            "heading",
            {
              name: "Customer Support",
            },
          ),
        ).toBeTruthy();

        fireEvent.change(
          screen.getByLabelText(
            "Subject",
          ),
          {
            target: {
              value:
                "Invoice problem",
            },
          },
        );

        fireEvent.change(
          screen.getByLabelText(
            "Description",
          ),
          {
            target: {
              value:
                "Please check my invoice amount.",
            },
          },
        );

        fireEvent.change(
          screen.getByLabelText(
            /Related Job/,
          ),
          {
            target: {
              value: "101",
            },
          },
        );

        fireEvent.click(
          screen.getByRole(
            "button",
            {
              name:
                /Submit Support Request/,
            },
          ),
        );

        await waitFor(() => {
          expect(
            mockedCreateCustomerSupportRequest,
          ).toHaveBeenCalledWith({
            subject:
              "Invoice problem",
            description:
              "Please check my invoice amount.",
            related_job_id: 101,
          });
        });

        expect(
          await screen.findByText(
            "Support request SUP-TEST-001 was submitted successfully.",
          ),
        ).toBeTruthy();
      },
    );

    it(
      "shows backend resolution updates to the customer",
      async () => {
        mockedGetCustomerSupportRequests
          .mockResolvedValueOnce({
            data: [
              {
                ...customerRequest,
                status: "RESOLVED",
                resolution_note:
                  "Invoice checked and corrected.",
                resolved_at:
                  "2026-10-06T10:30:00Z",
                updated_at:
                  "2026-10-06T10:30:00Z",
              },
            ],
          } as any);

        render(
          <CustomerSupportPage />,
        );

        expect(
          await screen.findByText(
            "Invoice checked and corrected.",
          ),
        ).toBeTruthy();

        expect(
          screen.getByText("RESOLVED"),
        ).toBeTruthy();
      },
    );

    it(
      "shows the staff support queue with customer and job context",
      async () => {
        authMocks.user.role =
          "dispatcher";

        render(
          <CustomerSupportPage />,
        );

        expect(
          await screen.findByText(
            "Support Queue",
          ),
        ).toBeTruthy();

        expect(
          screen.getByText(
            "Test Customer",
          ),
        ).toBeTruthy();

        expect(
          screen.getByText(
            "Job #101",
          ),
        ).toBeTruthy();

        fireEvent.click(
          screen.getByRole(
            "button",
            {
              name: /SUP-TEST-001/,
            },
          ),
        );

        expect(
          await screen.findByText(
            "Handle Support Case",
          ),
        ).toBeTruthy();

        expect(
          screen.getByText(
            "Technician One",
          ),
        ).toBeTruthy();

        expect(
          screen.getByText(
            "Cooling issue",
          ),
        ).toBeTruthy();
      },
    );

    it(
      "requires a resolution note before a staff member resolves a case",
      async () => {
        authMocks.user.role =
          "dispatcher";

        render(
          <CustomerSupportPage
            initialRequestId={1}
          />,
        );

        expect(
          await screen.findByText(
            "Handle Support Case",
          ),
        ).toBeTruthy();

        fireEvent.change(
          screen.getByLabelText(
            "Status",
          ),
          {
            target: {
              value: "RESOLVED",
            },
          },
        );

        fireEvent.click(
          screen.getByRole(
            "button",
            {
              name:
                /Save & Notify Customer/,
            },
          ),
        );

        expect(
          await screen.findByText(
            "A resolution note is required before resolving or closing a support request.",
          ),
        ).toBeTruthy();

        expect(
          mockedUpdateAdminCustomerSupportRequest,
        ).not.toHaveBeenCalled();
      },
    );

    it(
      "updates the staff case and confirms that the customer was notified",
      async () => {
        authMocks.user.role =
          "dispatcher";

        render(
          <CustomerSupportPage
            initialRequestId={1}
          />,
        );

        expect(
          await screen.findByText(
            "Handle Support Case",
          ),
        ).toBeTruthy();

        fireEvent.change(
          screen.getByLabelText(
            "Status",
          ),
          {
            target: {
              value: "RESOLVED",
            },
          },
        );

        fireEvent.change(
          screen.getByLabelText(
            "Resolution / response",
          ),
          {
            target: {
              value:
                "Invoice checked and corrected.",
            },
          },
        );

        fireEvent.click(
          screen.getByRole(
            "button",
            {
              name:
                /Save & Notify Customer/,
            },
          ),
        );

        await waitFor(() => {
          expect(
            mockedUpdateAdminCustomerSupportRequest,
          ).toHaveBeenCalledWith(
            1,
            {
              status: "RESOLVED",
              resolution_note:
                "Invoice checked and corrected.",
            },
          );
        });

        expect(
          await screen.findByText(
            "Support request SUP-TEST-001 updated and the customer was notified.",
          ),
        ).toBeTruthy();
      },
    );
  },
);