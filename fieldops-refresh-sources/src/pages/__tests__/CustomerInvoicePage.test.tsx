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

import CustomerInvoicePage from "../customer/CustomerInvoicePage";
import {
  getCustomerInvoices,
  getCustomerPaymentHistory,
  getCustomerPaymentStatus,
} from "../../services/customerPortalService";

vi.mock(
  "../../services/customerPortalService",
  () => ({
    getCustomerInvoices: vi.fn(),
    getCustomerPaymentHistory: vi.fn(),
    getCustomerPaymentStatus: vi.fn(),
  }),
);

const mockedGetCustomerInvoices =
  vi.mocked(getCustomerInvoices);

const mockedGetCustomerPaymentHistory =
  vi.mocked(getCustomerPaymentHistory);

const mockedGetCustomerPaymentStatus =
  vi.mocked(getCustomerPaymentStatus);

const invoice = {
  id: "501",
  job_id: 101,
  customer_name: "Customer User",
  service_type: "HVAC Repair",
  location: "12 Main Street, Chennai",
  work_summary: "Replaced failed compressor and tested the unit.",
  labour_cost: 1500,
  material_cost: 2500,
  subtotal: 4000,
  gst_rate: 5,
  gst_amount: 200,
  total_amount: 4200,
  completed_at: "2026-09-29T15:30:00Z",
  created_at: "2026-09-29T16:00:00Z",
};

const successfulPaymentStatus = {
  job_id: 101,
  invoice_id: 501,
  status: "SUCCESSFUL",
  updated_at: "2026-09-29T17:00:00Z",
};

