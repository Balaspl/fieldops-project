import axios, {
  InternalAxiosRequestConfig,
  AxiosResponse,
} from "axios";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  "http://localhost:8000";

const api = axios.create({
  baseURL: API_BASE_URL,

  /*
   * Required for browser-based SSO.
   *
   * The backend stores SSO access/refresh tokens
   * in HttpOnly cookies.
   */
  withCredentials: true,

  headers: {
    "Content-Type": "application/json",
  },

  timeout: 30000,
});

// ─────────────────────────────────────────────
// Auth mode
// ─────────────────────────────────────────────
//
// "local" = email/password authentication
// "sso"   = browser SSO using HttpOnly cookies
//
// SSO tokens are NEVER read from JavaScript.
// ─────────────────────────────────────────────

type AuthMode = "local" | "sso";

const getAuthMode = (): AuthMode => {
  return localStorage.getItem("auth_mode") === "sso"
    ? "sso"
    : "local";
};

// ─────────────────────────────────────────────
// Request Interceptor
// ─────────────────────────────────────────────
//
// LOCAL LOGIN:
//   localStorage access token
//        ↓
//   Authorization: Bearer <token>
//
// SSO LOGIN:
//   HttpOnly cookie
//        ↓
//   browser automatically sends cookie
//
// JavaScript NEVER reads the SSO cookie.
// ─────────────────────────────────────────────

api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const authMode = getAuthMode();

    /*
     * Only attach a Bearer token for local authentication.
     *
     * For SSO, the browser automatically sends the
     * HttpOnly cookie because withCredentials=true.
     */
    if (authMode === "local") {
      const token =
        localStorage.getItem("access_token") ||
        localStorage.getItem("token");

      if (token && config.headers) {
        config.headers.Authorization =
          `Bearer ${token}`;
      }
    }

    return config;
  },
  (error) => Promise.reject(error)
);

// ─────────────────────────────────────────────
// Response Interceptor
// ─────────────────────────────────────────────

let isRefreshing = false;

let failedQueue: Array<{
  resolve: (value: any) => void;
  reject: (reason?: any) => void;
}> = [];

const processQueue = (
  error: any,
  token: string | null = null
) => {
  failedQueue.forEach(
    ({ resolve, reject }) => {
      if (error) {
        reject(error);
      } else {
        resolve(token);
      }
    }
  );

  failedQueue = [];
};

// ─────────────────────────────────────────────
// Response handling
// ─────────────────────────────────────────────

api.interceptors.response.use(
  (response: AxiosResponse) => response,

  async (error) => {
    const originalRequest =
      error.config;

    if (!originalRequest) {
      return Promise.reject(error);
    }

    // ─────────────────────────────────────────
    // Authentication endpoints
    // ─────────────────────────────────────────

    const isAuthEndpoint =
      originalRequest.url?.includes(
        "/auth/login"
      ) ||
      originalRequest.url?.includes(
        "/auth/refresh"
      ) ||
      originalRequest.url?.includes(
        "/auth/register"
      ) ||
      originalRequest.url?.includes(
        "/auth/sso/login"
      ) ||
      originalRequest.url?.includes(
        "/auth/sso/callback"
      );

    // ─────────────────────────────────────────
    // Only handle 401 once
    // ─────────────────────────────────────────

    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      !isAuthEndpoint
    ) {
      const authMode = getAuthMode();

      // =================================================
      // SSO MODE
      // =================================================
      //
      // SSO refresh token is HttpOnly.
      //
      // We therefore DO NOT read it from localStorage.
      //
      // Instead, ask the backend to refresh using:
      //
      //     fieldops_refresh_token
      //
      // cookie.
      // =================================================

      if (authMode === "sso") {
        if (isRefreshing) {
          return new Promise(
            (resolve, reject) => {
              failedQueue.push({
                resolve,
                reject,
              });
            }
          ).then(() => {
            return api(originalRequest);
          });
        }

        originalRequest._retry = true;
        isRefreshing = true;

        try {
          /*
           * No refresh token is placed in the request body.
           *
           * The backend reads the HttpOnly refresh cookie.
           */
          await api.post(
            "/auth/refresh",
            null,
            {
              withCredentials: true,
            }
          );

          /*
           * New access/refresh cookies have been
           * created by the backend.
           *
           * JavaScript never sees them.
           */
          processQueue(null, null);

          return api(originalRequest);
        } catch (refreshError) {
          processQueue(
            refreshError,
            null
          );

          /*
           * SSO cookies are HttpOnly.
           *
           * JavaScript cannot delete them.
           *
           * Call backend logout so the server can
           * revoke/clear the SSO session.
           */
          try {
            await axios.post(
              `${API_BASE_URL}/auth/logout`,
              null,
              {
                withCredentials: true,
              }
            );
          } catch {
            // Ignore logout failure.
          }

          localStorage.removeItem(
            "auth_mode"
          );

          localStorage.removeItem(
            "user"
          );

          localStorage.removeItem(
            "tenant_id"
          );

          window.location.href = "/";

          return Promise.reject(
            refreshError
          );
        } finally {
          isRefreshing = false;
        }
      }

      // =================================================
      // LOCAL LOGIN MODE
      // =================================================

      const refreshToken =
        localStorage.getItem(
          "refresh_token"
        );

      /*
       * No local refresh token.
       *
       * There is nothing JavaScript can refresh.
       */
      if (!refreshToken) {
        return Promise.reject(error);
      }

      if (isRefreshing) {
        return new Promise(
          (resolve, reject) => {
            failedQueue.push({
              resolve,
              reject,
            });
          }
        ).then((token) => {
          if (token) {
            originalRequest.headers.Authorization =
              `Bearer ${token}`;
          }

          return api(
            originalRequest
          );
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        /*
         * Local authentication sends the refresh token
         * explicitly in the request body.
         */
        const response =
          await axios.post(
            `${API_BASE_URL}/auth/refresh`,
            {
              refresh_token:
                refreshToken,
            },
            {
              withCredentials: true,
            }
          );

        const {
          access_token,
          refresh_token:
            newRefreshToken,
        } = response.data;

        if (!access_token) {
          throw new Error(
            "Refresh response did not contain an access token"
          );
        }

        localStorage.setItem(
          "access_token",
          access_token
        );

        if (newRefreshToken) {
          localStorage.setItem(
            "refresh_token",
            newRefreshToken
          );
        }

        processQueue(
          null,
          access_token
        );

        originalRequest.headers.Authorization =
          `Bearer ${access_token}`;

        return api(
          originalRequest
        );
      } catch (refreshError) {
        processQueue(
          refreshError,
          null
        );

        localStorage.removeItem(
          "access_token"
        );

        localStorage.removeItem(
          "refresh_token"
        );

        localStorage.removeItem(
          "user"
        );

        localStorage.removeItem(
          "tenant_id"
        );

        localStorage.removeItem(
          "auth_mode"
        );

        window.location.href = "/";

        return Promise.reject(
          refreshError
        );
      } finally {
        isRefreshing = false;
      }
    }

    // ─────────────────────────────────────────
    // Log non-401 errors
    // ─────────────────────────────────────────

    if (
      error.response?.status !== 401
    ) {
      console.error(
        "Backend API Error:",
        {
          baseURL: API_BASE_URL,
          url:
            error.config?.url,
          method:
            error.config?.method,
          status:
            error.response?.status,
          data:
            error.response?.data,
          message:
            error.message,
        }
      );
    }

    return Promise.reject(error);
  }
);

export default api;