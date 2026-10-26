
type AppEnvironment = "development" | "staging" | "production";

const rawEnvironment = (
  process.env.EXPO_PUBLIC_APP_ENV ?? "development"
).trim().toLowerCase();

const supportedEnvironments: AppEnvironment[] = [
  "development",
  "staging",
  "production"
];

if (
  !supportedEnvironments.includes(rawEnvironment as AppEnvironment)
) {
  throw new Error(
    "EXPO_PUBLIC_APP_ENV must be development, staging, or production."
  );
}

const APP_ENV = rawEnvironment as AppEnvironment;

const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL;
const configuredWsBaseUrl = process.env.EXPO_PUBLIC_WS_BASE_URL;

function validateUrl(
  value: string,
  name: string,
  allowedProtocols: string[]
): string {
  let parsed: URL;

  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`${name} is not a valid absolute URL.`);
  }

  if (!allowedProtocols.includes(parsed.protocol)) {
    throw new Error(
      `${name} must use one of these protocols: ${allowedProtocols.join(", ")}.`
    );
  }

  if (parsed.username || parsed.password) {
    throw new Error(`${name} must not contain embedded credentials.`);
  }

  if (parsed.search || parsed.hash) {
    throw new Error(`${name} must not contain a query string or fragment.`);
  }

  return value.replace(/\/+$/, "");
}

if (!apiBaseUrl?.trim()) {
  throw new Error(
    "EXPO_PUBLIC_API_BASE_URL is missing. Check the mobile .env file or EAS environment variables."
  );
}

const API_BASE_URL = validateUrl(
  apiBaseUrl.trim(),
  "EXPO_PUBLIC_API_BASE_URL",
  ["http:", "https:"]
);

const parsedApiUrl = new URL(API_BASE_URL);

if (
  APP_ENV !== "development" &&
  parsedApiUrl.protocol !== "https:"
) {
  throw new Error(
    `EXPO_PUBLIC_API_BASE_URL must use HTTPS in ${APP_ENV}.`
  );
}

const defaultWsUrl = API_BASE_URL.replace(
  /^https?:/,
  parsedApiUrl.protocol === "https:" ? "wss:" : "ws:"
);

const WS_BASE_URL = configuredWsBaseUrl?.trim()
  ? validateUrl(
      configuredWsBaseUrl.trim(),
      "EXPO_PUBLIC_WS_BASE_URL",
      ["ws:", "wss:"]
    )
  : defaultWsUrl;

const parsedWsUrl = new URL(WS_BASE_URL);

if (
  APP_ENV !== "development" &&
  parsedWsUrl.protocol !== "wss:"
) {
  throw new Error(
    `EXPO_PUBLIC_WS_BASE_URL must use WSS in ${APP_ENV}.`
  );
}

export const env = {
  APP_ENV,
  API_BASE_URL,
  WS_BASE_URL
};
