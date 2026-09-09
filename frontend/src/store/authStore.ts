/**
 * Authentication store (Zustand).
 *
 * Manages user authentication state, JWT tokens, and login/logout flows.
 * Token refresh is handled automatically by the API interceptor.
 */

import { create } from "zustand";
import api from "../services/api";

export interface AuthUser {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: "super_admin" | "admin" | "dispatcher" | "technician" | "customer";
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
  login: (email: string, password: string) => Promise<void>;
  register: (data: RegisterData) => Promise<void>;
  logout: () => Promise<void>;
  refreshTokens: () => Promise<boolean>;
  loadFromStorage: () => void;
  authenticateWithTokens: (
    accessToken: string,
    refreshToken: string,
    user: AuthUser,
  ) => void;
  clearError: () => void;
  updateUser: (updatedFields: Partial<AuthUser>) => void;
}

interface RegisterData {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  role?: string;
  tenant_id: string;
}

const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  accessToken: null,
  refreshToken: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,

  login: async (email: string, password: string) => {
    set({ isLoading: true, error: null });
    try {
      const response = await api.post("/auth/login", { email, password });
      const { access_token, refresh_token, user } = response.data;

      // Store tokens
      localStorage.setItem("access_token", access_token);
      localStorage.setItem("refresh_token", refresh_token);
      localStorage.setItem("tenant_id", user.tenant_id);
      localStorage.setItem("user", JSON.stringify(user));

      set({
        user,
        accessToken: access_token,
        refreshToken: refresh_token,
        isAuthenticated: true,
        isLoading: false,
        error: null,
      });
    } catch (err: any) {
      const detail = err.response?.data?.detail || err.response?.data?.message;
      const message =
        typeof detail === "string"
          ? detail
          : detail
            ? JSON.stringify(detail)
            : "Login failed. Please verify credentials or connection.";
      set({ isLoading: false, error: message, isAuthenticated: false });
      throw new Error(message);
    }
  },
  authenticateWithTokens: (
    accessToken: string,
    refreshToken: string,
    user: AuthUser,
  ) => {
    localStorage.setItem("access_token", accessToken);
    localStorage.setItem("refresh_token", refreshToken);
    localStorage.setItem("tenant_id", user.tenant_id);
    localStorage.setItem("user", JSON.stringify(user));

    set({
      user,
      accessToken,
      refreshToken,
      isAuthenticated: true,
      isLoading: false,
      error: null,
    });
  },

  register: async (data: RegisterData) => {
    set({ isLoading: true, error: null });
    try {
      const response = await api.post("/auth/register", data);
      const { access_token, refresh_token, user } = response.data;

      localStorage.setItem("access_token", access_token);
      localStorage.setItem("refresh_token", refresh_token);
      localStorage.setItem("tenant_id", user.tenant_id);
      localStorage.setItem("user", JSON.stringify(user));

      set({
        user,
        accessToken: access_token,
        refreshToken: refresh_token,
        isAuthenticated: true,
        isLoading: false,
        error: null,
      });
    } catch (err: any) {
      const message = err.response?.data?.detail || "Registration failed.";
      set({ isLoading: false, error: message });
      throw new Error(message);
    }
  },

  logout: async () => {
    try {
      await api.post("/auth/logout");
    } catch {
      // Logout even if the API call fails
    }

    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("tenant_id");
    localStorage.removeItem("user");
    localStorage.removeItem("token");

    set({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      error: null,
    });
  },

  refreshTokens: async () => {
    const refreshToken = localStorage.getItem("refresh_token");
    if (!refreshToken) return false;

    try {
      const response = await api.post("/auth/refresh", {
        refresh_token: refreshToken,
      });
      const { access_token, refresh_token: newRefresh, user } = response.data;

      localStorage.setItem("access_token", access_token);
      localStorage.setItem("refresh_token", newRefresh);

      set({
        accessToken: access_token,
        refreshToken: newRefresh,
        user,
        isAuthenticated: true,
      });
      return true;
    } catch {
      // Refresh failed — force logout
      get().logout();
      return false;
    }
  },

  loadFromStorage: () => {
    const accessToken = localStorage.getItem("access_token");
    const refreshToken = localStorage.getItem("refresh_token");
    const userStr = localStorage.getItem("user");

    if (accessToken && userStr) {
      try {
        const user = JSON.parse(userStr);
        set({
          user,
          accessToken,
          refreshToken,
          isAuthenticated: true,
        });
      } catch {
        set({ isAuthenticated: false });
      }
    }
  },

  clearError: () => set({ error: null }),

  updateUser: (updatedFields: Partial<AuthUser>) => {
    const currentUser = get().user;
    if (!currentUser) return;

    const updatedUser = { ...currentUser, ...updatedFields };
    localStorage.setItem("user", JSON.stringify(updatedUser));
    set({ user: updatedUser });
  },
}));

export default useAuthStore;
