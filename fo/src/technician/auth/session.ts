import { clearTokens, getAccessToken, getRefreshToken, storeTokens } from "../../auth/session";

export { getAccessToken, getRefreshToken };
export async function storeSessionTokens(tokens: { accessToken: string; refreshToken?: string }): Promise<void> {
  if (!tokens.refreshToken) throw new Error("The server did not return a refresh token.");
  await storeTokens(tokens.accessToken, tokens.refreshToken);
}
export const clearSessionTokens = clearTokens;
