import React, { useState } from "react";
import {
  X,
  Trash2,
  CheckCircle2,
  IndianRupee,
  Image as ImageIcon,
  Upload,
} from "lucide-react";
import { closeJob, JobClosureData } from "../../services/planningService";

interface JobClosureModalProps {
  jobId: number | string;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const compressImage = (
  file: File,
  maxWidth = 800,
  quality = 0.7
): Promise<string> => {
  return new Promise((resolve) => {
    const reader = new FileReader();

    reader.onload = (event) => {
      const img = new Image();

      img.onload = () => {
        let width = img.width;
        let height = img.height;

        if (width > maxWidth) {
          height = Math.round((height * maxWidth) / width);
          width = maxWidth;
        }

        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;

        const ctx = canvas.getContext("2d");

        if (ctx) {
          ctx.drawImage(img, 0, 0, width, height);
          resolve(canvas.toDataURL("image/jpeg", quality));
        } else {
          resolve((event.target?.result as string) || "");
        }
      };

      img.onerror = () => resolve("");
      img.src = (event.target?.result as string) || "";
    };

    reader.onerror = () => resolve("");
    reader.readAsDataURL(file);
  });
};

export const JobClosureModal: React.FC<JobClosureModalProps> = ({
  jobId,
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [workSummary, setWorkSummary] = useState("");
  const [beforeImages, setBeforeImages] = useState<string[]>([]);
  const [afterImages, setAfterImages] = useState<string[]>([]);

  const [serviceCharge, setServiceCharge] = useState<string>("");
  const [materialCost, setMaterialCost] = useState<string>("");

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

    for (const file of Array.from(files)) {
      try {
        const compressedBase64 = await compressImage(file);

        if (compressedBase64) {
          if (type === "before") {
            setBeforeImages((prev) => [...prev, compressedBase64]);
          } else {
            setAfterImages((prev) => [...prev, compressedBase64]);
          }
        }
      } catch (err) {
        console.error("Failed to compress image:", err);
      }
    }

    e.target.value = "";
  };

  const handleRemoveBeforeImage = (index: number) => {
    setBeforeImages((prev) => prev.filter((_, i) => i !== index));
  };

  const handleRemoveAfterImage = (index: number) => {
    setAfterImages((prev) => prev.filter((_, i) => i !== index));
  };

  // -----------------------------
  // SUBMIT
  // -----------------------------

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!workSummary.trim()) {
      setError("Work summary is required.");
      return;
    }


    if (serviceCharge.trim() === "" || materialCost.trim() === "") {
      setError("Service Charge and Material Cost are required.");
      return;
    }


    const filteredAfterImages = afterImages
      .map((img) => img.trim())
      .filter(Boolean);

    if (filteredAfterImages.length === 0) {
      setError("At least one after image is required.");
      return;
    }

    const filteredBeforeImages = beforeImages
      .map((img) => img.trim())
      .filter(Boolean);

    setIsSubmitting(true);

    try {
      const payload: JobClosureData = {
        work_summary: workSummary.trim(),
        before_images: filteredBeforeImages,
        after_images: filteredAfterImages,

        // Service Charge is stored as labour/service cost for billing reports.
        labour_cost: Math.max(
          0,
          Number(serviceCharge) || 0
        ),

        material_cost: Math.max(
          0,
          Number(materialCost) || 0
        ),
      };

      await closeJob(jobId, payload);

      onSuccess();
      onClose();
    } catch (err: any) {
      const errMsg =
        err?.response?.data?.detail ||
        err?.message ||
        "Failed to complete job.";

      setError(
        typeof errMsg === "string"
          ? errMsg
          : JSON.stringify(errMsg)
      );
    } finally {
      setIsSubmitting(false);
    }
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
              Complete Job #{jobId}
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

          {/* Work Summary */}
          <div style={styles.formGroup}>
            <label style={styles.label}>
              Work Summary{" "}
              <span style={styles.req}>*</span>
            </label>

            <textarea
              style={styles.textarea}
              rows={3}
              value={workSummary}
              onChange={(e) =>
                setWorkSummary(e.target.value)
              }
              placeholder="Describe work completed, tests run, and final status..."
              required
            />
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

          {/* Financial Breakdown */}
          <div style={styles.costGrid}>

            {/* Service Charge */}
            <div style={styles.formGroup}>
              <label style={styles.label}>
                Service Charge (₹)
              </label>

              <input
                type="number"
                step="0.01"
                min="0"
                required
                style={styles.input}
                value={serviceCharge}
                onChange={(e) => {
                  const value =
                    e.target.value.replace(
                      /^0+(?=\d)/,
                      ""
                    );

                  setServiceCharge(value);
                }}
              />
            </div>

            {/* Material Cost */}
            <div style={styles.formGroup}>
              <label style={styles.label}>
                Material Cost (₹)
              </label>

              <input
                type="number"
                step="0.01"
                min="0"
                required
                style={styles.input}
                value={materialCost}
                onChange={(e) => {
                  const value =
                    e.target.value.replace(
                      /^0+(?=\d)/,
                      ""
                    );

                  setMaterialCost(value);
                }}
              />
            </div>

            {/* Subtotal */}
            <div style={styles.formGroup}>
              <label style={styles.label}>
                Subtotal (₹)
              </label>

              <input
                type="text"
                style={{
                  ...styles.input,
                  backgroundColor: "#f1f5f9",
                  fontWeight: 700,
                  color: "#166534",
                }}
                value={`₹ ${subtotal.toFixed(2)}`}
                readOnly
                disabled
              />
            </div>

            {/* GST */}
            <div style={styles.formGroup}>
              <label style={styles.label}>
                GST (5%)
              </label>

              <input
                type="text"
                style={{
                  ...styles.input,
                  backgroundColor: "#f1f5f9",
                  fontWeight: 700,
                  color: "#166534",
                }}
                value={`₹ ${gstAmount.toFixed(2)}`}
                readOnly
                disabled
              />
            </div>

            {/* Total */}
            <div style={styles.formGroup}>
              <label style={styles.label}>
                Total (₹)
              </label>

              <input
                type="text"
                style={{
                  ...styles.input,
                  backgroundColor: "#dcfce7",
                  fontWeight: 700,
                  color: "#166534",
                }}
                value={`₹ ${totalAmount.toFixed(2)}`}
                readOnly
                disabled
              />
            </div>
          </div>

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

            <button
              type="submit"
              style={styles.submitBtn}
              disabled={isSubmitting}
            >
              {isSubmitting
                ? "Submitting..."
                : "Submit Job Closure"}
            </button>
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

  modal: {
    backgroundColor: "#ffffff",
    borderRadius: "16px",
    width: "90%",
    maxWidth: "900px",
    minHeight: "auto",
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