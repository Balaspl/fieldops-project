
"""LangGraph pipeline for the Communication Agent.

Flow:
    START -> load -> one compose branch per recipient -> dispatch -> END

Responsibilities:
- Load the job, technician and notification recipients.
- Compose and validate notification messages.
- Persist notifications using a caller-supplied event_version.
- Skip stale events that do not update an existing notification.
- Publish live updates only after the database commit.
- Queue SMS and email through the existing delivery helpers.

Important:
- The event producer must allocate and persist event_version before invoking
  this graph.
- Never generate event_version inside the graph or a retrying Celery task.
- Only load() and dispatch() access the database session. compose() is pure.
"""

import logging
import os
import operator
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Annotated, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

try:
    from langgraph.types import Send
except ImportError:
    from langgraph.constants import Send

from app.models_legacy import ETAHistory, InAppNotification, Job, Technician
from app.models.job_closure import JobClosure
from app.models.payment_status import JobPaymentStatus
from app.services.invoice_service import invoice_summary

from .channels import (
    claim_delivery,
    enqueue_email,
    enqueue_sms,
    external_channels_enabled,
    idem_key,
    mark_delivery,
    normalize_phone,
    push_live,
)
from .events import EMAIL, IN, SMS, JobEvent
from .message import build_card, build_copy, personalize_customer_title
from .recipients import Recipient, resolve_recipients
from .store import upsert_notification
from .texts import (
    email_content,
    sms_text,
    tracking_link,
    validate_text,
)

logger = logging.getLogger(__name__)


def _log_exception_safely(message: str, *args, **kwargs) -> None:
    """Keep logging-handler failures from replacing a notification error."""
    try:
        logger.exception(message, *args, **kwargs)
    except Exception:
        # Logging is diagnostic only; preserve the original operation result.
        pass


# ---------------------------------------------------------------------------
# State definitions
# ---------------------------------------------------------------------------

class CommState(TypedDict, total=False):
    job_id: int
    event: str
    event_version: int
    technician_id: int | None
    correlation_id: str | None

    job: dict | None
    technician: dict | None
    recipients: list[dict]

    # Messages produced by parallel compose branches are merged into this list.
    messages: Annotated[list[dict], operator.add]

    notification_ids: list[str]


