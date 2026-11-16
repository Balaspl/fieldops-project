import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import * as SecureStore from 'expo-secure-store';

const API_BASE_URL = (process.env.EXPO_PUBLIC_API_BASE_URL || 'http://10.0.2.2:8000').replace(/\/$/, '');

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
});

let accessToken: string | null = null;
let refreshToken: string | null = null;
let refreshPromise: Promise<string | null> | null = null;
let onSessionExpired: (() => void) | null = null;

export const setSession = async (access: string | null, refresh: string | null) => {
  accessToken = access;
  refreshToken = refresh;
  if (access) await SecureStore.setItemAsync('fieldops_access_token', access);
  else await SecureStore.deleteItemAsync('fieldops_access_token');
  if (refresh) await SecureStore.setItemAsync('fieldops_refresh_token', refresh);
  else await SecureStore.deleteItemAsync('fieldops_refresh_token');
};

export const restoreSessionTokens = async () => {
  const [access, refresh] = await Promise.all([
    SecureStore.getItemAsync('fieldops_access_token'),
    SecureStore.getItemAsync('fieldops_refresh_token'),
  ]);
  accessToken = access;
  refreshToken = refresh;
  return { accessToken: access, refreshToken: refresh };
};

export const clearSession = async () => setSession(null, null);
export const setSessionExpiredHandler = (handler: (() => void) | null) => {
  onSessionExpired = handler;
};
export const getAccessToken = () => accessToken;
export const getApiBaseUrl = () => API_BASE_URL;

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`;
  // The API derives tenant scope from the verified JWT. Never inject X-Tenant-ID
  // from local UI state into normal staff requests.
  return config;
});

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshToken) return null;
  if (!refreshPromise) {
    refreshPromise = axios.post(`${API_BASE_URL}/auth/refresh`, { refresh_token: refreshToken }, {
      timeout: 30000,
      headers: { 'Content-Type': 'application/json' },
    }).then(async (response) => {
      const nextAccess = response.data?.access_token;
      const nextRefresh = response.data?.refresh_token || refreshToken;
      if (!nextAccess) throw new Error('Refresh response did not contain an access token.');
      await setSession(nextAccess, nextRefresh);
      return nextAccess as string;
    }).catch(async () => {
      await clearSession();
      onSessionExpired?.();
      return null;
    }).finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

api.interceptors.response.use(
  response => response,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _fieldOpsRetried?: boolean }) | undefined;
    if (error.response?.status === 401 && original && !original._fieldOpsRetried && !String(original.url || '').includes('/auth/')) {
      original._fieldOpsRetried = true;
      const token = await refreshAccessToken();
      if (token) {
        original.headers.Authorization = `Bearer ${token}`;
        return api(original);
      }
    }
    return Promise.reject(error);
  },
);

export function getApiErrorMessage(error: unknown, fallback = 'Something went wrong. Please try again.') {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail || error.response?.data?.message || error.message;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map((item: any) => item.msg || String(item)).join('\n');
    if (detail && typeof detail === 'object') return JSON.stringify(detail);
  }
  return error instanceof Error ? error.message : fallback;
}
