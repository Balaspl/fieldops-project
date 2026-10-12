import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ReDispatchTriggerService:
    RULES = {
        "P1": {
            "triggers": ["rejection", "timeout", "offline"],
            "pre_alert_seconds": 30,
            "max_attempts": 3,
        },
        "P2": {
            "triggers": ["rejection", "timeout", "offline"],
            "pre_alert_seconds": 30,
            "max_attempts": 4,
        },
        "P3": {
            "triggers": ["rejection", "timeout"],
            "pre_alert_seconds": 60,
            "max_attempts": 5,
        },
        "P4": {
            "triggers": ["rejection", "timeout"],
            "pre_alert_seconds": 60,
            "max_attempts": 5,
        },
        "P5": {
            "triggers": ["manual_only"],
            "pre_alert_seconds": 0,
            "max_attempts": 2,
        },
    }

    @classmethod
    def detect_trigger(
        cls,
        job,
        tech,
        timer_exists: bool,
        timer_ttl: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Detects if a job should trigger an auto-redispatch or a pre-alert.
        Returns dict with "type": "trigger"|"pre_alert" and "reason", "urgency"
        """
        if not job or job.status.upper() != "ASSIGNED":
            return None

        priority = job.priority or "P4"
        rules = cls.RULES.get(priority, cls.RULES["P4"])

        # P5 is manual only
        if "manual_only" in rules["triggers"]:
            return None

        now = datetime.now(timezone.utc)

        # 1. Check Technician Offline (if rules allow)
        if "offline" in rules["triggers"]:
            if tech and tech.technician_status == "OFFLINE":
                return {
                    "type": "trigger",
                    "reason": "tech_offline",
                    "urgency": "immediate",
                }

        # 2. Check SLA Proximity
        if hasattr(job, "sla_deadline") and job.sla_deadline:
            if job.sla_deadline.tzinfo is None:
                sla = job.sla_deadline.replace(tzinfo=timezone.utc)
            else:
                sla = job.sla_deadline.astimezone(timezone.utc)

            sla_remaining = sla - now

            if sla_remaining < timedelta(minutes=30) and priority in ["P1", "P2"]:
                return {
                    "type": "trigger",
                    "reason": "sla_risk",
                    "urgency": "high",
                }

        # 3. Check Timeout
        if "timeout" in rules["triggers"]:
            if timer_exists:
                if 0 < timer_ttl <= rules["pre_alert_seconds"]:
                    return {
                        "type": "pre_alert",
                        "reason": "imminent_timeout",
                    }

                return None

            # Redis timer is missing.
            # Use the actual assignment time as the fallback timeout source.
            assigned_at = getattr(job, "assigned_at", None)

            if assigned_at is None:
                logger.warning(
                    "No assigned_at timestamp for assigned job=%s; "
                    "cannot determine acceptance timeout.",
                    job.id,
                )
                return None

            if assigned_at.tzinfo is None:
                assigned_at = assigned_at.replace(tzinfo=timezone.utc)
            else:
                assigned_at = assigned_at.astimezone(timezone.utc)

            # Technician has 5 minutes to accept/reject.
            acceptance_timeout_seconds = 5 * 60

            elapsed_seconds = (now - assigned_at).total_seconds()

            logger.debug(
                "Acceptance timeout check | job=%s | elapsed=%.1fs | "
                "timeout=%ss | timer_exists=%s",
                job.id,
                elapsed_seconds,
                acceptance_timeout_seconds,
                timer_exists,
            )

            if elapsed_seconds >= acceptance_timeout_seconds:
                return {
                    "type": "trigger",
                    "reason": "timeout",
                    "urgency": "high",
                }

            return None