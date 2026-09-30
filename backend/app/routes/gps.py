"""
app/routers/gps.py
──────────────────
GPS ingest + history.

Live path (what the customer sees):
    /ping  ->  Redis gps:latest (snapshot) + gps:updates (pub/sub)
           ->  redis_gps_listener  ->  WebSocket
    The DB history write happens AFTER the live publish.

/ping runs its blocking work (SQLAlchemy + sync Redis) in a threadpool so it
never stalls the event loop that serves the WebSockets.
"""

import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import msgpack
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .. import models, schemas
from ..auth.dependencies import AuthenticatedUser, get_current_user
from ..auth.rbac import Permission
from ..database import get_db
from ..logger import logger
from ..redis_client import get_redis_client
from ..utils import as_utc, iso_utc, parse_iso_utc
from .dispatch import verify_jwt_token

# ── Constants ─────────────────────────────────────────────────────────────────
REDIS_GPS_CHANNEL = "gps:updates"
LATEST_TTL_S = 120                 # gps:latest snapshot lifetime
BROADCAST_DEDUP_TTL_S = 120        # must match the scheduler's dedup TTL
REJECT_LOG_INTERVAL_S = 60         # rejected-ping DB rows: max 1/min per technician
BATCH_MAX_AGE_S = 60               # /batch: never publish pings older than this
ACTIVE_STATUSES = {"ASSIGNED", "EN_ROUTE", "ON_SITE", "IN_PROGRESS", "ACTIVE"}


class TechnicianAvailabilityLocationRequest(BaseModel):
    latitude: float
    longitude: float
    accuracy: Optional[float] = None
    altitude: Optional[float] = None
    timestamp: datetime


