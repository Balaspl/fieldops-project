import pytest
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.redis_client import get_redis_client
from app.services.google_maps_client import (
    GoogleMapsClient,
    MapsAPIException,
    get_route_cache_key,
)
from app.routes.eta import GPSBatchRouteRequest


client = TestClient(app)


# Helper to run async test functions synchronously
def run_async(func):
    import asyncio
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        return asyncio.run(func(*args, **kwargs))

    return wrapper


# Mock Redis class for Maps testing
class MockRedis:
    def __init__(self):
        self.data = {}
        self.ttls = {}

    def get(self, key):
        return self.data.get(key)

    def setex(self, key, seconds, value):
        self.data[key] = str(value)
        self.ttls[key] = seconds

    def ttl(self, key):
        return self.ttls.get(key, -2)

    def incr(self, key):
        val = int(self.data.get(key, 0)) + 1
        self.data[key] = str(val)
        return val

    def incrbyfloat(self, key, amount):
        val = float(self.data.get(key, 0.0)) + amount
        self.data[key] = str(val)
        return val

    def delete(self, key):
        if key in self.data:
            del self.data[key]

        if key in self.ttls:
            del self.ttls[key]

    def flushall(self):
        self.data.clear()
        self.ttls.clear()


mock_redis = MockRedis()


@pytest.fixture(autouse=True)
def setup_redis_override(monkeypatch):
    mock_redis.flushall()

    monkeypatch.setenv(
        "GOOGLE_MAPS_API_KEY",
        "test-api-key",
    )

    monkeypatch.setattr(
        "app.redis_client.redis_manager",
        mock_redis,
    )

    monkeypatch.setattr(
        "app.redis_client.get_redis_client",
        lambda: mock_redis,
    )

    yield


@pytest.fixture(autouse=True)
def apply_overrides():
    app.dependency_overrides[get_redis_client] = (
        lambda: mock_redis
    )

    yield

    app.dependency_overrides.clear()


# Helper to mock aiohttp responses
class MockResponse:
    def __init__(self, json_data, status=200):
        self._json_data = json_data
        self.status = status

    async def json(self, **kwargs):
        return self._json_data

    async def __aenter__(self):
        return self

    async def __aexit__(
        self,
        exc_type,
        exc_val,
        exc_tb,
    ):
        pass


# ---------------------------------------------------------------------------
# Google Maps client tests
# ---------------------------------------------------------------------------

@run_async
async def test_successful_api_call_returns_distance_and_duration():
    gmaps = GoogleMapsClient(mock_redis)
    gmaps.api_key = "test-api-key"

    mock_api_response = {
        "status": "OK",
        "rows": [
            {
                "elements": [
                    {
                        "distance": {
                            "value": 12500
                        },
                        "duration": {
                            "value": 1680
                        },
                        "duration_in_traffic": {
                            "value": 2100
                        },
                        "status": "OK",
                    }
                ]
            }
        ],
    }

    with patch(
        "aiohttp.ClientSession.get",
        return_value=MockResponse(
            mock_api_response,
            200,
        ),
    ):
        result = await gmaps.get_route_duration(
            12.90,
            80.12,
            13.00,
            80.25,
        )

        assert result["distance_meters"] == 12500
        assert result["duration_seconds"] == 1680
        assert result["duration_in_traffic_seconds"] == 2100
        assert (
            result["duration_in_traffic_seconds"]
            > result["duration_seconds"]
        )
        assert result["cached"] is False


@run_async
async def test_redis_cache_hit_returns_cached_data_without_api_call():
    gmaps = GoogleMapsClient(mock_redis)
    gmaps.api_key = "test-api-key"

    cache_key = get_route_cache_key(
        12.90,
        80.12,
        13.00,
        80.25,
    )

    cached_data = {
        "distance_meters": 5000,
        "duration_seconds": 600,
        "duration_in_traffic_seconds": 800,
        "cached": False,
        "route_calculated_at": "2026-06-25T12:00:00Z",
    }

    mock_redis.setex(
        cache_key,
        300,
        json.dumps(cached_data),
    )

    with patch(
        "aiohttp.ClientSession.get",
        side_effect=Exception(
            "API should not be called"
        ),
    ):
        result = await gmaps.get_route_duration(
            12.90,
            80.12,
            13.00,
            80.25,
        )

        assert result["distance_meters"] == 5000
        assert result["duration_seconds"] == 600
        assert (
            result["duration_in_traffic_seconds"]
            == 800
        )
        assert result["cached"] is True


