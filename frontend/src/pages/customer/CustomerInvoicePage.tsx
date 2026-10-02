

import { useCallback, useEffect, useState } from "react";

import {

  AlertCircle,

  Calendar,

  CheckCircle,

  FileText,

  MapPin,

  Receipt,

  RefreshCw,

} from "lucide-react";

import {
  CustomerInvoiceResponse,
  CustomerPaymentHistoryResponse,
  CustomerPaymentStatusResponse,
  getCustomerInvoices,
  getCustomerPaymentHistory,
  getCustomerPaymentStatus,
} from "../../services/customerPortalService";

function formatCurrency(value: number) {

  return new Intl.NumberFormat("en-IN", {

    style: "currency",

    currency: "INR",

    minimumFractionDigits: 2,

    maximumFractionDigits: 2,

  }).format(value);

}

function formatDate(value: string | null) {

  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return "—";

  return date.toLocaleDateString("en-IN", {

    day: "2-digit",

    month: "short",

    year: "numeric",

  });

}

function getPaymentStatusPresentation(
  status: string,
) {

  switch (status) {

    case "SUCCESSFUL":

      return {

        label: "Payment confirmed",

        message: "Payment has been confirmed by the billing backend.",

        icon: CheckCircle,

      };

    case "PENDING":

      return {

        label: "Payment pending",

        message: "Payment is awaiting backend verification.",

        icon: RefreshCw,

      };

    case "FAILED":

      return {

        label: "Payment failed",

        message: "The latest backend payment status is failed.",

        icon: AlertCircle,

      };

    default:

      return {

        label: "Online payment unavailable",

        message:

          "Online payment status is currently unavailable. Please try again later.",

        icon: AlertCircle,

      };

  }

}

function getErrorMessage(error: unknown) {

  const responseStatus =

    (error as { response?: { status?: number } } | null)?.response?.status;

  if (responseStatus === 401) {

    return "Your session has expired. Please sign in again.";

  }

  if (responseStatus === 403) {

    return "You do not have permission to view these invoices.";

  }

  return "We couldn't load your invoices right now. Please try again.";

}

