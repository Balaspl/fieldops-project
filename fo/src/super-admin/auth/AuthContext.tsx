
import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { useAuthStore } from "../../auth/authStore";
import { getAccessTokenSync } from "../../auth/session";
import { normalizeRole } from "../../auth/roles";

interface AuthValue {
  user: any;
  accessToken: string | null;
  role: "super_admin" | "dispatcher" | null;
  loading: boolean;
  error: string | null;

  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  clearError: () => void;
  reloadUser: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

function AuthBridge({ children }: { children: React.ReactNode }) {
  const state = useAuthStore();

  const [accessToken, setAccessToken] = useState<string | null>(
    getAccessTokenSync(),
  );

  useEffect(() => {
    const timer = setInterval(() => {
      setAccessToken(getAccessTokenSync());
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  const role =
    state.user?.role === "dispatcher"
      ? "dispatcher"
      : normalizeRole(state.user?.role) === "super_admin"
        ? "super_admin"
        : null;

  const value = useMemo<AuthValue>(
    () => ({
      user: state.user,
      accessToken,
      role,
      loading: !state.initialized || state.isLoading,
      error: state.error,

      signIn: async (email, password) => {
        await state.login(email, password);
      },

      signOut: state.logout,
      clearError: state.clearError,
      reloadUser: state.restoreSession,
    }),
    [state, accessToken, role],
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function AuthProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AuthBridge>{children}</AuthBridge>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);

  if (!value) {
    throw new Error(
      "useAuth must be used inside the unified FieldOps app.",
    );
  }

  return value;
}
