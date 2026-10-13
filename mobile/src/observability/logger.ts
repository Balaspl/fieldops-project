
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
    const safeError =
      error instanceof Error
        ? {
            name: error.name,
            message: "An error occurred."
          }
        : { message: "An unexpected error occurred." };

    console.error(
      `[FieldOps] ${event}`,
      sanitizeValue({
        ...metadata,
        error: safeError
      })
    );
  }
}
