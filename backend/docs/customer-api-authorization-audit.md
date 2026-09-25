# Customer API authorization audit

## Scope and identity

Customer portal identity comes from `get_current_user`, which validates the token's user, role, and tenant against the database. Customer endpoints use `current_user.user_id` and `current_user.tenant_id`; no route accepts a caller-selected customer identity or tenant.

Jobs are assigned to service-provider tenants, which may differ from the customer's tenant. A customer job is therefore visible only through a `ServiceRequest` whose `customer_user_id` and `tenant_id` match the authenticated user. When present, `Job.customer_id` must also match; legacy jobs without that column value still require the tenant-scoped owned request link.

## Customer portal route inventory

| Route | Permission | Ownership / tenant boundary |
| --- | --- | --- |
| `GET /api/customer/profile` | `CUSTOMERS_VIEW_OWN` | Profile and user lookups use authenticated user ID plus tenant. |
| `POST, PUT /api/customer/profile` | `CUSTOMERS_VIEW_OWN` | Profile is created or updated only for authenticated user ID plus tenant. |
| `POST /api/customer/change-password` | `CUSTOMERS_VIEW_OWN` | User lookup uses authenticated user ID plus tenant. |
| `GET /api/customer/service-requests` | `JOBS_VIEW_OWN` | Request query is customer and tenant scoped; linked job status is fetched in the same outer-join query. |
| `POST /api/customer/service-requests` | `CUSTOMERS_CREATE_REQUEST` | User, request, and job customer IDs derive from authenticated identity; request tenant derives from authenticated tenant. Provider assignment is retained. |
| `GET /api/customer/service-requests/{sr_id}` | `JOBS_VIEW_OWN` | Request ID, customer ID, and tenant are all required. |
| `PUT /api/customer/service-requests/{sr_id}` | `CUSTOMERS_CREATE_REQUEST` | Owned request and linked job are locked and scoped; edits require the effective job to remain `CREATED` and update both request and job fields. Control fields such as status and linked job ID are rejected by the schema. |
| `POST /api/customer/service-requests/{sr_id}/cancel` | `CUSTOMERS_CREATE_REQUEST` | Owned request and linked job are locked; cancellation eligibility uses linked job state when present. Both records transition together; job transition rules deny cancellation after dispatch progress disallows it. |
| `GET /api/customer/jobs` | `JOBS_VIEW_OWN` | Jobs must link to a request owned by authenticated user and tenant. Technician and profile enrichment is batch-loaded and tenant keyed. |
| `GET /api/customer/jobs/{job_id}` | `JOBS_VIEW_OWN` | Job ID, authenticated customer identity, and owned tenant-scoped request link are required. No fallback query bypasses the same predicate. |
| `GET /api/customer/jobs/{job_id}/report` | `REPORTS_DOWNLOAD` | Completion closure must join through the same owned tenant-scoped request and match the provider job tenant. The PDF returns completion information, not internal cost fields. |
| `GET /api/customer/service-history` | `JOBS_VIEW_OWN` | Completed/cancelled requests are filtered by authenticated user ID plus tenant. |
| `GET /api/customer/notifications` | `NOTIFICATIONS_VIEW_OWN` | Notification recipient and tenant are authenticated user ID plus tenant. |
| `PUT /api/customer/notifications/{notification_id}/read` | `NOTIFICATIONS_VIEW_OWN` | Notification ID, recipient, and tenant are all required. |
| `PUT /api/customer/notifications/read-all` | `NOTIFICATIONS_VIEW_OWN` | Bulk update filters recipient, tenant, and unread status. |
| `GET /api/customer/dashboard` | `DASHBOARD_CUSTOMER_VIEW` | All counts use authenticated customer ID plus tenant. |

Administrative job, dispatch, audit, and organization routes continue to require permissions the customer role does not hold. The customer role's existing RBAC set does not grant `JOBS_VIEW_ALL`, job management, dispatch, audit, or organization management.

## Regression coverage

`backend/tests/test_customer_portal_authorization.py` covers own job access, another customer's job, another tenant, altered authenticated identity, customer denial from an admin permission, rejecting client-supplied status/linkage fields, linked-job edit/cancel propagation using actual job state, and report ownership isolation.

## Review note

The linked service request is the tenant boundary for cross-provider jobs. Applying the customer's tenant directly to `Job.tenant_id` would hide legitimately routed jobs and is not the correct authorization predicate for this data model.
