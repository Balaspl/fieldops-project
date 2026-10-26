from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import asyncio
import json
import uuid
import logging
import uuid

from html import escape
from urllib.parse import quote

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import AuditEvent, Technician, User, InAppNotification
from ..redis_client import get_redis_client
from ..context import correlation_id_ctx

from .preferences import get_technician_preferences

from .ai.integrations.communication_integration import (
    CommunicationIntegration,
    CommunicationIntegrationError,
)

from .ai.FieldOpsAI.services.communication_configuration_service import (
    CommunicationConfigurationService,
)
from .ai.FieldOpsAI.repositories.communication_configuration_repository import (
    CommunicationConfigurationRepository,
)
from .ai.FieldOpsAI.schemas.communication_configuration import (
    CommunicationMessageCategory,
    CommunicationChannelDisabledError,
)
from .ai.FieldOpsAI.services.customer_preference_service import (
    CustomerPreferenceService,
)
from .ai.FieldOpsAI.repositories.customer_profile_repository import (
    CustomerProfileRepository,
)
from .ai.FieldOpsAI.services.communication_delivery_policy_service import (
    CommunicationDeliveryPolicyService,
)


logger = logging.getLogger(__name__)


# ======================================================
# Job Status Event
# ======================================================

@dataclass
class JobStatusEvent:
    job_id: str
    tenant_id: str
    from_status: str
    to_status: str
    actor_id: str
    actor_role: str
    reason: Optional[str]
    timestamp: datetime

    job_title: str
    job_location: str

    technician_id: Optional[str]
    technician_name: Optional[str]

    customer_id: Optional[str]
    customer_name: Optional[str]
    customer_phone: Optional[str]
    customer_email: Optional[str]

    eta: Optional[str]

    notification_channels: list[str]

    event_type: str = "job_status_changed"
    correlation_id: Optional[str] = None
    event_version: Optional[int] = None
    email_managed_by_communication_graph: bool = False


# ======================================================
# SMTP Service
# ======================================================

class SMTPEmailService:
    """Send customer email through the configured SMTP relay."""

    def __init__(self) -> None:
        from .email.smtp_email import SMTPEmailService as DeliveryService
        self._delivery_service = DeliveryService()

    async def send_email(self, to_email: str, subject: str, html_content: str) -> bool:
        result = await self._delivery_service.send_email(
            to_email=to_email,
            subject=subject,
            html_body=html_content,
        )
        return result.success

# ======================================================
# Event Publisher
# ======================================================

class EventPublisher:

    def __init__(
        self,
        redis_client=None,
    ):
        self.redis = (
            redis_client
            if redis_client is not None
            else get_redis_client()
        )

        self.channel = (
            "events:job_status_changed"
        )

    async def publish(
        self,
        event: JobStatusEvent,
    ) -> None:

        payload_dict = {
            "event_type": event.event_type,
            "job_id": event.job_id,
            "tenant_id": event.tenant_id,
            "from_status": event.from_status,
            "to_status": event.to_status,
            "actor_id": event.actor_id,
            "actor_role": event.actor_role,
            "reason": event.reason,
            "timestamp": (
                event.timestamp.isoformat()
                if hasattr(
                    event.timestamp,
                    "isoformat",
                )
                else str(event.timestamp)
            ),
            "job_title": event.job_title,
            "job_location": event.job_location,
            "technician_id": event.technician_id,
            "technician_name": event.technician_name,
            "customer_id": event.customer_id,
            "customer_name": event.customer_name,
            "eta": event.eta,
            "notification_channels": (
                event.notification_channels
            ),
        }

        # --------------------------------------------------
        # Redis Pub/Sub
        # --------------------------------------------------

        if self.redis:
            try:
                self.redis.publish(
                    self.channel,
                    json.dumps(payload_dict),
                )

                logger.info(
                    "Published status event to Redis. "
                    "channel=%s job_id=%s",
                    self.channel,
                    event.job_id,
                )

            except Exception:
                logger.error(
                    "Failed to publish status event to Redis."
                )

        # --------------------------------------------------
        # Audit
        # --------------------------------------------------

        await self._write_audit(event)

    async def _write_audit(
        self,
        event: JobStatusEvent,
    ) -> None:

        db = SessionLocal()

        try:
            audit_record = AuditEvent(
                event_type="job_status_transition",
                tech_id=(
                    event.technician_id
                    or "system"
                ),
                tenant_id=event.tenant_id,
                old_status=event.from_status,
                new_status=event.to_status,
                reason=event.reason,
                job_id=event.job_id,
                actor_id=event.actor_id,
                details={
                    "from_status": event.from_status,
                    "to_status": event.to_status,
                    "reason": event.reason,
                    "job_title": event.job_title,
                    "technician_id": (
                        event.technician_id
                    ),
                    "notification_channels": (
                        event.notification_channels
                    ),
                },
                timestamp=event.timestamp,
                correlation_id=(
                    correlation_id_ctx.get()
                    or None
                ),
            )

            db.add(audit_record)
            db.commit()

            logger.info(
                "AuditEvent written. "
                "job_id=%s status=%s",
                event.job_id,
                event.to_status,
            )

        except Exception:
            db.rollback()

            logger.error(
                "Failed to write AuditEvent."
            )

        finally:
            db.close()


# ======================================================
# Notification Router
# ======================================================

