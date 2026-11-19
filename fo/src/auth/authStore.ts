
import { create } from "zustand";
import { authApi, type TokenResponse } from "../api/auth";
import { getApiErrorMessage } from "../api/client";
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  storeTokens,
} from "./session";
import type { AuthUser } from "./roles";

interface AuthState {
  user: AuthUser | null;
  initialized: boolean;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  login: (email: string, password: string) => Promise<void>;
  restoreSession: () => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  );
}

function parseUser(value: unknown): AuthUser | null {
  if (
    !isRecord(value) ||
    !value.id ||
    !value.email ||
    !value.role
  ) {
    return null;
  }

  return value as unknown as AuthUser;
}

async function saveAndFetchProfile(
  response: TokenResponse,
): Promise<AuthUser> {
  if (!response.access_token || !response.refresh_token) {
    throw new Error(
      "The server did not return a complete sign-in session.",
    );
  }

  await storeTokens(
    response.access_token,
    response.refresh_token,
  );

  // Always use the backend profile as the source of the user's role.
  const user = parseUser(await authApi.me());

  if (!user) {
    throw new Error(
      "The backend did not return a supported user profile.",
    );
  }

  return user;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  initialized: false,
  isAuthenticated: false,
  isLoading: false,
  error: null,

  login: async (email, password) => {
    set({ isLoading: true, error: null });

    try {
      const response = await authApi.login(email, password);

      const user = await saveAndFetchProfile(response);

      set({
        user,
        isAuthenticated: true,
        initialized: true,
        isLoading: false,
        error: null,
      });
    } catch (error) {
      await clearTokens().catch(() => undefined);

      const message = getApiErrorMessage(
        error,
        "Unable to sign in.",
      );

      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: message,
      });

      throw new Error(message);
    }
  },

  restoreSession: async () => {
    set({ isLoading: true, error: null });

    try {
      const [accessToken, refreshToken] = await Promise.all([
        getAccessToken(),
        getRefreshToken(),
      ]);

      if (!accessToken || !refreshToken) {
        await clearTokens().catch(() => undefined);

        set({
          user: null,
          isAuthenticated: false,
          initialized: true,
          isLoading: false,
        });

        return;
      }

      const user = parseUser(await authApi.me());

      if (!user) {
        throw new Error(
          "The backend did not return a valid user profile.",
        );
      }

      set({
        user,
        isAuthenticated: true,
        initialized: true,
        isLoading: false,
        error: null,
      });
    } catch (error) {
      await clearTokens().catch(() => undefined);

      set({
        user: null,
        isAuthenticated: false,
        initialized: true,
        isLoading: false,
        error: getApiErrorMessage(error),
      });
    }
  },

  logout: async () => {
    set({ isLoading: true });

    try {
      await authApi.logout();
    } catch {
      // Local sign-out must still complete.
    }

    await clearTokens().catch(() => undefined);

    set({
      user: null,
      isAuthenticated: false,
      initialized: true,
      isLoading: false,
      error: null,
    });
  },

  clearError: () => set({ error: null }),
}));
