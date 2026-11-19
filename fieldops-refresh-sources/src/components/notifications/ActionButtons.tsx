/**
 * ActionButtons.tsx
 * Accept / Reject / Reassign button group with confirmation modals,
 * form validation, loading states, and full keyboard accessibility.
 */
import React, { useState, useEffect } from "react";
import { CheckCircle, X, Shuffle, Loader2, Search, User } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import StatusBadge from "../ui/StatusBadge";
import api from "../../services/api";
import type { ActionButtonsProps } from "../../types/notifications";

const MIN_REASON_LENGTH = 10;

interface ColleagueOption {
  technician_id: number;
  technician_name: string;
  technician_status: string;
  technician_skill: string;
}

const styles = {
  group: {
    display: "flex",
    gap: "10px",
    marginTop: "20px",
    flexWrap: "wrap",
  } as React.CSSProperties,

  btn: {
    flex: 1,
    minWidth: "110px",
    height: "44px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "8px",
    fontSize: "14px",
    fontWeight: 700,
    borderRadius: "8px",
    cursor: "pointer",
    transition: "all 0.2s ease",
    border: "none",
    touchAction: "manipulation",
    outline: "none",
  } as React.CSSProperties,

  acceptBtn: {
    background: "linear-gradient(135deg, #10b981 0%, #059669 100%)",
    color: "#ffffff",
    boxShadow: "0 2px 8px rgba(16, 185, 129, 0.25)",
  } as React.CSSProperties,

  rejectBtn: {
    background: "linear-gradient(135deg, #ef4444 0%, #dc2626 100%)",
    color: "#ffffff",
    boxShadow: "0 2px 8px rgba(239, 68, 68, 0.25)",
  } as React.CSSProperties,

  reassignBtn: {
    background: "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)",
    color: "#ffffff",
    boxShadow: "0 2px 8px rgba(59, 130, 246, 0.25)",
  } as React.CSSProperties,

  backdrop: {
    position: "fixed",
    top: 0,
    left: 0,
    width: "100%",
    height: "100%",
    backgroundColor: "rgba(15, 23, 42, 0.4)",
    backdropFilter: "blur(4px)",
    zIndex: 1001,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "20px",
  } as React.CSSProperties,

  rejectModal: {
    backgroundColor: "#ffffff",
    borderRadius: "12px",
    boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
    width: "100%",
    maxWidth: "440px",
    padding: "24px",
    boxSizing: "border-box",
    textAlign: "left",
  } as React.CSSProperties,

  reassignModal: {
    backgroundColor: "#ffffff",
    borderRadius: "12px",
    boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
    width: "100%",
    maxWidth: "480px",
    padding: "24px",
    boxSizing: "border-box",
    textAlign: "left",
  } as React.CSSProperties,

  textarea: {
    width: "100%",
    height: "90px",
    padding: "10px",
    border: "1px solid #cbd5e1",
    borderRadius: "6px",
    fontFamily: "inherit",
    fontSize: "14px",
    marginBottom: "16px",
    resize: "none",
    boxSizing: "border-box",
  } as React.CSSProperties,

  charCount: {
    fontSize: "11px",
    color: "#94a3b8",
    textAlign: "right",
    marginTop: "-10px",
    marginBottom: "12px",
    fontWeight: 500,
  } as React.CSSProperties,

  modalActions: {
    display: "flex",
    justifyContent: "flex-end",
    gap: "12px",
  } as React.CSSProperties,

  cancelBtn: {
    height: "38px",
    padding: "0 16px",
    fontSize: "14px",
    fontWeight: 600,
    borderRadius: "6px",
    cursor: "pointer",
    border: "none",
    backgroundColor: "#f1f5f9",
    color: "#475569",
    transition: "background-color 0.2s",
  } as React.CSSProperties,

  submitBtn: {
    height: "38px",
    padding: "0 16px",
    fontSize: "14px",
    fontWeight: 600,
    borderRadius: "6px",
    cursor: "pointer",
    border: "none",
    backgroundColor: "#ef4444",
    color: "#ffffff",
    transition: "background-color 0.2s",
  } as React.CSSProperties,

  searchContainer: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    padding: "8px 12px",
    border: "1px solid #cbd5e1",
    borderRadius: "8px",
    backgroundColor: "#f8fafc",
    marginBottom: "12px",
    transition: "border-color 0.2s",
  } as React.CSSProperties,

  searchInput: {
    flex: 1,
    border: "none",
    background: "transparent",
    fontSize: "14px",
    fontFamily: "inherit",
    outline: "none",
    color: "#1e293b",
  } as React.CSSProperties,

  techList: {
    maxHeight: "220px",
    overflowY: "auto",
    border: "1px solid #e2e8f0",
    borderRadius: "8px",
    backgroundColor: "#ffffff",
  } as React.CSSProperties,

  techItem: {
    display: "flex",
    alignItems: "center",
    gap: "10px",
    padding: "10px 12px",
    border: "none",
    borderBottom: "1px solid #f1f5f9",
    backgroundColor: "transparent",
    cursor: "pointer",
    width: "100%",
    textAlign: "left",
    transition: "background-color 0.15s",
    fontFamily: "inherit",
  } as React.CSSProperties,

  techAvatar: {
    width: "32px",
    height: "32px",
    borderRadius: "8px",
    background: "linear-gradient(135deg, #e0e7ff, #c7d2fe)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#4f46e5",
    flexShrink: 0,
  } as React.CSSProperties,

  techInfo: {
    flex: 1,
    minWidth: 0,
    display: "flex",
    flexDirection: "column",
  } as React.CSSProperties,

  techName: {
    fontSize: "13px",
    fontWeight: 600,
    color: "#1e293b",
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
  } as React.CSSProperties,

  techSkill: {
    fontSize: "11px",
    color: "#94a3b8",
  } as React.CSSProperties,

  techConfirmBtn: {
    height: "38px",
    padding: "0 16px",
    fontSize: "14px",
    fontWeight: 600,
    borderRadius: "6px",
    cursor: "pointer",
    border: "none",
    backgroundColor: "#3b82f6",
    color: "#ffffff",
    display: "flex",
    alignItems: "center",
    gap: "6px",
    transition: "background-color 0.2s",
  } as React.CSSProperties,

  loadingOrEmpty: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: "8px",
    padding: "24px",
    color: "#94a3b8",
    fontSize: "13px",
  } as React.CSSProperties,
};

