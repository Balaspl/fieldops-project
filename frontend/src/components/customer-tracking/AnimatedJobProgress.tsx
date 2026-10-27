import { useEffect } from "react";
import {
  Bike,
  CalendarCheck2,
  Check,
  CircleCheck,
  MapPin,
  Navigation,
  Wrench,
} from "lucide-react";
import { useTrackingStore } from "../../store/trackingStore";
import "./AnimatedJobProgress.css";

type AnimatedJobProgressProps = {
  jobId: string | number;
  status?: string | null;
  estimatedArrival?: string | null;
  etaDurationMinutes?: number | null;
  etaDistanceKm?: number | null;
  etaTrafficDelayMinutes?: number | null;
  etaStatus?: string | null;
  etaUpdatedAt?: string | null;
  etaMessage?: string | null;
  arrivedAt?: string | null;
  workStartedAt?: string | null;
  completedAt?: string | null;
  compact?: boolean;
  useLiveUpdates?: boolean;
};

const stages = [
  { label: "Booked", Icon: CalendarCheck2 },
  { label: "Accepted", Icon: Wrench },
  { label: "On the way", Icon: Bike },
  { label: "Arrived", Icon: MapPin },
  { label: "Work started", Icon: Wrench },
  { label: "Completed", Icon: CircleCheck },
];

function normalizeStatus(status?: string | null): string {
  return String(status ?? "").trim().toUpperCase();
}

function stageForStatus(status: string, workStartedAt?: string | null): number {
  switch (status) {
    case "EN_ROUTE":
      return 2;
    case "ACCEPTED":
      return 1;
    case "ON_SITE":
      return 3;
    case "IN_PROGRESS":
      return workStartedAt ? 4 : 3;
    case "PAUSED":
      return 4;
    case "COMPLETED":
      return 5;
    default:
      return 0;
  }
}

