
# FieldOps Mobile Environment Configuration

## 1. Development

Use the local `.env` file for development on your computer and Android emulator.

Example:

```env
EXPO_PUBLIC_API_BASE_URL=http://192.168.1.84:8000
EXPO_PUBLIC_WS_BASE_URL=ws://192.168.1.84:8000
```

Keep the API address aligned with the backend host and port reachable from the device or emulator.

The local `.env` file is ignored by Git. Do not commit it.

## 2. Staging

Use the EAS `preview` build profile for staging builds.

Configure these variables in the EAS environment associated with the `preview` profile:

- `EXPO_PUBLIC_API_BASE_URL`
- `EXPO_PUBLIC_WS_BASE_URL`

Use the actual staging backend URLs supplied by your deployment environment. Use HTTPS for the API and WSS for WebSocket connections when staging uses HTTPS.

Never use the local development server address for a deployed staging build.

## 3. Production

Use the EAS `production` build profile.

Configure these variables in the EAS `production` environment:

- `EXPO_PUBLIC_API_BASE_URL`
- `EXPO_PUBLIC_WS_BASE_URL`

Production must use HTTPS for the API and WSS for WebSocket connections. The build environment validation script must reject missing or insecure production URLs.

Use the real production service URLs configured for your deployment. Do not substitute example domains or local addresses.

## 4. Environment variables and secrets

Variables prefixed with `EXPO_PUBLIC_` are embedded in the client application and may be visible to users.

Appropriate public configuration includes API and WebSocket base URLs.

Never put passwords, access tokens, refresh tokens, signing keys, private API keys, database credentials, or other secrets in:

- `EXPO_PUBLIC_` variables
- `.env.example`
- application source code
- committed configuration files

Keep server-side secrets in the backend's protected environment or secret manager.

## 5. Configuration validation

Before distributing a build:

1. Select the intended EAS build profile.
2. Verify its EAS environment contains the correct API and WebSocket URLs.
3. Run `npm run typecheck`.
4. Run `npm test`.
5. Run `npx expo export --platform android`.
6. Confirm production validation rejects missing URLs and non-HTTPS/WSS endpoints.

## 6. Local configuration

Use `.env.example` as the tracked template for local development. Copy it to `.env` and set the local backend address for your machine.

Do not replace working local settings merely to prepare for staging or production. Configure those environments independently in EAS.