class ComposeInput(TypedDict):
    event: str
    event_version: int
    job: dict
    technician: dict | None
    recipient: dict
    correlation_id: str | None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_event_version(value: object) -> int:
    """Require the persisted positive integer supplied by the event producer."""
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 1
    ):
        raise ValueError(
            "Communication Agent requires a persisted positive event_version"
        )

    return value


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def load(state: CommState, config: RunnableConfig) -> dict:
    """Load the job, associated technician and notification recipients."""
    event_version = _validate_event_version(
        state.get("event_version")
    )

    job_id = state.get("job_id")
    event_value = state.get("event")

    if not isinstance(job_id, int) or isinstance(job_id, bool):
        raise ValueError("Communication Agent requires a valid job_id")

    if not isinstance(event_value, str) or not event_value:
        raise ValueError("Communication Agent requires an event")

    db = config["configurable"]["db"]

    job = db.get(Job, job_id)

    if not job:
        logger.warning(
            "Communication Agent: job not found job_id=%s version=%s",
            job_id,
            event_version,
        )
        return {
            "job": None,
            "technician": None,
            "recipients": [],
        }

    tech_pk = (
        state.get("technician_id")
        or job.assigned_technician_id
    )

    technician = (
        db.get(Technician, tech_pk)
        if tech_pk
        else None
    )

    latest_eta = (
        db.query(ETAHistory)
        .filter(ETAHistory.job_id == job.id)
        .order_by(ETAHistory.calculated_at.desc())
        .first()
    )
    eta_minutes = None
    eta_updated_at = None
    if latest_eta and latest_eta.calculated_at and latest_eta.eta:
        calculated_at = latest_eta.calculated_at
        if calculated_at.tzinfo is None:
            calculated_at = calculated_at.replace(tzinfo=timezone.utc)
        age_seconds = (
            datetime.now(timezone.utc) - calculated_at.astimezone(timezone.utc)
        ).total_seconds()
        if 0 <= age_seconds <= 15 * 60:
            eta_updated_at = calculated_at.astimezone(timezone.utc).isoformat()
            eta = latest_eta.eta
            if eta.tzinfo is None:
                eta = eta.replace(tzinfo=timezone.utc)
            eta_minutes = max(
                0,
                round(
                    (eta.astimezone(timezone.utc) - datetime.now(timezone.utc))
                    .total_seconds()
                    / 60
                ),
            )

    if tech_pk and technician is None:
        logger.warning(
            "Communication Agent: technician not found job_id=%s technician_id=%s",
            job_id,
            tech_pk,
        )

    event = JobEvent(event_value)

    recipients = resolve_recipients(
        db,
        job,
        event,
        technician,
    )

    closure = None
    payment = None
    invoice_data = None
    if event == JobEvent.INVOICE_READY:
        closure = (
            db.query(JobClosure)
            .filter(
                JobClosure.job_id == job.id,
                JobClosure.tenant_id == job.tenant_id,
            )
            .order_by(JobClosure.completed_at.desc(), JobClosure.id.desc())
            .first()
        )
        if not closure or str(job.status).upper() != "COMPLETED":
            logger.warning(
                "Communication Agent skipped invoice notice without persisted completion",
                extra={"job_id": str(job.id), "event_type": event.value},
            )
            recipients = []
        else:
            try:
                invoice_data = invoice_summary(job, closure)
            except ValueError:
                logger.warning(
                    "Communication Agent skipped invoice notice with incomplete totals",
                    extra={"job_id": str(job.id), "event_type": event.value},
                )
                recipients = []
                closure = None

        if closure:
            payment = (
                db.query(JobPaymentStatus)
                .filter(
                    JobPaymentStatus.job_id == job.id,
                    JobPaymentStatus.tenant_id == job.tenant_id,
                    JobPaymentStatus.invoice_id == closure.id,
                )
                .first()
            )

    expires = job.share_token_expires_at
    frontend_base_url = os.getenv("FRONTEND_BASE_URL", "").rstrip("/")
    invoice_link = (
        f"{frontend_base_url}/?tab=cust_invoices"
        if closure and frontend_base_url
        else None
    )
    if event == JobEvent.INVOICE_READY and not invoice_link:
        logger.error(
            "Invoice email suppressed because FRONTEND_BASE_URL is not configured",
            extra={"job_id": str(job.id), "tenant_id": str(job.tenant_id)},
        )
        for recipient in recipients:
            if recipient.role == "customer":
                recipient.channels = [
                    channel for channel in recipient.channels if channel != EMAIL
                ]

    job_data = {
        "id": job.id,
        "tenant_id": job.tenant_id,
        "service_type": job.service_type,
        "location": job.location,
        "eta_min": eta_minutes,
        "eta_updated_at": eta_updated_at,
        "customer_name": job.customer_name,
        "technician_name": technician.technician_name if technician else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "preferred_service_date": (
            job.preferred_service_date.isoformat()
            if job.preferred_service_date else None
        ),
        "preferred_time": getattr(job, "preferred_time", None),
        "status": str(job.status or "").upper(),
        "completed_at": (
            closure.completed_at.isoformat()
            if closure and closure.completed_at
            else job.completed_at.isoformat() if job.completed_at else None
        ),
        "cancellation_reason": getattr(job, "cancellation_reason", None),
        "work_report": getattr(job, "work_report", None),
        "closure_id": closure.id if closure else None,
        "invoice_number": invoice_data["invoice_number"] if invoice_data else None,
        "currency": invoice_data["currency"] if invoice_data else None,
        "invoice_total": invoice_data["total_amount"] if invoice_data else None,
        "payment_status": (
            str(payment.status).upper()
            if payment and payment.status else "UNAVAILABLE"
        ),
        "invoice_link": invoice_link,
        "share_token": job.share_token,
        "share_expires": (
            expires.isoformat()
            if expires
            else None
        ),
    }

    # Keep the technician's own tenant and stable recipient ID in graph state.
    # A dispatched job may belong to a different tenant, so never derive the
    # technician notification tenant from job.tenant_id.
    technician_data = (
        {
            "technician_name": technician.technician_name,
            "tech_id": str(technician.tech_id),
            "tenant_id": str(technician.tenant_id),
        }
        if technician
        else None
    )

    logger.info(
        "Communication Agent loaded job and recipients",
        extra={
            "job_id": str(job.id),
            "event_type": event.value,
            "event_version": event_version,
            "recipient_count": len(recipients),
            "recipient_roles": sorted({r.role for r in recipients}),
            "correlation_id": state.get("correlation_id"),
        },
    )

    return {
        "job": job_data,
        "technician": technician_data,
        "recipients": [
            asdict(recipient)
            for recipient in recipients
        ],
    }


