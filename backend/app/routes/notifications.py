"""
Notification API routes.

Manual technician push and SMS endpoints generate their
recipient-facing content through the production-safe
CommunicationService workflow before calling transport adapters.
"""

from __future__ import annotations

import uuid

from dataclasses import dataclass
from typing import Optional, Sequence

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
from app.services.ai.FieldOpsAI.services.intent_service import IntentService
from app.services.ai.FieldOpsAI.schemas.intent import IntentContext
from app.services.ai.FieldOpsAI.services.realtime_sentiment import (
    RealTimeSentimentScorer,
)

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


@router.post(
    "/technicians/{id}/fcm-token"
)
def register_fcm_token(
    id: str,
    payload: FCMTokenRegistration,
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
):
    _ = authorization

    correlation_id = request.headers.get(
        "X-Correlation-ID",
        str(
            uuid.uuid4()
        ),
    )

    log_extra = {
        "correlation_id": correlation_id,
        "tenant_id": x_tenant_id,
        "tech_id": id,
    }

    try:
        uuid.UUID(
            id,
            version=4,
        )

    except ValueError as exc:
        logger.warning(
            "Invalid technician ID format.",
            extra=log_extra,
        )

        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid technician ID format "
                "(must be UUID)."
            ),
        ) from exc

    technician = (
        db.query(Technician)
        .filter(
            Technician.tech_id == id
        )
        .first()
    )

    if technician is None:
        logger.error(
            "Technician not found.",
            extra=log_extra,
        )

        raise HTTPException(
            status_code=404,
            detail="Technician not found.",
        )

    if (
        technician.tenant_id
        and technician.tenant_id
        != x_tenant_id
    ):
        logger.error(
            "Access denied for tenant.",
            extra=log_extra,
        )

        raise HTTPException(
            status_code=403,
            detail="Access denied.",
        )

    technician.fcm_token = (
        payload.token
    )

    technician.device_type = (
        payload.device_type
    )

    db.commit()

    logger.info(
        "Registered technician FCM token.",
        extra=log_extra,
    )

    return {
        "status": "registered",
        "tech_id": id,
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
    _ = To

    logger.info(
        "Received Twilio status webhook. "
        "status=%s",
        MessageStatus,
    )

    delivery = (
        db.query(SMSDelivery)
        .filter(
            SMSDelivery.sms_sid
            == MessageSid
        )
        .first()
    )

    if delivery:
        delivery.status = (
            MessageStatus
        )

        if ErrorCode:
            delivery.error_message = (
                f"ErrorCode: {ErrorCode}"
            )

        if Price is not None:
            delivery.cost = abs(
                Price
            )

        db.commit()

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

    if (
        Body
        and Body.strip().upper()
        in stop_keywords
    ):
        technician = (
            db.query(Technician)
            .filter(
                Technician.phone_number
                == From
            )
            .first()
        )

        if technician:
            technician.sms_opt_out = 1
            db.commit()

            logger.info(
                "Technician opted out of SMS. "
                "tech_id=%s",
                technician.tech_id,
            )

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

        if customer_job:
            sentiment_scorer = RealTimeSentimentScorer(db=db)

            sentiment_result = await sentiment_scorer.score_reply(
                reply_text=Body,
                customer_id=customer.id,
                job_id=customer_job.id,
                channel="SMS",
                language="en",
                context=None,
            )

            logger.info(
                "Customer sentiment classified. "
                "user_id=%s job_id=%s sentiment=%s confidence=%.2f",
                customer.id,
                customer_job.id,
                sentiment_result.sentiment,
                sentiment_result.confidence,
            )
        else:
            logger.info(
                "No active job found for customer sentiment analysis. "
                "user_id=%s",
                customer.id,
            )