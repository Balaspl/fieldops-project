import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import JobExpenseModal from "../JobExpenseModal";
import {
  submitTechnicianJobExpense,
  TechnicianJobExpense,
} from "../../../services/technicianPortalService";

vi.mock("../../../services/technicianPortalService", () => ({
  submitTechnicianJobExpense: vi.fn(),
}));

const mockedSubmitTechnicianJobExpense = vi.mocked(
  submitTechnicianJobExpense,
);

const representativeExpense: TechnicianJobExpense = {
  id: 41,
  job_id: 101,
  technician_id: 1001,
  amount: "125.50",
  description: "Parking fee",
  submitted_at: "2026-09-28T08:00:00Z",
  created_at: "2026-09-28T08:00:00Z",
  updated_at: "2026-09-28T08:00:00Z",
};

describe("JobExpenseModal", () => {
  const defaultProps = {
    jobId: 101,
    isOpen: true,
    onClose: vi.fn(),
    onSuccess: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the expense form", () => {
    render(<JobExpenseModal {...defaultProps} />);

    expect(
      screen.getByRole("dialog"),
    ).toBeTruthy();

    expect(
      screen.getByRole("heading", {
        name: "Add Expense",
      }),
    ).toBeTruthy();

    expect(
      screen.getByText(
        "Submit an expense against Job #101.",
      ),
    ).toBeTruthy();

    expect(
      screen.getByLabelText("Amount"),
    ).toBeTruthy();

    expect(
      screen.getByLabelText("Description"),
    ).toBeTruthy();

    expect(
      screen.getByRole("button", {
        name: "Submit Expense",
      }),
    ).toBeTruthy();
  });

  it("renders nothing when the modal is closed", () => {
    render(
      <JobExpenseModal
        {...defaultProps}
        isOpen={false}
      />,
    );

    expect(
      screen.queryByRole("dialog"),
    ).toBeNull();
  });

  it("requires an expense amount", async () => {
    render(<JobExpenseModal {...defaultProps} />);

    fireEvent.change(
      screen.getByLabelText("Description"),
      {
        target: {
          value: "Parking fee",
        },
      },
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Submit Expense",
      }),
    );

    expect(
      (await screen.findByRole("alert")).textContent,
    ).toBe("Expense amount is required.");

    expect(
      mockedSubmitTechnicianJobExpense,
    ).not.toHaveBeenCalled();
  });

  it("requires a non-empty description", async () => {
    render(<JobExpenseModal {...defaultProps} />);

    fireEvent.change(
      screen.getByLabelText("Amount"),
      {
        target: {
          value: "125.50",
        },
      },
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Submit Expense",
      }),
    );

    expect(
      (await screen.findByRole("alert")).textContent,
    ).toBe("Expense description is required.");

    expect(
      mockedSubmitTechnicianJobExpense,
    ).not.toHaveBeenCalled();
  });

  it("rejects more than two decimal places", async () => {
    render(<JobExpenseModal {...defaultProps} />);

    fireEvent.change(
      screen.getByLabelText("Amount"),
      {
        target: {
          value: "125.501",
        },
      },
    );

    fireEvent.change(
      screen.getByLabelText("Description"),
      {
        target: {
          value: "Parking fee",
        },
      },
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Submit Expense",
      }),
    );

    expect(
      (await screen.findByRole("alert")).textContent,
    ).toBe(
      "Enter a valid amount with no more than 2 decimal places.",
    );

    expect(
      mockedSubmitTechnicianJobExpense,
    ).not.toHaveBeenCalled();
  });

  it("rejects zero amount", async () => {
    render(<JobExpenseModal {...defaultProps} />);

    fireEvent.change(
      screen.getByLabelText("Amount"),
      {
        target: {
          value: "0.00",
        },
      },
    );

    fireEvent.change(
      screen.getByLabelText("Description"),
      {
        target: {
          value: "Parking fee",
        },
      },
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Submit Expense",
      }),
    );

    expect(
      (await screen.findByRole("alert")).textContent,
    ).toBe(
      "Expense amount must be greater than zero.",
    );

    expect(
      mockedSubmitTechnicianJobExpense,
    ).not.toHaveBeenCalled();
  });

  it("rejects negative amount", async () => {
    render(<JobExpenseModal {...defaultProps} />);

    fireEvent.change(
      screen.getByLabelText("Amount"),
      {
        target: {
          value: "-25.00",
        },
      },
    );

    fireEvent.change(
      screen.getByLabelText("Description"),
      {
        target: {
          value: "Parking fee",
        },
      },
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Submit Expense",
      }),
    );

    expect(
      (await screen.findByRole("alert")).textContent,
    ).toBe(
      "Enter a valid amount with no more than 2 decimal places.",
    );

    expect(
      mockedSubmitTechnicianJobExpense,
    ).not.toHaveBeenCalled();
  });

  it("submits canonicalized amount and trimmed description", async () => {
    mockedSubmitTechnicianJobExpense.mockResolvedValue({
      data: representativeExpense,
    } as any);

    const onClose = vi.fn();
    const onSuccess = vi.fn();

    render(
      <JobExpenseModal
        {...defaultProps}
        onClose={onClose}
        onSuccess={onSuccess}
      />,
    );

    fireEvent.change(
      screen.getByLabelText("Amount"),
      {
        target: {
          value: "00125.50",
        },
      },
    );

    fireEvent.change(
      screen.getByLabelText("Description"),
      {
        target: {
          value: "  Parking fee  ",
        },
      },
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Submit Expense",
      }),
    );

    await waitFor(() => {
      expect(
        mockedSubmitTechnicianJobExpense,
      ).toHaveBeenCalledWith(101, {
        amount: "125.50",
        description: "Parking fee",
      });
    });

    expect(onSuccess).toHaveBeenCalledWith(
      representativeExpense,
    );

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("prevents duplicate submissions while the request is pending", async () => {
    let resolveRequest:
      | ((value: { data: TechnicianJobExpense }) => void)
      | undefined;

    mockedSubmitTechnicianJobExpense.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveRequest = resolve;
        }) as any,
    );

    render(<JobExpenseModal {...defaultProps} />);

    fireEvent.change(
      screen.getByLabelText("Amount"),
      {
        target: {
          value: "125.50",
        },
      },
    );

    fireEvent.change(
      screen.getByLabelText("Description"),
      {
        target: {
          value: "Parking fee",
        },
      },
    );

    const submitButton = screen.getByRole(
      "button",
      {
        name: "Submit Expense",
      },
    );

    fireEvent.click(submitButton);
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(
        mockedSubmitTechnicianJobExpense,
      ).toHaveBeenCalledTimes(1);
    });

    expect(
      screen.getByText("Submitting..."),
    ).toBeTruthy();

    expect(
      (
        screen.getByRole("button", {
          name: "Submitting...",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);

    resolveRequest?.({
      data: representativeExpense,
    });

    await waitFor(() => {
      expect(
        defaultProps.onClose,
      ).toHaveBeenCalledTimes(1);
    });
  });

  it("surfaces backend validation or authorization errors", async () => {
    mockedSubmitTechnicianJobExpense.mockRejectedValue({
      response: {
        status: 403,
        data: {
          detail:
            "You are not authorized to submit an expense for this job.",
        },
      },
    });

    render(<JobExpenseModal {...defaultProps} />);

    fireEvent.change(
      screen.getByLabelText("Amount"),
      {
        target: {
          value: "125.50",
        },
      },
    );

    fireEvent.change(
      screen.getByLabelText("Description"),
      {
        target: {
          value: "Parking fee",
        },
      },
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Submit Expense",
      }),
    );

    expect(
      (await screen.findByRole("alert")).textContent,
    ).toBe(
      "You are not authorized to submit an expense for this job.",
    );

    expect(
      defaultProps.onClose,
    ).not.toHaveBeenCalled();
  });

  it("uses the backend validation message when available", async () => {
    mockedSubmitTechnicianJobExpense.mockRejectedValue({
      response: {
        status: 422,
        data: {
          detail:
            "Expense amount must have at most 2 decimal places.",
        },
      },
    });

    render(<JobExpenseModal {...defaultProps} />);

    fireEvent.change(
      screen.getByLabelText("Amount"),
      {
        target: {
          value: "125.50",
        },
      },
    );

    fireEvent.change(
      screen.getByLabelText("Description"),
      {
        target: {
          value: "Parking fee",
        },
      },
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Submit Expense",
      }),
    );

    expect(
      (await screen.findByRole("alert")).textContent,
    ).toBe(
      "Expense amount must have at most 2 decimal places.",
    );

    expect(
      defaultProps.onClose,
    ).not.toHaveBeenCalled();
  });

  it("uses a generic message for unexpected API failures", async () => {
    mockedSubmitTechnicianJobExpense.mockRejectedValue(
      new Error("Network failure"),
    );

    render(<JobExpenseModal {...defaultProps} />);

    fireEvent.change(
      screen.getByLabelText("Amount"),
      {
        target: {
          value: "25.00",
        },
      },
    );

    fireEvent.change(
      screen.getByLabelText("Description"),
      {
        target: {
          value: "Fuel",
        },
      },
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Submit Expense",
      }),
    );

    expect(
      (await screen.findByRole("alert")).textContent,
    ).toBe(
      "Unable to submit the expense. Please try again.",
    );

    expect(
      defaultProps.onClose,
    ).not.toHaveBeenCalled();
  });

  it("closes from the Cancel button without making an API request", () => {
    const onClose = vi.fn();

    render(
      <JobExpenseModal
        {...defaultProps}
        onClose={onClose}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Cancel",
      }),
    );

    expect(onClose).toHaveBeenCalledTimes(1);

    expect(
      mockedSubmitTechnicianJobExpense,
    ).not.toHaveBeenCalled();
  });

  it("closes from the close button without making an API request", () => {
    const onClose = vi.fn();

    render(
      <JobExpenseModal
        {...defaultProps}
        onClose={onClose}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "Close expense dialog",
      }),
    );

    expect(onClose).toHaveBeenCalledTimes(1);

    expect(
      mockedSubmitTechnicianJobExpense,
    ).not.toHaveBeenCalled();
  });
});
