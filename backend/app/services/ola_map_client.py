import asyncio
import hashlib
import json
import logging
import math
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, List

import aiohttp

from ..context import correlation_id_ctx

logger = logging.getLogger("fieldops")

OLA_BASE_URL = "https://api.olamaps.io"
CB_FAILURE_THRESHOLD = 5
CB_RECOVERY_TIMEOUT = 60


def is_valid_coordinate(latitude: Any, longitude: Any) -> bool:
    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError):
        return False
    return (
        math.isfinite(lat)
        and math.isfinite(lng)
        and -90 <= lat <= 90
        and -180 <= lng <= 180
        and not (lat == 0 and lng == 0)
    )


def is_valid_route_result(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    try:
        distance = float(result["distance_meters"])
        duration = float(result["duration_seconds"])
    except (KeyError, TypeError, ValueError):
        return False
    if not math.isfinite(distance) or distance < 0:
        return False
    if not math.isfinite(duration) or duration < 0:
        return False
    traffic_duration = result.get("duration_in_traffic_seconds")
    if traffic_duration is not None:
        try:
            traffic_duration = float(traffic_duration)
        except (TypeError, ValueError):
            return False
        if not math.isfinite(traffic_duration) or traffic_duration < 0:
            return False
    route_points = result.get("route_points")
    if route_points is not None:
        if not isinstance(route_points, list):
            return False
        for point in route_points:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                return False
            try:
                longitude, latitude = float(point[0]), float(point[1])
            except (TypeError, ValueError):
                return False
            if not (
                math.isfinite(longitude)
                and math.isfinite(latitude)
                and -180 <= longitude <= 180
                and -90 <= latitude <= 90
            ):
                return False
    return True


class MapsAPIException(Exception):
    def __init__(self, status_code: str, message: str | None = None):
        self.status_code = status_code
        self.message = message or f"Ola Maps API error: {status_code}"
        super().__init__(self.message)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0 * (2 * math.asin(math.sqrt(a)))


def get_route_cache_key(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> str:
    origin = f"{origin_lat:.6f},{origin_lng:.6f}"
    dest = f"{dest_lat:.6f},{dest_lng:.6f}"
    return f"maps:ola:route:{hashlib.md5(origin.encode()).hexdigest()}:{hashlib.md5(dest.encode()).hexdigest()}"


def decode_polyline(encoded: str) -> list[list[float]]:
    """Decode Google's/Ola's encoded polyline into [lng, lat] pairs."""
    if not encoded:
        return []
    coords: list[list[float]] = []
    index = lat = lng = 0
    length = len(encoded)
    while index < length:
        shift = result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        lat += ~(result >> 1) if result & 1 else result >> 1

        shift = result = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        lng += ~(result >> 1) if result & 1 else result >> 1
        coords.append([lng / 1e5, lat / 1e5])
    return coords


class CircuitBreaker:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.key_failures = "cb:failures:ola_maps"
        self.key_state = "cb:state:ola_maps"

    def is_open(self) -> bool:
        try:
            return self.redis.get(self.key_state) == "OPEN"
        except Exception:
            return False

    def record_failure(self) -> None:
        try:
            failures = self.redis.incr(self.key_failures)
            if failures == 1:
                self.redis.expire(self.key_failures, CB_RECOVERY_TIMEOUT)
            if failures >= CB_FAILURE_THRESHOLD:
                self.redis.setex(self.key_state, CB_RECOVERY_TIMEOUT, "OPEN")
                self.redis.delete(self.key_failures)
                logger.warning("Ola Maps circuit breaker opened")
        except Exception:
            pass

    def record_success(self) -> None:
        try:
            if not self.is_open():
                self.redis.delete(self.key_failures)
        except Exception:
            pass


class RateLimiter:
    def __init__(self, redis_client, rate_limit: int = 100, window: int = 60):
        self.redis = redis_client
        self.rate_limit = rate_limit
        self.window = window

    def allow_request(self) -> bool:
        try:
            key = f"rate_limit:ola_maps:{int(time.time() // self.window)}"
            count = self.redis.incr(key)
            if count == 1:
                self.redis.expire(key, self.window + 10)
            return count <= self.rate_limit
        except Exception:
            return True


class OlaMapsClient:
    """Server-side Ola Maps adapter for routing, distance and road matching."""

    def __init__(self, redis_client):
        self.api_key = os.getenv("OLA_MAPS_API_KEY", "").strip()
        self.redis = redis_client
        self.cb = CircuitBreaker(redis_client)
        self.rate_limiter = RateLimiter(redis_client)

    def _metric_call(self) -> None:
        try:
            self.redis.incr("metrics:ola_maps_api_calls_total")
        except Exception:
            pass

    def _metric_cache_hit(self) -> None:
        try:
            self.redis.incr("metrics:ola_maps_cache_hits")
        except Exception:
            pass

    def _metric_latency(self, seconds: float) -> None:
        try:
            self.redis.incrbyfloat("metrics:ola_maps_latency_seconds", seconds)
        except Exception:
            pass

    async def search_places(self, query: str) -> list[dict[str, Any]]:
        """Search addresses using Ola's existing server-side geocoding API."""
        payload, _ = await self._request(
            "/places/v1/geocode", {"address": query.strip()}
        )
        raw_results = payload.get("geocodingResults", [])
        results: list[dict[str, Any]] = []
        for result in raw_results:
            geometry = result.get("geometry", {})
            point = geometry.get("location", {})
            try:
                latitude = float(point["lat"])
                longitude = float(point["lng"])
            except (KeyError, TypeError, ValueError):
                continue
            address = result.get("formatted_address") or result.get("name")
            if not address:
                continue
            components = result.get("address_components") or []
            place_name = result.get("name") or next(
                (
                    component.get("long_name")
                    for component in components
                    if any(
                        kind in {"premise", "establishment", "point_of_interest"}
                        for kind in component.get("types", [])
                    )
                ),
                "",
            )
            result_types = result.get("types") or []
            results.append({
                "name": place_name or address,
                "formatted_address": address,
                "latitude": latitude,
                "longitude": longitude,
                "place_id": result.get("place_id"),
                "type": result_types[0] if result_types else None,
            })
        return results

    async def reverse_geocode(self, latitude: float, longitude: float) -> dict[str, Any] | None:
        payload, _ = await self._request(
            "/places/v1/reverse-geocode",
            {"latlng": f"{latitude},{longitude}"},
        )
        results = payload.get("results", [])
        if not results:
            return None
        result = results[0]
        address = result.get("formatted_address")
        if not address:
            return None
        return {
            "name": result.get("name") or result.get("premise") or "",
            "formatted_address": address,
            "latitude": latitude,
            "longitude": longitude,
        }

    def _fallback_route(self, origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> dict:
        distance_meters = int(haversine_distance(origin_lat, origin_lng, dest_lat, dest_lng) * 1000)
        duration_seconds = int(distance_meters / 13.889)
        return {
            "distance_meters": distance_meters,
            "duration_seconds": duration_seconds,
            "duration_in_traffic_seconds": int(duration_seconds * 1.2),
            "route_points": [[origin_lng, origin_lat], [dest_lng, dest_lat]],
            "provider": "haversine_fallback",
            "cached": False,
            "fallback": True,
            "route_calculated_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _request(self, path: str, params: dict[str, Any], method: str = "GET") -> tuple[dict, int]:
        if self.cb.is_open() or not self.api_key:
            raise MapsAPIException("maps_unavailable", "Ola Maps API key is missing or circuit breaker is open")
        if not self.rate_limiter.allow_request():
            raise MapsAPIException("maps_quota", "Ola Maps rate limit exceeded")

        params = {**params, "api_key": self.api_key}
        correlation_id = correlation_id_ctx.get() or str(uuid.uuid4())
        start = time.perf_counter()
        last_error: Exception | None = None

        for attempt in range(3):
            try:
                self._metric_call()
                timeout = aiohttp.ClientTimeout(total=6.0)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.request(
                        method,
                        f"{OLA_BASE_URL}{path}",
                        params=params,
                        headers={"X-Request-Id": correlation_id, "X-Correlation-ID": correlation_id},
                    ) as response:
                        payload = await response.json(content_type=None)
                        latency = time.perf_counter() - start
                        self._metric_latency(latency)
                        if response.status == 200:
                            self.cb.record_success()
                            logger.info("ola_maps_call", extra={"path": path, "status": response.status, "latency_ms": round(latency * 1000), "correlation_id": correlation_id})
                            return payload, response.status
                        if response.status == 429:
                            last_error = MapsAPIException("maps_quota", "Ola Maps returned HTTP 429")
                        else:
                            last_error = MapsAPIException("maps_error", f"Ola Maps HTTP {response.status}: {payload}")
            except asyncio.TimeoutError as exc:
                last_error = MapsAPIException("maps_timeout", "Ola Maps request timed out")
            except Exception as exc:
                last_error = exc
            if attempt < 2:
                await asyncio.sleep(0.5 * (2 ** attempt))

        self.cb.record_failure()
        if isinstance(last_error, MapsAPIException):
            raise last_error
        raise MapsAPIException("maps_unavailable", str(last_error))
    async def get_route_duration(
    self,
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,) -> dict:

        if not is_valid_coordinate(origin_lat, origin_lng) or not is_valid_coordinate(dest_lat, dest_lng):
            raise MapsAPIException(
                "INVALID_REQUEST",
                "Invalid latitude/longitude coordinates",
            )
    
        cache_key = get_route_cache_key(
            origin_lat,
            origin_lng,
            dest_lat,
            dest_lng,
        )
    
        try:
            cached = self.redis.get(cache_key)
    
            if cached:
                self._metric_cache_hit()
    
                result = json.loads(cached)
                if not is_valid_route_result(result):
                    raise ValueError("Cached Ola route response is invalid")
                result["cached"] = True
    
                logger.info(
                    "[OLA ROUTE] cache hit: %s -> %s",
                    (origin_lat, origin_lng),
                    (dest_lat, dest_lng),
                )
    
                return result
    
        except Exception as exc:
            logger.warning("[OLA ROUTE] cache read failed: %s", exc)
    
        params = {
            "origin": f"{origin_lat},{origin_lng}",
            "destination": f"{dest_lat},{dest_lng}",
            "mode": "driving",
            "overview": "full",
            "steps": "false",
            "traffic_metadata": "true",
            "route_preference": "fastest",
        }
    
        logger.info("[OLA ROUTE] requesting route")
        logger.info("[OLA ROUTE] params=%s", params)
    
        data, _ = await self._request(
            "/routing/v1/directions",
            params,
            method="POST",
        )
    
        # IMPORTANT DEBUG
        logger.info(
            "[OLA ROUTE] response status=%s routes=%s",
            data.get("status"),
            len(data.get("routes") or []),
        )
    
        logger.info(
            "[OLA ROUTE] response keys=%s",
            list(data.keys()),
        )
    
        if data.get("status") not in ("OK", "SUCCESS"):
            logger.error("[OLA ROUTE] unexpected response: %s", data)
            raise MapsAPIException(
                str(data.get("status", "UNKNOWN")),
                f"Ola Maps routing failed: {data.get('error_message', 'unknown error')}",
            )
    
        routes = data.get("routes") or []
    
        if not routes:
            logger.error("[OLA ROUTE] SUCCESS but routes array is empty: %s", data)
    
            raise MapsAPIException(
                "NO_ROUTE",
                "Ola Maps returned SUCCESS but no routes",
            )
    
        route = routes[0]
    
        legs = route.get("legs") or []
    
        if not legs:
            logger.error("[OLA ROUTE] route exists but legs are empty: %s", route)
    
            raise MapsAPIException(
                "NO_ROUTE",
                "Ola Maps returned a route without legs",
            )
    
        distance_meters = sum(
            float(leg.get("distance") or 0)
            for leg in legs
        )
    
        duration_seconds = sum(
            float(leg.get("duration") or 0)
            for leg in legs
        )

        if (
            not math.isfinite(distance_meters)
            or distance_meters < 0
            or not math.isfinite(duration_seconds)
            or duration_seconds < 0
        ):
            raise MapsAPIException(
                "INVALID_ROUTE",
                "Ola Maps returned invalid distance or duration values",
            )
    
        overview_polyline = route.get("overview_polyline") or ""
    
        route_points = []
    
        if overview_polyline:
            try:
                route_points = decode_polyline(overview_polyline)
            except Exception as exc:
                logger.exception(
                    "[OLA ROUTE] polyline decode failed: %s",
                    exc,
                )

        if route_points and not is_valid_route_result({
            "distance_meters": distance_meters,
            "duration_seconds": duration_seconds,
            "duration_in_traffic_seconds": duration_seconds,
            "route_points": route_points,
        }):
            raise MapsAPIException(
                "INVALID_ROUTE",
                "Ola Maps returned invalid route coordinates",
            )
    
        result = {
            "distance_meters": int(distance_meters),
            "duration_seconds": int(duration_seconds),
            "duration_in_traffic_seconds": int(duration_seconds),
            "route_points": route_points,
            "overview_polyline": overview_polyline,
            "travel_advisory": route.get("travel_advisory"),
            "provider": "ola_maps",
            "cached": False,
            "fallback": False,
            "route_calculated_at": datetime.now(timezone.utc).isoformat(),
        }

        if not is_valid_route_result(result):
            raise MapsAPIException(
                "INVALID_ROUTE",
                "Ola Maps returned an invalid route response",
            )
    
        logger.info(
            "[OLA ROUTE] SUCCESS distance=%sm duration=%ss points=%s",
            result["distance_meters"],
            result["duration_seconds"],
            len(route_points),
        )
    
        try:
            self.redis.setex(
                cache_key,
                30,
                json.dumps(result),
            )
        except Exception as exc:
            logger.warning(
                "[OLA ROUTE] cache write failed: %s",
                exc,
            )
    
        return result
    
    async def get_distance(self, origin: dict, dest: dict) -> float:
        origin_lat, origin_lng = origin["lat"], origin["lng"]
        dest_lat, dest_lng = dest["lat"], dest["lng"]
        result = await self.get_route_duration(origin_lat, origin_lng, dest_lat, dest_lng)
        return float(result["distance_meters"]) / 1000.0

    async def get_batch_route_durations(self, origins: List[tuple[float, float]], destinations: List[tuple[float, float]]) -> List[dict]:
        if not origins or not destinations:
            return []
        if len(origins) * len(destinations) > 50:
            raise MapsAPIException("INVALID_REQUEST", "Maximum 50 origin-destination pairs supported")

        origins_str = "|".join(f"{lat},{lng}" for lat, lng in origins)
        destinations_str = "|".join(f"{lat},{lng}" for lat, lng in destinations)
        data, _ = await self._request(
            "/routing/v1/distanceMatrix",
            {
                "origins": origins_str,
                "destinations": destinations_str,
                "mode": "driving",
                "route_preference": "fastest",
            },
        )
        if data.get("status") not in ("SUCCESS", "OK"):
            raise MapsAPIException(str(data.get("status", "UNKNOWN")), "Ola Maps distance matrix failed")

        results: list[dict] = []
        for row in data.get("rows", []):
            for element in row.get("elements", []):
                if element.get("status") != "OK":
                    results.append(self._fallback_route(*origins[len(results)], *destinations[0]))
                else:
                    results.append({
                        "distance_meters": int(element.get("distance", 0)),
                        "duration_seconds": int(element.get("duration", 0)),
                        "duration_in_traffic_seconds": int(element.get("duration", 0)),
                        "provider": "ola_maps",
                        "cached": False,
                        "fallback": False,
                        "route_calculated_at": datetime.now(timezone.utc).isoformat(),
                    })
        return results

    async def snap_to_road(self, latitude: float, longitude: float) -> dict | None:
        data, _ = await self._request(
            "/routing/v1/snapToRoad",
            {"points": f"{latitude},{longitude}", "interpolate": "true"},
        )
        points = data.get("snappedPoints") or data.get("points") or []
        if not points:
            return None
        point = points[0]
        location = point.get("location") or point.get("snapped_location") or {}
        if "lat" in location and "lng" in location:
            return {"latitude": float(location["lat"]), "longitude": float(location["lng"])}
        return None
