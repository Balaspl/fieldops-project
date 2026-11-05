"""
Notification API routes.

Manual technician push and SMS endpoints generate their
recipient-facing content through the production-safe
CommunicationService workflow before calling transport adapters.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from dataclasses import dataclass
from typing import Optional, Sequence
from app.services.sms.delivery_status import SMSDeliveryStatusService
from fastapi import (
    APIRouter,
    Depends,
    Form,
    Header,
    HTTPException,
    Request,
)
from sqlalchemy.orm import Session

from .dispatch import verify_jwt_token
from .technician_portal import _get_tech_for_user
from ..auth.dependencies import (
    AuthenticatedUser,
    require_role,
)
from ..auth.rbac import UserRole
from ..context import correlation_id_ctx
from ..database import get_db
from ..logger import logger
from ..models import (
    Job,
    SMSDelivery,
    Technician,
)
from ..schemas import (
    FCMTokenRegistration,
    NotificationSendRequest,
    NotificationSendResponse,
    SMSSendRequest,
    SMSPreviewRequest,
    SMSSendDirectRequest,
    SMSBulkSendRequest,
)


from ..services.ai.integrations.communication_integration import (
    CommunicationIntegration,
    CommunicationIntegrationError,
)
from ..services.fcm import (
    send_job_assignment_notification,
)
from ..services.twilio_sms import (
    send_job_assignment_sms,
)
from app.models import User
from app.models_legacy import NotificationChannelDelivery
from app.services.ai.FieldOpsAI.services.intent_service import IntentService
from app.services.ai.FieldOpsAI.schemas.intent import IntentContext
from app.services.ai.FieldOpsAI.services.realtime_sentiment import (
    RealTimeSentimentScorer,
)
from app.services.inbound_customer_communication import (
    handle_customer_sms,
)
from app.services.inbound_technician_communication import handle_technician_sms
from app.services.communication_delivery import enqueue_tracked_sms
from app.services.socket_manager import sio
from app.services.sms.twilio_service import TwilioSMSService
from app.tasks import send_sms_async, send_bulk_sms_async


router = APIRouter(
    tags=["Notifications"]
)


# ==========================================================
# Safe Communication Event
# ==========================================================


@dataclass(frozen=True)
class ManualTechnicianNotificationEvent:
    """
    Minimal event required by CommunicationIntegration.

    Technician and customer names are deliberately omitted
    because one manual request may target multiple technicians.
    The generated message must therefore remain generic.
    """

    job_id: str
    tenant_id: str
    to_status: str
    job_title: str

    technician_name: str | None = None
    customer_name: str | None = None
    eta: str | None = None


# ==========================================================
# Dependencies
# ==========================================================


def get_communication_integration(
) -> CommunicationIntegration:
    """
    Create the production communication adapter.

    A FastAPI dependency makes this replaceable in route tests.
    """

    return CommunicationIntegration()


# ==========================================================
# Validation Helpers
# ==========================================================


def _load_tenant_job(
    *,
    db: Session,
    job_id: object,
    tenant_id: str,
) -> Job:
    """
    Load a job using both job ID and tenant ID.

    This prevents a tenant from sending notifications for
    another tenant's job.
    """

    normalized_job_id = str(
        job_id
    ).strip()

    if not normalized_job_id.isdigit():
        raise HTTPException(
            status_code=400,
            detail="job_id must be a numeric job identifier.",
        )

    job = (
        db.query(Job)
        .filter(
            Job.id == int(
                normalized_job_id
            ),
            Job.tenant_id == tenant_id,
        )
        .first()
    )

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Job was not found for this tenant.",
        )

    return job


def _validate_tenant_technicians(
    *,
    db: Session,
    tech_ids: Sequence[object],
    tenant_id: str,
) -> list[str]:
    """
    Validate and normalize all requested technician IDs.

    Every technician must belong to the requesting tenant.
    """

    normalized_ids = list(
        dict.fromkeys(
            str(
                tech_id
            ).strip()
            for tech_id in tech_ids
            if str(
                tech_id
            ).strip()
        )
    )

    if not normalized_ids:
        raise HTTPException(
            status_code=400,
            detail="tech_ids list cannot be empty.",
        )

    if len(normalized_ids) > 50:
        raise HTTPException(
            status_code=400,
            detail=(
                "Cannot send to more than "
                "50 technicians at once."
            ),
        )

    technicians = (
        db.query(Technician)
        .filter(
            Technician.tech_id.in_(
                normalized_ids
            ),
            Technician.tenant_id
            == tenant_id,
        )
        .all()
    )

    found_ids = {
        str(
            technician.tech_id
        )
        for technician in technicians
    }

    missing_ids = (
        set(
            normalized_ids
        )
        - found_ids
    )

    if missing_ids:
        # Do not reveal whether the missing technicians exist
        # in another tenant.
        raise HTTPException(
            status_code=404,
            detail=(
                "One or more technicians were not "
                "found for this tenant."
            ),
        )

    return normalized_ids


def _job_title(
    job: Job,
) -> str:
    """
    Return a trusted non-empty job title.
    """

    value = (
        getattr(
            job,
            "service_type",
            None,
        )
        or getattr(
            job,
            "required_skill",
            None,
        )
    )

    normalized = (
        str(
            value
        ).strip()
        if value is not None
        else ""
    )

    if not normalized:
        raise HTTPException(
            status_code=422,
            detail=(
                "The job does not contain a valid "
                "service type or required skill."
            ),
        )

    return normalized


def _job_location(
    job: Job,
) -> str:
    """
    Return the trusted job location used by transport metadata.
    """

    value = getattr(
        job,
        "location",
        None,
    )

    normalized = (
        str(
            value
        ).strip()
        if value is not None
        else ""
    )

    if not normalized:
        raise HTTPException(
            status_code=422,
            detail=(
                "The job does not contain a valid location."
            ),
        )

    return normalized


def _push_priority(
    job: Job,
) -> str:
    """
    Convert FieldOps priority values into transport priority.
    """

    priority = str(
        getattr(
            job,
            "priority",
            "",
        )
        or ""
    ).strip().upper()

    if priority in {
        "HIGH",
        "URGENT",
        "P1",
        "P2",
    }:
        return "HIGH"

    return "NORMAL"


async def _generate_safe_technician_content(
    *,
    communication: CommunicationIntegration,
    job: Job,
    tenant_id: str,
    channel: str,
    correlation_id: str,
):
    """
    Generate guardrail-approved technician content.

    No hardcoded recipient-facing fallback is used here.
    CommunicationService owns fallback selection.
    """

    event = ManualTechnicianNotificationEvent(
        job_id=str(
            job.id
        ),
        tenant_id=tenant_id,
        to_status="ASSIGNED",
        job_title=_job_title(
            job
        ),
    )

    context_token = (
        correlation_id_ctx.set(
            correlation_id
        )
    )

    try:
        return await communication.generate(
            event=event,
            recipient_type="technician",
            channel=channel,
            notification_type=(
                "technician_job_assigned"
            ),
            locale="en",
        )

    except CommunicationIntegrationError as exc:
        logger.error(
            "Safe manual technician notification "
            "generation failed. job_id=%s channel=%s",
            job.id,
            channel,
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Safe notification content could not "
                "be generated."
            ),
        ) from exc

    finally:
        correlation_id_ctx.reset(
            context_token
        )


# ==========================================================
# FCM Token Registration
# ==========================================================


@router.post("/technicians/{id}/fcm-token")
@router.post("/technicians/{id}/push-token")
def register_fcm_token(
    id: str,
    payload: FCMTokenRegistration,
    request: Request,
    x_tenant_id: str = Header(
        ...,
        alias="X-Tenant-ID",
    ),
    current_user: AuthenticatedUser = Depends(
        require_role(UserRole.TECHNICIAN)
    ),
    db: Session = Depends(get_db),
):
    correlation_id = request.headers.get(
        "X-Correlation-ID",
        str(uuid.uuid4()),
    )

    tenant_id = current_user.tenant_id

    log_extra = {
        "correlation_id": correlation_id,
        "tenant_id": tenant_id,
        "tech_id": id,
        "user_id": current_user.user_id,
    }

    # Keep the existing UUID-based route contract.
    try:
        technician_id = str(uuid.UUID(id))
    except (ValueError, TypeError, AttributeError) as exc:
        logger.warning(
            "Invalid technician ID format.",
            extra=log_extra,
        )
        raise HTTPException(
            status_code=400,
            detail="Invalid technician ID format (must be UUID).",
        ) from exc

    # The signed identity is authoritative; the header is only
    # accepted when it matches that authenticated tenant.
    if not tenant_id or x_tenant_id != tenant_id:
        logger.warning(
            "Push token registration tenant mismatch.",
            extra=log_extra,
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied.",
        )

    # Resolve the authenticated user's technician record through
    # the project's existing tenant-scoped mapping.
    technician = _get_tech_for_user(
        db,
        current_user.user_id,
        tenant_id,
    )

    if technician is None:
        logger.warning(
            "Technician not found for token registration.",
            extra=log_extra,
        )
        raise HTTPException(
            status_code=404,
            detail="Technician not found.",
        )

    # The URL must identify the technician resolved for this caller.
    try:
        resolved_technician_id = str(
            uuid.UUID(str(technician.tech_id))
        )
    except (ValueError, TypeError, AttributeError):
        logger.error(
            "Resolved technician has an invalid ID format.",
            extra=log_extra,
        )
        raise HTTPException(
            status_code=404,
            detail="Technician not found.",
        )

    if resolved_technician_id != technician_id:
        logger.warning(
            "Push token registration technician mismatch.",
            extra=log_extra,
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied.",
        )

    # Expo push tokens are stored in the legacy fcm_token column so existing
    # technician records and notification delivery queries remain compatible.
    technician.fcm_token = payload.token
    technician.device_type = payload.device_type

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception(
            "Failed to register technician push token.",
            extra=log_extra,
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to register device token.",
        ) from exc

    logger.info(
        "Registered technician push token.",
        extra=log_extra,
    )

    return {
        "status": "registered",
        "tech_id": technician_id,
    }


# ==========================================================
# Safe Manual Push
# ==========================================================


@router.post(
    "/notifications/send-push",
    response_model=NotificationSendResponse,
)
async def send_push_notification(
    payload: NotificationSendRequest,
    request: Request,
    x_tenant_id: str = Header(
        ...,
        alias="X-Tenant-ID",
    ),
    authorization: str = Depends(
        verify_jwt_token
    ),
    db: Session = Depends(
        get_db
    ),
    communication: CommunicationIntegration = Depends(
        get_communication_integration
    ),
):
    _ = authorization

    correlation_id = request.headers.get(
        "X-Correlation-ID",
        str(
            uuid.uuid4()
        ),
    )

    job = _load_tenant_job(
        db=db,
        job_id=payload.job_id,
        tenant_id=x_tenant_id,
    )

    technician_ids = (
        _validate_tenant_technicians(
            db=db,
            tech_ids=payload.tech_ids,
            tenant_id=x_tenant_id,
        )
    )

    safe_result = (
        await _generate_safe_technician_content(
            communication=communication,
            job=job,
            tenant_id=x_tenant_id,
            channel="push",
            correlation_id=(
                correlation_id
            ),
        )
    )

    title = (
        safe_result.decision.title
    )

    if not title:
        raise HTTPException(
            status_code=503,
            detail=(
                "Safe push content did not contain "
                "a notification title."
            ),
        )

    logger.info(
        "Dispatching safe technician push notifications. "
        "job_id=%s recipient_count=%s",
        job.id,
        len(
            technician_ids
        ),
    )

    return await send_job_assignment_notification(
        db=db,
        job_id=str(
            job.id
        ),
        job_title=_job_title(
            job
        ),
        location=_job_location(
            job
        ),
        tech_ids=technician_ids,
        correlation_id=correlation_id,
        notification_title=title,
        notification_body=(
            safe_result.decision.message
        ),
        notification_type=(
            "technician_job_assigned"
        ),
        priority=_push_priority(
            job
        ),
    )


# ==========================================================
# Safe Manual SMS
# ==========================================================


@router.post(
    "/notifications/send-sms",
    response_model=NotificationSendResponse,
)
async def send_sms_notification(
    payload: SMSSendRequest,
    request: Request,
    x_tenant_id: str = Header(
        ...,
        alias="X-Tenant-ID",
    ),
    authorization: str = Depends(
        verify_jwt_token
    ),
    db: Session = Depends(
        get_db
    ),
    communication: CommunicationIntegration = Depends(
        get_communication_integration
    ),
):
    _ = authorization

    correlation_id = request.headers.get(
        "X-Correlation-ID",
        str(
            uuid.uuid4()
        ),
    )

    job = _load_tenant_job(
        db=db,
        job_id=payload.job_id,
        tenant_id=x_tenant_id,
    )

    technician_ids = (
        _validate_tenant_technicians(
            db=db,
            tech_ids=payload.tech_ids,
            tenant_id=x_tenant_id,
        )
    )

    safe_result = (
        await _generate_safe_technician_content(
            communication=communication,
            job=job,
            tenant_id=x_tenant_id,
            channel="sms",
            correlation_id=(
                correlation_id
            ),
        )
    )

    logger.info(
        "Dispatching safe technician SMS notifications. "
        "job_id=%s recipient_count=%s",
        job.id,
        len(
            technician_ids
        ),
    )

    return await send_job_assignment_sms(
        db=db,
        job_id=str(
            job.id
        ),
        job_title=_job_title(
            job
        ),
        location=_job_location(
            job
        ),
        priority=str(
            getattr(
                job,
                "priority",
                None,
            )
            or "NORMAL"
        ),
        tech_ids=technician_ids,
        correlation_id=correlation_id,
        message_body=(
            safe_result.decision.message
        ),
    )


# ==========================================================
# Twilio Webhooks
# ==========================================================


@router.post(
    "/webhooks/twilio-status"
)

async def twilio_status_webhook(
    MessageSid: str = Form(
        ...
    ),
    MessageStatus: str = Form(
        ...
    ),
    ErrorCode: Optional[str] = Form(
        None
    ),

    ErrorMessage: Optional[str] = Form(None),
    
    To: Optional[str] = Form(
        None
    ),
    Price: Optional[float] = Form(
        None
    ),
    db: Session = Depends(
        get_db
    ),
):
    logger.info(
        "Received Twilio status webhook. "
        "sid=%s status=%s",
        MessageSid,
        MessageStatus,
    )

    payload = {
        "MessageSid": MessageSid,
        "MessageStatus": MessageStatus,
        "ErrorCode": ErrorCode,
        "ErrorMessage": ErrorMessage,
        "To": To,
        "Price": Price,
    }

    service = SMSDeliveryStatusService(db)

    delivery = service.process_webhook(
        payload
    )

    channel_delivery = (
        db.query(NotificationChannelDelivery)
        .filter(NotificationChannelDelivery.provider_id == MessageSid)
        .first()
    )
    if channel_delivery:
        status_value = (MessageStatus or "").strip().lower()
        tracked_status = {
            "queued": "queued",
            "sending": "sending",
            "sent": "accepted",
            "delivered": "delivered",
            "failed": "failed",
            "undelivered": "failed",
        }.get(status_value)
        if tracked_status:
            current_status = str(channel_delivery.status or "").lower()
            rank = {
                "queued": 0,
                "sending": 1,
                "accepted": 2,
                "sent": 2,
                "failed": 3,
                "delivered": 3,
            }
            may_advance = rank.get(tracked_status, 0) >= rank.get(current_status, 0)
            if current_status in {"delivered", "failed"} and tracked_status != "delivered":
                may_advance = False
            if may_advance:
                channel_delivery.status = tracked_status
                if tracked_status == "failed" and (ErrorCode or ErrorMessage):
                    channel_delivery.error_message = (
                        f"Twilio {status_value}: {ErrorCode or ErrorMessage}"
                    )[:500]
                elif tracked_status != "failed":
                    channel_delivery.error_message = None
                db.commit()

    if delivery is None:
        logger.warning(
            "SMS delivery record not found. "
            "sid=%s",
            MessageSid,
        )

    # Update the latest Twilio delivery status in Redis.
    try:
        from app.redis_client import get_redis_client

        redis_client = get_redis_client()

        if redis_client:
            redis_client.set(
                f"sms_delivery:{MessageSid}",
                {
                    "sid": MessageSid,
                    "status": MessageStatus,
                    "error_code": ErrorCode,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                ex=86400,
            )

    except Exception as exc:
        logger.warning(
            "Failed to update SMS delivery status in Redis. sid=%s error=%s",
            MessageSid,
            exc,
        )

    return {
        "status": "ok"
    }


# ==========================================================
# Twilio Inbound Webhook
# ==========================================================


@router.post(
    "/webhooks/twilio-inbound"
)
async def twilio_inbound_webhook(
    MessageSid: str = Form(
        ...
    ),
    From: str = Form(
        ...
    ),
    Body: str = Form(
        ...
    ),
    db: Session = Depends(
        get_db
    ),
):
    _ = MessageSid

    masked_from = (
        f"+{'*' * (len(From) - 5)}"
        f"{From[-4:]}"
        if len(
            From
        )
        > 8
        else "***"
    )

    logger.info(
        "Received Twilio inbound message "
        "from %s.",
        masked_from,
    )

    # ---------------------------------------------------------
    # Technician SMS opt-out handling
    # ---------------------------------------------------------

    stop_keywords = {
        "STOP",
        "UNSUBSCRIBE",
        "CANCEL",
        "QUIT",
        "END",
    }

    technician_matches = (
        db.query(Technician)
        .filter(Technician.phone_number == From)
        .all()
    )
    if len(technician_matches) > 1:
        logger.warning("Inbound SMS sender maps to multiple technician records.")
        return {"status": "ok", "communication": {"status": "sender_ambiguous"}}
    technician_sender = technician_matches[0] if technician_matches else None

    # ---------------------------------------------------------
    # Customer Intent Recognition
    # ---------------------------------------------------------

    customer = (
        db.query(User)
        .filter(
            User.phone_number == From,
            User.role == "customer",
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
        .first()
    )

    if customer and technician_sender:
        logger.warning("Inbound SMS sender maps to both a customer and technician account.")
        return {"status": "ok", "communication": {"status": "sender_ambiguous"}}

    if (
        technician_sender
        and Body
        and Body.strip().upper() in stop_keywords
    ):
        technician_sender.sms_opt_out = 1
        db.commit()
        logger.info(
            "Technician opted out of SMS. tech_id=%s",
            technician_sender.tech_id,
        )
        return {"status": "ok", "communication": {"status": "opted_out"}}

    customer_stop_keywords = {"STOP", "UNSUBSCRIBE", "QUIT", "END"}
    if customer and Body and Body.strip().upper() in customer_stop_keywords:
        from app.services.ai.FieldOpsAI.repositories.customer_profile_repository import (
            CustomerProfileRepository,
        )
        from app.services.ai.FieldOpsAI.schemas.customer_profile import (
            CustomerPreferenceUpdate,
        )
        from app.services.ai.FieldOpsAI.services.customer_preference_service import (
            CustomerPreferenceService,
        )

        CustomerPreferenceService(
            CustomerProfileRepository(db)
        ).update_preferences(
            tenant_id=str(customer.tenant_id),
            customer_id=str(customer.id),
            payload=CustomerPreferenceUpdate(sms_enabled=False),
            actor_id=str(customer.id),
            actor_source="CUSTOMER",
            correlation_id=correlation_id_ctx.get() or None,
        )
        logger.info(
            "Customer SMS opt-out received; no conversational reply will be sent. "
            "user_id=%s",
            customer.id,
        )
        return {"status": "ok", "communication": {"status": "opted_out"}}

    if customer and Body and Body.strip():
        intent_service = IntentService(
            db=db
        )

        intent_result = intent_service.recognize(
            IntentContext(
                message=Body,
                language="en",
            ),
            tenant_id=customer.tenant_id,
            user_id=customer.id,
            user_email=customer.email,
            role=customer.role,
        )

        logger.info(
            "Customer intent classified. "
            "user_id=%s intent=%s confidence=%.2f",
            customer.id,
            intent_result.intent,
            intent_result.confidence,
        )

        # -----------------------------------------------------
        # Real-Time Sentiment Analysis - Story 12.2
        # -----------------------------------------------------

        customer_job = (
            db.query(Job)
            .filter(
                Job.customer_id == str(customer.id),
                Job.tenant_id == customer.tenant_id,
                Job.status.notin_(
                    ["COMPLETED", "CANCELLED", "CLOSED"]
                ),
            )
            .order_by(Job.updated_at.desc())
            .first()
        )

        sentiment_scorer = RealTimeSentimentScorer(db=db)
        sentiment_result = await sentiment_scorer.score_reply(
            reply_text=Body,
            customer_id=customer.id,
            job_id=customer_job.id if customer_job else None,
            channel="SMS",
            language="en",
            context=None,
            tenant_id=customer.tenant_id,
            source_type="SMS",
            source_id=MessageSid,
        )

        logger.info(
            "Customer sentiment classified. "
            "user_id=%s job_id=%s sentiment=%s confidence=%.2f",
            customer.id,
            customer_job.id if customer_job else None,
            sentiment_result.sentiment if sentiment_result else "SKIPPED",
            sentiment_result.confidence if sentiment_result else 0.0,
        )
        try:
            communication_result = handle_customer_sms(
                db,
                customer=customer,
                body=Body,
                message_sid=MessageSid,
            )
        except Exception as exc:
            logger.exception(
                "Communication Agent could not process inbound customer SMS. "
                "user_id=%s",
                customer.id,
            )
            raise HTTPException(
                status_code=503,
                detail="Unable to process the customer message right now.",
            ) from exc

        logger.info(
            "Inbound customer SMS routed through Communication Agent. "
            "user_id=%s conversation_id=%s status=%s reply_queued=%s",
            customer.id,
            communication_result.get("conversation_id"),
            communication_result.get("status"),
            communication_result.get("reply_queued"),
        )
    elif technician_sender and Body and Body.strip():
        technician_result = handle_technician_sms(
            db,
            technician=technician_sender,
            body=Body,
            message_sid=MessageSid,
        )
        state = technician_result.get("status")
        if state == "job_selection_required":
            enqueue_tracked_sms(
                db,
                tenant_id=str(technician_sender.tenant_id),
                recipient_id=str(technician_result["technician_user_id"]),
                recipient_role="technician",
                technician_id=technician_sender.tech_id,
                to_number=From,
                body=(
                    "You have multiple active jobs. Reply with JOB #<number> "
                    "followed by your message so I can attach it to the right job."
                ),
                source_type="INBOUND_TECH_SMS_CLARIFICATION",
                source_id=MessageSid,
                title="Specify the job for your message",
            )
        elif state == "job_not_assigned_or_chat_unavailable":
            enqueue_tracked_sms(
                db,
                tenant_id=str(technician_sender.tenant_id),
                recipient_id=str(technician_result["technician_user_id"]),
                recipient_role="technician",
                technician_id=technician_sender.tech_id,
                to_number=From,
                body=(
                    "I couldn't match that job to an active assignment. "
                    "Please send this update from the FieldOps technician app."
                ),
                source_type="INBOUND_TECH_SMS_CLARIFICATION",
                source_id=MessageSid,
                title="Job update needs the technician app",
            )
        elif state == "stored":
            try:
                await sio.emit(
                    "job_message",
                    {
                        "job_id": technician_result["job_id"],
                        "message": {
                            "id": technician_result["message_id"],
                            "job_id": technician_result["job_id"],
                            "sender_user_id": technician_result["sender_user_id"],
                            "sender_role": technician_result["sender_role"],
                            "body": technician_result["body"],
                            "created_at": technician_result["created_at"],
                            "delivered_at": None,
                            "read_at": None,
                            "is_mine": False,
                        },
                    },
                    room=f"user_{technician_result['customer_user_id']}",
                )
            except Exception:
                logger.exception(
                    "Could not broadcast inbound technician SMS to the customer. "
                    "job_id=%s",
                    technician_result.get("job_id"),
                )
        logger.info(
            "Inbound technician SMS handled. tech_id=%s status=%s job_id=%s",
            technician_sender.tech_id,
            state,
            technician_result.get("job_id"),
        )
    return {
        "status": "ok",
        **(
            {
                "communication": communication_result,
            }
            if customer and Body and Body.strip()
            else {}
        ),
        **(
            {"communication": technician_result}
            if technician_sender and not customer and Body and Body.strip()
            else {}
        ),
    }


@router.post("/sms/preview")
def preview_sms(
    payload: SMSPreviewRequest,
):
    # Preview validates the SMS but never sends it through Twilio.
    service = TwilioSMSService()

    try:
        return service.preview_sms(
            to_number=payload.to_number,
            body=payload.body,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )

@router.post("/sms/send")
def queue_sms(
    payload: SMSSendDirectRequest,
):
    # Validate the SMS before putting it into the background queue.
    service = TwilioSMSService()

    try:
        service.preview_sms(
            to_number=payload.to_number,
            body=payload.body,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )

    # Queue the actual Twilio delivery so the API stays non-blocking.
    task = send_sms_async.delay(
        to_number=payload.to_number,
        body=payload.body,
        from_number=payload.from_number,
    )

    return {
        "success": True,
        "status": "queued",
        "task_id": task.id,
    }

@router.post("/sms/send-bulk")
def queue_bulk_sms(
    payload: SMSBulkSendRequest,
):
    # Validate the message and every recipient before queueing.
    service = TwilioSMSService()

    if not payload.recipients:
        raise HTTPException(
            status_code=422,
            detail="Recipients list cannot be empty",
        )

    if len(payload.recipients) > 50:
        raise HTTPException(
            status_code=422,
            detail="Cannot send to more than 50 recipients at once",
        )

    try:
        for recipient in payload.recipients:
            service.validate_phone_number(recipient)

        if not payload.body or not payload.body.strip():
            raise ValueError("SMS body cannot be empty")

        if len(payload.body) > 160:
            raise ValueError("SMS body cannot exceed 160 characters")

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )

    # Queue bulk delivery so the API remains non-blocking.
    task = send_bulk_sms_async.delay(
        recipients=payload.recipients,
        body=payload.body,
        from_number=payload.from_number,
    )

    return {
        "success": True,
        "status": "queued",
        "recipient_count": len(payload.recipients),
        "task_id": task.id,
    }