function formatTime(value?: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return null;
  return date.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

function arrivalDetail(
  status: string,
  arrival: string | null,
  durationMinutes: number | null,
  etaMessage?: string | null,
): { title: string; detail: string | null } | null {
  if (status !== "EN_ROUTE") return null;
  if (arrival) {
    const duration = Number(durationMinutes);
    return {
      title: `Estimated arrival ${arrival}`,
      detail:
        Number.isFinite(duration) && duration > 0
          ? `About ${Math.round(duration)} min away`
          : null,
    };
  }
  const duration = Number(durationMinutes);
  if (
    durationMinutes !== null &&
    durationMinutes !== undefined &&
    Number.isFinite(duration) &&
    duration >= 0
  ) {
    return {
      title: duration < 1 ? "Arriving now" : `About ${Math.round(duration)} min away`,
      detail: null,
    };
  }
  return {
    title: "Arrival estimate unavailable",
    detail: etaMessage || null,
  };
}

export default function AnimatedJobProgress({
  jobId,
  status: apiStatus,
  estimatedArrival,
  etaDurationMinutes,
  etaDistanceKm,
  etaTrafficDelayMinutes,
  etaStatus,
  etaUpdatedAt,
  etaMessage,
  arrivedAt,
  workStartedAt,
  completedAt,
  compact = false,
  useLiveUpdates = true,
}: AnimatedJobProgressProps) {
  const liveUpdate = useTrackingStore(
    (state) => state.jobLiveUpdates[String(jobId)],
  );

  const apiNorm = normalizeStatus(apiStatus);
  const liveNorm = normalizeStatus(useLiveUpdates ? liveUpdate?.status : undefined);

  // Resolution rules:
  // 1. If apiStatus is in terminal status (COMPLETED, CLOSED, CANCELLED), API is authoritative!
  //    Never let a stale liveUpdate from when the technician was on the road keep the UI in EN_ROUTE!
  // 2. If both exist and neither is terminal, pick whichever stage is further along.
  // 3. Otherwise fall back to whichever is present.
  let status = apiNorm;
  if (["COMPLETED", "CLOSED", "CANCELLED"].includes(apiNorm)) {
    status = apiNorm;
  } else if (["COMPLETED", "CLOSED", "CANCELLED"].includes(liveNorm)) {
    status = liveNorm;
  } else if (apiNorm && liveNorm) {
    const apiStage = stageForStatus(apiNorm, workStartedAt);
    const liveStage = stageForStatus(liveNorm, workStartedAt);
    status = liveStage >= apiStage ? liveNorm : apiNorm;
  } else {
    status = liveNorm || apiNorm;
  }

  const currentStage = stageForStatus(status, workStartedAt);
  const completed = status === "COMPLETED";
  const cancelled = status === "CANCELLED";
  const closed = status === "CLOSED";

  // Sync terminal status to tracking store so all tracking observers stay aligned
  useEffect(() => {
    if (completed && jobId) {
      useTrackingStore.getState().setJobTrackingSnapshot(String(jobId), {
        status: "COMPLETED",
        eta: null,
        duration_minutes: null,
      });
    }
  }, [completed, jobId]);

  const eta =
    useLiveUpdates && liveUpdate?.eta !== undefined
      ? formatTime(liveUpdate.eta)
      : formatTime(estimatedArrival);
  const duration =
    useLiveUpdates && liveUpdate?.duration_minutes !== undefined
      ? liveUpdate.duration_minutes
      : etaDurationMinutes ?? null;
  const etaContent = arrivalDetail(
    status,
    eta,
    duration,
    etaMessage,
  );

  const statusTitle = cancelled
    ? "This job was cancelled"
    : closed
      ? "This job is closed"
      : completed
        ? "Your job is complete"
        : stages[currentStage].label === "Booked"
          ? "Your service is booked"
          : stages[currentStage].label === "Accepted"
            ? "Your technician accepted the job"
          : stages[currentStage].label === "On the way"
            ? "Your technician is on the way"
            : stages[currentStage].label === "Arrived"
              ? "Your technician has arrived"
              : status === "PAUSED"
                ? "Work is paused"
                : status === "IN_PROGRESS" && !workStartedAt
                  ? "Your technician has arrived"
                  : "Work is in progress";

  const arrivalTime = formatTime(arrivedAt);
  const workStartTime = formatTime(workStartedAt);
  const completionTime = formatTime(completedAt);

  return (
    <section
      className={`animated-job-progress${compact ? " is-compact" : ""}${completed ? " is-completed" : ""}${cancelled || closed ? " is-terminal-other" : ""}`}
      aria-label={`Job progress: ${statusTitle}`}
      data-testid={`job-progress-${jobId}`}
      data-stage={currentStage}
    >
      {!compact && <div className="animated-job-progress__heading">
        <div className="animated-job-progress__heading-icon" aria-hidden="true">
          {completed ? <Check size={18} /> : <Navigation size={17} />}
        </div>
        <div className="animated-job-progress__heading-copy">
          <h3>{statusTitle}</h3>
          <span>
            {cancelled || closed
              ? "Status confirmed by FieldOps"
              : completed
                ? "Thanks for choosing FieldOps"
                : "We'll keep you updated as your visit progresses"}
          </span>
        </div>
      </div>}

      {compact && (completed || cancelled || closed) && (
        <div className="animated-job-progress__compact-status" role="status">
          {statusTitle}
        </div>
      )}

      {!cancelled && !closed && (
        <>
          <div className="animated-job-progress__track" aria-label="Job stages">
            <div className="animated-job-progress__rail" aria-hidden="true" />
            <div
              className="animated-job-progress__rail-fill"
              style={{ width: `${(currentStage / 5) * 85}%` }}
              aria-hidden="true"
            />
            <div
              className="animated-job-progress__traveler"
              style={{ left: `${7.5 + currentStage * 17}%` }}
              aria-hidden="true"
              data-testid={`job-progress-indicator-${jobId}`}
            >
              {completed ? <Check size={15} /> : <Navigation size={15} />}
            </div>
            <ol className="animated-job-progress__stages">
              {stages.map(({ label, Icon }, index) => {
                const isCurrent = index === currentStage;
                const isDone = index < currentStage || (completed && index === 4);
                return (
                  <li
                    key={label}
                    className={`animated-job-progress__stage${isCurrent ? " is-current" : ""}${isDone ? " is-done" : ""}`}
                    aria-current={isCurrent ? "step" : undefined}
                    data-testid={`job-progress-stage-${index}`}
                  >
                    <span className="animated-job-progress__stage-icon" aria-hidden="true">
                      {isDone && !isCurrent ? <Check size={13} /> : <Icon size={14} />}
                    </span>
                    <span className="animated-job-progress__stage-label">{label}</span>
                  </li>
                );
              })}
            </ol>
          </div>

          {etaContent && (
            <div className="animated-job-progress__eta" role="status" aria-live="polite">
              <span className="animated-job-progress__eta-label">Estimated arrival</span>
              <strong>{etaContent.title.replace("Estimated arrival ", "")}</strong>
              {etaContent.detail && <span>{etaContent.detail}</span>}
              {eta && etaDistanceKm != null && Number.isFinite(Number(etaDistanceKm)) && (
                <span>{Number(etaDistanceKm).toFixed(1)} km route</span>
              )}
              {eta && etaTrafficDelayMinutes != null && Number(etaTrafficDelayMinutes) > 0 && (
                <span>Traffic +{Math.round(Number(etaTrafficDelayMinutes))} min</span>
              )}
              {eta && etaStatus && etaStatus !== "unknown" && (
                <span className="animated-job-progress__eta-status">
                  {etaStatus === "calculated" ? "Route based" : "Estimated"}
                </span>
              )}
              {eta && formatTime(etaUpdatedAt) && (
                <span className="animated-job-progress__eta-updated">
                  Updated {formatTime(etaUpdatedAt)}
                </span>
              )}
            </div>
          )}

          {(arrivalTime || workStartTime || (completed && completionTime)) && (
            <div className="animated-job-progress__timestamps" aria-label="Visit times">
              {arrivalTime && (
                <span>
                  <MapPin size={13} aria-hidden="true" />
                  Arrived {arrivalTime}
                </span>
              )}
              {workStartTime && (
                <span>
                  <Wrench size={13} aria-hidden="true" />
                  Work started {workStartTime}
                </span>
              )}
              {completed && completionTime && (
                <span>
                  <CircleCheck size={13} aria-hidden="true" />
                  Completed {completionTime}
                </span>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
