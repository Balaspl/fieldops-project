"""Authenticated customer support chat endpoints."""

from datetime import datetime, timezone
import uuid
import logging
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser, get_current_user, require_role
from app.auth.rbac import UserRole
from app.database import get_db
from app.models import CustomerChatConversation, CustomerChatMessage, CustomerSupportFAQ, CustomerSupportRequest
from app.middleware.rate_limit import RateLimitPolicy, rate_limit_dependency
from app.services.customer_support_graph import customer_support_graph
from app.services.customer_support_cases import create_support_case

router = APIRouter(prefix="/api/v1/customer/chat", tags=["Customer Support Chat"], dependencies=[Depends(require_role(UserRole.CUSTOMER))])
logger = logging.getLogger(__name__)
faq_router = APIRouter(prefix="/api/v1/admin/customer-support/faqs", tags=["Customer Support FAQ"], dependencies=[Depends(require_role(UserRole.SUPER_ADMIN))])
_chat_limiter = rate_limit_dependency(RateLimitPolicy("customer_chat", 300, 60, False))
_tenant_chat_limiter = rate_limit_dependency(RateLimitPolicy("customer_chat_tenant", 1000, 60, False))


async def authenticated_chat_rate_limit(request: Request, user: AuthenticatedUser = Depends(get_current_user)) -> None:
    request.state.tenant_id = user.tenant_id
    request.state.user_id = user.user_id
    await _chat_limiter(request)
    request.state.user_id = None
    await _tenant_chat_limiter(request)


class SendMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, min_length=36, max_length=36)
    client_message_id: str = Field(min_length=36, max_length=36)


class CreateConversation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=120)


class SupportCaseFromChat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    related_job_id: int | None = Field(default=None, ge=1)


class FAQUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=4, max_length=500)
    answer: str = Field(min_length=1, max_length=4000)
    category: str = Field(min_length=2, max_length=60)
    faq_key: str | None = Field(default=None, min_length=2, max_length=100)
    alternate_questions: list[str] = Field(default_factory=list, max_length=20)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    language: str = Field(default="en", min_length=2, max_length=12)
    is_published: bool = True


class SupportComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["job_status", "service_catalog", "support"]
    title: str = Field(max_length=160)
    status: str | None = Field(default=None, max_length=40)
    job_id: int | None = Field(default=None, ge=1)
    preferred_service_date: str | None = Field(default=None, max_length=40)
    arrival_estimate: str | None = Field(default=None, max_length=60)
    completed_at: str | None = Field(default=None, max_length=60)
    closure_report_available: bool = False
    items: list[str] = Field(default_factory=list, max_length=30)
    action: Literal["service_requests", "tracking", "support", "create_support_case", "download_report"] | None = None


class SupportReply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1, max_length=4000)
    intent: str | None = Field(default=None, max_length=40)
    sources: list[dict[str, str | int]] = Field(default_factory=list, max_length=10)
    escalation: bool = False
    components: list[SupportComponent] = Field(default_factory=list, max_length=10)
    follow_up_suggestions: list[str] = Field(default_factory=list, max_length=10)


