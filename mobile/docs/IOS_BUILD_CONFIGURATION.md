# FieldOps iOS Build Configuration

## App identity
- App: FieldOps
- Bundle identifier: com.fieldops.mobile
- URL scheme: fieldops
- Version: 1.0.0
- Expo owner: yeswanth1631
- EAS project: @yeswanth1631/fieldops-mobile
- EAS project ID: d4664812-e07b-429c-8f98-8f9e9e0d0b76

## Build profiles
- ios-simulator: development client, development environment, simulator enabled.
- ios-device: internal distribution, preview environment, physical-device build.
- preview: internal distribution, preview environment.
- production: store distribution, production environment, automatic version increments.
- App version source: remote.

## Permissions and iOS configuration
- Foreground and background location permission descriptions configured.
- Background location enabled through the Expo Location plugin.
- Camera and microphone permission descriptions configured.
- Expo Notifications plugin configured.
- Non-exempt encryption declaration set to false.

## EAS environment configuration
- Development: API and WebSocket variables configured.
- Preview: API and WebSocket variables configured.
- Production: API and WebSocket variables intentionally unset pending deployment selection.
- Development and preview currently use 192.168.1.84:8000.
- These local-network URLs are for development and internal testing only.

## Verification evidence
- iOS Simulator EAS cloud build successful.
- Successful build ID: eaf67671-e2d4-4d4c-aed8-c907a80ccfde
- Upload archive reduced from 654 MB to approximately 9.2 MB.
- Mobile setup tests: 12 passed, 0 failed.
- TypeScript typecheck: passed.
- iOS JavaScript bundle export: passed (1,203 modules; generated output in ignored dist/).
- API URL validation tests: passed; missing URLs and incorrect protocols are rejected.
- Mobile source endpoint regression test: passed.
- Latest Expo Doctor result: 20/21 checks passed.
- Remaining Expo Doctor warning concerns synchronizing app.json settings with the existing native Android project.
- EAS archive inspection confirmed the required mobile configuration files were included and generated Android build files were excluded.
- EAS iOS Simulator pre-install hook: executed successfully; environment validation passed.

## Remaining prerequisites
- Select a production hosting provider and configure production API and WebSocket URLs.
- Obtain valid Apple Developer signing credentials.
- Complete a signed physical-device iOS build.
- Verify installation and the technician workflow on a physical iPhone.
- Verify production signing and App Store distribution.

## Build commands

From the mobile directory:

```powershell
npx eas-cli build --platform ios --profile ios-simulator
npx eas-cli build --platform ios --profile ios-device
npx eas-cli build --platform ios --profile production




```

