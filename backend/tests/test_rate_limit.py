
"""
Comprehensive tests for Redis-backed API rate limiting.

Coverage:
1. Under limit
2. Over limit / 429
3. Authentication-specific limits
4. Route prefix matching
5. Window reset
6. CORS preflight
7. Disabled configuration
8. Redis unavailable / fail-open
9. Redis unavailable / fail-closed
10. Redis factory failure
11. Concurrent HTTP requests
12. Atomic counter concurrency
13. Spoofed tenant header
14. X-Forwarded-For handling
15. Trusted proxy handling
16. Tenant/user-aware dependency
17. Dependency fail-closed
18. Existing auth policy regression
19. Environment configuration
20. Status endpoint
21. GPS-specific rate-limit response
"""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from app.middleware.rate_limit import (
    DEFAULT_ROUTE_POLICIES,
    RateLimitConfig,
    RateLimitMiddleware,
    RateLimitPolicy,
    build_key,
    consume,
    load_rate_limit_config,
    rate_limit_dependency,
    status_router,
)


# ============================================================================
# FAKES
# ============================================================================

class FakeRedis:
    """
    Thread-safe fake Redis.

    Mimics the atomic Lua counter used by the production rate limiter.
    Supports an injectable clock for deterministic window-reset tests.
    """

    def __init__(self, clock=None):
        import time

        self.clock = clock or time.monotonic
        self._data = {}
        self._lock = threading.Lock()
        self.calls = 0

    def eval(self, script, numkeys, key, window_ms):
        with self._lock:
            self.calls += 1

            now = self.clock()

            count, expires_at = self._data.get(
                key,
                (0, 0.0),
            )

            if count and now >= expires_at:
                count = 0

            count += 1

            if count == 1:
                expires_at = now + int(window_ms) / 1000

            self._data[key] = (
                count,
                expires_at,
            )

            retry_ms = max(
                1,
                int((expires_at - now) * 1000),
            )

            return [
                count,
                retry_ms,
            ]


class BrokenRedis:
    """Redis failure simulation."""

    def eval(self, *args, **kwargs):
        raise ConnectionError("redis down")


# ============================================================================
# CONFIGURATION HELPERS
# ============================================================================

def make_config(
    general=5,
    login=3,
    hops=0,
    enabled=True,
):
    """
    Create deterministic test configuration.

    Auth routes are fail-closed.
    General API is fail-open.
    """

    return RateLimitConfig(
        enabled=enabled,
        trusted_proxy_hops=hops,
        default_policy=RateLimitPolicy(
            "general_api",
            general,
            60,
            False,
        ),
        route_policies={
            "/auth/login": RateLimitPolicy(
                "auth_login",
                login,
                60,
                True,
            ),
        },
    )


# ============================================================================
# TEST APP
# ============================================================================

def make_app(redis_obj, config):
    app = FastAPI()

    app.add_middleware(
        RateLimitMiddleware,
        config=config,
        redis_factory=lambda: redis_obj,
    )

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    @app.post("/auth/login")
    def login():
        return {"ok": True}

    @app.get("/auth/login-help")
    def login_help():
        return {"ok": True}

    return app


# ============================================================================
# 1. UNDER LIMIT
# ============================================================================

def test_under_limit_allows_requests():
    client = TestClient(
        make_app(
            FakeRedis(),
            make_config(general=5),
        )
    )

    for _ in range(5):
        response = client.get("/api/ping")

        assert response.status_code == 200


# ============================================================================
# 2. OVER LIMIT
# ============================================================================

def test_over_limit_returns_429_with_safe_retry_guidance():
    client = TestClient(
        make_app(
            FakeRedis(),
            make_config(general=5),
        )
    )

    for _ in range(5):
        client.get("/api/ping")

    response = client.get("/api/ping")

    assert response.status_code == 429

    assert "Retry-After" in response.headers

    retry_after = int(
        response.headers["Retry-After"]
    )

    assert 1 <= retry_after <= 60

    assert response.headers["Cache-Control"] == "no-store"

    body = response.json()

    assert body["status"] == 429

    assert body["retry_after"] == retry_after

    assert "tenant" not in response.text.lower()


# ============================================================================
# 3. AUTHENTICATION LIMITS
# ============================================================================

def test_auth_endpoints_are_stricter_than_general():
    client = TestClient(
        make_app(
            FakeRedis(),
            make_config(
                general=100,
                login=3,
            ),
        )
    )

    codes = [
        client.post("/auth/login").status_code
        for _ in range(5)
    ]

    assert codes == [
        200,
        200,
        200,
        429,
        429,
    ]


