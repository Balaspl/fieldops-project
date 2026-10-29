import { create } from "zustand";
import { customerApi } from "../api/customer";
import { clearTokens, cacheUser, clearCachedUser, getAccessToken, getCachedUser, storeTokens } from "./session";
import { getApiErrorMessage } from "../api/client";
import type { AuthUser, LoginResponse, TokenResponse } from "../types/api";

interface AuthState {
  user: AuthUser | null;
  initialized: boolean;
  isLoading: boolean;
  mfaChallenge: string | null;
  error: string | null;
  login: (email: string, password: string) => Promise<{ mfaRequired: boolean }>;
  verifyMfa: (code: string, trustDevice: boolean) => Promise<void>;
  verifyRecovery: (recoveryCode: string) => Promise<void>;
  restoreSession: () => Promise<void>;
  logout: () => Promise<void>;
  clearError: () => void;
}

function isCustomer(user: unknown): user is AuthUser {
  if (!user || typeof user !== "object" || !("role" in user)) return false;
  const role = String((user as { role?: unknown }).role ?? "").trim().toLowerCase();
  return role === "customer";
}

function assertCustomer(response: TokenResponse): AuthUser {
  if (!isCustomer(response.user)) {
    throw new Error("This app is for customer accounts. Please sign in with a FieldOps customer account.");
  }
  if (!response.access_token || !response.refresh_token) {
    throw new Error("The server did not return a complete sign-in session.");
  }
  return response.user;
}

async function persistCustomerSession(response: TokenResponse): Promise<AuthUser> {
  const user = assertCustomer(response);
  await storeTokens(response.access_token, response.refresh_token);
  await cacheUser(user).catch(() => undefined);
  return user;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  initialized: false,
  isLoading: false,
  mfaChallenge: null,
  error: null,
  login: async (email, password) => {
    set({ isLoading: true, error: null, mfaChallenge: null });
    try {
      const response = await customerApi.login(email.trim().toLowerCase(), password) as LoginResponse;
      if ("mfa_required" in response && response.mfa_required) {
        if (!response.challenge?.trim()) throw new Error("The server required MFA but did not provide a valid challenge.");
        await clearTokens().catch(() => undefined);
        set({ mfaChallenge: response.challenge, isLoading: false });
        return { mfaRequired: true };
      }
      const user = await persistCustomerSession(response as TokenResponse);
      set({ user, initialized: true, isLoading: false, mfaChallenge: null, error: null });
      return { mfaRequired: false };
    } catch (error) {
      await clearTokens().catch(() => undefined);
      await clearCachedUser().catch(() => undefined);
      const message = getApiErrorMessage(error, "Unable to sign in.");
      set({ isLoading: false, error: message });
      throw new Error(message);
    }
  },
  verifyMfa: async (code, trustDevice) => {
    const challenge = get().mfaChallenge;
    if (!challenge) throw new Error("Your verification session has expired. Please sign in again.");
    if (!/^\d{6}$/.test(code)) throw new Error("Enter the six-digit authenticator code.");
    set({ isLoading: true, error: null });
    try {
      const response = await customerApi.verifyMfa(challenge, code, trustDevice) as TokenResponse;
      const user = await persistCustomerSession(response);
      set({ user, initialized: true, isLoading: false, mfaChallenge: null, error: null });
    } catch (error) {
      await clearTokens().catch(() => undefined);
      const message = getApiErrorMessage(error, "MFA verification failed.");
      set({ isLoading: false, error: message });
      throw new Error(message);
    }
  },
  verifyRecovery: async (recoveryCode) => {
    const challenge = get().mfaChallenge;
    if (!challenge) throw new Error("Your verification session has expired. Please sign in again.");
    if (!recoveryCode.trim()) throw new Error("Enter your recovery code.");
    set({ isLoading: true, error: null });
    try {
      const response = await customerApi.verifyRecovery(challenge, recoveryCode.trim()) as TokenResponse;
      const user = await persistCustomerSession(response);
      set({ user, initialized: true, isLoading: false, mfaChallenge: null, error: null });
    } catch (error) {
      await clearTokens().catch(() => undefined);
      const message = getApiErrorMessage(error, "Recovery-code verification failed.");
      set({ isLoading: false, error: message });
      throw new Error(message);
    }
  },
  restoreSession: async () => {
    set({ isLoading: true, error: null });
    try {
      const token = await getAccessToken();
      if (!token) {
        await clearCachedUser().catch(() => undefined);
        set({ user: null, initialized: true, isLoading: false });
        return;
      }
      const user = await customerApi.currentUser() as AuthUser;
      if (!isCustomer(user)) {
        await clearTokens();
        await clearCachedUser();
        set({ user: null, initialized: true, isLoading: false });
        return;
      }
      await cacheUser(user).catch(() => undefined);
      set({ user, initialized: true, isLoading: false, error: null });
    } catch (error) {
      const cachedUser = await getCachedUser();
      const message = getApiErrorMessage(error);
      const status = (error as { response?: { status?: number } })?.response?.status;
      const authenticationFailed = status === 401 || status === 403 || message.toLowerCase().includes("session has expired") || message.toLowerCase().includes("invalid or expired refresh token");
      // A temporary outage may retain the last customer identity for navigation, but an authentication failure must never do so.
      if (cachedUser && isCustomer(cachedUser) && !authenticationFailed) {
        set({ user: cachedUser, initialized: true, isLoading: false, error: null });
        return;
      }
      set({ user: null, initialized: true, isLoading: false, error: null });
      if (authenticationFailed) {
        await clearTokens().catch(() => undefined);
        await clearCachedUser().catch(() => undefined);
      }
    }
  },
  logout: async () => {
    try { await customerApi.logout(); } catch { /* Local session still must be cleared. */ }
    await clearTokens().catch(() => undefined);
    await clearCachedUser().catch(() => undefined);
    set({ user: null, initialized: true, isLoading: false, mfaChallenge: null, error: null });
  },
  clearError: () => set({ error: null }),
}));
