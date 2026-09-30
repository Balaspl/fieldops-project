"""
app/routes/tracking.py
──────────────────────
Real-time GPS position broadcast WebSocket server.

Endpoints:
  GET  /ws/v1/tracking?token=<jwt>   WebSocket upgrade
  GET  /api/v1/tracking/metrics      JSON metrics snapshot

WebSocket message protocol (client → server):
  {"type": "subscribe",   "channel": "tenant:{id}:technician:{tech_id}"}
  {"type": "unsubscribe", "channel": "tenant:{id}:job:{job_id}"}
  {"type": "pong",        "timestamp": "..."}

WebSocket message protocol (server → client):
  {"type": "subscribed",      "channel": "..."}
  {"type": "unsubscribed",    "channel": "..."}
  {"type": "ping",            "timestamp": "..."}
  {"type": "position_update", ...}
  {"type": "error",           "code": "...", "message": "..."}

Changes in this version
───────────────────────
1. redis_gps_listener() no longer dies on the first error. It reconnects with
   exponential backoff (1s → 15s) and re-subscribes, so a Redis restart or
   network blip cannot silently kill live tracking.
2. Fan-out to the technician / job / all channels is now concurrent
   (asyncio.gather), and updates inside one batch are also fanned out
   concurrently, so one slow client cannot delay a customer.
3. The WebSocket endpoint ALWAYS unregisters the connection (the cross-tenant
   rejection path used to leak a connection slot and heartbeat task).
4. Invalid JSON / non-object messages no longer disconnect the client, and
   errors inside subscribe/unsubscribe no longer tear down the connection.
5. The cross-tenant security log runs in a worker thread (sync DB work no
   longer blocks the event loop).
"""

from __future__ import annotations

import asyncio
import json

import msgpack
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi import Depends, HTTPException, status

from ..auth.dependencies import AuthenticatedUser, get_current_user
from ..logger import logger
from ..services.tracking_manager import connection_manager
from ..services.broadcast_scheduler import REDIS_GPS_CHANNEL


router = APIRouter(tags=["Tracking"])

# Reject absurd channel names before they reach the database validator.
MAX_CHANNEL_LENGTH = 200

# Reconnect backoff for the Redis listener (seconds).
LISTENER_BACKOFF_START_S = 1
LISTENER_BACKOFF_MAX_S = 15


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
async def _safe_send_error(
    websocket: WebSocket,
    code: str,
    message: str,
) -> None:
    """Send an error frame without ever raising."""
    try:
        await websocket.send_json(
            {
                "type": "error",
                "code": code,
                "message": message,
            }
        )
    except Exception:
        pass


