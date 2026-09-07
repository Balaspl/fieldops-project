from fastapi import APIRouter, Depends, HTTPException, Header, status, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import uuid
import json
import time
import logging
import msgpack

from ..database import get_db
from ..redis_client import get_redis_client
from ..logger import logger
from .. import models, schemas
from .dispatch import verify_jwt_token

router = APIRouter(
    prefix="/api/v1/gps",
    tags=["GPS"]
)

def check_sliding_window_rate_limit(redis_client, technician_id: str, tenant_id: str) -> bool:
    """
    Checks if a technician has exceeded the rate limit.
    Enforces max 1 ping per 30 seconds per technician using a sliding window in Redis.
    """
    global redis_failures_count
    if redis_failures_count >= 3:
        return True
    now = time.time()
    window = 30
    limit = 1
    key = f"rate_limit:gps:{tenant_id}:{technician_id}"
    
    try:
        # Remove elements older than the sliding window
        redis_client.zremrangebyscore(key, 0, now - window)
        # Count remaining requests in the window
        count = redis_client.zcard(key)
        
        if count >= limit:
            return False
            
        # Add the current request timestamp with a unique identifier to prevent collisions
        member = f"{now}:{uuid.uuid4().hex}"
        redis_client.zadd(key, {member: now})
        # Set expire to clean up the key after sliding window passes
        redis_client.expire(key, 60)
        return True
    except Exception as e:
        logger.warning(f"Redis rate limiter connection issue: {e}. Falling back to allowing request.")
        return True

redis_failures_count = 0

def log_rejected_ping(db: Session, technician_id: str, job_id: str, tenant_id: str, reason: str):
    try:
        rejected_log = models.GPSRejectedPingLog(
            technician_id=technician_id,
            job_id=str(job_id) if job_id else None,
            reason=reason,
            tenant_id=tenant_id
        )
        db.add(rejected_log)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to log rejected ping: {e}")

def check_and_set_interval(redis_client, db: Session, tenant_id: str, technician_id: str, job_id: str, correlation_id: str) -> tuple[bool, int, str]:
    global redis_failures_count
    interval_key = f"gps:interval:{tenant_id}:{technician_id}:{job_id}"
    
    use_fallback = (redis_failures_count >= 3)
    
    if not use_fallback:
        try:
            if redis_client.exists(interval_key):
                ttl = redis_client.ttl(interval_key)
                if ttl <= 0:
                    ttl = 30
                redis_failures_count = 0
                return False, ttl, "redis"
            redis_client.setex(interval_key, 30, "1")
            redis_failures_count = 0
            return True, 0, "redis"
        except Exception as e:
            redis_failures_count += 1
            logger.warning(f"Redis connection failure in interval check ({redis_failures_count}/3): {e}")
            use_fallback = True
            
    if use_fallback:
        last_ping = db.query(models.GPSPing).filter(
            models.GPSPing.technician_id == technician_id,
            models.GPSPing.job_id == str(job_id)
        ).order_by(models.GPSPing.timestamp.desc()).first()
        
        if last_ping:
            now = datetime.now(timezone.utc)
            last_time = last_ping.timestamp
            if last_time.tzinfo is None:
                last_time = last_time.replace(tzinfo=timezone.utc)
            delta = (now - last_time).total_seconds()
            if delta < 30:
                retry_after = int(30 - delta)
                if retry_after <= 0:
                    retry_after = 1
                return False, retry_after, "fallback"
                
        return True, 0, "fallback"

from typing import Optional

@router.get("/history/{technician_id}", response_model=list[schemas.GPSPingResponse])
def get_gps_history(
    technician_id: str,
    job_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    db: Session = Depends(get_db),
    authorization: str = Depends(verify_jwt_token)
):
    query = db.query(models.GPSPing).filter(models.GPSPing.technician_id == technician_id)
    if x_tenant_id:
        query = query.filter(models.GPSPing.tenant_id == x_tenant_id)
    
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
            created_at=p.created_at
        )
        for p in pings
    ]

