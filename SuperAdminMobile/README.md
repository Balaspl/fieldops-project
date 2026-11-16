# FieldOps Staff Mobile

A new, standalone Expo / React Native application for **Super Admin** and **Dispatcher** users. It is intentionally named `FieldOpsStaff` and does not replace or reuse the existing `mobile` or `customer-mobile` project folders.

The app is a mobile client for the existing FieldOps Commander backend. It reuses the backend's authentication, tenant-scoped APIs, dispatch decisions, AI-agent workflow records, GPS stream and customer-support workflow. It does not duplicate job assignment rules or pretend to execute server-side AI agents locally.

## Included workspaces

| Workspace | Super Admin | Dispatcher |
|---|---:|---:|
| Operations dashboard | Yes | Yes |
| Planning and dispatch queue | Yes | Yes |
| Assign technician / exceptional override | Yes | Yes |
| Technician directory and availability | Yes | Yes |
| Create technician login + profile | Yes | Yes |
| Dispatcher directory | Yes | No |
| Live technician tracking | Yes | Yes |
| Service catalog | Manage | Read only |
| Customer support cases | Yes | Yes |
| Staff notifications | Yes | Yes |
| Staff profile and password | Yes | Yes |
| AI Agent Tracking timeline | Yes | No |

The same web assets supplied in `frontend(5).zip` are reused in the app: FieldOps logo, dispatcher and dashboard banners, technician banner, customer/service banners and service-category images.

## Backend integration requirements

The mobile app calls the existing FastAPI backend. Most workflows use existing endpoints. One required backend route was missing from the supplied snapshot: `POST /dispatchers/provision-technician`.

That route is supplied here:

`backend-patch/app/routes/dispatcher.py`

### Apply the backend patch

1. Back up your existing `backend/app/routes/dispatcher.py`.
2. Replace it with the supplied file at `backend-patch/app/routes/dispatcher.py`.
3. No router registration change is needed: the supplied backend snapshot already mounts `dispatcher.router` from `app/main.py`.
4. No database migration is required for this patch; it uses the existing `users`, `technicians` and `organizations` tables and columns.
5. Restart the FastAPI backend.
6. Verify `POST /dispatchers/provision-technician` while authenticated as a tenant `super_admin` or `dispatcher`.

The endpoint derives `tenant_id` from the verified JWT, restricts the caller to `super_admin` / `dispatcher`, rejects platform-only tenant identities, hashes a strong password using the backend's password utilities, creates the login `User` and operational `Technician` with the same ID, and commits both rows atomically. It writes `USER_CREATED` and `TECHNICIAN_CREATED` audit entries in the same transaction. The password and hash are never returned by the endpoint. New technicians start `OFFLINE`. Availability is controlled by the technician in their own portal, consistent with the web staff directory.

The mobile UI generates a temporary password using Expo Crypto and only displays it after the backend confirms successful provisioning. It is shown once in the creation confirmation and is not persisted by this app. Share the password securely; the endpoint does not currently implement a forced-password-reset-on-first-login policy.

## Local setup

Requirements:
- Node.js 22 LTS recommended
- npm 10+
- Android Studio / Android SDK for Android native builds
- Xcode for iOS native builds (macOS only)
- Expo CLI is invoked through the local project dependency

```bash
cd FieldOpsStaff
npm install
```

Copy `.env.example` to `.env` and set the backend address.

### API address examples

Android emulator:

```env
EXPO_PUBLIC_API_BASE_URL=http://10.0.2.2:8000
EXPO_PUBLIC_SOCKET_URL=ws://10.0.2.2:8000
EXPO_PUBLIC_SOCKET_IO_URL=http://10.0.2.2:8000
```

iOS simulator:

```env
EXPO_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
EXPO_PUBLIC_SOCKET_URL=ws://127.0.0.1:8000
EXPO_PUBLIC_SOCKET_IO_URL=http://127.0.0.1:8000
```

Physical device: use the reachable LAN IP / DNS name of the computer or server running FastAPI, for example `http://192.168.1.20:8000` and `ws://192.168.1.20:8000`. The phone and backend must be able to reach each other. `EXPO_PUBLIC_SOCKET_URL` is the raw WebSocket endpoint for GPS; `EXPO_PUBLIC_SOCKET_IO_URL` is the HTTP(S) origin used by the authenticated Socket.IO notification client. For production, use HTTPS and WSS with a valid TLS certificate, and set the Socket.IO origin to the HTTPS origin.

For Android map tiles, provide a Google Maps Android API key with Maps SDK for Android enabled:

```env
EXPO_PUBLIC_GOOGLE_MAPS_API_KEY=your_google_maps_android_key
```

If using the web project’s Ola Maps key for a future Ola-map implementation, store it only in a local `.env` file and do not commit it. This implementation uses `react-native-maps`; Google Maps tiles on Android need the Android key above. iOS uses the native map provider by default.

Start the Expo bundler:

```bash
npm start
```

Build / run on a connected Android device or emulator:

```bash
npm run android
```

For iOS on macOS:

```bash
npm run ios
```

Static TypeScript check and Expo dependency doctor:

```bash
npm run typecheck
npm run doctor
```

## Authentication and authorization

