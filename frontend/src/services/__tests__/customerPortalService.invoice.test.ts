import { beforeEach, describe, expect, it, vi } from "vitest";

import api from "../api";
import {
  getCustomerInvoice,
  getCustomerInvoices,
  getCustomerPaymentStatus,
} from "../customerPortalService";

vi.mock("../api", () => ({
  default: {
    get: vi.fn(),
  },
}));

const mockedApi = vi.mocked(api);

describe("customerPortalService - customer invoice API", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("requests the authenticated customer's invoice collection", async () => {
    const response = {
      data: [
        {
          id: "501",
          job_id: 101,
          customer_name: "Customer User",
          service_type: "HVAC Repair",
          location: "12 Main Street, Chennai",
          work_summary: "Replaced failed compressor.",
          labour_cost: 1500,
          material_cost: 2500,
          subtotal: 4000,
          gst_rate: 5,
          gst_amount: 200,
          total_amount: 4200,
          completed_at: "2026-09-29T15:30:00Z",
          created_at: "2026-09-29T16:00:00Z",
        },
      ],
    };

    mockedApi.get.mockResolvedValueOnce(response as any);

    const result = await getCustomerInvoices();

    expect(mockedApi.get).toHaveBeenCalledTimes(1);
    expect(mockedApi.get).toHaveBeenCalledWith(
      "/api/customer/invoices",
    );
    expect(result).toBe(response);
    expect(result.data).toHaveLength(1);
    expect(result.data[0].job_id).toBe(101);
  });

  it("requests one customer invoice by job id using the backend ownership scope", async () => {
    const response = {
      data: {
        id: "501",
        job_id: 101,
        customer_name: "Customer User",
        service_type: "HVAC Repair",
        location: "12 Main Street, Chennai",
        work_summary: "Replaced failed compressor.",
        labour_cost: 1500,
        material_cost: 2500,
        subtotal: 4000,
        gst_rate: 5,
        gst_amount: 200,
        total_amount: 4200,
        completed_at: "2026-09-29T15:30:00Z",
        created_at: "2026-09-29T16:00:00Z",
      },
    };

    mockedApi.get.mockResolvedValueOnce(response as any);

    const result = await getCustomerInvoice(101);

    expect(mockedApi.get).toHaveBeenCalledTimes(1);
    expect(mockedApi.get).toHaveBeenCalledWith(
      "/api/customer/invoices/101",
    );
    expect(result).toBe(response);
    expect(result.data.total_amount).toBe(4200);
  });

  it("requests the backend-authoritative payment status by job id", async () => {
    const response = {
      data: {
        job_id: 101,
        invoice_id: 501,
        status: "SUCCESSFUL",
        updated_at: "2026-09-29T17:00:00Z",
      },
    };

    mockedApi.get.mockResolvedValueOnce(response as any);

    const result = await getCustomerPaymentStatus(101);

    expect(mockedApi.get).toHaveBeenCalledTimes(1);
    expect(mockedApi.get).toHaveBeenCalledWith(
      "/api/customer/invoices/101/payment-status",
    );
    expect(result).toBe(response);
    expect(result.data.job_id).toBe(101);
    expect(result.data.invoice_id).toBe(501);
    expect(result.data.status).toBe("SUCCESSFUL");
    expect(result.data.updated_at).toBe(
      "2026-09-29T17:00:00Z",
    );
  });

  it("does not add customer identity or tenant selectors to customer requests", async () => {
    mockedApi.get
      .mockResolvedValueOnce({ data: [] } as any)
      .mockResolvedValueOnce({
        data: {
          id: "501",
          job_id: 101,
        },
      } as any)
      .mockResolvedValueOnce({
        data: {
          job_id: 101,
          invoice_id: 501,
          status: "PENDING",
          updated_at: "2026-09-29T17:00:00Z",
        },
      } as any);

    await getCustomerInvoices();
    await getCustomerInvoice(101);
    await getCustomerPaymentStatus(101);

    const calls = mockedApi.get.mock.calls;

    expect(calls).toEqual([
      ["/api/customer/invoices"],
      ["/api/customer/invoices/101"],
      ["/api/customer/invoices/101/payment-status"],
    ]);

    for (const [url, config] of calls) {
      expect(String(url)).not.toContain("tenant_id");
      expect(String(url)).not.toContain("user_id");
      expect(config).toBeUndefined();
    }
  });
});