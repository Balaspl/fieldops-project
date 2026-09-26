import React from "react";
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";

import JobCreationForm from "../JobsPage";

import {
  getJobAuditHistory,
  getJobClosure,
  getJobInvoice,
  getJobInvoicePdf,
  getJobPaymentStatus,
  getJobCustomerFeedback,
  getJobs,
  getJobSla,
  getTechnicians,
} from "../../services/planningService";

vi.mock("../../services/planningService", () => ({
  getJobAuditHistory: vi.fn(),
  getJobClosure: vi.fn(),
  getJobInvoice: vi.fn(),
  getJobInvoicePdf: vi.fn(),
  getJobPaymentStatus: vi.fn(),
  getJobCustomerFeedback: vi.fn(),
  getJobs: vi.fn(),
  getJobSla: vi.fn(),
  getTechnicians: vi.fn(),
}));

vi.mock("../../store/authStore", () => ({
  default: () => ({
    user: {
      role: "dispatcher",
    },
  }),
}));

vi.mock("../../components/customer-tracking/JobStatusTimeline", () => ({
  default: () => (
    <div data-testid="mock-job-status-timeline">
      Mock Job Status Timeline
    </div>
  ),
}));

vi.mock("../../components/jobs/JobClosureModal", () => ({
  JobClosureModal: () => null,
}));

const mockedGetJobs = vi.mocked(getJobs);
const mockedGetTechnicians = vi.mocked(getTechnicians);
const mockedGetJobSla = vi.mocked(getJobSla);
const mockedGetJobClosure = vi.mocked(getJobClosure);
const mockedGetJobAuditHistory = vi.mocked(getJobAuditHistory);
const mockedGetJobInvoice = vi.mocked(getJobInvoice);
const mockedGetJobInvoicePdf = vi.mocked(getJobInvoicePdf);
const mockedGetJobPaymentStatus = vi.mocked(getJobPaymentStatus);
const mockedGetJobCustomerFeedback = vi.mocked(getJobCustomerFeedback);
const completedJob = {
  id: 101,
  customer_name: "Acme Customer",
  location: "Coimbatore",
  issue_description: "Air conditioner repair",
  priority: "HIGH",
  service_type: "HVAC_REPAIR",
  contact_number: "9876543210",
  preferred_service_date: "2026-09-24",
  status: "COMPLETED",
  required_skill: "HVAC",
  completed_at: "2026-09-24T10:00:00Z",
  completed_by: "TECH-01",
};

const invoiceRecord = {
  id: 5001,
  job_id: 101,
  customer_name: "Acme Customer",
  service_type: "HVAC_REPAIR",
  location: "Coimbatore",
  work_summary: "AC compressor repaired and tested successfully.",
  labour_cost: 1200,
  material_cost: 800,
  subtotal: 2000,
  gst_rate: 5,
  gst_amount: 100,
  total_amount: 2100,
  completed_at: "2026-09-24T10:00:00Z",
  created_at: "2026-09-24T10:05:00Z",
};


const paymentStatusRecord = {
  job_id: 101,
  invoice_id: 5001,
  status: "SUCCESSFUL",
  updated_at: "2026-09-24T10:30:00Z",
};

const customerFeedbackRecord = {
  job_id: 101,
  has_feedback: true,
  feedback: {
    id: 7001,
    rating: 5,
    comment: "Excellent service. The technician resolved the issue quickly.",
    created_at: "2026-09-24T11:00:00Z",
    updated_at: "2026-09-24T11:05:00Z",
  },
};

const customerFeedbackEmptyResponse = {
  job_id: 101,
  has_feedback: false,
  feedback: null,
};

const completedClosure = {
  technician_id: "TECH-01",
  work_summary: "AC compressor repaired and tested successfully.",
  before_images: [],
  after_images: [],
  labour_cost: 1200,
  material_cost: 800,
  subtotal: 2000,
  completed_at: "2026-09-24T10:00:00Z",
  created_at: "2026-09-24T10:05:00Z",
  updated_at: "2026-09-24T10:05:00Z",
};