- Login uses the backend `POST /auth/login` contract (`email`, `password`).
- MFA challenge and verification use `POST /auth/mfa/verify`.
- The session is restored through `GET /auth/me`.
- Access and refresh tokens are stored with `expo-secure-store`.
- The app rejects roles other than `super_admin` and `dispatcher`.
- Tenant scope is taken from the verified backend identity. The app does not send a client-controlled tenant header for staff operations.
- API permissions remain authoritative. Hiding a menu item on mobile is not a security control.

## Operational behavior

### Planning and dispatch

The queue reads `/jobs/pending` and `/planned-assignments`, splitting Manager/CTO escalations into a separate tab as in the web app. Technician choices come from `/technicians/available`. Normal assignment posts to `/assign-job`; manual override uses `/technicians/assignments/{job_id}/override` with required justification. Escalated jobs support SLA extension through `/escalations/{job_id}/extend-sla` and escalation force assignment through `/escalations/{job_id}/force-assign`. Skill eligibility, workload, tenant, audit, notification and assignment timer checks remain backend-authoritative.

### Live tracking

The tracking screen loads the latest technician GPS fields and connects to the authenticated `/ws/v1/tracking?token=...` WebSocket. It subscribes to `tenant:{tenant_id}:all`, handles ping/pong, reconnects with backoff, validates coordinates, ignores older GPS timestamps, and applies the web tracking page’s 120-second heartbeat freshness window for Online / Offline filtering. The map is a live view of backend technician coordinates, not the phone's own location.

### Agent workflow tracking

The Super Admin-only view uses `GET /api/admin/agent-tracking` and `GET /api/admin/agent-tracking/{job_id}`. It displays backend-supplied Planning, dispatch, Communication, technician work, Sentiment and Closure stages plus recorded audit, chat, notification and delivery events. The app does not start, modify or simulate an AI agent run.

### Services

Both roles can read `/api/admin/services`. Only Super Admin can create, toggle or delete service entries. The create form follows the backend schema (`service_type`, `category`, `issue`, optional description and priority); no price field is introduced. Dispatcher is read-only as in the web permissions.

### Customer support

Support lists are read from `/api/admin/customer-support`, details from `/{id}`, and case updates are sent to `PATCH /{id}`. The app honours backend status choices and requires a resolution note before RESOLVED or CLOSED.

### Staff notifications

The inbox reads `/admin/notifications` for the signed-in staff recipient and uses `/notifications/{id}/read`, `/notifications/batch-read` and `/notifications/{id}/dismiss` for actions. It subscribes to the existing authenticated Socket.IO notifications (`new_notification`, `notification`, `notification:new` and `notification:unread_count`) and refreshes the unread count from the server. The backend controls recipient and tenant scope.

### Staff profile

The profile screen updates the signed-in user through `PUT /auth/profile` and changes the password through `PUT /auth/change-password`. The email and role are read-only. MFA enrollment and recovery settings remain in the web security settings flow.

## Important notes / known dependencies

- The actual backend must be running and reachable; the ZIP does not contain a production backend instance or credentials.
- Agent Tracking is Super Admin-only because the supplied backend endpoint itself permits Super Admin (and platform `head`) but does not grant Dispatcher access.
- The supplied dispatcher directory API is tenant-scoped. A `__platform__` user needs an organization-selection flow before managing organization staff; this single-tenant mobile build deliberately blocks platform-wide provisioning.
- The staff notification inbox is included and receives server-side real-time updates over the existing authenticated Socket.IO channel. Native OS push registration/token handling is not included; push delivery still depends on the backend’s existing provider registrations.
- The web application’s own role and tenant permissions continue to govern what is returned. If a user's backend role/permissions differ from the UI role expected here, the backend response is authoritative. The existing technician DELETE endpoint removes the operational profile but does not deactivate the linked user login; the app mirrors this web behavior and the backend should be enhanced with a linked-account deactivation policy before production use.
- No real API/device test can be claimed without access to your running backend, user accounts, map key and an Android/iOS runtime.

## Reference and implementation notes

- `docs/WEB_PARITY_MAP.md` maps the mobile screens and role permissions to the reviewed web application and backend APIs, and lists intentional mobile adaptations.
- `docs/INTEGRATION_CHECKLIST.md` contains backend patch, environment, role-acceptance and release-security checks.

## Project structure

```text
FieldOpsStaff/
├── App.tsx
├── app.json
├── app.config.js
├── package.json
├── .env.example
├── assets/
│   ├── brand/
│   ├── banners/
│   └── services/
├── backend-patch/
│   └── app/routes/dispatcher.py
├── docs/
│   ├── WEB_PARITY_MAP.md
│   └── INTEGRATION_CHECKLIST.md
└── src/
    ├── api/             # Axios client, token refresh and endpoint wrappers
    ├── auth/            # Login, MFA, secure-session restore and role gate
    ├── components/      # UI kit and role-aware staff shell
    ├── hooks/           # Authenticated GPS WebSocket lifecycle
    ├── screens/         # Dashboard, team, planning, tracking, services, support, agents
    ├── types/
    ├── theme.ts
    └── utils/           # Formatting and temporary credential generation
```

## Security reminder

Do not commit `.env`, production API keys or credentials. The supplied source ZIPs contained environment files with non-empty values; rotate any values that may have been live. The example environment file in this package intentionally contains no secrets.