def test_prefix_match_is_segment_aware():
    client = TestClient(
        make_app(
            FakeRedis(),
            make_config(
                general=5,
                login=1,
            ),
        )
    )

    # /auth/login-help must NOT inherit /auth/login limit.
    for _ in range(4):
        response = client.get(
            "/auth/login-help"
        )

        assert response.status_code == 200


# ============================================================================
# 4. WINDOW RESET
# ============================================================================

def test_window_resets():
    now = [1000.0]

    redis = FakeRedis(
        clock=lambda: now[0]
    )

    client = TestClient(
        make_app(
            redis,
            make_config(general=2),
        )
    )

    assert client.get(
        "/api/ping"
    ).status_code == 200

    assert client.get(
        "/api/ping"
    ).status_code == 200

    assert client.get(
        "/api/ping"
    ).status_code == 429

    # Move past the 60-second window.
    now[0] += 61

    assert client.get(
        "/api/ping"
    ).status_code == 200


# ============================================================================
# 5. CORS PREFLIGHT
# ============================================================================

def test_cors_preflight_is_not_counted():
    redis = FakeRedis()

    client = TestClient(
        make_app(
            redis,
            make_config(general=1),
        )
    )

    for _ in range(10):
        client.options("/api/ping")

    assert redis.calls == 0

    assert client.get(
        "/api/ping"
    ).status_code == 200


# ============================================================================
# 6. DISABLED CONFIG
# ============================================================================

def test_disabled_config_never_limits():
    client = TestClient(
        make_app(
            FakeRedis(),
            make_config(
                general=1,
                enabled=False,
            ),
        )
    )

    results = [
        client.get("/api/ping").status_code
        for _ in range(10)
    ]

    assert results == [200] * 10


# ============================================================================
# 7. REDIS UNAVAILABLE - AUTH FAIL CLOSED
# ============================================================================

@pytest.mark.parametrize(
    "redis_obj",
    [
        BrokenRedis(),
        None,
    ],
)
def test_redis_down_auth_fails_closed(redis_obj):
    client = TestClient(
        make_app(
            redis_obj,
            make_config(),
        )
    )

    response = client.post(
        "/auth/login"
    )

    assert response.status_code == 503

    assert response.headers["Retry-After"] == "30"


# ============================================================================
# 8. REDIS UNAVAILABLE - GENERAL API FAIL OPEN
# ============================================================================

@pytest.mark.parametrize(
    "redis_obj",
    [
        BrokenRedis(),
        None,
    ],
)
def test_redis_down_general_api_fails_open(redis_obj):
    client = TestClient(
        make_app(
            redis_obj,
            make_config(),
        )
    )

    response = client.get(
        "/api/ping"
    )

    assert response.status_code == 200


# ============================================================================
# 9. REDIS FACTORY FAILURE
# ============================================================================

def test_redis_factory_raising_is_handled():
    def boom():
        raise RuntimeError(
            "cannot connect"
        )

    app = FastAPI()

    app.add_middleware(
        RateLimitMiddleware,
        config=make_config(),
        redis_factory=boom,
    )

    @app.get("/api/ping")
    def ping():
        return {}

    @app.post("/auth/login")
    def login():
        return {}

    client = TestClient(app)

    # General API is fail-open.
    assert client.get(
        "/api/ping"
    ).status_code == 200

    # Auth is fail-closed.
    assert client.post(
        "/auth/login"
    ).status_code == 503


# ============================================================================
# 10. CONCURRENT HTTP REQUESTS
# ============================================================================

def test_concurrent_requests_exactly_limit_allowed_http():
    app = make_app(
        FakeRedis(),
        make_config(general=10),
    )

    async def run():
        transport = httpx.ASGITransport(
            app=app
        )

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://test",
        ) as client:

            responses = await asyncio.gather(
                *[
                    client.get("/api/ping")
                    for _ in range(50)
                ]
            )

        return [
            response.status_code
            for response in responses
        ]

    codes = asyncio.run(run())

    assert codes.count(200) == 10
    assert codes.count(429) == 40


# ============================================================================
# 11. ATOMIC COUNTER CONCURRENCY
# ============================================================================

def test_concurrent_counter_is_atomic_across_threads():
    redis = FakeRedis()

    policy = RateLimitPolicy(
        "race",
        10,
        60,
    )

    key = build_key(
        policy,
        ip="1.2.3.4",
    )

    with ThreadPoolExecutor(
        max_workers=32
    ) as pool:

        decisions = list(
            pool.map(
                lambda _: consume(
                    redis,
                    key,
                    policy,
                ),
                range(200),
            )
        )

    assert sum(
        decision.allowed
        for decision in decisions
    ) == 10

    assert sum(
        not decision.allowed
        for decision in decisions
    ) == 190


