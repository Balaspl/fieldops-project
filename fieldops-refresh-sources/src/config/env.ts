type AppEnvironment = "development" | "staging" | "production";

const rawEnvironment = (
  process.env.EXPO_PUBLIC_APP_ENV ?? "development"
)
  .trim()
  .toLowerCase();

const allowedEnvironments: AppEnvironment[] = [
  "development",
  "staging",
  "production",
];

if (!allowedEnvironments.includes(rawEnvironment as AppEnvironment)) {
  throw new Error(
    "EXPO_PUBLIC_APP_ENV must be development, staging, or production.",
  );
}

const APP_ENV = rawEnvironment as AppEnvironment;

const rawApiUrl = process.env.EXPO_PUBLIC_API_BASE_URL?.trim();

if (!rawApiUrl) {
  throw new Error(
    "EXPO_PUBLIC_API_BASE_URL is missing. Copy .env.example to .env and configure it.",
  );
}

function validateBaseUrl(value: string): string {
  let parsed: URL;

  try {
    parsed = new URL(value);
  } catch {
    throw new Error(
      "EXPO_PUBLIC_API_BASE_URL must be an absolute URL, such as http://10.0.2.2:8000.",
    );
  }

  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error(
      "EXPO_PUBLIC_API_BASE_URL must use HTTP or HTTPS.",
    );
  }

  if (
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash
  ) {
    throw new Error(
      "The API base URL must not contain credentials, a query string, or a fragment.",
    );
  }

  if (APP_ENV !== "development" && parsed.protocol !== "https:") {
    throw new Error(
      "HTTPS is required for staging and production.",
    );
  }

  return value.replace(/\/+$/, "");
}

export const env = {
  APP_ENV,

  API_BASE_URL: validateBaseUrl(rawApiUrl),

  // Client-side map SDK key; restrict this key in the Ola Maps console.
  OLA_MAPS_API_KEY: (
    process.env.EXPO_PUBLIC_OLA_MAPS_API_KEY ?? ""
  ).trim(),
};