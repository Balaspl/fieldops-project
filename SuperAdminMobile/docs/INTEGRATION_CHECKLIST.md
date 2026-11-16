# Integration and Release Checklist

## 1. Backend patch

- [ ] Back up `backend/app/routes/dispatcher.py` in the working backend.
- [ ] Review `backend-patch/app/routes/dispatcher.py` against any local changes made after the supplied code snapshot.
- [ ] Replace `backend/app/routes/dispatcher.py` with the included patched route.
- [ ] Confirm `app/main.py` still includes `dispatcher.router` (it does in the supplied snapshot).
- [ ] Restart FastAPI.
- [ ] Confirm the OpenAPI document contains `POST /dispatchers/provision-technician`.
- [ ] Test technician provisioning using a non-production tenant Super Admin and Dispatcher account.
- [ ] Confirm one `users` row and one linked `technicians` row are created with the same technician `tech_id` / user ID.
- [ ] Confirm tenant ID is inherited from the JWT and cannot be selected by a mobile request.
- [ ] Confirm a duplicate tenant email returns HTTP 409 and does not leave a partial record.
- [ ] Confirm the original web payload (`first_name`, `last_name`, `email`, `password`) still works; absent skill/location values default to `General` / `Unassigned`.
- [ ] Confirm an inactive or deleted organization is rejected and user/technician plan limits are enforced.
- [ ] Confirm two concurrent provisioning requests cannot exceed the organization limits.
- [ ] Confirm enterprise audit rows exist for both user and technician creation.
- [ ] Confirm the API response contains no password or password hash.

## 2. Mobile environment

- [ ] Install Node.js 22 LTS and npm 10 or newer.
- [ ] Copy `.env.example` to `.env`.
- [ ] Set `EXPO_PUBLIC_API_BASE_URL` to the address reachable from the phone/emulator.
- [ ] Set `EXPO_PUBLIC_SOCKET_URL` to the matching `ws://` / `wss://` GPS WebSocket origin.
- [ ] Set `EXPO_PUBLIC_SOCKET_IO_URL` to the matching `http://` / `https://` Socket.IO origin (the same backend host).
- [ ] Set `EXPO_PUBLIC_GOOGLE_MAPS_API_KEY` for Android native Google map tiles.
- [ ] Use HTTPS and WSS, plus a valid certificate, for production deployment.
- [ ] Keep `.env` and real API keys out of source control.

## 3. Install and run

```bash
npm install
npm run typecheck
npx expo-doctor
npm start
```

For Android native run:

```bash
npm run android
```

For iOS native run on macOS with Xcode:

```bash
npm run ios
```

## 4. Role acceptance tests

### Super Admin

- [ ] Log in with a tenant-level `super_admin` account.
- [ ] Verify Dashboard and tenant metrics load.
- [ ] Verify Planning Pending, Manager/CTO Escalations and Assigned tabs load.
- [ ] Assign one test job normally and verify server-side assignment side effects.
- [ ] Verify manual override requires a meaningful justification and is audited by the backend.
- [ ] Extend an active escalation SLA by 30 minutes and verify the backend closes the escalation response.
- [ ] Force-assign an escalated job and verify the backend audit and technician notification.
- [ ] Verify Technician roster, status filters, profile edits and profile deletion. Confirm technician availability remains controlled by the technician portal.
- [ ] Provision a test technician and verify the linked login and technician profile.
- [ ] Verify Dispatcher directory shows only dispatchers from the current tenant.
- [ ] Verify technician deletion behavior: the supplied backend removes the operational profile but does not deactivate the linked login account; do not use as an offboarding control until this is fixed server-side.
- [ ] Verify Live Tracking WebSocket connects and current GPS updates are visible.
- [ ] Verify service create/activate/deactivate/delete operations.
- [ ] Verify Customer Support case detail, assignment-to-self, status and resolution-note flows.
- [ ] Verify the notification inbox, unread badge, live Socket.IO event refresh, mark read, mark all read and dismiss actions.
- [ ] Verify staff profile name update and password change.
- [ ] Verify Agent Tracking list and event detail.

### Dispatcher

- [ ] Log in with a tenant `dispatcher` account.
- [ ] Verify Dashboard, Planning (including escalations), Technician roster, Live Tracking and Customer Support.
- [ ] Verify Technician provisioning works only within the current tenant.
- [ ] Verify technicians can be edited/deleted only according to backend permissions; do not treat profile deletion as account offboarding.
- [ ] Verify Service Catalog is read-only.
- [ ] Verify Dispatcher directory is not accessible.
- [ ] Verify the notification inbox and live unread badge update from dispatcher notification events.
- [ ] Verify staff profile name update and password change.
- [ ] Verify Agent Tracking is not visible in navigation and is rejected by backend for Dispatcher.

## 5. Release security checks

- [ ] Test tenant A and tenant B with separate staff accounts and verify no cross-tenant data is visible.
- [ ] Confirm the app refuses non-staff roles such as customer, technician and `head`.
- [ ] Confirm expired sessions refresh once; failed refresh returns to login.
- [ ] Confirm temporary technician credentials are shared through an approved secure channel and not written to logs/screenshots.
- [ ] Rotate any credentials that were present in the originally supplied ZIP files if they may be live.

## Validation performed in the build workspace

- JSON manifests parsed successfully.
- All relative TS/TSX imports and statically referenced bundled asset paths resolved.
- All 22 TypeScript / TSX / JavaScript source files passed TypeScript transpile syntax parsing with zero syntax diagnostics.
- Backend patch passed Python bytecode compilation (`py_compile`).
- `app.config.js` passed Node syntax check.

A full dependency-resolved TypeScript typecheck, Expo Doctor, native Android/iOS build and live API/WebSocket tests were not completed in this environment: npm registry access failed with a DNS/network `EAI_AGAIN` error, and no live FieldOps backend/device session was available. Run the checklist above in the development environment before production use.
