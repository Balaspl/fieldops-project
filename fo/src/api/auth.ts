
import { apiClient } from "./client";

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type?: string;
  expires_in?: number;
  user?: unknown;
}

export const authApi = {
  login: async (email: string, password: string) =>
    (
      await apiClient.post<TokenResponse>("/auth/login", {
        email: email.trim().toLowerCase(),
        password,
      })
    ).data,

  me: async () => (await apiClient.get("/auth/me")).data,

  logout: async () => apiClient.post("/auth/logout"),
};
