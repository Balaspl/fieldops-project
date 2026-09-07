import os

import jwt
import socketio

from ..logger import logger


# Initialize AsyncServer for ASGI.
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
)
sio_app = socketio.ASGIApp(sio)


def _decode_socket_token(token: str) -> dict:
    """
    Decode and validate the JWT used by Socket.IO clients.
    """
    jwt_secret = os.getenv("JWT_SECRET", "").strip()
    jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256").strip()

    if not jwt_secret:
        raise ValueError("Authentication service unavailable.")

    if jwt_algorithm != "HS256":
        raise ValueError("Authentication service unavailable.")

    return jwt.decode(
        token,
        jwt_secret,
        algorithms=[jwt_algorithm],
        options={
            "require": ["exp"],
        },
    )


@sio.event
async def connect(sid, environ, auth=None):
    """
    Authenticate the Socket.IO connection and bind it to the
    tenant from the verified JWT.

    The tenant_id supplied by the client is never trusted.
    """
    token = None

    # Socket.IO clients may send the token through the auth payload.
    if isinstance(auth, dict):
        token = auth.get("token")

    # Backward-compatible fallback for clients sending token
    # through the query string.
    if not token:
        query_string = environ.get("QUERY_STRING", "")
        for param in query_string.split("&"):
            if param.startswith("token="):
                token = param.split("=", 1)[1]
                break

    if not token:
        logger.warning(
            f"Socket.io connection rejected: missing token for {sid}"
        )
        return False

    try:
        claims = _decode_socket_token(token)
    except jwt.ExpiredSignatureError:
        logger.warning(
            f"Socket.io connection rejected: expired token for {sid}"
        )
        return False
    except jwt.PyJWTError:
        logger.warning(
            f"Socket.io connection rejected: invalid token for {sid}"
        )
        return False
    except ValueError as exc:
        logger.error(
            f"Socket.io authentication unavailable for {sid}: {exc}"
        )
        return False

    tenant_id = str(
        claims.get("tenant_id", "")
    ).strip()

    user_id = str(
        claims.get(
            "sub",
            claims.get("user_id", ""),
        )
    ).strip()

    if not tenant_id or not user_id:
        logger.warning(
            f"Socket.io connection rejected: incomplete JWT claims for {sid}"
        )
        return False

    # Never trust tenant_id or tech_id from the client.
    tech_id = str(
        claims.get("tech_id", "")
    ).strip()

    await sio.save_session(
        sid,
        {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "tech_id": tech_id or None,
        },
    )

    # Tenant room is derived exclusively from the verified JWT.
    await sio.enter_room(
        sid,
        f"tenant_{tenant_id}",
    )

    logger.info(
        f"Socket.io client connected: {sid} "
        f"mapped to tenant {tenant_id}"
    )

    # Technician room is also scoped by tenant.
    if tech_id:
        await sio.enter_room(
            sid,
            f"tenant_{tenant_id}:tech_{tech_id}",
        )

        logger.info(
            f"Socket.io client connected: {sid} "
            f"mapped to technician {tech_id} "
            f"within tenant {tenant_id}"
        )


@sio.event
async def disconnect(sid):
    logger.info(
        f"Socket.io client disconnected: {sid}"
    )


@sio.event
async def subscribe_to_job(sid, data):
    """
    Allow a client to subscribe to real-time ETA updates for a job.

    The job room is scoped to the authenticated tenant.
    The tenant is never accepted from the client payload.
    """
    job_id = (
        data.get("job_id")
        if isinstance(data, dict)
        else None
    )

    if not job_id:
        return

    try:
        session = await sio.get_session(sid)
    except KeyError:
        logger.warning(
            f"Socket.io subscription rejected: "
            f"no authenticated session for {sid}"
        )
        return

    tenant_id = str(
        session.get("tenant_id", "")
    ).strip()

    if not tenant_id:
        logger.warning(
            f"Socket.io subscription rejected: "
            f"missing tenant for {sid}"
        )
        return

    # Job rooms are tenant-scoped.
    room = f"tenant_{tenant_id}:job:{job_id}"

    await sio.enter_room(
        sid,
        room,
    )

    logger.info(
        f"Socket.io client {sid} subscribed to "
        f"tenant-scoped job room: {room}"
    )


async def emit_notification(
    tech_id: str,
    payload: dict,
):
    """
    Emit a real-time notification to a specific technician
    within the notification tenant.
    """
    try:
        tenant_id = str(
            payload.get("tenant_id", "")
        ).strip()

        if not tenant_id:
            logger.warning(
                "Notification rejected: missing tenant_id"
            )
            return

        room = f"tenant_{tenant_id}:tech_{tech_id}"

        await sio.emit(
            "new_notification",
            payload,
            room=room,
        )

        logger.info(
            f"Emitted real-time notification to "
            f"tech_id {tech_id} in tenant {tenant_id}"
        )
    except Exception as e:
        logger.error(
            f"Failed to emit socket.io notification "
            f"to {tech_id}: {e}"
        )


class WebSocketManager:
    """
    Manager for broadcasting job-scoped and tenant-scoped events.
    """

    async def broadcast_to_job(
        self,
        job_id,
        payload: dict,
    ):
        """
        Broadcast a message to clients subscribed to a
        tenant-scoped job room.
        """
        tenant_id = str(
            payload.get("tenant_id", "")
        ).strip()

        if not tenant_id:
            logger.warning(
                f"Job broadcast rejected: missing tenant_id "
                f"for job {job_id}"
            )
            return

        room = f"tenant_{tenant_id}:job:{job_id}"

        try:
            await sio.emit(
                "eta_update",
                payload,
                room=room,
            )

            logger.info(
                f"Broadcast eta_update to room {room}: "
                f"eta={payload.get('eta')}"
            )
        except Exception as e:
            logger.error(
                f"Failed to broadcast eta_update "
                f"to job {job_id}: {e}"
            )

    async def broadcast_to_tenant(
        self,
        tenant_id: str,
        payload: dict,
    ):
        """
        Broadcast exclusively to clients belonging to a
        specific tenant.
        """
        room = f"tenant_{tenant_id}"

        try:
            event_name = payload.get(
                "type",
                "dispatch_event",
            )

            await sio.emit(
                event_name,
                payload,
                room=room,
            )

            logger.info(
                f"Broadcasted to tenant room {room}: "
                f"event={event_name}"
            )
        except Exception as e:
            logger.error(
                f"Failed to broadcast to tenant "
                f"{tenant_id}: {e}"
            )

    async def broadcast(
        self,
        channel: str,
        payload: dict,
    ):
        """
        Broadcast a message to a specific tenant-scoped
        room/channel.

        The channel must already contain the authenticated
        tenant scope supplied by the caller.
        """
        try:
            event_name = payload.get(
                "type",
                "update",
            )

            await sio.emit(
                event_name,
                payload,
                room=channel,
            )

            logger.info(
                f"Broadcasted to room {channel}: "
                f"event={event_name}"
            )
        except Exception as e:
            logger.error(
                f"Failed to broadcast to channel "
                f"{channel}: {e}"
            )


ws_manager = WebSocketManager()