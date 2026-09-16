
/**
 * Authentication store (Zustand).
 *
 * Supports:
 * - Normal email/password JWT authentication
 * - Browser-based Enterprise SSO/OIDC authentication
 * - HttpOnly SSO access cookie
 * - Existing localStorage JWT authentication
 * - Token refresh handled by the API interceptor
 */

import { create } from "zustand";
import api from "../services/api";

export interface AuthUser {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role:
    | "super_admin"
    | "admin"
    | "dispatcher"
    | "technician"
    | "customer";
  tenant_id: string;
  organization_name: string | null;
}

interface AuthState {
  user: AuthUser | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  // Actions
  login: (
    email: string,
    password: string
  ) => Promise<void>;

  register: (
    data: RegisterData
  ) => Promise<void>;

  logout: () => Promise<void>;

  refreshTokens: () => Promise<boolean>;

  /*
   * Loads an existing localStorage session.
   */
  loadFromStorage: () => void;

  /*
   * Loads the authenticated user from the backend.
   *
   * Used mainly for SSO because the access token
   * is stored inside an HttpOnly cookie and cannot
   * be accessed by JavaScript.
   */
  loadFromSession: () => Promise<boolean>;

  authenticateWithTokens: (
    accessToken: string,
    refreshToken: string,
    user: AuthUser
  ) => void;

  clearError: () => void;

  updateUser: (
    updatedFields: Partial<AuthUser>
  ) => void;
}

interface RegisterData {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  role?: string;
  tenant_id: string;
}

