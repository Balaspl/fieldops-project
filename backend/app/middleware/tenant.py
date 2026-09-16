"""
Tenant isolation middleware and security middleware.

TenantMiddleware:
- Extracts tenant_id from JWT and injects into request.state
- Blocks access if organization is suspended/deleted
- Super Admin can access any tenant via X-Tenant-Override header

SecurityHeadersMiddleware:
- Adds security headers to all responses
- Implements basic rate limiting
"""

import logging
from typing import Optional

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses.

    Headers:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Strict-Transport-Security (HSTS)
    - Cache-Control: no-store for API responses
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(self)"

        # HSTS (only in production with HTTPS)
        # response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Prevent caching of API responses
        if request.url.path.startswith("/api") or request.url.path.startswith("/auth"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Redis-backed rate limiting middleware.

    Applies different limits based on endpoint:
    - Auth endpoints (login, register): 10 requests/minute
    - General API: 100 requests/minute
    - GPS ping endpoints: 60 requests/minute
    """

    # Rate limit configs: (max_requests, window_seconds)
    RATE_LIMITS = {
        "/auth/login": (10, 60),
        "/auth/register": (5, 60),
        "/auth/forgot-password": (3, 300),
        "/auth/refresh": (20, 60),
        "/auth/sso/login": (20, 60),
        "/auth/sso/callback": (30, 60),
    }
    DEFAULT_LIMIT = (100, 60)

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks and static files
        path = request.url.path
        if path in ("/", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        # Get client identifier
        client_ip = request.client.host if request.client else "unknown"

        # Determine rate limit for this path
        max_requests, window = self.DEFAULT_LIMIT
        for prefix, limits in self.RATE_LIMITS.items():
            if path.startswith(prefix):
                max_requests, window = limits
                break

        # Check rate limit via Redis
        from ..redis_client import get_redis_client
        redis = get_redis_client()

        if redis:
            rate_key = f"rate_limit:{client_ip}:{path}"
            try:
                current = redis.incr(rate_key)
                if current == 1:
                    redis.expire(rate_key, window)
                if current and current > max_requests:
                    logger.warning(
                        "Rate limit exceeded: ip=%s path=%s count=%s limit=%s",
                        client_ip, path, current, max_requests,
                    )
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Too many requests. Please try again later."},
                        headers={"Retry-After": str(window)},
                    )
            except Exception as e:
                # Redis failure should not block requests
                logger.warning("Rate limit check failed: %s", e)

        return await call_next(request)
class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    MAX_BODY_SIZE = 1024 * 1024  # 1 MB

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")

        if content_length:
            try:
                if int(content_length) > self.MAX_BODY_SIZE:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Request body too large."},
                    )
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Invalid Content-Length header."},
                )

        return await call_next(request)