from datetime import datetime, timedelta, timezone
import logging


from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.sentiment import SentimentThreadMessage
from app.models.sentiment_escalation import SentimentEscalation
from app.models.user import User
from app.sentiment.audit import SentimentAuditLogger

logger = logging.getLogger(__name__)


class SentimentEscalationService:
    """
    Handles negative-sentiment escalation detection,
    manager assignment, suppression, and escalation records.
    """

    COMPLAINT_KEYWORDS = {
        "terrible",
        "worst",
        "never again",
        "cancel",
        "refund",
    }

    ACKNOWLEDGE_SLA_MINUTES = 15
    RESOLVE_SLA_HOURS = 2
    SUPPRESSION_MINUTES = 30

    def __init__(self, db: Session):
        self.db = db
        self.audit_logger = SentimentAuditLogger(db)

    def detect_triggers(
        self,
        message: SentimentThreadMessage,
    ) -> list[str]:
        """
        Detect all escalation triggers for a customer message.
        """

        triggers: list[str] = []

        # 1. Negative sentiment with confidence > 0.8
        if (
            message.sentiment.upper() == "NEGATIVE"
            and message.confidence > 0.8
        ):
            triggers.append("NEGATIVE_SENTIMENT")

        # 2. Explicit complaint keywords
        message_text = message.message.lower()

        if any(
            keyword in message_text
            for keyword in self.COMPLAINT_KEYWORDS
        ):
            triggers.append("COMPLAINT_KEYWORD")

        # 3. Two or more negative replies in the same job/thread
        negative_count = (
            self.db.query(SentimentThreadMessage)
            .filter(
                and_(
                    SentimentThreadMessage.job_id == message.job_id,
                    SentimentThreadMessage.sentiment.ilike("NEGATIVE"),
                )
            )
            .count()
        )

        if negative_count >= 2:
            triggers.append("REPEATED_NEGATIVE")

        # 4. Customer explicitly requests human/agent
        requires_human = str(
            message.requires_human or ""
        ).lower()

        human_request = any(
            phrase in message_text
            for phrase in (
                "human",
                "agent",
                "speak to someone",
                "talk to someone",
                "manager",
            )
        )

        if requires_human in {"true", "yes", "1"} or human_request:
            triggers.append("HUMAN_REQUEST")

        return triggers

    def is_suppressed(self, job_id: int) -> bool:
        """
        Prevent re-escalation for the same job within 30 minutes.
        """

        cutoff = datetime.now(timezone.utc) - timedelta(
            minutes=self.SUPPRESSION_MINUTES
        )

        existing = (
            self.db.query(SentimentEscalation.id)
            .filter(
                SentimentEscalation.job_id == job_id,
                SentimentEscalation.created_at >= cutoff,
            )
            .first()
        )

        return existing is not None

    def assign_manager(self, tenant_id: str) -> User | None:
        """
        Assign an active manager using round-robin order.
        """

        managers = (
            self.db.query(User)
            .filter(
                User.tenant_id == tenant_id,
                User.role.ilike("MANAGER"),
                User.is_active.is_(True),
                User.is_on_duty.is_(True),
            )
            .order_by(User.id)
            .all()
        )

        if not managers:
            return None

        # Use the most recently assigned manager for this tenant.
        last_assignment = (
            self.db.query(SentimentEscalation)
            .filter(
                SentimentEscalation.tenant_id == tenant_id,
                SentimentEscalation.assigned_manager_id.isnot(None),
            )
            .order_by(SentimentEscalation.created_at.desc())
            .first()
        )

        if not last_assignment:
            return managers[0]

        manager_ids = [manager.id for manager in managers]

        try:
            last_index = manager_ids.index(
                last_assignment.assigned_manager_id
            )
        except ValueError:
            return managers[0]

        next_index = (last_index + 1) % len(managers)

        return managers[next_index]

    def get_manager_contact(self, manager: User) -> dict:
        """
        Get manager contact details for escalation notifications.
        """

        return {
            "manager_id": manager.id,
            "email": manager.email,
            "phone_number": manager.phone_number,
        }

    def build_escalation_payload(
        self,
        escalation: SentimentEscalation,
    ) -> dict:
        """
        Build the notification payload for the assigned manager.
        """

        return {
            "escalation_id": escalation.id,
            "customer_name": escalation.customer_name,
            "job_id": escalation.job_id,
            "sentiment_score": escalation.sentiment_score,
            "sentiment_label": escalation.sentiment_label,
            "reply_text": escalation.reply_text,
            "technician_name": escalation.technician_name,
            "trigger_reason": escalation.trigger_reason,
            "suggested_action": escalation.suggested_action,
            "status": escalation.status,
            "acknowledge_deadline": escalation.acknowledge_deadline,
            "resolve_deadline": escalation.resolve_deadline,
        }

    def check_sla_breach(
        self,
        escalation: SentimentEscalation,
    ) -> str | None:
        """
        Check whether an open escalation has breached
        its acknowledgement or resolution SLA.
        """

        now = datetime.now(timezone.utc)

        if escalation.status == "OPEN":
            if now >= escalation.resolve_deadline:
                return "RESOLVE_SLA_BREACHED"

            if now >= escalation.acknowledge_deadline:
                return "ACKNOWLEDGE_SLA_BREACHED"

        return None

    def create_escalation(
        self,
        message: SentimentThreadMessage,
        technician_name: str | None = None,
        suggested_action: str | None = None,
    ) -> SentimentEscalation | None:
        """
        Create an escalation record when a message requires escalation.
        """

        triggers = self.detect_triggers(message)

        if not triggers:
            return None

        if self.is_suppressed(message.job_id):
            return None

        manager = self.assign_manager(message.tenant_id)
        customer = (
    self.db.query(User)
    .filter(User.id == message.customer_id)
    .first()
)

        customer_name = (
    f"{customer.first_name} {customer.last_name}"
    if customer
    else "Unknown"
)
        customer_phone = (
    customer.phone_number
    if customer
    else None
)

        now = datetime.now(timezone.utc)

        escalation = SentimentEscalation(
            tenant_id=message.tenant_id,
            job_id=message.job_id,
            customer_id=message.customer_id,
            customer_name=customer_name,
            technician_name=technician_name,
            reply_text=message.message,
            sentiment_label=message.sentiment,
            sentiment_score=message.confidence,
            trigger_reason=",".join(triggers),
            suggested_action=suggested_action,
            assigned_manager_id=manager.id if manager else None,
            status="OPEN",
            created_at=now,
            acknowledge_deadline=(
                now + timedelta(
                    minutes=self.ACKNOWLEDGE_SLA_MINUTES
                )
            ),
            resolve_deadline=(
                now + timedelta(
                    hours=self.RESOLVE_SLA_HOURS
                )
            ),
            updated_at=now,
        )

        self.db.add(escalation)
        self.db.flush()

        self.audit_logger.log_escalation(
            {
                "tenant_id": message.tenant_id,
                "customer_id": message.customer_id,
                "job_id": message.job_id,
                "manager_id": (
                    manager.id if manager else None
                ),
                "trigger_reason": ",".join(triggers),
            }
        )

        self.db.commit()
        self.db.refresh(escalation)

        return escalation

    def generate_auto_response(self) -> str:
        return (
            "Your concern has been escalated to a manager "
            "who will contact you within 15 minutes"
        )

    async def send_auto_response(
        self,
        customer_phone: str | None,
    ) -> bool:
        if not customer_phone:
            return False

        try:
            from app.services.twilio_sms import dispatch_twilio_message

            await dispatch_twilio_message(
                body=self.generate_auto_response(),
                to_phone=customer_phone,
            )

            return True

        except Exception:
            logger.exception(
                "Failed to send escalation auto-response."
            )
            return False

    async def notify_manager(
        self,
        escalation: SentimentEscalation,
    ) -> dict:
        """
        Send escalation notifications to the assigned manager.

        Channels:
        - SMS
        - Email
        - Dashboard

        Push is currently not sent because the existing FCM
        helper is designed around technician notification flow.
        """

        # --------------------------------------------------
        # 1. Find assigned manager
        # --------------------------------------------------

        if not escalation.assigned_manager_id:
            return {
                "manager_id": None,
                "sms": False,
                "email": False,
                "push": False,
                "dashboard": False,
            }

        manager = (
            self.db.query(User)
            .filter(
                User.id == escalation.assigned_manager_id
            )
            .first()
        )

        if not manager:
            return {
                "manager_id": None,
                "sms": False,
                "email": False,
                "push": False,
                "dashboard": False,
            }

        payload = self.build_escalation_payload(
            escalation
        )

        result = {
            "manager_id": manager.id,
            "manager_email": manager.email,
            "manager_phone": manager.phone_number,
            "payload": payload,
            "sms": False,
            "email": False,
            "push": False,
            "dashboard": False,
        }

        # --------------------------------------------------
        # 2. Notification message
        # --------------------------------------------------

        subject = (
            "FieldOps Escalation: "
            f"Job #{escalation.job_id}"
        )

        message = (
            "Customer escalation requires your attention.\n\n"
            f"Job ID: {escalation.job_id}\n"
            f"Customer: {escalation.customer_name}\n"
            f"Sentiment: {escalation.sentiment_label}\n"
            f"Confidence: {escalation.sentiment_score}\n"
            f"Trigger: {escalation.trigger_reason}\n"
            f"Reply: {escalation.reply_text}\n\n"
            "Please acknowledge this escalation "
            "within 15 minutes."
        )

        # --------------------------------------------------
        # 3. SMS
        # --------------------------------------------------

        if manager.phone_number:
            try:
                from app.services.twilio_sms import (
                    dispatch_twilio_message,
                )

                await dispatch_twilio_message(
                    body=message,
                    to_phone=manager.phone_number,
                )

                result["sms"] = True

            except Exception:
                logger.exception(
                    "Failed to send escalation SMS. "
                    "job_id=%s manager_id=%s",
                    escalation.job_id,
                    manager.id,
                )

        # --------------------------------------------------
        # 4. Email
        # --------------------------------------------------

        if manager.email:
            try:
                from app.services.notification_services import (
                    SMTPEmailService,
                )

                email_service = SMTPEmailService()

                body_html = (
                    "<h2>FieldOps Escalation</h2>"
                    f"<p><strong>Job ID:</strong> "
                    f"{escalation.job_id}</p>"
                    f"<p><strong>Customer:</strong> "
                    f"{escalation.customer_name}</p>"
                    f"<p><strong>Sentiment:</strong> "
                    f"{escalation.sentiment_label}</p>"
                    f"<p><strong>Confidence:</strong> "
                    f"{escalation.sentiment_score}</p>"
                    f"<p><strong>Trigger:</strong> "
                    f"{escalation.trigger_reason}</p>"
                    f"<p><strong>Customer Reply:</strong> "
                    f"{escalation.reply_text}</p>"
                    "<p><strong>SLA:</strong> "
                    "Please acknowledge within 15 minutes.</p>"
                )

                delivered = await email_service.send_email(
                    manager.email,
                    subject,
                    body_html,
                )

                result["email"] = bool(delivered)

            except Exception:
                logger.exception(
                    "Failed to send escalation email. "
                    "job_id=%s manager_id=%s",
                    escalation.job_id,
                    manager.id,
                )

        # --------------------------------------------------
        # 5. Push
        # --------------------------------------------------

        if manager.fcm_token:
            try:
                from firebase_admin import messaging

                notification = messaging.Notification(
                    title="FieldOps Escalation",
                    body=(
                        f"Job #{escalation.job_id} requires "
                        "your attention."
                    ),
                )

                message_obj = messaging.Message(
                    token=manager.fcm_token,
                    notification=notification,
                    data={
                        "type": "sentiment_escalation",
                        "escalation_id": str(escalation.id),
                        "job_id": str(escalation.job_id),
                        "status": escalation.status,
                    },
                )

                messaging.send(message_obj)
                result["push"] = True

            except Exception:
                logger.exception(
                    "Failed to send escalation push. "
                    "job_id=%s manager_id=%s",
                    escalation.job_id,
                    manager.id,
                )

        # --------------------------------------------------
        # 6. Dashboard
        # --------------------------------------------------

        try:
            from app.services.socket_manager import (
                default_ws_manager,
            )

            await default_ws_manager.broadcast(
                (
                    "tenant:"
                    f"{escalation.tenant_id}:"
                    "dispatchers"
                ),
                {
                    "type": "sentiment_escalation",
                    "payload": payload,
                },
            )

            result["dashboard"] = True

        except Exception:
            logger.exception(
                "Failed to broadcast escalation to dashboard. "
                "job_id=%s manager_id=%s",
                escalation.job_id,
                manager.id,
            )

        return result
