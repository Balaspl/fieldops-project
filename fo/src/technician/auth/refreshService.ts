import axios from "axios";
import { env } from "../config/env";
import { getRefreshToken, storeSessionTokens } from "./session";

export async function refreshAccessToken(): Promise<string> {
  const refreshToken = await getRefreshToken();
  if (!refreshToken) throw new Error("Your session expired. Please sign in again.");
  const { data } = await axios.post(`${env.API_BASE_URL}/auth/refresh`, { refresh_token: refreshToken });
  if (!data.access_token || !data.refresh_token) throw new Error("The server returned an incomplete session refresh.");
  await storeSessionTokens({ accessToken: data.access_token, refreshToken: data.refresh_token });
  return data.access_token;
}
