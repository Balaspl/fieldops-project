import * as SecureStore from "expo-secure-store";

// This app deliberately has its own token namespace. All three role portals
// inside `fo` use this pair through the same API client and refresh coordinator.
const ACCESS_TOKEN_KEY = "fo.auth.access.v1";
const REFRESH_TOKEN_KEY = "fo.auth.refresh.v1";
let accessTokenCache: string | null = null;

export function getAccessTokenSync(): string | null { return accessTokenCache; }

export async function getAccessToken(): Promise<string | null> {
  accessTokenCache = await SecureStore.getItemAsync(ACCESS_TOKEN_KEY);
  return accessTokenCache;
}

export async function getRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
}

export async function storeTokens(accessToken: string, refreshToken: string): Promise<void> {
  if (!accessToken.trim() || !refreshToken.trim()) {
    throw new Error("The server did not return a complete session.");
  }
  await SecureStore.setItemAsync(ACCESS_TOKEN_KEY, accessToken);
  accessTokenCache = accessToken;
  try {
    await SecureStore.setItemAsync(REFRESH_TOKEN_KEY, refreshToken);
  } catch (error) {
    await SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY).catch(() => undefined);
    throw error;
  }
}

export async function clearTokens(): Promise<void> {
  accessTokenCache = null;
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY),
    SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY),
  ]);
}
