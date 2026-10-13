
export interface AuthenticatedUser {
  id: string | number;
  email: string;
  role: string;
  full_name?: string;
  tenant_id?: string | number;
}

export interface AuthTokens {
  access_token: string;
  refresh_token?: string;
  token_type?: string;
  expires_in?: number;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token?: string;
  refresh_token?: string;
  token_type?: string;
  expires_in?: number;
  user?: AuthenticatedUser;
  mfa_required?: boolean;
  message?: string;
}

export interface AuthSession {
  user: AuthenticatedUser;
  accessToken: string;
  refreshToken?: string;
}

export interface ApiErrorResponse {
  detail?: string;
  message?: string;
  code?: string;
}
