import {
  CalendarDays,
  Check,
  Clock,
  MapPin,
  Navigation,
  Phone,
  User,
  Wrench,
  X,
  AlertTriangle,
} from "lucide-react";
import { formatAcceptanceCountdown } from "../../hooks/useAcceptanceCountdown";
import "./TechnicianJobAssignmentPopup.css";

interface TechnicianJob {
  id: number | string;
  customer_name?: string | null;
  contact_number?: string | null;
  priority?: string | null;
  preferred_service_date?: string | null;
  preferred_service_time?: string | null;
  preferred_visit_time?: string | null;
  site_address?: string | null;
  location?: string | null;
  service_type?: string | null;
  issue_description?: string | null;
}

interface TechnicianJobAssignmentPopupProps {
  job: TechnicianJob;
  countdownSeconds: number | null;
  distanceDisplay: string;
  loading: boolean;
  rejecting?: boolean;
  rejectReason?: string;
  onClose: () => void;
  onAccept: () => void;
  onReject: () => void;
  onRejectReasonChange?: (reason: string) => void;
  onConfirmReject?: () => void;
  onCancelReject?: () => void;
}

const formatTime = (timeStr?: string | null): string => {
  if (!timeStr) return "";
  const trimmed = String(timeStr).trim();
  if (/am|pm/i.test(trimmed)) return trimmed;
  const parts = trimmed.split(":");
  if (parts.length >= 2) {
    const hours = parseInt(parts[0], 10);
    const minutes = parts[1];
    if (!isNaN(hours)) {
      const ampm = hours >= 12 ? "PM" : "AM";
      const h12 = hours % 12 || 12;
      return `${String(h12).padStart(2, "0")}:${minutes} ${ampm}`;
    }
  }
  return trimmed;
};

const formatSchedule = (job: TechnicianJob): string => {
  const date = job.preferred_service_date;
  const rawTime = job.preferred_service_time || job.preferred_visit_time;
  const time = formatTime(rawTime);
  if (date && time) return `${date} at ${time}`;
  return date || time || "N/A";
};

const getPriorityTheme = (p?: string | null) => {
  const norm = String(p || "MEDIUM").toUpperCase().trim();
  switch (norm) {
    case "URGENT":
    case "CRITICAL":
      return {
        label: "EMERGENCY / CRITICAL",
        color: "#DC2626",
        bg: "#FEF2F2",
        border: "#FCA5A5",
        iconBg: "#FEE2E2",
      };
    case "HIGH":
      return {
        label: "HIGH PRIORITY",
        color: "#D97706",
        bg: "#FFFBEB",
        border: "#FDE68A",
        iconBg: "#FEF3C7",
      };
    case "LOW":
      return {
        label: "LOW PRIORITY",
        color: "#059669",
        bg: "#ECFDF5",
        border: "#A7F3D0",
        iconBg: "#D1FAE5",
      };
    case "MEDIUM":
    default:
      return {
        label: "STANDARD PRIORITY",
        color: "#2563EB",
        bg: "#EFF6FF",
        border: "#BFDBFE",
        iconBg: "#DBEAFE",
      };
  }
};

