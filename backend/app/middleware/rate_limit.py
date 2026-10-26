"""
API abuse control: configurable, Redis-backed rate limiting.

Layers
------
1. RateLimitMiddleware  (runs BEFORE authentication)
   - Keys are derived ONLY from the network client IP. Nothing the client
     can set (X-Tenant-ID, X-User-ID, query params, arbitrary headers) is
     used as a counter identity.
   - Longest matching route prefix wins; auth endpoints are strict.

2. rate_limit_dependency(policy)  (runs AFTER authentication)
   - Keys are derived from request.state.tenant_id / user_id, which are set
     by the authentication dependency from a *verified* JWT. This is where
     tenant/user-aware limits (e.g. GPS) belong. If no verified identity is
     present it falls back to the IP, it never skips the limit.

Redis behaviour is explicit per policy:
   fail_closed=True  -> 503 + Retry-After   (credential-style endpoints)
   fail_closed=False -> request is allowed, error is logged (general API)

Counting is a single atomic Lua script (INCR + PEXPIRE + PTTL), so a crash
between INCR and EXPIRE can never leave an immortal counter.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import math
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable, Mapping, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


# ─────────────────────────── policy & configuration ───────────────────────────


@dataclass(frozen=True)
class RateLimitPolicy:
    name: str
    max_requests: int
    window_seconds: int
    fail_closed: bool = False

    def __post_init__(self):
        if not self.name:
            raise ValueError("Rate-limit policy needs a name")
        if self.max_requests <= 0 or self.window_seconds <= 0:
            raise ValueError(
                f"Rate-limit policy '{self.name}': max_requests and "
                "window_seconds must be positive integers"
            )


# Adjust the non-auth prefixes (/gps, /tracking, /socket.io) to your real
# route prefixes. They are generous per-IP CEILINGS only: many technicians
# can share one NAT/depot IP, so the real per-user GPS limit belongs in
# rate_limit_dependency (see gps.py example).
DEFAULT_ROUTE_POLICIES: Mapping[str, RateLimitPolicy] = {
    "/auth/login": RateLimitPolicy("auth_login", 10, 60, True),
    "/auth/register": RateLimitPolicy("auth_register", 5, 60, True),
    "/auth/forgot-password": RateLimitPolicy("auth_forgot_password", 3, 300, True),
    "/auth/reset-password": RateLimitPolicy("auth_reset_password", 3, 300, True),
    "/auth/change-password": RateLimitPolicy("auth_change_password", 10, 60, True),
    "/auth/refresh": RateLimitPolicy("auth_refresh", 20, 60, True),
    "/auth/sso/login": RateLimitPolicy("auth_sso_login", 20, 60, True),
    "/auth/sso/callback": RateLimitPolicy("auth_sso_callback", 30, 60, True),
    # Every other /auth/* route: stricter than general, but fail-open so a
    # Redis blip does not lock everybody out of e.g. /auth/me.
    "/auth": RateLimitPolicy("auth_other", 60, 60, False),
    "/api/v1/gps": RateLimitPolicy("gps_ip_ceiling", 300, 60, False),
    "/gps": RateLimitPolicy("gps_ip_ceiling", 300, 60, False),
    "/api/technician": RateLimitPolicy("technician_api", 300, 60, False),
    "/technicians": RateLimitPolicy("technician_api", 300, 60, False),
    "/api/v1/jobs": RateLimitPolicy("technician_jobs_api", 300, 60, False),
    "/jobs": RateLimitPolicy("technician_jobs_api", 300, 60, False),
    "/tracking": RateLimitPolicy("tracking_ip_ceiling", 600, 60, False),
    "/socket.io": RateLimitPolicy("socket_io_ceiling", 600, 60, False),
    "GET /*": RateLimitPolicy("read_api", 600, 60, False),
    "HEAD /*": RateLimitPolicy("read_api", 600, 60, False),
}

DEFAULT_GENERAL_POLICY = RateLimitPolicy("general_api", 300, 60, False)

DEFAULT_SKIP_PATHS = frozenset({"/", "/docs", "/openapi.json", "/redoc"})


@dataclass(frozen=True)
class RateLimitConfig:
    enabled: bool = True
    # Number of trusted reverse proxies in front of the app. 0 = never trust
    # X-Forwarded-For (safe default).
    trusted_proxy_hops: int = 0
    default_policy: RateLimitPolicy = DEFAULT_GENERAL_POLICY
    route_policies: Mapping[str, RateLimitPolicy] = field(
        default_factory=lambda: dict(DEFAULT_ROUTE_POLICIES)
    )
    skip_paths: frozenset = DEFAULT_SKIP_PATHS


def _env_bool(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _slug(prefix: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", prefix.lower()).strip("_") or "root"


def load_rate_limit_config(env: Optional[Mapping[str, str]] = None) -> RateLimitConfig:
    """
    Environment variables
    ---------------------
    RATE_LIMIT_ENABLED              true|false                       (default true)
    RATE_LIMIT_TRUSTED_PROXY_HOPS   int                              (default 0)
    RATE_LIMIT_DEFAULT_MAX          int                              (default 300)
    RATE_LIMIT_DEFAULT_WINDOW       seconds                          (default 60)
    RATE_LIMIT_POLICIES_JSON        route-prefix or METHOD /path overrides, e.g.
        {"/auth/login": {"max": 5, "window": 60, "fail_closed": true},
         "GET /api/reports": {"max": 600, "window": 60}}

    Invalid configuration raises ValueError at startup instead of silently
    weakening protection.
    """
    env = os.environ if env is None else env

    default = RateLimitPolicy(
        DEFAULT_GENERAL_POLICY.name,
        int(env.get("RATE_LIMIT_DEFAULT_MAX", DEFAULT_GENERAL_POLICY.max_requests)),
        int(env.get("RATE_LIMIT_DEFAULT_WINDOW", DEFAULT_GENERAL_POLICY.window_seconds)),
        DEFAULT_GENERAL_POLICY.fail_closed,
    )

    hops = int(env.get("RATE_LIMIT_TRUSTED_PROXY_HOPS", 0))
    if hops < 0:
        raise ValueError("RATE_LIMIT_TRUSTED_PROXY_HOPS must be >= 0")

    policies = dict(DEFAULT_ROUTE_POLICIES)

    raw = env.get("RATE_LIMIT_POLICIES_JSON")
    if raw:
        try:
            overrides = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"RATE_LIMIT_POLICIES_JSON is not valid JSON: {exc}") from exc
        if not isinstance(overrides, dict):
            raise ValueError("RATE_LIMIT_POLICIES_JSON must be a JSON object")

        for prefix, spec in overrides.items():
            parsed_method, parsed_path = _policy_rule(prefix) if isinstance(prefix, str) else (None, "")
            if not isinstance(prefix, str) or (parsed_method is None and not prefix.startswith("/")):
                raise ValueError(f"Invalid rate-limit prefix: {prefix!r}")
            if not isinstance(spec, dict):
                raise ValueError(f"Policy for {prefix} must be an object")
            prefix = (
                f"{parsed_method} {parsed_path}"
                if parsed_method is not None
                else prefix.rstrip("/") or "/"
            )
            base = policies.get(prefix)
            if parsed_path.startswith("/auth"):
                auth_bases = [
                    (route, policy)
                    for route, policy in DEFAULT_ROUTE_POLICIES.items()
                    if route.startswith("/auth")
                    and (parsed_path == route or parsed_path.startswith(route.rstrip("/") + "/"))
                ]
                auth_base = max(auth_bases, key=lambda item: len(item[0]))[1]
                requested_max = int(spec.get("max", base.max_requests if base else -1))
                requested_fail_closed = bool(
                    spec.get("fail_closed", base.fail_closed if base else False)
                )
                if requested_max > auth_base.max_requests or (
                    auth_base.fail_closed and not requested_fail_closed
                ):
                    raise ValueError(
                        f"Authentication rate-limit override for {prefix} cannot be weaker than its default"
                    )
            policies[prefix] = RateLimitPolicy(
                name=spec.get("name") or (base.name if base else _slug(prefix)),
                max_requests=int(spec.get("max", base.max_requests if base else -1)),
                window_seconds=int(spec.get("window", base.window_seconds if base else -1)),
                fail_closed=bool(
                    spec.get("fail_closed", base.fail_closed if base else False)
                ),
            )

    return RateLimitConfig(
        enabled=_env_bool(env.get("RATE_LIMIT_ENABLED"), True),
        trusted_proxy_hops=hops,
        default_policy=default,
        route_policies=policies,
    )


@lru_cache(maxsize=1)
def get_rate_limit_config() -> RateLimitConfig:
    return load_rate_limit_config()


# ───────────────────────────── identity & keys ────────────────────────────────


def hash_identifier(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def client_ip(request: Request, trusted_proxy_hops: int = 0) -> str:
    """
    Direct peer address by default. X-Forwarded-For is honoured ONLY when
    trusted_proxy_hops > 0, and then only the entry appended by our own
    outermost trusted proxy (counted from the right), so a client cannot
    choose its own bucket by prepending fake entries.
    """
    direct = request.client.host if request.client else "unknown"

    if trusted_proxy_hops > 0:
        header = request.headers.get("x-forwarded-for", "")
        parts = [p.strip() for p in header.split(",") if p.strip()]
        if len(parts) >= trusted_proxy_hops:
            candidate = parts[-trusted_proxy_hops]
            try:
                return str(ipaddress.ip_address(candidate))
            except ValueError:
                pass
    return direct


def build_key(policy: RateLimitPolicy, **identity: object) -> str:
    """
    Keys are namespaced by policy and built from hashed identity parts,
    e.g. rl:v2:gps_location:tenant:<h>:user:<h>. Identity parts must come
    from trusted sources only (peer IP, verified JWT claims).
    """
    segments = [f"{k}:{hash_identifier(str(v))}" for k, v in identity.items()]
    return f"rl:v2:{policy.name}:" + ":".join(segments)


_HTTP_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
_PARAMETER_COLLECTIONS = frozenset({
    "jobs", "technicians", "users", "requests", "service-requests",
    "customers", "organizations", "notifications", "history",
})
_STATIC_COLLECTION_SEGMENTS = frozenset({
    "available", "all", "pending", "search", "history", "metrics",
    "count", "status", "unread-count",
})
_UUID_PATH_SEGMENT = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def normalize_route_path(path: str) -> str:
    """Normalize equivalent route URLs while keeping endpoint identities distinct."""
    parts = [part for part in str(path or "/").split("/") if part]
    normalized: list[str] = []
    for index, part in enumerate(parts):
        previous = parts[index - 1].lower() if index else ""
        if part.isdigit() or _UUID_PATH_SEGMENT.fullmatch(part):
            normalized.append("{id}")
        elif previous in _PARAMETER_COLLECTIONS and part.lower() not in _STATIC_COLLECTION_SEGMENTS:
            normalized.append("{id}")
        else:
            normalized.append(part)
    return "/" + "/".join(normalized) if normalized else "/"


def _policy_rule(rule: str) -> tuple[str | None, str]:
    """Split an optional HTTP method from a path-prefix policy rule."""
    method, separator, path = rule.partition(" ")
    if separator and method.upper() in _HTTP_METHODS and path.startswith("/"):
        return method.upper(), path.rstrip("/") or "/"
    return None, rule.rstrip("/") or "/"


def _policy_path_matches(path: str, rule_path: str) -> bool:
    if rule_path == "/*":
        return True
    if rule_path.endswith("/*"):
        prefix = rule_path[:-2].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return path == rule_path or path.startswith(rule_path.rstrip("/") + "/")


# ──────────────────────────────── Redis core ──────────────────────────────────

# Atomic fixed-window counter. Returns {count, ttl_ms}.
_COUNTER_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('PEXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('PTTL', KEYS[1])
if ttl < 0 then
  redis.call('PEXPIRE', KEYS[1], ARGV[1])
  ttl = tonumber(ARGV[1])
end
return {current, ttl}
"""