class NotificationRouter:
    """
    Route job-status notifications to configured channels.

    Customer SMS/email content comes from the safe
    CommunicationService workflow.

    Technician push/SMS and dispatcher in-app delivery
    continue using the existing delivery adapters.
    """

    STATUS_NOTIFICATIONS = {

        "ASSIGNED": {
            "technician": {
                "channels": [
                    "push",
                    "sms",
                ],
                "template": (
                    "technician_job_assigned"
                ),
                "priority": "high",
            },
            "dispatcher": {
                "channels": [
                    "in_app",
                ],
                "template": (
                    "dispatcher_job_assigned"
                ),
                "priority": "normal",
                "batch": True,
            },
        },

        "ACCEPTED": {
            "dispatcher": {
                "channels": ["in_app"],
                "template": "dispatcher_job_accepted",
                "priority": "normal",
            },
        },

        "EN_ROUTE": {
            "technician": {
                "channels": [
                    "push",
                ],
                "template": (
                    "technician_journey_started"
                ),
                "priority": "normal",
            },
            "customer": {
                "channels": [
                    "push",
                    "sms",
                ],
                "template": (
                    "technician_en_route"
                ),
                "priority": "high",
                "include_eta": True,
            },
            "dispatcher": {
                "channels": [
                    "in_app",
                ],
                "template": (
                    "dispatcher_en_route"
                ),
                "priority": "normal",
                "batch": True,
            },
        },

        "ON_SITE": {
            "technician": {
                "channels": [
                    "push",
                ],
                "template": (
                    "technician_arrived_on_site"
                ),
                "priority": "normal",
            },
            "customer": {
                "channels": [
                    "push",
                    "sms",
                ],
                "template": (
                    "technician_arrived"
                ),
                "priority": "high",
            },
            "dispatcher": {
                "channels": [
                    "in_app",
                ],
                "template": (
                    "dispatcher_on_site"
                ),
                "priority": "normal",
                "batch": True,
            },
        },

        "IN_PROGRESS": {
            "dispatcher": {
                "channels": ["in_app"],
                "template": "dispatcher_work_started",
                "priority": "normal",
            },
        },

        "REJECTED_BY_TECHNICIAN": {
            "dispatcher": {
                "channels": ["in_app"],
                "template": "dispatcher_technician_rejected",
                "priority": "high",
            },
        },

        "COMPLETED": {
            "technician": {
                "channels": [
                    "push",
                ],
                "template": (
                    "technician_job_completed"
                ),
                "priority": "normal",
            },
            "customer": {
                "channels": [
                    "push",
                    "email",
                ],
                "template": (
                    "job_done_survey"
                ),
                "priority": "normal",
                "include_survey_link": True,
            },
            "dispatcher": {
                "channels": [
                    "in_app",
                ],
                "template": (
                    "dispatcher_completed"
                ),
                "priority": "normal",
                "batch": True,
            },
        },

        "CANCELLED": {
            "technician": {
                "channels": [
                    "push",
                    "sms",
                ],
                "template": (
                    "technician_job_cancelled"
                ),
                "priority": "high",
            },
            "customer": {
                "channels": [
                    "push",
                    "sms",
                    "email",
                ],
                "template": (
                    "job_cancelled_customer"
                ),
                "priority": "high",
            },
            "dispatcher": {
                "channels": [
                    "in_app",
                ],
                "template": (
                    "dispatcher_cancelled"
                ),
                "priority": "high",
                "batch": False,
            },
        },
    }

    # ==================================================
    # Notification Type Aliases
    # ==================================================

    NOTIFICATION_TYPE_ALIASES = {
        "job_assigned": "job_assigned",

        "technician_job_assigned": (
            "job_assigned"
        ),

        "dispatcher_job_assigned": (
            "job_assigned"
        ),

        "journey_started": (
            "technician_en_route"
        ),

        "technician_journey_started": (
            "technician_en_route"
        ),

        "technician_en_route": (
            "technician_en_route"
        ),

        "dispatcher_en_route": (
            "technician_en_route"
        ),

        "arrived_on_site": (
            "technician_arrived"
        ),

        "technician_arrived": (
            "technician_arrived"
        ),

        "technician_arrived_on_site": (
            "technician_arrived"
        ),

        "dispatcher_on_site": (
            "technician_arrived"
        ),

        "job_completed": "job_completed",

        "technician_job_completed": (
            "job_completed"
        ),

        "job_done_survey": (
            "job_completed"
        ),

        "dispatcher_completed": (
            "job_completed"
        ),

        "job_cancelled": (
            "job_cancelled"
        ),

        "technician_job_cancelled": (
            "job_cancelled"
        ),

        "job_cancelled_customer": (
            "job_cancelled"
        ),

        "dispatcher_cancelled": (
            "job_cancelled"
        ),
    }

    # ==================================================
    # Constructor
    # ==================================================

    def __init__(
        self,
        fcm_service=None,
        sms_service=None,
        email_service=None,
        ws_manager=None,
        redis_client=None,
        communication_integration=None,
        lifecycle_event_publisher=None,
    ) -> None:

        if fcm_service is None:
            from .fcm import (
                send_job_assignment_notification,
            )

            fcm_service = (
                send_job_assignment_notification
            )

        if sms_service is None:
            from .twilio_sms import (
                send_job_assignment_sms,
            )

            sms_service = (
                send_job_assignment_sms
            )

        if ws_manager is None:
            from .socket_manager import (
                ws_manager as default_ws_manager,
            )

            ws_manager = default_ws_manager

        self.fcm = fcm_service
        self.sms = sms_service

        self.email = (
            email_service
            if email_service is not None
            else SMTPEmailService()
        )

        self.ws = ws_manager

        self.redis = (
            redis_client
            if redis_client is not None
            else get_redis_client()
        )

        self.communication = (
            communication_integration
            if communication_integration is not None
            else CommunicationIntegration(
                redis_client=self.redis
            )
        )

        self.lifecycle_event_publisher = (
            lifecycle_event_publisher
        )

    # ==================================================
    # Customer Delivery Policy
    # ==================================================

    def _evaluate_customer_delivery_policy(
        self,
        *,
        event: JobStatusEvent,
        channel: str,
        category: CommunicationMessageCategory,
    ):

        with SessionLocal() as db:

            configuration_repository = (
                CommunicationConfigurationRepository(
                    db
                )
            )

            configuration_service = (
                CommunicationConfigurationService(
                    configuration_repository,
                    db,
                    redis_client=self.redis,
                )
            )

            preference_repository = (
                CustomerProfileRepository(
                    db
                )
            )

            preference_service = (
                CustomerPreferenceService(
                    preference_repository
                )
            )

            policy_service = (
                CommunicationDeliveryPolicyService(
                    configuration_service,
                    preference_service,
                )
            )

            return policy_service.evaluate(
                channel=channel,
                category=category,
                recipient_type="CUSTOMER",
                tenant_id=event.tenant_id,
                customer_id=event.customer_id,
            )

    # ==================================================
    # Main Routing
    # ==================================================

    async def route(
        self,
        event: JobStatusEvent,
        lifecycle_event_publisher=None,
    ) -> None:

        from app.services.ai.FieldOpsAI.schemas.prompt_template import (
            normalize_template_status,
            UnsupportedTemplateStatusError,
        )

        try:
            canon_enum = normalize_template_status(
                event.to_status
            )

            canon_status_name = canon_enum.name

            if canon_status_name == "ENROUTE":
                canon_status_name = "EN_ROUTE"

            elif canon_status_name == "ONSITE":
                canon_status_name = "ON_SITE"

        except UnsupportedTemplateStatusError:
            canon_status_name = (
                str(event.to_status).upper()
            )

        routing = (
            self.STATUS_NOTIFICATIONS.get(
                event.to_status
            )
            or self.STATUS_NOTIFICATIONS.get(
                canon_status_name
            )
            or {}
        )

        for recipient_type, config in routing.items():

            if not await self._check_preferences(
                event,
                recipient_type,
            ):
                continue

            payload = self._build_payload(
                event,
                recipient_type,
                config,
            )

            notification_type = (
                self._resolve_notification_type(
                    config.get(
                        "template",
                        "",
                    )
                )
            )

            for channel in config.get(
                "channels",
                [],
            ):

                # Production lifecycle email is sent by the versioned graph;
                # direct NotificationRouter callers retain legacy behavior.
                if (
                    channel == "email"
                    and recipient_type == "customer"
                    and event.email_managed_by_communication_graph
                ):
                    continue

                # ------------------------------------------
                # Preference-level channel filtering
                # ------------------------------------------

                if not self._channel_allowed_for_recipient(
                    event,
                    recipient_type,
                    channel,
                ):
                    continue

                self._record_attempted_channel(
                    event,
                    channel,
                )

                # ------------------------------------------
                # Push
                # ------------------------------------------

                if channel == "push":

                    lifecycle_base = (
                        f"notification:"
                        f"{event.tenant_id}:"
                        f"{event.job_id}:"
                        f"{recipient_type}:"
                        f"{channel}:"
                        f"{notification_type}"
                    )

                    await self._publish_notification_lifecycle(
                        event=event,
                        event_type="NOTIFICATION_QUEUED",
                        event_id=f"{lifecycle_base}:queued",
                        recipient_type=recipient_type,
                        channel=channel,
                        notification_type=notification_type,
                    )

                    delivered = await self._send_push(
                        event,
                        recipient_type,
                        payload,
                        config.get(
                            "priority",
                            "normal",
                        ),
                        notification_type,
                    )

                    lifecycle_status = (
                        "NOTIFICATION_SENT"
                        if delivered
                        else "NOTIFICATION_FAILED"
                    )

                    await self._publish_notification_lifecycle(
                        event=event,
                        event_type=lifecycle_status,
                        event_id=f"{lifecycle_base}:"
                        f"{'sent' if delivered else 'failed'}",
                        recipient_type=recipient_type,
                        channel=channel,
                        notification_type=notification_type,
                    )

                # ------------------------------------------
                # SMS
                # ------------------------------------------

                elif channel == "sms":

                    lifecycle_base = (
                        f"notification:"
                        f"{event.tenant_id}:"
                        f"{event.job_id}:"
                        f"{recipient_type}:"
                        f"{channel}:"
                        f"{notification_type}"
                    )

                    await self._publish_notification_lifecycle(
                        event=event,
                        event_type="NOTIFICATION_QUEUED",
                        event_id=f"{lifecycle_base}:queued",
                        recipient_type=recipient_type,
                        channel=channel,
                        notification_type=notification_type,
                    )

                    try:
                        delivered = await self._send_sms(
                            event,
                            recipient_type,
                            payload,
                            notification_type,
                            category=(
                                CommunicationMessageCategory.STANDARD
                            ),
                        )

                    except CommunicationChannelDisabledError:
                        logger.info(
                            "SMS delivery blocked by policy. "
                            "job_id=%s",
                            event.job_id,
                        )
                        delivered = None

                    if delivered is not None:
                        lifecycle_status = (
                            "NOTIFICATION_SENT"
                            if delivered
                            else "NOTIFICATION_FAILED"
                        )

                        await self._publish_notification_lifecycle(
                            event=event,
                            event_type=lifecycle_status,
                            event_id=f"{lifecycle_base}:"
                            f"{'sent' if delivered else 'failed'}",
                            recipient_type=recipient_type,
                            channel=channel,
                            notification_type=notification_type,
                        )

                # ------------------------------------------
                # Email
                # ------------------------------------------

                elif channel == "email":

                    lifecycle_base = (
                        f"notification:"
                        f"{event.tenant_id}:"
                        f"{event.job_id}:"
                        f"{recipient_type}:"
                        f"{channel}:"
                        f"{notification_type}"
                    )

                    await self._publish_notification_lifecycle(
                        event=event,
                        event_type="NOTIFICATION_QUEUED",
                        event_id=f"{lifecycle_base}:queued",
                        recipient_type=recipient_type,
                        channel=channel,
                        notification_type=notification_type,
                    )

                    try:
                        delivered = await self._send_email(
                            event,
                            recipient_type,
                            payload,
                            config,
                            notification_type,
                            category=(
                                CommunicationMessageCategory.STANDARD
                            ),
                        )

                    except CommunicationChannelDisabledError:
                        logger.info(
                            "Email delivery blocked by policy. "
                            "job_id=%s",
                            event.job_id,
                        )
                        delivered = None

                    if delivered is not None:
                        lifecycle_status = (
                            "NOTIFICATION_SENT"
                            if delivered
                            else "NOTIFICATION_FAILED"
                        )

                        await self._publish_notification_lifecycle(
                            event=event,
                            event_type=lifecycle_status,
                            event_id=f"{lifecycle_base}:"
                            f"{'sent' if delivered else 'failed'}",
                            recipient_type=recipient_type,
                            channel=channel,
                            notification_type=notification_type,
                        )

                # ------------------------------------------
                # In-App
                # ------------------------------------------

                elif channel == "in_app":

                    lifecycle_base = (
                        f"notification:"
                        f"{event.tenant_id}:"
                        f"{event.job_id}:"
                        f"{recipient_type}:"
                        f"{channel}:"
                        f"{notification_type}"
                    )

                    await self._publish_notification_lifecycle(
                        event=event,
                        event_type="NOTIFICATION_QUEUED",
                        event_id=f"{lifecycle_base}:queued",
                        recipient_type=recipient_type,
                        channel=channel,
                        notification_type=notification_type,
                    )

                    delivered = await self._send_in_app(
                        event,
                        recipient_type,
                        payload,
                        config.get(
                            "batch",
                            False,
                        ),
                        notification_type,
                    )

                    lifecycle_status = (
                        "NOTIFICATION_SENT"
                        if delivered
                        else "NOTIFICATION_FAILED"
                    )

                    await self._publish_notification_lifecycle(
                        event=event,
                        event_type=lifecycle_status,
                        event_id=f"{lifecycle_base}:"
                        f"{'sent' if delivered else 'failed'}",
                        recipient_type=recipient_type,
                        channel=channel,
                        notification_type=notification_type,
                    )
    async def _publish_notification_lifecycle(
        self,
        *,
        event: JobStatusEvent,
        event_type: str,
        event_id: str,
        recipient_type: str,
        channel: str,
        notification_type: str,
        attempt: int | None = None,
    ) -> None:
        """Publish a notification lifecycle event with Redis deduplication.

        Redis is a best-effort idempotency aid; Kafka remains the event
        transport. Stable event IDs allow consumers to deduplicate events.
        """
        publisher = self.lifecycle_event_publisher

        if publisher is None:
            return

        marker_key = (
            "notification:lifecycle:published:"
            f"{event.tenant_id}:{event_id}"
        )
        claim_key = f"{marker_key}:claim"
        claim_token = str(uuid.uuid4())

        # Claim a short-lived lock atomically to prevent concurrent publishers
        # from publishing the same event at the same time.
        claim_acquired = False
        redis_available = self.redis is not None

        if redis_available:
            try:
                if self.redis.get(marker_key):
                    logger.info(
                        "Skipping duplicate notification lifecycle event. "
                        "event_type=%s event_id=%s job_id=%s",
                        event_type,
                        event_id,
                        event.job_id,
                    )
                    return

                claim_acquired = bool(
                    self.redis.set(
                        claim_key,
                        claim_token,
                        nx=True,
                        ex=60,
                    )
                )

                if not claim_acquired:
                    logger.info(
                        "Skipping notification lifecycle event with an "
                        "active publish claim. event_id=%s job_id=%s",
                        event_id,
                        event.job_id,
                    )
                    return

            except Exception:
                # Redis failure must not block notification delivery.
                logger.warning(
                    "Notification lifecycle idempotency claim failed. "
                    "Continuing without Redis deduplication. event_id=%s",
                    event_id,
                )
                redis_available = False
                claim_acquired = False

        payload = {
            "recipient_type": recipient_type,
            "channel": channel,
            "notification_type": notification_type,
        }

        if attempt is not None:
            payload["attempt"] = attempt

        published = False

        try:
            published = bool(
                await publisher(
                    event_type=event_type,
                    event_id=event_id,
                    job_id=str(event.job_id),
                    tenant_id=str(event.tenant_id),
                    correlation_id=getattr(
                        event,
                        "correlation_id",
                        None,
                    ),
                    payload=payload,
                )
            )

            if not published:
                logger.warning(
                    "Notification lifecycle publisher returned failure. "
                    "event_type=%s event_id=%s job_id=%s",
                    event_type,
                    event_id,
                    event.job_id,
                )
                return

            if redis_available:
                try:
                    self.redis.set(
                        marker_key,
                        "1",
                        ex=7 * 24 * 60 * 60,
                    )
                except Exception:
                    logger.warning(
                        "Notification lifecycle idempotency marker "
                        "could not be stored. event_id=%s job_id=%s",
                        event_id,
                        event.job_id,
                    )

        except Exception:
            logger.exception(
                "Notification lifecycle event publish failed. "
                "event_type=%s event_id=%s job_id=%s",
                event_type,
                event_id,
                event.job_id,
            )

        finally:
            # Release the claim after the publish attempt so a failed publish
            # can be retried. This uses Redis delete; the claim has a TTL as
            # a fallback if Redis is unavailable.
                if claim_acquired:
                    try:
                        self.redis.eval(
                            """
                            if redis.call('GET', KEYS[1]) == ARGV[1] then
                                return redis.call('DEL', KEYS[1])
                            end
                            return 0
                            """,
                            1,
                            claim_key,
                            claim_token,
                        )
                    except Exception:
                        logger.warning(
                            "Notification lifecycle claim could not be released. "
                            "event_id=%s job_id=%s",
                            event_id,
                            event.job_id,
                        )
    # ==================================================
    # Channel Preference Check
    # ==================================================

    def _channel_allowed_for_recipient(
        self,
        event: JobStatusEvent,
        recipient_type: str,
        channel: str,
    ) -> bool:

        if recipient_type != "technician":
            return True

        if not event.technician_id:
            return True

        db = SessionLocal()

        try:
            technician = (
                db.query(
                    Technician
                )
                .filter(
                    Technician.tech_id
                    == event.technician_id
                )
                .first()
            )

            if technician is None:
                return True

            if (
                channel == "sms"
                and technician.sms_opt_out == 1
            ):
                logger.info(
                    "Technician SMS disabled by opt-out. "
                    "job_id=%s",
                    event.job_id,
                )
                return False

            preferences = (
                get_technician_preferences(
                    db,
                    technician.tech_id,
                )
            )

            if channel == "sms":
                return preferences.get(
                    "sms_enabled",
                    True,
                )

            if channel == "push":
                return preferences.get(
                    "push_enabled",
                    True,
                )

            if channel == "in_app":
                return preferences.get(
                    "inapp_enabled",
                    True,
                )

            return True

        except Exception:
            logger.warning(
                "Unable to evaluate technician "
                "channel preference. "
                "job_id=%s channel=%s",
                event.job_id,
                channel,
            )

            # Fail closed for technician delivery.
            return False

        finally:
            db.close()

    # ==================================================
    # Preferences
    # ==================================================

    async def _check_preferences(
        self,
        event: JobStatusEvent,
        recipient_type: str,
    ) -> bool:

        if (
            recipient_type == "technician"
            and event.technician_id
        ):
            db = SessionLocal()

            try:
                technician = (
                    db.query(
                        Technician
                    )
                    .filter(
                        Technician.tech_id
                        == event.technician_id
                    )
                    .first()
                )

                if technician is None:
                    return True

                preferences = (
                    get_technician_preferences(
                        db,
                        technician.tech_id,
                    )
                )

                if (
                    not preferences.get(
                        "sms_enabled",
                        True,
                    )
                    and not preferences.get(
                        "push_enabled",
                        True,
                    )
                    and not preferences.get(
                        "inapp_enabled",
                        True,
                    )
                ):
                    return False

            except Exception:
                logger.warning(
                    "Unable to evaluate technician "
                    "notification preferences."
                )

                return False

            finally:
                db.close()

        return True

    # ==================================================
    # Legacy Routing Name Normalization
    # ==================================================

    @classmethod
    def _resolve_notification_type(
        cls,
        template_name: str,
    ) -> str:

        normalized = (
            str(
                template_name
            )
            .strip()
            .lower()
        )

        return cls.NOTIFICATION_TYPE_ALIASES.get(
            normalized,
            normalized,
        )

    # ==================================================
    # Safe AI Communication Generation
    # ==================================================

    async def _generate_safe_communication(
        self,
        *,
        event: JobStatusEvent,
        recipient_type: str,
        channel: str,
        notification_type: str,
    ):

        try:

            result = await self.communication.generate(
                event=event,
                recipient_type=recipient_type,
                channel=channel,
                notification_type=notification_type,
                locale="en",
            )

        except CommunicationChannelDisabledError:
            raise

        except CommunicationIntegrationError:

            logger.error(
                "Safe communication generation failed. "
                "Notification delivery was skipped. "
                "job_id=%s channel=%s recipient_type=%s",
                event.job_id,
                channel,
                recipient_type,
            )
            return None

        except Exception:

            logger.error(
                "Unexpected safe communication failure. "
                "Notification delivery was skipped. "
                "job_id=%s channel=%s recipient_type=%s",
                event.job_id,
                channel,
                recipient_type,
            )
            return None

        if result is None:
            logger.error(
                "Communication integration returned no result. "
                "job_id=%s",
                event.job_id,
            )

            return None

        expected_channel = (
            channel
            .strip()
            .upper()
            .replace(
                "-",
                "_",
            )
        )

        try:
            actual_channel = (
                result.decision.channel
            )
        except AttributeError:
            logger.error(
                "Communication result has an invalid "
                "decision structure. job_id=%s",
                event.job_id,
            )
            return None

        if actual_channel != expected_channel:
            logger.error(
                "Safe communication returned the wrong "
                "channel. Notification delivery was skipped. "
                "job_id=%s",
                event.job_id,
            )

            return None

        return result

    # ==================================================
    # Payload
    # ==================================================

    def _build_payload(
        self,
        event: JobStatusEvent,
        recipient_type: str,
        config: dict,
    ) -> dict:

        base = {
            "job_id": event.job_id,
            "job_title": event.job_title,
            "job_location": event.job_location,
            "status": event.to_status,
            "timestamp": (
                event.timestamp.isoformat()
                if hasattr(
                    event.timestamp,
                    "isoformat",
                )
                else str(
                    event.timestamp
                )
            ),
            "deep_link": (
                "https://fieldops.io/jobs/"
                f"{quote(str(event.job_id), safe='')}"
            ),
        }

        if recipient_type == "technician":

            base["technician_name"] = (
                event.technician_name
            )

        elif recipient_type == "customer":

            base["customer_name"] = (
                event.customer_name
            )

            if config.get(
                "include_eta"
            ):
                base["eta"] = (
                    event.eta
                    or "calculating..."
                )

            if config.get(
                "include_survey_link"
            ):
                base["survey_link"] = (
                    "https://fieldops.io/survey/"
                    f"{quote(str(event.job_id), safe='')}"
                )

        elif recipient_type == "dispatcher":

            base["actor_name"] = (
                event.actor_id
            )

        return base

    # ==================================================
    # Push Delivery
    # ==================================================

    # ======================================================
