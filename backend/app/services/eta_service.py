import json
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List
from fastapi import HTTPException, status

from .. import models
from ..services.google_maps_client import GoogleMapsClient, MapsAPIException
from .fallback_eta_service import FallbackETAService

class ETAService:
    def __init__(self, db, redis_client, maps_client: GoogleMapsClient):
        self.db = db
        self.redis = redis_client
        self.maps = maps_client

    async def calculate_eta(self, technician_id: str, job_id: int) -> dict:
        """
        Calculates real-time ETA for a technician to a job site based on latest GPS position.
        Caches predictions in Redis for 30 seconds.
        """
        cache_key = f"eta:{technician_id}:{job_id}"

        # 1. Check Redis cache
        if self.redis:
            try:
                cached = self.redis.get(cache_key)
                if cached:
                    return json.loads(cached)
                cached_fallback = self.redis.get(f"eta:fallback:{technician_id}:{job_id}")
                if cached_fallback:
                    return json.loads(cached_fallback)
            except Exception:
                pass

        # 2. Fetch Job site coordinates
        job = self.db.query(models.Job).filter(models.Job.id == job_id).first()
        if not job or job.site_latitude is None or job.site_longitude is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job site coordinates not found"
            )

        # 3. Fetch Technician and verify tenant isolation
        tech = self.db.query(models.Technician).filter(models.Technician.tech_id == technician_id).first()
        if not tech:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Technician not found: {technician_id}"
            )

        if tech.tenant_id != job.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant mismatch or access denied"
            )

        # 4. Fetch latest GPS ping
        
        latest_gps = (
            self.db.query(models.GPSPing)
            .filter(models.GPSPing.technician_id == technician_id)
            .order_by(models.GPSPing.timestamp.desc())
            .first()
        )

        now = datetime.now(timezone.utc)

        # Missing GPS
        if latest_gps is None:
            return {
                "status": "unknown",
                "technician_id": str(technician_id),
                "job_id": str(job_id),
                "last_known_location": {
                    "latitude": None,
                    "longitude": None,
                },
                "message": "No recent GPS data available",
                "calculated_at": now.isoformat().replace("+00:00", "Z"),
            }

        ping_time = latest_gps.timestamp
        if ping_time.tzinfo is None:
            ping_time = ping_time.replace(tzinfo=timezone.utc)

        is_stale = (now - ping_time).total_seconds() > 300

        if is_stale:
            return {
                "status": "unknown",
                "technician_id": str(technician_id),
                "job_id": str(job_id),
                "last_known_location": {
                    "latitude": latest_gps.latitude,
                    "longitude": latest_gps.longitude,
                },
                "message": "No recent GPS data available - last ping is stale",
                "calculated_at": now.isoformat().replace("+00:00", "Z"),
            }

        # 5. Fetch route duration
              
    
        
        try:
            route = await self.maps.get_route_duration(
                latest_gps.latitude,
                latest_gps.longitude,
                job.site_latitude,
                job.site_longitude
            )
        except Exception as exc:
            reason = "maps_error"
            metric_reason = "error"
            if isinstance(exc, MapsAPIException):
                status_code = exc.status_code
                if status_code == "maps_timeout":
                    reason = "maps_timeout"
                    metric_reason = "timeout"
                elif status_code in ("maps_quota", "OVER_QUERY_LIMIT"):
                    reason = "maps_quota"
                    metric_reason = "quota"
                elif status_code == "maps_unavailable":
                    reason = "maps_unavailable"
                    metric_reason = "error"
                else:
                    reason = "maps_error"
                    metric_reason = "error"
            elif isinstance(exc, asyncio.TimeoutError):
                reason = "maps_timeout"
                metric_reason = "timeout"

            fallback_service = FallbackETAService()
            fallback_res = fallback_service.calculate_fallback_eta(
                tech_lat=latest_gps.latitude,
                tech_lng=latest_gps.longitude,
                site_lat=job.site_latitude,
                site_lng=job.site_longitude,
                reason=reason
            )
            fallback_res["fallback_reason"] = reason
            fallback_res["status"] = "estimated"
            fallback_res["technician_id"] = str(technician_id)
            fallback_res["job_id"] = str(job_id)
            fallback_res["calculated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

            import logging
            logger = logging.getLogger("fieldops")
            logger.warning(
                "fallback_triggered",
                extra={
                    "reason": reason,
                    "technician_id": str(technician_id),
                    "job_id": str(job_id),
                    "estimated_duration": fallback_res["duration_minutes"]
                }
            )

            # Cache fallback longer due to lower accuracy
            fallback_key = f"eta:fallback:{technician_id}:{job_id}"
            if self.redis:
                try:
                    self.redis.setex(fallback_key, 60, json.dumps(fallback_res))
                    print(self.redis.get(fallback_key))
                except Exception:
                    pass

            # Metrics
            if self.redis:
                try:
                    self.redis.incr(f"metrics:fallback_eta_total:{metric_reason}")
                    print(metric_reason)
                except Exception:
                    pass

            return fallback_res

        # 6. Calculate ETA & Delay
        eta = now + timedelta(seconds=route["duration_in_traffic_seconds"])
        traffic_delay = route["duration_in_traffic_seconds"] - route["duration_seconds"]

        result = {
            "status": "calculated",
            "technician_id": str(technician_id),
            "job_id": str(job_id),
            "eta": eta.isoformat().replace("+00:00", "Z"),
            "duration_minutes": round(route["duration_in_traffic_seconds"] / 60.0, 1),
            "distance_km": round(route["distance_meters"] / 1000.0, 1),
            "current_location": {
                "latitude": latest_gps.latitude,
                "longitude": latest_gps.longitude,
                "last_ping": latest_gps.timestamp.isoformat()
            },
            "job_site": {
                "latitude": job.site_latitude,
                "longitude": job.site_longitude,
                "address": job.site_address
            },
            "route_cached": route.get("cached", False)
        }

        if traffic_delay > 0:
            result["traffic_delay_minutes"] = round(traffic_delay / 60.0, 1)

        if route.get("fallback"):
            result["fallback"] = True

        # Cache results in Redis with 30s TTL
        if self.redis:
            try:
                self.redis.setex(cache_key, 30, json.dumps(result))
            except Exception:
                pass

        return result

    async def calculate_batch_eta(self, technician_ids: List[str], job_id: int) -> List[dict]:
        """
        Calculates real-time ETAs for multiple technicians to a single job site.
        Supports up to 10 technicians.
        """
        if not technician_ids:
            return []

        results = [None] * len(technician_ids)
        cache_miss_indices = []
        gps_pings = {}

        # 1. Fetch Job
        job = self.db.query(models.Job).filter(models.Job.id == job_id).first()
        if not job or job.site_latitude is None or job.site_longitude is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job site coordinates not found"
            )

        # 2. Check Cache & retrieve pings
        for idx, tech_id in enumerate(technician_ids):
            cache_key = f"eta:{tech_id}:{job_id}"
            fallback_key = f"eta:fallback:{tech_id}:{job_id}"
            if self.redis:
                try:
                    cached = self.redis.get(cache_key)
                    if cached:
                        results[idx] = json.loads(cached)
                        continue
                    cached_fallback = self.redis.get(fallback_key)
                    if cached_fallback:
                        results[idx] = json.loads(cached_fallback)
                        continue
                except Exception:
                    pass

            # Fetch Technician
            tech = self.db.query(models.Technician).filter(models.Technician.tech_id == tech_id).first()
            if not tech:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Technician not found: {tech_id}"
                )

            # Tenant isolation check
            if tech.tenant_id != job.tenant_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Tenant mismatch or access denied"
                )

            # Fetch latest GPS
            latest_gps = self.db.query(models.GPSPing).filter(
                models.GPSPing.technician_id == tech_id
            ).order_by(models.GPSPing.timestamp.desc()).first()

            now = datetime.now(timezone.utc)
            is_stale = False
            if latest_gps:
                ping_time = latest_gps.timestamp
                if ping_time.tzinfo is None:
                    ping_time = ping_time.replace(tzinfo=timezone.utc)
                is_stale = (now - ping_time).total_seconds() > 300

            fallback_service = FallbackETAService()

            res = fallback_service.calculate_fallback_eta(
            tech_lat=latest_gps.latitude if latest_gps else job.site_latitude,
            tech_lng=latest_gps.longitude if latest_gps else job.site_longitude,
            site_lat=job.site_latitude,
            site_lng=job.site_longitude,
            reason="gps_unavailable"
            )

            res["fallback_reason"] = "gps_unavailable"
            res["status"] = "estimated"
            res["technician_id"] = str(tech_id)
            res["job_id"] = str(job_id)
            res["calculated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

            if latest_gps is None or is_stale:
                if self.redis:
                    try:
                        self.redis.setex(
                            f"eta:fallback:{tech_id}:{job_id}",
                            60,
                            json.dumps(res)
                        )
                    except Exception:
                        pass

                results[idx] = res
                continue

            gps_pings[idx] = latest_gps
            cache_miss_indices.append(idx)

        # 3. Query Distance Matrix for cache misses
        if cache_miss_indices:
            origins = [(gps_pings[idx].latitude, gps_pings[idx].longitude) for idx in cache_miss_indices]
            destinations = [(job.site_latitude, job.site_longitude)]

            try:
                routes = await self.maps.get_batch_route_durations(origins, destinations)

                # Calculate and populate result for each miss
                now = datetime.now(timezone.utc)
                for i, idx in enumerate(cache_miss_indices):
                    tech_id = technician_ids[idx]
                    latest_gps = gps_pings[idx]
                    route = routes[i]

                    eta = now + timedelta(seconds=route["duration_in_traffic_seconds"])
                    traffic_delay = route["duration_in_traffic_seconds"] - route["duration_seconds"]

                    res = {
                        "status": "calculated",
                        "technician_id": str(tech_id),
                        "job_id": str(job_id),
                        "eta": eta.isoformat().replace("+00:00", "Z"),
                        "duration_minutes": round(route["duration_in_traffic_seconds"] / 60.0, 1),
                        "distance_km": round(route["distance_meters"] / 1000.0, 1),
                        "current_location": {
                            "latitude": latest_gps.latitude,
                            "longitude": latest_gps.longitude,
                            "last_ping": latest_gps.timestamp.isoformat()
                        },
                        "job_site": {
                            "latitude": job.site_latitude,
                            "longitude": job.site_longitude,
                            "address": job.site_address
                        },
                        "route_cached": route.get("cached", False)
                    }

                    if traffic_delay > 0:
                        res["traffic_delay_minutes"] = round(traffic_delay / 60.0, 1)

                    if route.get("fallback"):
                        res["fallback"] = True

                    # Cache
                    pair_cache_key = f"eta:{tech_id}:{job_id}"
                    if self.redis:
                        try:
                            self.redis.setex(pair_cache_key, 30, json.dumps(res))
                        except Exception:
                            pass

                    results[idx] = res

            except Exception as exc:
                reason = "maps_error"
                metric_reason = "error"
                if isinstance(exc, MapsAPIException):
                    status_code = getattr(exc, "status_code", "")
                    if status_code == "maps_timeout":
                        reason = "maps_timeout"
                        metric_reason = "timeout"
                    elif status_code in ("maps_quota", "OVER_QUERY_LIMIT"):
                        reason = "maps_quota"
                        metric_reason = "quota"
                    elif status_code == "maps_unavailable":
                        reason = "maps_unavailable"
                        metric_reason = "error"
                    else:
                        reason = "maps_error"
                        metric_reason = "error"
                elif isinstance(exc, asyncio.TimeoutError):
                    reason = "maps_timeout"
                    metric_reason = "timeout"

                fallback_service = FallbackETAService()
                now_utc = datetime.now(timezone.utc)
                for idx in cache_miss_indices:
                    tech_id = technician_ids[idx]
                    gps = gps_pings[idx]
                    fallback_res = fallback_service.calculate_fallback_eta(
                        tech_lat=gps.latitude,
                        tech_lng=gps.longitude,
                        site_lat=job.site_latitude,
                        site_lng=job.site_longitude,
                        reason=reason
                    )
                    fallback_res["fallback_reason"] = reason
                    fallback_res["technician_id"] = str(tech_id)
                    fallback_res["status"] = "estimated"
                    fallback_res["job_id"] = str(job_id)
                    fallback_res["calculated_at"] = now_utc.isoformat().replace("+00:00", "Z")

                    import logging
                    logger = logging.getLogger("fieldops")
                    logger.warning(
                        "fallback_triggered",
                        extra={
                            "reason": reason,
                            "technician_id": str(tech_id),
                            "job_id": str(job_id),
                            "estimated_duration": fallback_res["duration_minutes"]
                        }
                    )

                    # Cache fallback longer due to lower accuracy
                    fallback_key = f"eta:fallback:{tech_id}:{job_id}"
                    if self.redis:
                        try:
                            self.redis.setex(fallback_key, 60, json.dumps(fallback_res))
                        except Exception:
                            pass

                    # Metrics
                    if self.redis:
                        try:
                            self.redis.incr(f"metrics:fallback_eta_total:{metric_reason}")
                        except Exception:
                            pass

                    results[idx] = fallback_res

        return results