def fan_out(state: CommState):
    """Create one independent compose branch for each recipient."""
    if not state.get("job"):
        return END

    sends = [
        Send(
            "compose",
            {
                "event": state["event"],
                "event_version": state["event_version"],
                "job": state["job"],
                "technician": state.get("technician"),
                "recipient": recipient,
                "correlation_id": state.get("correlation_id"),
            },
        )
        for recipient in state.get("recipients", [])
    ]

    return sends if sends else END


def _validated_recipient(
    raw_recipient: dict,
    technician_data: dict | None,
) -> Recipient | None:
    """Validate recipient identity and tenant before any notification write.

    Technician notifications must target the exact technician loaded for this
    event and use that technician's tenant. Cross-tenant job assignment remains
    supported: job.tenant_id is intentionally not compared to this tenant.
    """
    try:
        recipient = Recipient(**raw_recipient)
    except (TypeError, ValueError) as exc:
        logger.warning("Communication Agent: invalid recipient payload: %s", exc)
        return None

    if not recipient.role or not recipient.id or not recipient.tenant_id:
        logger.warning("Communication Agent: recipient missing role/id/tenant")
        return None

    if recipient.role.lower() == "technician":
        if not technician_data:
            logger.warning(
                "Communication Agent: skipping technician recipient without "
                "validated technician context recipient_id=%s",
                recipient.id,
            )
            return None

        expected_id = str(technician_data.get("tech_id") or "")
        expected_tenant = str(technician_data.get("tenant_id") or "")
        if (
            not expected_id
            or not expected_tenant
            or str(recipient.id) != expected_id
            or str(recipient.tenant_id) != expected_tenant
        ):
            logger.error(
                "Communication Agent: technician recipient identity/tenant "
                "mismatch recipient_id=%s recipient_tenant=%s "
                "expected_id=%s expected_tenant=%s",
                recipient.id,
                recipient.tenant_id,
                expected_id,
                expected_tenant,
            )
            return None

    return recipient


