# Web-to-Mobile Parity Map

Reference source: `backend(5).zip` and `frontend(5).zip`, reviewed 13 November 2026.

This is a native mobile implementation of the organization Super Admin and Dispatcher operating workspace. It reuses the live backend contracts and service-side decisions. It is not a pixel-for-pixel rendering of the desktop web app: native navigation, cards, sheets, map layout and compact forms are adapted to phone screens.

## Role coverage

| Web workspace / capability | Super Admin | Dispatcher | Mobile behavior |
|---|---|---|---|
| Operations dashboard | Yes | Yes | Date-filtered job status and payment metrics, technician availability/performance, service categories, SLA health, searchable recent jobs and quick navigation |
| Planning / pending queue | Yes | Yes | Separate Pending, Manager/CTO Escalations and Assigned views; tenant-visible queue; backend-ranked technician recommendations and bulk pending-job actions |
| Normal job assignment | Yes | Yes | Calls `/assign-job`; backend performs eligibility, tenant, workload, timers, notifications and audit logic |
| Exceptional assignment override | Yes | Yes | Calls `/technicians/assignments/{job_id}/override` with required justification; escalated jobs use `/escalations/{job_id}/force-assign` |
| SLA escalation response | Yes | Yes | Manager/CTO escalation cards, SLA deadline extension using `/escalations/{job_id}/extend-sla`, and escalation-specific force assignment |
| Technician directory | Yes | Yes | Search/filter roster, skill, work zone, status, workload, contact details and GPS recency; edit and delete operational profile |
| Technician availability | Technician controlled | Technician controlled | Status is displayed and filtered; mobile staff directory cannot change it, and profile edits omit status so they cannot overwrite technician-controlled availability |
| Provision technician login + profile | Yes | Yes | Calls the new `/dispatchers/provision-technician` endpoint in the included patch |
| Dispatcher directory | Yes | No | Super Admin only; tenant-scoped `/dispatchers` |
| Organization live tracking | Yes | Yes | Ola Maps live map, roster search, All/Online/Offline heartbeat filter, live GPS, job ID and server ETA when available |
| Service catalog | Manage | Read only | Super Admin create/activate/deactivate/delete; Dispatcher browse only |
| Customer support | Yes | Yes | Tenant-visible cases, customer and job context, sentiment triage, transcript/activity, assignment-to-self and status/resolution updates |
| Staff notifications | Yes | Yes | User-specific inbox, unread counts, mark-read, batch-read and dismiss actions; authenticated Socket.IO event refresh |
| Staff profile | Yes | Yes | Update first/last name and change password using the same auth APIs |
| Agent Tracking | Yes | No | Read-only live workflow stages, progress, running/completed/failed filters, sentiment, communication/delivery events, closure checks and detailed event payloads; Super Admin only in app navigation |
| Communication Center | Yes | Yes | Same read-only endpoint with server-side search, channel and delivery-state filters, and pagination in native cards |

The `head` platform role is deliberately excluded. This is an organization-staff app, not the cross-tenant platform control panel.

## Backend contracts used

| Feature | Existing API / channel |
|---|---|
| Authentication | `POST /auth/login`, `POST /auth/mfa/verify`, `POST /auth/refresh`, `GET /auth/me`, `POST /auth/logout` |
| Dashboard | `GET /jobs/stats?time_range=week`, `GET /planning/kpi`, `GET /jobs`, `GET /technicians` |
| Planning | `GET /jobs/pending`, `GET /planned-assignments`, `GET /technicians/available`, `POST /assign-job`, `POST /technicians/assignments/{job_id}/override`, `POST /escalations/{job_id}/extend-sla`, `POST /escalations/{job_id}/force-assign` |
| Technicians | `GET /technicians`, `PUT /technicians/{id}`, `DELETE /technicians/{id}`, plus the custom linked-login provisioning patch |
| Dispatcher directory | `GET /dispatchers` |
| Live tracking | `GET /technicians`, WebSocket `GET /ws/v1/tracking?token=<JWT>`, subscribe `tenant:{tenant_id}:all` |
| Services | `GET /api/admin/services`, `GET /api/admin/services/taxonomy-suggestions`, `POST /api/admin/services`, `PATCH /api/admin/services/{id}/toggle-active`, `DELETE /api/admin/services/{id}` |
| Support | `GET /api/admin/customer-support`, `GET /api/admin/customer-support/{id}`, `PATCH /api/admin/customer-support/{id}` |
| Notifications | `GET /admin/notifications`, `PATCH /notifications/{id}/read`, `PATCH /notifications/batch-read`, `PATCH /notifications/{id}/dismiss`; Socket.IO `new_notification`, `notification`, `notification:new`, `notification:unread_count` |
| Staff profile | `PUT /auth/profile`, `PUT /auth/change-password` |
| Agent Tracking | `GET /api/admin/agent-tracking?limit=250`, `GET /api/admin/agent-tracking/{job_id}` |
| Communication Center | `GET /admin/communication-center?search=…&channel=…&status=…&limit=50&offset=…` |

