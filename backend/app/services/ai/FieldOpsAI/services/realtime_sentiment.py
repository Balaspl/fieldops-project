from typing import Optional

from sqlalchemy.orm import Session
import re
from app.models import Job, SentimentThreadMessage, User
from app.services.ai.integrations.sentiment_integration import (
    SentimentIntegration,
)
from app.services.dispatcher_alert_service import DispatcherAlertService
from app.sentiment.retention import RetentionWorkflowService
from app.sentiment.audit import SentimentAuditLogger

from app.sentiment.escalation import (
    SentimentEscalationService,
)

class RealTimeSentimentScorer:
    """
    Coordinates real-time sentiment analysis for incoming
    customer replies.

    Uses the existing 12.1 sentiment pipeline.
    """

    def __init__(
        self,
        db: Session,
    ):
        self.db = db
        self.sentiment_integration = SentimentIntegration()
        self.audit_logger = SentimentAuditLogger(db)
        self.escalation_service = SentimentEscalationService(db)


    def _get_previous_messages(
        self,
        customer_id: int | str,
        job_id: int | None,
        source_type: str | None = None,
    ) -> list[str]:
        """
        Return the previous 3 customer messages for the
        same customer and job.
        """

        records = (
            self.db.query(SentimentThreadMessage)
            .filter(
                SentimentThreadMessage.customer_id
                == str(customer_id),
                SentimentThreadMessage.job_id == job_id,
                *([SentimentThreadMessage.source_type == source_type] if source_type else []),
            )
            .order_by(
                SentimentThreadMessage.created_at.desc()
            )
            .limit(3)
            .all()
        )

        return [
            record.message
            for record in reversed(records)
        ]

    async def score_reply(
        self,
        reply_text: str,
        customer_id: int | str,
        job_id: int | None,
        channel: str,
        language: Optional[str] = None,
        context: Optional[list[str]] = None,
        source_message_id: Optional[str] = None,
        source_type: Optional[str] = None,
        source_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ):
        """
        Analyze and persist an incoming customer reply.
        """

        if not reply_text or not reply_text.strip():
            return None

        language = language or self._detect_language(reply_text)

        if source_message_id:
            existing = (
                self.db.query(SentimentThreadMessage)
                .filter(SentimentThreadMessage.source_message_id == source_message_id)
                .first()
            )
            if existing:
                return existing

        source_type = (source_type or channel).upper()
        if source_id:
            existing = self.db.query(SentimentThreadMessage).filter(
                SentimentThreadMessage.source_type == source_type,
                SentimentThreadMessage.source_id == str(source_id),
            ).first()
            if existing:
                return existing

        supported_channels = {
            "EMAIL", "SMS", "CHAT", "WHATSAPP", "PORTAL", "SUPPORT_TICKET",
            "DISPATCH_NOTE", "JOB_CHAT", "SUPPORT_CHAT", "JOB_FEEDBACK", "SUPPORT_CASE",
        }

        if channel.upper() not in supported_channels:
            raise ValueError(
                f"Unsupported sentiment channel: {channel}"
            )

        channel = channel.upper()

        
        if self._is_automated_reply(reply_text):
            return None


        previous_messages = (
            context
            if context is not None
            else self._get_previous_messages(
                customer_id=customer_id,
                job_id=job_id,
                source_type=source_type if job_id is None else None,
            )
        )

        result = self.sentiment_integration.analyze(
            message=reply_text,
            channel=channel,
            language=language,
            previous_messages=previous_messages[-3:],
        )

        negative_alert = self._should_alert_negative(result)
        sentiment_shift = self._has_sentiment_shift(
            previous_messages=previous_messages,
            current_sentiment=result.sentiment,
        )

        if negative_alert or sentiment_shift:
            alert_reason = (
                "positive_to_negative_shift"
                if sentiment_shift
                else "negative_high_confidence"
            )
            job = self.db.query(Job).filter(Job.id == job_id).first() if job_id is not None else None

            if job:
                DispatcherAlertService.trigger_sentiment_alert(
                    db=self.db,
                    job=job,
                    sentiment=result.sentiment,
                    confidence=result.confidence,
                    alert_reason=alert_reason,
                )

        sentiment_record = SentimentThreadMessage(
            tenant_id=tenant_id or self._get_tenant_id(job_id),
            customer_id=str(customer_id),
            job_id=job_id,
            channel=channel,
            message=reply_text,
            sentiment=result.sentiment,
            confidence=result.confidence,
            emotion=getattr(
                result,
                "emotion",
                None,
            ),
            urgency=getattr(
                result,
                "urgency",
                None,
            ),
            requires_human=str(
                getattr(
                    result,
                    "requires_human",
                    None,
                )
            ),
            summary=getattr(
                result,
                "summary",
                None,
            ),
            severity=getattr(result, "severity", None),
            issue_categories=getattr(result, "issue_categories", []),
            recommended_action=getattr(result, "recommended_action", None),
            source_message_id=source_message_id,
            source_type=source_type,
            source_id=str(source_id) if source_id is not None else source_message_id,
        )

        self.db.add(sentiment_record)
        self.db.commit()
        self.db.refresh(sentiment_record)

        escalation = self.escalation_service.create_escalation(
            message=sentiment_record,
            suggested_action=getattr(result, "recommended_action", None),
        )

        if escalation:
            customer = (
        self.db.query(User)
        .filter(User.id == str(customer_id))
        .first()
    )

            if customer and channel not in {"JOB_CHAT", "SUPPORT_CHAT", "JOB_FEEDBACK", "SUPPORT_CASE"}:
                await self.escalation_service.send_auto_response(
                customer_phone=customer.phone_number,
                escalation=escalation,
        )

            await self.escalation_service.notify_manager(
                escalation
    )

        job = self.db.query(Job).filter(Job.id == job_id).first() if job_id is not None else None
        if job:
            RetentionWorkflowService(self.db).create_workflow(
                tenant_id=job.tenant_id,
                customer_id=str(customer_id),
                sentiment=result.sentiment,
                confidence=result.confidence,
                message=reply_text,
            )

        return result

    @staticmethod
    def _detect_language(message: str) -> str:
        """Detect supported scripts and common Spanish cues locally."""
        if any("\u0b80" <= char <= "\u0bff" for char in message):
            return "ta"
        if any("\u0900" <= char <= "\u097f" for char in message):
            return "hi"
        words = set(re.findall(r"[a-záéíóúüñ]+", message.lower()))
        if words & {
            "gracias", "hola", "bueno", "buena", "excelente", "problema",
            "queja", "retraso", "molesto", "molesta", "decepcionado",
            "decepcionada", "funciona", "servicio", "técnico", "técnica",
        }:
            return "es"
        return "en"

    def _get_tenant_id(
        self,
        job_id: int,
    ) -> str:
        """
        Get tenant ID from the associated job.
        """

        job = (
            self.db.query(Job)
            .filter(
                Job.id == job_id
            )
            .first()
        )

        if job is None:
            raise ValueError(
                f"Job {job_id} not found."
            )

        if not job.tenant_id:
            raise ValueError(
                f"Job {job_id} does not have a tenant_id."
            )

        return job.tenant_id

    def _is_automated_reply(self, message: str) -> bool:
        """
        Detect common automated replies such as
        out-of-office and bounce messages.
        """

        automated_patterns = [
            r"\bout of office\b",
            r"\bautomatic reply\b",
            r"\bauto[- ]?reply\b",
            r"\bautoreply\b",
            r"\bmail delivery failed\b",
            r"\bdelivery failed\b",
            r"\bmessage could not be delivered\b",
            r"\baddress not found\b",
            r"\buser unknown\b",
            r"\bmailbox unavailable\b",
            r"\bdelivery status notification\b",
        ]

        return any(
            re.search(
                pattern,
                message,
                re.IGNORECASE,
            )
            for pattern in automated_patterns
        )

    def _should_alert_negative(self, result) -> bool:
        """
        Return True when sentiment is negative
        with high confidence.
        """

        return (
            result.sentiment == "NEGATIVE"
            and result.confidence > 0.8
        )

    def _has_sentiment_shift(
        self,
        previous_messages: list[str],
        current_sentiment: str,
    ) -> bool:
        """
        Detect a POSITIVE -> NEGATIVE sentiment shift.

        The previous messages are analyzed using the existing
        sentiment integration.
        """

        if current_sentiment != "NEGATIVE":
            return False

        if not previous_messages:
            return False

        previous_result = self.sentiment_integration.analyze(
            message=previous_messages[-1],
            channel="SMS",
            language="en",
            previous_messages=previous_messages[:-1],
        )

        return previous_result.sentiment == "POSITIVE"

    def get_job_sentiment_summary(
        self,
        job_id: int,
    ) -> dict:
        """
        Calculate average sentiment score and trend for a job.
        """

        records = (
            self.db.query(SentimentThreadMessage)
            .filter(
                SentimentThreadMessage.job_id == job_id
            )
            .order_by(
                SentimentThreadMessage.created_at.asc()
            )
            .all()
        )

        if not records:
            return {
                "job_id": job_id,
                "average_score": 0.0,
                "trend": "NEUTRAL",
            }

        sentiment_values = {
            "POSITIVE": 1.0,
            "MIXED": 0.5,
            "NEUTRAL": 0.0,
            "NEGATIVE": -1.0,
        }

        scores = [
            sentiment_values.get(
                record.sentiment,
                0.0,
            )
            for record in records
        ]

        average_score = sum(scores) / len(scores)

        if len(scores) < 2:
            trend = "NEUTRAL"
        else:
            previous_score = scores[-2]
            latest_score = scores[-1]

            if latest_score > previous_score:
                trend = "IMPROVING"
            elif latest_score < previous_score:
                trend = "DECLINING"
            else:
                trend = "STABLE"

        return {
            "job_id": job_id,
            "average_score": round(average_score, 3),
            "trend": trend,
        }
