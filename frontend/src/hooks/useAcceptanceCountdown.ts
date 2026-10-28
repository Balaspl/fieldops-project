import { useEffect, useMemo, useState } from "react";

export const ACCEPTANCE_WINDOW_SECONDS = 5 * 60;

export interface AcceptanceCountdownJob {
  id?: number | string;
  status?: string | null;
  assigned_at?: string | null;
  acceptance_expires_at?: string | null;
}

export const isAwaitingAcceptance = (
  job: AcceptanceCountdownJob | null | undefined,
): boolean => {
  const status = String(job?.status ?? "").trim().toUpperCase();
  return [
    "ASSIGNED",
    "ACTIVE",
    "PENDING",
    "AWAITING_ACCEPTANCE",
  ].includes(status);
};

export const getAcceptanceDeadline = (
  job: AcceptanceCountdownJob | null | undefined,
): number | null => {
  if (!job || !isAwaitingAcceptance(job)) return null;

  if (job.acceptance_expires_at) {
    const acceptanceDeadline = new Date(
      job.acceptance_expires_at,
    ).getTime();
    if (Number.isFinite(acceptanceDeadline)) return acceptanceDeadline;
  }

  if (!job.assigned_at) return null;
  const assignedAt = new Date(job.assigned_at).getTime();
  return Number.isFinite(assignedAt)
    ? assignedAt + ACCEPTANCE_WINDOW_SECONDS * 1000
    : null;
};

export const getRemainingAcceptanceSeconds = (
  job: AcceptanceCountdownJob | null | undefined,
  now = Date.now(),
): number | null => {
  const deadline = getAcceptanceDeadline(job);
  if (deadline === null) return null;
  return Math.max(0, Math.floor((deadline - now) / 1000));
};

export const formatAcceptanceCountdown = (seconds: number): string => {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(
    remainingSeconds,
  ).padStart(2, "0")}`;
};

export const useAcceptanceCountdowns = (
  jobs: readonly AcceptanceCountdownJob[],
): Record<string, number | null> => {
  const timerSignature = useMemo(
    () =>
      jobs
        .filter((job) => isAwaitingAcceptance(job))
        .map((job) => {
          const deadline = getAcceptanceDeadline(job);
          return deadline === null ? null : `${job.id}:${deadline}`;
        })
        .filter((value): value is string => value !== null)
        .sort()
        .join("|"),
    [jobs],
  );
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    setNow(Date.now());
    if (!timerSignature) return;

    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [timerSignature]);

  return useMemo(() => {
    const countdowns: Record<string, number | null> = {};
    for (const job of jobs) {
      if (job.id === undefined || job.id === null) continue;
      countdowns[String(job.id)] = getRemainingAcceptanceSeconds(job, now);
    }
    return countdowns;
  }, [jobs, now]);
};
