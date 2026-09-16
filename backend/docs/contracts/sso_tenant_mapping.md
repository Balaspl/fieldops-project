# SSO Tenant Mapping — FieldOps OIDC Integration

This document describes:

- The SSO authentication flow
- How to configure and enable OIDC
- How to create enterprise user identity links (tenant mapping)
- Logout and session behavior
- Expected output contract

---

## Overview

FieldOps SSO uses the **OpenID Connect Authorization Code Flow**.
Google is the currently supported identity provider.

Security model:

- The OIDC provider (Google) **proves external identity only**.
- FieldOps **always controls** role, tenant, and authorization.
- No FieldOps user is **automatically created** during SSO.
- Provider-supplied claims (e.g. injected `role`, `tenant_id`) are **silently ignored**.

---

## SSO Flow Diagram

```
Enterprise User
      │
      ▼
GET /auth/sso/login
      │  FieldOps generates cryptographically secure state + nonce
      │  Stores {nonce, redirect_uri} in Redis with 5-minute TTL
      │  Builds Google authorization URL
      ▼
Redirect → Google OIDC (accounts.google.com)
      │  User authenticates with Google
      ▼
GET /auth/sso/callback?code=...&state=...
      │
      ├── [1] Validate state (retrieve + delete from Redis — single-use)
      ├── [2] Exchange code for ID token with Google
      ├── [3] Validate ID token (issuer, audience, expiry, nonce, signature)
      ├── [4] Extract issuer + subject from verified claims
      ├── [5] Resolve OIDCIdentity → FieldOps User
      │         • Checks user is active
      │         • Checks tenant/organization is active
      │         • Role and tenant_id come from FieldOps DB
      └── [6] Issue normal FieldOps JWT (access_token + refresh_token)
```

---

## Environment Variables

Set these in `backend/.env` or your deployment secrets manager.

| Variable                   | Required | Default                                   | Description                                                             |
| -------------------------- | -------- | ----------------------------------------- | ----------------------------------------------------------------------- |
| `OIDC_ENABLED`             | **Yes**  | `false`                                   | Set to `true` to enable SSO                                             |
| `OIDC_PROVIDER`            | **Yes**  | `google`                                  | OIDC provider name. Only `google` is supported                          |
| `OIDC_ISSUER_URL`          | **Yes**  | `https://accounts.google.com`             | OIDC issuer URL. Must match the provider's discovery document           |
| `OIDC_CLIENT_ID`           | **Yes**  | _(empty)_                                 | OAuth2 client ID from Google Cloud Console                              |
| `OIDC_CLIENT_SECRET`       | **Yes**  | _(empty)_                                 | OAuth2 client secret from Google Cloud Console                          |
| `OIDC_AUDIENCE`            | No       | Same as `OIDC_CLIENT_ID`                  | JWT audience claim. Defaults to client ID                               |
| `OIDC_REDIRECT_URI`        | No       | Auto-detected from request                | Callback URL registered in Google Cloud Console. Set this in production |
| `SSO_FRONTEND_SUCCESS_URL` | No       | `http://localhost:5173/auth/sso/callback` | Frontend URL that receives the SSO result                               |
| `SSO_FRONTEND_ERROR_URL`   | No       | `http://localhost:5173/login`             | Frontend URL to redirect on failure                                     |
| `REDIS_URL`                | **Yes**  | `redis://localhost:6379/0`                | Redis URL for SSO state storage                                         |

### Example `.env` (Google Workspace)

```dotenv
OIDC_ENABLED=true
OIDC_PROVIDER=google
OIDC_ISSUER_URL=https://accounts.google.com
OIDC_CLIENT_ID=123456789-xxxxx.apps.googleusercontent.com
OIDC_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxxxxxxxxx
OIDC_REDIRECT_URI=https://api.fieldops.example.com/auth/sso/callback
SSO_FRONTEND_SUCCESS_URL=https://app.fieldops.example.com/auth/sso/callback
SSO_FRONTEND_ERROR_URL=https://app.fieldops.example.com/login
```

---

## Tenant Mapping — How to Link Enterprise Users

Before an enterprise user can sign in via SSO, an **admin must create an
`OIDCIdentity` record** that links their Google identity to an existing FieldOps
user account.

> [!IMPORTANT]
> SSO **never creates new FieldOps accounts automatically**. Every enterprise
> user must have a FieldOps account created first (via `POST /auth/register` or
> the admin panel), and then linked to their Google identity.

### Method 1 — Self-Service API (Recommended)

An already-authenticated FieldOps user links their own Google account:

```http
POST /auth/oidc/google/link
Authorization: Bearer <fieldops_access_token>
Content-Type: application/json

{
  "id_token": "<google_id_token>"
}
```

The frontend obtains the `id_token` from a Google One-Tap or OAuth2 flow
and sends it here. FieldOps validates the token and creates the link.

**Response (success):**

```json
{
  "status": "LINKED",
  "provider": "google"
}
```

**Constraints enforced:**

- One FieldOps user can link **at most one** Google identity.
- One Google identity can be linked to **at most one** FieldOps user.

---

### Method 2 — Admin Database Insert

For bulk onboarding, an admin can insert `OIDCIdentity` rows directly.
The Google `sub` (subject) claim uniquely identifies a Google account.

```sql
INSERT INTO oidc_identities (id, user_id, provider, issuer, subject)
VALUES (
    gen_random_uuid(),
    '<fieldops_user_id>',       -- UUID from the users table
    'google',
    'https://accounts.google.com',
    '<google_subject_claim>'    -- "sub" from the user's Google ID token
);
```

