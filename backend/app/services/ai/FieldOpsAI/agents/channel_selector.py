from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from enum import Enum
from typing import Any, Callable, Mapping, Optional

import pytz


class ChannelPriority(str, Enum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    FALLBACK = "FALLBACK"


SUPPORTED_CHANNELS = ("SMS", "EMAIL", "PUSH", "PORTAL")


@dataclass(frozen=True)
class ChannelSelection:
    channel: Optional[str]
    priority: Optional[ChannelPriority]
    urgency_score: int
    reason: str
    attempted_channels: tuple[str, ...] = ()


class ChannelSelector:
    """
    Select the best communication channel based on:

    - customer preference
    - message urgency
    - quiet hours
    - channel opt-out
    - channel availability

    This class only decides the channel.
    Actual message delivery remains with the existing
    CommunicationAgent / NotificationService.
    """

    QUIET_HOURS_START = time(22, 0)
    QUIET_HOURS_END = time(7, 0)

    def __init__(
        self,
        preference_service: Any = None,
        configuration_service: Any = None,
        health_checker: Optional[Callable[[str], bool]] = None,
    ) -> None:
        self.preference_service = preference_service
        self.configuration_service = configuration_service
        self.health_checker = health_checker

    # ------------------------------------------------------------------
    # Urgency
    # ------------------------------------------------------------------

    def score_urgency(self, message_context: Mapping[str, Any]) -> int:
        """
        Return urgency score from 1 to 5.

        5 = critical / immediate
        4 = urgent
        3 = normal status update
        2 = low priority
        1 = informational
        """

        explicit_score = message_context.get("urgency_score")

        if explicit_score is not None:
            try:
                score = int(explicit_score)
            except (TypeError, ValueError):
                score = 3

            return max(1, min(5, score))

        notification_type = str(
            message_context.get("notification_type", "")
        ).strip().upper()

        if notification_type in {
            "ETA",
            "ETA_ALERT",
            "EMERGENCY",
            "CRITICAL",
        }:
            return 5

        if notification_type in {
            "URGENT",
            "JOB_DELAY",
            "DELAY",
        }:
            return 4

        if notification_type in {
            "STATUS_UPDATE",
            "JOB_STATUS",
            "ENROUTE",
            "ONSITE",
            "COMPLETED",
        }:
            return 3

        if notification_type in {
            "REMINDER",
            "FOLLOW_UP",
        }:
            return 2

        return 1

    # ------------------------------------------------------------------
    # Quiet hours
    # ------------------------------------------------------------------

    def is_quiet_hours(
        self,
        current_time: datetime,
        timezone_name: str,
    ) -> bool:
        """
        Check whether the supplied timezone-local time is inside
        the configured quiet-hours window.

        Quiet hours:
            10:00 PM -> 7:00 AM
        """

        if current_time.tzinfo is None:
            raise ValueError("current_time must be timezone-aware")

        try:
            timezone = pytz.timezone(timezone_name)
        except pytz.UnknownTimeZoneError as exc:
            raise ValueError(
                f"Unknown timezone: {timezone_name}"
            ) from exc

        local_time = current_time.astimezone(timezone).time()

        return (
            local_time >= self.QUIET_HOURS_START
            or local_time < self.QUIET_HOURS_END
        )

    # ------------------------------------------------------------------
    # Channel preference
    # ------------------------------------------------------------------

    def _preferred_channel(
        self,
        customer_prefs: Mapping[str, Any],
    ) -> Optional[str]:
        preferred = customer_prefs.get("preferred_channel")

        if preferred is None:
            preferred = customer_prefs.get("channel")

        if not isinstance(preferred, str):
            return None

        preferred = preferred.strip().upper()

        if preferred == "IN_APP":
            preferred = "PORTAL"

        if preferred not in SUPPORTED_CHANNELS:
            return None

        return preferred

    # ------------------------------------------------------------------
    # Opt-out
    # ------------------------------------------------------------------

    def _channel_allowed(
        self,
        channel: str,
        customer_prefs: Mapping[str, Any],
    ) -> bool:
        """
        Evaluate channel opt-out information.

        Existing CustomerPreferenceService can be injected for the
        authoritative preference check. Mapping fallback is provided
        for isolated unit testing.
        """

        if self.preference_service is not None:
            tenant_id = customer_prefs.get("tenant_id")
            customer_id = customer_prefs.get("customer_id")

            if tenant_id is not None and customer_id is not None:
                decision = self.preference_service.evaluate_channel(
                    tenant_id=tenant_id,
                    customer_id=customer_id,
                    channel=channel,
                )
                return bool(decision.allowed)

        field_map = {
            "SMS": "sms_enabled",
            "EMAIL": "email_enabled",
            "PUSH": "push_enabled",
            "PORTAL": "portal_enabled",
        }

        field = field_map[channel]

        value = customer_prefs.get(field, True)

        return bool(value)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def _channel_healthy(self, channel: str) -> bool:
        """
        Check channel availability.

        Health is injectable because the existing project has a
        provider-health monitor, while Twilio/SMTP are currently
        delivered through the notification service.
        """

        if self.health_checker is None:
            return True

        try:
            return bool(self.health_checker(channel))
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def _channel_configured(
        self,
        channel: str,
        urgency_score: int,
    ) -> bool:
        """
        Reuse the existing communication configuration service
        for channels it currently supports.

        PUSH and PORTAL are not passed into that service because
        its current contract supports SMS and EMAIL only.
        """

        if self.configuration_service is None:
            return True

        if channel not in {"SMS", "EMAIL"}:
            return True

        try:
            from app.services.ai.FieldOpsAI.schemas.communication_configuration import (
                CommunicationMessageCategory,
            )

            category = (
                CommunicationMessageCategory.EMERGENCY
                if urgency_score >= 5
                else CommunicationMessageCategory.STANDARD
            )

            decision = self.configuration_service.evaluate_delivery(
                channel=channel,
                category=category,
            )

            return bool(decision.allowed)

        except Exception:
            return False

    # ------------------------------------------------------------------
    # Candidate ordering
    # ------------------------------------------------------------------

    def _candidate_channels(
        self,
        preferred_channel: Optional[str],
        urgency_score: int,
    ) -> list[str]:
        """
        Build the priority chain.

        Preferred channel is always considered first when valid.

        Urgent messages prefer SMS.
        Normal status updates prefer PUSH/EMAIL.
        """

        if urgency_score >= 4:
            default_order = ["SMS", "PUSH", "EMAIL", "PORTAL"]
        else:
            default_order = ["PUSH", "EMAIL", "SMS", "PORTAL"]

        if preferred_channel is not None:
            default_order.remove(preferred_channel)
            return [preferred_channel, *default_order]

        return default_order

    # ------------------------------------------------------------------
    # Main selection
    # ------------------------------------------------------------------

    def select_channel(
        self,
        message_context: Mapping[str, Any],
        customer_prefs: Mapping[str, Any],
    ) -> ChannelSelection:
        """
        Select the best available communication channel.

        The selector evaluates at most three candidates, representing
        PRIMARY -> SECONDARY -> FALLBACK.
        """

        urgency_score = self.score_urgency(message_context)

        preferred_channel = self._preferred_channel(
            customer_prefs
        )

        timezone_name = (
            message_context.get("timezone")
            or customer_prefs.get("timezone")
            or "UTC"
        )

        current_time = message_context.get("current_time")

        if current_time is None:
            current_time = datetime.now(pytz.UTC)

        if not isinstance(current_time, datetime):
            raise ValueError(
                "current_time must be a datetime"
            )

        quiet_hours = self.is_quiet_hours(
            current_time=current_time,
            timezone_name=timezone_name,
        )

        candidates = self._candidate_channels(
            preferred_channel=preferred_channel,
            urgency_score=urgency_score,
        )

        attempted: list[str] = []

        for channel in candidates[:3]:
            attempted.append(channel)

            # SMS is deferred during quiet hours unless the message
            # is urgent enough to bypass quiet hours.
            if (
                channel == "SMS"
                and quiet_hours
                and urgency_score < 5
            ):
                continue

            if not self._channel_allowed(
                channel,
                customer_prefs,
            ):
                continue

            if not self._channel_healthy(channel):
                continue

            if not self._channel_configured(
                channel,
                urgency_score,
            ):
                continue

            if len(attempted) == 1:
                priority = ChannelPriority.PRIMARY
            elif len(attempted) == 2:
                priority = ChannelPriority.SECONDARY
            else:
                priority = ChannelPriority.FALLBACK

            return ChannelSelection(
                channel=channel,
                priority=priority,
                urgency_score=urgency_score,
                reason=(
                    f"Selected {channel} as "
                    f"{priority.value.lower()} channel."
                ),
                attempted_channels=tuple(attempted),
            )

        return ChannelSelection(
            channel=None,
            priority=None,
            urgency_score=urgency_score,
            reason="No eligible communication channel available.",
            attempted_channels=tuple(attempted),
        )
