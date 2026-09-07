import aiohttp
import asyncio
import math
import os
import time
import json
import logging
import hashlib
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any

from ..context import correlation_id_ctx

logger = logging.getLogger("fieldops")

# Circuit breaker config
CB_FAILURE_THRESHOLD = 5  # Failures
CB_RECOVERY_TIMEOUT = 60  # Seconds

class MapsAPIException(Exception):
    def __init__(self, status_code: str, message: str = None):
        self.status_code = status_code
        self.message = message or f"Google Maps API error: {status_code}"
        super().__init__(self.message)

class CircuitBreaker:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.key_failures = "cb:failures:gmaps"
        self.key_state = "cb:state:gmaps"

    def is_open(self):
        try:
            state = self.redis.get(self.key_state)
            return state == "OPEN"
        except Exception:
            return False

    def record_failure(self):
        try:
            failures = self.redis.incr(self.key_failures)
            if failures is None:
                return
                
            if failures == 1:
                self.redis.expire(self.key_failures, CB_RECOVERY_TIMEOUT)
            
            if failures >= CB_FAILURE_THRESHOLD:
                # Open the circuit for the recovery timeout
                self.redis.setex(self.key_state, CB_RECOVERY_TIMEOUT, "OPEN")
                self.redis.delete(self.key_failures)
                logger.warning("Google Maps Circuit Breaker OPENED")
        except Exception:
            pass

    def record_success(self):
        try:
            if not self.is_open():
                self.redis.delete(self.key_failures)
        except Exception:
            pass