**How to find the Google `sub`:**

1. Ask the user to visit `https://accounts.google.com/o/oauth2/v2/auth` with
   `response_type=id_token&scope=openid email` and your client ID.
2. Decode the returned ID token (e.g. `jwt.io`).
3. Extract the `sub` field — it is a stable numeric string like `"108523945123456789"`.

---

## Lookup Table — Tenant Resolution

| Step                    | Source                                 | Claim Used For                                    |
| ----------------------- | -------------------------------------- | ------------------------------------------------- |
| External identity proof | Google                                 | `iss` + `sub` (identifies the `OIDCIdentity` row) |
| FieldOps user lookup    | `oidc_identities.user_id` → `users.id` | Links Google → FieldOps                           |
| Tenant determination    | `users.tenant_id`                      | Always from the FieldOps DB                       |
| Role determination      | `users.role`                           | Always from the FieldOps DB                       |
| Token issuance          | `users` row                            | `access_token` + `refresh_token`                  |

**Google claims that are explicitly ignored:** `role`, `tenant_id`, `groups`,
`hd` (hosted domain), `permissions`, and any other non-standard claims.

---

## Logout and Session Behavior

| Action                        | What Happens                                                                                                      |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `POST /auth/logout`           | Blacklists the FieldOps access token (Redis JTI blacklist) and revokes all active refresh tokens in the database. |
| Google-side logout            | **Not propagated to FieldOps.** Logging out of Google does not revoke the FieldOps JWT.                           |
| Google password change        | **Not propagated to FieldOps.** The FieldOps token remains valid until expiry or explicit logout.                 |
| FieldOps access token expiry  | Client must use `POST /auth/refresh` with the refresh token to obtain a new access token.                         |
| FieldOps refresh token expiry | User must complete the SSO flow again via `GET /auth/sso/login`.                                                  |

> [!NOTE]
> FieldOps does not implement Single Log-Out (SLO) toward the OIDC provider.
> If SLO is required in a future release, the logout route can be extended to
> call the provider's `end_session_endpoint` from the OIDC discovery document.

---

## Failure States and Error Codes

The browser SSO callback (`GET /auth/sso/callback`) always redirects to
`SSO_FRONTEND_ERROR_URL` on failure, never exposes internal errors to the browser.

| Error Code                  | When It Occurs                                                |
| --------------------------- | ------------------------------------------------------------- |
| `sso_provider_error`        | Provider returned `?error=...` in the callback                |
| `invalid_state`             | State missing, expired (> 5 min), or already consumed         |
| `missing_code`              | State valid but no authorization code returned                |
| `sso_authentication_failed` | Token exchange failed or ID token validation failed           |
| `sso_not_authorized`        | Google identity not mapped, user disabled, or tenant inactive |
| `sso_unavailable`           | Unexpected internal error                                     |

---

## Required OIDC API Endpoints

| Endpoint        | File                                                                                                               | Route                         |
| --------------- | ------------------------------------------------------------------------------------------------------------------ | ----------------------------- |
| SSO initiation  | [`routes/sso.py`](file:///c:/Users/DHARSAN/OneDrive/Documents/GitHub/fieldops-project/backend/app/routes/sso.py)   | `GET /auth/sso/login`         |
| SSO callback    | [`routes/sso.py`](file:///c:/Users/DHARSAN/OneDrive/Documents/GitHub/fieldops-project/backend/app/routes/sso.py)   | `GET /auth/sso/callback`      |
| API OIDC login  | [`routes/auth.py`](file:///c:/Users/DHARSAN/OneDrive/Documents/GitHub/fieldops-project/backend/app/routes/auth.py) | `POST /auth/oidc/google`      |
| Account linking | [`routes/auth.py`](file:///c:/Users/DHARSAN/OneDrive/Documents/GitHub/fieldops-project/backend/app/routes/auth.py) | `POST /auth/oidc/google/link` |

---

## Expected Output Contract

After a successful SSO flow, the FieldOps API returns:

```json
{
  "access_token": "<signed_hs256_jwt>",
  "refresh_token": "<signed_hs256_jwt>",
  "token_type": "bearer",
  "expires_in": 1800,
  "user": {
    "id": "<fieldops_user_uuid>",
    "email": "<user_email>",
    "first_name": "<first_name>",
    "last_name": "<last_name>",
    "role": "<fieldops_role>",
    "tenant_id": "<fieldops_tenant_uuid>",
    "organization_name": "<organization_name>"
  }
}
```

SSO status contract:

```json
{
  "status": "SUPPORTED",
  "sso": true,
  "identity_provider": "configured",
  "fieldops_authorization": "enforced"
}
```

---

## Security Checklist

- [x] State and nonce generated with `secrets.token_urlsafe(32)`
- [x] State stored in Redis with 5-minute TTL
- [x] State consumed atomically (single-use via Redis pipeline)
- [x] ID token signature validated against Google JWKS
- [x] Issuer pinned to `https://accounts.google.com`
- [x] Audience validated against configured `OIDC_CLIENT_ID`
- [x] Nonce verified on every token validation
- [x] Tenant and role derived exclusively from FieldOps DB
- [x] No automatic user creation
- [x] Disabled users and inactive tenants rejected
- [x] Error responses never expose internal details to the browser
- [x] Redirect URI is server-controlled (never accepted from client)
