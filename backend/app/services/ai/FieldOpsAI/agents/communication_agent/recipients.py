"""Decide who gets a notification and on which channels."""

import logging
from dataclasses import dataclass, field

from sqlalchemy import func
from sqlalchemy.orm import Session

from ......models_legacy import (
    CommunicationChannelConfiguration,
    CustomerProfile,
    Job,
    Technician,
)
from app.auth.rbac import UserRole
from app.models.user import User
from .events import EMAIL, IN, RECIPIENT_RULES, SMS, JobEvent

logger = logging.getLogger(__name__)


@dataclass
class Recipient:
    role: str  # customer | technician | org_admin | super_admin
    id: str
    tenant_id: str
    channels: list[str] = field(default_factory=list)
    phone: str | None = None
    email: str | None = None
    name: str | None = None


def _tenant_channel_on(
    db: Session,
    tenant_id: str,
    channel: str,
) -> bool:
    """Check the channel configuration for the recipient's organization."""
    row = (
        db.query(CommunicationChannelConfiguration)
        .filter(
            CommunicationChannelConfiguration.tenant_id == tenant_id,
            func.lower(CommunicationChannelConfiguration.channel)
            == channel.lower(),
        )
        .first()
    )

    # No configuration means enabled; when configured, only ENABLED is allowed.
    return row is None or str(row.state).upper() == "ENABLED"


