
import os
from http.cookies import SimpleCookie
from urllib.parse import unquote

import jwt
import socketio

from sqlalchemy.orm import Session

from ..logger import logger
from ..database import SessionLocal
from ..models import Job, Technician
from ..models.user import User
from ..auth.jwt_handler import verify_access_token
from ..auth.session_service import validate_session, touch_session
from ..auth.rbac import UserRole, Permission, has_permission


# ============================================================
# SOCKET.IO CONFIGURATION
# ============================================================

# Socket.IO withCredentials=True cannot be used with wildcard CORS origins.
# Configure one or more exact frontend origins in SOCKETIO_ALLOWED_ORIGINS.
# Example:
# SOCKETIO_ALLOWED_ORIGINS=http://localhost:5173,https://your-frontend.example.com
_origins = os.getenv(
    "SOCKETIO_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
)

ALLOWED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in _origins.split(",")
    if origin.strip()
]

if not ALLOWED_ORIGINS:
    raise RuntimeError(
        "SOCKETIO_ALLOWED_ORIGINS must contain at least one explicit frontend origin."
    )

if "*" in ALLOWED_ORIGINS:
    raise RuntimeError(
        "SOCKETIO_ALLOWED_ORIGINS cannot contain '*' when Socket.IO credentials/cookies are used. "
        "Configure explicit frontend origins instead."
    )

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=ALLOWED_ORIGINS,
)

sio_app = socketio.ASGIApp(sio)

SSO_ACCESS_COOKIE = "fieldops_access_token"


# ============================================================
# TOKEN EXTRACTION
# ============================================================

def _extract_token(environ: dict, auth: dict | None) -> str | None:
    """
    Accept the existing access token from:
    1. Socket.IO auth payload.
    2. Authorization: Bearer header.
    3. Existing SSO HttpOnly cookie.

    Never use client-provided IDs as proof of identity.
    """

    if isinstance(auth, dict):
        token = auth.get("token")

        if isinstance(token, str) and token.strip():
            return token.strip()

    authorization = environ.get("HTTP_AUTHORIZATION", "")

    if authorization:
        scheme, _, credentials = authorization.partition(" ")

        if scheme.lower() == "bearer" and credentials.strip():
            return credentials.strip()

    cookie_header = environ.get("HTTP_COOKIE", "")

    if cookie_header:
        try:
            cookies = SimpleCookie()
            cookies.load(cookie_header)

            cookie = cookies.get(SSO_ACCESS_COOKIE)

            if cookie and cookie.value:
                return unquote(cookie.value)

        except Exception:
            logger.warning("Could not parse Socket.IO authentication cookie")

    return None


# ============================================================
# AUTHENTICATION
# ============================================================

