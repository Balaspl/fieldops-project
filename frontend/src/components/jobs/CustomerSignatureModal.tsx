import React, {
  PointerEvent as ReactPointerEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  captureCustomerSignature,
  getCustomerSignature,
} from "../../services/planningService";

import type {
  CustomerSignatureResponse,
} from "../../services/planningService";

type CustomerSignatureModalProps = {
  jobId: string | number;
  onClose: () => void;
  onSuccess?: (signature: CustomerSignatureResponse) => void;
};

const CANVAS_WIDTH = 700;
const CANVAS_HEIGHT = 280;

const getBackendErrorMessage = (
  error: unknown,
  fallback: string,
): string => {
  const response = (error as any)?.response;
  const detail = response?.data?.detail;

  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  if (detail && typeof detail === "object") {
    if (
      typeof detail.message === "string" &&
      detail.message.trim()
    ) {
      return detail.message;
    }

    if (
      typeof detail.error === "string" &&
      detail.error.trim()
    ) {
      return detail.error;
    }
  }

  if (
    typeof response?.data?.message === "string" &&
    response.data.message.trim()
  ) {
    return response.data.message;
  }

  return fallback;
};

export const CustomerSignatureModal = ({
  jobId,
  onClose,
  onSuccess,
}: CustomerSignatureModalProps) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawingRef = useRef(false);
  const hasDrawingRef = useRef(false);
  const submitInFlightRef = useRef(false);

  const [signature, setSignature] =
    useState<CustomerSignatureResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [hasDrawing, setHasDrawing] = useState(false);

  const prepareCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    const context = canvas.getContext("2d");
    if (!context) {
      return;
    }

    const ratio =
      typeof window !== "undefined" && window.devicePixelRatio
        ? Math.max(window.devicePixelRatio, 1)
        : 1;

    canvas.width = CANVAS_WIDTH * ratio;
    canvas.height = CANVAS_HEIGHT * ratio;
    canvas.style.width = `${CANVAS_WIDTH}px`;
    canvas.style.height = `${CANVAS_HEIGHT}px`;

    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);
    context.strokeStyle = "#1f2937";
    context.lineWidth = 2;
    context.lineCap = "round";
    context.lineJoin = "round";
  }, []);

  useEffect(() => {
    prepareCanvas();
  }, [prepareCanvas]);

  useEffect(() => {
    let active = true;

    const loadSignature = async () => {
      setLoading(true);
      setError(null);
      setSavedMessage(null);

      try {
        const response = await getCustomerSignature(jobId);

        if (!active) {
          return;
        }

        setSignature(response);
      } catch (requestError) {
        if (!active) {
          return;
        }

        const status =
          (requestError as any)?.response?.status;

        if (status === 404) {
          setSignature(null);
          return;
        }

        setError(
          getBackendErrorMessage(
            requestError,
            "Unable to load the customer signature.",
          ),
        );
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    void loadSignature();

    return () => {
      active = false;
    };
  }, [jobId]);

  const getCanvasPoint = (
    event: ReactPointerEvent<HTMLCanvasElement>,
  ) => {
    const canvas = canvasRef.current;

    if (!canvas) {
      return null;
    }

    const rect = canvas.getBoundingClientRect();

    if (!rect.width || !rect.height) {
      return null;
    }

    return {
      x:
        ((event.clientX - rect.left) / rect.width) *
        CANVAS_WIDTH,
      y:
        ((event.clientY - rect.top) / rect.height) *
        CANVAS_HEIGHT,
    };
  };

  const handlePointerDown = (
    event: ReactPointerEvent<HTMLCanvasElement>,
  ) => {
    if (signature || saving) {
      return;
    }

    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    const point = getCanvasPoint(event);

    if (!canvas || !context || !point) {
      return;
    }

    event.preventDefault();
    canvas.setPointerCapture?.(event.pointerId);

    drawingRef.current = true;
    hasDrawingRef.current = true;
    setHasDrawing(true);

    context.beginPath();
    context.moveTo(point.x, point.y);
    context.lineTo(point.x + 0.01, point.y + 0.01);
    context.stroke();
  };

  const handlePointerMove = (
    event: ReactPointerEvent<HTMLCanvasElement>,
  ) => {
    if (
      !drawingRef.current ||
      signature ||
      saving
    ) {
      return;
    }

    const context = canvasRef.current?.getContext("2d");
    const point = getCanvasPoint(event);

    if (!context || !point) {
      return;
    }

    event.preventDefault();
    context.lineTo(point.x, point.y);
    context.stroke();
  };

  const stopDrawing = (
    event?: ReactPointerEvent<HTMLCanvasElement>,
  ) => {
    drawingRef.current = false;

    if (
      event &&
      canvasRef.current?.hasPointerCapture?.(
        event.pointerId,
      )
    ) {
      canvasRef.current.releasePointerCapture(
        event.pointerId,
      );
    }
  };

  const clearSignature = () => {
    if (signature || saving) {
      return;
    }

    prepareCanvas();
    hasDrawingRef.current = false;
    setHasDrawing(false);
    setError(null);
    setSavedMessage(null);
  };

  const handleSubmit = async () => {
    if (submitInFlightRef.current || saving) {
      return;
    }

    const canvas = canvasRef.current;

    if (!canvas || !hasDrawingRef.current) {
      setError(
        "Please capture the customer's signature before submitting.",
      );
      return;
    }

    let signatureData = "";

    try {
      signatureData = canvas.toDataURL("image/png");
    } catch {
      setError(
        "Unable to prepare the customer signature. Please try again.",
      );
      return;
    }

    if (!signatureData.startsWith("data:image/png;base64,")) {
      setError(
        "The captured signature format is not supported.",
      );
      return;
    }

    submitInFlightRef.current = true;
    setSaving(true);
    setError(null);
    setSavedMessage(null);

    try {
      const response = await captureCustomerSignature(
        jobId,
        signatureData,
      );

      setSignature(response);
      setSavedMessage(
        "Customer signature saved successfully.",
      );
      onSuccess?.(response);
    } catch (requestError) {
      setError(
        getBackendErrorMessage(
          requestError,
          "Unable to save the customer signature.",
        ),
      );
    } finally {
      submitInFlightRef.current = false;
      setSaving(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="customer-signature-title"
      data-testid="customer-signature-modal"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 1000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 20,
        background: "rgba(15, 23, 42, 0.55)",
      }}
    >
      <div
        style={{
          width: "min(760px, 100%)",
          maxHeight: "90vh",
          overflowY: "auto",
          background: "#ffffff",
          borderRadius: 14,
          boxShadow: "0 20px 45px rgba(15, 23, 42, 0.25)",
          padding: 24,
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: 16,
            marginBottom: 18,
          }}
        >
          <div>
            <h2
              id="customer-signature-title"
              style={{
                margin: 0,
                fontSize: 20,
                fontWeight: 700,
                color: "#111827",
              }}
            >
              Customer Signature
            </h2>
            <p
              style={{
                margin: "6px 0 0",
                fontSize: 13,
                color: "#6b7280",
              }}
            >
              Job #{jobId}
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Close customer signature"
            disabled={saving}
            style={{
              border: "none",
              background: "transparent",
              color: "#6b7280",
              cursor: saving ? "not-allowed" : "pointer",
              fontSize: 22,
              lineHeight: 1,
            }}
          >
            ×
          </button>
        </div>

        {loading ? (
          <div
            role="status"
            style={{
              padding: "28px 12px",
              textAlign: "center",
              color: "#6b7280",
              fontSize: 14,
            }}
          >
            Loading customer signature...
          </div>
        ) : (
          <>
            {signature ? (
              <div>
                <div
                  style={{
                    marginBottom: 12,
                    padding: 12,
                    borderRadius: 10,
                    background: "#ecfdf5",
                    border: "1px solid #a7f3d0",
                    color: "#065f46",
                    fontSize: 13,
                  }}
                  role="status"
                >
                  Customer signature already captured.
                </div>

                <div
                  style={{
                    border: "1px solid #d1d5db",
                    borderRadius: 10,
                    background: "#ffffff",
                    padding: 10,
                    overflowX: "auto",
                  }}
                >
                  <img
                    src={signature.signature_data}
                    alt="Captured customer signature"
                    style={{
                      display: "block",
                      width: "100%",
                      minWidth: 420,
                      maxHeight: 280,
                      objectFit: "contain",
                      background: "#ffffff",
                    }}
                  />
                </div>
              </div>
            ) : (
              <div>
                <p
                  style={{
                    margin: "0 0 10px",
                    fontSize: 13,
                    color: "#374151",
                  }}
                >
                  Ask the customer to sign inside the box below.
                </p>

                <div
                  style={{
                    border: "1px solid #d1d5db",
                    borderRadius: 10,
                    overflowX: "auto",
                    background: "#ffffff",
                  }}
                >
                  <canvas
                    ref={canvasRef}
                    width={CANVAS_WIDTH}
                    height={CANVAS_HEIGHT}
                    aria-label="Customer signature drawing area"
                    onPointerDown={handlePointerDown}
                    onPointerMove={handlePointerMove}
                    onPointerUp={stopDrawing}
                    onPointerCancel={stopDrawing}
                    onPointerLeave={stopDrawing}
                    style={{
                      display: "block",
                      width: "100%",
                      maxWidth: CANVAS_WIDTH,
                      height: "auto",
                      touchAction: "none",
                      cursor: saving
                        ? "not-allowed"
                        : "crosshair",
                    }}
                  />
                </div>

                <div
                  style={{
                    marginTop: 8,
                    fontSize: 12,
                    color: "#6b7280",
                  }}
                >
                  Signature is captured as a PNG data URL and submitted
                  through the backend customer-confirmation endpoint.
                </div>
              </div>
            )}

            {error && (
              <div
                role="alert"
                style={{
                  marginTop: 14,
                  padding: 12,
                  borderRadius: 10,
                  background: "#fef2f2",
                  border: "1px solid #fecaca",
                  color: "#991b1b",
                  fontSize: 13,
                  lineHeight: 1.5,
                }}
              >
                {error}
              </div>
            )}

            {savedMessage && (
              <div
                role="status"
                style={{
                  marginTop: 14,
                  padding: 12,
                  borderRadius: 10,
                  background: "#eff6ff",
                  border: "1px solid #bfdbfe",
                  color: "#1e40af",
                  fontSize: 13,
                }}
              >
                {savedMessage}
              </div>
            )}

            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                gap: 10,
                marginTop: 18,
              }}
            >
              <button
                type="button"
                onClick={onClose}
                disabled={saving}
                style={{
                  border: "1px solid #d1d5db",
                  borderRadius: 8,
                  padding: "9px 14px",
                  background: "#ffffff",
                  color: "#374151",
                  cursor: saving ? "not-allowed" : "pointer",
                }}
              >
                Close
              </button>

              {!signature && (
                <>
                  <button
                    type="button"
                    onClick={clearSignature}
                    disabled={saving || !hasDrawing}
                    style={{
                      border: "1px solid #d1d5db",
                      borderRadius: 8,
                      padding: "9px 14px",
                      background: "#ffffff",
                      color: "#374151",
                      cursor:
                        saving || !hasDrawingRef.current
                          ? "not-allowed"
                          : "pointer",
                    }}
                  >
                    Clear
                  </button>

                  <button
                    type="button"
                    onClick={handleSubmit}
                    disabled={saving}
                    style={{
                      border: "none",
                      borderRadius: 8,
                      padding: "9px 16px",
                      background: saving
                        ? "#93c5fd"
                        : "#2563eb",
                      color: "#ffffff",
                      fontWeight: 600,
                      cursor: saving ? "not-allowed" : "pointer",
                    }}
                  >
                    {saving
                      ? "Saving signature..."
                      : "Save Signature"}
                  </button>
                </>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default CustomerSignatureModal;
