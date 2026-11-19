
import type { TechnicianJobAction } from "../api/jobActions";

export type CanonicalJobStatus =
  | "UNASSIGNED"
  | "AWAITING_ACCEPTANCE"
  | "ASSIGNED"
  | "ACTIVE"
  | "ACCEPTED"
  | "EN_ROUTE"
  | "ON_SITE"
  | "IN_PROGRESS"
  | "PAUSED"
  | "COMPLETED"
  | "CANCELLED"
  | "REJECTED"
  | "UNKNOWN";

export interface JobActionOption {
  action: TechnicianJobAction;
  label: string;
}

const STATUS_ALIASES: Record<string, CanonicalJobStatus> = {
  UNASSIGNED: "UNASSIGNED",
  AWAITING_ACCEPTANCE: "AWAITING_ACCEPTANCE",
  PENDING_ACCEPTANCE: "AWAITING_ACCEPTANCE",
  ASSIGNED: "ASSIGNED",
  ACTIVE: "ACTIVE",
  ACCEPTED: "ACCEPTED",
  EN_ROUTE: "EN_ROUTE",
  ENROUTE: "EN_ROUTE",
  ONSITE: "ON_SITE",
  ON_SITE: "ON_SITE",
  IN_PROGRESS: "IN_PROGRESS",
  PAUSED: "PAUSED",
  COMPLETED: "COMPLETED",
  COMPLETE: "COMPLETED",
  CANCELLED: "CANCELLED",
  CANCELED: "CANCELLED",
  REJECTED: "REJECTED",
  REJECTED_BY_TECHNICIAN: "REJECTED"
};

export function normalizeJobStatus(
  status: string | null | undefined
): CanonicalJobStatus {
  if (!status?.trim()) {
    return "UNKNOWN";
  }

  const normalized = status
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

  return STATUS_ALIASES[normalized] ?? "UNKNOWN";
}

export function getJobStatusLabel(
  status: string | null | undefined
): string {
  const normalized = normalizeJobStatus(status);

  if (normalized === "UNKNOWN") {
    return "Unknown";
  }

  return normalized
    .toLowerCase()
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

/**
 * These are UI suggestions only.
 * The backend must validate every requested transition and job ownership.
 */
export function getJobActionOptions(
  status: string | null | undefined
): JobActionOption[] {
  switch (normalizeJobStatus(status)) {
    case "AWAITING_ACCEPTANCE":
    case "ASSIGNED":
    case "ACTIVE":
      return [
        { action: "accept", label: "Accept" },
        { action: "reject", label: "Reject" }
      ];

    case "ACCEPTED":
      return [{ action: "start", label: "Start Travel" }];

    case "EN_ROUTE":
      return [{ action: "on-site", label: "Mark Onsite" }];

    case "ON_SITE":
    case "IN_PROGRESS":
      return [
        { action: "complete", label: "Complete Job" }
      ];

    case "PAUSED":
      return [{ action: "resume", label: "Resume Job" }];

    default:
      return [];
  }
}
