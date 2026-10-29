import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";
import { env } from "../config/env";
import { clearTokens, getAccessToken, getRefreshToken, storeTokens } from "../auth/session";

interface RetryConfig extends InternalAxiosRequestConfig { _customerRetry?: boolean }
interface RefreshResponse { access_token?: string; refresh_token?: string; token_type?: string }

const AUTH_PATHS = ["/auth/login", "/auth/refresh", "/auth/mfa/verify", "/auth/mfa/recovery"];
let refreshInFlight: Promise<string> | null = null;

export const apiClient = axios.create({
  baseURL: env.API_BASE_URL,
  timeout: 25000,
  headers: { Accept: "application/json", "Content-Type": "application/json" },
});

function isAuthRequest(url?: string): boolean {
  return Boolean(url && AUTH_PATHS.some((path) => url.includes(path)));
}

async function refreshAccessToken(): Promise<string> {
  const refreshToken = await getRefreshToken();
  if (!refreshToken) throw new Error("Your session has expired. Please sign in again.");
  const response = await axios.post<RefreshResponse>(
    `${env.API_BASE_URL}/auth/refresh`,
    { refresh_token: refreshToken },
    { timeout: 15000, headers: { Accept: "application/json", "Content-Type": "application/json" } },
  );
  const access = response.data.access_token;
  const refresh = response.data.refresh_token;
  if (!access || !refresh) throw new Error("The session refresh response was incomplete.");
  await storeTokens(access, refresh);
  return access;
}

apiClient.interceptors.request.use(async (config) => {
  const accessToken = await getAccessToken();
  if (accessToken) config.headers.set("Authorization", `Bearer ${accessToken}`);
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetryConfig | undefined;
    if (!original || error.response?.status !== 401 || original._customerRetry || isAuthRequest(original.url)) {
      return Promise.reject(error);
    }
    original._customerRetry = true;
    try {
      if (!refreshInFlight) {
        refreshInFlight = refreshAccessToken().finally(() => { refreshInFlight = null; });
      }
      const accessToken = await refreshInFlight;
      original.headers.set("Authorization", `Bearer ${accessToken}`);
      return apiClient(original);
    } catch (refreshError) {
      await clearTokens().catch(() => undefined);
      return Promise.reject(refreshError);
    }
  },
);

export function getApiErrorMessage(error: unknown, fallback = "Something went wrong. Please try again."): string {
  if (axios.isAxiosError(error)) {
    const data = error.response?.data as { detail?: unknown; message?: unknown; error?: unknown } | undefined;
    const detail = data?.detail ?? data?.message ?? data?.error;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      const joined = detail.map((item) => typeof item === "object" && item !== null && "msg" in item ? String(item.msg) : String(item)).join(" ");
      if (joined) return joined;
    }
    if (!error.response) return "Could not connect to the FieldOps server. Check the API URL and network connection.";
    if (error.response.status === 401) return "Your session has expired. Please sign in again.";
    if (error.response.status === 403) return "You do not have permission to perform this action.";
    if (error.response.status >= 500) return "The server could not complete this request. Please try again shortly.";
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}