const localCss = `
  @keyframes spinAnim {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
  .action-btn-spinner {
    animation: spinAnim 0.8s linear infinite;
  }
  .action-btn-accept-hover:hover:not(:disabled) {
    background: linear-gradient(135deg, #059669 0%, #047857 100%) !important;
    box-shadow: 0 4px 12px rgba(16, 185, 129, 0.35) !important;
    transform: translateY(-1px);
  }
  .action-btn-reject-hover:hover:not(:disabled) {
    background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%) !important;
    box-shadow: 0 4px 12px rgba(239, 68, 68, 0.35) !important;
    transform: translateY(-1px);
  }
  .action-btn-reassign-hover:hover:not(:disabled) {
    background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.35) !important;
    transform: translateY(-1px);
  }
  .cancel-btn-hover:hover {
    background-color: #e2e8f0 !important;
  }
  .submit-btn-hover:hover:not(:disabled) {
    background-color: #dc2626 !important;
  }
  .tech-confirm-btn-hover:hover:not(:disabled) {
    background-color: #2563eb !important;
  }
  .tech-item-hover:hover {
    background-color: #f8fafc !important;
  }
  .reassign-tech-selected {
    background-color: #eff6ff !important;
    border-left: 3px solid #3b82f6 !important;
  }
  .reassign-search-focus:focus-within {
    border-color: #3b82f6 !important;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.15) !important;
  }
  .action-btn-focus:focus-visible {
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.4) !important;
  }
  @media (max-width: 640px) {
    .action-btn-group-mobile {
      flex-direction: column !important;
    }
    .action-btn-mobile {
      min-width: 100% !important;
    }
    .reassign-modal-mobile {
      max-width: 100% !important;
      padding: 16px !important;
    }
  }
`;