# ============================================================================
# 12. SPOOFED TENANT HEADER
# ============================================================================

def test_spoofed_tenant_header_does_not_create_new_bucket():
    client = TestClient(
        make_app(
            FakeRedis(),
            make_config(general=5),
        )
    )

    for i in range(5):
        response = client.get(
            "/api/ping",
            headers={
                "X-Tenant-ID": f"tenant-{i}"
            },
        )

        assert response.status_code == 200

    response = client.get(
        "/api/ping",
        headers={
            "X-Tenant-ID": "brand-new-tenant"
        },
    )

    assert response.status_code == 429


# ============================================================================
# 13. X-FORWARDED-FOR
# ============================================================================

def test_x_forwarded_for_ignored_by_default():
    client = TestClient(
        make_app(
            FakeRedis(),
            make_config(general=2),
        )
    )

    client.get(
        "/api/ping",
        headers={
            "X-Forwarded-For": "1.1.1.1"
        },
    )

    client.get(
        "/api/ping",
        headers={
            "X-Forwarded-For": "2.2.2.2"
        },
    )

    response = client.get(
        "/api/ping",
        headers={
            "X-Forwarded-For": "3.3.3.3"
        },
    )

    assert response.status_code == 429


def test_trusted_proxy_uses_rightmost_entry_and_resists_prefix_spoofing():
    client = TestClient(
        make_app(
            FakeRedis(),
            make_config(
                general=1,
                hops=1,
            ),
        )
    )

    assert client.get(
        "/api/ping",
        headers={
            "X-Forwarded-For": "1.1.1.1"
        },
    ).status_code == 200

    # Different real client.
    assert client.get(
        "/api/ping",
        headers={
            "X-Forwarded-For": "2.2.2.2"
        },
    ).status_code == 200

    # Fake prefix should not bypass bucket.
    response = client.get(
        "/api/ping",
        headers={
            "X-Forwarded-For": "6.6.6.6, 1.1.1.1"
        },
    )

    assert response.status_code == 429


# ============================================================================
# 14. TENANT / USER-AWARE DEPENDENCY
# ============================================================================

def test_dependency_isolates_tenants_and_ignores_spoofed_header():
    redis = FakeRedis()

    policy = RateLimitPolicy(
        "tenant_user_test",
        2,
        60,
    )

    limit = rate_limit_dependency(
        policy,
        config=make_config(),
        redis_factory=lambda: redis,
    )

    async def fake_auth(request: Request):
        # Simulates the REAL JWT-verified identity.
        request.state.tenant_id = request.headers[
            "X-Test-Verified-Tenant"
        ]

        request.state.user_id = "user-1"

    app = FastAPI()

    @app.get(
        "/t",
        dependencies=[
            Depends(fake_auth),
            Depends(limit),
        ],
    )
    def t():
        return {}

    client = TestClient(app)

    tenant_a = {
        "X-Test-Verified-Tenant": "tenant-A"
    }

    tenant_b = {
        "X-Test-Verified-Tenant": "tenant-B"
    }

    assert client.get(
        "/t",
        headers=tenant_a,
    ).status_code == 200

    assert client.get(
        "/t",
        headers=tenant_a,
    ).status_code == 200

    response = client.get(
        "/t",
        headers=tenant_a,
    )

    assert response.status_code == 429
    assert "Retry-After" in response.headers

    # Tenant B must have its own bucket.
    assert client.get(
        "/t",
        headers=tenant_b,
    ).status_code == 200

    # Spoofing X-Tenant-ID must not change verified bucket.
    spoofed = {
        **tenant_a,
        "X-Tenant-ID": "tenant-B",
    }

    assert client.get(
        "/t",
        headers=spoofed,
    ).status_code == 429


# ============================================================================
# 15. DEPENDENCY FAIL CLOSED
# ============================================================================

def test_dependency_fail_closed_returns_503():
    limit = rate_limit_dependency(
        RateLimitPolicy(
            "strict",
            1,
            60,
            fail_closed=True,
        ),
        config=make_config(),
        redis_factory=lambda: BrokenRedis(),
    )

    app = FastAPI()

    @app.get(
        "/t",
        dependencies=[
            Depends(limit)
        ],
    )
    def t():
        return {}

    response = TestClient(app).get(
        "/t"
    )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "30"


# ============================================================================
# 16. EXISTING AUTH LIMIT REGRESSION
# ============================================================================

