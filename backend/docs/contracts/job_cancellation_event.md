# Job Cancellation Event Contract

## Event

`job-cancelled`

The `job-cancelled` event represents a successful authoritative job cancellation. It is published only after the cancellation transaction has been committed successfully.

## Topic

`fieldops.events`

The existing Kafka producer and canonical `MessageEnvelope` are used. Kafka is not the source of truth for the job lifecycle; the database cancellation transaction remains authoritative.

## Cancellation lifecycle

The bulk cancellation API validates the requested jobs and cancellation reason before mutation. Each valid cancellation uses the existing job status transition rules.

Supported cancellation transitions are governed by the existing `JobStatusMachine`. Terminal states that cannot be cancelled are rejected before the cancellation is persisted.

The cancellation reason is stored on the job as `cancellation_reason`. The authoritative cancellation timestamp and actor are persisted as `cancelled_at` and `cancelled_by`.

The Kafka event is prepared and scheduled only after the database transaction commits successfully.

## Event envelope

The event payload contains:

- `event_type`: `job-cancelled`
- `event_id`: deterministic value in the form `job-cancelled:{tenant_id}:{job_id}:{cancelled_at}`
- `job_id`: cancelled job identifier
- `tenant_id`: authenticated tenant identifier
- `cancelled_by`: actor that performed the cancellation
- `cancellation_reason`: persisted cancellation reason
- `cancelled_at`: authoritative persisted cancellation timestamp
- `schema_version`: `1`
- `timestamp`: UTC event publication timestamp
- `correlation_id`: optional value from the `X-Correlation-ID` request header

The event sender uses the dispatch identity and the existing event message type.

## Example payload

```json
{
  "event_type": "job-cancelled",
  "event_id": "job-cancelled:tenant-1:1001:2026-10-03T10:15:00+00:00",
  "job_id": "1001",
  "tenant_id": "tenant-1",
  "cancelled_by": "dispatcher-001",
  "cancellation_reason": "Customer requested cancellation",
  "cancelled_at": "2026-10-03T10:15:00+00:00",
  "schema_version": 1,
  "timestamp": "2026-10-03T10:15:01+00:00",
  "correlation_id": "cancel-correlation-123"
}