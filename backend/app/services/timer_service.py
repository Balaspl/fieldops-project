import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class TimerService:
    """
    Technician assignment acceptance timer.

    Redis is used for:
      - fast timer lookup
      - countdown/TTL
      - warning processing

    The database assignment timestamp should remain the
    authoritative source for whether an assignment is actually expired.
    """

    ACCEPTANCE_DURATION_SECONDS = 600
    WARNING_BEFORE_SECONDS = 120

    TIMER_PREFIX = "job:timer:"
    WARNING_PREFIX = "job:timer_warning:"
    WARNED_PREFIX = "job:timer_warned:"

    @classmethod
    def _timer_key(cls, job_id: str) -> str:
        return f"{cls.TIMER_PREFIX}{job_id}"

    @classmethod
    def _warning_key(cls, job_id: str) -> str:
        return f"{cls.WARNING_PREFIX}{job_id}"

    @classmethod
    def _warned_key(cls, job_id: str) -> str:
        return f"{cls.WARNED_PREFIX}{job_id}"

    @classmethod
    def start_timer(
        cls,
        redis_client,
        job_id: str,
        tech_id: str,
        duration_seconds: int = ACCEPTANCE_DURATION_SECONDS,
    ) -> bool:
        """
        Start or restart the technician acceptance timer.
        """

        if redis_client is None:
            logger.warning(
                "TimerService: Redis unavailable for job %s",
                job_id,
            )
            return False

        try:
            duration_seconds = int(duration_seconds)
        except (TypeError, ValueError):
            duration_seconds = cls.ACCEPTANCE_DURATION_SECONDS

        duration_seconds = max(1, duration_seconds)

        now = datetime.now(timezone.utc)

        expires_at = now + timedelta(
            seconds=duration_seconds
        )

        warning_seconds = max(
            0,
            duration_seconds - cls.WARNING_BEFORE_SECONDS,
        )

        warning_at = now + timedelta(
            seconds=warning_seconds
        )

        timer_data = {
            "job_id": str(job_id),
            "tech_id": str(tech_id),
            "started_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "duration_seconds": duration_seconds,
        }

        warning_data = {
            "job_id": str(job_id),
            "tech_id": str(tech_id),
            "warning_at": warning_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

        try:
            # Always replace the old timer.
            redis_client.setex(
                cls._timer_key(job_id),
                duration_seconds,
                json.dumps(timer_data),
            )

            # Create warning timer.
            if warning_seconds > 0:
                redis_client.setex(
                    cls._warning_key(job_id),
                    warning_seconds,
                    json.dumps(warning_data),
                )
            else:
                redis_client.delete(
                    cls._warning_key(job_id)
                )

            # Clear previous warning flag.
            redis_client.delete(
                cls._warned_key(job_id)
            )

            logger.info(
                "TimerService: Started timer "
                "job=%s tech=%s duration=%ss expires=%s",
                job_id,
                tech_id,
                duration_seconds,
                expires_at.isoformat(),
            )

            return True

        except Exception:
            logger.exception(
                "TimerService: Failed to start timer for job %s",
                job_id,
            )
            return False

    @classmethod
    def cancel_timer(
        cls,
        redis_client,
        job_id: str,
    ) -> bool:
        """
        Cancel all timer-related Redis keys.
        """

        if redis_client is None:
            return False

        try:
            deleted = redis_client.delete(
                cls._timer_key(job_id),
                cls._warning_key(job_id),
                cls._warned_key(job_id),
            )

            if deleted:
                logger.info(
                    "TimerService: Cancelled timer for job %s",
                    job_id,
                )

            return bool(deleted)

        except Exception:
            logger.exception(
                "TimerService: Failed to cancel timer for job %s",
                job_id,
            )
            return False

    @classmethod
    def get_timer(
        cls,
        redis_client,
        job_id: str,
    ) -> Optional[dict]:
        """
        Read timer payload from Redis.

        None means Redis does not currently contain
        the timer. It does NOT mean that the assignment
        is necessarily expired.
        """

        if redis_client is None:
            return None

        try:
            raw = redis_client.get(
                cls._timer_key(job_id)
            )

            if raw is None:
                return None

            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")

            data = json.loads(raw)

            if not isinstance(data, dict):
                return None

            return data

        except Exception:
            logger.exception(
                "TimerService: Failed to read timer for job %s",
                job_id,
            )
            return None

    @classmethod
    def get_remaining_seconds(
        cls,
        redis_client,
        job_id: str,
    ) -> Optional[int]:
        """
        Get Redis TTL.

        None means Redis timer is unavailable/missing.
        """

        if redis_client is None:
            return None

        try:
            ttl = redis_client.ttl(
                cls._timer_key(job_id)
            )

            if ttl is None or ttl < 0:
                return None

            return int(ttl)

        except Exception:
            logger.exception(
                "TimerService: Failed to read TTL for job %s",
                job_id,
            )
            return None

    @classmethod
    def is_timer_active(
        cls,
        redis_client,
        job_id: str,
    ) -> bool:
        """
        Fast Redis check.

        IMPORTANT:
        This is only a Redis availability check.
        It must NOT be used as the authoritative
        assignment-expiration check.
        """

        if redis_client is None:
            return False

        try:
            return bool(
                redis_client.exists(
                    cls._timer_key(job_id)
                )
            )
        except Exception:
            logger.exception(
                "TimerService: Failed checking timer for job %s",
                job_id,
            )
            return False