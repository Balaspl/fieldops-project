# Sentiment Agent

## Purpose

The Sentiment Agent reads a customer or technician message and returns a structured assessment for FieldOps workflows. It identifies the overall tone and dominant emotion, estimates business urgency, recommends human intervention when appropriate, and gives a short factual summary.

The agent is read-only. It does not reply to customers, change job priority, assign or dispatch technicians, write database records, or send notifications. Business services own persistence, escalation, and follow-up actions.

## Input and output

The input is a `SentimentContext`: channel, message, language, and up to three previous messages. Supported channels are `EMAIL`, `SMS`, `CHAT`, `WHATSAPP`, `PORTAL`, `SUPPORT_TICKET`, `DISPATCH_NOTE`, `JOB_CHAT`, `SUPPORT_CHAT`, `JOB_FEEDBACK`, and `SUPPORT_CASE`. Supported languages are English (`en`), Spanish (`es`), Tamil (`ta`), and Hindi (`hi`). The orchestrator sanitizes PII before sending the request to the provider.

The output is a `SentimentDecision` containing:

- Sentiment: `POSITIVE`, `NEUTRAL`, `NEGATIVE`, or `MIXED`.
- One dominant emotion, such as `CALM`, `HAPPY`, `CONCERNED`, `FRUSTRATED`, or `ANGRY`.
- Urgency: `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`.
- Impact severity, distinct from urgency, and up to five issue categories such as technician delay, communication, service quality, safety, or billing.
- `requires_human`, a recommendation for human review.
- A confidence score from 0 to 1, a short factual summary, and a suggested next action for staff.

Use `MIXED` only when the emotional tone has both positive and negative signals. Base the assessment only on the supplied message and conversation context; do not infer missing facts. Human review is especially important for safety or legal concerns, manager requests, severe anger, repeated unresolved complaints, or low-confidence analysis.

## Runtime flow

`SentimentAgent` implements the shared `BaseAgent` contract and calls the AI orchestrator with the `SENTIMENT` task and `SentimentDecision` response schema. `SentimentEngine` is the synchronous compatibility path and uses keyword-based fallback analysis when the provider fails. `SentimentService` and `SentimentIntegration` adapt application workflows to the engine.

Customer-authored messages in web or mobile job chat and customer support chat, written job feedback, submitted support requests, customer-authored support case updates, and inbound SMS are analyzed. Feedback includes the star rating as context; rating-only feedback without a comment is not sent for text analysis. Each background task opens its own database session and stores results against the tenant, customer, and source identity, which prevents duplicate analysis when a task is redelivered. Chat-created support cases are not analyzed twice because their messages already have individual assessments. Inbound SMS uses the provider message ID for deduplication and is analyzed even if the customer has no active job. The real-time scorer owns persistence and downstream escalation/retention workflows; those side effects belong to the service layer, not the agent. Customer chat messages are not automatically answered by the escalation workflow.

Staff can view recent analyses and the existing escalation feed from the web app's **Sentiment Intelligence** page. The tenant-scoped endpoint is `GET /admin/sentiment/dashboard/analyses`; the existing dashboard bundle supplies metrics and active escalations. Apply the database change with `alembic upgrade head`. On Windows, run a single-process Celery worker for the analysis queue with `celery -A app.celery_app:celery_app worker --pool=solo --loglevel=info` from the backend directory. On Linux, the default worker pool is suitable.

## Source files

- Agent: `app/services/ai/FieldOpsAI/agents/sentiment_agent.py`
- Prompt: `app/services/ai/FieldOpsAI/prompts/sentiment.md`
- Schemas: `app/services/ai/FieldOpsAI/schemas/sentiment.py`
- Compatibility engine and service: `app/services/ai/FieldOpsAI/agents/sentiment_engine.py` and `app/services/ai/FieldOpsAI/services/sentiment_service.py`
- Real-time workflow: `app/services/ai/FieldOpsAI/services/realtime_sentiment.py`
- Background tasks: `app/sentiment/job_message_tasks.py` (job chat, support chat, job feedback, and support cases)
- Staff page: `frontend/src/pages/SentimentIntelligencePage.tsx`