The mobile app does not make its own dispatch/AI decisions and does not create fake GPS or agent events. The server remains authoritative for business rules, permissions, assignment and workflow processing.

## Shared web assets

The mobile package reuses the same supplied web image files (verified byte-for-byte before copying) for the FieldOps logo, dispatcher banner, dashboard banner, technician banner, customer/service banners and 18 service-category images. They are stored under `assets/` and statically bundled; no remote image download is required for these assets.

## Native adaptations and known web-only differences

These differences are deliberate and should not be interpreted as server feature replacements:

- Live Tracking follows the web technician roster filters, online/offline freshness, technician search, counts, refresh behavior, Ola Maps markers and authenticated WebSocket updates. Ola's Web SDK is rendered in a native WebView so Android does not use Google Maps.
- The mobile planning view includes Pending, Manager/CTO Escalations and Assigned, normal assignment, justified override, backend-ranked candidates, SLA extension, escalation force assignment, and bulk assignment/cancellation. It does not yet port every desktop planning subview, historical redispatch/override panels, detailed SLA dashboards, or full route playback/ETA exploration. These are presentation and investigation gaps; assignment, eligibility, escalation and dispatch decisions remain on the same backend endpoints.
- The mobile service catalog currently creates one catalog row at a time. The backend batch endpoint is available but the mobile screen does not expose batch creation.
- The mobile support view assigns a case to the current user when requested. The supplied backend update contract has no explicit unassign operation, so the mobile UI does not claim to support unassigning an already assigned case.
- The app includes a staff inbox and authenticated Socket.IO notification updates. It does not register a native OS push token; existing backend push/SMS/email delivery continues through the provider registrations already configured on the server.
- The mobile app uses native bottom navigation and bottom sheets rather than copying desktop sidebars, multi-column tables and desktop-only interaction patterns.

## Backend parity audit

- Mobile staff workflows use the same API routes as the web for assignment, overrides, escalations, ranked planning, support, service catalog operations, agent tracking, notifications and communication activity. Technician ranking, eligibility, dispatch race handling, fallback assignment and job state transitions remain server-owned.
- The technician directory only edits profile fields and displays backend-reported status. Availability changes remain in the technician portal, matching web admin behavior.
- Web Super Admin has richer planning history, map controls/route exploration, service batch creation and additional SLA views. These remain UI coverage gaps; they do not require separate mobile backend rules.
- Technician provisioning uses the same `/dispatchers/provision-technician` endpoint as web. That route is not defined in the checked-in `backend/app/routes` sources in this workspace, so both clients require the matching backend implementation to be deployed for provisioning to work.

## Important backend gap fixed by the included patch

The supplied web frontend calls `POST /dispatchers/provision-technician`, but the supplied backend snapshot does not implement it. The existing `POST /technicians` operation creates an operational technician row only; it does not provision the technician's login account.

`backend-patch/app/routes/dispatcher.py` preserves the directory GET route and adds secure account provisioning:

1. The tenant ID is taken from the authenticated JWT, never the request body.
2. Only organization `super_admin` and `dispatcher` users can create a technician account; platform-only identities are rejected.
3. The organization must exist, be active and not be soft-deleted; organization user/technician plan limits are enforced; email uniqueness is checked within the tenant (with database uniqueness races handled as conflicts).
4. The password is validated and hashed using the backend's existing password utilities.
5. The `User` identity and linked `Technician` record are created in one SQL transaction.
6. `USER_CREATED` and `TECHNICIAN_CREATED` audit entries are written in that same transaction.
7. Password or password hash is never returned by the API.

No schema migration is expected because the patch uses existing user, technician, organization and enterprise-audit models. Replace the backend route file only after taking a backup and reviewing it against any local changes made after the supplied snapshot.

## Technician deletion caveat in supplied backend

The existing `DELETE /technicians/{technician_id}` endpoint deletes the operational technician row only; it does not delete/deactivate the linked `User` login. The mobile app matches this web behavior and labels the action as deleting the technician profile. Before using this action in production, review whether account deactivation should be added server-side so a removed technician cannot continue signing in.