export const ActionButtons: React.FC<ActionButtonsProps> = ({
  onAccept,
  onReject,
  onReassign,
  jobId,
  disabled = false,
}) => {
  // Modal states
  const [isRejectModalOpen, setIsRejectModalOpen] = useState(false);
  const [isReassignModalOpen, setIsReassignModalOpen] = useState(false);

  // Reject modal
  const [rejectReason, setRejectReason] = useState("");
  const [rejectLoading, setRejectLoading] = useState(false);

  // Reassign modal
  const [reassignSearch, setReassignSearch] = useState("");
  const [reassignReason, setReassignReason] = useState("");
  const [selectedColleague, setSelectedColleague] = useState<number | null>(null);
  const [reassignLoading, setReassignLoading] = useState(false);
  const [colleagues, setColleagues] = useState<ColleagueOption[]>([]);
  const [colleaguesLoading, setColleaguesLoading] = useState(false);

  // Accept loading
  const [acceptLoading, setAcceptLoading] = useState(false);

  // Track if any action completed
  const [actioned, setActioned] = useState(false);

  const anyLoading = acceptLoading || rejectLoading || reassignLoading;
  const isDisabled = disabled || actioned || anyLoading;

  // Fetch colleagues for reassign modal
  useEffect(() => {
    if (!isReassignModalOpen) return;
    let cancelled = false;
    const fetchColleagues = async () => {
      setColleaguesLoading(true);
      try {
        const res = await api.get("/technicians/available");
        const data = res.data;
        if (!cancelled) {
          setColleagues(
            data.map((t: any) => ({
              technician_id: t.id || t.technician_id,
              technician_name: t.technician || t.technician_name,
              technician_status: t.status || t.technician_status || "AVAILABLE",
              technician_skill: t.skill || t.technician_skill || "",
            }))
          );
        }
      } catch {
        if (!cancelled) setColleagues([]);
      } finally {
        if (!cancelled) setColleaguesLoading(false);
      }
    };
    fetchColleagues();
    return () => { cancelled = true; };
  }, [isReassignModalOpen]);

  const filteredColleagues = colleagues.filter((c) =>
    c.technician_name.toLowerCase().includes(reassignSearch.toLowerCase())
  );

  // ─── Handlers ───────────────────────────────────────────

  const handleAccept = async () => {
    setAcceptLoading(true);
    try {
      await onAccept(jobId);
      setActioned(true);
    } finally {
      setAcceptLoading(false);
    }
  };

  const handleRejectConfirm = async () => {
    setRejectLoading(true);
    try {
      await onReject(jobId, rejectReason);
      setActioned(true);
      setIsRejectModalOpen(false);
      setRejectReason("");
    } finally {
      setRejectLoading(false);
    }
  };

  const handleReassignConfirm = async () => {
    setReassignLoading(true);
    try {
      await onReassign(jobId, selectedColleague ?? undefined, reassignReason);
      setActioned(true);
      setIsReassignModalOpen(false);
      setSelectedColleague(null);
      setReassignReason("");
      setReassignSearch("");
    } finally {
      setReassignLoading(false);
    }
  };

  const reasonValid = rejectReason.trim().length >= MIN_REASON_LENGTH;

  return (
    <>
      <style>{localCss}</style>

      {/* Button Group */}
      <div 
        className="action-btn-group-mobile" 
        style={styles.group} 
        data-testid="action-buttons" 
        role="group" 
        aria-label="Job response actions"
      >
        <button
          type="button"
          className="action-btn-accept-hover action-btn-focus action-btn-mobile"
          style={{ ...styles.btn, ...styles.acceptBtn }}
          onClick={handleAccept}
          disabled={isDisabled}
          aria-label="Accept this job assignment"
          data-testid="accept-btn"
        >
          {acceptLoading ? (
            <Loader2 size={16} className="action-btn-spinner" aria-hidden="true" />
          ) : (
            <CheckCircle size={16} aria-hidden="true" />
          )}
          <span>Accept Job</span>
        </button>

        <button
          type="button"
          className="action-btn-reject-hover action-btn-focus action-btn-mobile"
          style={{ ...styles.btn, ...styles.rejectBtn }}
          onClick={() => setIsRejectModalOpen(true)}
          disabled={isDisabled}
          aria-label="Reject this job assignment"
          data-testid="reject-btn"
        >
          <X size={16} aria-hidden="true" />
          <span>Reject</span>
        </button>

        <button
          type="button"
          className="action-btn-reassign-hover action-btn-focus action-btn-mobile"
          style={{ ...styles.btn, ...styles.reassignBtn }}
          onClick={() => setIsReassignModalOpen(true)}
          disabled={isDisabled}
          aria-label="Reassign this job to a colleague"
          data-testid="reassign-btn"
        >
          <Shuffle size={16} aria-hidden="true" />
          <span>Reassign</span>
        </button>
      </div>

      {/* ─── Reject Modal ─────────────────────────────────────── */}
      <AnimatePresence>
        {isRejectModalOpen && (
          <div
            style={styles.backdrop}
            data-testid="reject-modal-backdrop"
            onClick={(e) => {
              if (e.target === e.currentTarget && !rejectLoading) {
                setIsRejectModalOpen(false);
                setRejectReason("");
              }
            }}
          >
            <motion.div
              style={styles.rejectModal}
              data-testid="reject-modal"
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              role="dialog"
              aria-modal="true"
              aria-labelledby="reject-modal-title"
            >
              <h3 id="reject-modal-title" style={{ margin: "0 0 12px 0", fontSize: "16px", fontWeight: 700, color: "#0f172a" }}>Reject Assignment</h3>
              <p style={{ fontSize: "13px", color: "#64748b", margin: "0 0 12px 0" }}>
                Please provide a reason for rejecting this assignment (min. {MIN_REASON_LENGTH} characters).
              </p>
              <textarea
                className="rejection-textarea"
                style={styles.textarea}
                placeholder="Reason (e.g. Travel distance too long, lack of parts…)"
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                disabled={rejectLoading}
                aria-label="Rejection reason"
                data-testid="reject-reason-input"
              />
              <div 
                className={!reasonValid && rejectReason.length > 0 ? "char-count-error" : ""}
                style={styles.charCount}
              >
                {rejectReason.trim().length}/{MIN_REASON_LENGTH} characters
              </div>
              <div style={styles.modalActions}>
                <button
                  type="button"
                  className="cancel-btn-hover"
                  style={styles.cancelBtn}
                  onClick={() => {
                    setIsRejectModalOpen(false);
                    setRejectReason("");
                  }}
                  disabled={rejectLoading}
                  data-testid="reject-cancel-btn"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="submit-btn-hover"
                  style={styles.submitBtn}
                  onClick={handleRejectConfirm}
                  disabled={rejectLoading || !reasonValid}
                  data-testid="reject-confirm-btn"
                >
                  {rejectLoading ? (
                    <>
                      <Loader2 size={14} className="action-btn-spinner" aria-hidden="true" style={{ display: "inline", marginRight: "6px" }} />
                      Rejecting…
                    </>
                  ) : (
                    "Confirm Rejection"
                  )}
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ─── Reassign Modal ───────────────────────────────────── */}
      <AnimatePresence>
        {isReassignModalOpen && (
          <div
            style={styles.backdrop}
            data-testid="reassign-modal-backdrop"
            onClick={(e) => {
              if (e.target === e.currentTarget && !reassignLoading) {
                setIsReassignModalOpen(false);
                setSelectedColleague(null);
                setReassignSearch("");
                setReassignReason("");
              }
            }}
          >
            <motion.div
              className="reassign-modal-mobile"
              style={styles.reassignModal}
              data-testid="reassign-modal"
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              role="dialog"
              aria-modal="true"
              aria-labelledby="reassign-modal-title"
            >
              <h3 id="reassign-modal-title" style={{ margin: "0 0 8px 0", fontSize: "16px", fontWeight: 700, color: "#0f172a" }}>Reassign to Colleague</h3>
              <p style={{ fontSize: "13px", color: "#64748b", margin: "0 0 12px 0" }}>
                Search and select a colleague to reassign this job.
              </p>

              {/* Search */}
              <div className="reassign-search-focus" style={styles.searchContainer}>
                <Search size={14} aria-hidden="true" style={{ color: "#94a3b8", flexShrink: 0 }} />
                <input
                  type="text"
                  style={styles.searchInput}
                  placeholder="Search technicians…"
                  value={reassignSearch}
                  onChange={(e) => setReassignSearch(e.target.value)}
                  disabled={reassignLoading}
                  aria-label="Search colleagues"
                  data-testid="reassign-search-input"
                />
              </div>

              {/* Colleague list */}
              <div style={styles.techList} role="listbox" aria-label="Available technicians" data-testid="reassign-tech-list">
                {colleaguesLoading ? (
                  <div style={styles.loadingOrEmpty}>
                    <Loader2 size={18} className="action-btn-spinner" />
                    <span>Loading technicians…</span>
                  </div>
                ) : filteredColleagues.length === 0 ? (
                  <div style={styles.loadingOrEmpty}>No technicians found</div>
                ) : (
                  filteredColleagues.map((c) => (
                    <button
                      key={c.technician_id}
                      type="button"
                      className={`tech-item-hover ${selectedColleague === c.technician_id ? "reassign-tech-selected" : ""}`}
                      style={styles.techItem}
                      onClick={() => setSelectedColleague(c.technician_id)}
                      role="option"
                      aria-selected={selectedColleague === c.technician_id}
                      data-testid={`reassign-tech-${c.technician_id}`}
                    >
                      <div style={styles.techAvatar}>
                        <User size={14} aria-hidden="true" />
                      </div>
                      <div style={styles.techInfo}>
                        <span style={styles.techName}>{c.technician_name}</span>
                        <span style={styles.techSkill}>{c.technician_skill}</span>
                      </div>
                      <StatusBadge status={c.technician_status as any} size="sm" />
                    </button>
                  ))
                )}
              </div>

              {/* Optional reason */}
              <textarea
                className="rejection-textarea"
                style={{ ...styles.textarea, height: "60px", marginTop: "12px", marginBottom: "16px" }}
                placeholder="Reason for reassignment (optional)"
                value={reassignReason}
                onChange={(e) => setReassignReason(e.target.value)}
                disabled={reassignLoading}
                aria-label="Reassignment reason"
                data-testid="reassign-reason-input"
              />

              <div style={styles.modalActions}>
                <button
                  type="button"
                  className="cancel-btn-hover"
                  style={styles.cancelBtn}
                  onClick={() => {
                    setIsReassignModalOpen(false);
                    setSelectedColleague(null);
                    setReassignSearch("");
                    setReassignReason("");
                  }}
                  disabled={reassignLoading}
                  data-testid="reassign-cancel-btn"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="tech-confirm-btn-hover"
                  style={styles.techConfirmBtn}
                  onClick={handleReassignConfirm}
                  disabled={reassignLoading || selectedColleague === null}
                  data-testid="reassign-confirm-btn"
                >
                  {reassignLoading ? (
                    <>
                      <Loader2 size={14} className="action-btn-spinner" aria-hidden="true" />
                      Reassigning…
                    </>
                  ) : (
                    "Confirm Reassign"
                  )}
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
};

export default ActionButtons;