export default function CustomerInvoicePage() {

  const [invoices, setInvoices] = useState<CustomerInvoiceResponse[]>([]);

  const [paymentStatuses, setPaymentStatuses] = useState<

    Record<number, CustomerPaymentStatusResponse>

  >({});

  const [paymentHistory, setPaymentHistory] = useState<
    CustomerPaymentHistoryResponse[]
  >([]);

  const [paymentHistoryLoading, setPaymentHistoryLoading] =
    useState(true);

  const [paymentHistoryError, setPaymentHistoryError] =
    useState<string | null>(null);

  const [loading, setLoading] = useState(true);

  const [error, setError] = useState<string | null>(null);

  const loadInvoices = useCallback(async () => {

    setLoading(true);

    setError(null);

    setPaymentStatuses({});

    try {

      const response = await getCustomerInvoices();

      const nextInvoices = Array.isArray(response.data)

        ? response.data

        : [];

      setInvoices(nextInvoices);

      if (nextInvoices.length === 0) {

        return;

      }

      const paymentResults = await Promise.all(

        nextInvoices.map(async (invoice) => {

          try {

            const paymentResponse = await getCustomerPaymentStatus(

              invoice.job_id,

            );

            return {

              jobId: invoice.job_id,

              status: paymentResponse.data,

            };

          } catch {

            return {

              jobId: invoice.job_id,

              status: {

                job_id: invoice.job_id,

                invoice_id: null,

                status: "UNAVAILABLE" as const,

                updated_at: null,

              },

            };

          }

        }),

      );

      const nextPaymentStatuses: Record<

        number,

        CustomerPaymentStatusResponse

      > = {};

      paymentResults.forEach(({ jobId, status }) => {

        nextPaymentStatuses[jobId] = status;

      });

      setPaymentStatuses(nextPaymentStatuses);

    } catch (requestError) {

      setInvoices([]);

      setPaymentStatuses({});

      setError(getErrorMessage(requestError));

    } finally {

      setLoading(false);

    }

  }, []);

  const loadPaymentHistory = useCallback(async () => {
    setPaymentHistoryLoading(true);
    setPaymentHistoryError(null);

    try {
      const response = await getCustomerPaymentHistory();

      setPaymentHistory(
        Array.isArray(response.data)
          ? response.data
          : [],
      );
    } catch (requestError) {
      setPaymentHistory([]);

      const responseStatus =
        (
          requestError as {
            response?: {
              status?: number;
            };
          } | null
        )?.response?.status;

      if (responseStatus === 401) {
        setPaymentHistoryError(
          "Your session has expired. Please sign in again.",
        );
      } else if (responseStatus === 403) {
        setPaymentHistoryError(
          "You do not have permission to view payment history.",
        );
      } else {
        setPaymentHistoryError(
          "We couldn't load your payment history right now. Please try again.",
        );
      }
    } finally {
      setPaymentHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadInvoices();
  }, [loadInvoices]);

  useEffect(() => {
    void loadPaymentHistory();
  }, [loadPaymentHistory]);

  return (

    <div

      style={{

        padding: "24px",

        height: "100%",

        overflowY: "auto",

        background: "#EEF4F1",

        fontFamily: "'Inter', sans-serif",

        boxSizing: "border-box",

      }}

      data-testid="customer-invoices-page"

    >

      <div

        style={{

          display: "flex",

          justifyContent: "space-between",

          alignItems: "flex-start",

          gap: "16px",

          marginBottom: "24px",

          flexWrap: "wrap",

        }}

      >

        <div>

          <h1

            style={{

              margin: 0,

              display: "flex",

              alignItems: "center",

              gap: "9px",

              fontSize: "24px",

              fontWeight: 700,

              color: "#1F2933",

            }}

          >

            <Receipt size={23} color="#7AAE8A" />

            My Invoices

          </h1>

          <p

            style={{

              margin: "6px 0 0",

              fontSize: "14px",

              color: "#6B7280",

              lineHeight: 1.5,

            }}

          >

            View invoices generated from your completed service jobs.

          </p>

        </div>

        <button

          type="button"

          onClick={() => void loadInvoices()}

          disabled={loading}

          aria-label="Refresh invoices"

          style={{

            display: "inline-flex",

            alignItems: "center",

            justifyContent: "center",

            gap: "7px",

            padding: "9px 14px",

            border: "1px solid #CFE0D6",

            borderRadius: "9px",

            background: "#FFFFFF",

            color: "#2F4F3E",

            fontSize: "13px",

            fontWeight: 700,

            cursor: loading ? "default" : "pointer",

            opacity: loading ? 0.6 : 1,

          }}

        >

          <RefreshCw size={15} />

          Refresh

        </button>

      </div>

      {loading ? (

        <div

          role="status"

          aria-live="polite"

          data-testid="customer-invoices-loading"

          style={{

            minHeight: "220px",

            background: "#FFFFFF",

            border: "1px solid #E3ECE7",

            borderRadius: "14px",

            display: "flex",

            alignItems: "center",

            justifyContent: "center",

            color: "#6B7280",

            fontSize: "14px",

          }}

        >

          Loading invoices...

        </div>

      ) : error ? (

        <div

          role="alert"

          data-testid="customer-invoices-error"

          style={{

            minHeight: "220px",

            background: "#FFFFFF",

            border: "1px solid #F2D5D5",

            borderRadius: "14px",

            padding: "28px",

            display: "flex",

            flexDirection: "column",

            alignItems: "center",

            justifyContent: "center",

            textAlign: "center",

            boxSizing: "border-box",

          }}

        >

          <AlertCircle size={30} color="#B42318" />

          <div

            style={{

              marginTop: "10px",

              fontSize: "16px",

              fontWeight: 700,

              color: "#7A271A",

            }}

          >

            Unable to load invoices

          </div>

          <div

            style={{

              marginTop: "6px",

              maxWidth: "520px",

              fontSize: "14px",

              color: "#6B7280",

              lineHeight: 1.5,

            }}

          >

            {error}

          </div>

          <button

            type="button"

            onClick={() => void loadInvoices()}

            style={{

              marginTop: "16px",

              padding: "9px 16px",

              border: "none",

              borderRadius: "9px",

              background: "#7AAE8A",

              color: "#FFFFFF",

              fontSize: "13px",

              fontWeight: 700,

              cursor: "pointer",

            }}

          >

            Try Again

          </button>

        </div>

      ) : invoices.length === 0 ? (

        <div

          data-testid="customer-invoices-empty"

          style={{

            minHeight: "220px",

            background: "#FFFFFF",

            border: "1px solid #E3ECE7",

            borderRadius: "14px",

            padding: "28px",

            display: "flex",

            flexDirection: "column",

            alignItems: "center",

            justifyContent: "center",

            textAlign: "center",

            boxSizing: "border-box",

          }}

        >

          <FileText size={32} color="#9CA3AF" />

          <div

            style={{

              marginTop: "10px",

              fontSize: "16px",

              fontWeight: 700,

              color: "#374151",

            }}

          >

            No invoices yet

          </div>

          <div

            style={{

              marginTop: "6px",

              maxWidth: "500px",

              fontSize: "14px",

              color: "#6B7280",

              lineHeight: 1.5,

            }}

          >

            Invoices will appear here after a completed service job has a

            persisted invoice record.

          </div>

        </div>

      ) : (

        <div

          data-testid="customer-invoices-list"

          style={{

            display: "grid",

            gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",

            gap: "16px",

          }}

        >

          {invoices.map((invoice) => (

            <article

              key={invoice.id}

              data-testid={`customer-invoice-${invoice.id}`}

              style={{

                background: "#FFFFFF",

                border: "1px solid #E3ECE7",

                borderRadius: "14px",

                padding: "18px",

                boxShadow: "0 2px 8px rgba(0,0,0,0.05)",

                minWidth: 0,

              }}

            >

              <div

                style={{

                  display: "flex",

                  justifyContent: "space-between",

                  alignItems: "flex-start",

                  gap: "12px",

                  marginBottom: "14px",

                }}

              >

                <div style={{ minWidth: 0 }}>

                  <div

                    style={{

                      fontSize: "11px",

                      color: "#64748B",

                      fontWeight: 600,

                      marginBottom: "4px",

                    }}

                  >

                    Invoice #{invoice.id}

                  </div>

                  <h2

                    style={{

                      margin: 0,

                      fontSize: "17px",

                      lineHeight: 1.35,

                      color: "#17212B",

                      fontWeight: 700,

                    }}

                  >

                    {invoice.service_type || "Service"}

                  </h2>

                </div>

                <div

                  style={{

                    display: "inline-flex",

                    alignItems: "center",

                    gap: "5px",

                    padding: "4px 9px",

                    borderRadius: "20px",

                    background: "#D1FAE5",

                    color: "#065F46",

                    fontSize: "11px",

                    fontWeight: 700,

                    whiteSpace: "nowrap",

                  }}

                >

                  <CheckCircle size={12} />

                  Persisted

                </div>

              </div>

              <div

                style={{

                  display: "grid",

                  gap: "8px",

                  marginBottom: "16px",

                  color: "#4B5563",

                  fontSize: "13px",

                  lineHeight: 1.45,

                }}

              >

                <div

                  style={{

                    display: "flex",

                    alignItems: "flex-start",

                    gap: "7px",

                  }}

                >

                  <MapPin size={14} color="#7AAE8A" style={{ marginTop: "2px" }} />

                  <span>{invoice.location || "N/A"}</span>

                </div>

                <div

                  style={{

                    display: "flex",

                    alignItems: "flex-start",

                    gap: "7px",

                  }}

                >

                  <Calendar

                    size={14}

                    color="#7AAE8A"

                    style={{ marginTop: "2px" }}

                  />

                  <span>

                    Completed: {formatDate(invoice.completed_at)}

                  </span>

                </div>

              </div>

              <div

                style={{

                  background: "#F8FBF9",

                  border: "1px solid #E6EFEA",

                  borderRadius: "10px",

                  padding: "12px",

                  marginBottom: "14px",

                }}

              >

                <div

                  style={{

                    fontSize: "11px",

                    color: "#64748B",

                    fontWeight: 600,

                    marginBottom: "6px",

                  }}

                >

                  Work Summary

                </div>

                <div

                  style={{

                    fontSize: "13px",

                    color: "#374151",

                    lineHeight: 1.5,

                    whiteSpace: "pre-wrap",

                  }}

                >

                  {invoice.work_summary || "N/A"}

                </div>

              </div>

              <div

                style={{

                  display: "grid",

                  gap: "7px",

                  fontSize: "13px",

                  color: "#4B5563",

                }}

              >

                <div

                  style={{

                    display: "flex",

                    justifyContent: "space-between",

                    gap: "12px",

                  }}

                >

                  <span>Labour</span>

                  <span>{formatCurrency(invoice.labour_cost)}</span>

                </div>

                <div

                  style={{

                    display: "flex",

                    justifyContent: "space-between",

                    gap: "12px",

                  }}

                >

                  <span>Materials</span>

                  <span>{formatCurrency(invoice.material_cost)}</span>

                </div>

                <div

                  style={{

                    display: "flex",

                    justifyContent: "space-between",

                    gap: "12px",

                  }}

                >

                  <span>Subtotal</span>

                  <span>{formatCurrency(invoice.subtotal)}</span>

                </div>

                <div

                  style={{

                    display: "flex",

                    justifyContent: "space-between",

                    gap: "12px",

                  }}

                >

                  <span>GST ({invoice.gst_rate}%)</span>

                  <span>{formatCurrency(invoice.gst_amount)}</span>

                </div>

                <div

                  style={{

                    borderTop: "1px solid #E3ECE7",

                    marginTop: "3px",

                    paddingTop: "9px",

                    display: "flex",

                    justifyContent: "space-between",

                    gap: "12px",

                    fontSize: "15px",

                    fontWeight: 800,

                    color: "#17212B",

                  }}

                >

                  <span>Total</span>

                  <span>{formatCurrency(invoice.total_amount)}</span>

                </div>

              </div>

              <div

                style={{

                  marginTop: "14px",

                  padding: "14px",

                  border: "1px solid #E3ECE7",

                  borderRadius: "10px",

                  background: "#FFFFFF",

                }}

                data-testid={`customer-invoice-payment-${invoice.id}`}

              >

                {(() => {

                  const paymentStatus =

                    paymentStatuses[invoice.job_id]?.status ??

                    "UNAVAILABLE";

                  const paymentPresentation =

                    getPaymentStatusPresentation(paymentStatus);

                  const PaymentIcon =

                    paymentPresentation.icon;

                  return (

                    <>

                      <div

                        style={{

                          display: "flex",

                          alignItems: "center",

                          justifyContent: "space-between",

                          gap: "12px",

                          marginBottom: "8px",

                        }}

                      >

                        <div

                          style={{

                            fontSize: "13px",

                            fontWeight: 800,

                            color: "#17212B",

                          }}

                        >

                          Online Payment

                        </div>

                        <div

                          style={{

                            display: "inline-flex",

                            alignItems: "center",

                            gap: "5px",

                            fontSize: "11px",

                            fontWeight: 700,

                            color:

                              paymentStatus === "SUCCESSFUL"

                                ? "#065F46"

                                : paymentStatus === "PENDING"

                                  ? "#92400E"

                                  : "#7A271A",

                          }}

                          data-testid={`customer-invoice-payment-status-${invoice.id}`}

                        >

                          <PaymentIcon size={13} />

                          {paymentPresentation.label}

                        </div>

                      </div>

                      <div

                        style={{

                          fontSize: "12px",

                          color: "#6B7280",

                          lineHeight: 1.5,

                        }}

                      >

                        {paymentPresentation.message}

                      </div>

                      {paymentStatus === "SUCCESSFUL" ? (

                        <div

                          style={{

                            marginTop: "10px",

                            padding: "9px 11px",

                            borderRadius: "8px",

                            background: "#ECFDF3",

                            color: "#065F46",

                            fontSize: "12px",

                            lineHeight: 1.45,

                          }}

                        >

                          This confirmation comes from the billing backend.

                        </div>

                      ) : paymentStatus === "PENDING" ? (

                        <div

                          style={{

                            marginTop: "10px",

                            padding: "9px 11px",

                            borderRadius: "8px",

                            background: "#FFFAEB",

                            color: "#92400E",

                            fontSize: "12px",

                            lineHeight: 1.45,

                          }}

                        >

                          Do not treat the payment as completed until the

                          backend reports a successful verification.

                        </div>

                      ) : null}

                    </>

                  );

                })()}

              </div>

            </article>

          ))}

        </div>

      )}

  <section
    data-testid="customer-payment-history"
    style={{
      marginTop: "24px",
      background: "#FFFFFF",
      border: "1px solid #E3ECE7",
      borderRadius: "14px",
      padding: "18px",
      boxShadow: "0 2px 8px rgba(0,0,0,0.04)",
    }}
  >
    <div
      style={{
        marginBottom: "14px",
      }}
    >
      <h2
        style={{
          margin: 0,
          fontSize: "18px",
          fontWeight: 800,
          color: "#17212B",
        }}
      >
        Payment History
      </h2>

      <p
        style={{
          margin: "5px 0 0",
          fontSize: "13px",
          color: "#6B7280",
          lineHeight: 1.5,
        }}
      >
        View payment status recorded by the billing backend for your
        invoices.
      </p>
    </div>

    {paymentHistoryLoading ? (
      <div
        role="status"
        aria-live="polite"
        data-testid="customer-payment-history-loading"
        style={{
          minHeight: "120px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#6B7280",
          fontSize: "13px",
        }}
      >
        Loading payment history...
      </div>
    ) : paymentHistoryError ? (
      <div
        role="alert"
        data-testid="customer-payment-history-error"
        style={{
          padding: "16px",
          borderRadius: "10px",
          background: "#FEF3F2",
          border: "1px solid #F2D5D5",
          color: "#7A271A",
          fontSize: "13px",
          lineHeight: 1.5,
        }}
      >
        {paymentHistoryError}
      </div>
    ) : paymentHistory.length === 0 ? (
      <div
        data-testid="customer-payment-history-empty"
        style={{
          minHeight: "120px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          textAlign: "center",
          color: "#6B7280",
          fontSize: "13px",
        }}
      >
        No payment history is available yet.
      </div>
    ) : (
      <div
        data-testid="customer-payment-history-list"
        style={{
          display: "grid",
          gap: "10px",
        }}
      >
        {paymentHistory.map((entry) => {
          const paymentPresentation =
            getPaymentStatusPresentation(
              entry.payment_status,
            );

          return (
            <article
              key={entry.invoice_id}
              data-testid={
                `customer-payment-history-${entry.invoice_id}`
              }
              style={{
                border: "1px solid #E6EFEA",
                borderRadius: "10px",
                padding: "13px",
                background: "#F8FBF9",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  justifyContent: "space-between",
                  gap: "12px",
                  flexWrap: "wrap",
                }}
              >
                <div>
                  <div
                    style={{
                      fontSize: "11px",
                      color: "#64748B",
                      fontWeight: 600,
                    }}
                  >
                    Invoice #{entry.invoice_id}
                  </div>

                  <div
                    style={{
                      marginTop: "3px",
                      fontSize: "14px",
                      fontWeight: 800,
                      color: "#17212B",
                    }}
                  >
                    {entry.service_type || "Service"}
                  </div>
                </div>

                <div
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "5px",
                    padding: "4px 9px",
                    borderRadius: "20px",
                    background:
                      entry.payment_status === "SUCCESSFUL"
                        ? "#D1FAE5"
                        : entry.payment_status === "PENDING"
                          ? "#FEF3C7"
                          : "#FEE2E2",
                    color:
                      entry.payment_status === "SUCCESSFUL"
                        ? "#065F46"
                        : entry.payment_status === "PENDING"
                          ? "#92400E"
                          : "#991B1B",
                    fontSize: "11px",
                    fontWeight: 700,
                    whiteSpace: "nowrap",
                  }}
                  data-testid={
                    `customer-payment-history-status-${entry.invoice_id}`
                  }
                >
                  {paymentPresentation.label}
                </div>
              </div>

              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: "12px",
                  marginTop: "12px",
                  paddingTop: "10px",
                  borderTop: "1px solid #E6EFEA",
                  fontSize: "13px",
                  color: "#4B5563",
                }}
              >
                <span>Invoice total</span>

                <strong
                  style={{
                    color: "#17212B",
                  }}
                >
                  {formatCurrency(entry.total_amount)}
                </strong>
              </div>

              <div
                style={{
                  display: "grid",
                  gap: "5px",
                  marginTop: "8px",
                  fontSize: "12px",
                  color: "#6B7280",
                }}
              >
                <div>
                  Completed: {formatDate(entry.completed_at)}
                </div>

                <div>
                  Invoice created:{" "}
                  {formatDate(entry.invoice_created_at)}
                </div>

                <div>
                  Payment status updated:{" "}
                  {formatDate(
                    entry.payment_status_updated_at,
                  )}
                </div>
              </div>
            </article>
          );
        })}
      </div>
    )}
  </section>
    </div>

  );

}
