
export function formatStatus(status: string | null | undefined): string {
  if (!status?.trim()) {
    return "Unknown";
  }

  return status
    .trim()
    .replace(/[_-]+/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function formatDateTime(
  value: string | number | Date | null | undefined
): string {
  if (value === null || value === undefined || value === "") {
    return "Not available";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Invalid date";
  }

  return date.toLocaleString();
}

export function formatDate(
  value: string | number | Date | null | undefined
): string {
  if (value === null || value === undefined || value === "") {
    return "Not available";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Invalid date";
  }

  return date.toLocaleDateString();
}

export function formatPriority(
  priority: string | null | undefined
): string {
  if (!priority?.trim()) {
    return "Not specified";
  }

  return priority
    .trim()
    .replace(/[_-]+/g, " ")
    .toUpperCase();
}
