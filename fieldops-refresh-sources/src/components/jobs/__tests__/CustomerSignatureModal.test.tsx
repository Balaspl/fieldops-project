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

import CustomerSignatureModal from "../CustomerSignatureModal";
import {
  captureCustomerSignature,
  getCustomerSignature,
} from "../../../services/planningService";
import type {
  CustomerSignatureResponse,
} from "../../../services/planningService";

vi.mock("../../../services/planningService", () => ({
  captureCustomerSignature: vi.fn(),
  getCustomerSignature: vi.fn(),
}));

const mockedCaptureCustomerSignature = vi.mocked(
  captureCustomerSignature,
);
const mockedGetCustomerSignature = vi.mocked(
  getCustomerSignature,
);

const existingSignature = {
  id: 11,
  job_id: 101,
  job_closure_id: 21,
  signature_data: "data:image/png;base64,EXISTING_SIGNATURE",
  signed_at: "2026-09-26T10:00:00Z",
  created_at: "2026-09-26T10:00:00Z",
  updated_at: "2026-09-26T10:00:00Z",
};

describe("CustomerSignatureModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockedGetCustomerSignature.mockRejectedValue({
      response: { status: 404 },
    });

    HTMLCanvasElement.prototype.getContext = vi
      .fn()
      .mockReturnValue({
        beginPath: vi.fn(),
        moveTo: vi.fn(),
        lineTo: vi.fn(),
        stroke: vi.fn(),
        clearRect: vi.fn(),
        fillRect: vi.fn(),
        setTransform: vi.fn(),
        closePath: vi.fn(),
      } as unknown as CanvasRenderingContext2D);

    HTMLCanvasElement.prototype.toDataURL = vi
      .fn()
      .mockReturnValue("data:image/png;base64,CAPTURED_SIGNATURE");

    vi.spyOn(
      HTMLCanvasElement.prototype,
      "getBoundingClientRect",
    ).mockReturnValue({
      x: 0,
      y: 0,
      width: 700,
      height: 280,
      top: 0,
      right: 700,
      bottom: 280,
      left: 0,
      toJSON: () => ({}),
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the loading state before the signature API resolves", async () => {
    let rejectRequest:
      | ((reason?: unknown) => void)
      | undefined;

    mockedGetCustomerSignature.mockImplementation(
      () =>
        new Promise<CustomerSignatureResponse>(
          (_resolve, reject) => {
            rejectRequest = reject;
          },
        ),
    );

    render(
      <CustomerSignatureModal
        jobId={101}
        onClose={() => {}}
      />,
    );

    expect(
      screen.getByText("Loading customer signature..."),
    ).toBeTruthy();

    rejectRequest?.({
      response: { status: 404 },
    });

    await waitFor(() => {
      expect(
        screen.getByText(
          "Ask the customer to sign inside the box below.",
        ),
      ).toBeTruthy();
    });
  });

  it("shows the empty capture screen when no signature exists", async () => {
    render(
      <CustomerSignatureModal
        jobId={101}
        onClose={() => {}}
      />,
    );

    expect(
      await screen.findByText(
        "Ask the customer to sign inside the box below.",
      ),
    ).toBeTruthy();

    expect(
      screen.getByRole("button", {
        name: "Save Signature",
      }),
    ).toBeTruthy();

    expect(
      mockedGetCustomerSignature,
    ).toHaveBeenCalledWith(101);
  });

  it("renders the backend-authoritative existing signature", async () => {
    mockedGetCustomerSignature.mockResolvedValue(
      existingSignature,
    );

    render(
      <CustomerSignatureModal
        jobId={101}
        onClose={() => {}}
      />,
    );

    expect(
      await screen.findByText(
        "Customer signature already captured.",
      ),
    ).toBeTruthy();

    const image = screen.getByRole("img", {
      name: "Captured customer signature",
    });

    expect(
      image.getAttribute("src"),
    ).toBe(existingSignature.signature_data);

    expect(
      screen.queryByRole("button", {
        name: "Save Signature",
      }),
    ).toBeNull();
  });

  it("treats a 404 signature response as an unavailable signature, not a page failure", async () => {
    mockedGetCustomerSignature.mockRejectedValue({
      response: { status: 404 },
    });

    render(
      <CustomerSignatureModal
        jobId={101}
        onClose={() => {}}
      />,
    );

    expect(
      await screen.findByText(
        "Ask the customer to sign inside the box below.",
      ),
    ).toBeTruthy();

    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("renders a backend error when signature retrieval fails", async () => {
    mockedGetCustomerSignature.mockRejectedValue({
      response: {
        status: 403,
        data: {
          detail: "Insufficient permissions",
        },
      },
    });

    render(
      <CustomerSignatureModal
        jobId={101}
        onClose={() => {}}
      />,
    );

    expect(
      (
        await screen.findByRole("alert")
      ).textContent
    ).toContain("Insufficient permissions");
  });

  it("validates that a signature is present before submission", async () => {
    render(
      <CustomerSignatureModal
        jobId={101}
        onClose={() => {}}
      />,
    );

    await screen.findByText(
      "Ask the customer to sign inside the box below.",
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Save Signature",
      }),
    );

    expect(
      screen.getByRole("alert").textContent,
    ).toContain(
      "Please capture the customer's signature before submitting.",
    );

    expect(
      mockedCaptureCustomerSignature,
    ).not.toHaveBeenCalled();
  });

  it("captures, submits, and reports the backend-authoritative saved signature", async () => {
    mockedCaptureCustomerSignature.mockResolvedValue(
      existingSignature,
    );

    const onSuccess = vi.fn();

    render(
      <CustomerSignatureModal
        jobId={101}
        onClose={() => {}}
        onSuccess={onSuccess}
      />,
    );

    const canvas = await screen.findByLabelText(
      "Customer signature drawing area",
    );

    fireEvent.pointerDown(canvas, {
      clientX: 100,
      clientY: 100,
      pointerId: 1,
    });

    fireEvent.pointerMove(canvas, {
      clientX: 220,
      clientY: 140,
      pointerId: 1,
    });

    fireEvent.pointerUp(canvas, {
      clientX: 220,
      clientY: 140,
      pointerId: 1,
    });

    fireEvent.click(
      screen.getByRole("button", {
        name: "Save Signature",
      }),
    );

    await waitFor(() => {
      expect(
        mockedCaptureCustomerSignature,
      ).toHaveBeenCalledWith(
        101,
        "data:image/png;base64,CAPTURED_SIGNATURE",
      );
    });

    expect(
      await screen.findByText(
        "Customer signature saved successfully.",
      ),
    ).toBeTruthy();

    expect(onSuccess).toHaveBeenCalledWith(
      existingSignature,
    );
  });

  it("prevents duplicate signature submissions while the request is pending", async () => {
    let resolveSave:
      | ((value: CustomerSignatureResponse) => void)
      | undefined;

    mockedCaptureCustomerSignature.mockImplementation(
      () =>
        new Promise<CustomerSignatureResponse>((resolve) => {
          resolveSave = resolve;
        }),
    );

    render(
      <CustomerSignatureModal
        jobId={101}
        onClose={() => {}}
      />,
    );

    const canvas = await screen.findByLabelText(
      "Customer signature drawing area",
    );

    fireEvent.pointerDown(canvas, {
      clientX: 50,
      clientY: 50,
      pointerId: 2,
    });

    fireEvent.pointerUp(canvas, {
      clientX: 50,
      clientY: 50,
      pointerId: 2,
    });

    const saveButton = screen.getByRole("button", {
      name: "Save Signature",
    });

    fireEvent.click(saveButton);
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(
        mockedCaptureCustomerSignature,
      ).toHaveBeenCalledTimes(1);
    });

    expect(
      (
        screen.getByRole("button", {
          name: "Saving signature...",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);

    resolveSave?.(existingSignature);

    await waitFor(() => {
      expect(
        screen.getByText(
          "Customer signature saved successfully.",
        ),
      ).toBeTruthy();
    });
  });

  it("surfaces backend validation or permission failures from signature submission", async () => {
    mockedCaptureCustomerSignature.mockRejectedValue({
      response: {
        status: 403,
        data: {
          detail: "Only technicians can capture customer signatures",
        },
      },
    });

    render(
      <CustomerSignatureModal
        jobId={101}
        onClose={() => {}}
      />,
    );

    const canvas = await screen.findByLabelText(
      "Customer signature drawing area",
    );

    fireEvent.pointerDown(canvas, {
      clientX: 75,
      clientY: 75,
      pointerId: 3,
    });

    fireEvent.pointerUp(canvas, {
      clientX: 75,
      clientY: 75,
      pointerId: 3,
    });

    fireEvent.click(
      screen.getByRole("button", {
        name: "Save Signature",
      }),
    );

    expect(
      (
        await screen.findByRole("alert")
      ).textContent
    ).toContain(
      "Only technicians can capture customer signatures",
    );
  });

  it("clears the locally captured signature without calling the backend", async () => {
    render(
      <CustomerSignatureModal
        jobId={101}
        onClose={() => {}}
      />,
    );

    const canvas = await screen.findByLabelText(
      "Customer signature drawing area",
    );

    fireEvent.pointerDown(canvas, {
      clientX: 90,
      clientY: 90,
      pointerId: 4,
    });

    fireEvent.pointerUp(canvas, {
      clientX: 90,
      clientY: 90,
      pointerId: 4,
    });

    fireEvent.click(
      screen.getByRole("button", {
        name: "Clear",
      }),
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Save Signature",
      }),
    );

    expect(
      screen.getByRole("alert").textContent,
    ).toContain(
      "Please capture the customer's signature before submitting.",
    );

    expect(
      mockedCaptureCustomerSignature,
    ).not.toHaveBeenCalled();
  });

  it("calls onClose from the modal close action", async () => {
    const onClose = vi.fn();

    render(
      <CustomerSignatureModal
        jobId={101}
        onClose={onClose}
      />,
    );

    await screen.findByText(
      "Ask the customer to sign inside the box below.",
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Close customer signature",
      }),
    );

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
