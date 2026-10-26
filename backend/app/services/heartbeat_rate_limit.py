"""Atomic heartbeat throttling with a safe expiry-boundary retry."""

from __future__ import annotations

import math


HEARTBEAT_RATE_LIMIT_TTL_SECONDS = 25


def claim_heartbeat_slot(redis_client, key: str) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds); Redis outages fail open.

    A denied SET can race key expiry. When PTTL is zero or the key vanished,
    retry the atomic SET once before returning 429. Legacy no-expiry keys are
    repaired so they cannot block a technician permanently.
    """
    ttl = HEARTBEAT_RATE_LIMIT_TTL_SECONDS
    try:
        result = redis_client.set(key, "1", ex=ttl, nx=True)
        if result is True:
            return True, 0
        if result is None:
            return True, 0

        remaining_ms = redis_client.pttl(key)
        if remaining_ms in (0, -2):
            result = redis_client.set(key, "1", ex=ttl, nx=True)
            if result is True:
                return True, 0
            if result is None:
                return True, 0
            remaining_ms = redis_client.pttl(key)

        if remaining_ms == -1:
            redis_client.expire(key, ttl)
            remaining_ms = redis_client.pttl(key)
            if remaining_ms == -2:
                result = redis_client.set(key, "1", ex=ttl, nx=True)
                if result is True:
                    return True, 0
                if result is None:
                    return True, 0
                remaining_ms = redis_client.pttl(key)
        if remaining_ms is None or remaining_ms < 0:
            return True, 0

        return False, max(1, math.ceil(int(remaining_ms) / 1000))
    except Exception:
        return True, 0