@faq_router.get("")
def list_faqs(user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(CustomerSupportFAQ).filter(
        (CustomerSupportFAQ.tenant_id == user.tenant_id) | (CustomerSupportFAQ.tenant_id.is_(None))
    ).order_by(CustomerSupportFAQ.category, CustomerSupportFAQ.question).all()
    return {"faqs": [{"id": row.id, "tenant_id": row.tenant_id, "faq_key": row.faq_key, "question": row.question, "alternate_questions": row.alternate_questions or [], "keywords": row.keywords or [], "answer": row.answer, "category": row.category, "language": row.language, "is_published": bool(row.is_published)} for row in rows]}


@faq_router.post("", status_code=status.HTTP_201_CREATED)
def create_faq(payload: FAQUpsert, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    row = CustomerSupportFAQ(tenant_id=user.tenant_id, faq_key=payload.faq_key.strip().lower() if payload.faq_key else None, question=payload.question.strip(), alternate_questions=[q.strip() for q in payload.alternate_questions if q.strip()], keywords=[k.strip().lower() for k in payload.keywords if k.strip()], answer=payload.answer.strip(), category=payload.category.strip(), language=payload.language.strip().lower(), is_published=int(payload.is_published), created_by=user.user_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "tenant_id": row.tenant_id, "faq_key": row.faq_key, "question": row.question, "alternate_questions": row.alternate_questions, "keywords": row.keywords, "answer": row.answer, "category": row.category, "language": row.language, "is_published": bool(row.is_published)}


@faq_router.patch("/{faq_id}")
def update_faq(faq_id: int, payload: FAQUpsert, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(CustomerSupportFAQ).filter(CustomerSupportFAQ.id == faq_id, CustomerSupportFAQ.tenant_id == user.tenant_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="FAQ not found")
    row.question = payload.question.strip()
    row.faq_key = payload.faq_key.strip().lower() if payload.faq_key else None
    row.alternate_questions = [q.strip() for q in payload.alternate_questions if q.strip()]
    row.keywords = [k.strip().lower() for k in payload.keywords if k.strip()]
    row.answer = payload.answer.strip()
    row.category = payload.category.strip()
    row.language = payload.language.strip().lower()
    row.is_published = int(payload.is_published)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "tenant_id": row.tenant_id, "faq_key": row.faq_key, "question": row.question, "alternate_questions": row.alternate_questions, "keywords": row.keywords, "answer": row.answer, "category": row.category, "language": row.language, "is_published": bool(row.is_published)}


def _conversation(db: Session, user: AuthenticatedUser, conversation_id: str) -> CustomerChatConversation:
    conversation = db.query(CustomerChatConversation).filter(
        CustomerChatConversation.id == conversation_id,
        CustomerChatConversation.tenant_id == user.tenant_id,
        CustomerChatConversation.customer_user_id == user.user_id,
    ).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def _message_dict(message: CustomerChatMessage) -> dict:
    return {"id": message.id, "sender": message.sender_type, "content": message.content,
            "created_at": message.created_at, "intent": message.intent, "status": message.status,
            "escalation": bool(message.needs_escalation),
            "components": message.response_components or [],
            "follow_up_suggestions": message.follow_up_suggestions or []}


@router.get("/conversations")
def list_conversations(user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(CustomerChatConversation).filter_by(tenant_id=user.tenant_id, customer_user_id=user.user_id).order_by(desc(CustomerChatConversation.updated_at)).limit(50).all()
    return {"conversations": [{"id": row.id, "title": row.title, "status": row.status, "created_at": row.created_at, "updated_at": row.updated_at} for row in rows]}


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
def create_conversation(payload: CreateConversation, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    row = CustomerChatConversation(id=str(uuid.uuid4()), tenant_id=user.tenant_id, customer_user_id=user.user_id, title=payload.title)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "title": row.title, "status": row.status, "created_at": row.created_at, "updated_at": row.updated_at}


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    conversation = _conversation(db, user, conversation_id)
    messages = db.query(CustomerChatMessage).filter_by(tenant_id=user.tenant_id, conversation_id=conversation.id).order_by(CustomerChatMessage.created_at, CustomerChatMessage.id).all()
    return {"id": conversation.id, "title": conversation.title, "status": conversation.status, "messages": [_message_dict(message) for message in messages]}


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: str, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Delete only the authenticated customer's chat session and its messages."""
    conversation = _conversation(db, user, conversation_id)
    linked_case = db.query(CustomerSupportRequest).filter_by(
        source_chat_conversation_id=conversation.id,
        tenant_id=user.tenant_id,
        customer_user_id=user.user_id,
    ).first()
    if linked_case:
        raise HTTPException(status_code=409, detail="This conversation is attached to support request " + linked_case.request_number + " and is retained for the support team.")
    db.query(CustomerChatMessage).filter(
        CustomerChatMessage.tenant_id == user.tenant_id,
        CustomerChatMessage.conversation_id == conversation.id,
    ).delete(synchronize_session=False)
    db.delete(conversation)
    db.commit()


@router.post("/conversations/{conversation_id}/support-case")
def create_case_from_chat(
    conversation_id: str,
    payload: SupportCaseFromChat,
    response: Response,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conversation = _conversation(db, user, conversation_id)
    messages = db.query(CustomerChatMessage).filter(
        CustomerChatMessage.conversation_id == conversation.id,
        CustomerChatMessage.tenant_id == user.tenant_id,
        CustomerChatMessage.status == "SUCCEEDED",
    ).order_by(CustomerChatMessage.created_at, CustomerChatMessage.id).all()
    customer_messages = [row for row in messages if row.sender_type == "customer"]
    if not customer_messages:
        raise HTTPException(status_code=400, detail="Send a message before creating a support request.")
    escalation_reply = next((row for row in reversed(messages) if row.sender_type == "assistant" and row.needs_escalation and row.reply_to_message_id), None)
    issue_message = next((row for row in customer_messages if escalation_reply and row.id == escalation_reply.reply_to_message_id), customer_messages[-1])
    latest_customer_message = issue_message.content.strip()
    subject = re.sub(r"\s+", " ", latest_customer_message).strip(" .!?\n")[:190] or "Customer support request from chat"
    related_job_id = payload.related_job_id
    if related_job_id is None:
        for row in reversed(messages):
            for component in row.response_components or []:
                if component.get("type") == "job_status" and component.get("job_id"):
                    related_job_id = component["job_id"]
                    break
            if related_job_id:
                break
    case, created = create_support_case(
        db,
        customer_id=user.user_id,
        tenant_id=user.tenant_id,
        subject=subject,
        description=latest_customer_message,
        related_job_id=related_job_id,
        source_chat_conversation_id=conversation.id,
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return {
        "id": case.id,
        "request_number": case.request_number,
        "status": case.status,
        "priority": case.priority,
        "created": created,
        "message": "Your conversation is now linked to a support case. The support team can review the chat and follow up here.",
    }


@router.post("", dependencies=[Depends(authenticated_chat_rate_limit)])
def send_message(payload: SendMessage, user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if not payload.message.strip():
        raise HTTPException(status_code=422, detail="Message cannot be blank")
    try:
        uuid.UUID(payload.client_message_id)
        if payload.conversation_id:
            uuid.UUID(payload.conversation_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid identifier")
    if payload.conversation_id:
        conversation = _conversation(db, user, payload.conversation_id)
    else:
        conversation = CustomerChatConversation(id=str(uuid.uuid4()), tenant_id=user.tenant_id, customer_user_id=user.user_id)
        db.add(conversation)
        db.flush()
    prior = db.query(CustomerChatMessage).filter_by(conversation_id=conversation.id, client_message_id=payload.client_message_id).first()
    if prior:
        assistant = db.query(CustomerChatMessage).filter_by(reply_to_message_id=prior.id, sender_type="assistant").first()
        if assistant:
            return {"conversation_id": conversation.id, "answer": assistant.content, "intent": assistant.intent, "sources": assistant.source_references, "escalation": bool(assistant.needs_escalation), "components": assistant.response_components or [], "follow_up_suggestions": assistant.follow_up_suggestions or []}
        if prior.status == "PENDING":
            return {"conversation_id": conversation.id, "answer": "Your message is being processed.", "intent": None, "sources": [], "escalation": False}
        incoming = prior
        incoming.status = "PENDING"
    else:
        incoming = CustomerChatMessage(conversation_id=conversation.id, tenant_id=user.tenant_id, sender_type="customer", content=payload.message.strip(), client_message_id=payload.client_message_id, status="PENDING")
        db.add(incoming)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        prior = db.query(CustomerChatMessage).filter_by(conversation_id=conversation.id, client_message_id=payload.client_message_id).first()
        if not prior:
            raise HTTPException(status_code=409, detail="Unable to accept this message. Please retry.")
        assistant = db.query(CustomerChatMessage).filter_by(reply_to_message_id=prior.id).first()
        return {"conversation_id": conversation.id, "answer": assistant.content if assistant else "Your message is being processed.", "intent": assistant.intent if assistant else None, "sources": assistant.source_references if assistant else [], "escalation": bool(assistant.needs_escalation) if assistant else False, "components": (assistant.response_components or []) if assistant else [], "follow_up_suggestions": (assistant.follow_up_suggestions or []) if assistant else []}
    try:
        from app.sentiment.job_message_tasks import analyze_customer_support_message
        analyze_customer_support_message.delay(incoming.id)
    except Exception:
        # Sentiment is supplemental; support chat remains available if Celery is down.
        logger.exception("Unable to queue support chat sentiment analysis for message %s", incoming.id)
    try:
        history_rows = db.query(CustomerChatMessage).filter(
            CustomerChatMessage.tenant_id == user.tenant_id,
            CustomerChatMessage.conversation_id == conversation.id,
            CustomerChatMessage.id < incoming.id,
            CustomerChatMessage.status == "SUCCEEDED",
        ).order_by(desc(CustomerChatMessage.id)).limit(8).all()
        history = [{"sender": item.sender_type, "content": item.content, "components": item.response_components or []} for item in reversed(history_rows)]
        result = customer_support_graph.invoke({"db": db, "tenant_id": user.tenant_id, "customer_id": user.user_id, "conversation_id": conversation.id, "message": payload.message.strip(), "history": history})
        answer = str(result.get("answer", "I couldn’t verify an answer. Please contact FieldOps Support."))[:4000]
        reply = SupportReply(answer=answer, intent=result.get("intent"), sources=result.get("sources", []), escalation=bool(result.get("escalate")), components=result.get("components", []), follow_up_suggestions=result.get("follow_up_suggestions", []))
        response = CustomerChatMessage(conversation_id=conversation.id, tenant_id=user.tenant_id, reply_to_message_id=incoming.id, sender_type="assistant", content=reply.answer, intent=reply.intent, needs_escalation=int(reply.escalation), source_references=reply.sources, response_components=[item.model_dump() for item in reply.components], follow_up_suggestions=reply.follow_up_suggestions, status="SUCCEEDED")
        db.add(response)
        incoming.status = "SUCCEEDED"
        conversation.updated_at = datetime.now(timezone.utc)
        db.commit()
        return {"conversation_id": conversation.id, **reply.model_dump()}
    except Exception:
        db.rollback()
        failed = db.query(CustomerChatMessage).filter_by(conversation_id=conversation.id, client_message_id=payload.client_message_id).first()
        if failed:
            failed.status = "FAILED"
            db.commit()
        # Keep the customer message, and return a safe retryable fallback.
        raise HTTPException(status_code=503, detail="Support chat is temporarily unavailable. Please retry.")
