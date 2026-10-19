
"""
Tenant isolation middleware and security middleware.

SecurityHeadersMiddleware:
- Adds security headers to all responses.
- Allows required ReDoc documentation assets on documentation routes.
- Keeps a restrictive Content Security Policy on other routes.

RequestSizeLimitMiddleware:
- Limits request bodies to 1 MB.
"""

import logging

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .rate_limit import RateLimitMiddleware

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply security headers to application responses."""

    
    DOCS_CSP = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline' https:; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "connect-src 'self' https: wss:;"
    )

    DEFAULT_CSP = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data: https:; "
        "style-src 'self' 'unsafe-inline' https:; "
        "script-src 'self'; "
        "connect-src 'self' https: wss:;"
    )

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(self)"
        )

        path = request.url.path

        # Keep CDN and inline-script exceptions restricted to docs.
        if path in {"/docs", "/redoc"}:
            response.headers["Content-Security-Policy"] = self.DOCS_CSP
        else:
            response.headers["Content-Security-Policy"] = self.DEFAULT_CSP

        # Do not enable HSTS on local HTTP development.
        # Configure HSTS for production HTTPS deployments.
        #
        # response.headers["Strict-Transport-Security"] = (
        #     "max-age=31536000; includeSubDomains"
        # )

        if path.startswith("/api") or path.startswith("/auth"):
            response.headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate"
            )
            response.headers["Pragma"] = "no-cache"

        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject request bodies larger than 1 MB."""

    MAX_BODY_SIZE = 1024 * 1024

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")

        if content_length is not None:
            try:
                size = int(content_length)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={
                        "detail": "Invalid Content-Length header."
                    },
                )

            if size < 0:
                return JSONResponse(
                    status_code=400,
                    content={
                        "detail": "Invalid Content-Length header."
                    },
                )

            if size > self.MAX_BODY_SIZE:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body too large."},
                )

        return await call_next(request)
