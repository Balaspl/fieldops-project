import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api, clearSession, restoreSessionTokens, setSession, setSessionExpiredHandler, getApiErrorMessage } from '../api/client';
import type { AuthUser, StaffRole } from '../types';

type SignInResult = { mfaRequired: true; challenge: string } | { mfaRequired: false };
interface AuthContextValue {
  user: AuthUser | null;
  accessToken: string | null;
  role: StaffRole | null;
  loading: boolean;
  error: string | null;
  signIn: (email: string, password: string) => Promise<SignInResult>;
  verifyMfa: (challenge: string, code: string) => Promise<void>;
  signOut: () => Promise<void>;
  clearError: () => void;
  reloadUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function mapUser(raw: any): AuthUser {
  return {
    id: String(raw?.id ?? ''), email: String(raw?.email ?? ''),
    first_name: String(raw?.first_name ?? ''), last_name: String(raw?.last_name ?? ''),
    role: String(raw?.role ?? '').toLowerCase(), tenant_id: String(raw?.tenant_id ?? ''),
    organization_name: raw?.organization_name ?? null, is_active: raw?.is_active ?? true,
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const clearLocalSession = useCallback(async () => {
    setUser(null);
    setAccessToken(null);
    await clearSession();
  }, []);

  useEffect(() => {
    setSessionExpiredHandler(() => { void clearLocalSession(); });
    let mounted = true;
    (async () => {
      try {
        const tokens = await restoreSessionTokens();
        if (tokens.accessToken) {
          const response = await api.get('/auth/me');
          const loadedUser = mapUser(response.data);
          if (!mounted) return;
          if (!['super_admin', 'dispatcher'].includes(loadedUser.role)) {
            await clearLocalSession();
          } else {
            setUser(loadedUser);
            setAccessToken(tokens.accessToken);
          }
        }
      } catch {
        await clearLocalSession();
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; setSessionExpiredHandler(null); };
  }, [clearLocalSession]);

  const signIn = useCallback(async (email: string, password: string): Promise<SignInResult> => {
    setError(null);
    const response = await api.post('/auth/login', { email: email.trim().toLowerCase(), password });
    const data = response.data;
    if (data?.mfa_required && data?.challenge) return { mfaRequired: true, challenge: data.challenge };
    const nextUser = mapUser(data?.user);
    if (!['super_admin', 'dispatcher'].includes(nextUser.role)) {
      throw new Error('This app is for Super Admin and Dispatcher accounts only. Please use the correct FieldOps app for your role.');
    }
    if (!data?.access_token || !data?.refresh_token) throw new Error('The server did not return a valid session.');
    await setSession(data.access_token, data.refresh_token);
    setAccessToken(data.access_token);
    setUser(nextUser);
    return { mfaRequired: false };
  }, []);

  const verifyMfa = useCallback(async (challenge: string, code: string) => {
    setError(null);
    const response = await api.post('/auth/mfa/verify', { challenge, code: code.replace(/\s/g, ''), trust_device: false });
    const data = response.data;
    const nextUser = mapUser(data?.user);
    if (!['super_admin', 'dispatcher'].includes(nextUser.role)) throw new Error('This account does not have access to FieldOps Staff.');
    if (!data?.access_token || !data?.refresh_token) throw new Error('MFA verification did not return a session.');
    await setSession(data.access_token, data.refresh_token);
    setAccessToken(data.access_token);
    setUser(nextUser);
  }, []);

  const signOut = useCallback(async () => {
    try { await api.post('/auth/logout'); } catch { /* Local secure-store cleanup must still happen. */ }
    await clearLocalSession();
  }, [clearLocalSession]);

  const reloadUser = useCallback(async () => {
    const response = await api.get('/auth/me');
    setUser(mapUser(response.data));
  }, []);

  const role = user?.role === 'super_admin' || user?.role === 'dispatcher' ? user.role as StaffRole : null;
  const value = useMemo<AuthContextValue>(() => ({
    user, accessToken, role, loading, error,
    signIn: async (email, password) => {
      try { return await signIn(email, password); }
      catch (err) { const message = getApiErrorMessage(err, 'Login failed.'); setError(message); throw new Error(message); }
    },
    verifyMfa: async (challenge, code) => {
      try { await verifyMfa(challenge, code); }
      catch (err) { const message = getApiErrorMessage(err, 'MFA verification failed.'); setError(message); throw new Error(message); }
    },
    signOut, clearError: () => setError(null), reloadUser,
  }), [user, accessToken, role, loading, error, signIn, verifyMfa, signOut, reloadUser]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}
