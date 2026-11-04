# CommunicationAgent Migration Documentation

This document describes the design, constructor contract, lifecycle management, and architectural responsibilities of the migrated `CommunicationAgent` within the FieldOps AI agent framework.

## BaseAgent Inheritance & Task Configuration
The `CommunicationAgent` inherits from the abstract base class `BaseAgent[CommunicationDecision]`.
- It validates that the configuration is specifically configured for communication tasks. A configuration whose `agent_type` is not `AITask.COMMUNICATION` is explicitly rejected in the constructor with a `ValueError`.
- It overrides the standard `timeout_seconds` settings via the YAML configuration defaults (configured to `5.0` seconds in `ai.yaml`).

## Constructor Contract
The constructor signature is:
```python
def __init__(
    self,
    config: AgentConfig,
    orchestrator: Optional[AIOrchestrator] = None,
) -> None
```
- It explicitly propagates the `AgentConfig` to `super().__init__(config)`.
- It preserves orchestrator dependency injection. The existing global `ai_orchestrator` is used only if `orchestrator` is `None` (using strict `is None` checking).

## Tenant Isolation & Validation
The agent runtime strictly enforces tenant isolation:
- `BaseAgent` validates that `tenant_id` is present in the execution dictionary and matches the configured tenant before `run()` is executed. Any mismatch raises a `TenantIsolationError`.
- `CommunicationContext` enforces `extra="forbid"`. Because `tenant_id` is lifecycle metadata, it must not be sent to the AI domain schema.
- In `run()`, the agent copies the context dictionary, safely removes `tenant_id`, and validates the remaining data with `CommunicationContext.model_validate(...)` before executing the orchestrator.

## Async Run Flow
The asynchronous run logic executes via:
```python
async def run(
    self,
    context: dict[str, Any],
) -> CommunicationDecision
```
- It converts context dictionary to a validated `CommunicationContext` schema.
- Because `AIOrchestrator.execute` is a synchronous call, it is offloaded using `asyncio.to_thread` to prevent blocking the async event loop.
- It invokes the orchestrator exactly once, passing:
  - `task=AITask.COMMUNICATION`
  - `context=validated_context.model_dump(mode="json")`
  - `response_schema=CommunicationDecision`
- It validates that the returned value is a `CommunicationDecision`.

## Synchronous Compatibility Limitation
The agent preserves a synchronous compatibility method:
```python
def generate(
    self,
    context: CommunicationContext,
) -> CommunicationDecision
```
- It rejects execution from an active event loop, raising a `RuntimeError` if called within one.
- It is operation-scoped and single-use: since lifecycle execution terminates the agent on exit, a terminated agent cannot be silently reused. Re-invoking `generate()` on a terminated agent raises an `AgentLifecycleError`.
- It adds the authoritative agent `tenant_id` to the execution dictionary.
- It executes through `AgentLifecycle` and `AgentPool`.
- It verifies `AgentResultStatus.SUCCESS` and checks that the result output is a `CommunicationDecision`.
- It makes exactly one orchestrator call and always tears down the agent through the lifecycle context manager.

## Operational Logging
To protect sensitive data, the agent enforces a zero-PII logging policy:
- **Never log**: Customer names, technician names, phone numbers, email addresses, locations, prompts, generated messages, raw provider responses, API keys, or exception text containing those values.
- **Allowed logging**: Safe operational metadata such as `agent_id`, `agent_type`, `channel`, `notification_type`, elapsed time, and `correlation_id`.

## Service & Architectural Boundaries
The communication subsystem enforces a strict division of responsibilities:
- **No side effects**: The `CommunicationAgent` never connects to databases, sends SMS/emails, makes real Groq/external API calls directly, or invokes WebSockets.
- **Service Ownership**: The `CommunicationService` remains the sole owner of PII sanitization (before calling the agent), guardrails pipeline validation, fallback rendering (Jinja2), placeholder restoration, and audit row persistence. The agent remains focused purely on producing a recommendation.

## Internal Agent Request Contract

Other FieldOps agents request recipient-facing copy through
`AgentCommunicationRequest` and `AgentCommunicationCoordinator` rather than
calling the model or a provider directly. A request identifies the allowed
requesting agent, a correlation/request ID, and a validated
`CommunicationContext`. The coordinator receives the trusted tenant ID from
the business service and delegates generation to `CommunicationService`.

The request only asks for safe copy. It cannot mutate a job, assign staff, or
send a message. The caller continues to use the existing channel/delivery
layer. The Sentiment Agent uses this contract for a customer acknowledgement
after creating a sentiment escalation; if safe generation is unavailable, it
uses a fixed factual acknowledgement and still follows the existing SMS
transport path.

## Inbound SMS and Tracked Delivery

The Twilio inbound webhook routes a uniquely identified customer message to
the tenant-scoped Customer Support graph, saves both sides of the exchange in
the customer's chat history, runs sentiment analysis, and queues the answer.
Technician SMS is associated only with an active job assigned to the verified
technician account; ambiguous job selection is clarified instead of guessed.
Job chat remains the source of truth for technician/customer history.

Outbound customer replies, sentiment acknowledgements, and technician
clarification prompts use `enqueue_tracked_sms`. It persists the notification
and `NotificationChannelDelivery` idempotency record before queueing the
existing Celery/Twilio task. Failed deliveries can be reclaimed on retry, and
queued or accepted deliveries are not sent twice.
Set `TWILIO_STATUS_CALLBACK_URL` to the publicly reachable
`/v1/webhooks/twilio-status` endpoint to update tracked rows when Twilio reports
`sent`, `delivered`, or `failed`; immediate provider acceptance and Celery
retry state remain tracked even when callbacks are not configured.

## Dispatcher Communication Center

Dispatchers and super admins can inspect the tenant-scoped automatic message
feed in the web Communication Center. The read-only
`GET /admin/communication-center` endpoint supports search, channel and status
filters, and pagination. The page refreshes every 30 seconds and can also be
refreshed manually.

Customer iOS/Android devices register their authenticated Expo push token at
`PUT /api/customer/notification-device`; clearing the preference unregisters
it with `DELETE /api/customer/notification-device`. Technician mobile devices
use the existing authenticated technician token route. The lifecycle graph
queues push alongside email/SMS only when the recipient has opted in and has a
registered device. Celery sends Expo tokens through Expo Push Service and
existing Firebase tokens through Firebase Admin; the delivery row records
provider acceptance or failure.

Job notifications are updated in place to keep one current in-app card per
recipient and job. External delivery rows from earlier event versions may
therefore reference that same current card. The feed matches external deliveries
to the card's current event version and returns only the newest tracked row per
channel, so old email/SMS states do not appear beside a newer message. Delivery
filters use those same current-event rows, and in-app read state comes from the
notification card.

# Technician-to-customer job chat lifecycle updates

The technician portal writes customer-visible lifecycle updates to the same
`job_messages` conversation used for two-way customer/technician chat:

- On the first successful technician acceptance, it posts that the technician
  accepted the job and will continue updates in chat.
- When the technician starts travel, it posts that they are on the way. If a
  fresh GPS position and route estimate are available, the message includes
  distance in kilometres and estimated travel time. If not, it says the estimate
  is pending fresh GPS data.
- When the technician marks arrival, pauses work, resumes work, or completes the
  job, it posts a clear automatic update in the conversation.
- These messages are persisted and broadcast over the existing job-message
  Socket.IO event. Retried accept/start requests do not create another message.