describe("CustomerInvoicePage - Task 7 Invoice View", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockedGetCustomerPaymentHistory.mockResolvedValue({
      data: [],
    } as any);
  });

  it("loads and renders the backend-authoritative invoice and payment fields", async () => {
    mockedGetCustomerInvoices.mockResolvedValueOnce({
      data: [invoice],
    } as any);

    mockedGetCustomerPaymentStatus.mockResolvedValueOnce({
      data: successfulPaymentStatus,
    } as any);

    render(<CustomerInvoicePage />);

    expect(
      screen.getByTestId(
        "customer-invoices-loading",
      ),
    ).toBeTruthy();

    expect(
      await screen.findByTestId(
        "customer-invoice-501",
      ),
    ).toBeTruthy();

    expect(
      screen.getByText("Invoice #501"),
    ).toBeTruthy();

    expect(
      screen.getByText("HVAC Repair"),
    ).toBeTruthy();

    expect(
      screen.getByText(
        "12 Main Street, Chennai",
      ),
    ).toBeTruthy();

    expect(
      screen.getByText(
        "Replaced failed compressor and tested the unit.",
      ),
    ).toBeTruthy();

    expect(
      screen.getByText("₹1,500.00"),
    ).toBeTruthy();

    expect(
      screen.getByText("₹2,500.00"),
    ).toBeTruthy();

    expect(
      screen.getByText("₹4,000.00"),
    ).toBeTruthy();

    expect(
      screen.getByText("₹200.00"),
    ).toBeTruthy();

    expect(
      screen.getByText("₹4,200.00"),
    ).toBeTruthy();

    expect(
      mockedGetCustomerInvoices,
    ).toHaveBeenCalledTimes(1);

    expect(
      mockedGetCustomerPaymentStatus,
    ).toHaveBeenCalledTimes(1);

    expect(
      mockedGetCustomerPaymentStatus,
    ).toHaveBeenCalledWith(101);

    expect(
      screen.getByTestId(
        "customer-invoice-payment-501",
      ),
    ).toBeTruthy();

    expect(
      screen.getByTestId(
        "customer-invoice-payment-status-501",
      ).textContent,
    ).toContain(
      "Payment confirmed",
    );

    expect(
      screen.getByText(
        "Payment has been confirmed by the billing backend.",
      ),
    ).toBeTruthy();
  });



  it("maps multiple invoices and requests each payment status once", async () => {
    mockedGetCustomerInvoices.mockResolvedValueOnce({
      data: [
        invoice,
        {
          ...invoice,
          id: "502",
          job_id: 102,
          service_type: "Electrical Service",
          total_amount: 2100,
        },
      ],
    } as any);

    mockedGetCustomerPaymentStatus
      .mockResolvedValueOnce({
        data: successfulPaymentStatus,
      } as any)
      .mockResolvedValueOnce({
        data: {
          ...successfulPaymentStatus,
          job_id: 102,
          invoice_id: 502,
          status: "PENDING",
        },
      } as any);

    render(<CustomerInvoicePage />);

    expect(
      await screen.findByTestId(
        "customer-invoice-501",
      ),
    ).toBeTruthy();

    expect(
      screen.getByTestId(
        "customer-invoice-502",
      ),
    ).toBeTruthy();

    expect(
      mockedGetCustomerInvoices,
    ).toHaveBeenCalledTimes(1);

    expect(
      mockedGetCustomerPaymentStatus,
    ).toHaveBeenCalledTimes(2);

    expect(
      mockedGetCustomerPaymentStatus,
    ).toHaveBeenNthCalledWith(
      1,
      101,
    );

    expect(
      mockedGetCustomerPaymentStatus,
    ).toHaveBeenNthCalledWith(
      2,
      102,
    );

    expect(
      screen.getByTestId(
        "customer-invoice-payment-status-501",
      ).textContent,
    ).toContain(
      "Payment confirmed",
    );

    expect(
      screen.getByTestId(
        "customer-invoice-payment-status-502",
      ).textContent,
    ).toContain(
      "Payment pending",
    );
  });

  it("shows the loading state while the invoice request is pending", async () => {
    let resolveRequest:
      | ((value: unknown) => void)
      | undefined;

    mockedGetCustomerInvoices.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveRequest = resolve;
        }) as any,
    );

    render(<CustomerInvoicePage />);

    expect(
      screen.getByTestId(
        "customer-invoices-loading",
      ).textContent,
    ).toContain(
      "Loading invoices...",
    );

    expect(
      mockedGetCustomerInvoices,
    ).toHaveBeenCalledTimes(1);

    mockedGetCustomerPaymentStatus.mockResolvedValueOnce({
      data: successfulPaymentStatus,
    } as any);

    resolveRequest?.({
      data: [invoice],
    });

    await waitFor(() => {
      expect(
        screen.getByTestId(
          "customer-invoice-501",
        ),
      ).toBeTruthy();
    });

    expect(
      mockedGetCustomerPaymentStatus,
    ).toHaveBeenCalledWith(101);
  });

  it("displays PENDING payment status from the backend", async () => {
    mockedGetCustomerInvoices.mockResolvedValueOnce({
      data: [invoice],
    } as any);

    mockedGetCustomerPaymentStatus.mockResolvedValueOnce({
      data: {
        ...successfulPaymentStatus,
        status: "PENDING",
      },
    } as any);

    render(<CustomerInvoicePage />);

    expect(
      (
        await screen.findByTestId(
          "customer-invoice-payment-status-501",
        )
      ).textContent,
    ).toContain(
      "Payment pending",
    );

    expect(
      screen.getByText(
        "Payment is awaiting backend verification.",
      ),
    ).toBeTruthy();

    expect(
      screen.getByText(
        "Do not treat the payment as completed until the backend reports a successful verification.",
      ),
    ).toBeTruthy();
  });

  it("displays FAILED payment status from the backend", async () => {
    mockedGetCustomerInvoices.mockResolvedValueOnce({
      data: [invoice],
    } as any);

    mockedGetCustomerPaymentStatus.mockResolvedValueOnce({
      data: {
        ...successfulPaymentStatus,
        status: "FAILED",
      },
    } as any);

    render(<CustomerInvoicePage />);

    expect(
      (
        await screen.findByTestId(
          "customer-invoice-payment-status-501",
        )
      ).textContent,
    ).toContain(
      "Payment failed",
    );

    expect(
      screen.getByText(
        "The latest backend payment status is failed.",
      ),
    ).toBeTruthy();
  });

  it("shows UNAVAILABLE when the payment-status request fails", async () => {
    mockedGetCustomerInvoices.mockResolvedValueOnce({
      data: [invoice],
    } as any);

    mockedGetCustomerPaymentStatus.mockRejectedValueOnce(
      new Error("payment service unavailable"),
    );

    render(<CustomerInvoicePage />);

    expect(
      (
        await screen.findByTestId(
          "customer-invoice-payment-status-501",
        )
      ).textContent,
    ).toContain(
      "Online payment unavailable",
    );

    expect(
      screen.getByText(
        "Online payment status is currently unavailable. Please try again later.",
      ),
    ).toBeTruthy();

    expect(
      screen.getByTestId(
        "customer-invoice-payment-501",
      ).textContent,
    ).not.toContain(
      "payment service unavailable",
    );
  });

  it("treats an unexpected backend payment state as unavailable", async () => {
    mockedGetCustomerInvoices.mockResolvedValueOnce({
      data: [invoice],
    } as any);

    mockedGetCustomerPaymentStatus.mockResolvedValueOnce({
      data: {
        ...successfulPaymentStatus,
        status: "COMPLETED",
      },
    } as any);

    render(<CustomerInvoicePage />);

    expect(
      (
        await screen.findByTestId(
          "customer-invoice-payment-status-501",
        )
      ).textContent,
    ).toContain(
      "Online payment unavailable",
    );
  });

  it("does not duplicate payment-status requests during the initial render", async () => {
    mockedGetCustomerInvoices.mockResolvedValueOnce({
      data: [invoice],
    } as any);

    mockedGetCustomerPaymentStatus.mockResolvedValueOnce({
      data: successfulPaymentStatus,
    } as any);

    render(<CustomerInvoicePage />);

    await screen.findByTestId(
      "customer-invoice-payment-501",
    );

    expect(
      mockedGetCustomerInvoices,
    ).toHaveBeenCalledTimes(1);

    expect(
      mockedGetCustomerPaymentStatus,
    ).toHaveBeenCalledTimes(1);

    expect(
      mockedGetCustomerPaymentStatus,
    ).toHaveBeenCalledWith(101);
  });


  it("shows the empty state when the backend returns no invoices", async () => {
    mockedGetCustomerInvoices.mockResolvedValueOnce({
      data: [],
    } as any);

    render(<CustomerInvoicePage />);

    expect(
      await screen.findByTestId(
        "customer-invoices-empty",
      ),
    ).toBeTruthy();

    expect(
      screen.getByText(
        "No invoices yet",
      ),
    ).toBeTruthy();

    expect(
      mockedGetCustomerPaymentStatus,
    ).not.toHaveBeenCalled();
  });

  it("treats an unexpected non-array payload as an empty invoice list", async () => {
    mockedGetCustomerInvoices.mockResolvedValueOnce({
      data: null,
    } as any);

    render(<CustomerInvoicePage />);

    expect(
      await screen.findByTestId(
        "customer-invoices-empty",
      ),
    ).toBeTruthy();

    expect(
      screen.queryByTestId(
        "customer-invoices-error",
      ),
    ).toBeNull();
  });

  it("shows a session-expired message for a 401 response", async () => {
    mockedGetCustomerInvoices.mockRejectedValueOnce({
      response: {
        status: 401,
      },
    });

    render(<CustomerInvoicePage />);

    const error = await screen.findByRole(
      "alert",
    );

    expect(error.textContent).toContain(
      "Your session has expired. Please sign in again.",
    );

    expect(
      screen.getByRole("button", {
        name: "Try Again",
      }),
    ).toBeTruthy();

    expect(
      mockedGetCustomerPaymentStatus,
    ).not.toHaveBeenCalled();
  });

  it("shows a permission message for a 403 response", async () => {
    mockedGetCustomerInvoices.mockRejectedValueOnce({
      response: {
        status: 403,
      },
    });

    render(<CustomerInvoicePage />);

    const error = await screen.findByRole(
      "alert",
    );

    expect(error.textContent).toContain(
      "You do not have permission to view these invoices.",
    );

    expect(
      mockedGetCustomerPaymentStatus,
    ).not.toHaveBeenCalled();
  });

  it("shows a safe generic message for other API failures", async () => {
    mockedGetCustomerInvoices.mockRejectedValueOnce(
      new Error("database credentials leaked"),
    );

    render(<CustomerInvoicePage />);

    const error = await screen.findByRole(
      "alert",
    );

    expect(error.textContent).toContain(
      "We couldn't load your invoices right now. Please try again.",
    );

    expect(error.textContent).not.toContain(
      "database credentials leaked",
    );
  });

  it("reloads exactly once when the customer clicks Refresh", async () => {
    mockedGetCustomerInvoices
      .mockResolvedValueOnce({
        data: [invoice],
      } as any)
      .mockResolvedValueOnce({
        data: [
          {
            ...invoice,
            id: "503",
          },
        ],
      } as any);

    mockedGetCustomerPaymentStatus
      .mockResolvedValueOnce({
        data: successfulPaymentStatus,
      } as any)
      .mockResolvedValueOnce({
        data: {
          ...successfulPaymentStatus,
          job_id: 101,
          invoice_id: 503,
        },
      } as any);

    render(<CustomerInvoicePage />);

    expect(
      await screen.findByTestId(
        "customer-invoice-501",
      ),
    ).toBeTruthy();

    fireEvent.click(
      screen.getByRole("button", {
        name: "Refresh invoices",
      }),
    );

    await waitFor(() => {
      expect(
        screen.getByTestId(
          "customer-invoice-503",
        ),
      ).toBeTruthy();
    });

    expect(
      mockedGetCustomerInvoices,
    ).toHaveBeenCalledTimes(2);

    expect(
      mockedGetCustomerPaymentStatus,
    ).toHaveBeenCalledTimes(2);

    expect(
      mockedGetCustomerPaymentStatus,
    ).toHaveBeenNthCalledWith(
      1,
      101,
    );

    expect(
      mockedGetCustomerPaymentStatus,
    ).toHaveBeenNthCalledWith(
      2,
      101,
    );

    expect(
      screen.getByTestId(
        "customer-invoice-payment-status-503",
      ).textContent,
    ).toContain(
      "Payment confirmed",
    );
  });
});
