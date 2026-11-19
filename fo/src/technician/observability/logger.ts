
type LogMetadata = Record<string, unknown>;

const SENSITIVE_KEY_PATTERN =
  /password|token|authorization|cookie|secret|email|phone|address|api.?key/i;

function sanitizeValue(value: unknown, key = ""): unknown {
  if (SENSITIVE_KEY_PATTERN.test(key)) {
    return "[REDACTED]";
  }

  if (value instanceof Error) {
    return {
      name: value.name,
      message: "An error occurred."
    };
  }

  if (Array.isArray(value)) {
    return value.map((item) => sanitizeValue(item));
  }

  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([childKey, childValue]) => [
        childKey,
        sanitizeValue(childValue, childKey)
      ])
    );
  }

  if (typeof value === "string") {
    return value
      .replace(/Bearer\s+\S+/gi, "Bearer [REDACTED]")
      .replace(
        /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi,
        "[EMAIL REDACTED]"
      );
  }

  return value;
}

export function logEvent(
  event: string,
  metadata?: LogMetadata
): void {
  if (__DEV__) {
    console.info(
      `[FieldOps] ${event}`,
      sanitizeValue(metadata ?? {})
    );
  }
}

export function logError(
  event: string,
  error: unknown,
  metadata?: LogMetadata
): void {
  if (__DEV__) {
    const candidate =
      typeof error === "object" && error !== null
        ? error as {
            name?: unknown;
            code?: unknown;
            response?: { status?: unknown } | null;
          }
        : null;
    const safeError: Record<string, unknown> = {
      name:
        typeof candidate?.name === "string"
          ? candidate.name
          : "Error",
      message: "An error occurred."
    };

    if (
      typeof candidate?.code === "string" &&
      /^[A-Z0-9_]+$/i.test(candidate.code)
    ) {
      safeError.code = candidate.code;
    }

    if (
      typeof candidate?.response?.status === "number" &&
      Number.isInteger(candidate.response.status)
    ) {
      safeError.httpStatus = candidate.response.status;
    }

    console.error(
      `[FieldOps] ${event}`,
      sanitizeValue({
        ...metadata,
        error: safeError
      })
    );
  }
}