@dataclass(frozen=True)
class Decision:
    allowed: bool
    retry_after: int = 0
    backend_error: bool = False


def consume(redis, key: str, policy: RateLimitPolicy) -> Decision:
    """Synchronous, atomic. Never raises."""
    try:
        current, ttl_ms = redis.eval(
            _COUNTER_SCRIPT, 1, key, policy.window_seconds * 1000
        )
        current, ttl_ms = int(current), int(ttl_ms)
    except Exception as exc:
        logger.error(
            "Rate limit Redis operation failed: policy=%s error=%s",
            policy.name,
            exc,
        )
        return Decision(allowed=not policy.fail_closed, backend_error=True)

    if current > policy.max_requests:
        retry_after = min(policy.window_seconds, max(1, math.ceil(ttl_ms / 1000)))
        return Decision(allowed=False, retry_after=retry_after)
    return Decision(allowed=True)


def _default_redis_factory():
    from ..redis_client import get_redis_client

    return get_redis_client()


async def enforce(
    redis_factory: Callable[[], object],
    key: str,
    policy: RateLimitPolicy,
) -> Decision:
    try:
        redis = redis_factory()
    except Exception as exc:
        logger.error(
            "Unable to obtain Redis client for rate limiting: policy=%s error=%s",
            policy.name,
            exc,
        )
        redis = None

    if redis is None:
        return Decision(allowed=not policy.fail_closed, backend_error=True)

    # redis-py is synchronous: keep it off the event loop.
    return await run_in_threadpool(consume, redis, key, policy)