router = APIRouter(
    prefix="/api/v1/gps",
    tags=["GPS"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _enforce_gps_actor(current_user: AuthenticatedUser, tenant_id: str, technician) -> None:
    """Bind GPS access to the signed-in tenant and, for technicians, identity."""
    if current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")
    if current_user.has_permission(Permission.GPS_TRACK):
        return
    if not current_user.has_permission(Permission.GPS_TRACK_OWN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    numeric_user_id = int(current_user.user_id) if str(current_user.user_id).isdigit() else -1
    if technician.tenant_id != current_user.tenant_id or not (
        technician.tech_id == str(current_user.user_id)
        or technician.technician_id == numeric_user_id
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Technician GPS access denied")


def _open_db(db_dep):
    """Open a session, honouring test dependency overrides."""
    db_res = db_dep()
    if hasattr(db_res, "__next__") or hasattr(db_res, "__iter__"):
        return next(db_res)
    return db_res


def log_rejected_ping(db: Session, technician_id: str, job_id: str, tenant_id: str, reason: str):
    try:
        rejected_log = models.GPSRejectedPingLog(
            technician_id=technician_id,
            job_id=str(job_id) if job_id else None,
            reason=reason,
            tenant_id=tenant_id,
        )
        db.add(rejected_log)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to log rejected ping: {e}")


def _log_rejected_throttled(redis_client, db: Session, technician_id: str, job_id: str,
                            tenant_id: str, reason: str) -> None:
    """Write a rejected-ping row at most once a minute per technician."""
    try:
        first = redis_client.set(
            f"gps:rej_log:{tenant_id}:{technician_id}", "1", nx=True, ex=REJECT_LOG_INTERVAL_S
        )
    except Exception:
        first = True  # Redis trouble -> still log
    if first:
        log_rejected_ping(db, technician_id, job_id, tenant_id, reason)


def _job_status_upper(job) -> str:
    return str(job.status or "").upper().strip()


def _read_eta(redis_client, technician_id: str, job_id: str):
    """Cached ETA only; never compute it on the live path."""
    try:
        raw = redis_client.get(f"eta:{technician_id}:{job_id}")
        if raw:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            data = json.loads(raw)
            return data.get("eta"), data.get("duration_minutes")
    except Exception:
        pass
    return None, None


def _build_update(*, technician_id, technician_name, job_id, tenant_id, latitude, longitude,
                  accuracy, altitude, job_status, timestamp, eta, eta_minutes, source) -> dict:
    now_iso = iso_utc(datetime.now(timezone.utc))
    return {
        "type": "position_update",
        "technician_id": technician_id,
        "technician_name": technician_name,
        "job_id": str(job_id),
        "tenant_id": tenant_id,
        "latitude": float(latitude),
        "longitude": float(longitude),
        "accuracy": float(accuracy) if accuracy is not None else None,
        "altitude": float(altitude) if altitude is not None else None,
        "job_status": job_status,
        "eta": eta,
        "eta_duration_minutes": eta_minutes,
        "timestamp": iso_utc(timestamp) if isinstance(timestamp, datetime) else str(timestamp),
        "server_ts": now_iso,       # client/server clock-skew free "age" is computed from this
        "broadcast_at": now_iso,
        "source": source,
    }


def _store_latest(redis_client, update: dict, only_if_newer: bool = False) -> bool:
    """
    Write the gps:latest snapshot (what a customer gets on subscribe).
    With only_if_newer, an older ping never overwrites a newer snapshot.
    Returns True if the snapshot was written.
    """
    key = f"gps:latest:{update['tenant_id']}:{update['job_id']}"
    if only_if_newer:
        try:
            raw = redis_client.get(key)
            if raw:
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                existing = json.loads(raw)
                if parse_iso_utc(existing["timestamp"]) >= parse_iso_utc(update["timestamp"]):
                    return False
        except Exception:
            pass
    redis_client.setex(key, LATEST_TTL_S, json.dumps(update))
    return True


def _publish_updates(redis_client, updates: list) -> None:
    envelope = {
        "type": "position_batch",
        "count": len(updates),
        "updates": updates,
        "broadcast_cycle_at": iso_utc(datetime.now(timezone.utc)),
    }
    redis_client.publish(REDIS_GPS_CHANNEL, msgpack.packb(envelope, use_bin_type=True))


def _mark_broadcast(redis_client, update: dict) -> None:
    """Tell the scheduler this exact ping has already been delivered."""
    redis_client.set(
        f"broadcast:last:{update['technician_id']}:{update['job_id']}",
        update["timestamp"],
        ex=BROADCAST_DEDUP_TTL_S,
    )


def _skipped(technician_id: str, job_id: str, **extra) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "skipped",
            "reason": "throttled",
            "technician_id": technician_id,
            "job_id": job_id,
            **extra,
        },
    )


def check_batch_sliding_window_rate_limit(redis_client, technician_id: str, tenant_id: str) -> bool:
    """Max 1 batch request per 5 seconds per technician (sliding window in Redis)."""
    now = time.time()
    window = 5
    limit = 1
    key = f"rate_limit:gps_batch:{tenant_id}:{technician_id}"

    try:
        redis_client.zremrangebyscore(key, 0, now - window)
        count = redis_client.zcard(key)
        if count >= limit:
            return False

        member = f"{now}:{uuid.uuid4().hex}"
        redis_client.zadd(key, {member: now})
        redis_client.expire(key, 10)
        return True
    except Exception as e:
        logger.warning(f"Redis rate limiter connection issue for batch: {e}. Falling back to allowing request.")
        return True


# ─────────────────────────────────────────────────────────────────────────────
# History
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/history/{technician_id}", response_model=list[schemas.GPSPingResponse])
def get_gps_history(
    technician_id: str,
    job_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    db: Session = Depends(get_db),
    authorization: str = Depends(verify_jwt_token),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    if current_user.tenant_id != (x_tenant_id or current_user.tenant_id):
        raise HTTPException(status_code=403, detail="Tenant access denied")
    technician = db.query(models.Technician).filter(
        models.Technician.tech_id == technician_id,
        models.Technician.tenant_id == current_user.tenant_id,
    ).first()
    if technician is None and technician_id.isdigit():
        technician = db.query(models.Technician).filter(
            models.Technician.technician_id == int(technician_id),
            models.Technician.tenant_id == current_user.tenant_id,
        ).first()
    if technician is None:
        raise HTTPException(status_code=404, detail="Technician not found")
    _enforce_gps_actor(current_user, current_user.tenant_id, technician)

    query = db.query(models.GPSPing).filter(
        models.GPSPing.technician_id == (technician.tech_id or str(technician.technician_id))
    )
    query = query.filter(models.GPSPing.tenant_id == current_user.tenant_id)

    if job_id:
        query = query.filter(models.GPSPing.job_id == job_id)
    if start_time:
        try:
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            query = query.filter(models.GPSPing.timestamp >= start_dt)
        except Exception:
            pass
    if end_time:
        try:
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            query = query.filter(models.GPSPing.timestamp <= end_dt)
        except Exception:
            pass

    pings = query.order_by(models.GPSPing.timestamp.asc()).all()

    return [
        schemas.GPSPingResponse(
            id=p.id,
            technician_id=p.technician_id,
            job_id=p.job_id,
            latitude=p.latitude,
            longitude=p.longitude,
            timestamp=p.timestamp,
            accuracy=p.accuracy,
            altitude=p.altitude,
            tenant_id=p.tenant_id,
            created_at=p.created_at,
        )
        for p in pings
    ]


# ─────────────────────────────────────────────────────────────────────────────
# /ping  (live path)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/ping", status_code=status.HTTP_201_CREATED, response_model=schemas.GPSPingResponse)
async def gps_ping(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    authorization: str = Depends(verify_jwt_token),
    redis_client=Depends(get_redis_client),
    bypass_interval: bool = False,  # kept for backward compatibility; ignored
    live_tracking: bool = False,    # kept for backward compatibility; server decides from job status
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Receive one technician GPS position and fan it out to live customers.

    Body parsing + schema validation stay on the event loop (cheap). Everything
    that touches the DB or sync Redis runs in a threadpool.
    """
    if current_user.tenant_id != x_tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access denied")

    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    log_extra = {"correlation_id": correlation_id, "tenant_id": x_tenant_id}

    # 1. Parse request body
    try:
        body_bytes = await request.body()
        body = json.loads(body_bytes.decode("utf-8"))
    except json.JSONDecodeError as jde:
        logger.error(f"Malformed JSON payload: {jde}", extra=log_extra)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Malformed JSON", "message": "The request body is not valid JSON"},
        )
    except Exception as e:
        logger.error(f"Error reading request body: {e}", extra=log_extra)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Bad request", "message": str(e)},
        )

    # 2. Pydantic validation before opening a DB session
    try:
        payload = schemas.GPSPingRequest(**body)
    except Exception as ve:
        logger.warning(f"Validation error: {ve}", extra=log_extra)
        formatted_errors = []

        if hasattr(ve, "errors"):
            pydantic_errors = ve.errors()
            custom_parsed = False

            for err in pydantic_errors:
                msg = err.get("msg", "")
                if msg.startswith("Value error, "):
                    msg = msg[len("Value error, "):]
                try:
                    custom_errors = json.loads(msg)
                    if isinstance(custom_errors, list):
                        for field, field_msg in custom_errors:
                            formatted_errors.append({
                                "loc": ["body", field],
                                "msg": field_msg,
                                "type": "value_error",
                            })
                        custom_parsed = True
                except Exception:
                    pass

            if not custom_parsed:
                for err in pydantic_errors:
                    loc = list(err.get("loc", []))
                    if not loc or loc[0] != "body":
                        loc.insert(0, "body")
                    msg = err.get("msg", "")
                    if msg.startswith("Value error, "):
                        msg = msg[len("Value error, "):]
                    formatted_errors.append({
                        "loc": loc,
                        "msg": msg,
                        "type": err.get("type", "value_error"),
                    })
        else:
            formatted_errors = [{"loc": ["body"], "msg": str(ve), "type": "value_error"}]

        return JSONResponse(status_code=422, content={"detail": formatted_errors})

    # 3. Everything blocking goes to the threadpool
    client_host = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")
    db_dep = request.app.dependency_overrides.get(get_db, get_db)

    return await run_in_threadpool(
        _process_ping_sync,
        db_dep, payload, x_tenant_id, current_user,
        redis_client, client_host, user_agent, correlation_id,
    )


def _process_ping_sync(db_dep, payload, x_tenant_id, current_user,
                       redis_client, client_host, user_agent, correlation_id):
    """Sync body of /ping. Must not contain `await`."""
    log_extra = {"correlation_id": correlation_id, "tenant_id": x_tenant_id}

    throttle_key = f"gps:live_interval:{x_tenant_id}:{payload.technician_id}:{payload.job_id}"

    # Cheap early exit: a ping inside the throttle window costs one Redis call,
    # not two DB queries.
    try:
        if redis_client.exists(throttle_key):
            return _skipped(
                payload.technician_id, payload.job_id,
                retry_after_ms=max(0, int(redis_client.pttl(throttle_key) or 0)),
            )
    except Exception:
        pass

    db = _open_db(db_dep)
    try:
        # ── 4. Technician authorization ──────────────────────────────────────
        tech = db.query(models.Technician).filter(
            models.Technician.tech_id == payload.technician_id
        ).first()

        if not tech:
            logger.error(f"Technician not found: {payload.technician_id}", extra=log_extra)
            _log_rejected_throttled(redis_client, db, payload.technician_id, payload.job_id,
                                    x_tenant_id, "Technician not found")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Technician not found")

        _enforce_gps_actor(current_user, x_tenant_id, tech)

        if tech.tenant_id and tech.tenant_id != x_tenant_id:
            _log_rejected_throttled(redis_client, db, payload.technician_id, payload.job_id,
                                    x_tenant_id, "Access denied for technician")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        # ── 5. Job authorization / status ────────────────────────────────────
        job = None
        if str(payload.job_id).isdigit():
            job = db.query(models.Job).filter(models.Job.id == int(payload.job_id)).first()

        if not job:
            _log_rejected_throttled(redis_client, db, payload.technician_id, payload.job_id,
                                    x_tenant_id, "Job not found")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

        if job.tenant_id and job.tenant_id != x_tenant_id:
            _log_rejected_throttled(redis_client, db, payload.technician_id, payload.job_id,
                                    x_tenant_id, "Access denied for job")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        job_status_upper = _job_status_upper(job)

        if job_status_upper not in ACTIVE_STATUSES:
            _log_rejected_throttled(redis_client, db, payload.technician_id, payload.job_id,
                                    x_tenant_id, f"Job status is {job.status}")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Job status is not active")

        # Assignment is enforced for EVERY active status, legacy "active" included.
        if job.assigned_technician_id != tech.technician_id:
            _log_rejected_throttled(redis_client, db, payload.technician_id, payload.job_id,
                                    x_tenant_id, "Technician not assigned to job")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Technician not assigned to job")

        # ── 6. Accuracy gate ─────────────────────────────────────────────────
        # Dev: set GPS_MAX_ACCURACY_METERS=250 (laptop GPS reports ~90-150 m).
        max_accuracy = float(os.getenv("GPS_MAX_ACCURACY_METERS", "100"))
        if payload.accuracy is not None and payload.accuracy > max_accuracy:
            reason = f"GPS accuracy {payload.accuracy:.1f}m exceeds {max_accuracy:.0f}m"
            _log_rejected_throttled(redis_client, db, payload.technician_id, payload.job_id,
                                    x_tenant_id, reason)
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=reason)

        # ── 7. Server-side throttle (one atomic SET NX) ──────────────────────
        # EN_ROUTE is 1500 ms (not 2000) so client jitter doesn't drop every
        # other ping from a client that sends every ~2 s.
        if job_status_upper == "EN_ROUTE":
            interval_ms = 1500
        elif job_status_upper in {"ON_SITE", "IN_PROGRESS", "ACTIVE"}:
            interval_ms = 5000
        else:
            interval_ms = 30000

        try:
            allowed = redis_client.set(throttle_key, "1", nx=True, px=interval_ms)
        except Exception as e:
            logger.warning(f"GPS throttle Redis error; allowing ping: {e}", extra=log_extra)
            allowed = True

        if not allowed:
            # No 429, no DB row: the client may keep sending; we drop duplicates silently.
            return _skipped(payload.technician_id, payload.job_id, interval_ms=interval_ms)

        # ── 8. Build the live update BEFORE touching the DB transaction ──────
        tenant_id = tech.tenant_id or x_tenant_id
        eta, eta_minutes = _read_eta(redis_client, payload.technician_id, payload.job_id)

        update_payload = _build_update(
            technician_id=payload.technician_id,
            technician_name=getattr(tech, "technician_name", None),
            job_id=payload.job_id,
            tenant_id=tenant_id,
            latitude=payload.latitude,
            longitude=payload.longitude,
            accuracy=payload.accuracy,
            altitude=payload.altitude,
            job_status=job.status,
            timestamp=payload.timestamp,
            eta=eta,
            eta_minutes=eta_minutes,
            source="live",
        )

        # ── 9. FAST PATH: snapshot + publish BEFORE the DB commit ────────────
        try:
            _store_latest(redis_client, update_payload)
            _publish_updates(redis_client, [update_payload])
            _mark_broadcast(redis_client, update_payload)   # scheduler won't resend this ping
        except Exception as e:
            logger.warning(f"Failed to publish GPS ping to Redis: {e}", extra=log_extra)

        # ── 10. Persist history AFTER the live publish ───────────────────────
        ping_id = str(uuid.uuid4())
        db_ping = models.GPSPing(
            id=ping_id,
            technician_id=payload.technician_id,
            job_id=payload.job_id,
            latitude=payload.latitude,
            longitude=payload.longitude,
            timestamp=payload.timestamp,
            accuracy=payload.accuracy,
            altitude=payload.altitude,
            tenant_id=tenant_id,
            ip_address=client_host,
            user_agent=user_agent,
            correlation_id=correlation_id,
        )
        db.add(db_ping)

        # Race-condition protection before committing history.
        db.refresh(job)
        if _job_status_upper(job) in {"CLOSED", "CANCELLED", "CANCELED"}:
            db.rollback()
            log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id,
                              "Job status changed during processing")
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"detail": "Job status changed during processing", "status": 409},
            )

        db.commit()

        logger.info(
            "GPS ping published and stored",
            extra={
                "ping_id": ping_id,
                "technician_id": payload.technician_id,
                "job_id": payload.job_id,
                "timestamp": update_payload["timestamp"],
                "correlation_id": correlation_id,
                "tenant_id": tenant_id,
            },
        )

        return {
            "status": "stored",
            "ping_id": ping_id,
            "timestamp": payload.timestamp,
            "technician_id": payload.technician_id,
            "job_id": payload.job_id,
        }

    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# /batch  (offline sync)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/batch", status_code=207)
async def gps_batch(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    authorization: str = Depends(verify_jwt_token),
    redis_client=Depends(get_redis_client),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    if current_user.tenant_id != x_tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access denied")
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    log_extra = {"correlation_id": correlation_id, "tenant_id": x_tenant_id}

    try:
        body_bytes = await request.body()
        body = json.loads(body_bytes.decode("utf-8"))
    except json.JSONDecodeError as jde:
        logger.error(f"Malformed JSON payload: {jde}", extra=log_extra)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Malformed JSON", "message": "The request body is not valid JSON"},
        )
    except Exception as e:
        logger.error(f"Error reading request body: {e}", extra=log_extra)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Bad request", "message": str(e)},
        )

    if not isinstance(body, dict) or "pings" not in body:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Pings array cannot be empty"},
        )

    pings = body.get("pings")
    if not isinstance(pings, list) or len(pings) == 0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Pings array cannot be empty"},
        )

    if len(pings) > 100:
        return JSONResponse(status_code=413, content={"detail": "Maximum 100 pings per batch"})

    try:
        schemas.GPSBatchRequest(**body)
    except Exception as e:
        msg = str(e)
        if "Value error, " in msg:
            msg = msg.split("Value error, ", 1)[1]
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": msg})

    logger.info(f"Received GPS batch insert request with {len(pings)} pings", extra=log_extra)

    def get_validation_error_reason(ve) -> str:
        if hasattr(ve, "errors"):
            for err in ve.errors():
                msg = err.get("msg", "")
                if msg.startswith("Value error, "):
                    msg = msg[len("Value error, "):]
                try:
                    custom_errs = json.loads(msg)
                    if isinstance(custom_errs, list) and len(custom_errs) > 0:
                        return custom_errs[0][1]
                except Exception:
                    pass
                if msg:
                    return msg
        msg = str(ve)
        if "Value error, " in msg:
            msg = msg.split("Value error, ", 1)[1]
        try:
            custom_errs = json.loads(msg)
            if isinstance(custom_errs, list) and len(custom_errs) > 0:
                return custom_errs[0][1]
        except Exception:
            pass
        return msg

    # Rate limit: max 1 batch request per 5 seconds per technician
    tech_ids = set()
    for ping in pings:
        if isinstance(ping, dict) and "technician_id" in ping:
            tech_ids.add(ping["technician_id"])

    for tech_id in tech_ids:
        if tech_id and not check_batch_sliding_window_rate_limit(redis_client, tech_id, x_tenant_id):
            logger.warning(f"Rate limit exceeded for technician: {tech_id}", extra=log_extra)
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too Many Requests")

    errors = []
    validated_pings = []
    seen_timestamps = set()

    # Phase 1: schema + duplicate timestamp validation
    for i, ping in enumerate(pings):
        if not isinstance(ping, dict):
            errors.append({"index": i, "reason": "Ping must be a JSON object"})
            continue

        try:
            payload = schemas.GPSPingRequest(**ping)
        except Exception as ve:
            errors.append({"index": i, "reason": get_validation_error_reason(ve)})
            continue

        key = (payload.technician_id, payload.timestamp)
        if key in seen_timestamps:
            errors.append({"index": i, "reason": "Duplicate timestamp within batch"})
            continue
        seen_timestamps.add(key)

        validated_pings.append((i, payload))

    db = _open_db(request.app.dependency_overrides.get(get_db, get_db))

    try:
        # Phase 2: technician + job existence / authorization
        tech_ids_to_check = list({p[1].technician_id for p in validated_pings})
        job_ids_to_check = list({p[1].job_id for p in validated_pings})

        tech_records = db.query(models.Technician).filter(
            models.Technician.tech_id.in_(tech_ids_to_check)
        ).all()
        tech_map = {t.tech_id: t for t in tech_records}

        numeric_job_ids = [int(j) for j in job_ids_to_check if str(j).isdigit()]
        job_records = db.query(models.Job).filter(models.Job.id.in_(numeric_job_ids)).all()
        job_map = {str(j.id): j for j in job_records}

        insert_dicts = []

        for i, payload in validated_pings:
            tech = tech_map.get(payload.technician_id)
            if not tech:
                log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, "Technician not found")
                errors.append({"index": i, "reason": "Technician not found"})
                continue

            try:
                _enforce_gps_actor(current_user, x_tenant_id, tech)
            except HTTPException:
                log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, "Access denied for technician")
                errors.append({"index": i, "reason": "Access denied for technician"})
                continue

            if tech.tenant_id and tech.tenant_id != x_tenant_id:
                log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, "Access denied for technician")
                errors.append({"index": i, "reason": "Access denied for technician"})
                continue

            job = job_map.get(str(payload.job_id))
            if not job:
                log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, "Job not found")
                errors.append({"index": i, "reason": "Job not found"})
                continue

            if job.tenant_id and job.tenant_id != x_tenant_id:
                log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, "Access denied for job")
                errors.append({"index": i, "reason": "Access denied for job"})
                continue

            if _job_status_upper(job) not in ACTIVE_STATUSES:
                log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, f"Job status is {job.status}")
                errors.append({"index": i, "reason": "Job status is not active"})
                continue

            # Assignment enforced for every active status (legacy "active" included).
            if job.assigned_technician_id != tech.technician_id:
                log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, "Technician not assigned to job")
                errors.append({"index": i, "reason": "Technician not assigned to job"})
                continue

            insert_dicts.append({
                "id": str(uuid.uuid4()),
                "technician_id": payload.technician_id,
                "job_id": payload.job_id,
                "latitude": payload.latitude,
                "longitude": payload.longitude,
                "timestamp": payload.timestamp,
                "accuracy": payload.accuracy,
                "altitude": payload.altitude,
                "tenant_id": tech.tenant_id or x_tenant_id,
                "ip_address": request.client.host if request.client else None,
                "user_agent": request.headers.get("User-Agent"),
                "correlation_id": correlation_id,
            })

        # Roll back on any validation failure
        if errors:
            db.rollback()
            errors.sort(key=lambda x: x["index"])
            total = len(pings)
            failed = len(errors)
            logger.warning(f"GPS batch insert failed validation with {failed} errors. Rolling back.", extra=log_extra)
            return JSONResponse(
                status_code=207,
                content={"total": total, "succeeded": total - failed, "failed": failed, "errors": errors},
            )

        # Race-condition prevention: refresh jobs right before commit
        for j in job_records:
            db.refresh(j)
            if _job_status_upper(j) in {"CLOSED", "CANCELLED", "CANCELED"}:
                db.rollback()
                for _, payload in validated_pings:
                    if str(payload.job_id) == str(j.id):
                        log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id,
                                          "Job status changed during processing")
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content={"detail": "Job status changed during processing", "status": 409},
                )

        # Insert ALL pings into history
        from sqlalchemy import insert
        if insert_dicts:
            db.execute(insert(models.GPSPing), insert_dicts)
            db.commit()

            # Live publish: only the NEWEST ping per (technician, job), and only if it is
            # recent. Offline-sync batches must not replay old positions as if they were live.
            try:
                cutoff = datetime.now(timezone.utc) - timedelta(seconds=BATCH_MAX_AGE_S)
                newest = {}
                for d in insert_dicts:
                    k = (d["technician_id"], str(d["job_id"]))
                    ts = as_utc(d["timestamp"])
                    if k not in newest or ts > newest[k][0]:
                        newest[k] = (ts, d)

                updates = []
                for ts, d in newest.values():
                    if ts < cutoff:
                        continue
                    job = job_map.get(str(d["job_id"]))
                    tech = tech_map.get(d["technician_id"])
                    eta, eta_minutes = _read_eta(redis_client, d["technician_id"], d["job_id"])
                    update = _build_update(
                        technician_id=d["technician_id"],
                        technician_name=getattr(tech, "technician_name", None),
                        job_id=d["job_id"],
                        tenant_id=d["tenant_id"],
                        latitude=d["latitude"],
                        longitude=d["longitude"],
                        accuracy=d["accuracy"],
                        altitude=d["altitude"],
                        job_status=job.status if job else "ASSIGNED",
                        timestamp=d["timestamp"],
                        eta=eta or "calculating...",
                        eta_minutes=eta_minutes,
                        source="batch",
                    )
                    # Keep gps:latest fresh, but never let an older batch ping overwrite
                    # a newer live snapshot; and don't publish it either.
                    if _store_latest(redis_client, update, only_if_newer=True):
                        _mark_broadcast(redis_client, update)
                        updates.append(update)

                if updates:
                    _publish_updates(redis_client, updates)
            except Exception as e:
                logger.warning(f"Failed to publish GPS batch to Redis: {e}")

            for d in insert_dicts:
                logger.info(
                    "GPS ping stored in audit trail via batch",
                    extra={
                        "ping_id": d["id"],
                        "technician_id": d["technician_id"],
                        "job_id": d["job_id"],
                        "timestamp": iso_utc(d["timestamp"]) if isinstance(d["timestamp"], datetime) else d["timestamp"],
                        "ip_address": d["ip_address"],
                        "user_agent": d["user_agent"],
                        "correlation_id": correlation_id,
                        "tenant_id": d["tenant_id"],
                    },
                )

        logger.info(f"Successfully processed GPS batch insert for {len(insert_dicts)} pings", extra=log_extra)
        return JSONResponse(
            status_code=207,
            content={"total": len(pings), "succeeded": len(pings), "failed": 0, "errors": []},
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Database error during batch insert: {e}", extra=log_extra)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database insertion failed")
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# /availability  (pre-assignment location for the Planning Agent; not job tracking)
# ─────────────────────────────────────────────────────────────────────────────
@router.post("/availability", status_code=status.HTTP_200_OK)
async def update_technician_availability_location(
    payload: TechnicianAvailabilityLocationRequest,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    redis_client=Depends(get_redis_client),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Store the technician's latest location before job assignment."""

    if str(current_user.tenant_id) != str(x_tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")

    if str(current_user.role).lower() != "technician":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only technicians can update availability location",
        )

    if not -90 <= payload.latitude <= 90:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid latitude")

    if not -180 <= payload.longitude <= 180:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid longitude")

    max_accuracy = float(os.getenv("GPS_MAX_ACCURACY_METERS", "100"))
    if payload.accuracy is not None and payload.accuracy > max_accuracy:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"GPS accuracy {payload.accuracy:.1f}m exceeds allowed {max_accuracy:.0f}m",
        )

    technician_id = str(current_user.user_id)
    tenant_id = str(current_user.tenant_id)

    redis_key = f"gps:availability:{tenant_id}:{technician_id}"

    location_data = {
        "technician_id": technician_id,
        "tenant_id": tenant_id,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "accuracy": payload.accuracy,
        "altitude": payload.altitude,
        "timestamp": iso_utc(payload.timestamp),
    }

    redis_client.setex(redis_key, 120, json.dumps(location_data))

    return {
        "status": "stored",
        "technician_id": technician_id,
        "latitude": payload.latitude,
        "longitude": payload.longitude,
        "accuracy": payload.accuracy,
        "timestamp": payload.timestamp,
        "expires_in_seconds": 120,
    }