function mockCommonApis() {
  mockedGetJobs.mockResolvedValue({
    data: [completedJob],
    headers: {
      "x-total-count": "1",
    },
  } as any);

  mockedGetTechnicians.mockResolvedValue({
    data: [],
  } as any);

  mockedGetJobSla.mockResolvedValue({
    data: {
      job_id: 101,
      deadline: null,
      remaining_minutes: 0,
      status: "NONE",
      is_critical: false,
      is_breached: false,
    },
  } as any);

  mockedGetJobClosure.mockResolvedValue(completedClosure as any);
  mockedGetJobPaymentStatus.mockResolvedValue(
    paymentStatusRecord as any
  );
  mockedGetJobCustomerFeedback.mockResolvedValue(
    customerFeedbackEmptyResponse as any
  );
  mockedGetJobAuditHistory.mockResolvedValue({
    job_id: 101,
    events: [],
    page: 1,
    page_size: 25,
    total: 0,
    has_more: false,
  } as any);
}

async function openCompletedJob() {
  render(<JobCreationForm />);

  await waitFor(() => {
    expect(
      screen.getByRole("button", { name: "View job" })
    ).toBeTruthy();
  });

  fireEvent.click(
    screen.getByRole("button", { name: "View job" })
  );

  await waitFor(() => {
    expect(
      screen.getByRole("heading", { name: "Invoice" })
    ).toBeTruthy();
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockCommonApis();

  if (typeof window !== "undefined") {
    localStorage.clear();
    localStorage.setItem("tenant_id", "tenant-1");
  }
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("JobsPage - Task 7 Invoice Section", () => {
  it("loads and displays backend-authoritative invoice data for a completed job", async () => {
    mockedGetJobInvoice.mockResolvedValue(invoiceRecord);

    await openCompletedJob();

    await waitFor(() => {
      expect(mockedGetJobInvoice).toHaveBeenCalledWith(101);
    });

    expect(
      screen.getByRole("heading", { name: "Invoice" })
    ).toBeTruthy();

    const invoiceHeading = screen.getByRole("heading", {
      name: "Invoice",
    });

    const invoiceSection = invoiceHeading
      .closest("div")
      ?.parentElement
      ?.parentElement;

    expect(invoiceSection).toBeTruthy();

    const invoice = within(invoiceSection as HTMLElement);

    expect(invoice.getAllByText("#5001")).toHaveLength(2);
    expect(invoice.getByText("Acme Customer")).toBeTruthy();
    expect(invoice.getByText("HVAC Repair")).toBeTruthy();

    expect(invoice.getByText("Labour Cost")).toBeTruthy();
    expect(invoice.getByText("Material Cost")).toBeTruthy();
    expect(invoice.getByText("Subtotal")).toBeTruthy();

    expect(
      invoice.getByText((_, element) => {
        return element?.textContent?.replace(/\s+/g, "") === "GST(5%)";
      })
    ).toBeTruthy();

    expect(invoice.getByText("Total")).toBeTruthy();

    expect(
      invoice.getByRole("button", {
        name: "Download invoice PDF",
      })
    ).toBeTruthy();
  });


  it("shows the loading state while invoice data is being fetched", async () => {
    let resolveInvoice!: (value: any) => void;

    mockedGetJobInvoice.mockReturnValue(
      new Promise((resolve) => {
        resolveInvoice = resolve;
      })
    );

    render(<JobCreationForm />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "View job" })
      ).toBeTruthy();
    });

    fireEvent.click(
      screen.getByRole("button", { name: "View job" })
    );

    expect(
      screen.getByText("Loading invoice...")
    ).toBeTruthy();

    resolveInvoice(invoiceRecord);

    await waitFor(() => {
      const invoiceHeading = screen.getByRole("heading", {
        name: "Invoice",
      });

      const invoiceSection = invoiceHeading
        .closest("div")
        ?.parentElement
        ?.parentElement;

      expect(invoiceSection).toBeTruthy();

      const invoice = within(invoiceSection as HTMLElement);

      expect(invoice.getAllByText("#5001")).toHaveLength(2);
    });
  });

  it("shows the authorization message when invoice access returns 403", async () => {
    mockedGetJobInvoice.mockRejectedValue({
      response: {
        status: 403,
      },
    });

    await openCompletedJob();

    await waitFor(() => {
      expect(
        screen.getByText(
          "You are not authorized to view the invoice for this job."
        )
      ).toBeTruthy();
    });
  });

  it("shows the unavailable state when invoice data returns 404", async () => {
    mockedGetJobInvoice.mockRejectedValue({
      response: {
        status: 404,
      },
    });

    await openCompletedJob();

    await waitFor(() => {
      expect(
        screen.getByText(
          "Invoice data is not available for this job."
        )
      ).toBeTruthy();
    });
  });

  it("shows a generic invoice error for an unexpected API failure", async () => {
    mockedGetJobInvoice.mockRejectedValue({
      response: {
        status: 500,
      },
    });

    await openCompletedJob();

    await waitFor(() => {
      expect(
        screen.getByText(
          "Invoice data is temporarily unavailable. Please try again."
        )
      ).toBeTruthy();
    });
  });

  it("does not request invoice data before the job is completed", async () => {
    mockedGetJobs.mockResolvedValue({
      data: [
        {
          ...completedJob,
          status: "IN_PROGRESS",
        },
      ],
      headers: {
        "x-total-count": "1",
      },
    } as any);

    render(<JobCreationForm />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "View job" })
      ).toBeTruthy();
    });

    fireEvent.click(
      screen.getByRole("button", { name: "View job" })
    );

    await waitFor(() => {
      expect(
        screen.getByText(
          "Invoice will be available after the job is completed."
        )
      ).toBeTruthy();
    });

    expect(mockedGetJobInvoice).not.toHaveBeenCalled();
  });

  it("downloads the invoice PDF through the backend-authoritative service", async () => {
    mockedGetJobInvoice.mockResolvedValue(invoiceRecord);
    mockedGetJobInvoicePdf.mockResolvedValue(
      new Blob(["invoice-pdf-content"], {
        type: "application/pdf",
      })
    );

    const createObjectURL = vi.fn(() => "blob:invoice-test");
    const revokeObjectURL = vi.fn();

    Object.defineProperty(window.URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: createObjectURL,
    });

    Object.defineProperty(window.URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: revokeObjectURL,
    });

    await openCompletedJob();

    const downloadButton = await screen.findByRole("button", {
      name: "Download invoice PDF",
    });

    fireEvent.click(downloadButton);

    await waitFor(() => {
      expect(mockedGetJobInvoicePdf).toHaveBeenCalledTimes(1);
      expect(mockedGetJobInvoicePdf).toHaveBeenCalledWith(101);
      expect(createObjectURL).toHaveBeenCalledTimes(1);
    });
  });

  it("shows a download authorization error when invoice PDF returns 403", async () => {
    mockedGetJobInvoice.mockResolvedValue(invoiceRecord);

    mockedGetJobInvoicePdf.mockRejectedValue({
      response: {
        status: 403,
      },
    });

    await openCompletedJob();

    const downloadButton = await screen.findByRole("button", {
      name: "Download invoice PDF",
    });

    fireEvent.click(downloadButton);

    await waitFor(() => {
      expect(
        screen.getByText(
          "You are not authorized to download the invoice PDF."
        )
      ).toBeTruthy();
    });
  });

  it("shows a download unavailable error when invoice PDF returns 404", async () => {
    mockedGetJobInvoice.mockResolvedValue(invoiceRecord);

    mockedGetJobInvoicePdf.mockRejectedValue({
      response: {
        status: 404,
      },
    });

    await openCompletedJob();

    const downloadButton = await screen.findByRole("button", {
      name: "Download invoice PDF",
    });

    fireEvent.click(downloadButton);

    await waitFor(() => {
      expect(
        screen.getByText(
          "Invoice PDF is not available for this job."
        )
      ).toBeTruthy();
    });
  });

  it("prevents duplicate invoice PDF downloads while the request is processing", async () => {
    mockedGetJobInvoice.mockResolvedValue(invoiceRecord);

    let resolvePdf!: (blob: Blob) => void;

    mockedGetJobInvoicePdf.mockReturnValue(
      new Promise((resolve) => {
        resolvePdf = resolve;
      })
    );

    await openCompletedJob();

    const downloadButton = await screen.findByRole("button", {
      name: "Download invoice PDF",
    });

    fireEvent.click(downloadButton);
    fireEvent.click(downloadButton);

    expect(mockedGetJobInvoicePdf).toHaveBeenCalledTimes(1);

    resolvePdf(
      new Blob(["invoice-pdf-content"], {
        type: "application/pdf",
      })
    );

    await waitFor(() => {
      expect(mockedGetJobInvoicePdf).toHaveBeenCalledTimes(1);
    });
  });
});

