"""Shared creation and serialization helpers for support cases."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import uuid

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.rbac import UserRole
from app.models import (
    CustomerChatConversation,
    CustomerChatMessage,
    CustomerSupportCaseUpdate,
    CustomerSupportRequest,
    InAppNotification,
    SentimentThreadMessage,
    ServiceRequest,
    User,
)

logger = logging.getLogger(__name__)


def _request_number() -> str:
    return f"SUP-{datetime.now(timezone.utc):%Y%m%d%H%M%S}-{str(uuid.uuid4())[:6].upper()}"


def _chat_priority(db: Session, conversation_id: str) -> str:
    customer_message_ids = [row[0] for row in db.query(CustomerChatMessage.id).filter(
        CustomerChatMessage.conversation_id == conversation_id,
        CustomerChatMessage.sender_type == "customer",
        CustomerChatMessage.status == "SUCCEEDED",
    ).all()]
    if not customer_message_ids:
        return "MEDIUM"
    analyses = db.query(SentimentThreadMessage).filter(
        SentimentThreadMessage.channel == "SUPPORT_CHAT",
        SentimentThreadMessage.source_id.in_([str(value) for value in customer_message_ids]),
    ).all()
    if any((row.severity or "").upper() == "CRITICAL" or (row.urgency or "").upper() == "CRITICAL" for row in analyses):
        return "URGENT"
    if any((row.urgency or "").upper() == "HIGH" or ((row.sentiment or "").upper() == "NEGATIVE" and row.confidence >= 0.85) for row in analyses):
        return "HIGH"
    return "MEDIUM"


def notify_support_staff(db: Session, support_request: CustomerSupportRequest, title: str, body: str, event_key: str) -> None:
    staff = db.query(User).filter(
        User.tenant_id == support_request.tenant_id,
        User.role.in_([UserRole.DISPATCHER.value, UserRole.SUPER_ADMIN.value]),
        User.is_active.is_(True),
        User.deleted_at.is_(None),
    ).all()
    for user in staff:
        db.add(InAppNotification(
            id=str(uuid.uuid4()),
            tenant_id=support_request.tenant_id,
            recipient_id=str(user.id),
            recipient_role="dispatcher",
            group_key=f"customer_support:{support_request.id}:{event_key}",
            job_id=f"support:{support_request.id}",
            type="CUSTOMER_SUPPORT_REQUEST",
            title=title,
            body=body,
            status="UNREAD",
            priority=support_request.priority,
            action_url=f"/customer-support/{support_request.id}",
            action_type="CUSTOMER_SUPPORT_REQUEST",
            event_version=1,
            notification_metadata={
                "support_request_id": support_request.id,
                "request_number": support_request.request_number,
                "priority": support_request.priority,
            },
        ))


def create_support_case(
    db: Session,
    *,
    customer_id: str,
    tenant_id: str,
    subject: str,
    description: str,
    related_job_id: int | None = None,
    source_chat_conversation_id: str | None = None,
) -> tuple[CustomerSupportRequest, bool]:
    """Create an idempotent, customer-owned case and notify tenant dispatchers."""
    conversation = None
    if source_chat_conversation_id:
        conversation = db.query(CustomerChatConversation).filter(
            CustomerChatConversation.id == source_chat_conversation_id,
            CustomerChatConversation.tenant_id == tenant_id,
            CustomerChatConversation.customer_user_id == customer_id,
        ).first()
        if conversation is None:
            raise HTTPException(status_code=404, detail="Support conversation not found.")
        existing = db.query(CustomerSupportRequest).filter_by(
            source_chat_conversation_id=source_chat_conversation_id,
            tenant_id=tenant_id,
            customer_user_id=customer_id,
        ).first()
        if existing:
            return existing, False

    if related_job_id is not None:
        owned_request = db.query(ServiceRequest).filter(
            ServiceRequest.linked_job_id == related_job_id,
            ServiceRequest.customer_user_id == customer_id,
            ServiceRequest.tenant_id == tenant_id,
        ).first()
        if owned_request is None:
            raise HTTPException(status_code=404, detail="Related job not found for this customer.")

    priority = _chat_priority(db, source_chat_conversation_id) if source_chat_conversation_id else "MEDIUM"
    customer = db.query(User).filter(User.id == customer_id, User.tenant_id == tenant_id).first()
    customer_name = (f"{customer.first_name} {customer.last_name}".strip() if customer else "Customer")
    category = "OTHER"
    if source_chat_conversation_id:
        customer_message_ids = [row[0] for row in db.query(CustomerChatMessage.id).filter(
            CustomerChatMessage.conversation_id == source_chat_conversation_id,
            CustomerChatMessage.sender_type == "customer",
            CustomerChatMessage.status == "SUCCEEDED",
        ).all()]
        analyses = db.query(SentimentThreadMessage).filter(
            SentimentThreadMessage.channel == "SUPPORT_CHAT",
            SentimentThreadMessage.source_id.in_([str(value) for value in customer_message_ids]),
        ).all() if customer_message_ids else []
        category_map = {
            "PRICING_BILLING": "BILLING",
            "SERVICE_QUALITY": "SERVICE_QUALITY",
            "TECHNICIAN_DELAY": "TECHNICIAN",
            "TECHNICIAN_BEHAVIOR": "TECHNICIAN",
            "SCHEDULING": "SCHEDULING",
            "COMMUNICATION": "GENERAL",
        }
        category = next((category_map[item] for row in reversed(analyses) for item in (row.issue_categories or []) if item in category_map), "OTHER")
    support_request = CustomerSupportRequest(
        request_number=_request_number(),
        customer_user_id=customer_id,
        tenant_id=tenant_id,
        subject=subject.strip()[:200],
        description=description.strip()[:5000],
        status="OPEN",
        category=category,
        priority=priority,
        related_job_id=related_job_id,
        source_chat_conversation_id=source_chat_conversation_id,
    )
    db.add(support_request)
    db.flush()
    notify_support_staff(db, support_request, f"New support case {support_request.request_number}", f"{customer_name} submitted: {support_request.subject}", "created")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if source_chat_conversation_id:
            existing = db.query(CustomerSupportRequest).filter_by(
                source_chat_conversation_id=source_chat_conversation_id,
                tenant_id=tenant_id,
                customer_user_id=customer_id,
            ).first()
            if existing:
                return existing, False
        raise
    db.refresh(support_request)
    if not source_chat_conversation_id:
        try:
            from app.sentiment.job_message_tasks import analyze_customer_support_case

            analyze_customer_support_case.delay(support_request.id)
        except Exception:
            # Case submission remains durable when the sentiment worker is unavailable.
            logger.exception(
                "Could not queue sentiment analysis for support case %s", support_request.id
            )
    return support_request, True


def support_updates(db: Session, support_request_id: int) -> list[dict]:
    rows = db.query(CustomerSupportCaseUpdate, User).outerjoin(
        User, User.id == CustomerSupportCaseUpdate.author_user_id,
    ).filter(
        CustomerSupportCaseUpdate.support_request_id == support_request_id,
    ).order_by(CustomerSupportCaseUpdate.created_at, CustomerSupportCaseUpdate.id).all()
    return [{
        "id": update.id,
        "author_role": update.author_role,
        "author_name": (
            f"{author.first_name} {author.last_name}".strip()
            if author else ("Customer" if update.author_role == "customer" else "Support team")
        ),
        "message": update.message,
        "created_at": update.created_at,
    } for update, author in rows]


def customer_case_payload(db: Session, support_request: CustomerSupportRequest) -> dict:
    assigned = db.query(User).filter(User.id == support_request.assigned_staff_id).first() if support_request.assigned_staff_id else None
    return {
        "id": support_request.id,
        "request_number": support_request.request_number,
        "subject": support_request.subject,
        "description": support_request.description,
        "related_job_id": support_request.related_job_id,
        "status": support_request.status,
        "category": support_request.category,
        "priority": support_request.priority,
        "assigned_staff_name": (f"{assigned.first_name} {assigned.last_name}".strip() if assigned else None),
        "resolution_note": support_request.resolution_note,
        "resolved_at": support_request.resolved_at,
        "created_at": support_request.created_at,
        "updated_at": support_request.updated_at,
        "updates": support_updates(db, support_request.id),
    }


def chat_transcript(db: Session, support_request: CustomerSupportRequest) -> list[dict]:
    if not support_request.source_chat_conversation_id:
        return []
    rows = db.query(CustomerChatMessage).filter(
        CustomerChatMessage.conversation_id == support_request.source_chat_conversation_id,
        CustomerChatMessage.tenant_id == support_request.tenant_id,
        CustomerChatMessage.status == "SUCCEEDED",
    ).order_by(CustomerChatMessage.created_at, CustomerChatMessage.id).all()
    return [{"sender": row.sender_type, "content": row.content, "created_at": row.created_at} for row in rows]


def support_sentiment_triage(db: Session, support_request: CustomerSupportRequest) -> dict | None:
    if support_request.source_chat_conversation_id:
        message_ids = [str(row[0]) for row in db.query(CustomerChatMessage.id).filter(
            CustomerChatMessage.conversation_id == support_request.source_chat_conversation_id,
            CustomerChatMessage.sender_type == "customer",
        ).all()]
        if not message_ids:
            return None
        query = db.query(SentimentThreadMessage).filter(
            SentimentThreadMessage.source_type == "SUPPORT_CHAT",
            SentimentThreadMessage.source_id.in_(message_ids),
        )
    else:
        update_ids = [str(row[0]) for row in db.query(CustomerSupportCaseUpdate.id).filter(
            CustomerSupportCaseUpdate.support_request_id == support_request.id,
            CustomerSupportCaseUpdate.author_role == "customer",
        ).all()]
        source_ids = [str(support_request.id), *update_ids]
        query = db.query(SentimentThreadMessage).filter(
            SentimentThreadMessage.source_type.in_(["SUPPORT_CASE", "SUPPORT_CASE_UPDATE"]),
            SentimentThreadMessage.source_id.in_(source_ids),
        )
    latest = query.order_by(SentimentThreadMessage.created_at.desc()).first()
    if latest is None:
        return None
    return {
        "sentiment": latest.sentiment,
        "emotion": latest.emotion,
        "urgency": latest.urgency,
        "severity": latest.severity,
        "confidence": latest.confidence,
        "issue_categories": latest.issue_categories or [],
        "recommended_action": latest.recommended_action,
    }
