# Customer mobile API contract notes

This document records the existing FieldOps backend routes used by `customer-mobile/`. It is based on the supplied backend and web frontend source archives, not a live server response.

| Feature | Method and route | Notes |
|---|---|---|
| Sign in | `POST /auth/login` | Returns access/refresh tokens, or an MFA challenge |
| Forgot password | `POST /auth/forgot-password` | Returns a generic confirmation to prevent account enumeration; email delivery and reset destination are backend configured |
| MFA | `POST /auth/mfa/verify` | Requires `challenge`, `code`, optional `trust_device` |
| Recovery | `POST /auth/mfa/recovery` | Requires `challenge`, `recovery_code` |
| Restore session | `GET /auth/me` | Client verifies role `CUSTOMER` before entering the app |
| Refresh | `POST /auth/refresh` | Mobile sends the refresh token in JSON body |
| Profile | `GET/POST/PUT /api/customer/profile` | Profile creation and updates use authenticated customer scope |
| Dashboard | `GET /api/customer/dashboard` | `total_requests`, `pending_requests`, `active_jobs`, `completed_jobs` |
| Catalog | `GET /api/services/catalog` | Active items provide `service_type`, `category`, `issue`, `description`, `priority` |
| Requests | `GET/POST /api/customer/service-requests` | Creation includes title, description, service type, category, issue, priority, date, location, contact and coordinate pair |
| Request detail/update | `GET/PUT /api/customer/service-requests/{id}` | Update schema intentionally does not accept category/issue or coordinates |
| Request cancellation | `POST /api/customer/service-requests/{id}/cancel` | Server checks whether the request can still be cancelled |
| Jobs/tracking | `GET /api/customer/jobs`, `GET /api/customer/jobs/{id}` | Customer-safe technician, GPS and ETA data; job ownership checked by backend |
| Service history | `GET /api/customer/service-history` | History summary data |
| Feedback | `GET/POST /api/customer/jobs/{id}/feedback` | Feedback is tied to an eligible job; rating and comment sent to backend |
| Invoices | `GET /api/customer/invoices`, `GET /api/customer/invoices/{job_id}` | Read-only invoice information |
| Payment information | `GET /api/customer/payment-history`, `GET /api/customer/invoices/{job_id}/payment-status` | Payment state/history only; no checkout route identified |
| Notifications | `GET /api/customer/notifications` | Feed object contains `notifications` and `unread_count` |
| Read notification | `PUT /api/customer/notifications/{notification_id}/read`, `PUT /api/customer/notifications/read-all` | Customer ownership enforced by backend |
| Preferences | `GET/PATCH /api/customer/notification-preferences` | Saved communication preferences |
| Support | `GET/POST /api/customer/support-requests` | Customer request list/create; admin response notes are displayed when returned |
| Location search | `GET /organizations/location-search?q=…` | Server-side address suggestions; provider credentials stay on backend |
| Reverse geocode | `GET /organizations/reverse-location?latitude=…&longitude=…` | Address resolution helper when available |

## Security and data rules

- The customer router requires the authenticated `CUSTOMER` role.
- The app does not include `customer_user_id` or `tenant_id` in API payloads to authorize requests.
- The role guard runs on sign-in, MFA completion and session restoration.
- Session tokens use Expo SecureStore and are not persisted in AsyncStorage.
- Backend statuses, ownership, dispatch, ETA and payment state are never authored by the mobile client.
