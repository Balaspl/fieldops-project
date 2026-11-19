export function formatDate(value?: string | null): string {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" }).format(date);
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }).format(date);
}

export function formatMoney(value?: number | string | null): string {
  const amount = Number(value ?? 0);
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(Number.isFinite(amount) ? amount : 0);
}

export function normalizedStatus(value?: string | null): string {
  return String(value ?? "UNKNOWN").trim().toUpperCase().replaceAll("-", "_").replaceAll(" ", "_");
}

export function canCancelRequest(requestStatus?: string | null, linkedJobStatus?: string | null, hasLinkedJob = false): boolean {
  if (hasLinkedJob) {
    // The backend only permits cancellation of a linked job while it is CREATED, ASSIGNED or ACCEPTED.
    return ["CREATED", "ASSIGNED", "ACCEPTED"].includes(normalizedStatus(linkedJobStatus));
  }
  return ["UNASSIGNED", "PENDING", "CREATED", "ASSIGNED"].includes(normalizedStatus(requestStatus));
}

export function canEditRequest(requestStatus?: string | null, linkedJobStatus?: string | null, hasLinkedJob = false): boolean {
  if (hasLinkedJob) {
    // The backend permits editing a linked request only while its job is still CREATED.
    return normalizedStatus(linkedJobStatus) === "CREATED";
  }
  return normalizedStatus(requestStatus) === "UNASSIGNED";
}

export function customerDisplayName(firstName?: string | null, fullName?: string | null): string {
  const name = fullName?.trim() || firstName?.trim() || "there";
  return name.split(/\s+/)[0] || "there";
}
