"""Background sentiment analysis for customer-authored messages and feedback."""

import asyncio
import logging

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models import (
    CustomerChatConversation,
    CustomerChatMessage,
    CustomerFeedback,
    CustomerSupportCaseUpdate,
    CustomerSupportRequest,
    JobMessage,
)
from app.services.ai.FieldOpsAI.services.realtime_sentiment import RealTimeSentimentScorer

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=20,
    name="app.sentiment.analyze_customer_job_message",
)
def analyze_customer_job_message(self, message_id: str) -> dict:
    db = SessionLocal()
    try:
        message = db.query(JobMessage).filter(JobMessage.id == message_id).first()
        if message is None or message.sender_role.upper() != "CUSTOMER":
            return {"status": "skipped", "reason": "not_customer_message"}

        result = asyncio.run(
            RealTimeSentimentScorer(db).score_reply(
                reply_text=message.body,
                customer_id=int(message.sender_user_id) if message.sender_user_id.isdigit() else message.sender_user_id,
                job_id=message.job_id,
                channel="JOB_CHAT",
                source_message_id=message.id,
            )
        )
        return {
            "status": "analyzed" if result is not None else "skipped",
            "message_id": message.id,
            "sentiment": getattr(result, "sentiment", None),
        }
    except Exception as exc:
        logger.exception("Customer job message sentiment analysis failed: %s", message_id)
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=20,
    name="app.sentiment.analyze_customer_support_message",
)
def analyze_customer_support_message(self, message_id: int) -> dict:
    db = SessionLocal()
    try:
        message = db.query(CustomerChatMessage).filter(CustomerChatMessage.id == message_id).first()
        if message is None or message.sender_type != "customer":
            return {"status": "skipped", "reason": "not_customer_message"}
        conversation = db.query(CustomerChatConversation).filter(
            CustomerChatConversation.id == message.conversation_id,
            CustomerChatConversation.tenant_id == message.tenant_id,
        ).first()
        if conversation is None:
            return {"status": "skipped", "reason": "conversation_not_found"}
        prior_rows = db.query(CustomerChatMessage).filter(
            CustomerChatMessage.conversation_id == message.conversation_id,
            CustomerChatMessage.tenant_id == message.tenant_id,
            CustomerChatMessage.sender_type == "customer",
            CustomerChatMessage.id < message.id,
        ).order_by(CustomerChatMessage.id.desc()).limit(3).all()
        result = asyncio.run(RealTimeSentimentScorer(db).score_reply(
            reply_text=message.content,
            customer_id=conversation.customer_user_id,
            job_id=None,
            channel="SUPPORT_CHAT",
            context=[row.content for row in reversed(prior_rows)],
            tenant_id=message.tenant_id,
            source_type="SUPPORT_CHAT",
            source_id=str(message.id),
        ))
        return {
            "status": "analyzed" if result is not None else "skipped",
            "message_id": message.id,
            "sentiment": getattr(result, "sentiment", None),
        }
    except Exception as exc:
        logger.exception("Customer support message sentiment analysis failed: %s", message_id)
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=20,
    name="app.sentiment.analyze_customer_job_feedback",
)
def analyze_customer_job_feedback(self, feedback_id: int) -> dict:
    """Analyze written customer feedback, with the star rating as context."""
    db = SessionLocal()
    try:
        feedback = db.query(CustomerFeedback).filter(CustomerFeedback.id == feedback_id).first()
        if feedback is None or not (feedback.comment or "").strip():
            return {"status": "skipped", "reason": "no_written_feedback"}

        message = f"Customer rating: {feedback.rating}/5. Written feedback: {feedback.comment.strip()}"
        result = asyncio.run(RealTimeSentimentScorer(db).score_reply(
            reply_text=message,
            customer_id=feedback.customer_id,
            job_id=feedback.job_id,
            channel="JOB_FEEDBACK",
            tenant_id=feedback.tenant_id,
            source_type="JOB_FEEDBACK",
            source_id=str(feedback.id),
        ))
        return {
            "status": "analyzed" if result is not None else "skipped",
            "feedback_id": feedback.id,
            "sentiment": getattr(result, "sentiment", None),
        }
    except Exception as exc:
        logger.exception("Customer job feedback sentiment analysis failed: %s", feedback_id)
        raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=20,
    name="app.sentiment.analyze_customer_support_case",
)
def analyze_customer_support_case(self, support_request_id: int, update_id: int | None = None) -> dict:
    """Analyze a submitted support request or a later customer-authored update."""
    db = SessionLocal()
    try:
        support_request = db.query(CustomerSupportRequest).filter(
            CustomerSupportRequest.id == support_request_id
        ).first()
        if support_request is None:
            return {"status": "skipped", "reason": "support_request_not_found"}

        if update_id is None:
            # Chat-originated cases already have each customer chat message analyzed.
            if support_request.source_chat_conversation_id:
                return {"status": "skipped", "reason": "chat_messages_analyzed_separately"}
            message = f"Support request: {support_request.subject}. Details: {support_request.description}"
            source_type = "SUPPORT_CASE"
            source_id = str(support_request.id)
        else:
            update = db.query(CustomerSupportCaseUpdate).filter(
                CustomerSupportCaseUpdate.id == update_id,
                CustomerSupportCaseUpdate.support_request_id == support_request.id,
                CustomerSupportCaseUpdate.author_role == "customer",
            ).first()
            if update is None:
                return {"status": "skipped", "reason": "customer_update_not_found"}
            message = update.message
            source_type = "SUPPORT_CASE_UPDATE"
            source_id = str(update.id)

        if not message.strip():
            return {"status": "skipped", "reason": "empty_support_message"}

        result = asyncio.run(RealTimeSentimentScorer(db).score_reply(
            reply_text=message,
            customer_id=support_request.customer_user_id,
            job_id=support_request.related_job_id,
            channel="SUPPORT_CASE",
            tenant_id=support_request.tenant_id,
            source_type=source_type,
            source_id=source_id,
        ))
        return {
            "status": "analyzed" if result is not None else "skipped",
            "support_request_id": support_request.id,
            "sentiment": getattr(result, "sentiment", None),
            "source_type": source_type,
        }
    except Exception as exc:
        logger.exception("Customer support case sentiment analysis failed: case=%s", support_request_id)
        raise self.retry(exc=exc)
    finally:
        db.close()