describe("JobsPage - Task 8 Payment Status", () => {
  it("loads and displays the backend-authoritative successful payment status", async () => {
    mockedGetJobPaymentStatus.mockResolvedValue(
      paymentStatusRecord as any
    );

    await openCompletedJob();

    await waitFor(() => {
      expect(mockedGetJobPaymentStatus).toHaveBeenCalledTimes(1);
      expect(mockedGetJobPaymentStatus).toHaveBeenCalledWith(101);

      const paymentHeading = screen.getByRole("heading", {
        name: "Payment Status",
      });

      const paymentSection = paymentHeading
        .closest("div")
        ?.parentElement
        ?.parentElement;

      expect(paymentSection).toBeTruthy();

      const payment = within(paymentSection as HTMLElement);

      expect(payment.getByText("SUCCESSFUL")).toBeTruthy();
      expect(payment.getByText("#5001")).toBeTruthy();
      expect(
        payment.getByText(
          new Date(paymentStatusRecord.updated_at).toLocaleString()
        )
      ).toBeTruthy();
    });
  });

  it("displays PENDING payment status from the backend", async () => {
    mockedGetJobPaymentStatus.mockResolvedValue({
      ...paymentStatusRecord,
      status: "PENDING",
    } as any);

    await openCompletedJob();

    await waitFor(() => {
      expect(screen.getByText("PENDING")).toBeTruthy();
    });
  });

  it("displays FAILED payment status from the backend", async () => {
    mockedGetJobPaymentStatus.mockResolvedValue({
      ...paymentStatusRecord,
      status: "FAILED",
    } as any);

    await openCompletedJob();

    await waitFor(() => {
      expect(screen.getByText("FAILED")).toBeTruthy();
    });
  });

  it("displays UNAVAILABLE when no payment record exists", async () => {
    mockedGetJobPaymentStatus.mockResolvedValue({
      job_id: 101,
      invoice_id: null,
      status: "UNAVAILABLE",
      updated_at: null,
    } as any);

    await openCompletedJob();

    await waitFor(() => {
      const paymentHeading = screen.getByRole("heading", {
        name: "Payment Status",
      });

      const paymentSection = paymentHeading
        .closest("div")
        ?.parentElement
        ?.parentElement;

      expect(paymentSection).toBeTruthy();

      const payment = within(paymentSection as HTMLElement);

      expect(payment.getByText("UNAVAILABLE")).toBeTruthy();
      expect(payment.getAllByText("N/A")).toHaveLength(2);
    });
  });

  it("shows the payment loading state while payment data is being fetched", async () => {
    let resolvePayment!: (value: any) => void;

    mockedGetJobPaymentStatus.mockReturnValue(
      new Promise((resolve) => {
        resolvePayment = resolve;
      })
    );

    render(<JobCreationForm />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "View job" })
      ).toBeTruthy();
    });

    fireEvent.click(
      screen.getByRole("button", { name: "View job" })
    );

    expect(
      screen.getByText("Loading payment status...")
    ).toBeTruthy();

    resolvePayment(paymentStatusRecord);

    await waitFor(() => {
      expect(screen.getByText("SUCCESSFUL")).toBeTruthy();
    });
  });

  it("shows the authorization message when payment status access returns 403", async () => {
    mockedGetJobPaymentStatus.mockRejectedValue({
      response: {
        status: 403,
      },
    });

    await openCompletedJob();

    await waitFor(() => {
      expect(
        screen.getByText(
          "You are not authorized to view the payment status for this job."
        )
      ).toBeTruthy();
    });
  });

  it("shows the unavailable message when payment status returns 404", async () => {
    mockedGetJobPaymentStatus.mockRejectedValue({
      response: {
        status: 404,
      },
    });

    await openCompletedJob();

    await waitFor(() => {
      expect(
        screen.getByText(
          "Payment status is not available for this job."
        )
      ).toBeTruthy();
    });
  });

  it("shows a generic payment error for an unexpected API failure", async () => {
    mockedGetJobPaymentStatus.mockRejectedValue({
      response: {
        status: 500,
      },
    });

    await openCompletedJob();

    await waitFor(() => {
      expect(
        screen.getByText(
          "Payment status is temporarily unavailable. Please try again."
        )
      ).toBeTruthy();
    });
  });

  it("requests payment status for the selected job only", async () => {
    mockedGetJobPaymentStatus.mockResolvedValue(
      paymentStatusRecord as any
    );

    await openCompletedJob();

    await waitFor(() => {
      expect(mockedGetJobPaymentStatus).toHaveBeenCalledWith(101);
    });

    expect(mockedGetJobPaymentStatus).toHaveBeenCalledTimes(1);
  });
});


