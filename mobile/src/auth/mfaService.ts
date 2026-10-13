
import { apiClient } from "../api/client";
import { storeSessionTokens } from "./session";
import type { AuthenticatedUser } from "../types/auth";

export interface MfaVerificationPayload {
  [key: string]: unknown;
}

export interface MfaVerificationResponse {
  access_token?: string;
  refresh_token?: string;
  token_type?: string;
  expires_in?: number;
  user?: AuthenticatedUser;
  mfa_required?: boolean;
  message?: string;
}

async function saveReturnedSession(
  result: MfaVerificationResponse
): Promise<void> {
  if (result.access_token) {
    await storeSessionTokens({
      accessToken: result.access_token,
      refreshToken: result.refresh_token
    });
  }
}

export async function verifyMfa(
  payload: MfaVerificationPayload
): Promise<MfaVerificationResponse> {
  const response = await apiClient.post<MfaVerificationResponse>(
    "/auth/mfa/verify",
    payload
  );

  await saveReturnedSession(response.data);
  return response.data;
}

export async function verifyMfaRecovery(
  payload: MfaVerificationPayload
): Promise<MfaVerificationResponse> {
  const response = await apiClient.post<MfaVerificationResponse>(
    "/auth/mfa/recovery",
    payload
  );

  await saveReturnedSession(response.data);
  return response.data;
}
