
import axios, {
  type AxiosError,
  type InternalAxiosRequestConfig,
} from "axios";

import { env } from "../config/env";

import {
  clearTokens,
  getAccessToken,
  getAccessTokenSync,
  getRefreshToken,
  storeTokens,
} from "../auth/session";

interface RetryConfig extends InternalAxiosRequestConfig {
  _foRetried?: boolean;
}

interface RefreshResponse {
  access_token?: string;
  refresh_token?: string;
}

const AUTH_PATHS = [
  "/auth/login",
  "/auth/refresh",
  "/auth/logout",
];

let refreshInFlight: Promise<string> | null = null;

export const apiClient = axios.create({
  baseURL: env.API_BASE_URL,
  timeout: 25_000,
  headers: {
    Accept: "application/json",
    "Content-Type": "application/json",
  },
});

async function refreshAccessToken(): Promise<string> {
  const refreshToken = await getRefreshToken();

  if (!refreshToken) {
    throw new Error("Your session expired. Please sign in again.");
  }

  const { data } = await axios.post<RefreshResponse>(
    `${env.API_BASE_URL}/auth/refresh`,
    {
      refresh_token: refreshToken,
    },
    {
      timeout: 15_000,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
    },
  );

  if (!data.access_token || !data.refresh_token) {
    throw new Error("The server returned an incomplete session refresh.");
  }

  await storeTokens(data.access_token, data.refresh_token);

  return data.access_token;
}

// Attach the current access token to every API request.
apiClient.interceptors.request.use(async (config) => {
  const accessToken = await getAccessToken();

  if (accessToken) {
    config.headers.set("Authorization", `Bearer ${accessToken}`);
  }

  return config;
});

// Refresh expired sessions and retry the original request once.
apiClient.interceptors.response.use(
  (response) => response,

  async (error: AxiosError) => {
    const original = error.config as RetryConfig | undefined;

    const isAuthRequest =
      original?.url &&
      AUTH_PATHS.some((path) => original.url?.includes(path));

    if (
      !original ||
      error.response?.status !== 401 ||
      original._foRetried ||
      isAuthRequest
    ) {
      return Promise.reject(error);
    }

    original._foRetried = true;

    try {
      // Reuse an active refresh request instead of sending multiple requests.
      if (!refreshInFlight) {
        refreshInFlight = refreshAccessToken().finally(() => {
          refreshInFlight = null;
        });
      }

      const accessToken = await refreshInFlight;

      original.headers.set(
        "Authorization",
        `Bearer ${accessToken}`,
      );

      return apiClient(original);
    } catch (refreshError) {
      const rejected =
        axios.isAxiosError(refreshError) &&
        [400, 401, 403].includes(
          refreshError.response?.status ?? 0,
        );

      const incomplete =
        refreshError instanceof Error &&
        /session|refresh/i.test(refreshError.message);

      if (rejected || incomplete) {
        await clearTokens().catch(() => undefined);

        try {
          const { useAuthStore } = await import("../auth/authStore");

          useAuthStore.setState({
            user: null,
            isAuthenticated: false,
            initialized: true,
            isLoading: false,
            error: null,
          });
        } catch {
          // The root route guard handles session restoration
          // if the authentication store is not loaded yet.
        }
      }

      return Promise.reject(refreshError);
    }
  },
);

export function getApiErrorMessage(
  error: unknown,
  fallback = "Something went wrong. Please try again.",
): string {
  if (axios.isAxiosError(error)) {
    const body = error.response?.data as
      | {
          detail?: unknown;
          message?: unknown;
          error?: unknown;
        }
      | undefined;

    const detail = body?.detail ?? body?.message ?? body?.error;

    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }

    if (!error.response) {
      return "Could not connect to FieldOps. Check the API URL and network.";
    }

    if (error.response.status === 401) {
      return "Your session expired. Please sign in again.";
    }

    if (error.response.status === 403) {
      return "Your account does not have access to this feature.";
    }

    if (error.response.status >= 500) {
      return "The server could not complete this request. Try again shortly.";
    }
  }

  return error instanceof Error && error.message
    ? error.message
    : fallback;
}

export { getAccessTokenSync };
