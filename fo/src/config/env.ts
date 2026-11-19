type AppEnvironment = "development" | "staging" | "production";

const appEnvironment = (process.env.EXPO_PUBLIC_APP_ENV ?? "development")
  .trim()
  .toLowerCase() as AppEnvironment;

if (!["development", "staging", "production"].includes(appEnvironment)) {
  throw new Error("EXPO_PUBLIC_APP_ENV must be development, staging, or production.");
}

const rawApiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL?.trim();
if (!rawApiBaseUrl) {
  throw new Error("EXPO_PUBLIC_API_BASE_URL is missing. Copy .env.example to .env and configure it.");
}

let parsedApiBaseUrl: URL;
try {
  parsedApiBaseUrl = new URL(rawApiBaseUrl);
} catch {
  throw new Error("EXPO_PUBLIC_API_BASE_URL must be an absolute HTTP(S) URL.");
}

if (!["http:", "https:"].includes(parsedApiBaseUrl.protocol)) {
  throw new Error("EXPO_PUBLIC_API_BASE_URL must use HTTP or HTTPS.");
}
if (parsedApiBaseUrl.username || parsedApiBaseUrl.password || parsedApiBaseUrl.search || parsedApiBaseUrl.hash) {
  throw new Error("EXPO_PUBLIC_API_BASE_URL must not contain credentials, a query, or a fragment.");
}
if (appEnvironment !== "development" && parsedApiBaseUrl.protocol !== "https:") {
  throw new Error("HTTPS is required outside development.");
}

export const env = {
  APP_ENV: appEnvironment,
  API_BASE_URL: rawApiBaseUrl.replace(/\/+$/, ""),
  OLA_MAPS_API_KEY: (process.env.EXPO_PUBLIC_OLA_MAPS_API_KEY ?? "").trim(),
};
