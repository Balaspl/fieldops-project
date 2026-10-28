import React, { useState } from "react";
import {
  X,
  Trash2,
  CheckCircle2,
  IndianRupee,
  Image as ImageIcon,
  Upload,
} from "lucide-react";
import { closeJob, type JobClosureData } from "../../services/planningService";

interface JobClosureModalProps {
  jobId: number | string;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (data: JobClosureData) => void;
  paymentFlow?: boolean;
}

const compressImage = (
  file: File,
  maxWidth = 800,
  quality = 0.7,
  onProgress?: (progress: number) => void,
): Promise<string> => {
  return new Promise((resolve) => {
    const reader = new FileReader();

    reader.onload = (event) => {
      const source = event.target?.result;

      // Never continue with an invalid or non-data-URL source.
      if (typeof source !== "string" || !source.startsWith("data:image/")) {
        resolve("");
        return;
      }

      const img = new Image();

      img.onload = () => {
        let width = img.width;
        let height = img.height;

        if (
          !Number.isFinite(width) ||
          !Number.isFinite(height) ||
          width <= 0 ||
          height <= 0
        ) {
          resolve("");
          return;
        }

        if (width > maxWidth) {
          height = Math.round((height * maxWidth) / width);
          width = maxWidth;
        }

        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;

        const ctx = canvas.getContext("2d");

        if (!ctx) {
          // Do NOT return the original user-controlled data URL.
          resolve("");
          return;
        }

        ctx.drawImage(img, 0, 0, width, height);

        // Always return a browser-generated JPEG data URL.
        const compressed = canvas.toDataURL("image/jpeg", quality);

        if (
          typeof compressed === "string" &&
          compressed.startsWith("data:image/jpeg;base64,")
        ) {
          resolve(compressed);
        } else {
          resolve("");
        }
      };

      img.onerror = () => resolve("");

      img.src = source;
    };

    reader.onerror = () => resolve("");

    reader.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress?.(
          Math.round((event.loaded / event.total) * 100),
        );
      }
    };

    reader.onloadend = () => onProgress?.(100);

    reader.readAsDataURL(file);
  });
};

