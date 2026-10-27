
import { apiClient } from "../api/client";
import {
  clearSessionTokens,
  storeSessionTokens
} from "./session";
import type { AuthenticatedUser } from "../types/auth";

export interface MfaCodePayload {
  challenge: string;
  code: string;
  trust_device?: boolean;
}

export interface MfaRecoveryPayload {
  challenge: string;
  recovery_code: string;
}

export interface MfaVerificationResponse {
  status: string;
  mfa_required: boolean;
  challenge: string;
  replay_protected: boolean;
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: AuthenticatedUser;
  trusted_device_token?: string;
}

async function persistMfaSession(
  result: MfaVerificationResponse
): Promise<void> {
  if (
    typeof result.access_token !== "string" ||
    !result.access_token.trim() ||
    typeof result.refresh_token !== "string" ||
    !result.refresh_token.trim()
  ) {
    try {
      await clearSessionTokens();
    } catch {
      // Preserve the missing-token error if cleanup also fails.
    }

    throw new Error(
      "MFA verification did not return valid session tokens."
    );
  }

  try {
    await storeSessionTokens({
      accessToken: result.access_token,
      refreshToken: result.refresh_token
    });
  } catch (error: unknown) {
    try {
      await clearSessionTokens();
    } catch {
      // Preserve the original secure-storage error.
    }

    throw error;
  }
}

export async function verifyMfa(
  payload: MfaCodePayload
): Promise<MfaVerificationResponse> {
  if (!payload.challenge.trim()) {
    throw new Error("The MFA challenge is missing. Please sign in again.");
  }

  if (!/^\d{6}$/.test(payload.code)) {
    throw new Error("Enter a valid six-digit verification code.");
  }

  const response = await apiClient.post<MfaVerificationResponse>(
    "/auth/mfa/verify",
    payload
  );

  await persistMfaSession(response.data);

  return response.data;
}

export async function verifyMfaRecovery(
  payload: MfaRecoveryPayload
): Promise<MfaVerificationResponse> {
  if (!payload.challenge.trim()) {
    throw new Error("The MFA challenge is missing. Please sign in again.");
  }

  if (!payload.recovery_code.trim()) {
    throw new Error("Enter your recovery code.");
  }

  const response = await apiClient.post<MfaVerificationResponse>(
    "/auth/mfa/recovery",
    payload
  );

  await persistMfaSession(response.data);

  return response.data;
}
