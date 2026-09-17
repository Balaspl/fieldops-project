# Technician Job Completion API

## Endpoint

`POST /jobs/{job_id}/close`

This is the authoritative technician-facing API for completing a job with the final closure payload.

## Permission and ownership

- Requires an authenticated user with role `technician`.
- The tenant is taken from the authenticated user context; tenant IDs from request payloads or headers are not trusted.
- The job must belong to the authenticated tenant.
- The job must be assigned to the authenticated technician.
- Non-technicians receive `403`.
- Unknown or cross-tenant jobs receive `404`.

## Completion lifecycle

The endpoint does not directly assign `COMPLETED` to `Job.status`.

The service delegates the transition to the existing `JobStatusMachine`, preserving the existing lifecycle authority and transition rules. The normal technician completion transition is:

`ON_SITE -> COMPLETED`

The existing completion prerequisite requires a work report. The closure payload's `work_summary` is used as that report for this transaction.

Terminal states such as `COMPLETED`, `CANCELLED`, and `CLOSED` are rejected.

## Request body

```json

{
  "work_summary": "Replaced faulty capacitor and completed repair.",
  "work_report": {
    "summary": "Replaced faulty capacitor and completed repair.",
    "parts_used": ["Capacitor"],
    "duration_minutes": 90
  },
  "checklist": {
    "items": [
      {
        "id": "power",
        "label": "Power supply checked",
        "status": "COMPLETED",
        "required": true
      },
      {
        "id": "safety",
        "label": "Safety inspection completed",
        "status": "COMPLETED",
        "required": true
      },
      {
        "id": "cleanup",
        "label": "Work area cleaned",
        "status": "INCOMPLETE",
        "required": false
      }
    ]
  },
  "before_images": ["/uploads/before.jpg"],
  "after_images": ["/uploads/after.jpg"],
  "labour_cost": 150.0,
  "material_cost": 75.5
}
```

Validation occurs before lifecycle mutation:

- `work_summary` is the completion-note input and must be non-empty after trimming.
- Completion notes are limited to 5000 characters after trimming.
- Completion notes are stored as plain text; HTML-like markup tags are rejected.
- Meaningful special characters and internal whitespace are preserved.
- At least one `after_images` item is required.
- Labour and material costs cannot be negative.

The trimmed `work_summary` is the canonical completion-notes value. The API
exposes it both as `work_summary` for backward compatibility and as
`completion_notes` for history/reporting consumers. No separate database column
is introduced; both fields resolve to the same persisted `JobClosure.work_summary`
value.

Invalid request bodies return `400` responses according to the project's global validation handler.

## Completion checklist

The optional `checklist` contains the completion steps acknowledged by the
technician.

Each checklist item contains:

- `id`: Unique identifier for the submitted checklist item.
- `label`: Human-readable description of the completion step.
- `status`: Either `COMPLETED` or `INCOMPLETE`.
- `required`: Indicates whether the item must be completed before the job can
  be completed.

Checklist rules:

- Required items must have status `COMPLETED`.
- Optional items may remain `INCOMPLETE`.
- Checklist validation occurs before job state mutation.
- If required items are incomplete, the completion request returns `400`.
- The response identifies the incomplete required items using the
  `INCOMPLETE_CHECKLIST` error code.
- The submitted checklist is persisted with the `JobClosure`.
- Checklist data is stored as part of the closure record; no separate
  checklist table is created.
- Because the current completion flow does not maintain a server-side
  checklist catalogue, submitted item IDs are treated as the checklist
  definition for that completion request. Malformed checklist items are
  rejected by request validation.

## Transaction behavior

The following database changes are committed atomically:

1. Job lifecycle transition to `COMPLETED`.
2. Canonical `JobClosure` creation.
3. `JOB_COMPLETED` `AuditEvent` creation.
4. Technician availability/current-job updates.

The job row is selected with a row lock where supported by the database to reduce concurrent duplicate completion races.

On a database failure, the transaction is rolled back and no false completion state is persisted.

## Event behavior

After the database transaction commits, the service publishes a `JOB_COMPLETED` dispatch event through the existing Redis event publisher.

Redis publication is intentionally post-commit. A Redis failure does not roll back an already committed database completion or convert it into a false API failure.

## Response

The endpoint returns the canonical `JobClosureResponse`. The response includes the closure ID, job ID, technician ID, completion summary, images, costs, subtotal, and completion timestamps.

Example core completion fields:

```json
{
  "status": "COMPLETED",
  "job_id": 1001,
  "completion_id": 501,
  "completed_at": "2026-09-10T12:15:00Z"
}
```

The current API response model also returns the persisted closure details.

## Failure behavior

| Condition | HTTP status |
|---|---:|
| Missing/invalid authentication | `401` |
| Authenticated non-technician | `403` |
| Job not found in authenticated tenant | `404` |
| Job assigned to another technician | `403` |
| Terminal or duplicate completion | `400` |
| Invalid lifecycle transition/prerequisite | `400` |
| Invalid completion payload | `400` |
| Required checklist items incomplete | `400` |
| Database failure | `500` |

For an incomplete required checklist, the error response uses the following
structure:

```json
{
  "error": "INCOMPLETE_CHECKLIST",
  "message": "Required checklist items are incomplete",
  "incomplete_items": [
    {
      "id": "safety",
      "label": "Safety inspection completed"
    }
  ]
}