class RateLimiter:
    def __init__(self, redis_client, rate_limit=100, window=60):
        self.redis = redis_client
        self.rate_limit = rate_limit
        self.window = window

    def allow_request(self) -> bool:
        """Token bucket inspired rate limiter using redis INCR and EXPIRE."""
        try:
            current_minute = int(time.time() // self.window)
            key = f"rate_limit:gmaps:{current_minute}"
            
            count = self.redis.incr(key)
            if count is None:
                return True
                
            if count == 1:
                self.redis.expire(key, self.window + 10)
                
            if count > self.rate_limit:
                logger.warning(f"Google Maps Rate limit exceeded: {count}/{self.rate_limit}")
                return False
            return True
        except Exception:
            return True


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance in kilometers between two points 
    on the earth (specified in decimal degrees)
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    r = 6371 # Radius of earth in kilometers
    return c * r


def get_route_cache_key(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> str:
    origin_str = f"{origin_lat:.6f},{origin_lng:.6f}"
    dest_str = f"{dest_lat:.6f},{dest_lng:.6f}"
    origin_hash = hashlib.md5(origin_str.encode('utf-8')).hexdigest()
    dest_hash = hashlib.md5(dest_str.encode('utf-8')).hexdigest()
    return f"maps:route:{origin_hash}:{dest_hash}"


class GoogleMapsClient:
    def __init__(self, redis_client):
        self.api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
        self.base_url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        self.redis = redis_client
        self.cb = CircuitBreaker(redis_client)
        self.rate_limiter = RateLimiter(redis_client)

    def _record_metric_call(self):
        try:
            self.redis.incr("metrics:maps_api_calls_total")
        except Exception:
            pass

    def _record_metric_hit(self):
        try:
            self.redis.incr("metrics:maps_api_cache_hits")
        except Exception:
            pass

    def _record_metric_latency(self, latency: float):
        try:
            self.redis.incrbyfloat("metrics:maps_api_latency_seconds", latency)
        except Exception:
            pass

    def _log_api_call(self, origin: str, destination: str, api_status: str, latency_ms: int, correlation_id: str):
        logger.info(
            "Google Maps Distance Matrix API call complete",
            extra={
                "origin": origin,
                "destination": destination,
                "api_status": api_status,
                "latency_ms": latency_ms,
                "correlation_id": correlation_id
            }
        )

    def _fallback_route(self, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> dict:
        distance_km = haversine_distance(origin_lat, origin_lng, dest_lat, dest_lng)
        distance_meters = int(distance_km * 1000)
        # Average speed 50 km/h = 13.889 meters per second
        duration_seconds = int(distance_meters / 13.889)
        # Traffic duration = 1.2 * duration_seconds
        duration_in_traffic_seconds = int(duration_seconds * 1.2)
        return {
            "distance_meters": distance_meters,
            "duration_seconds": duration_seconds,
            "duration_in_traffic_seconds": duration_in_traffic_seconds,
            "cached": False,
            "fallback": True,
            "route_calculated_at": datetime.now(timezone.utc).isoformat()
        }

    async def get_distance(self, origin: dict, dest: dict) -> float:
        """
        Returns distance in km between origin and dest.
        Uses Redis cache, Rate Limiting, Circuit Breaker, and Haversine fallback.
        """
        origin_lat, origin_lng = origin.get("lat"), origin.get("lng")
        dest_lat, dest_lng = dest.get("lat"), dest.get("lng")

        # Basic coordinate validation
        if not (-90 <= origin_lat <= 90 and -180 <= origin_lng <= 180):
            return haversine_distance(origin_lat, origin_lng, dest_lat, dest_lng)
        if not (-90 <= dest_lat <= 90 and -180 <= dest_lng <= 180):
            return haversine_distance(origin_lat, origin_lng, dest_lat, dest_lng)

        cache_key = f"proximity:{origin_lat},{origin_lng}:{dest_lat},{dest_lng}"
        
        # 1. Check Cache
        try:
            cached_result = self.redis.get(cache_key)
            if cached_result:
                return float(cached_result)
        except Exception:
            pass

        # 2. Check Circuit Breaker
        if self.cb.is_open() or not self.api_key:
            return haversine_distance(origin_lat, origin_lng, dest_lat, dest_lng)

        # 3. Check Rate Limit
        if not self.rate_limiter.allow_request():
            return haversine_distance(origin_lat, origin_lng, dest_lat, dest_lng)

        # 4. API Call
        try:
            params = {
                "origins": f"{origin_lat},{origin_lng}",
                "destinations": f"{dest_lat},{dest_lng}",
                "mode": "driving",
                "key": self.api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.base_url, params=params, timeout=2.0) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        
                        # Parse Google Maps response
                        if data.get("status") == "OK" and data["rows"][0]["elements"][0]["status"] == "OK":
                            # distance in meters -> km
                            distance_meters = data["rows"][0]["elements"][0]["distance"]["value"]
                            distance_km = distance_meters / 1000.0
                            
                            # Cache the successful result (300 seconds TTL)
                            try:
                                self.redis.setex(cache_key, 300, str(distance_km))
                            except Exception:
                                pass
                            self.cb.record_success()
                            return distance_km
                        else:
                            # API returned an error payload
                            self.cb.record_failure()
                            logger.error(f"Google Maps API error response: {data.get('status')}")
                            return haversine_distance(origin_lat, origin_lng, dest_lat, dest_lng)
                    else:
                        # HTTP error
                        self.cb.record_failure()
                        logger.error(f"Google Maps API HTTP Error: {resp.status}")
                        return haversine_distance(origin_lat, origin_lng, dest_lat, dest_lng)

        except Exception as e:
            # Network error or timeout
            self.cb.record_failure()
            logger.error(f"Google Maps API request failed: {str(e)}")
            return haversine_distance(origin_lat, origin_lng, dest_lat, dest_lng)

    async def get_route_duration(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float
    ) -> dict:
        """
        Returns routing details (distance, duration, traffic duration) between origin and destination.
        """
        # Coordinate validation
        if not (-90 <= origin_lat <= 90 and -180 <= origin_lng <= 180) or not (-90 <= dest_lat <= 90 and -180 <= dest_lng <= 180):
            raise MapsAPIException("INVALID_REQUEST", "Invalid latitude/longitude coordinates")

        cache_key = get_route_cache_key(origin_lat, origin_lng, dest_lat, dest_lng)
        
        # Check Cache
        try:
            cached = self.redis.get(cache_key)
            if cached:
                self._record_metric_hit()
                res = json.loads(cached)
                res["cached"] = True
                return res
        except Exception as e:
            logger.warning(f"Failed to read from Redis cache: {e}")

        # Check Circuit Breaker
        if self.cb.is_open() or not self.api_key:
            raise MapsAPIException("maps_unavailable", "Circuit breaker is open or API key is missing")

        # Check Rate Limit
        if not self.rate_limiter.allow_request():
            raise MapsAPIException("maps_quota", "Rate limit exceeded (rate limiter)")

        # Call Distance Matrix API with 3 retries and exponential backoff
        url = self.base_url
        params = {
            "origins": f"{origin_lat},{origin_lng}",
            "destinations": f"{dest_lat},{dest_lng}",
            "mode": "driving",
            "traffic_model": "best_guess",
            "departure_time": "now",
            "key": self.api_key
        }

        correlation_id = correlation_id_ctx.get() or str(uuid.uuid4())
        start_time = time.time()

        delay = 1.0
        response_data = None
        api_status = "UNKNOWN"

        for attempt in range(3):
            try:
                self._record_metric_call()
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5.0)) as session:
                    async with session.get(url, params=params) as resp:
                        if resp.status == 200:
                            response_data = await resp.json()
                            break
                        elif resp.status == 429:
                            if attempt == 2:
                                raise MapsAPIException("maps_quota", "Rate limit exceeded (429)")
                            await asyncio.sleep(delay)
                            delay *= 2.0
                        else:
                            if attempt == 2:
                                raise MapsAPIException("maps_error", f"HTTP error status: {resp.status}")
                            break
            except Exception as e:
                if attempt == 2:
                    logger.error(f"Google Maps API request failed after 3 attempts: {e}")
                    if isinstance(e, asyncio.TimeoutError):
                        raise MapsAPIException("maps_timeout", f"Request timed out: {e}")
                    raise MapsAPIException("maps_unavailable", f"Request failed: {e}")
                await asyncio.sleep(delay)
                delay *= 2.0

        if not response_data:
            self.cb.record_failure()
            raise MapsAPIException("maps_unavailable", "No response data received from Google Maps API")

        api_status = response_data.get("status", "UNKNOWN")
        if api_status != "OK":
            self.cb.record_failure()
            latency_ms = int((time.time() - start_time) * 1000)
            self._log_api_call(f"{origin_lat},{origin_lng}", f"{dest_lat},{dest_lng}", api_status, latency_ms, correlation_id)
            raise MapsAPIException(api_status, response_data.get("error_message"))

        rows = response_data.get("rows", [])
        if not rows or not rows[0].get("elements"):
            self.cb.record_failure()
            raise MapsAPIException("UNKNOWN", "Empty response elements")

        element = rows[0]["elements"][0]
        element_status = element.get("status", "UNKNOWN")
        if element_status != "OK":
            self.cb.record_failure()
            latency_ms = int((time.time() - start_time) * 1000)
            self._log_api_call(f"{origin_lat},{origin_lng}", f"{dest_lat},{dest_lng}", element_status, latency_ms, correlation_id)
            raise MapsAPIException(element_status)

        distance_meters = element["distance"]["value"]
        duration_seconds = element["duration"]["value"]
        duration_in_traffic_seconds = element.get("duration_in_traffic", {}).get("value", duration_seconds)

        result = {
            "distance_meters": distance_meters,
            "duration_seconds": duration_seconds,
            "duration_in_traffic_seconds": duration_in_traffic_seconds,
            "cached": False,
            "route_calculated_at": datetime.now(timezone.utc).isoformat()
        }

        # Cache the result for 5 minutes
        try:
            self.redis.setex(cache_key, 300, json.dumps(result))
        except Exception as e:
            logger.warning(f"Failed to write to Redis cache: {e}")

        self.cb.record_success()
        latency_ms = int((time.time() - start_time) * 1000)
        self._record_metric_latency(latency_ms / 1000.0)
        self._log_api_call(f"{origin_lat},{origin_lng}", f"{dest_lat},{dest_lng}", "OK", latency_ms, correlation_id)

        return result

    async def get_batch_route_durations(
        self,
        origins: List[tuple[float, float]],
        destinations: List[tuple[float, float]]
    ) -> List[dict]:
        """
        Returns routing details for a batch of origins to a single destination.
        Up to 10 origin-destination pairs.
        """
        if not origins or not destinations:
            return []

        results = [None] * len(origins)
        cache_miss_indices = []

        # Validate destination
        dest_lat, dest_lng = destinations[0]
        if not (-90 <= dest_lat <= 90 and -180 <= dest_lng <= 180):
            raise MapsAPIException("INVALID_REQUEST", "Invalid destination coordinates")

        # 1. Check cache for each origin
        for idx, origin in enumerate(origins):
            origin_lat, origin_lng = origin
            if not (-90 <= origin_lat <= 90 and -180 <= origin_lng <= 180):
                raise MapsAPIException("INVALID_REQUEST", "Invalid origin coordinates")

            cache_key = get_route_cache_key(origin_lat, origin_lng, dest_lat, dest_lng)
            try:
                cached = self.redis.get(cache_key)
                if cached:
                    self._record_metric_hit()
                    res = json.loads(cached)
                    res["cached"] = True
                    results[idx] = res
                    continue
            except Exception:
                pass
            
            cache_miss_indices.append(idx)

        # 2. Query Distance Matrix for cache misses
        if cache_miss_indices:
            # Check Circuit Breaker / Rate Limit or lack of key
            if self.cb.is_open() or not self.api_key:
                raise MapsAPIException("maps_unavailable", "Circuit breaker is open or API key is missing")
            if not self.rate_limiter.allow_request():
                raise MapsAPIException("maps_quota", "Rate limit exceeded (rate limiter)")

            # Google maps allows batching up to 10 pairs in this application context
            miss_origins = [origins[idx] for idx in cache_miss_indices]
            origins_str = "|".join(f"{lat},{lng}" for lat, lng in miss_origins)
            dest_str = f"{dest_lat},{dest_lng}"

            url = self.base_url
            params = {
                "origins": origins_str,
                "destinations": dest_str,
                "mode": "driving",
                "traffic_model": "best_guess",
                "departure_time": "now",
                "key": self.api_key
            }

            correlation_id = correlation_id_ctx.get() or str(uuid.uuid4())
            start_time = time.time()

            delay = 1.0
            response_data = None
            for attempt in range(3):
                try:
                    self._record_metric_call()
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5.0)) as session:
                        async with session.get(url, params=params) as resp:
                            if resp.status == 200:
                                response_data = await resp.json()
                                break
                            elif resp.status == 429:
                                if attempt == 2:
                                    raise MapsAPIException("maps_quota", "Rate limit exceeded (429)")
                                await asyncio.sleep(delay)
                                delay *= 2.0
                            else:
                                if attempt == 2:
                                    raise MapsAPIException("maps_error", f"HTTP error status: {resp.status}")
                                break
                except Exception as e:
                    if attempt == 2:
                        if isinstance(e, asyncio.TimeoutError):
                            raise MapsAPIException("maps_timeout", f"Request timed out: {e}")
                        raise MapsAPIException("maps_unavailable", f"Request failed: {e}")
                    await asyncio.sleep(delay)
                    delay *= 2.0

            if not response_data:
                self.cb.record_failure()
                raise MapsAPIException("maps_unavailable", "No response data received from Google Maps API")

            api_status = response_data.get("status", "UNKNOWN")
            if api_status != "OK":
                self.cb.record_failure()
                latency_ms = int((time.time() - start_time) * 1000)
                self._log_api_call(origins_str, dest_str, api_status, latency_ms, correlation_id)
                raise MapsAPIException(api_status, response_data.get("error_message"))

            rows = response_data.get("rows", [])
            for row_idx, row in enumerate(rows):
                orig_idx = cache_miss_indices[row_idx]
                origin_lat, origin_lng = origins[orig_idx]

                elements = row.get("elements", [])
                if not elements:
                    results[orig_idx] = self._fallback_route(origin_lat, origin_lng, dest_lat, dest_lng)
                    continue

                element = elements[0]
                element_status = element.get("status", "UNKNOWN")
                if element_status != "OK":
                    self.cb.record_failure()
                    latency_ms = int((time.time() - start_time) * 1000)
                    self._log_api_call(origins_str, dest_str, element_status, latency_ms, correlation_id)
                    raise MapsAPIException(element_status)

                distance_meters = element["distance"]["value"]
                duration_seconds = element["duration"]["value"]
                duration_in_traffic_seconds = element.get("duration_in_traffic", {}).get("value", duration_seconds)

                result = {
                    "distance_meters": distance_meters,
                    "duration_seconds": duration_seconds,
                    "duration_in_traffic_seconds": duration_in_traffic_seconds,
                    "cached": False,
                    "route_calculated_at": datetime.now(timezone.utc).isoformat()
                }

                # Cache individual pair
                pair_cache_key = get_route_cache_key(origin_lat, origin_lng, dest_lat, dest_lng)
                try:
                    self.redis.setex(pair_cache_key, 300, json.dumps(result))
                except Exception:
                    pass

                results[orig_idx] = result

            self.cb.record_success()
            latency_ms = int((time.time() - start_time) * 1000)
            self._record_metric_latency(latency_ms / 1000.0)
            self._log_api_call(origins_str, dest_str, "OK", latency_ms, correlation_id)

        return results