# Push Delivery — Existing Adapter
# ======================================================

    async def _send_push(
        self,
        event: JobStatusEvent,
        recipient_type: str,
        payload: dict,
        priority: str,
        notification_type: str,
    ) -> bool:
        """
        Send guardrail-approved push communication.
    
        Technician push is supported because technicians have an
        FCM token in the current backend.
    
        Customer push cannot currently be delivered because the
        backend does not store a customer FCM/device token.
    
        IMPORTANT:
        This method does NOT directly call SMS fallback.
        The main route() method handles the next configured
        channel, such as SMS.
        """
    
        _ = payload
    
        # ------------------------------------------------------
        # Push is currently supported only for technicians
        # ------------------------------------------------------
    
        if recipient_type != "technician":
            logger.info(
                "Push delivery is unavailable for this recipient "
                "type. job_id=%s recipient_type=%s",
                event.job_id,
                recipient_type,
            )
    
            return False
    
        # ------------------------------------------------------
        # Technician ID is required
        # ------------------------------------------------------
    
        if not event.technician_id:
            logger.warning(
                "Technician push skipped because the technician "
                "ID is missing. job_id=%s",
                event.job_id,
            )
    
            return False
    
        db = SessionLocal()
    
        try:
            technician = (
                db.query(
                    Technician
                )
                .filter(
                    Technician.tech_id
                    == event.technician_id
                )
                .first()
            )
    
            # --------------------------------------------------
            # No FCM token
            #
            # DO NOT call _send_sms() here.
            # route() will process the configured SMS channel.
            # --------------------------------------------------
    
            if (
                technician is None
                or not technician.fcm_token
            ):
                logger.warning(
                    "Technician push skipped because no FCM "
                    "token is available. job_id=%s",
                    event.job_id,
                )
    
                return False
    
            # --------------------------------------------------
            # Generate safe AI communication
            # --------------------------------------------------
    
            communication = (
                await self._generate_safe_communication(
                    event=event,
                    recipient_type="technician",
                    channel="push",
                    notification_type=(
                        notification_type
                    ),
                )
            )
    
            if communication is None:
                return False
    
            # --------------------------------------------------
            # Validate push title
            # --------------------------------------------------
    
            title = (
                communication
                .decision
                .output
                .title
            )
    
            if not title:
                logger.error(
                    "Safe push communication did not contain "
                    "a title. Delivery was skipped. job_id=%s",
                    event.job_id,
                )
    
                return False
    
            if len(title) > 50:
                logger.error(
                    "Final push title exceeds the transport "
                    "limit. Delivery was skipped. job_id=%s",
                    event.job_id,
                )
    
                return False
    
            # --------------------------------------------------
            # Send push through existing FCM service
            # --------------------------------------------------
    
            delivery_result = await self.fcm(
                db,
                event.job_id,
                event.tenant_id,
                event.job_title,
                event.job_location,
                [
                    event.technician_id,
                ],
                correlation_id_ctx.get(),
                notification_title=title,
                notification_body=(
                    communication
                    .decision
                    .output
                    .body
                ),
                notification_type=(
                    notification_type
                ),
                priority=priority,
            )
    
            if isinstance(
                delivery_result,
                dict,
            ):
                return (
                    int(
                        delivery_result.get(
                            "sent",
                            0,
                        )
                    )
                    > 0
                )
    
            return bool(
                delivery_result
            )
    
        except Exception:
            logger.error(
                "Technician push delivery failed. "
                "job_id=%s",
                event.job_id,
            )
    
            return False
    
        finally:
            db.close()
    
        # ==================================================
        # SMS Delivery
        # ==================================================
    
    async def _send_sms(
        self,
        event: JobStatusEvent,
        recipient_type: str,
        payload: dict,
        notification_type: str,
        category: CommunicationMessageCategory = (
            CommunicationMessageCategory.STANDARD
        ),
    ) -> bool:
        _ = payload

        if recipient_type not in {
            "customer",
            "technician",
        }:
            return False

        # ------------------------------------------------
        # Technician SMS
        # ------------------------------------------------

        if recipient_type == "technician":
            if not event.technician_id:
                logger.warning(
                    "Technician SMS skipped because technician "
                    "ID is missing. job_id=%s",
                    event.job_id,
                )
                return False

            # Generate approved communication only after the
            # technician recipient has been validated.
            communication = (
                await self._generate_safe_communication(
                    event=event,
                    recipient_type=recipient_type,
                    channel="sms",
                    notification_type=notification_type,
                )
            )

            if communication is None:
                return False

            output = communication.decision.output
            message_body = output.text

            if not isinstance(message_body, str):
                logger.error(
                    "SMS communication body is invalid. "
                    "job_id=%s",
                    event.job_id,
                )
                return False

            # ------------------------------------------------
            # SMS transport limit
            # ------------------------------------------------

            if len(message_body) > 160:
                logger.error(
                    "Final SMS content exceeds the transport "
                    "limit. Delivery was skipped. job_id=%s",
                    event.job_id,
                )
                return False

            db = SessionLocal()

            async def publish_sms_retry(*, attempt, delivery_id):
                await self._publish_notification_lifecycle(
                    event=event,
                    event_type="NOTIFICATION_RETRIED",
                    event_id=(
                        f"notification:"
                        f"{event.tenant_id}:"
                        f"{event.job_id}:"
                        f"technician:sms:"
                        f"{notification_type}:"
                        f"retry:{attempt}"
                    ),
                    recipient_type=recipient_type,
                    channel="sms",
                    notification_type=notification_type,
                    attempt=attempt,
                )

            try:
                delivery_result = await self.sms(
                    db,
                    event.job_id,
                    event.job_title,
                    event.job_location,
                    "HIGH",
                    [event.technician_id],
                    correlation_id_ctx.get(),
                    effective_message=message_body,
                    category=category,
                    on_retry=publish_sms_retry,
                )

                if isinstance(delivery_result, dict):
                    return (
                        int(delivery_result.get("sent", 0)) > 0
                    )

                return bool(delivery_result)

            except Exception:
                logger.error(
                    "Technician SMS delivery failed. "
                    "job_id=%s",
                    event.job_id,
                )
                return False

            finally:
                db.close()

        # ------------------------------------------------
        # Customer SMS
        # ------------------------------------------------

        # Normalize before checking. Whitespace-only values such as
        # "   " must be treated as a missing phone number.
        customer_phone = (event.customer_phone or "").strip()

        if not customer_phone:
            logger.warning(
                "Customer SMS skipped because the phone "
                "number is missing. job_id=%s",
                event.job_id,
            )
            return False

        # ------------------------------------------------
        # Generate safe communication
        # ------------------------------------------------

        communication = await self._generate_safe_communication(
            event=event,
            recipient_type=recipient_type,
            channel="sms",
            notification_type=notification_type,
        )

        # ------------------------------------------------
        # Customer delivery policy
        # ------------------------------------------------

        decision = self._evaluate_customer_delivery_policy(
            event=event,
            channel="SMS",
            category=category,
        )

        if not decision.allowed:
            logger.warning(
                "Customer SMS delivery blocked by policy. "
                "reason_code=%s",
                decision.final_reason_code,
            )

            raise CommunicationChannelDisabledError(
                (
                    "SMS delivery blocked: "
                    f"{decision.final_reason_code}"
                ),
                decision,
            )

        if communication is None:
            # Preserve the existing safe-generation failure behavior
            # for normal notifications. Emergency delivery may use
            # the existing minimal fallback message when policy allows.
            if category != CommunicationMessageCategory.EMERGENCY:
                return False

            message_body = "FieldOps notification update."
        else:
            output = communication.decision.output
            message_body = output.text


        if not isinstance(message_body, str):
            logger.error(
                "SMS communication body is invalid. "
                "job_id=%s",
                event.job_id,
            )
            return False

        # ------------------------------------------------
        # SMS transport limit
        # ------------------------------------------------

        if len(message_body) > 160:
            logger.error(
                "Final SMS content exceeds the transport "
                "limit. Delivery was skipped. job_id=%s",
                event.job_id,
            )
            return False

        # ------------------------------------------------
        # Twilio
        # ------------------------------------------------

        from .twilio_sms import (
            TWILIO_ACCOUNT_SID,
            dispatch_twilio_message,
        )

        local_mock_mode = (
            not TWILIO_ACCOUNT_SID
            or "dummy" in TWILIO_ACCOUNT_SID.lower()
            or "mock" in TWILIO_ACCOUNT_SID.lower()
        )

        if local_mock_mode:
            logger.info(
                "Customer SMS delivery simulated. "
                "job_id=%s",
                event.job_id,
            )
            return True

        try:
            loop = asyncio.get_running_loop()

            await loop.run_in_executor(
                None,
                lambda: dispatch_twilio_message(
                    body=message_body,
                    to_phone=customer_phone,
                ),
            )

            logger.info(
                "Customer SMS delivery completed. "
                "job_id=%s",
                event.job_id,
            )

            return True

        except Exception:
            logger.error(
                "Customer SMS delivery failed. "
                "job_id=%s",
                event.job_id,
            )
            return False


    async def _send_email(
        self,
        event: JobStatusEvent,
        recipient_type: str,
        payload: dict,
        config: dict,
        notification_type: str,
        category: CommunicationMessageCategory = (
            CommunicationMessageCategory.STANDARD
        ),
    ) -> bool:

        _ = payload

        if recipient_type != "customer":
            return False

        if not event.customer_email:

            logger.warning(
                "Customer email delivery skipped because "
                "email address is missing. job_id=%s",
                event.job_id,
            )
            return False

        # ------------------------------------------------------
        # Customer delivery policy MUST be checked first
        # ------------------------------------------------------

        decision = self._evaluate_customer_delivery_policy(
            event=event,
            channel="EMAIL",
            category=category,
        )

        if not decision.allowed:
            logger.warning(
                "Customer email delivery blocked by policy. "
                "reason_code=%s channel=EMAIL",
                decision.final_reason_code,
            )

            raise CommunicationChannelDisabledError(
                (
                    "Email delivery blocked: "
                    f"{decision.final_reason_code}"
                ),
                decision,
            )

        # ------------------------------------------------------
        # Generate safe content only after policy allows delivery
        # ------------------------------------------------------

        communication = (
            await self._generate_safe_communication(
                event=event,
                recipient_type="customer",
                channel="email",
                notification_type=notification_type,
            )
        )

        if communication is None:
            return False

        output = communication.decision.output

        subject = output.subject

        text_body = output.text_body

        body_html = (
            output.html_body
            or text_body
        )

        # ------------------------------------------------
        # Subject validation
        # ------------------------------------------------

        if not isinstance(
            subject,
            str,
        ):

            logger.error(
                "Final email subject is not a string. "
                "job_id=%s",
                event.job_id,
            )

            return False

        if not subject.strip():

            logger.error(
                "Final email subject is empty. "
                "job_id=%s",
                event.job_id,
            )

            return False

        if len(subject) > 78:

            logger.error(
                "Final email subject exceeds the transport "
                "limit. job_id=%s",
                event.job_id,
            )
            return False

        # ------------------------------------------------
        # Survey link
        # ------------------------------------------------

        if config.get(
            "include_survey_link"
        ):

            safe_job_id = quote(
                str(
                    event.job_id
                ),
                safe="",
            )

            survey_url = (
                "https://fieldops.io/survey/"
                f"{safe_job_id}"
            )

            body_html += (
                "<p>"
                "Please complete our service survey: "
                f'<a href="'
                f'{escape(survey_url, quote=True)}'
                f'">Take Survey</a>'
                "</p>"
            )

        # ------------------------------------------------
        # Delivery policy
        # ------------------------------------------------

        # ------------------------------------------------
        # Send
        # ------------------------------------------------

        delivered = await self.email.send_email(
            event.customer_email,
            subject,
            body_html,
        )

        if delivered:

            logger.info(
                "Customer email delivery completed. "
                "job_id=%s",
                event.job_id,
            )

        return bool(
            delivered
        )

    # ==================================================
    # Dispatcher In-App Delivery
    # ==================================================

    async def _send_in_app(
        self,
        event: JobStatusEvent,
        recipient_type: str,
        payload: dict,
        batch: bool,
        notification_type: str,
    ) -> bool:

        if recipient_type != "dispatcher":
            return False

        communication = await self._generate_safe_communication(
                event=event,
                recipient_type="dispatcher",
                channel="in_app",
                notification_type=notification_type,
            )

        output = (
            communication.decision.output
            if communication is not None
            else None
        )
        fallback = {
            "ACCEPTED": ("Technician accepted", "The assigned technician accepted the service request."),
            "EN_ROUTE": ("Technician en route", "The technician is travelling to the customer's location."),
            "ON_SITE": ("Technician arrived", "The technician arrived at the service location."),
            "IN_PROGRESS": ("Work started", "Service work has started."),
            "REJECTED_BY_TECHNICIAN": (
                "Technician rejected the job",
                "The assigned technician rejected the service request. Dispatch needs to assign another technician.",
            ),
            "COMPLETED": ("Job completed", "The technician finished the service work."),
            "CANCELLED": ("Job cancelled", "The service request was cancelled."),
            "ASSIGNED": ("Technician assigned", "A technician was assigned to the service request."),
        }
        fallback_title, fallback_body = fallback.get(
            str(event.to_status).upper(),
            ("Dispatch update", f"Service request status changed to {event.to_status.lower().replace('_', ' ')}."),
        )
        if str(event.to_status).upper() == "REJECTED_BY_TECHNICIAN":
            fallback_title = f"Technician rejected Job #{event.job_id}"
            if event.reason:
                fallback_body += f" Reason: {event.reason}"

        notification_body = (
            output.body
            if output and output.body
            else fallback_body
        )
        technician_name = (event.technician_name or "").strip()
        if (
            technician_name
            and technician_name.casefold()
            not in notification_body.casefold()
        ):
            notification_body = (
                f"{notification_body} Technician: {technician_name}."
            )

        safe_payload = {
            **payload,
            "notification_type": (
                notification_type
            ),
            "title": (output.title if output and output.title else fallback_title),
            "message": notification_body,
            "channel": "IN_APP",
        }
        event_key = (
            f"job_{event.job_id}:{str(event.to_status).upper()}:{event.event_version}"
            if event.event_version
            else f"job_{event.job_id}:{str(event.from_status).upper()}:{str(event.to_status).upper()}"
        )
        db = SessionLocal()
        created = []
        try:
            recipients = db.query(User).filter(
                User.tenant_id == event.tenant_id,
                User.is_active.is_(True),
                User.role.in_(["dispatcher", "super_admin"]),
            ).all()
            for recipient in recipients:
                existing = db.query(InAppNotification).filter(
                    InAppNotification.tenant_id == event.tenant_id,
                    InAppNotification.recipient_role == "dispatcher",
                    InAppNotification.recipient_id == str(recipient.id),
                    InAppNotification.group_key == event_key,
                ).first()
                if existing:
                    continue
                notification = InAppNotification(
                    id=str(uuid.uuid4()),
                    tenant_id=event.tenant_id,
                    recipient_id=str(recipient.id),
                    recipient_role="dispatcher",
                    group_key=event_key,
                    job_id=str(event.job_id),
                    type=notification_type or "dispatch_update",
                    title=safe_payload["title"],
                    body=safe_payload["message"],
                    status="UNREAD",
                    priority=str(safe_payload.get("priority", "NORMAL")).upper(),
                    event_version=event.event_version or 0,
                    notification_metadata={"job_id": str(event.job_id), "status": str(event.to_status).upper()},
                )
                db.add(notification)
                created.append(notification)
            db.commit()
            for notification in created:
                db.refresh(notification)
        except Exception:
            db.rollback()
            logger.exception("Dispatcher notification persistence failed. tenant_id=%s", event.tenant_id)
            return False
        finally:
            db.close()

        try:
            for notification in created:
                await self.ws.broadcast(
                    f"tenant:{event.tenant_id}:dispatchers",
                    {"type": "new_notification", "payload": {
                        "id": notification.id,
                        "tenant_id": notification.tenant_id,
                        "job_id": notification.job_id,
                        "type": notification.type,
                        "title": notification.title,
                        "body": notification.body,
                        "status": notification.status,
                        "created_at": notification.created_at.isoformat() if notification.created_at else None,
                        "event_version": notification.event_version,
                        "group_key": notification.group_key,
                    }},
                )
            return True
        except Exception:
            logger.exception("Dispatcher notification broadcast failed. tenant_id=%s", event.tenant_id)
            return False

    # ==================================================
    # Helpers
    # ==================================================

    # ======================================================