const useAuthStore = create<AuthState>(
  (set, get) => ({
    user: null,
    accessToken: null,
    refreshToken: null,
    isAuthenticated: false,
    isLoading: false,
    error: null,

    // ─────────────────────────────────────────────
    // Normal Email / Password Login
    // ─────────────────────────────────────────────

    login: async (
      email: string,
      password: string
    ) => {
      set({
        isLoading: true,
        error: null,
      });

      try {
        const response = await api.post(
          "/auth/login",
          {
            email,
            password,
          }
        );

        const {
          access_token,
          refresh_token,
          user,
        } = response.data;

        // Store normal JWT session
        localStorage.setItem(
          "access_token",
          access_token
        );

        localStorage.setItem(
          "refresh_token",
          refresh_token
        );

        localStorage.setItem(
          "tenant_id",
          user.tenant_id
        );

        localStorage.setItem(
          "user",
          JSON.stringify(user)
        );

        set({
          user,
          accessToken: access_token,
          refreshToken: refresh_token,
          isAuthenticated: true,
          isLoading: false,
          error: null,
        });
      } catch (err: any) {
        const detail =
          err.response?.data?.detail ||
          err.response?.data?.message;

        const message =
          typeof detail === "string"
            ? detail
            : detail
              ? JSON.stringify(detail)
              : "Login failed. Please verify credentials or connection.";

        set({
          isLoading: false,
          error: message,
          isAuthenticated: false,
        });

        throw new Error(message);
      }
    },

    // ─────────────────────────────────────────────
    // Authenticate using JWT tokens
    //
    // Kept for existing authentication flows.
    // ─────────────────────────────────────────────

    authenticateWithTokens: (
      accessToken: string,
      refreshToken: string,
      user: AuthUser
    ) => {
      localStorage.setItem(
        "access_token",
        accessToken
      );

      localStorage.setItem(
        "refresh_token",
        refreshToken
      );

      localStorage.setItem(
        "tenant_id",
        user.tenant_id
      );

      localStorage.setItem(
        "user",
        JSON.stringify(user)
      );

      set({
        user,
        accessToken,
        refreshToken,
        isAuthenticated: true,
        isLoading: false,
        error: null,
      });
    },

    // ─────────────────────────────────────────────
    // Enterprise SSO / HttpOnly Cookie Session
    // ─────────────────────────────────────────────
    //
    // The SSO access token is stored in an HttpOnly
    // cookie by the backend.
    //
    // JavaScript CANNOT read that cookie.
    //
    // Instead:
    //
    //   Browser
    //      ↓
    //   GET /auth/me
    //      ↓
    //   HttpOnly cookie automatically sent
    //      ↓
    //   Backend validates JWT
    //      ↓
    //   Authenticated user returned
    //
    // ─────────────────────────────────────────────

    loadFromSession: async () => {
      set({
        isLoading: true,
        error: null,
      });

      try {
        const response =
          await api.get("/auth/me");

        /*
         * Depending on your backend response,
         * the user may be returned directly or
         * inside a "user" property.
         */
        const user: AuthUser =
          response.data?.user ||
          response.data;

        if (!user || !user.id) {
          throw new Error(
            "Invalid authenticated user response."
          );
        }

        /*
         * Keep useful user information locally.
         *
         * We intentionally DO NOT store the
         * HttpOnly access token.
         */
        localStorage.setItem(
          "tenant_id",
          user.tenant_id
        );

        localStorage.setItem(
          "user",
          JSON.stringify(user)
        );

        set({
          user,
          /*
           * The access token is intentionally null
           * for an HttpOnly-cookie SSO session.
           */
          accessToken: null,
          refreshToken:
            localStorage.getItem(
              "refresh_token"
            ),
          isAuthenticated: true,
          isLoading: false,
          error: null,
        });

        return true;
      } catch (err: any) {
        /*
         * /auth/me failed.
         *
         * This means there is no valid browser
         * session available.
         */
        set({
          isLoading: false,
          isAuthenticated: false,
        });

        return false;
      }
    },

    // ─────────────────────────────────────────────
    // Registration
    // ─────────────────────────────────────────────

    register: async (
      data: RegisterData
    ) => {
      set({
        isLoading: true,
        error: null,
      });

      try {
        const response =
          await api.post(
            "/auth/register",
            data
          );

        const {
          access_token,
          refresh_token,
          user,
        } = response.data;

        localStorage.setItem(
          "access_token",
          access_token
        );

        localStorage.setItem(
          "refresh_token",
          refresh_token
        );

        localStorage.setItem(
          "tenant_id",
          user.tenant_id
        );

        localStorage.setItem(
          "user",
          JSON.stringify(user)
        );

        set({
          user,
          accessToken: access_token,
          refreshToken: refresh_token,
          isAuthenticated: true,
          isLoading: false,
          error: null,
        });
      } catch (err: any) {
        const message =
          err.response?.data?.detail ||
          "Registration failed.";

        set({
          isLoading: false,
          error: message,
        });

        throw new Error(message);
      }
    },

    // ─────────────────────────────────────────────
    // Logout
    // ─────────────────────────────────────────────

    logout: async () => {
      try {
        /*
         * Backend logout should:
         *
         * 1. Revoke refresh tokens
         * 2. Blacklist access token where applicable
         * 3. Clear the HttpOnly SSO cookie
         *
         * withCredentials is already enabled
         * in api.ts.
         */
        await api.post("/auth/logout");
      } catch {
        // Continue local logout even if API fails
      }

      localStorage.removeItem(
        "access_token"
      );

      localStorage.removeItem(
        "refresh_token"
      );

      localStorage.removeItem(
        "tenant_id"
      );

      localStorage.removeItem(
        "user"
      );

      localStorage.removeItem(
        "token"
      );

      set({
        user: null,
        accessToken: null,
        refreshToken: null,
        isAuthenticated: false,
        error: null,
      });
    },

    // ─────────────────────────────────────────────
    // Refresh JWT Tokens
    // ─────────────────────────────────────────────

    refreshTokens: async () => {
      const refreshToken =
        localStorage.getItem(
          "refresh_token"
        );

      /*
       * SSO does not expose its HttpOnly access
       * cookie to JavaScript.
       *
       * If there is no local refresh token,
       * don't attempt local JWT refresh.
       */
      if (!refreshToken) {
        return false;
      }

      try {
        const response =
          await api.post(
            "/auth/refresh",
            {
              refresh_token:
                refreshToken,
            }
          );

        const {
          access_token,
          refresh_token:
            newRefresh,
          user,
        } = response.data;

        localStorage.setItem(
          "access_token",
          access_token
        );

        if (newRefresh) {
          localStorage.setItem(
            "refresh_token",
            newRefresh
          );
        }

        if (user) {
          localStorage.setItem(
            "user",
            JSON.stringify(user)
          );

          localStorage.setItem(
            "tenant_id",
            user.tenant_id
          );
        }

        set({
          accessToken: access_token,
          refreshToken:
            newRefresh || refreshToken,
          user:
            user || get().user,
          isAuthenticated: true,
        });

        return true;
      } catch {
        /*
         * Refresh failed.
         */
        await get().logout();

        return false;
      }
    },

    // ─────────────────────────────────────────────
    // Load Existing LocalStorage Session
    // ─────────────────────────────────────────────

    loadFromStorage: () => {
      const accessToken =
        localStorage.getItem(
          "access_token"
        );

      const refreshToken =
        localStorage.getItem(
          "refresh_token"
        );

      const userStr =
        localStorage.getItem("user");

      if (
        accessToken &&
        userStr
      ) {
        try {
          const user =
            JSON.parse(
              userStr
            );

          set({
            user,
            accessToken,
            refreshToken,
            isAuthenticated: true,
          });
        } catch {
          /*
           * Invalid localStorage user.
           */
          localStorage.removeItem(
            "user"
          );

          set({
            user: null,
            accessToken: null,
            refreshToken: null,
            isAuthenticated: false,
          });
        }
      }
    },

    // ─────────────────────────────────────────────
    // Error Handling
    // ─────────────────────────────────────────────

    clearError: () =>
      set({
        error: null,
      }),

    // ─────────────────────────────────────────────
    // Update User
    // ─────────────────────────────────────────────

    updateUser: (
      updatedFields: Partial<AuthUser>
    ) => {
      const currentUser =
        get().user;

      if (!currentUser) {
        return;
      }

      const updatedUser = {
        ...currentUser,
        ...updatedFields,
      };

      localStorage.setItem(
        "user",
        JSON.stringify(updatedUser)
      );

      set({
        user: updatedUser,
      });
    },
  })
);

export default useAuthStore;