export default function TechnicianJobAssignmentPopup({
  job,
  countdownSeconds,
  distanceDisplay,
  loading,
  rejecting = false,
  rejectReason = "",
  onClose,
  onAccept,
  onReject,
  onRejectReasonChange,
  onConfirmReject,
  onCancelReject,
}: TechnicianJobAssignmentPopupProps) {
  const expired = countdownSeconds !== null && countdownSeconds <= 0;
  const priorityTheme = getPriorityTheme(job.priority);

  return (
    <div className="technician-job-assignment-modal">
      <div
        className="technician-job-assignment-backdrop"
        onClick={onClose}
      />
      <div
        className="technician-job-assignment-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="technician-job-assignment-title"
      >
        <header className="technician-job-assignment-header">
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
              <span className="technician-job-assignment-id">
                Job ID: #{job.id}
              </span>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "4px",
                  padding: "3px 9px",
                  borderRadius: "12px",
                  fontSize: "11px",
                  fontWeight: 800,
                  letterSpacing: "0.5px",
                  background: priorityTheme.bg,
                  color: priorityTheme.color,
                  border: `1px solid ${priorityTheme.border}`,
                }}
              >
                <AlertTriangle size={12} />
                {priorityTheme.label}
              </span>
            </div>
            <h3
              className="technician-job-assignment-title"
              id="technician-job-assignment-title"
            >
              Job Assigned
            </h3>
            <p className="technician-job-assignment-subtitle">
              You have been assigned a new service job.
            </p>
          </div>
          <button
            className="technician-job-assignment-close"
            type="button"
            aria-label="Close assigned job popup"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </header>

        {rejecting ? (
          <div className="technician-job-assignment-rejection">
            <label htmlFor="technician-assignment-reject-reason">
              Why are you rejecting this job?
            </label>
            <textarea
              id="technician-assignment-reject-reason"
              value={rejectReason}
              onChange={(event) => onRejectReasonChange?.(event.target.value)}
              placeholder="Explain why you're rejecting this job..."
              rows={4}
            />
          </div>
        ) : (
          <>
        <section
          className="technician-job-assignment-summary"
          aria-label="Offer time and customer distance"
        >
          <div className="technician-job-assignment-summary-cell">
            <span className="technician-job-assignment-icon">
              <Clock size={19} />
            </span>
            <div className="technician-job-assignment-summary-content">
              <span className="technician-job-assignment-eyebrow">
                TIME REMAINING
              </span>
              <div
                className="technician-job-assignment-summary-value"
                data-testid="assignment-countdown"
              >
                {countdownSeconds === null
                  ? "Unavailable"
                  : expired
                    ? "EXPIRED"
                    : formatAcceptanceCountdown(countdownSeconds)}
              </div>
              {countdownSeconds !== null && !expired && (
                <span className="technician-job-assignment-summary-note">
                  REMAINING
                </span>
              )}
            </div>
          </div>
          <div className="technician-job-assignment-summary-cell">
            <span className="technician-job-assignment-icon">
              <Navigation size={19} />
            </span>
            <div className="technician-job-assignment-summary-content">
              <span className="technician-job-assignment-eyebrow">
                DISTANCE TO CUSTOMER
              </span>
              <div
                className="technician-job-assignment-summary-value"
                data-testid="assignment-top-distance"
                aria-live="polite"
              >
                {distanceDisplay}
              </div>
            </div>
          </div>
        </section>

        <section className="technician-job-assignment-columns">
          <div className="technician-job-assignment-customer-stack">
            <article className="technician-job-assignment-info-card">
              <span className="technician-job-assignment-info-icon">
                <User size={17} />
              </span>
              <div className="technician-job-assignment-info-content">
                <span className="technician-job-assignment-eyebrow">
                  CUSTOMER
                </span>
                <div className="technician-job-assignment-info-value">
                  {job.customer_name || "N/A"}
                </div>
              </div>
            </article>
            <article className="technician-job-assignment-info-card">
              <span className="technician-job-assignment-info-icon is-blue">
                <Phone size={16} />
              </span>
              <div className="technician-job-assignment-info-content">
                <span className="technician-job-assignment-eyebrow">
                  CONTACT
                </span>
                <div className="technician-job-assignment-info-value">
                  {job.contact_number || "N/A"}
                </div>
              </div>
            </article>
            <article className="technician-job-assignment-info-card">
              <span className="technician-job-assignment-info-icon">
                <CalendarDays size={16} />
              </span>
              <div className="technician-job-assignment-info-content">
                <span className="technician-job-assignment-eyebrow">
                  APPOINTMENT DATE
                </span>
                <div className="technician-job-assignment-info-value">
                  {job.preferred_service_date || "Today"}
                </div>
              </div>
            </article>
            <article className="technician-job-assignment-info-card" style={{ border: "1.5px solid #93C5FD", background: "#F0F9FF" }}>
              <span className="technician-job-assignment-info-icon is-blue" style={{ background: "#DBEAFE", color: "#1D4ED8" }}>
                <Clock size={16} />
              </span>
              <div className="technician-job-assignment-info-content">
                <span className="technician-job-assignment-eyebrow" style={{ color: "#1E40AF", fontWeight: 700 }}>
                  PREFERRED TIME
                </span>
                <div className="technician-job-assignment-info-value" style={{ fontWeight: 800, color: "#1E3A8A", fontSize: "14px" }}>
                  {formatTime(job.preferred_service_time || job.preferred_visit_time) || "09:00 AM"}
                </div>
              </div>
            </article>
            <article className="technician-job-assignment-info-card" style={{ border: `1.5px solid ${priorityTheme.border}`, background: priorityTheme.bg }}>
              <span className="technician-job-assignment-info-icon" style={{ background: priorityTheme.iconBg, color: priorityTheme.color }}>
                <AlertTriangle size={16} />
              </span>
              <div className="technician-job-assignment-info-content">
                <span className="technician-job-assignment-eyebrow" style={{ color: priorityTheme.color, fontWeight: 700 }}>
                  JOB PRIORITY
                </span>
                <div className="technician-job-assignment-info-value" style={{ fontWeight: 800, color: priorityTheme.color, fontSize: "14px" }}>
                  {job.priority ? job.priority.toUpperCase() : "MEDIUM"}
                </div>
              </div>
            </article>
          </div>
          <article className="technician-job-assignment-info-card technician-job-assignment-location-card">
            <span className="technician-job-assignment-info-icon is-green">
              <MapPin size={17} />
            </span>
            <div className="technician-job-assignment-info-content">
              <span className="technician-job-assignment-eyebrow">
                LOCATION
              </span>
              <div className="technician-job-assignment-info-value">
                {job.site_address || job.location || "N/A"}
              </div>
            </div>
          </article>
        </section>

        <section
          className="technician-job-assignment-distance"
          aria-live="polite"
        >
          <div className="technician-job-assignment-distance-label">
            <span className="technician-job-assignment-icon">
              <Navigation size={18} />
            </span>
            <span>Current location to customer</span>
          </div>
          <strong
            className="technician-job-assignment-distance-value"
            data-testid="assignment-distance-summary"
          >
            {distanceDisplay}
          </strong>
        </section>

        <section className="technician-job-assignment-service">
          <div className="technician-job-assignment-service-heading">
            <span className="technician-job-assignment-info-icon">
              <Wrench size={17} />
            </span>
            <div>
              <span className="technician-job-assignment-eyebrow">
                SERVICE TYPE
              </span>
              <div className="technician-job-assignment-service-name">
                {job.service_type || "Service Request"}
              </div>
            </div>
          </div>
          {/* Prominent Appointment Date & Time Banner */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              background: "#F0FDF4",
              border: "1.5px solid #BBF7D0",
              borderRadius: "10px",
              padding: "10px 14px",
              margin: "12px 0",
              fontSize: "13px",
              color: "#166534",
            }}
          >
            <Clock size={16} color="#16A34A" />
            <span>
              Appointment Time:{" "}
              <strong style={{ color: "#15803D", fontSize: "14px" }}>
                {formatTime(job.preferred_service_time || job.preferred_visit_time) || "09:00 AM"}
              </strong>
              {job.preferred_service_date ? ` on ${job.preferred_service_date}` : ""}
            </span>
          </div>
          <p className="technician-job-assignment-service-description">
            {job.issue_description ||
              "No additional service details provided."}
          </p>
        </section>
          </>
        )}

        <div className="technician-job-assignment-actions">
          {rejecting ? (
            <>
              <button
                type="button"
                onClick={onCancelReject}
                disabled={loading}
                className="technician-job-assignment-action is-cancel"
              >
                Back
              </button>
              <button
                type="button"
                onClick={onConfirmReject}
                disabled={loading || rejectReason.trim().length < 10}
                className="technician-job-assignment-action is-reject"
              >
                {loading ? "Rejecting..." : "Confirm Reject"}
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={onAccept}
                disabled={loading || expired}
                className="technician-job-assignment-action is-accept"
              >
                <Check size={18} />
                {loading ? "Accepting..." : "Accept Job"}
              </button>
              <button
                type="button"
                onClick={onReject}
                disabled={loading}
                className="technician-job-assignment-action is-reject"
              >
                <X size={18} />
                Reject
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
