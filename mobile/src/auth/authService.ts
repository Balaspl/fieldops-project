
import { apiClient } from "../api/client";
import { clearSessionTokens, storeSessionTokens } from "./session";
import type {
  AuthenticatedUser,
  LoginRequest,
  LoginResponse
} from "../types/auth";

export async function login(
  credentials: LoginRequest
): Promise<LoginResponse> {
  const response = await apiClient.post<LoginResponse>(
    "/auth/login",
    credentials
  );

  const result = response.data;

  // Do not store a session until MFA has been completed.
  if (result.mfa_required) {
    return result;
  }

  if (result.access_token) {
    await storeSessionTokens({
      accessToken: result.access_token,
      refreshToken: result.refresh_token
    });
  }

  return result;
}

export async function getCurrentUser(): Promise<AuthenticatedUser> {
  const response = await apiClient.get<AuthenticatedUser>("/auth/me");
  return response.data;
}

export async function logout(): Promise<void> {
  try {
    await apiClient.post("/auth/logout");
  } finally {
    await clearSessionTokens();
  }
}
