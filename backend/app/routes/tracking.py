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
  {"type": "position_update", ... }
  {"type": "error",           "code": "...", "message": "..."}
"""

from __future__ import annotations

import asyncio
import json
import os

import msgpack
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..logger import logger
from ..services.tracking_manager import connection_manager
from ..services.broadcast_scheduler import REDIS_GPS_CHANNEL

router = APIRouter(tags=["Tracking"])


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket Endpoint
# ─────────────────────────────────────────────────────────────────────────────
@router.websocket("/ws/v1/tracking")
async def ws_tracking(websocket: WebSocket, token: str = "", tenant_id: str = ""):
    """
    WebSocket endpoint for real-time technician GPS position broadcasting.

    Authentication: JWT token passed as ?token= query parameter.
    Claims required: tenant_id, user_id, role ∈ {dispatcher, admin, supervisor}
    """
    # Authenticate and accept
    claims = await connection_manager.connect(websocket, token)
    if claims is None:
        return  # connect() already closed with 1008

    jwt_tenant_id = claims["tenant_id"]
    if tenant_id and jwt_tenant_id != tenant_id:
        from ..database import SessionLocal
        from ..services.tracking_manager import log_security_event
        db = SessionLocal()
        try:
            ip_addr = websocket.client.host if (websocket.client and hasattr(websocket.client, "host")) else "unknown"
            log_security_event(
                db=db,
                event_type="cross_tenant_handshake_attempt",
                severity="warning",
                user_tenant=jwt_tenant_id,
                attempted_channel=None,
                ip_address=ip_addr,
                websocket_id=f"ws-{id(websocket)}",
                action_taken="connection_rejected",
                target_tenant=tenant_id
            )
        finally:
            db.close()
        await websocket.close(code=1008, reason="Cross-tenant connection attempt")
        return

    tenant_id = jwt_tenant_id

    # Message receive loop
    try:
        while True:
            try:
                data = await websocket.receive_json()
            except Exception:
                break

            msg_type = data.get("type", "")

            if msg_type == "subscribe":
                channel = data.get("channel", "")
                await connection_manager.subscribe(websocket, channel, tenant_id)

            elif msg_type == "unsubscribe":
                channel = data.get("channel", "")
                await connection_manager.unsubscribe(websocket, channel)

            elif msg_type == "pong":
                # heartbeat pong handled inside _heartbeat coroutine via receive_json;
                # arriving here means client sent pong outside of the wait window — ignore
                pass

            else:
                await websocket.send_json({
                    "type": "error",
                    "code": "UNKNOWN_MESSAGE_TYPE",
                    "message": f"Unknown message type: {msg_type!r}",
                })

    except WebSocketDisconnect:
        pass
    finally:
        await connection_manager.disconnect(websocket, tenant_id)


# ─────────────────────────────────────────────────────────────────────────────
# Redis pub/sub listener for cross-instance broadcast
# ─────────────────────────────────────────────────────────────────────────────
async def redis_gps_listener(redis_async) -> None:
    """
    Subscribe to the Redis ``gps:updates`` channel and fan-out every
    MessagePack-encoded position batch to local WebSocket connections.

    Designed to run as a long-lived background coroutine started at app startup.
    """
    logger.info("[ws:listener] Starting Redis GPS pub/sub listener")
    try:
        pubsub = redis_async.pubsub()
        await pubsub.subscribe(REDIS_GPS_CHANNEL)

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = msgpack.unpackb(message["data"], raw=False)
                for update in data.get("updates", []):
                    tenant_id = update.get("tenant_id", "")
                    tech_id = update.get("technician_id", "")
                    job_id = update.get("job_id", "")

                    tech_channel = f"tenant:{tenant_id}:technician:{tech_id}"
                    job_channel = f"tenant:{tenant_id}:job:{job_id}"
                    all_channel = f"tenant:{tenant_id}:all"

                    await connection_manager.broadcast(tech_channel, update)
                    await connection_manager.broadcast(job_channel, update)
                    await connection_manager.broadcast(all_channel, update)
            except Exception as e:
                logger.error(f"[ws:listener] Error processing GPS message: {e}")
    except asyncio.CancelledError:
        logger.info("[ws:listener] Redis GPS listener cancelled")
    except Exception as e:
        logger.error(f"[ws:listener] Fatal error in GPS listener: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# Metrics Endpoint
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/api/v1/tracking/metrics")
def get_tracking_metrics():
    """Return a snapshot of active WebSocket connections and broadcast metrics."""
    return connection_manager.get_metrics()