export const JobClosureModal: React.FC<JobClosureModalProps> = ({
  jobId,
  isOpen,
  onClose,
  onSuccess,
  paymentFlow = false,
}) => {
  const [workSummary, setWorkSummary] = useState("");
  const [partsUsedText, setPartsUsedText] = useState("");
  const [durationMinutes, setDurationMinutes] = useState("");
  const [beforeImages, setBeforeImages] = useState<string[]>([]);
  const [afterImages, setAfterImages] = useState<string[]>([]);
  const [uploadingType, setUploadingType] = useState<"before" | "after" | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadResult, setUploadResult] = useState<string | null>(null);

  const [serviceCharge, setServiceCharge] = useState<string>("");
  const [materialCost, setMaterialCost] = useState<string>("");
  const [paymentMethod, setPaymentMethod] = useState<"CASH" | "UPI" | "BOTH">("CASH");
  const [paymentProvider, setPaymentProvider] = useState<"GOOGLE_PAY" | "PHONEPE">("GOOGLE_PAY");
  const [cashAmount, setCashAmount] = useState("");
  const [upiAmount, setUpiAmount] = useState("");
  const [step, setStep] = useState<"service" | "payment" | "upi_demo">("service");
  const [serviceData, setServiceData] = useState<JobClosureData | null>(null);
  const [pendingPaymentData, setPendingPaymentData] = useState<JobClosureData | null>(null);
  const [demoPaymentApproved, setDemoPaymentApproved] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  // -----------------------------
  // COST CALCULATIONS
  // -----------------------------

  const subtotal =
    (Number(serviceCharge) || 0) +
    (Number(materialCost) || 0);

  const gstRate = 0.05;
  const gstAmount = subtotal * gstRate;
  const totalAmount = subtotal + gstAmount;

  // -----------------------------
  // IMAGE UPLOAD
  // -----------------------------

  const handleFileUpload = async (
    e: React.ChangeEvent<HTMLInputElement>,
    type: "before" | "after"
  ) => {
    const files = e.target.files;

    if (!files || files.length === 0) return;

    setUploadError(null);
    setUploadResult(null);
    setUploadingType(type);
    setUploadProgress(0);

    const selectedFiles = Array.from(files);
    const preparedImages: string[] = [];
    let rejectedCount = 0;

    try {
      for (let index = 0; index < selectedFiles.length; index += 1) {
        const file = selectedFiles[index];
        const fileStart = (index / selectedFiles.length) * 100;
        const fileEnd = ((index + 1) / selectedFiles.length) * 100;

        if (!file.type.startsWith("image/")) {
          rejectedCount += 1;
          setUploadError(`\"${file.name}\" is not a supported image file.`);
          continue;
        }

        const compressedBase64 = await compressImage(
          file,
          800,
          0.7,
          (fileProgress) => {
            setUploadProgress(
              Math.round(
                fileStart +
                  ((fileEnd - fileStart) * fileProgress) / 100,
              ),
            );
          },
        );

        if (!compressedBase64) {
          rejectedCount += 1;
          setUploadError(`Unable to prepare \"${file.name}\" for upload.`);
          continue;
        }

        preparedImages.push(compressedBase64);
        setUploadProgress(Math.round(fileEnd));
      }

      if (preparedImages.length > 0) {
        if (type === "before") {
          setBeforeImages((prev) => [...prev, ...preparedImages]);
        } else {
          setAfterImages((prev) => [...prev, ...preparedImages]);
        }

        setUploadResult(
          `${preparedImages.length} photo${preparedImages.length === 1 ? "" : "s"} ready for completion upload${
            rejectedCount > 0
              ? `; ${rejectedCount} file${rejectedCount === 1 ? "" : "s"} rejected`
              : ""
          }.`,
        );
      } else {
        setUploadResult("No photos were added.");
      }
    } finally {
      setUploadProgress(100);
      setUploadingType(null);
      e.target.value = "";
    }
  };

  const handleRemoveBeforeImage = (index: number) => {
    setBeforeImages((prev) => prev.filter((_, i) => i !== index));
  };

  const handleRemoveAfterImage = (index: number) => {
    setAfterImages((prev) => prev.filter((_, i) => i !== index));
  };

  const uploadStatus = uploadingType
    ? `${uploadingType === "after" ? "After" : "Before"} photos preparing ${uploadProgress}%`
    : null;

  // -----------------------------
  // SUBMIT
  // -----------------------------

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (step === "upi_demo") return;

    if (step === "service") {
      const canonicalWorkSummary = workSummary.trim();
      if (!canonicalWorkSummary) {
        setError("Work summary is required.");
        return;
      }
      if (canonicalWorkSummary.length > 5000) {
        setError("Work summary cannot exceed 5000 characters.");
        return;
      }
      if (/<\s*\/?[A-Za-z][^>]*>/.test(canonicalWorkSummary)) {
        setError("Work summary must be plain text and cannot contain markup tags.");
        return;
      }

      const partsUsed = partsUsedText.split(/\r?\n/).map((part) => part.trim()).filter(Boolean);
      const normalizedDuration = durationMinutes.trim();
      let parsedDuration: number | undefined;
      if (normalizedDuration !== "") {
        parsedDuration = Number(normalizedDuration);
        if (!Number.isInteger(parsedDuration) || parsedDuration < 0) {
          setError("Duration must be a whole number of minutes greater than or equal to 0.");
          return;
        }
      }

      const filteredAfterImages = afterImages.map((img) => img.trim()).filter(Boolean);
      if (filteredAfterImages.length === 0) {
        setError("At least one after image is required.");
        return;
      }
      const structuredDetails = [
        `Work Summary: ${canonicalWorkSummary}`,
        partsUsed.length > 0 ? `Parts Used:\n${partsUsed.map((part) => `- ${part}`).join("\n")}` : "Parts Used: None reported",
        parsedDuration !== undefined ? `Duration (minutes): ${parsedDuration}` : "Duration (minutes): Not reported",
      ].join("\n\n");

      const closureDraft: JobClosureData = {
        work_summary: structuredDetails,
        before_images: beforeImages.map((img) => img.trim()).filter(Boolean),
        after_images: filteredAfterImages,
        labour_cost: Math.max(0, Number(serviceCharge) || 0),
        material_cost: Math.max(0, Number(materialCost) || 0),
      };

      if (!paymentFlow) {
        if (serviceCharge.trim() === "" || materialCost.trim() === "") {
          setError("Service Charge and Material Cost are required.");
          return;
        }
        setIsSubmitting(true);
        try {
          await closeJob(jobId, closureDraft);
          onSuccess(closureDraft);
          onClose();
        } catch (err: any) {
          const errMsg = err?.response?.data?.detail || err?.message || "Failed to complete job.";
          setError(typeof errMsg === "string" ? errMsg : JSON.stringify(errMsg));
        } finally {
          setIsSubmitting(false);
        }
        return;
      }

      setServiceData(closureDraft);
      setStep("payment");
      return;
    }

    if (serviceCharge.trim() === "" || materialCost.trim() === "") {
      setError("Service Charge and Material Cost are required.");
      return;
    }
    const service = Number(serviceCharge);
    const materials = Number(materialCost);
    if (!Number.isFinite(service) || service < 0 || !Number.isFinite(materials) || materials < 0) {
      setError("Enter valid non-negative service and material costs.");
      return;
    }
    if (!serviceData) {
      setError("Service details are missing. Return to the service step and try again.");
      return;
    }

    const roundedSubtotal = Math.round((service + materials) * 100) / 100;
    const roundedGst = Math.round(roundedSubtotal * 0.05 * 100) / 100;
    const roundedTotal = Math.round((roundedSubtotal + roundedGst) * 100) / 100;
    const paidCash = paymentMethod === "CASH" ? roundedTotal : paymentMethod === "BOTH" ? Number(cashAmount) : 0;
    const paidUpi = paymentMethod === "UPI" ? roundedTotal : paymentMethod === "BOTH" ? Number(upiAmount) : 0;

    if (paymentMethod === "BOTH") {
      if (!Number.isFinite(paidCash) || !Number.isFinite(paidUpi) || paidCash < 0 || paidUpi < 0) {
        setError("Enter valid cash and UPI amounts.");
        return;
      }
      if (Math.abs(paidCash + paidUpi - roundedTotal) > 0.01) {
        setError("Cash and UPI amounts must add up to the total.");
        return;
      }
    }

    const paymentData: JobClosureData = {
      ...serviceData,
      labour_cost: Math.round(service * 100) / 100,
      material_cost: Math.round(materials * 100) / 100,
      payment_method: paymentMethod,
      payment_provider: paymentMethod === "CASH" ? undefined : paymentProvider,
      payment_demo: paymentMethod !== "CASH",
      cash_amount: Math.round(paidCash * 100) / 100,
      upi_amount: Math.round(paidUpi * 100) / 100,
      gst_amount: roundedGst,
      total_amount: roundedTotal,
    };

    if (paymentMethod !== "CASH") {
      setPendingPaymentData(paymentData);
      setDemoPaymentApproved(false);
      setStep("upi_demo");
      return;
    }

    setIsSubmitting(true);
    try {
      onSuccess(paymentData);
    } catch (submitError: any) {
      setError(submitError?.message || "Unable to continue to customer signature.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const continueFromDemoPayment = () => {
    if (!demoPaymentApproved || !pendingPaymentData) return;
    onSuccess(pendingPaymentData);
  };

  // -----------------------------
  // UI
  // -----------------------------

  return (
    <div
      style={styles.overlay}
      onClick={onClose}
    >
      <div
        style={styles.modal}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={styles.header}>
          <div style={styles.headerTitleWrap}>
            <CheckCircle2
              size={18}
              color="#166534"
            />

            <h3 style={styles.headerTitle}>
              {step === "service" ? "Service Completion" : step === "upi_demo" ? "UPI Payment" : "Payment"} — Job #{jobId}
            </h3>
          </div>

          <button
            style={styles.closeBtn}
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </div>

        {/* Form Body */}
        <form
          onSubmit={handleSubmit}
          style={styles.body}
        >
          {error && (
            <div style={styles.errorAlert}>
              {error}
            </div>
          )}

          {(uploadStatus || uploadResult || uploadError) && (
            <div style={{ marginBottom: 14 }}>
              {(uploadStatus || uploadResult) && (
                <div
                  role="status"
                  style={{
                    padding: "10px 12px",
                    borderRadius: 10,
                    background: "#EFF6FF",
                    border: "1px solid #BFDBFE",
                    color: "#1E40AF",
                    fontSize: 12,
                    marginBottom: uploadError ? 8 : 0,
                  }}
                >
                  <div>{uploadStatus || uploadResult}</div>
                  {uploadingType && (
                    <div
                      aria-label="Photo upload progress"
                      style={{
                        height: 6,
                        marginTop: 8,
                        borderRadius: 999,
                        overflow: "hidden",
                        background: "#DBEAFE",
                      }}
                    >
                      <div
                        style={{
                          width: `${uploadProgress}%`,
                          height: "100%",
                          background: "#2563EB",
                          transition: "width 0.1s ease",
                        }}
                      />
                    </div>
                  )}
                </div>
              )}

              {uploadError && (
                <div
                  role="alert"
                  style={{
                    padding: "10px 12px",
                    borderRadius: 10,
                    background: "#FEF2F2",
                    border: "1px solid #FECACA",
                    color: "#991B1B",
                    fontSize: 12,
                  }}
                >
                  {uploadError}
                </div>
              )}
            </div>
          )}

          {step === "service" ? (
          <>
          {/* Work Summary */}
          <div style={styles.formGroup}>
            <label style={styles.label}>
              Work Summary{" "}
              <span style={styles.req}>*</span>
            </label>

            <textarea
              data-testid="work-report-summary"
              style={styles.textarea}
              rows={3}
              maxLength={5000}
              value={workSummary}
              onChange={(e) =>
                setWorkSummary(e.target.value)
              }
              placeholder="Describe work completed, tests run, and final status..."
              required
            />
          </div>

          {/* Structured Work Report */}
          <div
            style={{
              fontSize: "15px",
              fontWeight: 700,
              color: "#166534",
              marginTop: "4px",
              marginBottom: "-4px",
            }}
          >
            Work Report
          </div>
          <div style={styles.reportGrid}>
            {/* Parts Used */}
            <div style={styles.formGroup}>
              <label style={styles.label}>
                Parts Used (Optional)
              </label>

              <textarea
                data-testid="work-report-parts"
                style={styles.textarea}
                rows={4}
                value={partsUsedText}
                onChange={(e) => setPartsUsedText(e.target.value)}
                placeholder="Enter one part per line..."
              />

              <div style={styles.helperText}>
                Each non-empty line is sent as one structured part.
              </div>
            </div>

            {/* Duration */}
            <div style={styles.formGroup}>
              <label style={styles.label}>
                Duration (minutes)
              </label>

              <input
                data-testid="work-report-duration"
                type="number"
                min="0"
                step="1"
                style={styles.input}
                value={durationMinutes}
                onChange={(e) => setDurationMinutes(e.target.value)}
                placeholder="Optional"
              />

              <div style={styles.helperText}>
                Optional whole-number duration for the completed work.
              </div>
            </div>
          </div>

          {/* Images Section */}
          <div style={styles.imagesGrid}>

            {/* Before Images */}
            <div style={styles.formGroup}>
              <label style={styles.label}>
                Before Images (Optional)
              </label>

              <div style={styles.imagePreviewList}>
                {beforeImages.map((img, idx) => (
                  <div
                    key={idx}
                    style={styles.imagePreviewRow}
                  >
                    {img.startsWith("data:") ||
                    img.startsWith("http") ? (
                      <img
                        src={img}
                        alt={`Before ${idx + 1}`}
                        style={styles.thumbnail}
                      />
                    ) : (
                      <ImageIcon
                        size={14}
                        color="#64748b"
                      />
                    )}

                    <span style={styles.imageLabel}>
                      Before #{idx + 1}
                    </span>

                    <button
                      type="button"
                      style={styles.iconBtn}
                      onClick={() =>
                        handleRemoveBeforeImage(idx)
                      }
                    >
                      <Trash2
                        size={14}
                        color="#ef4444"
                      />
                    </button>
                  </div>
                ))}
              </div>

              <label style={styles.fileUploadBtn}>
                <Upload size={13} />

                {beforeImages.length > 0
                  ? "+ Add Another Image"
                  : "Choose File"}

                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) =>
                    handleFileUpload(e, "before")
                  }
                  style={{ display: "none" }}
                />
              </label>
            </div>

            {/* After Images */}
            <div style={styles.formGroup}>
              <label style={styles.label}>
                After Images (Min 1){" "}
                <span style={styles.req}>*</span>
              </label>

              <div style={styles.imagePreviewList}>
                {afterImages.map((img, idx) => (
                  <div
                    key={idx}
                    style={styles.imagePreviewRow}
                  >
                    {img.startsWith("data:") ||
                    img.startsWith("http") ? (
                      <img
                        src={img}
                        alt={`After ${idx + 1}`}
                        style={styles.thumbnail}
                      />
                    ) : (
                      <ImageIcon
                        size={14}
                        color="#166534"
                      />
                    )}

                    <span style={styles.imageLabel}>
                      After #{idx + 1}
                    </span>

                    <button
                      type="button"
                      style={styles.iconBtn}
                      onClick={() =>
                        handleRemoveAfterImage(idx)
                      }
                    >
                      <Trash2
                        size={14}
                        color="#ef4444"
                      />
                    </button>
                  </div>
                ))}
              </div>

              <label style={styles.fileUploadBtn}>
                <Upload size={13} />

                {afterImages.length > 0
                  ? "+ Add Another Image"
                  : "Choose File"}

                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) =>
                    handleFileUpload(e, "after")
                  }
                  style={{ display: "none" }}
                />
              </label>
            </div>
          </div>

          {!paymentFlow && (
            <div style={styles.costGrid}>
              <div style={styles.formGroup}><label style={styles.label}>Service Charge (₹)</label><input type="number" min="0" step="0.01" required style={styles.input} value={serviceCharge} onChange={(e) => setServiceCharge(e.target.value)} /></div>
              <div style={styles.formGroup}><label style={styles.label}>Material Cost (₹)</label><input type="number" min="0" step="0.01" required style={styles.input} value={materialCost} onChange={(e) => setMaterialCost(e.target.value)} /></div>
              <div style={styles.formGroup}><label style={styles.label}>Subtotal (₹)</label><input type="text" style={{ ...styles.input, backgroundColor: "#f1f5f9", fontWeight: 700, color: "#166534" }} value={`₹ ${subtotal.toFixed(2)}`} readOnly /></div>
              <div style={styles.formGroup}><label style={styles.label}>GST (5%)</label><input type="text" style={{ ...styles.input, backgroundColor: "#f1f5f9", fontWeight: 700, color: "#166534" }} value={`₹ ${gstAmount.toFixed(2)}`} readOnly /></div>
              <div style={styles.formGroup}><label style={styles.label}>Total (₹)</label><input type="text" style={{ ...styles.input, backgroundColor: "#dcfce7", fontWeight: 700, color: "#166534" }} value={`₹ ${totalAmount.toFixed(2)}`} readOnly /></div>
            </div>
          )}

          </>
          ) : step === "payment" ? (
          <>
            <div style={{ ...styles.paymentIntro, marginBottom: 2 }}>
              Review the service charges and record how the customer paid.
            </div>
            <div style={styles.costGrid}>
              <div style={styles.formGroup}>
                <label style={styles.label}>Service Charge (₹)</label>
                <input type="number" step="0.01" min="0" required style={styles.input} value={serviceCharge} onChange={(e) => setServiceCharge(e.target.value)} />
              </div>
              <div style={styles.formGroup}>
                <label style={styles.label}>Material Cost (₹)</label>
                <input type="number" step="0.01" min="0" required style={styles.input} value={materialCost} onChange={(e) => setMaterialCost(e.target.value)} />
              </div>
              <div style={styles.formGroup}>
                <label style={styles.label}>Subtotal (₹)</label>
                <input type="text" style={{ ...styles.input, backgroundColor: "#f1f5f9", fontWeight: 700, color: "#166534" }} value={`₹ ${subtotal.toFixed(2)}`} readOnly />
              </div>
              <div style={styles.formGroup}>
                <label style={styles.label}>GST (5%)</label>
                <input type="text" style={{ ...styles.input, backgroundColor: "#f1f5f9", fontWeight: 700, color: "#166534" }} value={`₹ ${gstAmount.toFixed(2)}`} readOnly />
              </div>
              <div style={styles.formGroup}>
                <label style={styles.label}>Total (₹)</label>
                <input type="text" style={{ ...styles.input, backgroundColor: "#dcfce7", fontWeight: 700, color: "#166534" }} value={`₹ ${totalAmount.toFixed(2)}`} readOnly />
              </div>
            </div>

            <fieldset style={styles.paymentFieldset}>
              <legend style={styles.label}>Payment Method</legend>
              <div style={styles.paymentMethods}>
                {(["CASH", "UPI", "BOTH"] as const).map((method) => (
                  <label key={method} style={{ ...styles.paymentMethod, ...(paymentMethod === method ? styles.paymentMethodSelected : {}) }}>
                    <input type="radio" name="payment-method" value={method} checked={paymentMethod === method} onChange={() => setPaymentMethod(method)} />
                    {method === "BOTH" ? "Cash + UPI" : method}
                  </label>
                ))}
              </div>
            </fieldset>

            {paymentMethod !== "CASH" && (
              <div>
                <div style={styles.label}>Choose UPI app</div>
                <div style={styles.paymentMethods}>
                  {([
                    { id: "GOOGLE_PAY", title: "Google Pay", mark: "G", color: "#4285F4" },
                    { id: "PHONEPE", title: "PhonePe", mark: "पे", color: "#5F259F" },
                  ] as const).map((provider) => (
                    <label key={provider.id} style={{ ...styles.paymentMethod, ...(paymentProvider === provider.id ? styles.paymentMethodSelected : {}) }}>
                      <input type="radio" name="upi-provider" value={provider.id} checked={paymentProvider === provider.id} onChange={() => setPaymentProvider(provider.id)} />
                      <span style={{ ...styles.providerMark, background: provider.color }}>{provider.mark}</span>
                      {provider.title}
                    </label>
                  ))}
                </div>
                <div style={styles.demoNotice} role="note">Payment preview only. No UPI app will open and no payment will be processed.</div>
              </div>
            )}

            {paymentMethod === "BOTH" ? (
              <div style={styles.costGrid}>
                <div style={styles.formGroup}>
                  <label style={styles.label}>Cash Amount (₹)</label>
                  <input type="number" min="0" step="0.01" style={styles.input} value={cashAmount} onChange={(e) => setCashAmount(e.target.value)} placeholder="Enter cash amount" required />
                </div>
                <div style={styles.formGroup}>
                  <label style={styles.label}>UPI Amount (₹)</label>
                  <input type="number" min="0" step="0.01" style={styles.input} value={upiAmount} onChange={(e) => setUpiAmount(e.target.value)} placeholder="Enter UPI amount" required />
                </div>
                <div style={styles.paymentTotalHint}>Cash + UPI must equal ₹ {totalAmount.toFixed(2)}</div>
              </div>
            ) : (
              <div style={styles.paymentTotalHint}>Amount received by {paymentMethod} : ₹ {totalAmount.toFixed(2)}</div>
            )}
          </>
          ) : (
            <div style={styles.demoCheckout}>
              <div style={styles.demoBadge}>PAYMENT PREVIEW · NO PAYMENT PROCESSED</div>
              <span style={{ ...styles.demoProviderMark, background: paymentProvider === "GOOGLE_PAY" ? "#4285F4" : "#5F259F" }}>
                {paymentProvider === "GOOGLE_PAY" ? "G" : "पे"}
              </span>
              <h2 style={styles.demoTitle}>Pay with {paymentProvider === "GOOGLE_PAY" ? "Google Pay" : "PhonePe"}</h2>
              <p style={styles.demoSubtitle}>Preview the payment confirmation flow. No payment is being requested from your bank account.</p>
              <div style={styles.demoReceipt}>
                <div><span>Pay to</span><strong>FieldOps Services</strong></div>
                <div><span>Merchant UPI ID</span><strong>merchant@upi</strong></div>
                <div><span>Job</span><strong>#{jobId}</strong></div>
                <div style={styles.demoAmountRow}><span>Amount</span><strong>₹ {pendingPaymentData?.total_amount?.toFixed(2) ?? totalAmount.toFixed(2)}</strong></div>
              </div>
              {demoPaymentApproved ? (
                <div style={styles.demoApproved} role="status">✓ Payment preview complete. No payment was processed.</div>
              ) : (
                <div style={styles.demoWaiting} role="status">Waiting for {paymentProvider === "GOOGLE_PAY" ? "Google Pay" : "PhonePe"} approval…</div>
              )}
              {!demoPaymentApproved && <button type="button" onClick={() => setDemoPaymentApproved(true)} style={styles.demoPayButton}>Preview payment confirmation</button>}
            </div>
          )}

          {/* Footer Actions */}
          <div style={styles.footer}>
            <button
              type="button"
              style={styles.cancelBtn}
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>

            {step === "payment" && <button
              type="button"
              style={styles.cancelBtn}
              onClick={() => { setError(null); setStep("service"); }}
              disabled={isSubmitting}
            >
              Back
            </button>}

            {step === "upi_demo" && <button
              type="button"
              style={styles.cancelBtn}
              onClick={() => { setError(null); setStep("payment"); }}
            >
              Back to Payment
            </button>}

            {step === "upi_demo" ? (
              <button type="button" style={styles.submitBtn} disabled={!demoPaymentApproved} onClick={continueFromDemoPayment}>
                Continue to Customer Signature
              </button>
            ) : (
              <button
                type="submit"
                data-testid="submit-job-closure"
                style={styles.submitBtn}
                disabled={isSubmitting || uploadingType !== null}
              >
                {isSubmitting ? "Submitting..." : step === "service" ? paymentFlow ? "Payment" : "Submit Job Closure" : "Review Payment"}
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: "fixed",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: "rgba(15, 23, 42, 0.6)",
    backdropFilter: "blur(4px)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1100,
    padding: "16px",
  },

  reportGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
    gap: "16px",
  },

  helperText: {
    marginTop: "6px",
    fontSize: "11px",
    lineHeight: 1.4,
    color: "#64748b",
  },

  modal: {
    backgroundColor: "#ffffff",
    borderRadius: "16px",
    width: "90%",
    maxWidth: "900px",
    minHeight: "auto",
    maxHeight: "calc(100vh - 32px)",
    display: "flex",
    flexDirection: "column",
    boxShadow:
      "0 20px 30px -5px rgba(0,0,0,0.15)",
    border: "1px solid #e2e8f0",
    overflow: "hidden",
  },

  header: {
    padding: "12px 20px",
    borderBottom: "1px solid #e2e8f0",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: "#f8fafc",
  },

  headerTitleWrap: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },

  headerTitle: {
    fontSize: "16px",
    fontWeight: 700,
    color: "#0f172a",
    margin: 0,
  },

  closeBtn: {
    background: "none",
    border: "none",
    color: "#64748b",
    cursor: "pointer",
    padding: "4px",
    borderRadius: "4px",
  },

  body: {
    padding: "26px 34px 24px",
    display: "flex",
    flexDirection: "column",
    gap: "20px",
    overflowY: "auto",
    minHeight: 0,
  },

  errorAlert: {
    padding: "8px 12px",
    backgroundColor: "#fef2f2",
    color: "#991b1b",
    borderRadius: "6px",
    fontSize: "13px",
    border: "1px solid #fecaca",
  },

  formGroup: {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
  },

  imagesGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: "12px",
  },

  label: {
    fontSize: "13px",
    fontWeight: 600,
    color: "#334155",
  },

  req: {
    color: "#dc2626",
  },

  textarea: {
    padding: "8px 10px",
    borderRadius: "6px",
    border: "1px solid #cbd5e1",
    fontSize: "13px",
    outline: "none",
    fontFamily: "inherit",
    resize: "none",
  },

  input: {
    width: "100%",
    padding: "7px 10px",
    borderRadius: "6px",
    border: "1px solid #cbd5e1",
    fontSize: "13px",
    outline: "none",
    boxSizing: "border-box",
  },

  fileUploadBtn: {
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    background: "#f1f5f9",
    border: "1px dashed #cbd5e1",
    color: "#334155",
    padding: "6px 12px",
    borderRadius: "6px",
    fontSize: "12px",
    fontWeight: 600,
    cursor: "pointer",
    alignSelf: "flex-start",
    marginTop: "2px",
  },

  imagePreviewList: {
    display: "flex",
    flexDirection: "column",
    gap: "4px",
    maxHeight: "80px",
    overflowY: "auto",
  },

  imagePreviewRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "3px 6px",
    background: "#f8fafc",
    borderRadius: "6px",
    border: "1px solid #e2e8f0",
  },

  thumbnail: {
    width: "24px",
    height: "24px",
    objectFit: "cover",
    borderRadius: "4px",
    border: "1px solid #cbd5e1",
  },

  imageLabel: {
    fontSize: "12px",
    color: "#334155",
    fontWeight: 500,
    flex: 1,
    marginLeft: "6px",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },

  iconBtn: {
    background: "none",
    border: "none",
    cursor: "pointer",
    padding: "2px",
  },

  costGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, 1fr)",
    gap: "12px",
  },

  paymentIntro: {
    padding: "12px 14px",
    borderRadius: 10,
    background: "#eff6ff",
    border: "1px solid #bfdbfe",
    color: "#1e3a8a",
    fontSize: 13,
  },

  paymentFieldset: {
    border: 0,
    padding: 0,
    margin: 0,
  },

  paymentMethods: {
    display: "grid",
    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
    gap: 10,
    marginTop: 8,
  },

  paymentMethod: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    padding: "12px 14px",
    borderRadius: 10,
    border: "1px solid #cbd5e1",
    background: "#fff",
    color: "#334155",
    fontSize: 13,
    fontWeight: 600,
    cursor: "pointer",
  },

  paymentMethodSelected: {
    border: "1px solid #16a34a",
    background: "#f0fdf4",
    color: "#166534",
    boxShadow: "0 0 0 2px rgba(22, 163, 74, .10)",
  },

  providerMark: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    width: 24,
    height: 24,
    borderRadius: 8,
    color: "white",
    fontWeight: 800,
  },

  demoNotice: {
    marginTop: 10,
    padding: "10px 12px",
    borderRadius: 9,
    background: "#eff6ff",
    border: "1px solid #bfdbfe",
    color: "#1e40af",
    fontSize: 12,
    lineHeight: 1.5,
  },

  demoCheckout: { display: "flex", flexDirection: "column", alignItems: "center", gap: 12, padding: "12px 0" },
  demoBadge: { padding: "6px 10px", borderRadius: 999, background: "#fff7ed", color: "#9a3412", fontSize: 11, fontWeight: 800, letterSpacing: ".04em" },
  demoProviderMark: { display: "inline-flex", alignItems: "center", justifyContent: "center", width: 58, height: 58, borderRadius: 18, color: "white", fontSize: 28, fontWeight: 800, boxShadow: "0 8px 18px rgba(15,23,42,.18)" },
  demoTitle: { margin: 0, color: "#0f172a", fontSize: 22 },
  demoSubtitle: { margin: 0, maxWidth: 480, textAlign: "center", color: "#64748b", fontSize: 13, lineHeight: 1.5 },
  demoReceipt: { width: "100%", maxWidth: 480, padding: 16, display: "grid", gap: 12, border: "1px solid #e2e8f0", borderRadius: 14, background: "#f8fafc" },
  demoAmountRow: { borderTop: "1px solid #e2e8f0", paddingTop: 12, fontSize: 17 },
  demoApproved: { width: "100%", maxWidth: 480, padding: 12, borderRadius: 10, background: "#dcfce7", color: "#166534", fontWeight: 700, textAlign: "center" },
  demoWaiting: { width: "100%", maxWidth: 480, padding: 12, borderRadius: 10, background: "#eff6ff", color: "#1d4ed8", textAlign: "center" },
  demoPayButton: { padding: "11px 18px", border: 0, borderRadius: 9, background: "#166534", color: "white", fontWeight: 700, cursor: "pointer" },

  paymentTotalHint: {
    gridColumn: "1 / -1",
    padding: "12px 14px",
    borderRadius: 10,
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    color: "#475569",
    fontSize: 13,
    fontWeight: 600,
  },

  footer: {
    display: "flex",
    justifyContent: "flex-end",
    gap: "10px",
    marginTop: "4px",
    paddingTop: "12px",
    borderTop: "1px solid #e2e8f0",
  },

  cancelBtn: {
    padding: "8px 16px",
    borderRadius: "6px",
    border: "1px solid #cbd5e1",
    backgroundColor: "#ffffff",
    color: "#475569",
    fontWeight: 600,
    fontSize: "13px",
    cursor: "pointer",
  },

  submitBtn: {
    padding: "8px 18px",
    borderRadius: "6px",
    border: "none",
    backgroundColor: "#166534",
    color: "#ffffff",
    fontWeight: 600,
    fontSize: "13px",
    cursor: "pointer",
  },
};
