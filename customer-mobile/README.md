# FieldOps Customer Mobile

A separate React Native + Expo + TypeScript customer application for the FieldOps project. It is intentionally isolated from the completed technician app in `mobile/` and uses the existing FastAPI backend and customer portal API contracts.

## Customer features included

- Customer-only email/password sign-in, MFA authenticator verification and recovery-code flow, plus password-reset email requests.
- Secure access/refresh token storage, one-at-a-time token refresh, session restoration, and logout.
- Customer dashboard using authoritative backend totals for total/pending requests, active jobs and completed jobs.
- Service catalog driven booking form, service type/category/issue selection, priority and preferred date.
- Explicit service address and contact details; current-location capture and manual coordinate confirmation for a booking.
- Customer-scoped request list, status filters, request detail, permitted editing and cancellation.
- Job status, authorized technician details, backend ETA/route metrics, a timeline, and REST polling while the job detail is open.
- Opens an external map application with the backend's latest technician coordinate (or service-site coordinate when no technician coordinate is available).
- Service history, completed-job feedback submission, invoice totals and itemized billing details, and persisted payment status/history.
- Customer in-app notification feed, unread counts, mark-one-read and mark-all-read actions.
- Notification preferences, customer profile creation/update, password change, and support-request creation/history/resolution notes.
- Separate Expo configuration, Android package, iOS bundle ID, app scheme, EAS profiles, TypeScript settings and environment template.

## Requirements

- Node.js 22 LTS or a currently supported Node release compatible with the Expo SDK used by this repository.
- npm.
- The FieldOps backend available on a URL reachable from the emulator/device.
- A customer user account in the backend. This app does not offer customer self-registration because the current customer portal contract does not expose a safe, tenant-aware public customer-registration workflow.

## Setup

1. Open a terminal in `customer-mobile/`.

2. Install the Expo-compatible WebView dependency used to host the same Ola Maps Web SDK as the web app, then install the project packages:

   ```bash
   npx expo install react-native-webview
   npm install
   ```

3. Copy `.env.example` to `.env` and set the reachable backend URL and your restricted Ola Maps client key.

   Android emulator (backend running on the same computer):

   ```dotenv
   EXPO_PUBLIC_API_BASE_URL=http://10.0.2.2:8000
   EXPO_PUBLIC_APP_ENV=development
   EXPO_PUBLIC_OLA_MAPS_API_KEY=your_ola_maps_client_key
   ```

   Physical Android/iOS device: use your development computer's LAN IP, such as `http://192.168.1.20:8000`, and ensure the device and computer can reach each other. `localhost` on a physical device points to the device, not your computer.

4. Start Metro with a clean cache after changing environment variables:

   ```bash
   npx expo start --clear
   ```

5. If you are using a native development build, rebuild it after adding WebView:

   ```bash
   npx expo run:android
   ```

   For iOS, build from macOS with Xcode:

   ```bash
   npx expo run:ios
   ```

6. Run the static TypeScript check:

   ```bash
   npm run typecheck
   ```

7. Check the Expo app configuration/dependencies:

   ```bash
   npx expo-doctor
   ```

## Environment and production settings

- `EXPO_PUBLIC_API_BASE_URL` is required. Production/staging rejects plain HTTP; use HTTPS.
- `EXPO_PUBLIC_OLA_MAPS_API_KEY` is used by the embedded Ola Maps Web SDK. It is bundled into the client app, so use a dedicated, appropriately restricted client key; do not reuse a backend-only secret.
- `.env` is excluded from version control. Do not put API secrets or signing credentials in `EXPO_PUBLIC_*`; client variables are bundled into the app.
- `com.fieldops.customer`, `com.fieldops.customer` (iOS) and the `fieldopscustomer://` URL scheme are deliberately distinct from the technician app IDs.
- `eas.json` provides development, preview and production profiles. Run `eas init` in this folder to associate the app with your own Expo/EAS project before using hosted EAS builds.
- If you use Android Firebase/FCM or iOS APNs for native push later, configure project credentials and add the customer device-registration/delivery contract on the backend first. No technician push-token endpoint is called by this app.

## Backend integration boundaries

All booking, request ownership, job state transitions, dispatch, ETA generation, payment-state persistence, notification authorization and role/tenant permissions remain server-authoritative. The client does not send a `tenant_id` or `customer_user_id` to decide its access scope.

Current customer routes consumed by this app:

- `/auth/login`, `/auth/me`, `/auth/refresh`, `/auth/logout`, `/auth/mfa/verify`, `/auth/mfa/recovery`
- `/api/customer/profile`, `/api/customer/change-password`, `/api/customer/dashboard`
- `/api/services/catalog`
- `/api/customer/service-requests` and `/api/customer/service-requests/{id}` plus `/cancel`
- `/api/customer/jobs` and `/api/customer/jobs/{id}`
- `/api/customer/service-history`
- `/api/customer/jobs/{id}/feedback`
- `/api/customer/invoices`, `/api/customer/invoices/{job_id}`, `/api/customer/invoices/{job_id}/payment-status`, `/api/customer/payment-history`
- `/api/customer/notifications`, `/api/customer/notifications/{notification_id}/read`, `/api/customer/notifications/read-all`
- `/api/customer/notification-preferences`
- `/api/customer/support-requests`
- `/organizations/location-search?q=…` for server-side service address suggestions
- `/organizations/reverse-location?latitude=…&longitude=…` for reverse geocoding when configured

## Known integration limitations

These are explicitly surfaced rather than hidden behind mocked behavior:

1. **Native push registration:** the inspected backend includes a customer in-app notification feed and preferences, but no customer device-registration endpoint matching the technician token registration API. This app therefore includes working in-app notification history/read states and does not pretend that native push is registered.
2. **Map and service address:** the mobile app uses the backend's server-side `/organizations/location-search` endpoint for address suggestions and `/organizations/reverse-location` for GPS reverse geocoding, so no map-provider API key is bundled in the app. A selected address still requires the customer to confirm its coordinates before booking; if search is unavailable, foreground GPS or manually entered coordinates remain available. The app never silently substitutes the backend's Chennai fallback. For technician navigation, it opens a map link using authorized backend coordinates.
3. **Payment initiation:** existing customer APIs expose invoices and persisted payment status/history, not a payment initiation/checkout API. This app displays billing information but does not invent payment processing.
4. **Request evidence uploads:** the current service-request contract has an `images` list, but a dedicated secure customer upload contract was not identified. The app sends an empty list and does not upload large base64 images into the request payload.
5. **Live tracking:** the job detail refreshes the customer-authorized REST tracking endpoint every 20 seconds while open. It does not subscribe to the tracking WebSocket because a customer's tenant and a dispatched provider's job tenant can differ in this backend, and the inspected socket channel contract is tenant-scoped. The REST endpoint remains the authority for customer-safe GPS and ETA fields.

## Folder layout

```text
customer-mobile/
├── app/
│   ├── (auth)/           # Login, MFA/recovery and password reset request
│   ├── (tabs)/           # Dashboard, requests, tracking, account
│   ├── jobs/             # Customer job detail, ETA and feedback
│   ├── requests/         # Create/edit/detail service requests
│   ├── history.tsx
│   ├── invoices.tsx
│   ├── notifications.tsx
│   ├── profile.tsx
│   ├── settings.tsx
│   └── support.tsx
├── assets/images/        # Existing FieldOps identity assets
├── src/api/              # API client and typed customer API functions
├── src/auth/             # Customer-only session and auth store
├── src/components/       # Shared UI and booking form
├── src/config/           # Environment validation
└── docs/                 # API contract notes
```
