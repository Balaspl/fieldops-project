
import axios from "axios";
import { env } from "../config/env";
import { logEvent } from "../observability/logger";
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
    logEvent("auth.refresh_missing_token", {
      reason: "no_refresh_token_stored"
    });

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
      !result.access_token.trim() ||
      typeof result.refresh_token !== "string" ||
      !result.refresh_token.trim()
    ) {
      try {
        await clearSessionTokens();
      } catch {
        // Preserve the invalid-response error if cleanup fails.
      }

      throw new Error(
        "The refresh response did not contain valid access and refresh tokens."
      );
    }

    await storeSessionTokens({
      accessToken: result.access_token,
      refreshToken: result.refresh_token
    });

    return result.access_token;
  } catch (error: unknown) {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      logEvent("auth.refresh_rejected", {
        status: 401
      });

      await clearSessionTokens();
      throw new Error("Your session has expired. Please sign in again.");
    }

    throw error;
  }
}
