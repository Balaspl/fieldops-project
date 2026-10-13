
import { create } from "zustand";
import { clearSessionTokens } from "./session";
import type {
  AuthenticatedUser,
  LoginRequest,
  LoginResponse
} from "../types/auth";
import {
  getCurrentUser,
  login as loginService,
  logout as logoutService
} from "./authService";

interface AuthStore {
  user: AuthenticatedUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  login: (credentials: LoginRequest) => Promise<LoginResponse>;
  restoreSession: () => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "An unexpected error occurred.";
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,

  login: async (credentials) => {
    set({ isLoading: true, error: null });

    try {
      const result = await loginService(credentials);

      if (result.mfa_required) {
        await clearSessionTokens();

        set({
          user: null,
          isAuthenticated: false,
          isLoading: false
        });

        return result;
      }

      if (!result.access_token && !result.user) {
        throw new Error(
          "The login response did not contain the expected session data."
        );
      }

      const user = result.user ?? await getCurrentUser();

      set({
        user,
        isAuthenticated: true,
        isLoading: false,
        error: null
      });

      return result;
    } catch (error: unknown) {
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: getErrorMessage(error)
      });

      throw error;
    }
  },

  restoreSession: async () => {
    set({ isLoading: true, error: null });

    try {
      const user = await getCurrentUser();

      set({
        user,
        isAuthenticated: true,
        isLoading: false,
        error: null
      });
    } catch {
      try {
        await clearSessionTokens();
      } catch {
        // Keep the app usable if secure-storage cleanup fails.
      }

      set({
        user: null,
        isAuthenticated: false,
        isLoading: false
      });
    }
  },

  logout: async () => {
    set({ isLoading: true, error: null });

    try {
      await logoutService();
    } finally {
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: null
      });
    }
  },

  clearError: () => set({ error: null })
}));
