from app.services.heartbeat_rate_limit import (
    HEARTBEAT_RATE_LIMIT_TTL_SECONDS,
    claim_heartbeat_slot,
)


class FakeRedis:
    def __init__(self):
        self.expires_ms = {}
        self.now_ms = 0
        self.fail = False
        self.zero_ttl = False

    def set(self, key, value, ex=None, nx=False):
        if self.fail:
            return None
        if nx and key in self.expires_ms and self.expires_ms[key] > self.now_ms:
            return False
        self.expires_ms[key] = self.now_ms + ex * 1000
        return True

    def pttl(self, key):
        if key not in self.expires_ms:
            return -2
        if self.zero_ttl:
            return 0
        return max(0, self.expires_ms[key] - self.now_ms)

    def expire(self, key, seconds):
        self.expires_ms[key] = self.now_ms + seconds * 1000
        return True


def test_heartbeat_slot_expires_before_the_35_second_frontend_interval():
    redis = FakeRedis()
    assert claim_heartbeat_slot(redis, "heartbeat:tenant:tech") == (True, 0)
    assert HEARTBEAT_RATE_LIMIT_TTL_SECONDS == 25
    redis.now_ms += 25_000
    assert claim_heartbeat_slot(redis, "heartbeat:tenant:tech") == (True, 0)


def test_ttl_zero_boundary_retries_atomic_claim_once():
    redis = FakeRedis()
    claim_heartbeat_slot(redis, "heartbeat:tenant:tech")
    redis.now_ms = 24_999
    redis.zero_ttl = True
    allowed, retry_after = claim_heartbeat_slot(redis, "heartbeat:tenant:tech")
    assert allowed is False
    assert retry_after == 1
    redis.now_ms = 25_000
    redis.zero_ttl = False
    assert claim_heartbeat_slot(redis, "heartbeat:tenant:tech") == (True, 0)


def test_redis_failure_does_not_masquerade_as_rate_limit():
    redis = FakeRedis()
    redis.fail = True
    assert claim_heartbeat_slot(redis, "heartbeat:tenant:tech") == (True, 0)
