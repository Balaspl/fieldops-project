
# FieldOps Mobile Technology Decision

- **Decision ID:** MOB-ADR-001
- **Status:** Accepted
- **Scope:** Technician mobile application technology selection (Task 1)

## Decision

Use **React Native with Expo, TypeScript, and Expo Router** for the FieldOps Technician Mobile Application. Build Android first and retain iOS support. Use Expo development builds for local development when native capabilities are needed and EAS Build for development, preview, and production builds.

## Context and requirements

The mobile application must support the existing FieldOps backend and technician workflow, including authenticated tenant-scoped access, job assignment and status actions, camera-based evidence, push notifications, location updates, and offline storage with synchronization when connectivity returns.

The agreed GPS behavior is to track the technician while logged in, including in the background and while working on assigned jobs. Tracking must stop on logout and respect operating-system permissions, privacy, and background-execution constraints.

## Options considered

| Option | Assessment | Decision |
|---|---|---|
| React Native + Expo | Reuses React/TypeScript skills and supports Android, iOS, camera, notifications, secure storage, and location capabilities. Development builds support native modules. | Selected |
| Bare React Native | Offers native control but requires more native project maintenance than currently needed. | Not selected |
| Web app / installable PWA | Reuses more web code but is a weaker default for the required native camera, background location, notifications, and offline workflow. | Not selected |

## Decision rationale

1. **Technician workflow:** Supports job lists, job details, status actions, forms, photos, and notifications.
2. **Existing skills:** React and TypeScript knowledge transfers, although web-specific UI components cannot be reused unchanged.
3. **Android and iOS:** One application can target Android first while retaining iOS support.
4. **Native capabilities:** Expo modules and development builds support camera, files, secure token storage, notifications, and location. Background location requires platform configuration, runtime permissions, and device testing.
5. **Build workflow:** Expo development builds support native modules; EAS Build provides development, preview, and production build profiles.
6. **Security and backend integration:** The app must preserve tenant context and backend-enforced authorization, avoid embedded secrets, and avoid logging tokens or unnecessary personal information.
7. **Reliability:** Offline storage and synchronization require explicit implementation. The backend remains authoritative for business rules and server state.

## Agreed platform and capability scope

- **Initial platform:** Android.
- **Additional platform:** iOS support required.
- **Location:** Track while logged in, including background operation and active jobs; stop on logout, subject to OS permissions and execution limits.
- **Evidence capture:** Camera and job photo/document capture.
- **Notifications:** Push notifications and device-token registration.
- **Offline:** Local storage and synchronization when connectivity returns.
- **Build system:** Expo development builds and EAS Build.
- **Navigation and code:** TypeScript and Expo Router.

## Implementation boundaries

This decision selects the technology; it does not claim that every capability is already production-ready. GPS cadence, background behavior, camera upload contracts, push-token lifecycle, offline conflict handling, and their tests must be implemented and verified in their respective tasks.

The backend remains responsible for authentication, roles, tenant isolation, technician/job authorization, business validation, and job assignment. The mobile app must handle denied permissions, expired sessions, unavailable services, and network failures safely.

## Consequences

- Continue using the existing `mobile/` workspace rather than creating a parallel application.
- Keep API, authentication, GPS, notification, and offline-sync logic in service modules rather than duplicating backend business rules in screens.
- Use `.env.example` for configuration names and exclude real `.env` files, credentials, dependencies, and local Expo state from source archives.
- Validate TypeScript, Expo configuration, Android builds, and technician workflows as their implementation tasks are completed.

## Task 1 acceptance mapping

| Acceptance point | Evidence |
|---|---|
| Select a mobile technology | React Native + Expo + TypeScript + Expo Router selected. |
| Evaluate workflow and platform needs | Options and trade-offs recorded above. |
| Account for GPS, camera, notifications, and offline requirements | All explicitly included, with background execution constraints. |
| Preserve backend authority and tenant isolation | Explicitly recorded in the decision and security rationale. |
| Record build approach | Expo development builds and EAS Build specified. |

**Task 1 decision status: complete.** This document records the technology choice and rationale; it does not claim all mobile capabilities are already implemented or end-to-end tested.
