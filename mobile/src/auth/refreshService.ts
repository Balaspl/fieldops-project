
import axios from "axios";
import { env } from "../config/env";
import {
  clearSessionTokens,
  getRefreshToken,
  storeSessionTokens
} from "./session";

export interface RefreshTokenResponse {
  access_token: string;
  refresh_token?: string;
  token_type?: string;
  expires_in?: number;
}

export async function refreshAccessToken(): Promise<string> {
  const refreshToken = await getRefreshToken();

  if (!refreshToken) {
    await clearSessionTokens();
    throw new Error("Your session has expired. Please sign in again.");
  }

  try {
    // Use a standalone Axios request to avoid the normal
    // API client's authentication interceptor.
    const response = await axios.post<RefreshTokenResponse>(
      `${env.API_BASE_URL}/auth/refresh`,
      { refresh_token: refreshToken },
      {
        timeout: 20000,
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        }
      }
    );

    const result = response.data;

    if (
      typeof result.access_token !== "string" ||
      !result.access_token.trim()
    ) {
      throw new Error("The refresh response did not contain an access token.");
    }

    await storeSessionTokens({
      accessToken: result.access_token,
      refreshToken: result.refresh_token ?? refreshToken
    });

    return result.access_token;
  } catch (error: unknown) {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      await clearSessionTokens();
      throw new Error("Your session has expired. Please sign in again.");
    }

    throw error;
  }
}