# ───────────────────────────────── responses ──────────────────────────────────


def too_many_requests_response(retry_after: int) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Too many requests. Please try again later.",
            "retry_after": retry_after,
            "status": 429,
        },
        headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
    )


def unavailable_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Rate limiting service is temporarily unavailable. "
                "Please try again later."
            )
        },
        headers={"Retry-After": "30", "Cache-Control": "no-store"},
    )


# ───────────────────────────────── middleware ─────────────────────────────────


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    IP-scoped limiter that runs before authentication.
    See module docstring for the security model.
    """

    def __init__(
        self,
        app,
        config: Optional[RateLimitConfig] = None,
        redis_factory: Optional[Callable[[], object]] = None,
    ):
        super().__init__(app)
        self.config = config or get_rate_limit_config()
        self._redis_factory = redis_factory or _default_redis_factory
        # Longest route prefix wins; method-specific ties beat generic rules.
        self._rules = sorted(
            self.config.route_policies,
            key=lambda rule: (
                len(_policy_rule(rule)[1].replace("*", "")),
                _policy_rule(rule)[0] is not None,
            ),
            reverse=True,
        )

    def policy_for(self, path: str, method: str = "GET") -> RateLimitPolicy:
        normalized_path = normalize_route_path(path)
        normalized_method = method.upper()
        for rule in self._rules:
            rule_method, rule_path = _policy_rule(rule)
            if rule_method is not None and rule_method != normalized_method:
                continue
            if _policy_path_matches(normalized_path, rule_path):
                return self.config.route_policies[rule]
        return self.config.default_policy

    async def dispatch(self, request: Request, call_next):
        cfg = self.config
        path = request.url.path

        if (
            not cfg.enabled
            or request.method == "OPTIONS"  # CORS preflight
            or path in cfg.skip_paths
            or request.headers.get("upgrade", "").lower() == "websocket"
        ):
            return await call_next(request)

        method = request.method.upper()
        policy = self.policy_for(path, method)
        ip = client_ip(request, cfg.trusted_proxy_hops)
        endpoint = f"{method}:{normalize_route_path(path)}"
        key = build_key(policy, endpoint=endpoint, ip=ip)

        decision = await enforce(self._redis_factory, key, policy)

        if decision.backend_error:
            if policy.fail_closed:
                logger.error(
                    "Rate limiter unavailable; failing closed: policy=%s path=%s",
                    policy.name,
                    path,
                )
                return unavailable_response()
            logger.warning(
                "Rate limiter unavailable; failing open: policy=%s path=%s",
                policy.name,
                path,
            )
            return await call_next(request)

        if not decision.allowed:
            logger.warning(
                "Rate limit exceeded: policy=%s path=%s limit=%s window=%ss ip=%s",
                policy.name,
                path,
                policy.max_requests,
                policy.window_seconds,
                hash_identifier(ip)[:8],
            )
            return too_many_requests_response(decision.retry_after)

        return await call_next(request)


# ──────────────── post-authentication tenant/user-aware limiter ───────────────


def rate_limit_dependency(
    policy: RateLimitPolicy,
    *,
    config: Optional[RateLimitConfig] = None,
    redis_factory: Optional[Callable[[], object]] = None,
):
    """
    FastAPI dependency. Put it AFTER the authentication dependency so
    request.state.tenant_id / user_id come from a verified token:

        gps_limit = rate_limit_dependency(RateLimitPolicy("gps_location", 120, 60))

        @router.post("/gps/location",
                     dependencies=[Depends(get_current_user), Depends(gps_limit)])

    Never reads request headers for identity. Falls back to the IP when no
    verified identity exists (it never skips the limit).
    """

    async def _dependency(request: Request) -> None:
        cfg = config or get_rate_limit_config()
        if not cfg.enabled:
            return

        tenant_id = getattr(request.state, "tenant_id", None)
        user_id = getattr(request.state, "user_id", None)

        if user_id is not None:
            key = build_key(
                policy,
                endpoint=f"{request.method.upper()}:{normalize_route_path(request.url.path)}",
                tenant=tenant_id or "none",
                user=user_id,
            )
        elif tenant_id is not None:
            key = build_key(
                policy,
                endpoint=f"{request.method.upper()}:{normalize_route_path(request.url.path)}",
                tenant=tenant_id,
            )
        else:
            key = build_key(
                policy,
                endpoint=f"{request.method.upper()}:{normalize_route_path(request.url.path)}",
                ip=client_ip(request, cfg.trusted_proxy_hops),
            )

        decision = await enforce(redis_factory or _default_redis_factory, key, policy)

        if decision.backend_error:
            if policy.fail_closed:
                raise HTTPException(
                    status_code=503,
                    detail="Rate limiting service is temporarily unavailable.",
                    headers={"Retry-After": "30"},
                )
            return

        if not decision.allowed:
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(decision.retry_after)},
            )

    return _dependency


def authenticated_rate_limit_dependency(
    policy: RateLimitPolicy,
    identity_dependency: Callable,
    *,
    config: Optional[RateLimitConfig] = None,
    redis_factory: Optional[Callable[[], object]] = None,
):
    """Apply the shared limiter using an identity returned by verified auth."""
    limiter = rate_limit_dependency(
        policy, config=config, redis_factory=redis_factory
    )

    async def _dependency(
        request: Request,
        identity=Depends(identity_dependency),
    ) -> None:
        request.state.tenant_id = getattr(identity, "tenant_id", None)
        request.state.user_id = getattr(identity, "user_id", None)
        await limiter(request)

    return _dependency


# ─────────────────────────────── status endpoint ──────────────────────────────

status_router = APIRouter(tags=["rate-limit"])


@status_router.get("/rate-limit/status")
def rate_limit_status():
    cfg = get_rate_limit_config()
    return {
        "status": "SUPPORTED",
        "rate_limiting": "enabled" if cfg.enabled else "disabled",
        "backend": "redis",
        "status_on_limit": 429,
    }
