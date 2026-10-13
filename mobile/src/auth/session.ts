
import * as SecureStore from "expo-secure-store";

const ACCESS_TOKEN_KEY = "fieldops_access_token";
const REFRESH_TOKEN_KEY = "fieldops_refresh_token";

export interface SessionTokens {
  accessToken: string;
  refreshToken?: string;
}

export async function storeSessionTokens(
  tokens: SessionTokens
): Promise<void> {
  const accessToken = tokens.accessToken.trim();

  if (!accessToken) {
    throw new Error("An access token is required.");
  }

  await SecureStore.setItemAsync(ACCESS_TOKEN_KEY, accessToken);

  if (tokens.refreshToken?.trim()) {
    await SecureStore.setItemAsync(
      REFRESH_TOKEN_KEY,
      tokens.refreshToken.trim()
    );
  } else {
    await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY);
  }
}

export async function getAccessToken(): Promise<string | null> {
  return SecureStore.getItemAsync(ACCESS_TOKEN_KEY);
}

export async function getRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
}

export async function clearSessionTokens(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY),
    SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY)
  ]);
}