# Audit Helper
# ======================================================

    
    # ==================================================
    # Audit / Attempted Channel
    # ==================================================

    @staticmethod
    def _record_attempted_channel(
        event: JobStatusEvent,
        channel: str,
    ) -> None:

        if (
            channel
            not in event.notification_channels
        ):
            event.notification_channels.append(
                channel
            )

async def route_escalation(
    self,
    manager_id: str,
    manager_email: str | None,
    manager_phone: str | None,
    payload: dict,
) -> dict:
    """
    Route a sentiment escalation to the assigned manager.
    """

    results = {
        "sms": False,
        "email": False,
        "push": False,
        "dashboard": False,
    }

    # Dashboard notification through existing WebSocket manager.
    if self.ws:
        try:
            await self.ws.broadcast(
                f"tenant:{payload.get('tenant_id')}:managers",
                {
                    "type": "sentiment_escalation",
                    "payload": payload,
                },
            )
            results["dashboard"] = True
        except Exception:
            logger.exception(
                "Failed to send escalation dashboard notification"
            )

    # Email delivery uses the configured SMTP relay.
    if manager_email:
        try:
            results["email"] = bool(
                await self.email.send_email(
                    manager_email,
                    "Negative Sentiment Escalation",
                    (
                        f"<h3>Customer Escalation</h3>"
                        f"<p>Job ID: {payload.get('job_id')}</p>"
                        f"<p>Customer: {payload.get('customer_name')}</p>"
                        f"<p>Sentiment: {payload.get('sentiment_score')}</p>"
                        f"<p>{payload.get('reply_text')}</p>"
                    ),
                )
            )
        except Exception:
            logger.exception(
                "Failed to send escalation email"
            )

    return results
