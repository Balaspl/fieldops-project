"""
app/services/tracking_manager.py
────────────────────────────────

WebSocket ConnectionManager for real-time GPS tracking.

Changes in this version
───────────────────────
1. DEAD SOCKETS ARE CLOSED, NOT SILENTLY UNSUBSCRIBED.
   Previously, when one send timed out or failed, the socket was removed from
   every channel (and its heartbeat cancelled) but the WebSocket itself stayed
   open. The customer looked connected but never received another update.
   Now a failed send / failed heartbeat closes the socket (code 1011), so the
   browser gets `onclose`, reconnects and re-subscribes.
2. PER-SOCKET SEND LOCK. Broadcasts, heartbeat pings, subscribe acks and the
   latest-position snapshot can run concurrently for the same socket. All
   sends now go through one helper that serialises them and applies a timeout.
3. SNAPSHOT AGE. The "latest position" snapshot sent on subscribe now carries
   `age_seconds` (computed on the server from `server_ts` / `broadcast_at`),
   so the frontend can show "Last known location · N s ago" instead of
   treating an old cached point as a live fix.
4. BROADCAST VALIDATION CACHE: expired entries are pruned, invalid results are
   cached only briefly, DB errors are not cached, and concurrent validations
   for the same (tenant, technician, job) share one DB query.
5. Redundant customer-channel branch removed; subscribe() refuses sockets
   that disconnected during validation; per-connection subscription cap;
   connection cap and send timeout are configurable through environment
   variables.

Existing behaviour that is intentionally unchanged:
    • Single WebSocket receive loop (in routes/tracking.py)
    • Heartbeat never calls receive_json()
    • Latest technician GPS sent immediately on job subscription
    • Redis latest-location cache
    • DB validation runs off the async event loop
    • Multi-tenant authorization rules

Environment variables (all optional)
    WS_MAX_CONNECTIONS_PER_TENANT        default 100
    WS_SEND_TIMEOUT_S                    default 5
    WS_MAX_SUBSCRIPTIONS_PER_CONNECTION  default 20
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
from fastapi import WebSocket, WebSocketDisconnect  # noqa: F401 (kept for importers)

from ..database import SessionLocal
from ..logger import logger


# ============================================================================
# OPTIONAL REDIS
# ============================================================================

try:
    import redis.asyncio as redis
except ImportError:
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
    os.getenv("WS_MAX_CONNECTIONS_PER_TENANT", "100")
)

MAX_SUBSCRIPTIONS_PER_CONNECTION = int(
    os.getenv("WS_MAX_SUBSCRIPTIONS_PER_CONNECTION", "20")
)

HEARTBEAT_INTERVAL_S = 30

# IMPORTANT:
#
# We DO NOT call websocket.receive_json() from the heartbeat.
#
# The main websocket endpoint in tracking.py is the only coroutine allowed
# to receive messages.


# ============================================================================
# BROADCAST CACHE / SEND LIMITS
# ============================================================================

BROADCAST_VALIDATION_TTL_S = 60

# A failed validation (unknown job/technician) is cached only briefly so a job
# that was just created is not blocked for a full minute.
INVALID_VALIDATION_TTL_S = 5

VALID_CACHE_MAX_ENTRIES = 5000

# A client that cannot accept a message within this time is treated as dead
# and its socket is closed so it reconnects cleanly.
BROADCAST_SEND_TIMEOUT_S = float(
    os.getenv("WS_SEND_TIMEOUT_S", "5")
)

LATEST_LOCATION_TTL_S = 120


# ============================================================================
# REDIS CONFIG
# ============================================================================

REDIS_URL = (
    os.getenv("REDIS_URL")
    or os.getenv("REDIS_ASYNC_URL")
    or "redis://localhost:6379/0"
)

GPS_LATEST_PREFIX = "gps:latest:"


# ============================================================================
# TIME HELPERS (local so this file has no new import dependencies)
# ============================================================================

def _as_utc(dt: datetime) -> datetime:
    """Return a timezone-aware UTC datetime (naive values are assumed UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _parse_iso_utc(value: Any) -> datetime | None:
    """Parse an ISO-8601 string / datetime into aware UTC, or None."""
    if not value:
        return None

    try:
        if isinstance(value, datetime):
            return _as_utc(value)

        return _as_utc(
            datetime.fromisoformat(
                str(value).replace("Z", "+00:00")
            )
        )
    except Exception:
        return None


# ============================================================================
# JWT HELPER
# ============================================================================

def decode_ws_token(token: str) -> dict[str, Any]:
    """
    Decode and validate WebSocket JWT token.
    """

    if not token:
        raise jwt.InvalidTokenError("Missing WebSocket token")

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
    extra_fields = {
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": severity,
        "action_taken": action_taken,
    }

    if user_tenant:
        extra_fields["user_tenant"] = user_tenant

    if attempted_channel:
        extra_fields["attempted_channel"] = attempted_channel

    if ip_address:
        extra_fields["ip_address"] = ip_address

    if websocket_id:
        extra_fields["websocket_id"] = websocket_id

    if payload_tenant:
        extra_fields["payload_tenant"] = payload_tenant

    if target_tenant:
        extra_fields["target_tenant"] = target_tenant

    if technician_id:
        extra_fields["technician_id"] = technician_id

    if job_id:
        extra_fields["job_id"] = str(job_id)

    if severity in {"critical", "error"}:
        logger.error(
            f"Security event: {event_type} - "
            f"{json.dumps(extra_fields)}"
        )
    else:
        logger.warning(
            f"Security event: {event_type} - "
            f"{json.dumps(extra_fields)}"
        )

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
            job_id=str(job_id) if job_id is not None else None,
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
            f"Failed to save security audit log: {exc}"
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
    Authorization validator.

    DB work is performed synchronously inside worker threads by the
    ConnectionManager so the FastAPI event loop is not blocked.
    """

    def __init__(self, db):
        self.db = db

    # ------------------------------------------------------------------------
    # SYNC VALIDATION
    # ------------------------------------------------------------------------

    def validate_channel_sync(
        self,
        channel: str,
        jwt_tenant_id: str,
        jwt_role: str,
        user_id: str | None = None,
    ) -> ValidationResult:

        parts = channel.split(":")

        if (
            len(parts) < 2
            or parts[0] != "tenant"
        ):
            return ValidationResult(
                False,
                "INVALID_CHANNEL_FORMAT",
                "Channel must follow format: tenant:{tenant_id}:...",
            )

        channel_tenant_id = parts[1]

        # ====================================================================
        # CUSTOMER
        #
        # Customers may only subscribe to tenant:{job_tenant}:job:{job_id}
        # for a job that belongs to one of their own service requests.
        # ====================================================================

        if jwt_role == "customer":

            if (
                len(parts) != 4
                or parts[2] != "job"
                or not parts[3].isdigit()
            ):
                return ValidationResult(
                    False,
                    "RESOURCE_ACCESS_DENIED",
                    "Customers may only access job tracking streams",
                )

            from ..models import Job, ServiceRequest

            job_id = int(parts[3])

            owned = (
                self.db.query(Job.id)
                .join(
                    ServiceRequest,
                    ServiceRequest.linked_job_id == Job.id,
                )
                .filter(
                    Job.id == job_id,
                    ServiceRequest.customer_user_id == str(user_id),
                    ServiceRequest.tenant_id == jwt_tenant_id,
                )
                .first()
            )

            if not owned:
                return ValidationResult(
                    False,
                    "RESOURCE_ACCESS_DENIED",
                    "Customer is not authorized for this job",
                )

            actual_job_tenant = (
                self.db.query(Job.tenant_id)
                .filter(
                    Job.id == job_id
                )
                .scalar()
            )

            if channel_tenant_id != actual_job_tenant:
                return ValidationResult(
                    False,
                    "INVALID_JOB_CHANNEL",
                    "Job channel does not match the job owner",
                )

            return ValidationResult(True)

        # ====================================================================
        # TECHNICIAN
        # ====================================================================

        if jwt_role == "technician":

            user_id = str(user_id or "")

            if (
                channel_tenant_id != jwt_tenant_id
                or len(parts) != 4
            ):
                return ValidationResult(
                    False,
                    "RESOURCE_ACCESS_DENIED",
                    "Technicians may only access their own tracking resources",
                )

            from ..models import Technician, Job

            numeric_user_id = (
                int(user_id)
                if user_id.isdigit()
                else -1
            )

            technician = (
                self.db.query(Technician)
                .filter(
                    Technician.tenant_id == jwt_tenant_id,
                    (
                        (Technician.tech_id == user_id)
                        | (
                            Technician.technician_id
                            == numeric_user_id
                        )
                    ),
                )
                .first()
            )

            authorized = False

            if (
                technician
                and parts[2] == "technician"
            ):
                authorized = (
                    parts[3]
                    in {
                        str(technician.tech_id),
                        str(technician.technician_id),
                    }
                )

            elif (
                technician
                and parts[2] == "job"
                and parts[3].isdigit()
            ):
                authorized = (
                    self.db.query(Job.id)
                    .filter(
                        Job.id == int(parts[3]),
                        Job.tenant_id == jwt_tenant_id,
                        Job.assigned_technician_id
                        == technician.technician_id,
                    )
                    .first()
                    is not None
                )

            if not authorized:
                return ValidationResult(
                    False,
                    "RESOURCE_ACCESS_DENIED",
                    "Technicians may only access their own tracking resources",
                )

            return ValidationResult(True)

        # ====================================================================
        # SAME TENANT
        # ====================================================================

        if channel_tenant_id == jwt_tenant_id:
            return ValidationResult(True)

        # ====================================================================
        # TENANT ADMIN
        # ====================================================================

        if jwt_role == "tenant_admin":

            from ..models import Tenant

            child = (
                self.db.query(Tenant)
                .filter(
                    Tenant.id == channel_tenant_id,
                    Tenant.parent_tenant_id == jwt_tenant_id,
                )
                .first()
            )

            if child:
                return ValidationResult(True)

        return ValidationResult(
            False,
            "CROSS_TENANT_ACCESS",
            "Access denied: channel belongs to different tenant",
        )


# ============================================================================
# CONNECTION MANAGER
# ============================================================================

class ConnectionManager:

    def __init__(self) -> None:

        # tenant_id -> list[WebSocket]
        self.active_connections: dict[
            str,
            list[WebSocket],
        ] = {}

        # channel -> set[WebSocket]
        self.channel_subscriptions: dict[
            str,
            set[WebSocket],
        ] = {}

        # websocket -> metadata
        self.connection_metadata: dict[
            int,
            dict,
        ] = {}

        # websocket -> heartbeat task
        self._heartbeat_tasks: dict[
            int,
            asyncio.Task,
        ] = {}

        # websocket -> send lock (serialises every send to one socket)
        self._send_locks: dict[
            int,
            asyncio.Lock,
        ] = {}

        # broadcast validation cache
        #
        # key:   (tenant, technician, job)
        # value: (expires_at, valid)
        self._valid_cache: dict[
            tuple[str, str, str],
            tuple[float, bool],
        ] = {}

        # in-flight validations, so concurrent broadcasts for the same
        # (tenant, technician, job) share a single DB query
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
        Lazily create a Redis async client.

        Redis is used only for latest GPS lookup here.
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
                    f"[ws:redis] Failed to create Redis client: {exc}"
                )
                return None

        return self._redis

    # ========================================================================
    # SAFE SEND (the ONLY place that writes to a client socket)
    # ========================================================================

    async def _send_json(
        self,
        websocket: WebSocket,
        message: dict,
    ) -> bool:
        """
        Send one JSON message to one client.

        • Serialised per socket (no interleaved concurrent sends).
        • Bounded by BROADCAST_SEND_TIMEOUT_S (includes waiting for the lock).
        • Never raises. Returns True on success, False on any failure.

        A False result means the client cannot receive data reliably; callers
        should treat the socket as dead (see _drop_connection()).
        """

        lock = self._send_locks.get(id(websocket))

        if lock is None:
            return False

        async def _do_send() -> None:
            async with lock:
                await websocket.send_json(message)

        try:
            await asyncio.wait_for(
                _do_send(),
                timeout=BROADCAST_SEND_TIMEOUT_S,
            )
            return True

        except Exception:
            # Includes asyncio.TimeoutError, RuntimeError (socket closed),
            # and transport errors. CancelledError is NOT swallowed.
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
    # DROP DEAD CONNECTION
    # ========================================================================

    async def _drop_connection(
        self,
        websocket: WebSocket,
        code: int = 1011,
        reason: str = "connection lost",
    ) -> None:
        """
        Close a socket that can no longer receive messages and remove it from
        all registries.

        Closing the socket matters: the browser then fires `onclose`, opens a
        new connection and subscribes again. Removing the socket from the
        registries WITHOUT closing it (the old behaviour) left the client
        connected but permanently unsubscribed.
        """

        meta = self.connection_metadata.get(
            id(websocket),
            {},
        )

        tenant_id = meta.get("tenant_id", "")

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
            tenant_id,
        )

    # ========================================================================
    # AUTHENTICATION
    # ========================================================================

    async def connect(
        self,
        websocket: WebSocket,
        token: str,
    ) -> dict | None:

        try:
            claims = decode_ws_token(token)

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

        tenant_id = claims.get("tenant_id")
        user_id = claims.get("user_id") or claims.get('sub')
        role = claims.get("role")

        if (
            not tenant_id
            or role not in ALLOWED_ROLES
        ):
            await websocket.close(
                code=1008,
                reason="Invalid role or tenant",
            )

            return None

        if (
            len(
                self.active_connections.get(
                    tenant_id,
                    [],
                )
            )
            >= MAX_CONNECTIONS_PER_TENANT
        ):
            await websocket.close(
                code=1008,
                reason="Tenant connection limit exceeded",
            )

            return None

        await websocket.accept()

        websocket_key = id(websocket)

        self.active_connections.setdefault(
            tenant_id,
            [],
        ).append(websocket)

        self.connection_metadata[
            websocket_key
        ] = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "role": role,
            "connected_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        self._send_locks[
            websocket_key
        ] = asyncio.Lock()

        logger.info(
            f"[ws:connect] tenant={tenant_id} "
            f"user={user_id} "
            f"role={role} "
            f"total_tenant="
            f"{len(self.active_connections[tenant_id])}"
        )

        # Start heartbeat.
        #
        # IMPORTANT:
        # _heartbeat NEVER calls receive_json().
        self._heartbeat_tasks[
            websocket_key
        ] = asyncio.create_task(
            self._heartbeat(
                websocket,
                tenant_id,
                str(user_id or ""),
            )
        )

        return claims

    # ========================================================================
    # SUBSCRIBE
    # ========================================================================

    async def subscribe(
        self,
        websocket: WebSocket,
        channel: str,
        tenant_id: str,
    ) -> bool:

        websocket_key = id(websocket)

        meta = self.connection_metadata.get(
            websocket_key
        )

        if meta is None:
            # Socket is not registered (already dropped / disconnected).
            return False

        jwt_role = meta.get("role")

        user_id = meta.get("user_id") or meta.get("sub")

        print("========== WS SUBSCRIBE DEBUG ==========")
        print("role:", jwt_role)
        print("user_id:", user_id)
        print("sub:", meta.get("sub"))
        print("meta:", meta)
        print("channel:", channel)
        print("tenant_id:", tenant_id)
        print("========================================")

        # --------------------------------------------------------------------
        # Per-connection subscription cap.
        # --------------------------------------------------------------------

        already_subscribed = websocket in self.channel_subscriptions.get(
            channel,
            (),
        )

        if not already_subscribed:

            current_count = sum(
                1
                for subscribers in self.channel_subscriptions.values()
                if websocket in subscribers
            )

            if current_count >= MAX_SUBSCRIPTIONS_PER_CONNECTION:

                await self._send_error(
                    websocket,
                    "SUBSCRIPTION_LIMIT",
                    "Too many subscriptions on this connection",
                )

                return False

        # --------------------------------------------------------------------
        # Validate in worker thread.
        # --------------------------------------------------------------------

        def validate():

            db = SessionLocal()

            try:
                validator = TenantValidator(db)

                return validator.validate_channel_sync(
                    channel=channel,
                    jwt_tenant_id=tenant_id,
                    jwt_role=jwt_role,
                    user_id=user_id,
                )

            finally:
                db.close()

        result = await asyncio.to_thread(
            validate
        )

        # The client may have disconnected while we were validating.
        if websocket_key not in self.connection_metadata:
            return False

        if not result.allowed:

            await self._send_error(
                websocket,
                result.code
                or "RESOURCE_ACCESS_DENIED",
                result.message
                or "Access denied",
            )

            return False

        # --------------------------------------------------------------------
        # Register subscription.
        # --------------------------------------------------------------------

        self.channel_subscriptions.setdefault(
            channel,
            set(),
        ).add(websocket)

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
            f"[ws:subscribe] channel={channel}"
        )

        # --------------------------------------------------------------------
        # Send the latest technician position immediately, so the customer
        # does not wait for the next GPS ping.
        # --------------------------------------------------------------------

        await self._send_latest_job_position(
            websocket,
            channel,
        )

        return True

    # ========================================================================
    # SEND LATEST JOB POSITION
    # ========================================================================

    async def _send_latest_job_position(
        self,
        websocket: WebSocket,
        channel: str,
    ) -> None:

        parts = channel.split(":")

        if (
            len(parts) != 4
            or parts[0] != "tenant"
            or parts[2] != "job"
        ):
            return

        tenant_id = parts[1]
        job_id = parts[3]

        redis_client = await self._get_redis()

        if redis_client is None:
            return

        key = (
            f"{GPS_LATEST_PREFIX}"
            f"{tenant_id}:"
            f"{job_id}"
        )

        try:

            raw = await redis_client.get(key)

            if not raw:
                return

            latest = self._decode_latest_location(raw)

            if not latest:
                return

            # Defence in depth: never deliver a cached point that belongs
            # to another tenant.
            if str(latest.get("tenant_id", tenant_id)) != tenant_id:
                logger.error(
                    f"[ws:latest] tenant mismatch for {key}; snapshot skipped"
                )
                return

            # Tell the frontend this is a cached position and HOW OLD it is.
            # Age is computed on the server, so it does not depend on the
            # client's clock or on the technician device's clock.
            latest["type"] = "position_update"
            latest["source"] = "latest_cache"

            sent_at = _parse_iso_utc(
                latest.get("server_ts")
                or latest.get("broadcast_at")
            )

            if sent_at is not None:
                latest["age_seconds"] = round(
                    max(
                        0.0,
                        (
                            datetime.now(timezone.utc)
                            - sent_at
                        ).total_seconds(),
                    ),
                    1,
                )
            else:
                latest["age_seconds"] = None

            delivered = await self._send_json(
                websocket,
                latest,
            )

            if not delivered:
                await self._drop_connection(
                    websocket,
                    reason="send failed",
                )
                return

            logger.debug(
                f"[ws:latest] sent latest GPS "
                f"tenant={tenant_id} "
                f"job={job_id} "
                f"age={latest.get('age_seconds')}"
            )

        except Exception as exc:

            logger.warning(
                f"[ws:latest] failed to send latest "
                f"location for {key}: {exc}"
            )

    # ========================================================================
    # DECODE REDIS LOCATION
    # ========================================================================

    @staticmethod
    def _decode_latest_location(
        raw: Any,
    ) -> dict | None:

        try:

            if isinstance(raw, bytes):

                # Try MessagePack first.
                try:
                    data = msgpack.unpackb(
                        raw,
                        raw=False,
                    )

                    if isinstance(data, dict):

                        # Redis may contain an envelope.
                        if "updates" in data:
                            updates = data.get(
                                "updates"
                            )

                            if updates:
                                return dict(
                                    updates[-1]
                                )

                        return dict(data)

                except Exception:
                    pass

                # Then JSON.
                try:
                    decoded = raw.decode(
                        "utf-8"
                    )

                    data = json.loads(
                        decoded
                    )

                    if isinstance(data, dict):
                        return data

                except Exception:
                    pass

            if isinstance(raw, str):

                data = json.loads(raw)

                if isinstance(data, dict):
                    return data

            if isinstance(raw, dict):
                return dict(raw)

        except Exception as exc:

            logger.warning(
                f"[ws:latest] decode failed: {exc}"
            )

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

        meta = self.connection_metadata.get(
            id(websocket)
        )

        if meta is None:
            return False

        jwt_role = meta.get("role")

        user_id = meta.get("user_id")

        def validate():

            db = SessionLocal()

            try:
                validator = TenantValidator(db)

                return validator.validate_channel_sync(
                    channel=channel,
                    jwt_tenant_id=tenant_id,
                    jwt_role=jwt_role,
                    user_id=user_id,
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

        subscriptions = (
            self.channel_subscriptions.get(
                channel
            )
        )

        if subscriptions:

            subscriptions.discard(
                websocket
            )

            if not subscriptions:
                self.channel_subscriptions.pop(
                    channel,
                    None,
                )

        await self._send_json(
            websocket,
            {
                "type": "unsubscribed",
                "channel": channel,
            },
        )

        return True

    # ========================================================================
    # BROADCAST VALIDATION
    # ========================================================================

    def _prune_valid_cache(
        self,
        now: float,
    ) -> None:
        """Keep the validation cache bounded."""

        if len(self._valid_cache) < VALID_CACHE_MAX_ENTRIES:
            return

        expired = [
            key
            for key, (expires_at, _valid)
            in self._valid_cache.items()
            if expires_at <= now
        ]

        for key in expired:
            self._valid_cache.pop(
                key,
                None,
            )

        if len(self._valid_cache) >= VALID_CACHE_MAX_ENTRIES:
            self._valid_cache.clear()

    async def _validate_broadcast(
        self,
        channel: str,
        message: dict,
    ) -> bool:

        parts = channel.split(":")

        target_tenant_id = (
            parts[1]
            if (
                len(parts) > 1
                and parts[0] == "tenant"
            )
            else None
        )

        if not target_tenant_id:
            return True

        payload_tenant = message.get(
            "tenant_id"
        )

        if not payload_tenant:
            logger.error(
                "[ws:broadcast] Missing tenant_id"
            )
            return False

        if payload_tenant != target_tenant_id:

            logger.error(
                "[ws:broadcast] Tenant mismatch "
                f"payload={payload_tenant} "
                f"channel={target_tenant_id}"
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
            target_tenant_id,
            technician_id,
            job_id,
        )

        now = time.monotonic()

        cached = self._valid_cache.get(
            cache_key
        )

        if cached:

            expires_at, valid = cached

            if now < expires_at:
                return valid

            self._valid_cache.pop(
                cache_key,
                None,
            )

        # --------------------------------------------------------------------
        # Another broadcast is already validating the same key
        # (for example the job / technician / all channels of one update).
        # Wait for its result instead of running the same DB query again.
        # --------------------------------------------------------------------

        inflight = self._validation_inflight.get(
            cache_key
        )

        if inflight is not None:
            return await inflight

        # --------------------------------------------------------------------
        # Perform DB validation outside the event loop.
        # --------------------------------------------------------------------

        def validate_db():

            db = SessionLocal()

            try:

                from ..models import (
                    Technician,
                    Job,
                )

                technician = (
                    db.query(Technician)
                    .filter(
                        Technician.tech_id
                        == technician_id,
                        Technician.tenant_id
                        == payload_tenant,
                    )
                    .first()
                )

                if not technician:
                    return False

                if not job_id:
                    return False

                try:
                    job_db_id = int(job_id)
                except (
                    ValueError,
                    TypeError,
                ):
                    return False

                job = (
                    db.query(Job)
                    .filter(
                        Job.id == job_db_id,
                        Job.tenant_id
                        == payload_tenant,
                    )
                    .first()
                )

                return job is not None

            finally:
                db.close()

        future = asyncio.get_running_loop().create_future()

        self._validation_inflight[
            cache_key
        ] = future

        valid = False
        cacheable = True

        try:
            valid = await asyncio.to_thread(
                validate_db
            )

        except Exception as exc:
            # A DB error must not be cached as "invalid".
            cacheable = False

            logger.error(
                f"[ws:broadcast] validation failed for {cache_key}: {exc}"
            )

        finally:
            self._validation_inflight.pop(
                cache_key,
                None,
            )

            if not future.done():
                future.set_result(valid)

        if cacheable:

            self._prune_valid_cache(now)

            ttl = (
                BROADCAST_VALIDATION_TTL_S
                if valid
                else INVALID_VALIDATION_TTL_S
            )

            self._valid_cache[
                cache_key
            ] = (
                time.monotonic() + ttl,
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

        subscribers = (
            self.channel_subscriptions.get(
                channel
            )
        )

        if not subscribers:
            return 0

        # --------------------------------------------------------------------
        # Security validation.
        # --------------------------------------------------------------------

        valid = await self._validate_broadcast(
            channel,
            message,
        )

        if not valid:
            return 0

        # Re-read subscribers: they may have changed while validating.
        sockets = [
            ws
            for ws in list(
                self.channel_subscriptions.get(
                    channel,
                    (),
                )
            )
            if id(ws) in self._send_locks
        ]

        if not sockets:
            return 0

        # --------------------------------------------------------------------
        # Send concurrently. Each send is serialised per socket and bounded
        # by BROADCAST_SEND_TIMEOUT_S, so one slow client cannot block the
        # others.
        # --------------------------------------------------------------------

        outcomes = await asyncio.gather(
            *(
                self._send_json(ws, message)
                for ws in sockets
            ),
        )

        sent = 0

        stale: list[WebSocket] = []

        for ws, success in zip(
            sockets,
            outcomes,
        ):

            if success:

                sent += 1

                self._total_messages_broadcast += 1

            else:

                stale.append(ws)

        # --------------------------------------------------------------------
        # Failed sockets are CLOSED (not just unsubscribed) so the browser
        # reconnects and re-subscribes.
        # --------------------------------------------------------------------

        if stale:

            logger.warning(
                f"[ws:broadcast] dropping {len(stale)} unresponsive "
                f"socket(s) on channel={channel}"
            )

            await asyncio.gather(
                *(
                    self._drop_connection(
                        ws,
                        reason="send failed",
                    )
                    for ws in stale
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

        await self._cleanup_connection(
            websocket,
            tenant_id,
        )

    # ========================================================================
    # CLEANUP (idempotent)
    # ========================================================================

    async def _cleanup_connection(
        self,
        websocket: WebSocket,
        tenant_id: str,
    ) -> None:

        websocket_id = id(websocket)

        was_registered = (
            websocket_id
            in self.connection_metadata
        )

        if not tenant_id:
            tenant_id = self.connection_metadata.get(
                websocket_id,
                {},
            ).get(
                "tenant_id",
                "",
            )

        # --------------------------------------------------------------------
        # Cancel heartbeat.
        # --------------------------------------------------------------------

        heartbeat_task = (
            self._heartbeat_tasks.pop(
                websocket_id,
                None,
            )
        )

        if heartbeat_task:

            current_task = (
                asyncio.current_task()
            )

            if heartbeat_task is not current_task:

                heartbeat_task.cancel()

                try:
                    await heartbeat_task

                except asyncio.CancelledError:
                    pass

                except Exception:
                    pass

        # --------------------------------------------------------------------
        # Remove tenant connection.
        # --------------------------------------------------------------------

        if (
            tenant_id
            and tenant_id
            in self.active_connections
        ):

            try:

                self.active_connections[
                    tenant_id
                ].remove(websocket)

            except ValueError:
                pass

            if not self.active_connections[
                tenant_id
            ]:
                del self.active_connections[
                    tenant_id
                ]

        # --------------------------------------------------------------------
        # Remove channel subscriptions.
        # --------------------------------------------------------------------

        empty_channels = []

        for channel, subscribers in list(
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
        # Remove metadata and send lock.
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
                f"[ws:disconnect] tenant={tenant_id}"
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
        Send an application-level ping every HEARTBEAT_INTERVAL_S.

        IMPORTANT:
        This coroutine NEVER calls receive_json(). The websocket endpoint in
        routes/tracking.py is the only reader of incoming messages.

        The frontend uses these pings as a liveness signal: if no message of
        any kind arrives for ~75 s it closes the socket and reconnects.

        If a ping cannot be delivered, the socket is closed and removed, so a
        half-open connection cannot linger as a zombie (and cannot keep
        consuming one of the tenant's connection slots).
        """

        try:

            while True:

                await asyncio.sleep(
                    HEARTBEAT_INTERVAL_S
                )

                ping_ts = (
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                )

                delivered = await self._send_json(
                    websocket,
                    {
                        "type": "ping",
                        "timestamp": ping_ts,
                    },
                )

                if not delivered:

                    logger.warning(
                        "[ws:heartbeat] "
                        f"ping failed user={user_id}; closing socket"
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
                "[ws:heartbeat] "
                f"heartbeat stopped user={user_id}: "
                f"{exc}"
            )

    # ========================================================================
    # METRICS
    # ========================================================================

    def get_metrics(self) -> dict:

        active_by_tenant = {
            tenant: len(sockets)
            for tenant, sockets
            in self.active_connections.items()
        }

        return {
            "active_connections_by_tenant":
                active_by_tenant,

            "total_active_connections":
                sum(
                    active_by_tenant.values()
                ),

            "total_messages_broadcast":
                self._total_messages_broadcast,

            "total_dropped_connections":
                self._total_dropped_connections,

            "uptime_seconds":
                round(
                    time.monotonic()
                    - self._started_at,
                    1,
                ),

            "validation_cache_entries":
                len(
                    self._valid_cache
                ),

            "subscriptions":
                len(
                    self.channel_subscriptions
                ),

            "send_timeout_s":
                BROADCAST_SEND_TIMEOUT_S,

            "heartbeat_interval_s":
                HEARTBEAT_INTERVAL_S,

            "max_connections_per_tenant":
                MAX_CONNECTIONS_PER_TENANT,
        }


# ============================================================================
# SINGLETON
# ============================================================================

connection_manager = ConnectionManager()