def _generate_customer_copy(
    event,
    recipient,
    job,
    technician,
    event_version=None,
    correlation_id=None,
):
    """Generate contextual customer copy; use approved local copy on failure."""
    fallback = build_copy(event, recipient, job, technician, event_version)

    try:
        from app.services.ai.FieldOpsAI.agents.communication_agent import (
            CommunicationAgent,
        )
        from app.services.ai.FieldOpsAI.config.agent_config_manager import (
            AgentConfigManager,
        )
        from app.services.ai.FieldOpsAI.schemas.ai_task import AITask
        from app.services.ai.FieldOpsAI.schemas.communication import (
            CommunicationContext,
            CommunicationRecipient,
        )

        status_by_event = {
            JobEvent.JOB_CREATED: "CREATED",
            JobEvent.TECHNICIAN_ASSIGNED: "ASSIGNED",
            JobEvent.INVOICE_READY: "COMPLETED",
            JobEvent.TECHNICIAN_ACCEPTED: "ASSIGNED",
            JobEvent.TECHNICIAN_REJECTED: "CREATED",
            JobEvent.DELAYED: "EN_ROUTE",
            JobEvent.EN_ROUTE: "EN_ROUTE",
            JobEvent.ON_SITE: "ON_SITE",
            JobEvent.SERVICE_STARTED: "IN_PROGRESS",
            JobEvent.COMPLETED: "COMPLETED",
            JobEvent.CANCELLED: "CANCELLED",
            JobEvent.CLOSED: "COMPLETED",
        }
        technician_name = (
            technician.technician_name
            if technician and technician.technician_name
            else None
        )
        facts = [f"Confirmed job event: {event.value}."]
        eta_minutes = getattr(job, "eta_min", None)
        if job.service_type:
            facts.append(f"Service: {job.service_type}.")
        if technician_name:
            facts.append(f"Assigned technician: {technician_name}.")
        if event == JobEvent.EN_ROUTE:
            facts.append("The technician has started travelling to the customer.")
            if eta_minutes is not None:
                facts.append(
                    f"The latest live estimate is about {eta_minutes} minutes away."
                )
        elif event == JobEvent.ON_SITE:
            facts.append("The technician has arrived at the service location.")
        elif event == JobEvent.DELAYED:
            facts.append("The trip is delayed; no new arrival time is confirmed.")

        context = CommunicationContext(
            job_id=str(job.id),
            correlation_id=correlation_id,
            notification_type=event.value,
            recipient_type=CommunicationRecipient.CUSTOMER,
            channel="IN_APP",
            locale="en",
            customer_name=(
                recipient.name.strip()
                if recipient.name and recipient.name.strip()
                else None
            ),
            technician_name=technician_name,
            job_status=status_by_event[event],
            job_title=job.service_type or None,
            eta=(
                f"about {eta_minutes} minutes"
                if eta_minutes is not None
                else None
            ),
            additional_context=" ".join(facts),
        )
        config = AgentConfigManager().resolve(
            agent_type=AITask.COMMUNICATION,
            tenant_id=str(recipient.tenant_id),
        )
        agent = CommunicationAgent(config=config)
        decision = agent.generate(context)
        output = decision.output
        if output.channel != "PORTAL":
            logger.warning(
                "Communication Agent output channel rejected; using approved fallback",
                extra={
                    "job_id": str(job.id),
                    "event_type": event.value,
                    "event_version": event_version,
                    "recipient_role": recipient.role,
                    "recipient_tenant_id": recipient.tenant_id,
                    "output_channel": output.channel,
                    "fallback_reason": "channel_mismatch",
                    "generation_source": "approved_fallback",
                    "correlation_id": correlation_id,
                },
            )
            return fallback

        title = (output.title or fallback[0]).strip()
        title = personalize_customer_title(event, title, technician)
        body = output.body.strip()
        action_prompt = {
            JobEvent.TECHNICIAN_ACCEPTED: "Open the job card for the latest details 👀",
            JobEvent.EN_ROUTE: "Tap Track live to follow the visit 👀",
            JobEvent.COMPLETED: "When you're ready, tell us how it went ⭐",
        }.get(event)
        if action_prompt and action_prompt.casefold() not in body.casefold():
            body = f"{body} {action_prompt}"
        valid, _ = validate_text(title, body)
        if not valid or not body:
            logger.warning(
                "Communication Agent output validation failed; using approved fallback",
                extra={
                    "job_id": str(job.id),
                    "event_type": event.value,
                    "event_version": event_version,
                    "recipient_role": recipient.role,
                    "recipient_tenant_id": recipient.tenant_id,
                    "fallback_reason": "text_validation",
                    "generation_source": "approved_fallback",
                    "correlation_id": correlation_id,
                },
            )
            return fallback
        logger.info(
            "Communication Agent produced customer copy",
            extra={
                "job_id": str(job.id),
                "event_type": event.value,
                "event_version": event_version,
                "recipient_role": recipient.role,
                "correlation_id": correlation_id,
                "generation_source": (
                    "approved_fallback"
                    if agent.last_generation_used_fallback
                    else "ai"
                ),
                "used_fallback": agent.last_generation_used_fallback,
            },
        )
        return title, body
    except Exception:
        logger.exception(
            "Communication Agent generation failed; using approved customer copy "
            "job_id=%s event=%s correlation_id=%s",
            job.id, event.value, correlation_id,
            extra={
                "job_id": str(job.id),
                "event_type": event.value,
                "event_version": event_version,
                "recipient_role": recipient.role,
                "recipient_tenant_id": recipient.tenant_id,
                "fallback_reason": "generation_exception",
                "generation_source": "approved_fallback",
                "correlation_id": correlation_id,
            },
        )
        return fallback


