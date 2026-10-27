
import axios from "axios";

interface ApiErrorPayload {
  detail?: unknown;
  message?: unknown;
  error?: unknown;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  );
}


function getPayloadMessage(payload: unknown): string | null {
  if (typeof payload === "string" && payload.trim()) {
    return payload.trim();
  }

  if (Array.isArray(payload)) {
    const messages = payload
      .map((item) => {
        if (isRecord(item)) {
          const message =
            typeof item.msg === "string"
              ? item.msg.trim()
              : getPayloadMessage(
                  item.message ?? item.detail ?? item.error
                );

          if (!message) {
            return null;
          }

          const location = Array.isArray(item.loc)
            ? item.loc.filter(
                (part): part is string | number =>
                  typeof part === "string" ||
                  typeof part === "number"
              )
            : [];

          const field = location
            .filter((part) => part !== "body")
            .join(".");

          return field ? `${field}: ${message}` : message;
        }

        return getPayloadMessage(item);
      })
      .filter((message): message is string => Boolean(message));

    return messages.length > 0
      ? [...new Set(messages)].join("; ")
      : null;
  }

  if (!isRecord(payload)) {
    return null;
  }

  if (typeof payload.msg === "string" && payload.msg.trim()) {
    const location = Array.isArray(payload.loc)
      ? payload.loc.filter(
          (part): part is string | number =>
            typeof part === "string" ||
            typeof part === "number"
        )
      : [];

    const field = location
      .filter((part) => part !== "body")
      .join(".");

    return field
      ? `${field}: ${payload.msg.trim()}`
      : payload.msg.trim();
  }

  for (const key of ["detail", "message", "error", "msg"]) {
    const value = payload[key];

    if (value === undefined || value === null) {
      continue;
    }

    const message = getPayloadMessage(value);

    if (message) {
      return message;
    }
  }

  return null;
}


export function getApiErrorMessage(
  error: unknown,
  fallback = "Something went wrong. Please try again."
): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) {
      return "Unable to connect to the server. Check your connection and try again.";
    }

    const message = getPayloadMessage(error.response.data);

    if (message) {
      return message;
    }

    switch (error.response.status) {
      case 400:
        return "The request was invalid. Check your input and try again.";
      case 401:
        return "Your session may have expired. Please sign in again.";
      case 403:
        return "You do not have permission to perform this action.";
      case 404:
        return "The requested information could not be found.";
      case 429:
        return "Too many requests. Please wait and try again.";
      default:
        return fallback;
    }
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message;
  }

  return fallback;
}
