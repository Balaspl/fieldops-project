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
  "before_images": ["/uploads/before.jpg"],
  "after_images": ["/uploads/after.jpg"],
  "labour_cost": 150.0,
  "material_cost": 75.5
}
```

Validation occurs before lifecycle mutation:

- `work_summary` must be non-empty.
- At least one `after_images` item is required.
- Labour and material costs cannot be negative.

Invalid request bodies return `400` responses according to the project's global validation handler.

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
| Database failure | `500` |