describe("JobsPage - Task 9 Customer Feedback", () => {
  it("loads and displays backend-authoritative customer feedback for a completed job", async () => {
    mockedGetJobCustomerFeedback.mockResolvedValue(
      customerFeedbackRecord as any
    );

    await openCompletedJob();

    await waitFor(() => {
      expect(mockedGetJobCustomerFeedback).toHaveBeenCalledTimes(1);
      expect(mockedGetJobCustomerFeedback).toHaveBeenCalledWith(101);
    });

    const feedbackHeading = screen.getByRole("heading", {
      name: "Customer Feedback",
    });

    expect(feedbackHeading).toBeTruthy();

    const feedbackSection = feedbackHeading
      .closest("div")
      ?.parentElement
      ?.parentElement;

    expect(feedbackSection).toBeTruthy();

    const feedback = within(feedbackSection as HTMLElement);

    expect(feedback.getByText("5/5")).toBeTruthy();
    expect(
      feedback.getByText(
        "Excellent service. The technician resolved the issue quickly."
      )
    ).toBeTruthy();
    expect(feedback.getByText("Submitted At")).toBeTruthy();
    expect(feedback.getByText("Last Updated")).toBeTruthy();
    expect(feedback.getByLabelText("5 out of 5 stars")).toBeTruthy();
  });

  it("renders the feedback loading state while customer feedback is being fetched", async () => {
    let resolveFeedback!: (value: any) => void;

    mockedGetJobCustomerFeedback.mockReturnValue(
      new Promise((resolve) => {
        resolveFeedback = resolve;
      })
    );

    render(<JobCreationForm />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "View job" })
      ).toBeTruthy();
    });

    fireEvent.click(
      screen.getByRole("button", { name: "View job" })
    );

    expect(
      screen.getByText("Loading customer feedback...")
    ).toBeTruthy();

    resolveFeedback(customerFeedbackRecord);

    await waitFor(() => {
      expect(screen.getByText("5/5")).toBeTruthy();
    });
  });

  it("renders the empty feedback state when no feedback record exists", async () => {
    mockedGetJobCustomerFeedback.mockResolvedValue(
      customerFeedbackEmptyResponse as any
    );

    await openCompletedJob();

    await waitFor(() => {
      expect(
        screen.getByText("No customer feedback is available for this job.")
      ).toBeTruthy();
    });
  });

  it("shows the authorization message when customer feedback access returns 403", async () => {
    mockedGetJobCustomerFeedback.mockRejectedValue({
      response: {
        status: 403,
      },
    });

    await openCompletedJob();

    await waitFor(() => {
      expect(
        screen.getByText(
          "You are not authorized to view customer feedback for this job."
        )
      ).toBeTruthy();
    });
  });

  it("shows the unavailable message when customer feedback returns 404", async () => {
    mockedGetJobCustomerFeedback.mockRejectedValue({
      response: {
        status: 404,
      },
    });

    await openCompletedJob();

    await waitFor(() => {
      expect(
        screen.getByText(
          "Customer feedback is not available for this job."
        )
      ).toBeTruthy();
    });
  });

  it("shows a generic customer feedback error for an unexpected API failure", async () => {
    mockedGetJobCustomerFeedback.mockRejectedValue({
      response: {
        status: 500,
      },
    });

    await openCompletedJob();

    await waitFor(() => {
      expect(
        screen.getByText(
          "Customer feedback is temporarily unavailable. Please try again."
        )
      ).toBeTruthy();
    });
  });

  it("does not request customer feedback before the job is completed", async () => {
    mockedGetJobs.mockResolvedValue({
      data: [
        {
          ...completedJob,
          status: "IN_PROGRESS",
        },
      ],
      headers: {
        "x-total-count": "1",
      },
    } as any);

    render(<JobCreationForm />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "View job" })
      ).toBeTruthy();
    });

    fireEvent.click(
      screen.getByRole("button", { name: "View job" })
    );

    await waitFor(() => {
      expect(
        screen.getByText(
          "Invoice will be available after the job is completed."
        )
      ).toBeTruthy();
    });

    expect(mockedGetJobCustomerFeedback).not.toHaveBeenCalled();
  });
});


