import { create } from "zustand";
import * as SecureStore from "expo-secure-store";
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

const CACHED_TECHNICIAN_KEY =
  "fieldops:auth:cached-technician:v1";

interface AuthStore {
  user: AuthenticatedUser | null;
  mfaChallenge: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  login: (credentials: LoginRequest) => Promise<LoginResponse>;
  restoreSession: () => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
  clearMfaChallenge: () => void;
}

interface OfflineCheckError {
  response?: {
    status?: unknown;
  } | null;
  code?: unknown;
  request?: unknown;
  isAxiosError?: unknown;
  message?: unknown;
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "An unexpected error occurred.";
}

function isTechnicianUser(
  value: unknown
): value is AuthenticatedUser {
  if (
    typeof value !== "object" ||
    value === null ||
    !("role" in value)
  ) {
    return false;
  }

  const role = (value as { role?: unknown }).role;

  return (
    typeof role === "string" &&
    role.trim().toLowerCase() === "technician"
  );
}

function isTransientRestoreError(
  error: unknown
): boolean {
  if (typeof error !== "object" || error === null) {
    return false;
  }

  const candidate = error as OfflineCheckError;

  if (candidate.response) {
    const status = candidate.response.status;

    if (typeof status !== "number") {
      return false;
    }

    return (
      status === 408 ||
      status === 425 ||
      status === 429 ||
      status >= 500
    );
  }

  const code =
    typeof candidate.code === "string"
      ? candidate.code.toUpperCase()
      : "";

  const networkErrorCodes = [
    "ERR_NETWORK",
    "ECONNABORTED",
    "ETIMEDOUT",
    "ECONNRESET",
    "EHOSTUNREACH",
    "ENETUNREACH",
    "ENOTFOUND",
    "EAI_AGAIN"
  ];

  if (networkErrorCodes.includes(code)) {
    return true;
  }

  const message =
    typeof candidate.message === "string"
      ? candidate.message
      : "";

  if (
    /network error|network request failed|failed to fetch|timeout of \d+ms exceeded|timed out/i.test(
      message
    )
  ) {
    return true;
  }

  return (
    candidate.isAxiosError === true &&
    candidate.response == null &&
    candidate.request != null
  );
}

async function saveCachedTechnician(
  user: AuthenticatedUser
): Promise<void> {
  try {
    if (!isTechnicianUser(user)) {
      return;
    }

    await SecureStore.setItemAsync(
      CACHED_TECHNICIAN_KEY,
      JSON.stringify(user)
    );
  } catch {
    // Authentication must not fail because profile caching failed.
  }
}

async function readCachedTechnician():
  Promise<AuthenticatedUser | null> {
  try {
    const storedUser = await SecureStore.getItemAsync(
      CACHED_TECHNICIAN_KEY
    );

    if (!storedUser) {
      return null;
    }

    const parsedUser: unknown = JSON.parse(storedUser);

    return isTechnicianUser(parsedUser)
      ? parsedUser
      : null;
  } catch {
    return null;
  }
}

async function clearCachedTechnician(): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(
      CACHED_TECHNICIAN_KEY
    );
  } catch {
    // Preserve the original authentication result or error.
  }
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  mfaChallenge: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,

  login: async (credentials) => {
    set({
      isLoading: true,
      error: null,
      mfaChallenge: null
    });

    try {
      const result = await loginService(credentials);

      if (result.mfa_required) {
        await clearSessionTokens();

        if (
          typeof result.challenge !== "string" ||
          !result.challenge.trim()
        ) {
          throw new Error(
            "The backend required MFA but did not return a valid challenge."
          );
        }

        set({
          user: null,
          mfaChallenge: result.challenge,
          isAuthenticated: false,
          isLoading: false,
          error: null
        });

        return result;
      }

      if (
        typeof result.access_token !== "string" ||
        !result.access_token.trim()
      ) {
        throw new Error(
          "Login did not return an access token. Please complete authentication and try again."
        );
      }

      const user = result.user ?? await getCurrentUser();

      if (!isTechnicianUser(user)) {
        await clearSessionTokens();
        await clearCachedTechnician();

        throw new Error(
          "This mobile application is for technician accounts."
        );
      }

      await saveCachedTechnician(user);

      set({
        user,
        mfaChallenge: null,
        isAuthenticated: true,
        isLoading: false,
        error: null
      });

      return result;
    } catch (error: unknown) {
      try {
        await clearSessionTokens();
      } catch {
        // Preserve the original login error if cleanup fails.
      }

      set({
        user: null,
        mfaChallenge: null,
        isAuthenticated: false,
        isLoading: false,
        error: getErrorMessage(error)
      });

      throw error;
    }
  },

  restoreSession: async () => {
    set({
      isLoading: true,
      error: null
    });

    let restoreTimeout: ReturnType<typeof setTimeout> | undefined;

    try {
      const user = await Promise.race([
        getCurrentUser(),
        new Promise<never>((_, reject) => {
          restoreTimeout = setTimeout(() => {
            const timeoutError = Object.assign(
              new Error("Session restoration timed out."),
              { code: "ECONNABORTED" }
            );

            reject(timeoutError);
          }, 8000);
        })
      ]);

      if (!isTechnicianUser(user)) {
        await clearSessionTokens();
        await clearCachedTechnician();

        throw new Error(
          "This mobile application is for technician accounts."
        );
      }

      await saveCachedTechnician(user);

      set({
        user,
        mfaChallenge: null,
        isAuthenticated: true,
        isLoading: false,
        error: null
      });
    } catch (error: unknown) {
      if (isTransientRestoreError(error)) {
        const cachedUser = await readCachedTechnician();

        if (cachedUser) {
          set({
            user: cachedUser,
            mfaChallenge: null,
            isAuthenticated: true,
            isLoading: false,
            error: null
          });

          return;
        }
      }

      await clearCachedTechnician();

      set({
        user: null,
        mfaChallenge: null,
        isAuthenticated: false,
        isLoading: false,
        error: getErrorMessage(error)
      });
    } finally {
      if (restoreTimeout !== undefined) {
        clearTimeout(restoreTimeout);
      }
    }
  },

  logout: async () => {
    set({
      isLoading: true,
      error: null
    });

    try {
      await logoutService();
    } finally {
      await clearCachedTechnician();

      set({
        user: null,
        mfaChallenge: null,
        isAuthenticated: false,
        isLoading: false,
        error: null
      });
    }
  },

  clearError: () => set({ error: null }),

  clearMfaChallenge: () => set({ mfaChallenge: null })
}));