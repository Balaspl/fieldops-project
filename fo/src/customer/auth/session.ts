import * as SecureStore from "expo-secure-store";
import type { AuthUser } from "../types/api";

const ACCESS_TOKEN_KEY = "fieldops.customer.access-token.v1";
const REFRESH_TOKEN_KEY = "fieldops.customer.refresh-token.v1";
const USER_CACHE_KEY = "fieldops.customer.user-cache.v1";

export async function getAccessToken(): Promise<string | null> {
  return SecureStore.getItemAsync(ACCESS_TOKEN_KEY);
}

export async function getRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
}

export async function storeTokens(accessToken: string, refreshToken: string): Promise<void> {
  if (!accessToken.trim() || !refreshToken.trim()) {
    throw new Error("The server did not return valid session tokens.");
  }
  await SecureStore.setItemAsync(ACCESS_TOKEN_KEY, accessToken);
  try {
    await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, refreshToken);
  } catch (error) {
    await SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY).catch(() => undefined);
    throw error;
  }
}

export async function clearTokens(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY),
    SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY),
  ]);
}

export async function cacheUser(user: AuthUser): Promise<void> {
  await SecureStore.setItemAsync(USER_CACHE_KEY, JSON.stringify(user));
}

export async function getCachedUser(): Promise<AuthUser | null> {
  try {
    const raw = await SecureStore.getItemAsync(USER_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AuthUser;
    if (parsed && typeof parsed.email === "string" && typeof parsed.role === "string") return parsed;
    return null;
  } catch {
    return null;
  }
}

export async function clearCachedUser(): Promise<void> {
  await SecureStore.deleteItemAsync(USER_CACHE_KEY);
}
