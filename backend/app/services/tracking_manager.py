"""
app/services/tracking_manager.py
================================

WebSocket ConnectionManager for real-time GPS tracking.

This version reconciles the existing tracking/security work:

1. JWT authentication is mandatory.
2. Per-tenant connection limits are enforced.
3. Customer subscriptions are allowed only for explicitly owned jobs.
4. Technician subscriptions are restricted to their own technician/jobs.
5. Internal roles remain tenant-scoped.
6. Tenant-admin child-tenant access remains supported.
7. Redis latest-location snapshots are sent immediately on job subscription.
8. Snapshot age is calculated on the server.
9. Every socket send is serialized through a per-socket lock.
10. Slow/dead sockets are closed and cleaned up so the browser can reconnect.
11. Broadcast messages are validated against technician/job ownership.
12. Broadcast validation is cached, with short-lived invalid results.
13. Concurrent validation for the same resource shares one in-flight result.
14. Heartbeat only sends; it never reads from the socket.
15. Subscription and connection limits remain configurable.
16. Security events are persisted without blocking the WebSocket event loop.
17. Older TenantValidator.validate_channel() callers remain supported.

The main WebSocket receive loop remains in routes/tracking.py.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import jwt
import msgpack
from fastapi import WebSocket, WebSocketDisconnect  # noqa: F401

from ..database import SessionLocal
from ..logger import logger


# ============================================================================
# OPTIONAL REDIS
# ============================================================================

try:
    import redis.asyncio as redis
except ImportError:  # pragma: no cover
    redis = None


# ============================================================================
# JWT
# ============================================================================

WS_JWT_SECRET = os.getenv("JWT_SECRET")
WS_JWT_ALGORITHM = "HS256"

if not WS_JWT_SECRET:
    raise RuntimeError("JWT_SECRET must be explicitly configured")


ALLOWED_ROLES = {
    "head",
    "super_admin",
    "dispatcher",
    "technician",
    "customer",
    "tenant_admin",
}


# ============================================================================
# LIMITS
# ============================================================================

MAX_CONNECTIONS_PER_TENANT = int(
    os.getenv(
        "WS_MAX_CONNECTIONS_PER_TENANT",
        "100",
    )
)

MAX_SUBSCRIPTIONS_PER_CONNECTION = int(
    os.getenv(
        "WS_MAX_SUBSCRIPTIONS_PER_CONNECTION",
        "20",
    )
)

HEARTBEAT_INTERVAL_S = 30

# Validation cache.
BROADCAST_VALIDATION_TTL_S = 60
INVALID_VALIDATION_TTL_S = 5
VALID_CACHE_MAX_ENTRIES = 5000

# Maximum time spent waiting for a single socket send.
BROADCAST_SEND_TIMEOUT_S = float(
    os.getenv(
        "WS_SEND_TIMEOUT_S",
        "5",
    )
)

LATEST_LOCATION_TTL_S = 120

REDIS_URL = (
    os.getenv("REDIS_URL")
    or os.getenv("REDIS_ASYNC_URL")
    or "redis://localhost:6379/0"
)

GPS_LATEST_PREFIX = "gps:latest:"


# ============================================================================
# TIME HELPERS
# ============================================================================

def _as_utc(value: datetime) -> datetime:
    """
    Return a timezone-aware UTC datetime.

    Naive values are treated as UTC because persisted GPS timestamps in the
    existing system are normalized to UTC.
    """
    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def _parse_iso_utc(
    value: Any,
) -> datetime | None:
    """
    Parse a datetime or ISO-8601 value to aware UTC.
    """
    if not value:
        return None

    try:
        if isinstance(
            value,
            datetime,
        ):
            return _as_utc(value)

        return _as_utc(
            datetime.fromisoformat(
                str(value).replace(
                    "Z",
                    "+00:00",
                )
            )
        )

    except Exception:
        return None


# ============================================================================
# JWT HELPER
# ============================================================================

def decode_ws_token(
    token: str,
) -> dict[str, Any]:
    """
    Decode and validate the WebSocket JWT.
    """
    if not token:
        raise jwt.InvalidTokenError(
            "Missing WebSocket token"
        )

    return jwt.decode(
        token,
        WS_JWT_SECRET,
        algorithms=[WS_JWT_ALGORITHM],
    )


# ============================================================================
# SECURITY LOGGING
# ============================================================================

def log_security_event(
    db,
    event_type: str,
    severity: str,
    user_tenant: str | None,
    attempted_channel: str | None,
    ip_address: str | None,
    websocket_id: str | None,
    action_taken: str,
    payload_tenant: str | None = None,
    target_tenant: str | None = None,
    technician_id: str | None = None,
    job_id: str | None = None,
):
    """
    Log a security event and persist it when the audit model is available.

    Security logging must never break the live WebSocket path.
    """

    extra_fields = {
        "event": event_type,
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "severity": severity,
        "action_taken": action_taken,
    }

    optional_fields = {
        "user_tenant": user_tenant,
        "attempted_channel": attempted_channel,
        "ip_address": ip_address,
        "websocket_id": websocket_id,
        "payload_tenant": payload_tenant,
        "target_tenant": target_tenant,
        "technician_id": technician_id,
        "job_id": (
            str(job_id)
            if job_id is not None
            else None
        ),
    }

    for key, value in optional_fields.items():
        if value:
            extra_fields[key] = value

    message = (
        f"Security event: {event_type} - "
        f"{json.dumps(extra_fields)}"
    )

    if severity in {
        "critical",
        "error",
    }:
        logger.error(message)
    else:
        logger.warning(message)

    try:
        from ..models import SecurityAuditLog

        audit = SecurityAuditLog(
            id=str(uuid.uuid4()),
            event=event_type,
            severity=severity,
            user_tenant=user_tenant,
            attempted_channel=attempted_channel,
            ip_address=ip_address,
            websocket_id=websocket_id,
            action_taken=action_taken,
            payload_tenant=payload_tenant,
            target_tenant=target_tenant,
            technician_id=technician_id,
            job_id=(
                str(job_id)
                if job_id is not None
                else None
            ),
            tenant_id=(
                user_tenant
                or target_tenant
                or payload_tenant
            ),
        )

        db.add(audit)
        db.commit()

    except Exception as exc:
        logger.error(
            "Failed to save security audit log: "
            f"{exc}"
        )


# ============================================================================
# CHANNEL VALIDATION RESULT
# ============================================================================

class ValidationResult:
    def __init__(
        self,
        allowed: bool,
        code: str | None = None,
        message: str | None = None,
    ):
        self.allowed = allowed
        self.code = code
        self.message = message


# ============================================================================
# TENANT VALIDATOR
# ============================================================================

class TenantValidator:
    """
    Synchronous database-backed authorization validator.

    The ConnectionManager executes this validation in worker threads so
    synchronous SQLAlchemy work does not block the WebSocket event loop.
    """

    def __init__(
        self,
        db,
    ):
        self.db = db

    # ------------------------------------------------------------------------
    # PRIMARY VALIDATION
    # ------------------------------------------------------------------------

    def validate_channel_sync(
        self,
        channel: str,
        jwt_tenant_id: str,
        jwt_role: str,
        user_id: str | None = None,
    ) -> ValidationResult:
        """
        Validate a channel against JWT tenant, role and ownership.
        """

        parts = channel.split(":")

        if (
            len(parts) < 2
            or parts[0] != "tenant"
        ):
            return ValidationResult(
                False,
                "INVALID_CHANNEL_FORMAT",
                (
                    "Channel must follow format: "
                    "tenant:{tenant_id}:..."
                ),
            )

        channel_tenant_id = str(
            parts[1]
        )

        role = str(
            jwt_role or ""
        ).lower()

        authenticated_user_id = str(
            user_id or ""
        )

        # ====================================================================
        # CUSTOMER
        # ====================================================================
        #
        # Customer tracking is intentionally different from ordinary
        # same-tenant access.
        #
        # The customer can belong to customer-tenant while the actual Job
        # belongs to provider-tenant. The ServiceRequest ownership relationship
        # is the explicit authorization bridge.
        # ====================================================================

        if role == "customer":

            if (
                len(parts) != 4
                or parts[2] != "job"
                or not parts[3].isdigit()
            ):
                return ValidationResult(
                    False,
                    "RESOURCE_ACCESS_DENIED",
                    (
                        "Customers may only access "
                        "job tracking streams"
                    ),
                )

            from ..models import (
                Job,
                ServiceRequest,
            )

            job_id = int(
                parts[3]
            )

            owned = (
                self.db.query(Job.id)
                .join(
                    ServiceRequest,
                    ServiceRequest.linked_job_id
                    == Job.id,
                )
                .filter(
                    Job.id == job_id,
                    ServiceRequest.customer_user_id
                    == authenticated_user_id,
                    ServiceRequest.tenant_id
                    == jwt_tenant_id,
                )
                .first()
            )

            if not owned:
                return ValidationResult(
                    False,
                    "RESOURCE_ACCESS_DENIED",
                    (
                        "Customer is not authorized "
                        "for this job"
                    ),
                )

            actual_job_tenant = (
                self.db.query(
                    Job.tenant_id
                )
                .filter(
                    Job.id == job_id
                )
                .scalar()
            )

            if (
                str(channel_tenant_id)
                != str(actual_job_tenant)
            ):
                return ValidationResult(
                    False,
                    "INVALID_JOB_CHANNEL",
                    (
                        "Job channel does not "
                        "match the job owner"
                    ),
                )

            return ValidationResult(True)

        # ====================================================================
        # TECHNICIAN
        # ====================================================================

        if role == "technician":

            if (
                channel_tenant_id
                != str(jwt_tenant_id)
                or len(parts) != 4
            ):
                return ValidationResult(
                    False,
                    "RESOURCE_ACCESS_DENIED",
                    (
                        "Technicians may only access "
                        "their own tracking resources"
                    ),
                )

            from ..models import (
                Job,
                Technician,
            )

            numeric_user_id = (
                int(authenticated_user_id)
                if authenticated_user_id.isdigit()
                else -1
            )

            technician = (
                self.db.query(
                    Technician
                )
                .filter(
                    Technician.tenant_id
                    == jwt_tenant_id,
                    (
                        (
                            Technician.tech_id
                            == authenticated_user_id
                        )
                        | (
                            Technician.technician_id
                            == numeric_user_id
                        )
                    ),
                )
                .first()
            )

            if technician is None:
                return ValidationResult(
                    False,
                    "RESOURCE_ACCESS_DENIED",
                    (
                        "Technicians may only access "
                        "their own tracking resources"
                    ),
                )

            if parts[2] == "technician":

                allowed = parts[3] in {
                    str(
                        technician.tech_id
                    ),
                    str(
                        technician.technician_id
                    ),
                }

            elif (
                parts[2] == "job"
                and parts[3].isdigit()
            ):

                allowed = (
                    self.db.query(
                        Job.id
                    )
                    .filter(
                        Job.id
                        == int(parts[3]),
                        Job.tenant_id
                        == jwt_tenant_id,
                        Job.assigned_technician_id
                        == technician.technician_id,
                    )
                    .first()
                    is not None
                )

            else:
                allowed = False

            if not allowed:
                return ValidationResult(
                    False,
                    "RESOURCE_ACCESS_DENIED",
                    (
                        "Technicians may only access "
                        "their own tracking resources"
                    ),
                )

            return ValidationResult(True)

        # ====================================================================
        # SAME TENANT
        # ====================================================================

        if (
            channel_tenant_id
            == str(jwt_tenant_id)
        ):
            return ValidationResult(True)

        # ====================================================================
        # TENANT ADMIN -> CHILD TENANTS
        # ====================================================================

        if role == "tenant_admin":

            from ..models import Tenant

            child = (
                self.db.query(
                    Tenant
                )
                .filter(
                    Tenant.id
                    == channel_tenant_id,
                    Tenant.parent_tenant_id
                    == jwt_tenant_id,
                )
                .first()
            )

            if child:
                return ValidationResult(True)

        # ====================================================================
        # DENY CROSS-TENANT ACCESS
        # ====================================================================

        return ValidationResult(
            False,
            "CROSS_TENANT_ACCESS",
            (
                "Access denied: channel belongs "
                "to different tenant"
            ),
        )

    # ------------------------------------------------------------------------
    # BACKWARD-COMPATIBILITY WRAPPER
    # ------------------------------------------------------------------------

    async def validate_channel(
        self,
        websocket: WebSocket,
        channel: str,
        jwt_tenant_id: str,
        jwt_role: str,
        user_id: str | None = None,
    ) -> bool:
        """
        Compatibility wrapper for older callers.

        New production code uses validate_channel_sync() through the
        ConnectionManager worker-thread path. This method remains available
        so older tests/in-process callers do not break after the merge.
        """

        result = self.validate_channel_sync(
            channel=channel,
            jwt_tenant_id=jwt_tenant_id,
            jwt_role=jwt_role,
            user_id=user_id,
        )

        if not result.allowed:
            try:
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": (
                            result.code
                            or "RESOURCE_ACCESS_DENIED"
                        ),
                        "message": (
                            result.message
                            or "Access denied"
                        ),
                    }
                )
            except Exception:
                pass

        return result.allowed


# ============================================================================
# CONNECTION MANAGER
# ============================================================================

class ConnectionManager:
    """
    Manages authenticated WebSocket connections and channel subscriptions.
    """

    def __init__(
        self,
    ) -> None:

        # tenant_id -> connected WebSockets
        self.active_connections: dict[
            str,
            list[WebSocket],
        ] = {}

        # channel -> subscribed WebSockets
        self.channel_subscriptions: dict[
            str,
            set[WebSocket],
        ] = {}

        # id(websocket) -> metadata
        self.connection_metadata: dict[
            int,
            dict[str, Any],
        ] = {}

        # id(websocket) -> heartbeat task
        self._heartbeat_tasks: dict[
            int,
            asyncio.Task,
        ] = {}

        # id(websocket) -> socket send lock
        self._send_locks: dict[
            int,
            asyncio.Lock,
        ] = {}

        # (tenant, technician, job) ->
        # (expires_at, validation_result)
        self._valid_cache: dict[
            tuple[str, str, str],
            tuple[float, bool],
        ] = {}

        # (tenant, technician, job) ->
        # in-flight Future[bool]
        self._validation_inflight: dict[
            tuple[str, str, str],
            asyncio.Future,
        ] = {}

        self._redis = None

        self._total_messages_broadcast = 0
        self._total_dropped_connections = 0

        self._started_at = time.monotonic()

    # ========================================================================
    # REDIS
    # ========================================================================

    async def _get_redis(self):
        """
        Lazily create the async Redis client.
        """

        if redis is None:
            return None

        if self._redis is None:
            try:
                self._redis = redis.from_url(
                    REDIS_URL,
                    decode_responses=False,
                    health_check_interval=30,
                    socket_keepalive=True,
                )

            except Exception as exc:
                logger.error(
                    "[ws:redis] Failed to create "
                    f"Redis client: {exc}"
                )

                return None

        return self._redis

    # ========================================================================
    # SAFE SOCKET SEND
    # ========================================================================

    async def _send_json(
        self,
        websocket: WebSocket,
        message: dict,
    ) -> bool:
        """
        Send a JSON frame through the socket's serialized send queue.

        Every socket has exactly one send lock so heartbeat frames,
        subscription acknowledgements, snapshots and broadcasts cannot
        interleave.

        Returns:
            True  -> message delivered
            False -> socket could not accept the message
        """

        websocket_id = id(
            websocket
        )

        lock = self._send_locks.get(
            websocket_id
        )

        if lock is None:
            lock = asyncio.Lock()
            self._send_locks[
                websocket_id
            ] = lock

        async def do_send() -> None:
            async with lock:
                await websocket.send_json(
                    message
                )

        try:
            await asyncio.wait_for(
                do_send(),
                timeout=BROADCAST_SEND_TIMEOUT_S,
            )

            return True

        except asyncio.CancelledError:
            raise

        except Exception:
            return False

    async def _send_error(
        self,
        websocket: WebSocket,
        code: str,
        message: str,
    ) -> None:
        await self._send_json(
            websocket,
            {
                "type": "error",
                "code": code,
                "message": message,
            },
        )

    # ========================================================================
    # DEAD CONNECTION HANDLING
    # ========================================================================

    async def _drop_connection(
        self,
        websocket: WebSocket,
        code: int = 1011,
        reason: str = "connection lost",
    ) -> None:
        """
        Close and fully unregister a dead socket.

        Closing is important because browsers need an actual close event to
        trigger the frontend reconnect path.
        """

        websocket_id = id(
            websocket
        )

        meta = self.connection_metadata.get(
            websocket_id,
            {},
        )

        self._total_dropped_connections += 1

        try:
            await asyncio.wait_for(
                websocket.close(
                    code=code,
                    reason=reason,
                ),
                timeout=2,
            )
        except Exception:
            pass

        await self._cleanup_connection(
            websocket,
            str(
                meta.get(
                    "tenant_id",
                    "",
                )
            ),
        )

    # ========================================================================
    # CONNECTION / AUTHENTICATION
    # ========================================================================

    async def connect(
        self,
        websocket: WebSocket,
        token: str,
    ) -> dict | None:
        """
        Authenticate and register a WebSocket connection.
        """

        try:
            claims = decode_ws_token(
                token
            )

        except jwt.ExpiredSignatureError:

            await websocket.close(
                code=1008,
                reason="Token expired",
            )

            return None

        except jwt.PyJWTError:

            await websocket.close(
                code=1008,
                reason="Invalid token",
            )

            return None

        tenant_id = claims.get(
            "tenant_id"
        )

        user_id = (
            claims.get("user_id")
            or claims.get("sub")
        )

        role = str(
            claims.get("role")
            or ""
        ).lower()

        # All authorization-bound identity information is mandatory.
        if (
            not tenant_id
            or not user_id
            or role not in ALLOWED_ROLES
        ):
            await websocket.close(
                code=1008,
                reason=(
                    "Invalid role, tenant, "
                    "or user"
                ),
            )

            return None

        tenant_id = str(
            tenant_id
        )

        user_id = str(
            user_id
        )

        current_connections = len(
            self.active_connections.get(
                tenant_id,
                [],
            )
        )

        if (
            current_connections
            >= MAX_CONNECTIONS_PER_TENANT
        ):
            await websocket.close(
                code=1008,
                reason=(
                    "Tenant connection "
                    "limit exceeded"
                ),
            )

            return None

        await websocket.accept()

        websocket_id = id(
            websocket
        )

        self.active_connections.setdefault(
            tenant_id,
            [],
        ).append(
            websocket
        )

        self.connection_metadata[
            websocket_id
        ] = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "role": role,
            "connected_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        }

        self._send_locks[
            websocket_id
        ] = asyncio.Lock()

        self._heartbeat_tasks[
            websocket_id
        ] = asyncio.create_task(
            self._heartbeat(
                websocket,
                tenant_id,
                user_id,
            )
        )

        logger.info(
            "[ws:connect] "
            f"tenant={tenant_id} "
            f"user={user_id} "
            f"role={role} "
            f"total_tenant="
            f"{len(self.active_connections[tenant_id])}"
        )

        return claims

    # ========================================================================
    # SUBSCRIPTION HELPERS
    # ========================================================================

    def _subscription_count(
        self,
        websocket: WebSocket,
    ) -> int:
        return sum(
            websocket in subscribers
            for subscribers
            in self.channel_subscriptions.values()
        )

    def _same_connection_tenant(
        self,
        websocket_id: int,
        tenant_id: str,
    ) -> bool:
        meta = self.connection_metadata.get(
            websocket_id
        )

        if not meta:
            return False

        return str(
            meta.get(
                "tenant_id",
                "",
            )
        ) == str(
            tenant_id
        )

    # ========================================================================
    # SUBSCRIBE
    # ========================================================================

    async def subscribe(
        self,
        websocket: WebSocket,
        channel: str,
        tenant_id: str,
    ) -> bool:
        websocket_id = id(
            websocket
        )

        meta = self.connection_metadata.get(
            websocket_id
        )

        if meta is None:
            return False

        connection_tenant = str(
            meta.get(
                "tenant_id",
                "",
            )
        )

        # The connection's JWT tenant is authoritative.
        if not self._same_connection_tenant(
            websocket_id,
            tenant_id,
        ):
            await self._send_error(
                websocket,
                "CROSS_TENANT_ACCESS",
                (
                    "Access denied: "
                    "connection tenant mismatch"
                ),
            )

            return False

        already_subscribed = (
            websocket
            in self.channel_subscriptions.get(
                channel,
                (),
            )
        )

        if (
            not already_subscribed
            and self._subscription_count(
                websocket
            )
            >= MAX_SUBSCRIPTIONS_PER_CONNECTION
        ):
            await self._send_error(
                websocket,
                "SUBSCRIPTION_LIMIT",
                (
                    "Too many subscriptions "
                    "on this connection"
                ),
            )

            return False

        def validate() -> ValidationResult:
            db = SessionLocal()

            try:
                validator = TenantValidator(
                    db
                )

                return validator.validate_channel_sync(
                    channel=channel,
                    jwt_tenant_id=connection_tenant,
                    jwt_role=str(
                        meta.get(
                            "role",
                            "",
                        )
                    ),
                    user_id=str(
                        meta.get(
                            "user_id",
                            "",
                        )
                    ),
                )

            finally:
                db.close()

        result = await asyncio.to_thread(
            validate
        )

        # Validation could finish after the browser disconnected.
        if (
            websocket_id
            not in self.connection_metadata
        ):
            return False

        if not result.allowed:

            if (
                result.code
                == "CROSS_TENANT_ACCESS"
            ):
                parts = channel.split(
                    ":"
                )

                target_tenant = (
                    parts[1]
                    if (
                        len(parts) > 1
                        and parts[0] == "tenant"
                    )
                    else None
                )

                client = getattr(
                    websocket,
                    "client",
                    None,
                )

                ip_address = getattr(
                    client,
                    "host",
                    None,
                )

                await self._audit_subscription_security(
                    event_type=(
                        "cross_tenant_access_attempt"
                    ),
                    severity="warning",
                    user_tenant=connection_tenant,
                    attempted_channel=channel,
                    ip_address=ip_address,
                    websocket_id=(
                        f"ws-{websocket_id}"
                    ),
                    action_taken=(
                        "subscription_rejected"
                    ),
                    target_tenant=(
                        str(target_tenant)
                        if target_tenant
                        else None
                    ),
                )

            await self._send_error(
                websocket,
                result.code
                or "RESOURCE_ACCESS_DENIED",
                result.message
                or "Access denied",
            )

            return False

        # Register exactly once.
        self.channel_subscriptions.setdefault(
            channel,
            set(),
        ).add(
            websocket
        )

        sent = await self._send_json(
            websocket,
            {
                "type": "subscribed",
                "channel": channel,
            },
        )

        if not sent:
            await self._drop_connection(
                websocket,
                reason="send failed",
            )

            return False

        logger.info(
            "[ws:subscribe] "
            f"tenant={connection_tenant} "
            f"channel={channel}"
        )

        await self._send_latest_job_position(
            websocket,
            channel,
        )

        return True

    # ========================================================================
    # LATEST JOB POSITION
    # ========================================================================

    async def _send_latest_job_position(
        self,
        websocket: WebSocket,
        channel: str,
    ) -> None:
        """
        Send the cached latest technician location immediately for job
        subscriptions.
        """

        parts = channel.split(
            ":"
        )

        if (
            len(parts) != 4
            or parts[0] != "tenant"
            or parts[2] != "job"
        ):
            return

        tenant_id = str(
            parts[1]
        )

        job_id = str(
            parts[3]
        )

        redis_client = await self._get_redis()

        if redis_client is None:
            return

        key = (
            f"{GPS_LATEST_PREFIX}"
            f"{tenant_id}:"
            f"{job_id}"
        )

        try:
            raw = await redis_client.get(
                key
            )

            if not raw:
                return

            latest = (
                self._decode_latest_location(
                    raw
                )
            )

            if not latest:
                return

            # Defence in depth.
            latest_tenant = str(
                latest.get(
                    "tenant_id",
                    "",
                )
            )

            if latest_tenant != tenant_id:
                logger.error(
                    "[ws:latest] tenant mismatch "
                    f"for {key}; snapshot skipped"
                )

                return

            latest["type"] = (
                "position_update"
            )

            latest["source"] = (
                "latest_cache"
            )

            sent_at = _parse_iso_utc(
                latest.get(
                    "server_ts"
                )
                or latest.get(
                    "broadcast_at"
                )
            )

            if sent_at is not None:
                age_seconds = (
                    datetime.now(
                        timezone.utc
                    )
                    - sent_at
                ).total_seconds()

                latest["age_seconds"] = round(
                    max(
                        0.0,
                        age_seconds,
                    ),
                    1,
                )

            else:
                latest[
                    "age_seconds"
                ] = None

            if not await self._send_json(
                websocket,
                latest,
            ):
                await self._drop_connection(
                    websocket,
                    reason="send failed",
                )

                return

            logger.debug(
                "[ws:latest] sent latest GPS "
                f"tenant={tenant_id} "
                f"job={job_id} "
                f"age="
                f"{latest.get('age_seconds')}"
            )

        except Exception as exc:
            logger.warning(
                "[ws:latest] failed for "
                f"{key}: {exc}"
            )

    # ========================================================================
    # REDIS SNAPSHOT DECODER
    # ========================================================================

    @staticmethod
    def _decode_latest_location(
        raw: Any,
    ) -> dict | None:
        """
        Decode either MessagePack or JSON latest-location data.

        Supports both a direct location dictionary and the position-batch
        envelope used by Redis pub/sub.
        """

        if isinstance(
            raw,
            dict,
        ):
            return dict(
                raw
            )

        if isinstance(
            raw,
            str,
        ):
            try:
                data = json.loads(
                    raw
                )

                if isinstance(
                    data,
                    dict,
                ):
                    return dict(
                        data
                    )

            except Exception:
                return None

            return None

        if not isinstance(
            raw,
            bytes,
        ):
            return None

        # MessagePack first.
        try:
            data = msgpack.unpackb(
                raw,
                raw=False,
            )

            if isinstance(
                data,
                dict,
            ):
                updates = data.get(
                    "updates"
                )

                if (
                    isinstance(
                        updates,
                        list,
                    )
                    and updates
                ):
                    return dict(
                        updates[-1]
                    )

                return dict(
                    data
                )

        except Exception:
            pass

        # JSON fallback.
        try:
            data = json.loads(
                raw.decode(
                    "utf-8"
                )
            )

            if isinstance(
                data,
                dict,
            ):
                return dict(
                    data
                )

        except Exception:
            pass

        return None

    # ========================================================================
    # UNSUBSCRIBE
    # ========================================================================

    async def unsubscribe(
        self,
        websocket: WebSocket,
        channel: str,
        tenant_id: str,
    ) -> bool:
        websocket_id = id(
            websocket
        )

        meta = self.connection_metadata.get(
            websocket_id
        )

        if meta is None:
            return False

        if not self._same_connection_tenant(
            websocket_id,
            tenant_id,
        ):
            await self._send_error(
                websocket,
                "CROSS_TENANT_ACCESS",
                (
                    "Access denied: "
                    "connection tenant mismatch"
                ),
            )

            return False

        connection_tenant = str(
            meta.get(
                "tenant_id",
                "",
            )
        )

        def validate() -> ValidationResult:
            db = SessionLocal()

            try:
                validator = TenantValidator(
                    db
                )

                return validator.validate_channel_sync(
                    channel=channel,
                    jwt_tenant_id=connection_tenant,
                    jwt_role=str(
                        meta.get(
                            "role",
                            "",
                        )
                    ),
                    user_id=str(
                        meta.get(
                            "user_id",
                            "",
                        )
                    ),
                )

            finally:
                db.close()

        result = await asyncio.to_thread(
            validate
        )

        if not result.allowed:
            await self._send_error(
                websocket,
                result.code
                or "RESOURCE_ACCESS_DENIED",
                result.message
                or "Access denied",
            )

            return False

        subscribers = (
            self.channel_subscriptions.get(
                channel
            )
        )

        if subscribers:
            subscribers.discard(
                websocket
            )

            if not subscribers:
                self.channel_subscriptions.pop(
                    channel,
                    None,
                )

        sent = await self._send_json(
            websocket,
            {
                "type": "unsubscribed",
                "channel": channel,
            },
        )

        if not sent:
            await self._drop_connection(
                websocket,
                reason="send failed",
            )

            return False

        return True

    # ========================================================================
    # VALIDATION CACHE
    # ========================================================================

    def _prune_valid_cache(
        self,
        now: float,
    ) -> None:
        """
        Remove expired entries and keep the cache bounded.
        """

        expired_keys = [
            key
            for key, (
                expires_at,
                _,
            ) in self._valid_cache.items()
            if expires_at <= now
        ]

        for key in expired_keys:
            self._valid_cache.pop(
                key,
                None,
            )

        if (
            len(self._valid_cache)
            < VALID_CACHE_MAX_ENTRIES
        ):
            return

        # Keep the entries with the longest remaining TTL. This avoids an
        # unbounded dictionary while preserving currently useful validations.
        live_entries = [
            (
                key,
                value,
            )
            for key, value
            in self._valid_cache.items()
            if value[0] > now
        ]

        live_entries.sort(
            key=lambda item: item[1][0]
        )

        keep_count = max(
            0,
            VALID_CACHE_MAX_ENTRIES - 1,
        )

        self._valid_cache = dict(
            live_entries[
                -keep_count:
            ]
            if keep_count
            else []
        )

    # ========================================================================
    # SUBSCRIPTION SECURITY AUDIT
    # ========================================================================

    async def _audit_subscription_security(
        self,
        *,
        event_type: str,
        severity: str,
        user_tenant: str | None,
        attempted_channel: str | None,
        ip_address: str | None,
        websocket_id: str | None,
        action_taken: str,
        target_tenant: str | None = None,
    ) -> None:
        """
        Persist subscription security events off the event loop.
        """

        def write() -> None:
            db = SessionLocal()

            try:
                log_security_event(
                    db=db,
                    event_type=event_type,
                    severity=severity,
                    user_tenant=user_tenant,
                    attempted_channel=attempted_channel,
                    ip_address=ip_address,
                    websocket_id=websocket_id,
                    action_taken=action_taken,
                    target_tenant=target_tenant,
                )

            except Exception as exc:
                logger.error(
                    "[ws:audit] subscription "
                    f"audit failed: {exc}"
                )

            finally:
                db.close()

        try:
            await asyncio.to_thread(
                write
            )

        except Exception as exc:
            logger.error(
                "[ws:audit] subscription audit "
                f"task failed: {exc}"
            )

    # ========================================================================
    # BROADCAST SECURITY AUDIT
    # ========================================================================

    async def _audit_broadcast_security(
        self,
        *,
        event_type: str,
        severity: str,
        payload_tenant: str | None,
        target_tenant: str | None,
        technician_id: str | None = None,
        job_id: str | None = None,
    ) -> None:
        """
        Persist broadcast security events off the event loop.
        """

        def write() -> None:
            db = SessionLocal()

            try:
                log_security_event(
                    db=db,
                    event_type=event_type,
                    severity=severity,
                    user_tenant=None,
                    attempted_channel=None,
                    ip_address=None,
                    websocket_id=None,
                    action_taken="message_dropped",
                    payload_tenant=payload_tenant,
                    target_tenant=target_tenant,
                    technician_id=technician_id,
                    job_id=job_id,
                )

            except Exception as exc:
                logger.error(
                    "[ws:audit] broadcast security "
                    f"log failed: {exc}"
                )

            finally:
                db.close()

        try:
            await asyncio.to_thread(
                write
            )

        except Exception as exc:
            logger.error(
                "[ws:audit] broadcast security "
                f"task failed: {exc}"
            )

    # ========================================================================
    # BROADCAST VALIDATION
    # ========================================================================

    async def _validate_broadcast(
        self,
        channel: str,
        message: dict,
    ) -> bool:
        """
        Validate that a broadcast's tenant, technician and job agree with
        persisted database ownership.

        This protects the cross-instance Redis -> local WebSocket path.
        """

        parts = channel.split(
            ":"
        )

        target_tenant_id = (
            parts[1]
            if (
                len(parts) > 1
                and parts[0] == "tenant"
            )
            else None
        )

        # Non-standard channels are not used by the GPS listener.
        if not target_tenant_id:
            return True

        payload_tenant = message.get(
            "tenant_id"
        )

        if not payload_tenant:
            logger.error(
                "[ws:broadcast] Missing tenant_id"
            )

            await self._audit_broadcast_security(
                event_type=(
                    "broadcast_missing_tenant"
                ),
                severity="critical",
                payload_tenant=None,
                target_tenant=str(
                    target_tenant_id
                ),
            )

            return False

        payload_tenant = str(
            payload_tenant
        )

        if (
            payload_tenant
            != str(target_tenant_id)
        ):
            logger.error(
                "[ws:broadcast] Tenant mismatch "
                f"payload={payload_tenant} "
                f"channel={target_tenant_id}"
            )

            await self._audit_broadcast_security(
                event_type=(
                    "broadcast_tenant_mismatch"
                ),
                severity="critical",
                payload_tenant=payload_tenant,
                target_tenant=str(
                    target_tenant_id
                ),
            )

            return False

        technician_id = str(
            message.get(
                "technician_id",
                "",
            )
        )

        job_id = str(
            message.get(
                "job_id",
                "",
            )
        )

        cache_key = (
            str(target_tenant_id),
            technician_id,
            job_id,
        )

        now = time.monotonic()

        cached = self._valid_cache.get(
            cache_key
        )

        if cached is not None:
            expires_at, valid = cached

            if now < expires_at:
                return valid

            self._valid_cache.pop(
                cache_key,
                None,
            )

        # Another broadcast can already be validating the same resource.
        inflight = (
            self._validation_inflight.get(
                cache_key
            )
        )

        if inflight is not None:
            try:
                return await inflight
            except asyncio.CancelledError:
                raise
            except Exception:
                return False

        loop = asyncio.get_running_loop()

        future: asyncio.Future = (
            loop.create_future()
        )

        self._validation_inflight[
            cache_key
        ] = future

        validation_result = (
            "resource_mismatch"
        )

        valid = False
        cacheable = True

        def validate_db() -> str:
            db = SessionLocal()

            try:
                from ..models import (
                    Job,
                    Technician,
                )

                # ------------------------------------------------------------
                # Technician lookup
                # ------------------------------------------------------------

                technician_query = (
                    db.query(
                        Technician
                    )
                    .filter(
                        Technician.tenant_id
                        == payload_tenant
                    )
                )

                if technician_id.isdigit():
                    numeric_id = int(
                        technician_id
                    )

                    technician_query = (
                        technician_query.filter(
                            (
                                Technician.tech_id
                                == technician_id
                            )
                            | (
                                Technician.technician_id
                                == numeric_id
                            )
                        )
                    )

                else:
                    technician_query = (
                        technician_query.filter(
                            Technician.tech_id
                            == technician_id
                        )
                    )

                technician = (
                    technician_query.first()
                )

                if technician is None:
                    return (
                        "technician_mismatch"
                    )

                # ------------------------------------------------------------
                # Job lookup
                # ------------------------------------------------------------

                if not job_id.isdigit():
                    return "job_mismatch"

                job = (
                    db.query(
                        Job
                    )
                    .filter(
                        Job.id
                        == int(job_id),
                        Job.tenant_id
                        == payload_tenant,
                    )
                    .first()
                )

                if job is None:
                    return "job_mismatch"

                # ------------------------------------------------------------
                # Assignment lookup
                # ------------------------------------------------------------

                if (
                    job.assigned_technician_id
                    != technician.technician_id
                ):
                    return (
                        "assignment_mismatch"
                    )

                return "valid"

            finally:
                db.close()

        try:
            validation_result = (
                await asyncio.to_thread(
                    validate_db
                )
            )

            valid = (
                validation_result
                == "valid"
            )

        except Exception as exc:
            # DB outage must not be cached as "invalid".
            cacheable = False

            logger.error(
                "[ws:broadcast] validation failed "
                f"for {cache_key}: {exc}"
            )

        finally:
            self._validation_inflight.pop(
                cache_key,
                None,
            )

            if not future.done():
                future.set_result(
                    valid
                )

        # Audit an invalid but successfully evaluated resource.
        if (
            not valid
            and cacheable
        ):
            event_type = {
                "technician_mismatch": (
                    "broadcast_technician_tenant_mismatch"
                ),
                "job_mismatch": (
                    "broadcast_job_tenant_mismatch"
                ),
                "assignment_mismatch": (
                    "broadcast_job_assignment_mismatch"
                ),
            }.get(
                validation_result,
                "broadcast_resource_mismatch",
            )

            await self._audit_broadcast_security(
                event_type=event_type,
                severity="critical",
                payload_tenant=str(
                    payload_tenant
                ),
                target_tenant=str(
                    target_tenant_id
                ),
                technician_id=(
                    technician_id
                    or None
                ),
                job_id=(
                    job_id
                    or None
                ),
            )

        if cacheable:
            self._prune_valid_cache(
                now
            )

            ttl = (
                BROADCAST_VALIDATION_TTL_S
                if valid
                else INVALID_VALIDATION_TTL_S
            )

            self._valid_cache[
                cache_key
            ] = (
                time.monotonic()
                + ttl,
                valid,
            )

        return valid

    # ========================================================================
    # BROADCAST
    # ========================================================================

    async def broadcast(
        self,
        channel: str,
        message: dict,
    ) -> int:
        """
        Broadcast a validated message to all local subscribers.
        """

        subscribers = (
            self.channel_subscriptions.get(
                channel
            )
        )

        if not subscribers:
            return 0

        # Validate before copying the subscriber list.
        if not await self._validate_broadcast(
            channel,
            message,
        ):
            return 0

        # Subscribers can change while DB validation runs.
        sockets = list(
            self.channel_subscriptions.get(
                channel,
                (),
            )
        )

        if not sockets:
            return 0

        outcomes = await asyncio.gather(
            *(
                self._send_json(
                    websocket,
                    message,
                )
                for websocket in sockets
            )
        )

        stale: list[
            WebSocket
        ] = []

        sent = 0

        for websocket, success in zip(
            sockets,
            outcomes,
        ):
            if success:
                sent += 1

                self._total_messages_broadcast += 1

            else:
                stale.append(
                    websocket
                )

        # Failed sockets are explicitly closed so the browser reconnects.
        if stale:
            logger.warning(
                "[ws:broadcast] dropping "
                f"{len(stale)} unresponsive "
                f"socket(s) on channel={channel}"
            )

            await asyncio.gather(
                *(
                    self._drop_connection(
                        websocket,
                        reason="send failed",
                    )
                    for websocket
                    in stale
                ),
                return_exceptions=True,
            )

        return sent

    # ========================================================================
    # DISCONNECT
    # ========================================================================

    async def disconnect(
        self,
        websocket: WebSocket,
        tenant_id: str,
    ) -> None:
        """
        Public idempotent disconnect entry point.
        """

        await self._cleanup_connection(
            websocket,
            tenant_id,
        )

    # ========================================================================
    # CLEANUP
    # ========================================================================

    async def _cleanup_connection(
        self,
        websocket: WebSocket,
        tenant_id: str,
    ) -> None:
        """
        Fully remove a socket from every manager registry.
        """

        websocket_id = id(
            websocket
        )

        was_registered = (
            websocket_id
            in self.connection_metadata
        )

        if not tenant_id:
            tenant_id = str(
                self.connection_metadata.get(
                    websocket_id,
                    {},
                ).get(
                    "tenant_id",
                    "",
                )
            )

        # --------------------------------------------------------------------
        # Cancel heartbeat
        # --------------------------------------------------------------------

        heartbeat_task = (
            self._heartbeat_tasks.pop(
                websocket_id,
                None,
            )
        )

        if heartbeat_task is not None:

            current_task = (
                asyncio.current_task()
            )

            if (
                heartbeat_task
                is not current_task
            ):

                heartbeat_task.cancel()

                try:
                    await heartbeat_task

                except asyncio.CancelledError:
                    pass

                except Exception:
                    pass

        # --------------------------------------------------------------------
        # Remove tenant connection
        # --------------------------------------------------------------------

        tenant_connections = (
            self.active_connections.get(
                tenant_id
            )
        )

        if tenant_connections:

            try:
                tenant_connections.remove(
                    websocket
                )

            except ValueError:
                pass

            if not tenant_connections:
                self.active_connections.pop(
                    tenant_id,
                    None,
                )

        # --------------------------------------------------------------------
        # Remove subscriptions
        # --------------------------------------------------------------------

        empty_channels: list[
            str
        ] = []

        for (
            channel,
            subscribers,
        ) in list(
            self.channel_subscriptions.items()
        ):

            subscribers.discard(
                websocket
            )

            if not subscribers:
                empty_channels.append(
                    channel
                )

        for channel in empty_channels:
            self.channel_subscriptions.pop(
                channel,
                None,
            )

        # --------------------------------------------------------------------
        # Remove metadata and send lock
        # --------------------------------------------------------------------

        self.connection_metadata.pop(
            websocket_id,
            None,
        )

        self._send_locks.pop(
            websocket_id,
            None,
        )

        if was_registered:
            logger.info(
                "[ws:disconnect] "
                f"tenant={tenant_id}"
            )

    # ========================================================================
    # HEARTBEAT
    # ========================================================================

    async def _heartbeat(
        self,
        websocket: WebSocket,
        tenant_id: str,
        user_id: str,
    ) -> None:
        """
        Send application heartbeat pings.

        This method NEVER reads from the WebSocket.

        routes/tracking.py remains the only receive_json() loop.
        """

        try:

            while True:

                await asyncio.sleep(
                    HEARTBEAT_INTERVAL_S
                )

                ping_timestamp = (
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                )

                delivered = await self._send_json(
                    websocket,
                    {
                        "type": "ping",
                        "timestamp": (
                            ping_timestamp
                        ),
                    },
                )

                if not delivered:

                    logger.warning(
                        "[ws:heartbeat] ping failed "
                        f"user={user_id}; closing socket"
                    )

                    await self._drop_connection(
                        websocket,
                        reason="heartbeat failed",
                    )

                    return

        except asyncio.CancelledError:
            return

        except Exception as exc:
            logger.warning(
                "[ws:heartbeat] stopped "
                f"user={user_id} "
                f"tenant={tenant_id}: {exc}"
            )

    # ========================================================================
    # METRICS
    # ========================================================================

    def get_metrics(
        self,
    ) -> dict:
        """
        Return connection/broadcast metrics.
        """

        active_by_tenant = {
            tenant: len(sockets)
            for (
                tenant,
                sockets,
            )
            in self.active_connections.items()
        }

        return {
            "active_connections_by_tenant": (
                active_by_tenant
            ),
            "total_active_connections": (
                sum(
                    active_by_tenant.values()
                )
            ),
            "total_messages_broadcast": (
                self._total_messages_broadcast
            ),
            "total_dropped_connections": (
                self._total_dropped_connections
            ),
            "uptime_seconds": round(
                (
                    time.monotonic()
                    - self._started_at
                ),
                1,
            ),
            "validation_cache_entries": (
                len(
                    self._valid_cache
                )
            ),
            "subscriptions": (
                len(
                    self.channel_subscriptions
                )
            ),
            "send_timeout_s": (
                BROADCAST_SEND_TIMEOUT_S
            ),
            "heartbeat_interval_s": (
                HEARTBEAT_INTERVAL_S
            ),
            "max_connections_per_tenant": (
                MAX_CONNECTIONS_PER_TENANT
            ),
            "max_subscriptions_per_connection": (
                MAX_SUBSCRIPTIONS_PER_CONNECTION
            ),
        }


# ============================================================================
# SINGLETON
# ============================================================================

connection_manager = ConnectionManager()