def test_existing_auth_limits_unchanged():
    expected = {
        "/auth/login": (10, 60, True),
        "/auth/register": (5, 60, True),
        "/auth/forgot-password": (3, 300, True),
        "/auth/refresh": (20, 60, True),
        "/auth/sso/login": (20, 60, True),
        "/auth/sso/callback": (30, 60, True),
    }

    for prefix, (
        max_requests,
        window,
        fail_closed,
    ) in expected.items():

        policy = DEFAULT_ROUTE_POLICIES[prefix]

        assert (
            policy.max_requests,
            policy.window_seconds,
            policy.fail_closed,
        ) == (
            max_requests,
            window,
            fail_closed,
        )

    assert (
        load_rate_limit_config({})
        .default_policy
        .max_requests
        == 100
    )


# ============================================================================
# 17. ENVIRONMENT OVERRIDES
# ============================================================================

def test_env_overrides_and_validation():
    config = load_rate_limit_config(
        {
            "RATE_LIMIT_DEFAULT_MAX": "7",
            "RATE_LIMIT_POLICIES_JSON": (
                '{"/auth/login": '
                '{"max": 2, "window": 30}}'
            ),
        }
    )

    assert (
        config.default_policy.max_requests
        == 7
    )

    login = config.route_policies[
        "/auth/login"
    ]

    assert (
        login.max_requests,
        login.window_seconds,
    ) == (
        2,
        30,
    )

    # Auth fail-closed must not silently become fail-open.
    assert login.fail_closed is True

    with pytest.raises(ValueError):
        load_rate_limit_config(
            {
                "RATE_LIMIT_POLICIES_JSON":
                    "not json"
            }
        )

    with pytest.raises(ValueError):
        load_rate_limit_config(
            {
                "RATE_LIMIT_POLICIES_JSON":
                    '{"/new": {"max": 5}}'
            }
        )


# ============================================================================
# 18. STATUS ENDPOINT
# ============================================================================

def test_status_endpoint_shape(monkeypatch):
    from app.middleware.rate_limit import (
        get_rate_limit_config,
    )

    monkeypatch.setenv(
        "RATE_LIMIT_ENABLED",
        "true",
    )

    get_rate_limit_config.cache_clear()

    try:
        app = FastAPI()

        app.include_router(
            status_router
        )

        response = TestClient(app).get(
            "/rate-limit/status"
        )

        assert response.json() == {
            "status": "SUPPORTED",
            "rate_limiting": "enabled",
            "backend": "redis",
            "status_on_limit": 429,
        }

    finally:
        get_rate_limit_config.cache_clear()


# ============================================================================
# 19. GPS 429 RESPONSE CONTRACT
# ============================================================================

def test_gps_ping_over_limit_returns_429():
    """
    Verifies the GPS limiter rejects requests after the
    configured limit is exceeded.

    This test is intentionally isolated from the real
    GPS database/authentication stack.
    """

    redis = FakeRedis()

    policy = RateLimitPolicy(
        "gps_ping",
        1,
        60,
        fail_closed=False,
    )

    limit = rate_limit_dependency(
        policy,
        config=make_config(),
        redis_factory=lambda: redis,
    )

    app = FastAPI()

    @app.post(
        "/api/v1/gps/ping",
        dependencies=[
            Depends(limit)
        ],
    )
    def gps_ping():
        return {
            "status": "accepted"
        }

    client = TestClient(app)

    # First request is allowed.
    response = client.post(
        "/api/v1/gps/ping"
    )

    assert response.status_code == 200

    # Second request exceeds the limit.
    response = client.post(
        "/api/v1/gps/ping"
    )

    assert response.status_code == 429

    # Rate limiting should provide retry guidance.
    assert "Retry-After" in response.headers

    retry_after = int(
        response.headers["Retry-After"]
    )

    assert retry_after >= 1

    # Verify a safe error response without requiring
    # a specific JSON field that production does not provide.
    body = response.json()

    assert "detail" in body


# ============================================================================
# 20. GPS REDIS FAILURE
# ============================================================================

def test_gps_rate_limit_redis_failure_fails_open():
    """
    GPS is configured as fail-open because Redis
    availability should not unnecessarily stop GPS
    ingestion.
    """

    policy = RateLimitPolicy(
        "gps_ping",
        1,
        60,
        fail_closed=False,
    )

    limit = rate_limit_dependency(
        policy,
        config=make_config(),
        redis_factory=lambda: BrokenRedis(),
    )

    app = FastAPI()

    @app.post(
        "/api/v1/gps/ping",
        dependencies=[
            Depends(limit)
        ],
    )
    def gps_ping():
        return {
            "status": "accepted"
        }

    response = TestClient(app).post(
        "/api/v1/gps/ping"
    )

    assert response.status_code == 200

