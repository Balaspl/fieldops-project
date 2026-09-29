import React, { useEffect, useRef, useState } from "react";
import { IndianRupee, Loader2, X } from "lucide-react";
import {
  submitTechnicianJobExpense,
  TechnicianJobExpense,
} from "../../services/technicianPortalService";

interface JobExpenseModalProps {
  jobId: number | string;
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: (expense: TechnicianJobExpense) => void | Promise<void>;
}

const MAX_DESCRIPTION_LENGTH = 2_000;

const styles = {
  overlay: {
    position: "fixed" as const,
    inset: 0,
    zIndex: 10000,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "20px",
    background: "rgba(15, 23, 42, 0.5)",
    backdropFilter: "blur(4px)",
  },

  card: {
    width: "100%",
    maxWidth: "460px",
    background: "#fff",
    borderRadius: "18px",
    boxShadow: "0 20px 60px rgba(0,0,0,0.18)",
    padding: "24px",
    boxSizing: "border-box" as const,
  },

  header: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: "16px",
    marginBottom: "20px",
  },

  title: {
    margin: 0,
    color: "#111827",
    fontSize: "20px",
    fontWeight: 800,
  },

  subtitle: {
    margin: "5px 0 0",
    color: "#6B7280",
    fontSize: "13px",
    lineHeight: 1.45,
  },

  close: {
    width: "34px",
    height: "34px",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    border: "1px solid #E5E7EB",
    borderRadius: "9px",
    background: "#fff",
    color: "#6B7280",
    cursor: "pointer",
    flexShrink: 0,
  },

  field: {
    marginBottom: "16px",
  },

  label: {
    display: "block",
    marginBottom: "7px",
    color: "#374151",
    fontSize: "12px",
    fontWeight: 700,
  },

  inputWrap: {
    position: "relative" as const,
  },

  prefix: {
    position: "absolute" as const,
    left: "12px",
    top: "50%",
    transform: "translateY(-50%)",
    color: "#6B7280",
    pointerEvents: "none" as const,
  },

  input: {
    width: "100%",
    boxSizing: "border-box" as const,
    padding: "11px 12px 11px 38px",
    border: "1.5px solid #D1D5DB",
    borderRadius: "9px",
    color: "#111827",
    background: "#fff",
    fontSize: "14px",
    outline: "none",
  },

  textarea: {
    width: "100%",
    minHeight: "112px",
    boxSizing: "border-box" as const,
    padding: "11px 12px",
    border: "1.5px solid #D1D5DB",
    borderRadius: "9px",
    color: "#111827",
    background: "#fff",
    fontSize: "14px",
    lineHeight: 1.45,
    resize: "vertical" as const,
    fontFamily: "inherit",
    outline: "none",
  },

  helper: {
    marginTop: "5px",
    color: "#9CA3AF",
    fontSize: "11px",
  },

  error: {
    marginBottom: "16px",
    padding: "10px 12px",
    borderRadius: "9px",
    background: "#FEF2F2",
    border: "1px solid #FECACA",
    color: "#991B1B",
    fontSize: "12px",
    lineHeight: 1.45,
  },

  footer: {
    display: "flex",
    justifyContent: "flex-end",
    gap: "8px",
    marginTop: "8px",
  },

  secondary: {
    padding: "9px 15px",
    border: "1px solid #D1D5DB",
    borderRadius: "9px",
    background: "#fff",
    color: "#374151",
    fontSize: "12px",
    fontWeight: 700,
    cursor: "pointer",
  },

  primary: {
    padding: "9px 16px",
    border: "none",
    borderRadius: "9px",
    background: "#047857",
    color: "#fff",
    fontSize: "12px",
    fontWeight: 700,
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
    gap: "7px",
  },
};

const getBackendErrorMessage = (error: unknown): string => {
  const response = (error as any)?.response;
  const detail = response?.data?.detail;

  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => item?.msg)
      .filter(
        (item): item is string =>
          typeof item === "string" && !!item.trim(),
      );

    if (messages.length > 0) {
      return messages.join(" ");
    }
  }

  if (response?.status === 403) {
    return "You are not authorized to submit an expense for this job.";
  }

  if (response?.status === 404) {
    return "This job is no longer available for expense submission.";
  }

  return "Unable to submit the expense. Please try again.";
};

const normalizeAmount = (value: string): string => {
  const trimmed = value.trim();

  if (!trimmed) {
    return "";
  }

  const [whole = "", fraction] = trimmed.split(".");

  const normalizedWhole =
    whole.replace(/^0+(?=\d)/, "") || "0";

  if (fraction === undefined) {
    return normalizedWhole;
  }

  return `${normalizedWhole}.${fraction}`;
};