describe("JobsPage - Task 12 Audit History Export", () => {
  it("renders the audit history export action", async () => {
    await openCompletedJob();

    await waitFor(() => {
      expect(
        screen.getByRole("button", {
          name: "Export audit history",
        })
      ).toBeTruthy();
    });
  });

  it("exports the currently loaded authorized audit history", async () => {
    mockedGetJobAuditHistory.mockResolvedValue({
      job_id: 101,
      events: [
        {
          id: "audit-1",
          job_id: 101,
          event_type: "JOB_ACCEPTED",
          event_category: "STATUS",
          title: "Job Accepted",
          description: "Technician accepted the job.",
          timestamp: "2026-09-24T10:00:00Z",
          from_status: "AWAITING_ACCEPTANCE",
          to_status: "ASSIGNED",
          actor_name: "Technician One",
          actor_role: "technician",
          source: "audit_event",
          is_current: true,
        },
      ],
      page: 1,
      page_size: 25,
      total: 1,
      has_more: false,
    } as any);
    const createObjectURL = vi
      .spyOn(URL, "createObjectURL")
      .mockReturnValue("blob:audit-history");

    const revokeObjectURL = vi
      .spyOn(URL, "revokeObjectURL")
      .mockImplementation(() => {});

    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});

    await openCompletedJob();

    const exportButton = await screen.findByRole("button", {
      name: "Export audit history",
    });

    fireEvent.click(exportButton);

    await waitFor(() => {
      expect(createObjectURL).toHaveBeenCalledTimes(1);
      expect(clickSpy).toHaveBeenCalledTimes(1);
      expect(revokeObjectURL).toHaveBeenCalledWith(
        "blob:audit-history"
      );
    });

    createObjectURL.mockRestore();
    revokeObjectURL.mockRestore();
    clickSpy.mockRestore();
  });

  it("disables audit history export when no events are available", async () => {
    mockedGetJobAuditHistory.mockResolvedValue({
      job_id: 101,
      events: [],
      page: 1,
      page_size: 25,
      total: 0,
      has_more: false,
    } as any);

    await openCompletedJob();

    const exportButton = await screen.findByRole("button", {
      name: "Export audit history",
    });

    expect(
      (exportButton as HTMLButtonElement).disabled
    ).toBe(true);
  });

  it("prevents duplicate audit history exports while exporting", async () => {

    mockedGetJobAuditHistory.mockResolvedValue({
      job_id: 101,
      events: [
        {
          id: "audit-1",
          job_id: 101,
          event_type: "JOB_COMPLETED",
          event_category: "COMPLETION",
          title: "Job completed",
          description: "Job completed successfully.",
          timestamp: "2026-09-24T10:00:00Z",
          from_status: "IN_PROGRESS",
          to_status: "COMPLETED",
          actor_name: "Dispatcher",
          actor_role: "dispatcher",
          source: "enterprise_audit",
          is_current: true,
        },
      ],
      page: 1,
      page_size: 25,
      total: 1,
      has_more: false,
    } as any);
    
    const createObjectURL = vi
      .spyOn(URL, "createObjectURL")
      .mockReturnValue("blob:audit-history");

    const revokeObjectURL = vi
      .spyOn(URL, "revokeObjectURL")
      .mockImplementation(() => {});

    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});

      

    await openCompletedJob();

    const exportButton = await screen.findByRole("button", {
      name: "Export audit history",
    });

    fireEvent.click(exportButton);
    fireEvent.click(exportButton);

    expect(createObjectURL).toHaveBeenCalledTimes(1);

    createObjectURL.mockRestore();
    revokeObjectURL.mockRestore();
    clickSpy.mockRestore();
  });
});