import axios, {
  type AxiosError,
  type InternalAxiosRequestConfig
} from "axios";
import * as SecureStore from "expo-secure-store";
import { env } from "../config/env";
import { getAccessToken } from "../auth/session";
import { refreshAccessToken } from "../auth/refreshService";

const ACCESS_TOKEN_KEY = "fieldops_access_token";

type RetryableRequestConfig = InternalAxiosRequestConfig & {
  _retry?: boolean;
};

const AUTH_ENDPOINTS = [
  "/auth/login",
  "/auth/refresh",
  "/auth/mfa/verify",
  "/auth/mfa/recovery"
];

const NETWORK_ERROR_CODES = new Set([
  "ERR_NETWORK",
  "ECONNABORTED",
  "ETIMEDOUT",
  "ECONNRESET",
  "EHOSTUNREACH",
  "ENETUNREACH",
  "ENOTFOUND",
  "EAI_AGAIN"
]);

function isAuthEndpoint(url?: string): boolean {
  if (!url) {
    return false;
  }

  return AUTH_ENDPOINTS.some((endpoint) => url.includes(endpoint));
}

/**
 * Identifies network failures and request timeouts.
 *
 * HTTP responses such as 401, 403, 404, 409, 429 and 500 are
 * not classified as network failures because the server responded.
 */
export function isNetworkUnavailableError(
  error: unknown
): boolean {
  let candidate: unknown = error;
  const seen = new Set<object>();

  while (
    typeof candidate === "object" &&
    candidate !== null
  ) {
    if (seen.has(candidate)) {
      return false;
    }

    seen.add(candidate);

    if (axios.isAxiosError(candidate)) {
      const axiosError: AxiosError = candidate;

      // An HTTP response is not a network-unavailable error.
      if (axiosError.response) {
        return false;
      }

      // Cancelled requests are not necessarily network failures.
      if (axiosError.code === "ERR_CANCELED") {
        return false;
      }

      if (
        axiosError.code &&
        NETWORK_ERROR_CODES.has(axiosError.code.toUpperCase())
      ) {
        return true;
      }

      // React Native Axios requests can fail without a response.
      return axiosError.request != null;
    }

    // Inspect the original error inside custom error wrappers.
    if (!("originalError" in candidate)) {
      return false;
    }

    candidate = (
      candidate as { originalError?: unknown }
    ).originalError;
  }

  return false;
}

let refreshPromise: Promise<string> | null = null;

function refreshAccessTokenOnce(): Promise<string> {
  if (!refreshPromise) {
    refreshPromise = refreshAccessToken().finally(() => {
      refreshPromise = null;
    });
  }

  return refreshPromise;
}

export const apiClient = axios.create({
  baseURL: env.API_BASE_URL,
  timeout: 20000,
  headers: {
    Accept: "application/json",
    "Content-Type": "application/json"
  }
});

apiClient.interceptors.request.use(async (config) => {
  const accessToken = await getAccessToken();

  if (accessToken) {
    config.headers.set("Authorization", `Bearer ${accessToken}`);
  }

  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest =
      error.config as RetryableRequestConfig | undefined;

    if (
      !originalRequest ||
      error.response?.status !== 401 ||
      originalRequest._retry ||
      isAuthEndpoint(originalRequest.url)
    ) {
      return Promise.reject(error);
    }

    originalRequest._retry = true;

    try {
      const newAccessToken = await refreshAccessTokenOnce();

      originalRequest.headers.set(
        "Authorization",
        `Bearer ${newAccessToken}`
      );

      return apiClient(originalRequest);
    } catch (refreshError: unknown) {
      // Preserve the existing refresh-service behavior.
      // Transient network failures must not be mistaken for proof
      // that the technician's credentials have been rejected.
      return Promise.reject(refreshError);
    }
  }
);

/**
 * Compatibility helpers for code that needs access-token-only operations.
 * Session management should normally use src/auth/session.ts.
 */
export async function saveAccessToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(ACCESS_TOKEN_KEY, token);
}

export async function clearAccessToken(): Promise<void> {
  await SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY);
}