def compose(state: ComposeInput) -> dict:
    """Build and validate notification content without database access."""
    event = JobEvent(state["event"])
    correlation_id = state.get("correlation_id")

    recipient = _validated_recipient(
        state["recipient"],
        state.get("technician"),
    )
    if recipient is None:
        return {"messages": []}

    job = SimpleNamespace(**state["job"])

    technician = (
        SimpleNamespace(**state["technician"])
        if state.get("technician")
        else None
    )

    if recipient.role == "customer":
        title, body = _generate_customer_copy(
            event,
            recipient,
            job,
            technician,
            state.get("event_version"),
            state.get("correlation_id"),
        )
    else:
        title, body = build_copy(
            event,
            recipient,
            job,
            technician,
            state.get("event_version"),
        )

    valid, reason = validate_text(title, body)

    if not valid:
        logger.warning(
            "Communication Agent: copy rejected reason=%s job_id=%s",
            reason,
            job.id,
        )

        title = f"Job #{job.id} update"
        body = "There is an update on your job."

    link = tracking_link(job)

    card = build_card(
        event,
        job,
        technician,
    )

    sms_message = (
        sms_text(title, body, link)
        if SMS in recipient.channels
        else None
    )

    email_message = (
        email_content(title, body, job, link, event)
        if EMAIL in recipient.channels
        else None
    )

    return {
        "messages": [
            {
                "recipient": state["recipient"],
                "title": title,
                "body": body,
                "card": card,
                "sms": sms_message,
                "email": email_message,
            }
        ]
    }


