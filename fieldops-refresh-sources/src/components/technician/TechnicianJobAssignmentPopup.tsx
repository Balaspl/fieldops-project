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
} from "lucide-react";
import { formatAcceptanceCountdown } from "../../hooks/useAcceptanceCountdown";
import "./TechnicianJobAssignmentPopup.css";

interface TechnicianJob {
  id: number | string;
  customer_name?: string | null;
  contact_number?: string | null;
  preferred_service_date?: string | null;
  preferred_service_time?: string | null;
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

const formatSchedule = (job: TechnicianJob): string => {
  const date = job.preferred_service_date;
  const time = job.preferred_service_time;
  if (date && time) return `${date} ${time}`;
  return date || time || "N/A";
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
            <span className="technician-job-assignment-id">
              Job ID: #{job.id}
            </span>
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
                  SCHEDULE
                </span>
                <div className="technician-job-assignment-info-value">
                  {formatSchedule(job)}
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