@run_async
async def test_redis_cache_miss_triggers_api_call_and_caches():
    gmaps = GoogleMapsClient(mock_redis)
    gmaps.api_key = "test-api-key"

    mock_api_response = {
        "status": "OK",
        "rows": [
            {
                "elements": [
                    {
                        "distance": {
                            "value": 8500
                        },
                        "duration": {
                            "value": 900
                        },
                        "duration_in_traffic": {
                            "value": 1100
                        },
                        "status": "OK",
                    }
                ]
            }
        ],
    }

    cache_key = get_route_cache_key(
        12.90,
        80.12,
        13.00,
        80.25,
    )

    assert mock_redis.get(cache_key) is None

    with patch(
        "aiohttp.ClientSession.get",
        return_value=MockResponse(
            mock_api_response,
            200,
        ),
    ):
        result = await gmaps.get_route_duration(
            12.90,
            80.12,
            13.00,
            80.25,
        )

        assert result["distance_meters"] == 8500
        assert result["cached"] is False

        cached_str = mock_redis.get(cache_key)

        assert cached_str is not None

        cached_json = json.loads(cached_str)

        assert cached_json["distance_meters"] == 8500


def test_cache_ttl_expires_after_300_seconds():
    gmaps = GoogleMapsClient(mock_redis)
    gmaps.api_key = "test-api-key"

    cache_key = get_route_cache_key(
        12.90,
        80.12,
        13.00,
        80.25,
    )

    mock_redis.setex(
        cache_key,
        300,
        "{}",
    )

    assert mock_redis.ttl(cache_key) == 300


@run_async
async def test_api_quota_exceeded_raises_maps_api_exception():
    gmaps = GoogleMapsClient(mock_redis)
    gmaps.api_key = "test-api-key"

    mock_api_response = {
        "status": "OVER_QUERY_LIMIT",
        "error_message": (
            "You have exceeded your daily "
            "request quota for this API."
        ),
    }

    with patch(
        "aiohttp.ClientSession.get",
        return_value=MockResponse(
            mock_api_response,
            200,
        ),
    ):
        with pytest.raises(MapsAPIException) as excinfo:
            await gmaps.get_route_duration(
                12.90,
                80.12,
                13.00,
                80.25,
            )

        assert (
            excinfo.value.status_code
            == "OVER_QUERY_LIMIT"
        )

        assert "quota" in excinfo.value.message


@run_async
async def test_api_timeout_triggers_retry():
    gmaps = GoogleMapsClient(mock_redis)
    gmaps.api_key = "test-api-key"

    mock_api_response = {
        "status": "OK",
        "rows": [
            {
                "elements": [
                    {
                        "distance": {
                            "value": 1000
                        },
                        "duration": {
                            "value": 120
                        },
                        "duration_in_traffic": {
                            "value": 150
                        },
                        "status": "OK",
                    }
                ]
            }
        ],
    }

    call_count = 0

    def mock_get(
        url,
        params=None,
        timeout=None,
    ):
        nonlocal call_count

        call_count += 1

        if call_count < 3:
            raise asyncio.TimeoutError(
                "Timeout"
            )

        return MockResponse(
            mock_api_response,
            200,
        )

    with patch(
        "aiohttp.ClientSession.get",
        side_effect=mock_get,
    ):
        with patch(
            "asyncio.sleep",
            return_value=None,
        ):
            result = await gmaps.get_route_duration(
                12.90,
                80.12,
                13.00,
                80.25,
            )

            assert result["distance_meters"] == 1000
            assert call_count == 3


@run_async
async def test_invalid_coordinates_returns_invalid_request():
    gmaps = GoogleMapsClient(mock_redis)
    gmaps.api_key = "test-api-key"

    with pytest.raises(MapsAPIException) as excinfo:
        await gmaps.get_route_duration(
            100.0,
            80.12,
            13.00,
            80.25,
        )

    assert (
        excinfo.value.status_code
        == "INVALID_REQUEST"
    )