def dispatch(
    state: CommState,
    config: RunnableConfig,
) -> dict:
    """Persist notification cards, then publish and queue delivery."""
    event_version = _validate_event_version(
        state.get("event_version")
    )
    correlation_id = state.get("correlation_id") or str(uuid.uuid4())

    db = config["configurable"]["db"]

    event = JobEvent(state["event"])

    if not state.get("job"):
        return {"notification_ids": []}

    job = SimpleNamespace(**state["job"])

    allowed_channels = external_channels_enabled()

    notification_ids: list[str] = []

    for message in state.get("messages", []):
        recipient = _validated_recipient(
            message.get("recipient", {}),
            state.get("technician"),
        )
        if recipient is None:
            logger.warning(
                "Communication Agent skipped invalid recipient",
                extra={
                    "job_id": str(job.id),
                    "event_type": event.value,
                    "event_version": event_version,
                    "correlation_id": correlation_id,
                },
            )
            continue

        if EMAIL in recipient.channels and EMAIL not in allowed_channels:
            logger.info(
                "Email delivery skipped",
                extra={"job_id": str(job.id), "event_type": event.value,
                       "event_version": event_version,
                       "recipient_role": recipient.role,
                       "reason": "email_channel_disabled_in_communication_settings"},
            )

        pending_deliveries: list[tuple[str, int]] = []
        replay_group_key = (
            f"invoice_{job.id}"
            if event == JobEvent.INVOICE_READY
            else f"job_{job.id}"
        )
        existing_version = None
        if hasattr(db, "query"):
            existing_version = (
                db.query(InAppNotification.event_version)
                .filter(
                    InAppNotification.tenant_id == recipient.tenant_id,
                    InAppNotification.recipient_role == recipient.role,
                    InAppNotification.recipient_id == recipient.id,
                    InAppNotification.group_key == replay_group_key,
                )
                .scalar()
            )
        is_replay = existing_version == event_version

        # ---------------------------------------------------------------
        # 1. Persist the card with the supplied event version.
        # ---------------------------------------------------------------
        try:
            notification_id = upsert_notification(
                db,
                recipient,
                job,
                event,
                message["title"],
                message["body"],
                message["card"],
                version=event_version,
            )

            # A None result means the upsert did not insert or update a card.
            # In particular, a stale event must not produce a live push.
            if notification_id is None:
                db.rollback()

                logger.info(
                    "Communication Agent skipped stale or duplicate notification",
                    extra={
                        "job_id": str(job.id),
                        "event_type": event.value,
                        "event_version": event_version,
                        "recipient_role": recipient.role,
                        "recipient_tenant_id": recipient.tenant_id,
                        "correlation_id": correlation_id,
                    },
                )

                continue

            # Claim external delivery rows only after a card was persisted.
            for channel in (SMS, EMAIL):
                if (
                    channel in recipient.channels
                    and channel in allowed_channels
                ):
                    delivery_id = claim_delivery(
                        db,
                        tenant_id=recipient.tenant_id,
                        notification_id=notification_id,
                        channel=channel,
                        recipient_id=recipient.id,
                        key=idem_key(
                            job.id,
                            event,
                            recipient,
                            channel,
                            event_version,
                        ),
                    )

                    if delivery_id:
                        pending_deliveries.append(
                            (channel, delivery_id)
                        )

            # Commit before publishing any live notification.
            db.commit()

        except Exception:
            try:
                db.rollback()
            except Exception:
                # A rollback error must not replace the notification failure.
                _log_exception_safely(
                    "Communication Agent rollback failed after notification error",
                    extra={
                        "job_id": str(job.id),
                        "event_type": event.value,
                        "event_version": event_version,
                        "recipient_role": recipient.role,
                        "recipient_tenant_id": recipient.tenant_id,
                        "correlation_id": correlation_id,
                    },
                )

            _log_exception_safely(
                "Communication Agent: notification save failed "
                "job_id=%s event=%s role=%s version=%s correlation_id=%s",
                job.id, event.value, recipient.role, event_version, correlation_id,
                extra={
                    "job_id": str(job.id),
                    "event_type": event.value,
                    "event_version": event_version,
                    "recipient_role": recipient.role,
                    "recipient_tenant_id": recipient.tenant_id,
                    "correlation_id": correlation_id,
                },
            )

            continue

        notification_ids.append(notification_id)
        logger.info(
            "Communication Agent notification committed",
            extra={
                "job_id": str(job.id),
                "event_type": event.value,
                "event_version": event_version,
                "recipient_role": recipient.role,
                "recipient_tenant_id": recipient.tenant_id,
                "correlation_id": correlation_id,
            },
        )

        # ---------------------------------------------------------------
        # 2. Publish the live update only after the commit.
        # ---------------------------------------------------------------
        if IN in recipient.channels and not is_replay:
            try:
                push_live(
                    recipient.role,
                    recipient.tenant_id,
                    job.id,
                    {
                        "type": "notification",
                        "id": notification_id,
                        "group_key": f"job_{job.id}",
                        "job_id": str(job.id),
                        "recipient_role": recipient.role,
                        "recipient_id": recipient.id,
                        "event": event.value,
                        "event_version": event_version,
                        "title": message["title"],
                        "body": message["body"],
                        "status": "UNREAD",
                        "metadata": message["card"],
                    },
                    correlation_id=correlation_id,
                )
                logger.info(
                    "Communication Agent published live notification",
                    extra={
                        "job_id": str(job.id),
                        "event_type": event.value,
                        "event_version": event_version,
                        "recipient_role": recipient.role,
                        "recipient_tenant_id": recipient.tenant_id,
                        "correlation_id": correlation_id,
                    },
                )

            except Exception:
                # A push failure must not undo the committed notification.
                logger.exception(
                    "Communication Agent: live push failed "
                    "job_id=%s notification_id=%s version=%s correlation_id=%s",
                    job.id, notification_id, event_version, correlation_id,
                    extra={
                        "job_id": str(job.id),
                        "event_type": event.value,
                        "event_version": event_version,
                        "recipient_role": recipient.role,
                        "recipient_tenant_id": recipient.tenant_id,
                        "correlation_id": correlation_id,
                    },
                )

        # ---------------------------------------------------------------
        # 3. Queue SMS and email deliveries.
        # ---------------------------------------------------------------
        for channel, delivery_id in pending_deliveries:
            try:
                if channel == SMS:
                    phone = normalize_phone(recipient.phone)

                    if not phone or not message.get("sms"):
                        mark_delivery(
                            db,
                            delivery_id,
                            "failed",
                            "no valid phone number or SMS content",
                        )
                        continue

                    enqueue_sms(
                        phone,
                        message["sms"],
                        delivery_id=delivery_id,
                    )

                elif channel == EMAIL:
                    if (
                        not recipient.email
                        or not message.get("email")
                    ):
                        reason = "missing_recipient_email" if not recipient.email else "missing_email_content"
                        logger.warning(
                            "Email delivery skipped",
                            extra={"job_id": str(job.id), "event_type": event.value,
                                   "event_version": event_version,
                                   "recipient_role": recipient.role,
                                   "delivery_id": delivery_id, "reason": reason},
                        )
                        mark_delivery(
                            db,
                            delivery_id,
                            "failed",
                            "no email address or email content",
                        )
                        continue

                    enqueue_email(
                        recipient.email,
                        **message["email"],
                        delivery_id=delivery_id,
                        invoice_job_id=(
                            int(job.id)
                            if event == JobEvent.INVOICE_READY
                            and recipient.role == "customer"
                            else None
                        ),
                        invoice_closure_id=(
                            int(job.closure_id)
                            if event == JobEvent.INVOICE_READY
                            and recipient.role == "customer"
                            and job.closure_id is not None
                            else None
                        ),
                    )
                    logger.info(
                        "Email delivery queued",
                        extra={"job_id": str(job.id), "event_type": event.value,
                               "event_version": event_version,
                               "recipient_role": recipient.role,
                               "delivery_id": delivery_id},
                    )

            except Exception as exc:
                logger.exception(
                    "Communication Agent delivery enqueue failed event_id=%s",
                    delivery_id,
                    extra={"channel": channel, "job_id": str(job.id),
                           "event_type": event.value, "delivery_id": delivery_id,
                           "event_id": str(delivery_id),
                           "event_version": event_version,
                           "tenant_id": recipient.tenant_id,
                           "recipient_id": recipient.id,
                           "reason": type(exc).__name__,
                           "error": str(exc)[:400]},
                )

                try:
                    mark_delivery(
                        db,
                        delivery_id,
                        "failed",
                        str(exc)[:500],
                    )
                except Exception:
                    db.rollback()

                    logger.exception(
                        "Communication Agent: failed to mark delivery "
                        "as failed delivery_id=%s",
                        delivery_id,
                    )

    return {
        "notification_ids": notification_ids,
    }


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

_builder = StateGraph(CommState)

_builder.add_node("load", load)
_builder.add_node("compose", compose)
_builder.add_node("dispatch", dispatch)

_builder.add_edge(START, "load")

_builder.add_conditional_edges(
    "load",
    fan_out,
)

_builder.add_edge("compose", "dispatch")
_builder.add_edge("dispatch", END)

communication_graph = _builder.compile()
