# FieldOps unified mobile app

This is a standalone Expo Router app for customer, technician, and super admin accounts. It uses the existing FieldOps API and a separate `fo` SecureStore token namespace. Existing mobile apps are not modified.

## Configure and run

1. Copy `.env.example` to `.env`.
2. Set `EXPO_PUBLIC_API_BASE_URL` to the API origin reachable from the device. Android emulator uses `http://10.0.2.2:8000`; a physical phone needs the development computer's LAN IP and the phone and computer must share a network.
3. Set `EXPO_PUBLIC_OLA_MAPS_API_KEY` for Ola Maps tracking. This is a client SDK key; restrict it in the Ola Maps console.
4. From this folder, run `npm install`, then `npm run start`.

Use HTTPS for staging and production. The API base URL and map key are provided through Expo public environment variables; never put access or refresh tokens in environment variables.

## Sign-in and role routing

All roles use `/auth/login`, MFA endpoints when challenged, `/auth/refresh`, and `/auth/me`. The profile from `/auth/me` decides the protected route group. Customer, technician, and super admin are supported. Other roles see an access denied message. API access remains enforced by the backend.

Tracking uses the existing customer jobs response, which exposes technician GPS only when backend tracking is active. The map waits for technician travel and a current GPS location before showing the live technician position.
