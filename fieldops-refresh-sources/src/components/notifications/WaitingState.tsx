import React from "react";
import { CheckCircle, XCircle, AlertTriangle, Loader2, RotateCcw, X } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import type { WaitingStateProps } from "../../types/notifications";

const styles = {
  overlay: {
    position: "absolute",
    top: 0,
    left: 0,
    width: "100%",
    height: "100%",
    backgroundColor: "rgba(255, 255, 255, 0.95)",
    backdropFilter: "blur(4px)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 50,
    borderRadius: "12px",
    fontFamily: "'Inter', sans-serif",
  } as React.CSSProperties,

  content: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    textAlign: "center",
    padding: "24px",
  } as React.CSSProperties,

  inner: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
  } as React.CSSProperties,

  text: {
    fontSize: "15px",
    fontWeight: 600,
    color: "#1e293b",
    margin: "12px 0 0 0",
    lineHeight: 1.4,
  } as React.CSSProperties,

  successIcon: {
    color: "#10b981",
  } as React.CSSProperties,

  errorIcon: {
    color: "#ef4444",
  } as React.CSSProperties,

  timeoutIcon: {
    color: "#f59e0b",
  } as React.CSSProperties,

  actions: {
    display: "flex",
    gap: "10px",
    marginTop: "16px",
  } as React.CSSProperties,

  retryBtn: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    height: "36px",
    padding: "0 14px",
    fontSize: "13px",
    fontWeight: 600,
    color: "#ffffff",
    backgroundColor: "#3b82f6",
    border: "none",
    borderRadius: "6px",
    cursor: "pointer",
    transition: "background-color 0.2s",
  } as React.CSSProperties,

  cancelBtn: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    height: "36px",
    padding: "0 14px",
    fontSize: "13px",
    fontWeight: 600,
    color: "#64748b",
    backgroundColor: "#f1f5f9",
    border: "none",
    borderRadius: "6px",
    cursor: "pointer",
    transition: "all 0.2s",
  } as React.CSSProperties,
  closeBtn: {
    position: "absolute",
    top: "12px",
    right: "12px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: "28px",
    height: "28px",
    borderRadius: "50%",
    border: "none",
    background: "#f1f5f9",
    cursor: "pointer",
    color: "#64748b",
    transition: "background-color 0.2s, color 0.2s",
    padding: 0,
    zIndex: 60,
  } as React.CSSProperties,
};

const localCss = `
  .waiting-spinner {
    animation: local-spin 1s linear infinite;
    color: #3b82f6;
  }
  .retry-btn-style:hover { background-color: #2563eb !important; }
  .cancel-btn-style:hover { background-color: #e2e8f0 !important; color: #1e293b !important; }
  @keyframes local-spin { to { transform: rotate(360deg); } }
`;

export const WaitingState: React.FC<WaitingStateProps> = ({
  state,
  message = "",
  onRetry,
  onCancel,
  onClose,
}) => {
  if (state === "IDLE") return null;

  return (
    <AnimatePresence>
      <motion.div
        style={styles.overlay}
        data-testid="waiting-state"
        data-state={state}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        aria-live="assertive"
        role="status"
      >
        <style>{localCss}</style>
        {state === "SUCCESS" && onClose && (
          <button
            type="button"
            onClick={onClose}
            className="cancel-btn-style"
            style={styles.closeBtn}
            aria-label="Close"
            title="Close"
          >
            <X size={16} />
          </button>
        )}
        <div style={styles.content}>
          {/* ─── LOADING ─────────────────────────────── */}
          {state === "LOADING" && (
            <motion.div
              style={styles.inner}
              initial={{ scale: 0.9 }}
              animate={{ scale: 1 }}
              data-testid="waiting-loading"
            >
              <Loader2 size={36} className="waiting-spinner" aria-hidden="true" />
              <p style={styles.text}>{message}</p>
            </motion.div>
          )}

          {/* ─── SUCCESS ─────────────────────────────── */}
          {state === "SUCCESS" && (
            <motion.div
              style={styles.inner}
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              data-testid="waiting-success"
            >
              <CheckCircle size={40} style={styles.successIcon} aria-hidden="true" />
              <p style={styles.text}>{message}</p>
            </motion.div>
          )}

          {/* ─── ERROR ───────────────────────────────── */}
          {state === "ERROR" && (
            <motion.div
              style={styles.inner}
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              data-testid="waiting-error"
            >
              <XCircle size={40} style={styles.errorIcon} aria-hidden="true" />
              <p style={styles.text}>{message}</p>
              <div style={styles.actions}>
                {onRetry && (
                  <button
                    type="button"
                    className="retry-btn-style"
                    style={styles.retryBtn}
                    onClick={onRetry}
                    data-testid="waiting-retry-btn"
                  >
                    <RotateCcw size={14} aria-hidden="true" />
                    Retry
                  </button>
                )}
                {onCancel && (
                  <button
                    type="button"
                    className="cancel-btn-style"
                    style={styles.cancelBtn}
                    onClick={onCancel}
                    data-testid="waiting-cancel-btn"
                  >
                    <X size={14} aria-hidden="true" />
                    Cancel
                  </button>
                )}
              </div>
            </motion.div>
          )}

          {/* ─── TIMEOUT ─────────────────────────────── */}
          {state === "TIMEOUT" && (
            <motion.div
              style={styles.inner}
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              data-testid="waiting-timeout"
            >
              <AlertTriangle size={40} style={styles.timeoutIcon} aria-hidden="true" />
              <p style={styles.text}>{message}</p>
              <div style={styles.actions}>
                {onRetry && (
                  <button
                    type="button"
                    className="retry-btn-style"
                    style={styles.retryBtn}
                    onClick={onRetry}
                    data-testid="waiting-timeout-retry-btn"
                  >
                    <RotateCcw size={14} aria-hidden="true" />
                    Retry
                  </button>
                )}
                {onCancel && (
                  <button
                    type="button"
                    className="cancel-btn-style"
                    style={styles.cancelBtn}
                    onClick={onCancel}
                    data-testid="waiting-timeout-cancel-btn"
                  >
                    <X size={14} aria-hidden="true" />
                    Cancel
                  </button>
                )}
              </div>
            </motion.div>
          )}
        </div>
      </motion.div>
    </AnimatePresence>
  );
};

export default WaitingState;
