import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services.ola_map_client import (
    MapsAPIException,
    OlaMapsClient,
    is_valid_coordinate,
    is_valid_route_result,
)


@pytest.mark.parametrize(
    "latitude,longitude",
    [
        (None, 80.2),
        (float("nan"), 80.2),
        (91, 80.2),
        (13.0, 181),
        (0, 0),
    ],
)
def test_route_coordinate_validator_rejects_invalid_values(latitude, longitude):
    assert not is_valid_coordinate(latitude, longitude)


def test_route_coordinate_validator_accepts_valid_zero_axis_coordinates():
    assert is_valid_coordinate(0, 80.2)
    assert is_valid_coordinate(13.0, 0)


def test_route_result_validator_checks_measurements_and_route_points():
    valid = {
        "distance_meters": 1234,
        "duration_seconds": 90,
        "duration_in_traffic_seconds": 100,
        "route_points": [[80.2, 13.0], [80.3, 13.1]],
    }
    assert is_valid_route_result(valid)
    assert not is_valid_route_result({**valid, "distance_meters": float("nan")})
    assert not is_valid_route_result({**valid, "distance_meters": -1})
    assert not is_valid_route_result({**valid, "duration_seconds": -1})
    assert not is_valid_route_result({**valid, "route_points": [[181, 13.0]]})


def test_first_ola_route_call_uses_the_requested_origin_and_destination():
    client = OlaMapsClient(redis_client=None)
    client._request = AsyncMock(return_value=(
        {
            "status": "OK",
            "routes": [{
                "legs": [{"distance": 4321, "duration": 321}],
                "overview_polyline": "",
            }],
        },
        200,
    ))

    result = asyncio.run(client.get_route_duration(13.085, 80.2101, 13.0827, 80.2707))

    client._request.assert_awaited_once()
    args = client._request.await_args.args
    assert args[1]["origin"] == "13.085,80.2101"
    assert args[1]["destination"] == "13.0827,80.2707"
    assert result["distance_meters"] == 4321


@pytest.mark.parametrize(
    "distance,duration",
    [(float("nan"), 10), (-1, 10), (20, float("inf")), (20, -1)],
)
def test_invalid_ola_route_measurements_are_rejected(distance, duration):
    client = OlaMapsClient(redis_client=None)
    client._request = AsyncMock(return_value=(
        {
            "status": "OK",
            "routes": [{
                "legs": [{"distance": distance, "duration": duration}],
                "overview_polyline": "",
            }],
        },
        200,
    ))

    with pytest.raises(MapsAPIException, match="invalid"):
        asyncio.run(client.get_route_duration(13.085, 80.2101, 13.0827, 80.2707))


def test_route_client_rejects_zero_zero_before_calling_ola():
    client = OlaMapsClient(redis_client=None)
    client._request = AsyncMock()

    with pytest.raises(MapsAPIException) as error:
        asyncio.run(client.get_route_duration(0, 0, 13.0827, 80.2707))

    assert error.value.status_code == "INVALID_REQUEST"
    client._request.assert_not_awaited()
