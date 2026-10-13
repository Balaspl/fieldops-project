
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

  if (!isRecord(payload)) {
    return null;
  }

  const data = payload as ApiErrorPayload;

  for (const value of [data.detail, data.message, data.error]) {
    if (typeof value === "string" && value.trim()) {
      return value.trim();
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