export const JobExpenseModal: React.FC<JobExpenseModalProps> = ({
  jobId,
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submitInFlightRef = useRef(false);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    setAmount("");
    setDescription("");
    setError(null);
    setSubmitting(false);
    submitInFlightRef.current = false;
  }, [isOpen, jobId]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !submitting) {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose, submitting]);

  if (!isOpen) {
    return null;
  }

  const handleSubmit = async (
    event: React.FormEvent<HTMLFormElement>,
  ) => {
    event.preventDefault();

    if (submitInFlightRef.current) {
      return;
    }

    setError(null);

    const canonicalAmount = normalizeAmount(amount);
    const canonicalDescription = description.trim();

    // Client-side validation for immediate UX.
    // Backend remains the final authority.
    if (!canonicalAmount) {
      setError("Expense amount is required.");
      return;
    }

    if (!/^\d+(?:\.\d{0,2})?$/.test(canonicalAmount)) {
      setError(
        "Enter a valid amount with no more than 2 decimal places.",
      );
      return;
    }

    const numericAmount = Number(canonicalAmount);

    if (
      !Number.isFinite(numericAmount) ||
      numericAmount <= 0
    ) {
      setError("Expense amount must be greater than zero.");
      return;
    }

    if (!canonicalDescription) {
      setError("Expense description is required.");
      return;
    }

    if (
      canonicalDescription.length > MAX_DESCRIPTION_LENGTH
    ) {
      setError(
        `Expense description cannot exceed ${MAX_DESCRIPTION_LENGTH} characters.`,
      );
      return;
    }

    submitInFlightRef.current = true;
    setSubmitting(true);

    try {
      const response = await submitTechnicianJobExpense(
        Number(jobId),
        {
          amount: canonicalAmount,
          description: canonicalDescription,
        },
      );

      await onSuccess?.(response.data);

      onClose();
    } catch (requestError) {
      setError(getBackendErrorMessage(requestError));
    } finally {
      submitInFlightRef.current = false;
      setSubmitting(false);
    }
  };

  return (
    <div
      style={styles.overlay}
      role="presentation"
      onMouseDown={(event) => {
        if (
          event.target === event.currentTarget &&
          !submitting
        ) {
          onClose();
        }
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="job-expense-title"
        style={styles.card}
        onMouseDown={(event) =>
          event.stopPropagation()
        }
      >
        <div style={styles.header}>
          <div>
            <h2
              id="job-expense-title"
              style={styles.title}
            >
              Add Expense
            </h2>

            <p style={styles.subtitle}>
              Submit an expense against Job #{jobId}.
            </p>
          </div>

          <button
            type="button"
            aria-label="Close expense dialog"
            style={styles.close}
            disabled={submitting}
            onClick={onClose}
          >
            <X size={17} />
          </button>
        </div>

        <form
          onSubmit={handleSubmit}
          noValidate
        >
          <div style={styles.field}>
            <label
              htmlFor="job-expense-amount"
              style={styles.label}
            >
              Amount
            </label>

            <div style={styles.inputWrap}>
              <IndianRupee
                size={15}
                style={styles.prefix}
              />

              <input
                id="job-expense-amount"
                name="amount"
                type="text"
                inputMode="decimal"
                autoComplete="off"
                value={amount}
                onChange={(event) =>
                  setAmount(event.target.value)
                }
                placeholder="0.00"
                aria-invalid={!!error}
                style={styles.input}
                disabled={submitting}
              />
            </div>

            <div style={styles.helper}>
              Maximum precision: 2 decimal places.
            </div>
          </div>

          <div style={styles.field}>
            <label
              htmlFor="job-expense-description"
              style={styles.label}
            >
              Description
            </label>

            <textarea
              id="job-expense-description"
              name="description"
              value={description}
              maxLength={MAX_DESCRIPTION_LENGTH}
              onChange={(event) =>
                setDescription(event.target.value)
              }
              placeholder="Describe what the expense was for."
              aria-invalid={!!error}
              style={styles.textarea}
              disabled={submitting}
            />

            <div style={styles.helper}>
              {description.length}/
              {MAX_DESCRIPTION_LENGTH}
            </div>
          </div>

          {error && (
            <div
              role="alert"
              style={styles.error}
            >
              {error}
            </div>
          )}

          <div style={styles.footer}>
            <button
              type="button"
              style={{
                ...styles.secondary,
                opacity: submitting ? 0.6 : 1,
                cursor: submitting
                  ? "not-allowed"
                  : "pointer",
              }}
              disabled={submitting}
              onClick={onClose}
            >
              Cancel
            </button>

            <button
              type="submit"
              style={{
                ...styles.primary,
                opacity: submitting ? 0.7 : 1,
                cursor: submitting
                  ? "not-allowed"
                  : "pointer",
              }}
              disabled={submitting}
              data-testid="submit-job-expense"
            >
              {submitting && (
                <Loader2
                  size={14}
                  className="job-expense-spinner"
                />
              )}

              {submitting
                ? "Submitting..."
                : "Submit Expense"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default JobExpenseModal;