"""Route inbound customer SMS through the existing support and delivery layers."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.customer_chat import CustomerChatConversation, CustomerChatMessage
from app.services.communication_delivery import enqueue_tracked_sms
from app.services.customer_support_graph import customer_support_graph

logger = logging.getLogger(__name__)


def inbound_sms_client_message_id(message_sid: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"fieldops:twilio:{message_sid}"))


def handle_customer_sms(
    db: Session,
    *,
    customer,
    body: str,
    message_sid: str,
) -> dict[str, str | bool]:
    """Persist, answer, and queue delivery for one inbound customer SMS.

    Twilio can retry webhooks. The provider SID is mapped to a stable client
    message ID so a retried webhook does not generate or send another answer.
    The support graph remains read-only and tenant-scoped; this layer only
    persists the conversation and queues the response through the existing SMS
    task.
    """
    client_message_id = inbound_sms_client_message_id(message_sid)
    conversation = (
        db.query(CustomerChatConversation)
        .filter(
            CustomerChatConversation.tenant_id == customer.tenant_id,
            CustomerChatConversation.customer_user_id == str(customer.id),
            CustomerChatConversation.status == "OPEN",
        )
        .order_by(desc(CustomerChatConversation.updated_at))
        .first()
    )
    if conversation is None:
        conversation = CustomerChatConversation(
            tenant_id=customer.tenant_id,
            customer_user_id=str(customer.id),
            title="SMS support conversation",
        )
        db.add(conversation)
        db.flush()

    incoming = (
        db.query(CustomerChatMessage)
        .filter_by(
            conversation_id=conversation.id,
            tenant_id=customer.tenant_id,
            client_message_id=client_message_id,
        )
        .first()
    )
    if incoming is not None:
        prior_reply = (
            db.query(CustomerChatMessage)
            .filter_by(reply_to_message_id=incoming.id, sender_type="assistant")
            .first()
        )
        delivery = None
        if prior_reply is not None:
            delivery = enqueue_tracked_sms(
                db,
                tenant_id=str(customer.tenant_id),
                recipient_id=str(customer.id),
                recipient_role="customer",
                to_number=customer.phone_number,
                body=(
                    prior_reply.content
                    if len(prior_reply.content) <= 160
                    else "I sent a detailed reply in your FieldOps Support chat. Please open the app to read it."
                ),
                source_type="INBOUND_CUSTOMER_SMS_REPLY",
                source_id=message_sid,
                title="FieldOps Support reply",
            )
        return {
            "status": "duplicate",
            "conversation_id": conversation.id,
            "reply_queued": bool(delivery and delivery.get("queued")),
        }

    incoming = CustomerChatMessage(
        conversation_id=conversation.id,
        tenant_id=customer.tenant_id,
        sender_type="customer",
        content=body.strip()[:4000],
        client_message_id=client_message_id,
        status="PENDING",
    )
    db.add(incoming)
    db.flush()

    previous = (
        db.query(CustomerChatMessage)
        .filter(
            CustomerChatMessage.tenant_id == customer.tenant_id,
            CustomerChatMessage.conversation_id == conversation.id,
            CustomerChatMessage.id < incoming.id,
            CustomerChatMessage.status == "SUCCEEDED",
        )
        .order_by(desc(CustomerChatMessage.id))
        .limit(8)
        .all()
    )
    history = [
        {
            "sender": row.sender_type,
            "content": row.content,
            "components": row.response_components or [],
        }
        for row in reversed(previous)
    ]

    try:
        result = customer_support_graph.invoke(
            {
                "db": db,
                "tenant_id": str(customer.tenant_id),
                "customer_id": str(customer.id),
                "conversation_id": conversation.id,
                "message": body.strip(),
                "history": history,
            }
        )
        answer = str(
            result.get(
                "answer",
                "I couldn’t verify an answer. Please contact FieldOps Support.",
            )
        ).strip()[:4000]
        if not answer:
            answer = "I couldn’t verify an answer. Please contact FieldOps Support."

        reply = CustomerChatMessage(
            conversation_id=conversation.id,
            tenant_id=customer.tenant_id,
            reply_to_message_id=incoming.id,
            sender_type="assistant",
            content=answer,
            intent=result.get("intent"),
            needs_escalation=int(bool(result.get("escalate"))),
            source_references=result.get("sources", []),
            response_components=[
                item.model_dump() if hasattr(item, "model_dump") else item
                for item in result.get("components", [])
            ],
            follow_up_suggestions=result.get("follow_up_suggestions", []),
            status="SUCCEEDED",
        )
        db.add(reply)
        incoming.status = "SUCCEEDED"
        conversation.updated_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "Unable to process inbound customer SMS; provider_sid=%s",
            message_sid,
        )
        raise

    delivery = enqueue_tracked_sms(
        db,
        tenant_id=str(customer.tenant_id),
        recipient_id=str(customer.id),
        recipient_role="customer",
        to_number=customer.phone_number,
        body=(
            answer
            if len(answer) <= 160
            else "I sent a detailed reply in your FieldOps Support chat. Please open the app to read it."
        ),
        source_type="INBOUND_CUSTOMER_SMS_REPLY",
        source_id=message_sid,
        job_id=next(
            (
                component.get("job_id")
                for component in result.get("components", [])
                if isinstance(component, dict)
                and component.get("type") == "job_status"
            ),
            None,
        ),
        title="FieldOps Support reply",
    )
    if not delivery.get("queued"):
        return {
            "status": "reply_saved_delivery_failed",
            "conversation_id": conversation.id,
            "reply_queued": False,
        }

    return {
        "status": "replied",
        "conversation_id": conversation.id,
        "reply_queued": True,
        "delivery_id": delivery.get("delivery_id"),
    }