def _customer(
    db: Session,
    job: Job,
    wanted: list[str],
) -> list[Recipient]:
    """Resolve the customer using the customer's organization."""
    customer_tenant_id = (
        getattr(job, "customer_tenant_id", None)
        or job.tenant_id
    )

    profile = None
    if job.customer_id:
        profile = (
            db.query(CustomerProfile)
            .filter_by(
                tenant_id=customer_tenant_id,
                customer_id=job.customer_id,
            )
            .first()
        )

    registered_user = None
    if job.customer_id:
        registered_user = (
            db.query(User)
            .filter(
                User.id == str(job.customer_id),
                User.tenant_id == str(customer_tenant_id),
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
            .first()
        )
    customer_email = (
        registered_user.email
        if registered_user
        else getattr(job, "customer_email", None)
        if not job.customer_id
        else None
    )

    allowed = {
        IN: (
            getattr(profile, "portal_enabled", True)
            if profile
            else True
        ),
        SMS: (
            getattr(profile, "sms_enabled", True)
            if profile
            else True
        ) and bool(job.contact_number),
        EMAIL: (
            getattr(profile, "email_enabled", True)
            if profile
            else True
        ) and bool(customer_email),
    }

    channels = [channel for channel in wanted if allowed.get(channel, False)]

    return [
        Recipient(
            role="customer",
            id=str(job.customer_id or f"guest-{job.id}"),
            tenant_id=str(customer_tenant_id),
            channels=channels,
            phone=job.contact_number,
            email=customer_email,
            name=job.customer_name,
        )
    ]


def _technician(
    technician: Technician | None,
    wanted: list[str],
) -> list[Recipient]:
    """Resolve the assigned technician in their own organization."""
    if not technician or not technician.tech_id:
        return []

    technician_tenant_id = getattr(technician, "tenant_id", None)
    if not technician_tenant_id:
        logger.warning(
            "Skipping technician notification because tenant_id is missing "
            "(technician_id=%s)",
            getattr(technician, "technician_id", None),
        )
        return []

    preferences = getattr(technician, "notification_preferences", None) or {}

    allowed = {
        IN: preferences.get("inapp_enabled", True),
        SMS: (
            preferences.get("sms_enabled", True)
            and not getattr(technician, "sms_opt_out", False)
            and bool(getattr(technician, "phone_number", None))
        ),
        EMAIL: False,  # Technician model has no email field in this workflow.
    }

    return [
        Recipient(
            role="technician",
            id=str(technician.tech_id),
            tenant_id=str(technician_tenant_id),
            channels=[channel for channel in wanted if allowed.get(channel, False)],
            phone=getattr(technician, "phone_number", None),
            name=getattr(technician, "technician_name", None),
        )
    ]


def _admins(
    db: Session,
    tenant_id: str | None,
    role: str,
    wanted: list[str],
) -> list[Recipient]:
    """Resolve organization admins or platform HEAD users from the User table."""
    if role == "org_admin":
        if not tenant_id:
            return []

        users = (
            db.query(User)
            .filter(
                User.tenant_id == tenant_id,
                User.role.in_(
                    [
                        UserRole.SUPER_ADMIN.value,
                        UserRole.DISPATCHER.value,
                    ]
                ),
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
            .all()
        )

        return [
            Recipient(
                role="org_admin",
                id=str(user.id),
                tenant_id=str(user.tenant_id),
                channels=list(wanted),
                phone=getattr(user, "phone_number", None),
                email=getattr(user, "email", None),
                name=f"{user.first_name} {user.last_name}".strip(),
            )
            for user in users
        ]

    if role == "super_admin":
        # In this application's RBAC, HEAD is the platform-level owner.
        platform_tenant_id = "__platform__"
        users = (
            db.query(User)
            .filter(
                User.tenant_id == platform_tenant_id,
                User.role == UserRole.HEAD.value,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
            .all()
        )

        return [
            Recipient(
                role="super_admin",
                id=str(user.id),
                tenant_id=str(user.tenant_id),
                channels=list(wanted),
                phone=getattr(user, "phone_number", None),
                email=getattr(user, "email", None),
                name=f"{user.first_name} {user.last_name}".strip(),
            )
            for user in users
        ]

    logger.warning("Unknown admin recipient role: %s", role)
    return []


def resolve_recipients(
    db: Session,
    job: Job,
    event: JobEvent,
    technician: Technician | None = None,
) -> list[Recipient]:
    """Resolve recipients and enforce each recipient's tenant channel settings."""
    recipients: list[Recipient] = []

    for role, wanted in RECIPIENT_RULES.get(event, {}).items():
        if role == "customer":
            customer_wanted = list(wanted)
            if event in {JobEvent.JOB_CREATED, JobEvent.INVOICE_READY}:
                # These transactional customer emails are delivered by the
                # independent database outbox; retain AI and in-app notices.
                customer_wanted = [channel for channel in customer_wanted if channel != EMAIL]
            recipients.extend(_customer(db, job, customer_wanted))

        elif role == "technician":
            recipients.extend(_technician(technician, wanted))

        elif role == "org_admin":
            recipients.extend(
                _admins(db, str(job.tenant_id), "org_admin", wanted)
            )

        elif role == "technician_org_admin":
            # Notify the technician's organization only when it differs from
            # the organization that owns the job.
            if (
                technician
                and technician.tenant_id
                and str(technician.tenant_id) != str(job.tenant_id)
            ):
                recipients.extend(
                    _admins(
                        db,
                        str(technician.tenant_id),
                        "org_admin",
                        wanted,
                    )
                )

        elif role == "super_admin":
            # RECIPIENT_RULES uses this key for platform-level HEAD recipients.
            recipients.extend(_admins(db, None, "super_admin", wanted))

    # Apply each recipient's own tenant channel configuration. In-app delivery
    # remains enabled by this filter; SMS/email obey that tenant's settings.
    seen: set[tuple[str, str, str]] = set()
    result: list[Recipient] = []

    for recipient in recipients:
        if not recipient.tenant_id:
            logger.warning(
                "Skipping notification recipient without tenant_id "
                "(role=%s, recipient_id=%s)",
                recipient.role,
                recipient.id,
            )
            continue

        had_email_channel = EMAIL in recipient.channels
        recipient.channels = [
            channel
            for channel in recipient.channels
            if channel == IN
            or _tenant_channel_on(db, recipient.tenant_id, channel)
        ]
        if (
            EMAIL in wanted
            and event not in {JobEvent.JOB_CREATED, JobEvent.INVOICE_READY}
            and EMAIL not in recipient.channels
        ):
            reason = (
                "tenant_email_channel_disabled"
                if had_email_channel
                else "recipient_email_missing_or_preference_disabled"
            )
            logger.info(
                "Email notification unavailable for recipient",
                extra={"job_id": str(job.id), "event_type": event.value,
                       "recipient_role": recipient.role, "reason": reason},
            )

        # Include tenant so identical IDs in different organizations do not
        # accidentally collapse into one recipient.
        key = (recipient.tenant_id, recipient.role, recipient.id)
        if recipient.channels and key not in seen:
            seen.add(key)
            result.append(recipient)

    return result
