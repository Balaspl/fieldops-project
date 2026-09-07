from fastapi import APIRouter, Depends, HTTPException, status, Header
from pydantic import BaseModel, Field
from typing import List
import logging
from sqlalchemy.orm import Session

from ..database import get_db
from ..redis_client import get_redis_client
from ..services.google_maps_client import GoogleMapsClient, MapsAPIException
from ..services.eta_service import ETAService
from ..routes.dispatch import verify_jwt_token
from .. import models

logger = logging.getLogger("fieldops")

router = APIRouter(tags=["ETA"])

class Coordinate(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)

class GPSBatchRouteRequest(BaseModel):
    origins: List[Coordinate]
    destinations: List[Coordinate]

class ETABatchRequest(BaseModel):
    technician_ids: List[str]
    job_id: int


@router.get("/api/v1/gps/route", response_model=dict)
async def get_route(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    redis_client = Depends(get_redis_client)
):
    """
    Returns driving route distance (meters) and duration (seconds) with traffic consideration.
    """
    client = GoogleMapsClient(redis_client)
    try:
        result = await client.get_route_duration(origin_lat, origin_lng, dest_lat, dest_lng)
        return result
    except MapsAPIException as e:
        if e.status_code == "INVALID_REQUEST":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
        # Graceful fallback for quota exceeded or other maps failures
        return client._fallback_route(origin_lat, origin_lng, dest_lat, dest_lng)
    except Exception as exc:
        logger.error(f"Unexpected error in single route lookup: {exc}")
        return client._fallback_route(origin_lat, origin_lng, dest_lat, dest_lng)


@router.post("/api/v1/gps/route/batch", response_model=List[dict])
async def get_batch_route(
    payload: GPSBatchRouteRequest,
    redis_client = Depends(get_redis_client)
):
    """
    Calculates routes for multiple technicians to a job site in a single batch request (up to 10 pairs).
    """
    if not payload.origins or not payload.destinations:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Origins and destinations list cannot be empty"
        )

    total_pairs = len(payload.origins) * len(payload.destinations)
    if total_pairs > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 10 origin-destination pairs supported"
        )

    client = GoogleMapsClient(redis_client)
    origins_list = [(c.lat, c.lng) for c in payload.origins]
    destinations_list = [(c.lat, c.lng) for c in payload.destinations]

    try:
        results = await client.get_batch_route_durations(origins_list, destinations_list)
        return results
    except MapsAPIException as e:
        if e.status_code == "INVALID_REQUEST":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)
        # Fallback for all items
        dest_lat, dest_lng = destinations_list[0]
        return [client._fallback_route(o.lat, o.lng, dest_lat, dest_lng) for o in payload.origins]
    except Exception as exc:
        logger.error(f"Unexpected error in batch route lookup: {exc}")
        dest_lat, dest_lng = destinations_list[0]
        return [client._fallback_route(o.lat, o.lng, dest_lat, dest_lng) for o in payload.origins]


@router.get("/api/v1/dispatch/metrics/maps", response_model=dict)
async def get_maps_metrics(redis_client = Depends(get_redis_client)):
    """
    Returns metrics tracking calls, cache hits, and latency for Google Maps API requests.
    """
    try:
        calls = redis_client.get("metrics:maps_api_calls_total") or 0
        hits = redis_client.get("metrics:maps_api_cache_hits") or 0
        latency = redis_client.get("metrics:maps_api_latency_seconds") or 0.0

        return {
            "maps_api_calls_total": int(calls),
            "maps_api_cache_hits": int(hits),
            "maps_api_latency_seconds": float(latency)
        }
    except Exception as e:
        logger.error(f"Failed to fetch maps metrics: {e}")
        return {
            "maps_api_calls_total": 0,
            "maps_api_cache_hits": 0,
            "maps_api_latency_seconds": 0.0
        }


@router.get("/api/v1/dispatch/metrics/fallback", response_model=dict)
async def get_fallback_metrics(redis_client = Depends(get_redis_client)):
    """
    Returns metrics tracking fallback ETA requests by failure reason.
    """
    try:
        timeout = redis_client.get("metrics:fallback_eta_total:timeout") or 0
        quota = redis_client.get("metrics:fallback_eta_total:quota") or 0
        error = redis_client.get("metrics:fallback_eta_total:error") or 0

        return {
            "fallback_eta_total": {
                "timeout": int(timeout),
                "quota": int(quota),
                "error": int(error)
            }
        }
    except Exception as e:
        logger.error(f"Failed to fetch fallback metrics: {e}")
        return {
            "fallback_eta_total": {
                "timeout": 0,
                "quota": 0,
                "error": 0
            }
        }


@router.get("/api/v1/eta", response_model=dict)
async def get_technician_eta(
    technician_id: str,
    job_id: int,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    authorization: str = Depends(verify_jwt_token),
    redis_client = Depends(get_redis_client),
    db: Session = Depends(get_db)
):
    """
    Calculates live ETA for a single technician to a job site based on live GPS tracking.
    """
    # 1. Verify technician existence and tenant boundary
    tech = db.query(models.Technician).filter(models.Technician.tech_id == technician_id).first()
    if not tech:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Technician not found: {technician_id}"
        )
    if tech.tenant_id != x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    # 2. Verify job existence and tenant boundary
    job = db.query(models.Job).filter(models.Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    if job.tenant_id != x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    # 3. Perform ETA calculation
    maps_client = GoogleMapsClient(redis_client)
    eta_service = ETAService(db, redis_client, maps_client)
    result = await eta_service.calculate_eta(technician_id, job_id)
    return result


@router.post("/api/v1/eta/batch", response_model=List[dict])
async def get_batch_technician_eta(
    payload: ETABatchRequest,
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    authorization: str = Depends(verify_jwt_token),
    redis_client = Depends(get_redis_client),
    db: Session = Depends(get_db)
):
    """
    Calculates live ETAs for a batch of technicians to a single job site (up to 10 technicians).
    """
    if not payload.technician_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Technician IDs list cannot be empty"
        )

    if len(payload.technician_ids) > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 10 technicians supported per request"
        )

    # 1. Verify Job existence and tenant boundary
    job = db.query(models.Job).filter(models.Job.id == payload.job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    if job.tenant_id != x_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    # 2. Verify all technicians existence and tenant boundaries
    for tech_id in payload.technician_ids:
        tech = db.query(models.Technician).filter(models.Technician.tech_id == tech_id).first()
        if not tech:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Technician not found: {tech_id}"
            )
        if tech.tenant_id != x_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )

    # 3. Perform batch calculation
    maps_client = GoogleMapsClient(redis_client)
    eta_service = ETAService(db, redis_client, maps_client)
    results = await eta_service.calculate_batch_eta(payload.technician_ids, payload.job_id)
    return results