def _log_cross_tenant_attempt(
    jwt_tenant_id: str,
    attempted_tenant_id: str,
    ip_address: str,
    websocket_id: str,
) -> None:
    """
    Synchronous security-audit write.

    Called through asyncio.to_thread() so the DB commit does not block the
    event loop (and therefore does not delay other customers' GPS updates).
    """
    from ..database import SessionLocal
    from ..services.tracking_manager import log_security_event

    db = SessionLocal()

    try:
        log_security_event(
            db=db,
            event_type="cross_tenant_handshake_attempt",
            severity="warning",
            user_tenant=jwt_tenant_id,
            attempted_channel=None,
            ip_address=ip_address,
            websocket_id=websocket_id,
            action_taken="connection_rejected",
            target_tenant=attempted_tenant_id,
        )
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket Endpoint
# ─────────────────────────────────────────────────────────────────────────────
@router.websocket("/ws/v1/tracking")
async def ws_tracking(
    websocket: WebSocket,
    token: str = "",
    tenant_id: str = "",
):
    """
    WebSocket endpoint for real-time technician GPS position broadcasting.

    Authentication: JWT token passed as ?token= query parameter.
    Claims required: tenant_id, user_id, role.

    The tenant is ALWAYS taken from the JWT. The optional ?tenant_id= query
    parameter is only compared with it; a mismatch closes the connection.
    """

    # Authenticate and accept
    claims = await connection_manager.connect(websocket, token)

    if claims is None:
        return  # connect() already closed with 1008

    jwt_tenant_id = claims["tenant_id"]

    # From this point on the connection is registered in the manager, so every
    # exit path MUST reach the `finally` block below.
    try:
        # ---------------------------------------------------------------------
        # Prevent client-supplied tenant from overriding JWT tenant
        # ---------------------------------------------------------------------
        if tenant_id and jwt_tenant_id != tenant_id:
            ip_addr = (
                websocket.client.host
                if websocket.client and hasattr(websocket.client, "host")
                else "unknown"
            )

            try:
                await asyncio.to_thread(
                    _log_cross_tenant_attempt,
                    jwt_tenant_id,
                    tenant_id,
                    ip_addr,
                    f"ws-{id(websocket)}",
                )
            except Exception as exc:
                logger.error(
                    f"[ws:tracking] failed to log cross-tenant attempt: {exc}"
                )

            await websocket.close(
                code=1008,
                reason="Cross-tenant connection attempt",
            )
            return

        # ---------------------------------------------------------------------
        # Message receive loop
        # ---------------------------------------------------------------------
        while True:
            try:
                data = await websocket.receive_json()

            except WebSocketDisconnect:
                break

            except (json.JSONDecodeError, KeyError, UnicodeDecodeError):
                # Bad frame from the client: tell it, but keep the connection.
                await _safe_send_error(
                    websocket,
                    "INVALID_MESSAGE",
                    "Message must be a JSON text object",
                )
                continue

            except Exception:
                # Socket closed / broken: leave the loop.
                break

            if not isinstance(data, dict):
                await _safe_send_error(
                    websocket,
                    "INVALID_MESSAGE",
                    "Message must be a JSON object",
                )
                continue

            msg_type = data.get("type", "")

            # -----------------------------------------------------------------
            # Subscribe
            # -----------------------------------------------------------------
            if msg_type == "subscribe":
                channel = data.get("channel", "")

                if (
                    not isinstance(channel, str)
                    or not channel
                    or len(channel) > MAX_CHANNEL_LENGTH
                ):
                    await _safe_send_error(
                        websocket,
                        "INVALID_CHANNEL_FORMAT",
                        "Channel must be a non-empty string",
                    )
                    continue

                try:
                    await connection_manager.subscribe(
                        websocket,
                        channel,
                        jwt_tenant_id,
                    )
                except Exception as exc:
                    logger.error(
                        f"[ws:tracking] subscribe failed channel={channel}: {exc}",
                        exc_info=True,
                    )
                    await _safe_send_error(
                        websocket,
                        "SUBSCRIBE_FAILED",
                        "Unable to subscribe. Please retry.",
                    )

            # -----------------------------------------------------------------
            # Unsubscribe
            # -----------------------------------------------------------------
            elif msg_type == "unsubscribe":
                channel = data.get("channel", "")

                if (
                    not isinstance(channel, str)
                    or not channel
                    or len(channel) > MAX_CHANNEL_LENGTH
                ):
                    await _safe_send_error(
                        websocket,
                        "INVALID_CHANNEL_FORMAT",
                        "Channel must be a non-empty string",
                    )
                    continue

                try:
                    await connection_manager.unsubscribe(
                        websocket,
                        channel,
                        jwt_tenant_id,
                    )
                except Exception as exc:
                    logger.error(
                        f"[ws:tracking] unsubscribe failed channel={channel}: {exc}",
                        exc_info=True,
                    )
                    await _safe_send_error(
                        websocket,
                        "UNSUBSCRIBE_FAILED",
                        "Unable to unsubscribe. Please retry.",
                    )

            # -----------------------------------------------------------------
            # Heartbeat pong (liveness is enforced by send failures in the
            # manager's heartbeat task; nothing to do here)
            # -----------------------------------------------------------------
            elif msg_type == "pong":
                pass

            # -----------------------------------------------------------------
            # Unknown message
            # -----------------------------------------------------------------
            else:
                await _safe_send_error(
                    websocket,
                    "UNKNOWN_MESSAGE_TYPE",
                    f"Unknown message type: {msg_type!r}",
                )

    except WebSocketDisconnect:
        pass

    finally:
        # Always unregister: removes the socket from tenant connections,
        # channel subscriptions, metadata and cancels its heartbeat task.
        await connection_manager.disconnect(
            websocket,
            jwt_tenant_id,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Redis pub/sub listener for cross-instance broadcast
# ─────────────────────────────────────────────────────────────────────────────
async def _fan_out_update(update: dict) -> None:
    """
    Deliver ONE position update to every relevant channel concurrently.

    Channels:
      tenant:{tenant}:job:{job}              → the customer's live map
      tenant:{tenant}:technician:{tech}      → per-technician subscribers
      tenant:{tenant}:all                    → dispatcher dashboards
    """
    if not isinstance(update, dict):
        return

    tenant_id = update.get("tenant_id", "")
    tech_id = update.get("technician_id", "")
    job_id = update.get("job_id", "")

    if not tenant_id:
        return

    await asyncio.gather(
        connection_manager.broadcast(
            f"tenant:{tenant_id}:job:{job_id}",
            update,
        ),
        connection_manager.broadcast(
            f"tenant:{tenant_id}:technician:{tech_id}",
            update,
        ),
        connection_manager.broadcast(
            f"tenant:{tenant_id}:all",
            update,
        ),
        return_exceptions=True,
    )


async def redis_gps_listener(redis_async) -> None:
    """
    Subscribe to the Redis ``gps:updates`` channel and fan-out every
    MessagePack-encoded position batch to local WebSocket connections.

    This coroutine is resilient: if Redis disconnects, restarts, or raises,
    it waits (exponential backoff, max 15 s), reconnects and subscribes again.
    It only exits when the task is cancelled (application shutdown).

    IMPORTANT
    ─────────
    * Start it ONCE per application worker at startup, e.g.
          app.state.gps_listener_task = asyncio.create_task(
              redis_gps_listener(redis_async)
          )
    * ``redis_async`` must be created with ``decode_responses=False`` because
      the payload is binary MessagePack. Recommended options:
          redis.asyncio.from_url(
              url,
              decode_responses=False,
              health_check_interval=30,
              socket_keepalive=True,
          )
    """
    logger.info("[ws:listener] Starting Redis GPS pub/sub listener")

    backoff = LISTENER_BACKOFF_START_S

    while True:
        pubsub = None

        try:
            pubsub = redis_async.pubsub()
            await pubsub.subscribe(REDIS_GPS_CHANNEL)

            logger.info(
                f"[ws:listener] Subscribed to Redis channel {REDIS_GPS_CHANNEL}"
            )

            # Connected successfully: reset the backoff.
            backoff = LISTENER_BACKOFF_START_S

            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue

                raw = message.get("data")

                if not isinstance(raw, (bytes, bytearray)):
                    logger.error(
                        "[ws:listener] Received non-binary payload; check that "
                        "the Redis client uses decode_responses=False"
                    )
                    continue

                try:
                    data = msgpack.unpackb(raw, raw=False)
                except Exception as exc:
                    logger.error(
                        f"[ws:listener] Could not decode MessagePack payload: {exc}"
                    )
                    continue

                updates = data.get("updates", []) if isinstance(data, dict) else []

                if not updates:
                    continue

                # All updates in the batch (and all three channels per update)
                # are delivered concurrently.
                results = await asyncio.gather(
                    *(_fan_out_update(update) for update in updates),
                    return_exceptions=True,
                )

                for result in results:
                    if isinstance(result, Exception):
                        logger.error(
                            f"[ws:listener] Error fanning out update: {result}"
                        )

        except asyncio.CancelledError:
            logger.info("[ws:listener] Redis GPS listener cancelled")
            raise

        except Exception as exc:
            logger.error(
                f"[ws:listener] Redis connection lost: {exc}. "
                f"Reconnecting in {backoff}s",
                exc_info=True,
            )

        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe(REDIS_GPS_CHANNEL)
                except Exception:
                    pass

                try:
                    close = getattr(pubsub, "aclose", None) or pubsub.close
                    result = close()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    pass

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, LISTENER_BACKOFF_MAX_S)


# ─────────────────────────────────────────────────────────────────────────────
# Metrics Endpoint
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/api/v1/tracking/metrics")
def get_tracking_metrics(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Return a snapshot of active WebSocket connections
    and broadcast metrics.

    Tracking metrics are restricted to:
      - dispatcher
      - super_admin
      - head
    """

    if current_user.role.value not in {
        "dispatcher",
        "super_admin",
        "head",
    }:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    return connection_manager.get_metrics()