def _authenticate_socket(token: str) -> dict | None:
    """
    Verify the access JWT, active user, database role,
    tenant, and server-side session using existing FieldOps
    authentication functions.
    """

    db: Session = SessionLocal()

    try:
        claims = verify_access_token(token)

        if claims.get("type") != "access":
            return None

        user_id = str(claims.get("sub") or "")
        token_tenant_id = str(claims.get("tenant_id") or "")
        token_role = str(claims.get("role") or "")
        session_id = str(claims.get("session_id") or "")

        if not user_id or not token_tenant_id or not session_id:
            return None

        user = (
            db.query(User)
            .filter(
                User.id == user_id,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
            .first()
        )

        if user is None or user.is_locked:
            return None

        database_tenant_id = str(user.tenant_id)
        database_role = (
            user.role.value
            if hasattr(user.role, "value")
            else str(user.role)
        )

        if token_tenant_id != database_tenant_id:
            return None

        if token_role != database_role:
            return None

        session = validate_session(
            session_id=session_id,
            user_id=user_id,
            tenant_id=database_tenant_id,
        )

        if session is None:
            return None

        if touch_session(session_id) is None:
            return None

        return {
            "user_id": user_id,
            "tenant_id": database_tenant_id,
            "role": database_role,
            "session_id": session_id,
        }

    except (jwt.InvalidTokenError, ValueError, TypeError):
        return None

    except Exception:
        logger.exception("Socket.IO authentication failed")
        return None

    finally:
        db.close()


# ============================================================
# TECHNICIAN LOOKUP
# ============================================================

def _get_technician(
    db: Session,
    user_id: str,
    tenant_id: str,
) -> Technician | None:
    """
    Match the authenticated user to the technician record,
    following the existing Jobs API mapping.
    """

    numeric_user_id = (
        int(user_id) if user_id.isdigit() else -1
    )

    return (
        db.query(Technician)
        .filter(
            Technician.tenant_id == tenant_id,
            (
                (Technician.tech_id == user_id)
                | (Technician.technician_id == numeric_user_id)
            ),
        )
        .first()
    )


# ============================================================
# JOB ROOM AUTHORIZATION
# ============================================================

def _can_access_job(
    db: Session,
    identity: dict,
    job_id: int,
) -> bool:
    """
    Allow job subscriptions only when the authenticated user
    is authorized for that job.

    Authorization paths:
    - Super admin.
    - Authorized tenant job viewer.
    - Technician assigned to the job.
    - Customer explicitly linked to the job.
    """

    user_id = identity["user_id"]
    tenant_id = identity["tenant_id"]
    role = identity["role"]

    try:
        user_role = UserRole(role)
    except ValueError:
        return False

    job = (
        db.query(Job)
        .filter(Job.id == job_id)
        .first()
    )

    if job is None:
        return False

    # Explicit platform-level administrator access.
    if user_role == UserRole.SUPER_ADMIN:
        return True

    # A technician may access a job only through their own
    # authenticated technician record and explicit assignment.
    # Do not require the job tenant to equal the technician tenant:
    # FieldOps supports jobs owned by one organization and assigned
    # to a technician in another organization.
    technician = _get_technician(db, user_id, tenant_id)

    if (
        technician is not None
        and job.assigned_technician_id == technician.technician_id
    ):
        return True

    # Tenant-wide job visibility requires the existing
    # application's JOBS_VIEW_ALL permission.
    if (
        str(job.tenant_id) == tenant_id
        and has_permission(user_role, Permission.JOBS_VIEW_ALL)
    ):
        return True

    # Customer access requires an explicit customer-to-job
    # identity match. Tenant membership alone is not enough.
    if (
        job.customer_id is not None
        and str(job.customer_id) == user_id
        and str(job.customer_tenant_id or "") == tenant_id
    ):
        return True

    return False


# ============================================================
# CONNECTION
# ============================================================

@sio.event
async def connect(sid, environ, auth=None):
    """
    Authenticate the Socket.IO connection.

    Query-string tech_id and tenant_id are deliberately ignored.
    Rooms are derived from the authenticated identity.
    """

    token = _extract_token(environ, auth)

    if not token:
        logger.warning(
            "Socket.IO connection rejected: missing credentials sid=%s",
            sid,
        )
        return False

    identity = _authenticate_socket(token)

    if identity is None:
        logger.warning(
            "Socket.IO connection rejected: invalid identity sid=%s",
            sid,
        )
        return False

    user_id = identity["user_id"]
    tenant_id = identity["tenant_id"]

    # Store only verified identity details for event handlers.
    await sio.save_session(sid, identity)

    # Authenticated tenant room.
    await sio.enter_room(sid, f"tenant_{tenant_id}")

    # Authenticated user room.
    await sio.enter_room(sid, f"user_{user_id}")

    # Customer notifications use a private user-specific room.
    await sio.enter_room(sid, f"customer_{user_id}")

    # Only users with the existing tenant-wide job-view permission join the
    # dispatcher room used by Communication Agent live notifications.
    try:
        authenticated_role = UserRole(identity["role"])
    except ValueError:
        authenticated_role = None

    if (
        authenticated_role is not None
        and has_permission(authenticated_role, Permission.JOBS_VIEW_ALL)
    ):
        await sio.enter_room(
            sid,
            f"tenant:{tenant_id}:dispatchers",
        )

    # Preserve existing technician notification room naming.
    db: Session = SessionLocal()

    try:
        technician = _get_technician(db, user_id, tenant_id)

        if technician is not None:
            if technician.tech_id:
                await sio.enter_room(sid, str(technician.tech_id))

            await sio.enter_room(
                sid,
                f"tech_{technician.technician_id}",
            )

    finally:
        db.close()

    logger.info(
        "Socket.IO authenticated: sid=%s user_id=%s tenant_id=%s",
        sid,
        user_id,
        tenant_id,
    )


@sio.event
async def disconnect(sid, reason=None):
    logger.info(
        "Socket.IO disconnected: sid=%s reason=%s",
        sid,
        reason,
    )


# ============================================================
# AUTHORIZED JOB SUBSCRIPTION
# ============================================================

@sio.event
async def subscribe_to_job(sid, data):
    """
    Subscribe to job ETA updates only after authorization.

    Expected payload:
        {"job_id": 123}
    """

    if not isinstance(data, dict):
        return {"ok": False, "error": "Invalid payload"}

    try:
        job_id = int(data.get("job_id"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "Invalid job ID"}

    if job_id <= 0:
        return {"ok": False, "error": "Invalid job ID"}

    try:
        identity = await sio.get_session(sid)
    except KeyError:
        return {"ok": False, "error": "Unauthenticated"}

    db: Session = SessionLocal()

    try:
        # Re-check authorization before joining the room.
        if not _can_access_job(db, identity, job_id):
            logger.warning(
                "Unauthorized job-room subscription: "
                "sid=%s user_id=%s job_id=%s",
                sid,
                identity.get("user_id"),
                job_id,
            )
            return {"ok": False, "error": "Access denied"}

        room = f"job:{job_id}"
        await sio.enter_room(sid, room)

        logger.info(
            "Socket.IO job subscription authorized: "
            "sid=%s job_id=%s",
            sid,
            job_id,
        )

        return {"ok": True, "job_id": job_id}

    finally:
        db.close()


@sio.event
async def unsubscribe_from_job(sid, data):
    """Leave a previously joined job room."""

    if not isinstance(data, dict):
        return {"ok": False, "error": "Invalid payload"}

    try:
        job_id = int(data.get("job_id"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "Invalid job ID"}

    if job_id <= 0:
        return {"ok": False, "error": "Invalid job ID"}

    await sio.leave_room(sid, f"job:{job_id}")

    return {"ok": True, "job_id": job_id}


# ============================================================
# TECHNICIAN NOTIFICATIONS
# ============================================================

async def emit_notification(tech_id: str, payload: dict):
    """
    Preserve the existing technician notification API.
    """

    try:
        await sio.emit(
            "new_notification",
            payload,
            room=str(tech_id),
        )

        logger.info(
            "Emitted real-time notification to technician"
        )

    except Exception:
        logger.exception(
            "Failed to emit technician notification"
        )


# ============================================================
# CUSTOMER NOTIFICATIONS
# ============================================================

async def emit_customer_notification(
    customer_user_id: str,
    payload: dict,
):
    """
    Send a notification only to the authenticated customer's
    private room.
    """

    try:
        await sio.emit(
            "new_notification",
            payload,
            room=f"customer_{customer_user_id}",
        )

        logger.info(
            "Emitted real-time customer notification"
        )

    except Exception:
        logger.exception(
            "Failed to emit customer notification"
        )


# ============================================================
# WEBSOCKET MANAGER
# ============================================================

class WebSocketManager:
    """Preserve existing job/tenant broadcasts and private notifications."""

    async def broadcast_to_technician(self, tech_id: str, payload: dict):
        """Send a private notification to the authenticated technician room."""
        await sio.emit(
            "new_notification",
            payload,
            room=str(tech_id),
        )

    async def broadcast_to_customer(self, customer_user_id: str, payload: dict):
        """Send a private notification to the authenticated customer room."""
        await sio.emit(
            "new_notification",
            payload,
            room=f"customer_{customer_user_id}",
        )

    async def broadcast_to_job(self, job_id, payload: dict):
        room = f"job:{job_id}"

        try:
            await sio.emit(
                "eta_update",
                payload,
                room=room,
            )

            logger.info(
                "Broadcast eta_update to job room %s",
                room,
            )

        except Exception:
            logger.exception(
                "Failed to broadcast ETA update for job %s",
                job_id,
            )

    async def broadcast_to_tenant(
        self,
        tenant_id: str,
        payload: dict,
    ):
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
                "Broadcast tenant event: tenant_id=%s event=%s",
                tenant_id,
                event_name,
            )

        except Exception:
            logger.exception(
                "Failed to broadcast to tenant %s",
                tenant_id,
            )

    async def broadcast(self, channel: str, payload: dict):
        try:
            event_name = payload.get("type", "update")

            await sio.emit(
                event_name,
                payload,
                room=channel,
            )

            logger.info(
                "Broadcast event=%s to room=%s",
                event_name,
                channel,
            )

        except Exception:
            logger.exception(
                "Failed to broadcast to room %s",
                channel,
            )


ws_manager = WebSocketManager()
