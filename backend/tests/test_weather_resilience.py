import asyncio
import io

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.integrations import flood_screening_client as flood_screening
from app.integrations import himawari_client
from app.main import app


def _forecast_payload():
    hours = [f"2026-11-08T{hour:02}:00" for hour in range(24)] * 3
    return {
        "hourly": {
            "time": hours,
            "precipitation": [0.0] * 72,
            "temperature_2m": [28.0] * 72,
            "pressure_msl": [1008.0] * 72,
            "wind_speed_10m": [18.0] * 72,
            "wind_direction_10m": [90.0] * 72,
        },
        "elevation": 10,
    }


class _Response:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self.headers = {}
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", flood_screening.FORECAST_URL)
            raise httpx.HTTPStatusError(
                "error", request=request, response=httpx.Response(self.status_code, request=request)
            )

    def json(self):
        return self._payload


class _FlakyClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    async def get(self, *_args, **_kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(flood_screening.asyncio, "sleep", no_sleep)


def test_forecast_batch_retries_rate_limits_and_timeouts():
    client = _FlakyClient([
        _Response(429),
        httpx.ReadTimeout("slow"),
        _Response(200, _forecast_payload()),
    ])
    result = asyncio.run(flood_screening._fetch_forecast_batch(client, ((10.0, 122.0),)))
    assert client.calls == 3
    assert result[0]["temperature_2m_c"] == 28.0


def test_forecast_batch_does_not_retry_client_errors():
    client = _FlakyClient([_Response(400)])
    with pytest.raises(flood_screening.FloodScreeningError, match="HTTP 400"):
        asyncio.run(flood_screening._fetch_forecast_batch(client, ((10.0, 122.0),)))
    assert client.calls == 1


def test_forecast_batch_gives_up_after_repeated_failures():
    client = _FlakyClient([httpx.ConnectError("down")] * flood_screening.FETCH_ATTEMPTS)
    with pytest.raises(flood_screening.FloodScreeningError):
        asyncio.run(flood_screening._fetch_forecast_batch(client, ((10.0, 122.0),)))
    assert client.calls == flood_screening.FETCH_ATTEMPTS


def test_simultaneous_requests_share_one_provider_fetch(monkeypatch):
    flood_screening._SCREENING_CACHE = None
    flood_screening._IN_FLIGHT.clear()
    builds = 0

    async def slow_build():
        nonlocal builds
        builds += 1
        await asyncio.sleep(0)
        flood_screening._SCREENING_CACHE = (flood_screening.time.monotonic(), {"features": []})
        return flood_screening._SCREENING_CACHE[1]

    monkeypatch.setattr(flood_screening, "_build_flood_screening", slow_build)

    async def run():
        return await asyncio.gather(*(flood_screening.get_nationwide_flood_screening() for _ in range(5)))

    results = asyncio.run(run())
    assert builds == 1
    assert all(result == {"features": []} for result in results)
    flood_screening._SCREENING_CACHE = None


def test_last_forecast_is_served_when_provider_fails(monkeypatch):
    stale = {"features": [{"stale": True}]}
    flood_screening._SCREENING_CACHE = (flood_screening.time.monotonic() - 10_000, stale)
    flood_screening._IN_FLIGHT.clear()

    async def failing_build():
        raise flood_screening.FloodScreeningError("down")

    monkeypatch.setattr(flood_screening, "_build_flood_screening", failing_build)
    assert asyncio.run(flood_screening.get_nationwide_flood_screening()) is stale
    flood_screening._SCREENING_CACHE = None


def test_failure_without_previous_forecast_is_reported(monkeypatch):
    flood_screening._SCREENING_CACHE = None
    flood_screening._IN_FLIGHT.clear()

    async def failing_build():
        raise flood_screening.FloodScreeningError("down")

    monkeypatch.setattr(flood_screening, "_build_flood_screening", failing_build)
    assert TestClient(app).get("/api/v1/weather/flood-screening").status_code == 502


def _infrared_tile(values):
    tile = Image.new("L", (len(values), 1))
    tile.putdata(values)
    output = io.BytesIO()
    tile.convert("RGB").save(output, format="JPEG", quality=100)
    return output.getvalue()


def test_cloud_overlay_makes_clear_sky_transparent_and_clouds_opaque():
    overlay = Image.open(io.BytesIO(himawari_client._cloud_overlay_png(_infrared_tile([30] * 8 + [230] * 8))))
    assert overlay.mode == "RGBA"
    assert overlay.getpixel((2, 0))[3] == 0
    assert overlay.getpixel((13, 0))[3] > 200
    assert overlay.getpixel((13, 0))[0] > 200


def test_cloud_overlay_rejects_non_image_data():
    with pytest.raises(himawari_client.HimawariServiceError):
        himawari_client._cloud_overlay_png(b"not an image")


def test_tile_frames_are_the_latest_observations_oldest_first(monkeypatch):
    himawari_client._TILE_INDEX_CACHE = None
    index = (
        "[" + ",".join(
            f'{{"basetime": "20261114{n:02}0000", "validtime": "20261114{n:02}0000"}}' for n in range(20)
        ) + ', {"basetime": "20261114000000", "validtime": "20261114230000"}]'
    )

    class FakeResponse:
        text = index

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url):
            assert url == himawari_client.TILE_INDEX_URL
            return FakeResponse()

    monkeypatch.setattr(himawari_client.httpx, "AsyncClient", FakeClient)
    frames = asyncio.run(himawari_client.get_himawari_tile_frames())
    assert len(frames) == himawari_client.TILE_FRAME_COUNT
    assert [frame["time_code"] for frame in frames] == sorted(frame["time_code"] for frame in frames)
    assert frames[-1]["time_code"] == "20261114190000"
    assert frames[-1]["observed_at"] == "19:00 UTC 14 Nov 2026"
    himawari_client._TILE_INDEX_CACHE = None


@pytest.mark.parametrize("path", [
    "/api/v1/weather/himawari/tiles/20261114010000/2/0/0.png",
    "/api/v1/weather/himawari/tiles/20261114010000/9/0/0.png",
    "/api/v1/weather/himawari/tiles/20261114010000/5/99/0.png",
])
def test_cloud_tile_outside_available_range_is_not_found(path):
    assert TestClient(app).get(path).status_code == 404


def test_cloud_tile_time_must_be_a_14_digit_code():
    assert TestClient(app).get("/api/v1/weather/himawari/tiles/../5/1/1.png").status_code in (404, 422)
    assert TestClient(app).get("/api/v1/weather/himawari/tiles/abcd/5/1/1.png").status_code == 422