@router.post("/ping", status_code=status.HTTP_201_CREATED, response_model=schemas.GPSPingResponse)
async def gps_ping(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    authorization: str = Depends(verify_jwt_token),
    redis_client = Depends(get_redis_client),
    bypass_interval: bool = False
):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    log_extra = {"correlation_id": correlation_id, "tenant_id": x_tenant_id}

    # Gracefully parse the JSON body to handle decode errors
    try:
        body_bytes = await request.body()
        body_str = body_bytes.decode("utf-8")
        body = json.loads(body_str)
    except json.JSONDecodeError as jde:
        logger.error(f"Malformed JSON payload: {jde}", extra=log_extra)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Malformed JSON", "message": "The request body is not valid JSON"}
        )
    except Exception as e:
        logger.error(f"Error reading request body: {e}", extra=log_extra)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Bad request", "message": str(e)}
        )

    # Validate schema fields (runs before database session is acquired)
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
                    # Attempt to parse msg as JSON list of (field, message)
                    custom_errors = json.loads(msg)
                    if isinstance(custom_errors, list):
                        for field, field_msg in custom_errors:
                            formatted_errors.append({
                                "loc": ["body", field],
                                "msg": field_msg,
                                "type": "value_error"
                            })
                        custom_parsed = True
                except Exception:
                    pass
            
            if not custom_parsed:
                # Fallback for standard Pydantic errors
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
                        "type": err.get("type", "value_error")
                    })
        else:
            formatted_errors = [{"loc": ["body"], "msg": str(ve), "type": "value_error"}]
            
        return JSONResponse(
            status_code=422,
            content={"detail": formatted_errors}
        )

    # Acquire database session only AFTER validation passes (uses overrides if present in test environment)
    db_dep = request.app.dependency_overrides.get(get_db, get_db)
    db_res = db_dep()
    if hasattr(db_res, "__next__") or hasattr(db_res, "__iter__"):
        db = next(db_res)
    else:
        db = db_res
    try:
        # Verify technician existence & tenant isolation
        tech = db.query(models.Technician).filter(models.Technician.tech_id == payload.technician_id).first()
        if not tech:
            logger.error(f"Technician not found: {payload.technician_id}", extra=log_extra)
            log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, "Technician not found")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Technician not found")

        if tech.tenant_id and tech.tenant_id != x_tenant_id:
            logger.error(f"Access denied: technician {payload.technician_id} belongs to different tenant", extra=log_extra)
            log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, "Access denied for technician")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        # Verify job existence & tenant isolation
        job = None
        if str(payload.job_id).isdigit():
            job = db.query(models.Job).filter(models.Job.id == int(payload.job_id)).first()
        if not job:
            logger.error(f"Job not found: {payload.job_id}", extra=log_extra)
            log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, "Job not found")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

        if job.tenant_id and job.tenant_id != x_tenant_id:
            logger.error(f"Access denied: job {payload.job_id} belongs to different tenant", extra=log_extra)
            log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, "Access denied for job")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        # Active Job Gating
        is_legacy_active = (job.status.lower() == "active")
        
        if not is_legacy_active:
            active_statuses = ["ASSIGNED", "EN_ROUTE", "ON_SITE"]
            job_status_upper = job.status.upper().strip()
            if job_status_upper not in active_statuses:
                logger.error(f"Job status outside active window: {job.status}", extra=log_extra)
                log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, f"Job status is {job.status}")
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Job status is not active")

            if job.assigned_technician_id != tech.technician_id:
                logger.error(f"Technician {payload.technician_id} not assigned to job {payload.job_id}", extra=log_extra)
                log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, "Technician not assigned to job")
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Technician not assigned to job")
        else:
            if job.status.lower() != "active":
                logger.error(f"Job status not active: {job.status}", extra=log_extra)
                log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, f"Job status is {job.status}")
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Job status is not active")

        job_status_upper = job.status.upper().strip()

        # Enforce 30-second interval gating
        if not bypass_interval and not is_legacy_active:
            # Check and handle job status transition to reset interval key
            current_status = job_status_upper
            status_key = f"gps:job_status:{payload.job_id}"
            interval_key = f"gps:interval:{x_tenant_id}:{payload.technician_id}:{payload.job_id}"
            if redis_client and redis_failures_count < 3:
                try:
                    last_status = redis_client.get(status_key)
                    if last_status != current_status:
                        redis_client.delete(interval_key)
                        redis_client.set(status_key, current_status, ex=86400)
                except Exception:
                    pass

            allowed, retry_after, mode = check_and_set_interval(
                redis_client, db, x_tenant_id, payload.technician_id, payload.job_id, correlation_id
            )
            if not allowed:
                if mode == "redis":
                    reason = "GPS ping interval minimum 30 seconds"
                    log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, reason)
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        headers={"Retry-After": str(retry_after)},
                        content={"detail": reason, "retry_after": retry_after, "status": 429}
                    )
                else:
                    reason = "GPS ping interval minimum 30 seconds (fallback mode)"
                    log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, reason)
                    return JSONResponse(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        headers={"Retry-After": str(retry_after)},
                        content={"detail": reason, "status": 429}
                    )

        # Enforce rate limiting: max 1 ping per 30 seconds per technician
        rate_limit_allowed = check_sliding_window_rate_limit(redis_client, payload.technician_id, x_tenant_id)
        if not rate_limit_allowed:
            logger.warning(f"Rate limit exceeded for technician: {payload.technician_id}", extra=log_extra)
            log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, "Too Many Requests (rate limit)")
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too Many Requests")

        # Insert into database with tenant_id isolation from technician record
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
            tenant_id=tech.tenant_id or x_tenant_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
            correlation_id=correlation_id
        )
        db.add(db_ping)

        # Capture ping attributes before commit to avoid ObjectDeletedError
        # after the after_insert event runs in a separate session
        ping_technician_id = db_ping.technician_id
        ping_job_id = db_ping.job_id
        ping_tenant_id = db_ping.tenant_id
        ping_latitude = db_ping.latitude
        ping_longitude = db_ping.longitude
        ping_accuracy = db_ping.accuracy
        ping_altitude = db_ping.altitude
        ping_timestamp = db_ping.timestamp
        ping_ip_address = request.client.host if request.client else None
        ping_user_agent = request.headers.get("User-Agent")

        # Race Condition Prevention: Refresh job right before commit
        db.refresh(job)
        if job.status.upper().strip() in ["CLOSED", "CANCELLED", "CANCELED"]:
            db.rollback()
            log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, "Job status changed during processing")
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={"detail": "Job status changed during processing", "status": 409}
            )

        db.commit()

        try:
            update_payload = {
                "type": "position_update",
                "technician_id": ping_technician_id,
                "job_id": ping_job_id,
                "tenant_id": ping_tenant_id,
                "latitude": float(ping_latitude),
                "longitude": float(ping_longitude),
                "accuracy": float(ping_accuracy) if ping_accuracy is not None else None,
                "altitude": float(ping_altitude) if ping_altitude is not None else None,
                "job_status": job.status if job else "ASSIGNED",
                "eta": "calculating...",
                "eta_duration_minutes": None,
                "timestamp": ping_timestamp.isoformat() if hasattr(ping_timestamp, "isoformat") else str(ping_timestamp),
                "broadcast_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                eta_key = f"eta:{ping_technician_id}:{ping_job_id}"
                eta_raw = redis_client.get(eta_key)
                if eta_raw:
                    eta_data = json.loads(eta_raw)
                    update_payload["eta"] = eta_data.get("eta", "calculating...")
                    update_payload["eta_duration_minutes"] = eta_data.get("duration_minutes")
            except Exception:
                pass

            envelope = {
                "type": "position_batch",
                "count": 1,
                "updates": [update_payload],
                "broadcast_cycle_at": datetime.now(timezone.utc).isoformat(),
            }
            compressed = msgpack.packb(envelope, use_bin_type=True)
            redis_client.publish("gps:updates", compressed)
        except Exception as e:
            logger.warning(f"Failed to publish GPS ping to Redis: {e}")

        # Log incoming pings to audit trail with correlation ID
        logger.info(
            "GPS ping stored in audit trail",
            extra={
                "ping_id": ping_id,
                "technician_id": ping_technician_id,
                "job_id": ping_job_id,
                "timestamp": payload.timestamp.isoformat(),
                "ip_address": ping_ip_address,
                "user_agent": ping_user_agent,
                "correlation_id": correlation_id,
                "tenant_id": ping_tenant_id
            }
        )

        return {
            "status": "stored",
            "ping_id": ping_id,
            "timestamp": payload.timestamp,
            "technician_id": payload.technician_id,
            "job_id": payload.job_id
        }
    finally:
        db.close()


def check_batch_sliding_window_rate_limit(redis_client, technician_id: str, tenant_id: str) -> bool:
    """
    Checks if a technician has exceeded the batch rate limit.
    Enforces max 1 batch request per 5 seconds per technician using a sliding window in Redis.
    """
    global redis_failures_count
    if redis_failures_count >= 3:
        return True
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


@router.post("/batch", status_code=207)
async def gps_batch(
    request: Request,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    authorization: str = Depends(verify_jwt_token),
    redis_client = Depends(get_redis_client)
):
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    log_extra = {"correlation_id": correlation_id, "tenant_id": x_tenant_id}

    # Gracefully parse the JSON body to handle decode errors
    try:
        body_bytes = await request.body()
        body_str = body_bytes.decode("utf-8")
        body = json.loads(body_str)
    except json.JSONDecodeError as jde:
        logger.error(f"Malformed JSON payload: {jde}", extra=log_extra)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Malformed JSON", "message": "The request body is not valid JSON"}
        )
    except Exception as e:
        logger.error(f"Error reading request body: {e}", extra=log_extra)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Bad request", "message": str(e)}
        )

    # Basic request-level checks before parsing items
    if not isinstance(body, dict) or "pings" not in body:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Pings array cannot be empty"}
        )
        
    pings = body.get("pings")
    if not isinstance(pings, list) or len(pings) == 0:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "Pings array cannot be empty"}
        )

    if len(pings) > 100:
        return JSONResponse(
            status_code=413,
            content={"detail": "Maximum 100 pings per batch"}
        )

    # Validate with Pydantic GPSBatchRequest schema to verify schema is satisfied
    try:
        schemas.GPSBatchRequest(**body)
    except Exception as e:
        # If schema itself fails validation, extract reason
        msg = str(e)
        if "Value error, " in msg:
            msg = msg.split("Value error, ", 1)[1]
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": msg}
        )

    logger.info(f"Received GPS batch insert request with {len(pings)} pings", extra=log_extra)

    # Helper function to extract validation error reason
    def get_validation_error_reason(ve) -> str:
        if hasattr(ve, "errors"):
            pydantic_errors = ve.errors()
            for err in pydantic_errors:
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

    # Enforce rate limiting: max 1 batch request per 5 seconds per technician
    # Get all unique technician IDs to apply rate limit
    tech_ids = set()
    for ping in pings:
        if isinstance(ping, dict) and "technician_id" in ping:
            tech_ids.add(ping["technician_id"])
            
    for tech_id in tech_ids:
        if tech_id:
            rate_limit_allowed = check_batch_sliding_window_rate_limit(redis_client, tech_id, x_tenant_id)
            if not rate_limit_allowed:
                logger.warning(f"Rate limit exceeded for technician: {tech_id}", extra=log_extra)
                raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Too Many Requests")

    errors = []
    validated_pings = []
    seen_timestamps = set()

    # Phase 1: Coordinate range, type, null/missing, and duplicate timestamp validation
    for i, ping in enumerate(pings):
        if not isinstance(ping, dict):
            errors.append({"index": i, "reason": "Ping must be a JSON object"})
            continue
            
        try:
            payload = schemas.GPSPingRequest(**ping)
        except Exception as ve:
            reason = get_validation_error_reason(ve)
            errors.append({"index": i, "reason": reason})
            continue

        tech_id = payload.technician_id
        timestamp = payload.timestamp
        key = (tech_id, timestamp)
        if key in seen_timestamps:
            errors.append({"index": i, "reason": "Duplicate timestamp within batch"})
            continue
        seen_timestamps.add(key)

        validated_pings.append((i, payload))

    # Acquire database session (uses overrides if present in test environment)
    db_dep = request.app.dependency_overrides.get(get_db, get_db)
    db_res = db_dep()
    if hasattr(db_res, "__next__") or hasattr(db_res, "__iter__"):
        db = next(db_res)
    else:
        db = db_res

    # Use a try-finally block to ensure DB session is closed
    try:
        # Phase 2: Technician and Job existence validation (Only for pings that passed Phase 1)
        tech_ids_to_check = list({p[1].technician_id for p in validated_pings})
        job_ids_to_check = list({p[1].job_id for p in validated_pings})

        # Batch query technicians
        tech_records = db.query(models.Technician).filter(models.Technician.tech_id.in_(tech_ids_to_check)).all()
        tech_map = {t.tech_id: t for t in tech_records}

        # Batch query jobs
        numeric_job_ids = []
        for jid in job_ids_to_check:
            if str(jid).isdigit():
                numeric_job_ids.append(int(jid))
        job_records = db.query(models.Job).filter(models.Job.id.in_(numeric_job_ids)).all()
        job_map = {str(j.id): j for j in job_records}

        insert_dicts = []

        for i, payload in validated_pings:
            tech = tech_map.get(payload.technician_id)
            if not tech:
                log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, "Technician not found")
                errors.append({"index": i, "reason": "Technician not found"})
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

            # Active Job Gating
            is_legacy_active = (job.status.lower() == "active")
            if not is_legacy_active:
                active_statuses = ["ASSIGNED", "EN_ROUTE", "ON_SITE"]
                if job.status.upper().strip() not in active_statuses:
                    log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, f"Job status is {job.status}")
                    errors.append({"index": i, "reason": "Job status is not active"})
                    continue

                if job.assigned_technician_id != tech.technician_id:
                    log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, "Technician not assigned to job")
                    errors.append({"index": i, "reason": "Technician not assigned to job"})
                    continue
            else:
                if job.status.lower() != "active":
                    log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, "Job status is not active")
                    errors.append({"index": i, "reason": "Job status is not active"})
                    continue

            # Build dict for optimized insert
            ping_id = str(uuid.uuid4())
            insert_dicts.append({
                "id": ping_id,
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
                "correlation_id": correlation_id
            })

        # Rollback transaction on any validation failure
        if errors:
            db.rollback()
            errors.sort(key=lambda x: x["index"])
            total = len(pings)
            failed = len(errors)
            succeeded = total - failed
            logger.warning(f"GPS batch insert failed validation with {failed} errors. Rolling back.", extra=log_extra)
            return JSONResponse(
                status_code=207,
                content={
                    "total": total,
                    "succeeded": succeeded,
                    "failed": failed,
                    "errors": errors
                }
            )

        # Race Condition Prevention: Refresh all jobs right before execute/commit
        for j in job_records:
            db.refresh(j)
            if j.status.upper().strip() in ["CLOSED", "CANCELLED", "CANCELED"]:
                db.rollback()
                # Log rejected pings for all pings in this batch associated with this job
                for i, payload in validated_pings:
                    if str(payload.job_id) == str(j.id):
                        log_rejected_ping(db, payload.technician_id, payload.job_id, x_tenant_id, "Job status changed during processing")
                return JSONResponse(
                    status_code=status.HTTP_409_CONFLICT,
                    content={"detail": "Job status changed during processing", "status": 409}
                )

        # No errors: insert and commit
        from sqlalchemy import insert
        if insert_dicts:
            db.execute(insert(models.GPSPing), insert_dicts)
            db.commit()

            try:
                updates = []
                for d in insert_dicts:
                    job = job_map.get(str(d["job_id"]))
                    update_payload = {
                        "type": "position_update",
                        "technician_id": d["technician_id"],
                        "job_id": d["job_id"],
                        "tenant_id": d["tenant_id"],
                        "latitude": float(d["latitude"]),
                        "longitude": float(d["longitude"]),
                        "accuracy": float(d["accuracy"]) if d["accuracy"] is not None else None,
                        "altitude": float(d["altitude"]) if d["altitude"] is not None else None,
                        "job_status": job.status if job else "ASSIGNED",
                        "eta": "calculating...",
                        "eta_duration_minutes": None,
                        "timestamp": d["timestamp"].isoformat() if hasattr(d["timestamp"], "isoformat") else str(d["timestamp"]),
                        "broadcast_at": datetime.now(timezone.utc).isoformat(),
                    }
                    try:
                        eta_key = f"eta:{d['technician_id']}:{d['job_id']}"
                        eta_raw = redis_client.get(eta_key)
                        if eta_raw:
                            eta_data = json.loads(eta_raw)
                            update_payload["eta"] = eta_data.get("eta", "calculating...")
                            update_payload["eta_duration_minutes"] = eta_data.get("duration_minutes")
                    except Exception:
                        pass
                    updates.append(update_payload)

                if updates:
                    envelope = {
                        "type": "position_batch",
                        "count": len(updates),
                        "updates": updates,
                        "broadcast_cycle_at": datetime.now(timezone.utc).isoformat(),
                    }
                    compressed = msgpack.packb(envelope, use_bin_type=True)
                    redis_client.publish("gps:updates", compressed)
            except Exception as e:
                logger.warning(f"Failed to publish GPS batch to Redis: {e}")
            
            # Log audit trail for all successful batch pings
            for d in insert_dicts:
                logger.info(
                    "GPS ping stored in audit trail via batch",
                    extra={
                        "ping_id": d["id"],
                        "technician_id": d["technician_id"],
                        "job_id": d["job_id"],
                        "timestamp": d["timestamp"].isoformat() if isinstance(d["timestamp"], datetime) else d["timestamp"],
                        "ip_address": d["ip_address"],
                        "user_agent": d["user_agent"],
                        "correlation_id": correlation_id,
                        "tenant_id": d["tenant_id"]
                    }
                )

        logger.info(f"Successfully processed GPS batch insert for {len(insert_dicts)} pings", extra=log_extra)
        return JSONResponse(
            status_code=207,
            content={
                "total": len(pings),
                "succeeded": len(pings),
                "failed": 0,
                "errors": []
            }
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Database error during batch insert: {e}", extra=log_extra)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database insertion failed")
    finally:
        db.close()


