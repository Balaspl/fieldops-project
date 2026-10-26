# Customer support chat

The authenticated customer portal mounts the floating support widget once in `App.tsx`; technician and staff sessions do not render it. The browser uses the existing `services/api.ts` client, including its established bearer or HttpOnly-cookie authentication and refresh behavior. Ten default quick questions stay in a separate section above the composer. Minimizing preserves a conversation. Closing deletes that chat conversation and its messages without deleting service requests. A saved conversation can be restored after a browser refresh until it is closed.

## API

- `POST /api/v1/customer/chat` — `{ "message": "...", "conversation_id": "<uuid-or-null>", "client_message_id": "<uuid>" }`. Returns `{ "conversation_id", "answer", "intent", "sources", "escalation" }`.
- `GET /api/v1/customer/chat/conversations` — list the caller's conversations.
- `POST /api/v1/customer/chat/conversations` — create a conversation; optional `{ "title": "..." }`.
- `GET /api/v1/customer/chat/conversations/{conversation_id}` — retrieve authorized history.
- `DELETE /api/v1/customer/chat/conversations/{conversation_id}` deletes this customer chat and its messages.
- `GET /api/v1/admin/customer-support/faqs` — list tenant and shared FAQ entries for a super admin.
- `POST /api/v1/admin/customer-support/faqs` and `PATCH /api/v1/admin/customer-support/faqs/{faq_id}` — create or update tenant FAQ content, including publication status. Shared FAQs are read-only to tenant administrators.

Messages are limited to 4,000 characters. Send requests are rate limited to 20 per authenticated customer and 1,000 per tenant per minute through the existing Redis rate limiter. Reuse the client message UUID when retrying an ambiguous request to prevent duplicate customer messages.

## Setup

Apply the new migration through the existing Alembic setup from `backend` after setting the usual `DATABASE_URL`:

```powershell
alembic upgrade head
```

No new environment variable or provider is required. Apply migrations through the current head to seed shared, published FAQs and persist structured reply components. FAQ retrieval normalizes common spelling and plural variants, filters by intent-compatible category, ranks canonical and alternate questions above keywords, applies a relevance threshold, and asks for clarification when top matches are tied. Generic one-word matches are rejected. High-confidence FAQ replies use the approved answer directly, avoiding an unnecessary generation call. The existing FieldOps orchestrator remains available for evidence-grounded generation where needed. Recent messages in the same authenticated conversation are supplied to resolve follow-up references. Live job facts are queried from PostgreSQL on each request.



## FAQ and intent audit map

| Canonical topic | Intent | Approved source | Answer behavior |
| --- | --- | --- | --- |
| What is FieldOps used for? | `fieldops_overview` | Shared `fieldops_overview` FAQ | Explain customer portal capabilities; do not describe the service selector as the platform's purpose. |
| What services does FieldOps offer? | `service_catalog` | Customer request form's eight service choices | Return the current catalog. |
| How do I create a service request? | `service_creation` | Shared FAQ and customer Service Requests page | Explain how to open the form and submit its required fields. |
| What information is required? / What happens after submission? / My request is missing | `request_information`, `request_history`, or `general_faq` | Shared FAQs and request form/list | Explain verified form requirements and the account-scoped request list; do not claim unverified dispatch events. |
| What is my request status? / Why is it delayed or unassigned? | `job_status` or `delays_reassignment` | Tenant and customer-scoped `ServiceRequest` / `Job` rows | Read current status only; do not invent assignment history or delay reasons. |
| When will my technician arrive? / Where is my technician? | `appointment` or `technician_tracking` | Customer-scoped job and fresh ETA history | Return preferred date and a fresh ETA when available; chat does not expose a technician's precise location or identity. |
| What does In Progress mean? | `status_explanation` | Shared status FAQ | Explain the status without querying a customer's jobs. |
| How are appointments scheduled? | `appointment_process` | Shared preferred-date FAQ and request form | Explain that the entered date is preferred, not a confirmed appointment time. |
| How do notifications work? | `notifications` | Shared FAQ and customer notification settings | Describe the Notifications area and account-configured channel preferences. |
| What is a closure report? / How do I download one? | `closure_report_explanation` or `job_completion` | Shared FAQ or customer-scoped `JobClosure` row | Explain reports generally, or check availability and offer download for the customer's job. |
| Account or portal problem / human support | `account_support` or `support_escalation` | Existing Support page | Direct the customer to Support; do not claim a case was created. |
| Unclear question | `unknown` or `general_faq` | No source unless a compatible FAQ clears the threshold | Ask for clarification or use the existing safe fallback. |

## Safety behavior

Conversation and job queries are scoped to the signed-in customer's user and tenant IDs. Live job responses omit technician identity/location and expose a fresh ETA only when the authoritative ETA history has a calculation less than five minutes old. Structured cards contain verified job fields and predefined navigation actions; generated model content cannot provide a URL or operation. FAQ answers reflect the portal's configured service types, preferred date field, request status, notifications, and closure report flow. Booking mutations and outbound customer messaging are not exposed. Unsupported requests direct customers to the existing Support page.