@run_async
async def test_batch_route_calculation_for_5_technicians():
    gmaps = GoogleMapsClient(mock_redis)
    gmaps.api_key = "test-api-key"

    origins = [
        (12.90, 80.12),
        (12.91, 80.13),
        (12.92, 80.14),
        (12.93, 80.15),
        (12.94, 80.16),
    ]

    destinations = [
        (13.00, 80.25)
    ]

    mock_api_response = {
        "status": "OK",
        "rows": [
            {
                "elements": [
                    {
                        "distance": {
                            "value": 10000
                        },
                        "duration": {
                            "value": 1000
                        },
                        "status": "OK",
                    }
                ]
            },
            {
                "elements": [
                    {
                        "distance": {
                            "value": 11000
                        },
                        "duration": {
                            "value": 1100
                        },
                        "status": "OK",
                    }
                ]
            },
            {
                "elements": [
                    {
                        "distance": {
                            "value": 12000
                        },
                        "duration": {
                            "value": 1200
                        },
                        "status": "OK",
                    }
                ]
            },
            {
                "elements": [
                    {
                        "distance": {
                            "value": 13000
                        },
                        "duration": {
                            "value": 1300
                        },
                        "status": "OK",
                    }
                ]
            },
            {
                "elements": [
                    {
                        "distance": {
                            "value": 14000
                        },
                        "duration": {
                            "value": 1400
                        },
                        "status": "OK",
                    }
                ]
            },
        ],
    }

    with patch(
        "aiohttp.ClientSession.get",
        return_value=MockResponse(
            mock_api_response,
            200,
        ),
    ):
        results = await gmaps.get_batch_route_durations(
            origins,
            destinations,
        )

        assert len(results) == 5
        assert results[0]["distance_meters"] == 10000
        assert results[4]["distance_meters"] == 14000


@run_async
async def test_fallback_when_api_completely_unavailable():
    gmaps = GoogleMapsClient(mock_redis)
    gmaps.api_key = "test-api-key"

    with patch(
        "aiohttp.ClientSession.get",
        side_effect=Exception(
            "Network down"
        ),
    ):
        with patch(
            "asyncio.sleep",
            return_value=None,
        ):
            with pytest.raises(MapsAPIException) as excinfo:
                await gmaps.get_route_duration(
                    12.90,
                    80.12,
                    13.00,
                    80.25,
                )

            assert (
                excinfo.value.status_code
                == "maps_unavailable"
            )


# ---------------------------------------------------------------------------
# Route endpoint metrics test
# ---------------------------------------------------------------------------

def test_metrics_collection_via_route_endpoints():
    mock_redis.flushall()

    mock_api_response = {
        "status": "OK",
        "routes": [
            {
                "summary": "Test Route",
                "legs": [
                    {
                        "distance": 5000,
                        "duration": 600,
                    }
                ],
                "overview_polyline": {
                    "points": "test_polyline"
                },
            }
        ],
    }

    # The GPS route endpoint now uses OlaMapsClient. Its transport is
    # implemented through ClientSession.request(..., method="POST").
    # Mock the transport boundary so this test verifies endpoint
    # metrics/cache behavior without making a real network request.
    with patch(
        "app.services.ola_map_client.OlaMapsClient._request",
        new_callable=AsyncMock,
        return_value=(mock_api_response, 200),
    ):
        # First request - cache miss
        response = client.get(
            "/api/v1/gps/route"
            "?origin_lat=12.90"
            "&origin_lng=80.12"
            "&dest_lat=13.00"
            "&dest_lng=80.25"
        )

    assert response.status_code == 200

    first_data = response.json()

    assert first_data["cached"] is False

    # Second request - should come from Redis cache
    response = client.get(
        "/api/v1/gps/route"
        "?origin_lat=12.90"
        "&origin_lng=80.12"
        "&dest_lat=13.00"
        "&dest_lng=80.25"
    )

    assert response.status_code == 200

    second_data = response.json()

    assert second_data["cached"] is True

def test_batch_calculation_limit_validation():
    # 6 origins * 2 destinations = 12 pairs
    # which is greater than the maximum of 10.
    payload = {
        "origins": [
            {
                "lat": 12.90,
                "lng": 80.12,
            },
            {
                "lat": 12.91,
                "lng": 80.13,
            },
            {
                "lat": 12.92,
                "lng": 80.14,
            },
            {
                "lat": 12.93,
                "lng": 80.15,
            },
            {
                "lat": 12.94,
                "lng": 80.16,
            },
            {
                "lat": 12.95,
                "lng": 80.17,
            },
        ],
        "destinations": [
            {
                "lat": 13.00,
                "lng": 80.25,
            },
            {
                "lat": 13.01,
                "lng": 80.26,
            },
        ],
    }

    response = client.post(
        "/api/v1/gps/route/batch",
        json=payload,
    )

    assert response.status_code == 400
    assert "Maximum 10" in response.json()["detail"]
