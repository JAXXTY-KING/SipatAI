import time

import pytest
from fastapi.testclient import TestClient

from app.integrations import openweathermap_client as owm
from app.integrations import open_meteo_weather_client as open_meteo
from app.integrations import flood_screening_client as flood_screening
from app.integrations import himawari_client
from app.api.routes import weather as weather_routes
from app.main import app


def test_overview_requires_configured_key(monkeypatch):
    monkeypatch.delenv("OPENWEATHERMAP_API_KEY", raising=False)
    monkeypatch.setattr(owm, "get_openweathermap_api_key", lambda: None)
    owm._OVERVIEW_CACHE.clear()
    assert TestClient(app).get("/api/v1/weather/overview").status_code == 503


def test_overview_builds_geojson_and_skips_failures(monkeypatch):
    owm._OVERVIEW_CACHE.clear()

    async def fake_current(lat, lon):
        if lat > 18:
            raise owm.WeatherServiceError("boom")
        return {"temperature_c": 27.0, "description": "clear"}

    monkeypatch.setattr(owm, "get_current_weather", fake_current)
    body = TestClient(app).get("/api/v1/weather/overview").json()
    assert body["type"] == "FeatureCollection"
    names = {f["properties"]["location_name"] for f in body["features"]}
    assert "Laoag" not in names and "Davao City" in names
    owm._OVERVIEW_CACHE.clear()


def test_tile_layer_allowlist():
    assert TestClient(app).get("/api/v1/weather/tiles/evil/1/0/0.png").status_code == 404


def test_location_search_uses_open_meteo_and_filters_non_philippine_results(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "results": [
                    {
                        "name": "Manila",
                        "admin1": "Metro Manila",
                        "country": "Philippines",
                        "country_code": "PH",
                        "latitude": 14.6,
                        "longitude": 120.98,
                    },
                    {
                        "name": "Manila",
                        "country": "United States",
                        "country_code": "US",
                        "latitude": 36.0,
                        "longitude": -83.7,
                    },
                ]
            }

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, *, params):
            assert url == open_meteo.GEOCODING_URL
            assert params["name"] == "Manila"
            return FakeResponse()

    monkeypatch.setattr(open_meteo.httpx, "AsyncClient", FakeClient)
    response = TestClient(app).get("/api/v1/weather/locations?q=Manila")
    assert response.status_code == 200
    assert response.json()["locations"] == [{
        "name": "Manila",
        "state": "Metro Manila",
        "country": "Philippines",
        "latitude": 14.6,
        "longitude": 120.98,
    }]


def test_current_weather_uses_open_meteo_without_provider_key(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "latitude": 14.6,
                "longitude": 120.98,
                "current": {
                    "time": "2026-11-08T08:00",
                    "temperature_2m": 29.3,
                    "relative_humidity_2m": 75,
                    "apparent_temperature": 34.1,
                    "precipitation": 0.2,
                    "weather_code": 61,
                    "wind_speed_10m": 2.4,
                    "wind_direction_10m": 90,
                },
            }

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, *, params):
            assert url == open_meteo.FORECAST_URL
            assert params["wind_speed_unit"] == "ms"
            assert "temperature_2m" in params["current"]
            return FakeResponse()

    monkeypatch.setattr(open_meteo.httpx, "AsyncClient", FakeClient)
    response = TestClient(app).post(
        "/api/v1/weather/current",
        json={"latitude": 14.6, "longitude": 120.98},
    )
    assert response.status_code == 200
    assert response.json()["provider"] == "Open-Meteo"
    assert response.json()["temperature_c"] == 29.3
    assert response.json()["condition"] == "Rain"
    assert response.json()["precipitation_1h_mm"] == 0.2


def test_himawari_image_uses_latest_jma_sector_time(monkeypatch):
    himawari_client._IMAGE_CACHE.clear()
    himawari_client._FRAME_CACHE = None

    class FakeResponse:
        def __init__(self, *, text="", content=b""):
            self.text = text
            self.content = content

        def raise_for_status(self):
            return None

    class FakeClient:
        requested_urls = []

        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url):
            self.__class__.requested_urls.append(url)
            if url == himawari_client.SOURCE_PAGE_URL:
                return FakeResponse(
                    text='<select name="slt_time"><option value=0540>05:50 UTC 08 November 2026</option></select>'
                )
            return FakeResponse(content=b"\xff\xd8fake-jpeg")

    monkeypatch.setattr(himawari_client.httpx, "AsyncClient", FakeClient)
    response = TestClient(app).get("/api/v1/weather/himawari/latest.jpg")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["x-himawari-observation-time"] == "05:50 UTC 08 November 2026"
    assert response.headers["x-himawari-band"] == "B13 (Infrared)"
    assert response.content == b"\xff\xd8fake-jpeg"
    assert FakeClient.requested_urls == [
        himawari_client.SOURCE_PAGE_URL,
        himawari_client.IMAGE_URL_TEMPLATE.format(band="b13", time_code="0540"),
    ]
    himawari_client._IMAGE_CACHE.clear()
    himawari_client._FRAME_CACHE = None


def test_himawari_frames_are_returned_newest_first(monkeypatch):
    himawari_client._FRAME_CACHE = None

    class FakeResponse:
        text = (
            '<select name="slt_time">'
            '<option value="0540">05:50 UTC</option>'
            '<option value="0530">05:40 UTC</option>'
            '<option value="0520">05:30 UTC</option>'
            '</select>'
        )

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url):
            return FakeResponse()

    monkeypatch.setattr(himawari_client.httpx, "AsyncClient", FakeClient)
    frames = TestClient(app).get("/api/v1/weather/himawari/frames?band=b13")
    assert frames.status_code == 200
    assert [frame["time_code"] for frame in frames.json()["frames"]] == ["0540", "0530", "0520"]
    himawari_client._FRAME_CACHE = None


def test_himawari_image_rejects_unsupported_band():
    response = TestClient(app).get("/api/v1/weather/himawari/latest.jpg?band=unknown")
    assert response.status_code == 422


def test_himawari_image_accepts_visible_daylight_band(monkeypatch):
    async def fake_image(band, time_code):
        assert band == "b03"
        assert time_code == "0540"
        return b"\xff\xd8visible-jpeg", "05:50 UTC 08 November 2026"

    monkeypatch.setattr(weather_routes, "get_himawari_image", fake_image)
    response = TestClient(app).get("/api/v1/weather/himawari/latest.jpg?band=b03&time_code=0540")
    assert response.status_code == 200
    assert response.headers["x-himawari-band"] == "B03 (Visible)"
    assert response.content == b"\xff\xd8visible-jpeg"


def test_flood_screening_builds_grid_and_caches_forecast(monkeypatch):
    flood_screening._SCREENING_CACHE = None
    monkeypatch.setattr(flood_screening, "_forecast_grid", lambda: ((10.0, 122.0),))

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "hourly": {
                    "time": [f"2026-11-08T{hour:02}:00" for hour in range(24)]
                    + [f"2026-11-09T{hour:02}:00" for hour in range(24)]
                    + [f"2026-11-10T{hour:02}:00" for hour in range(24)],
                    "precipitation": [5.0] * 72,
                    "temperature_2m": [28.0] * 72,
                    "pressure_msl": [1008.5] * 72,
                    "wind_speed_10m": [36.0] * 72,
                    "wind_direction_10m": [90.0] * 72,
                },
                "elevation": 12,
            }

    class FakeClient:
        params = None

        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            self.__class__.params = _kwargs["params"]
            return FakeResponse()

    monkeypatch.setattr(flood_screening.httpx, "AsyncClient", FakeClient)
    response = TestClient(app).get("/api/v1/weather/flood-screening")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "Open-Meteo"
    assert body["forecast_period_hours"] == 72
    assert body["features"][0]["properties"]["temperature_2m_c"] == 28.0
    assert body["features"][0]["properties"]["precipitation_6h_mm"] == 30.0
    assert body["features"][0]["properties"]["pressure_msl_hpa"] == 1008.5
    assert body["features"][0]["properties"]["rainfall_24h_mm"] == 120.0
    assert body["features"][0]["properties"]["rainfall_72h_mm"] == 360.0
    assert body["features"][0]["properties"]["screening_level"] == "elevated"
    assert FakeClient.params["forecast_hours"] == 72
    assert FakeClient.params["hourly"] == (
        "precipitation,temperature_2m,pressure_msl,wind_speed_10m,wind_direction_10m"
    )
    assert "wind_speed_10m_mps" not in body["features"][0]["properties"]
    flood_screening._SCREENING_CACHE = None


@pytest.mark.parametrize(
    ("rainfall", "elevation", "expected"),
    [
        (100, 500, "elevated"),
        (50, 20, "elevated"),
        (50, 500, "watch"),
        (25, 30, "watch"),
        (25, 31, "lower"),
    ],
)
def test_screening_levels_apply_rainfall_and_elevation_thresholds(rainfall, elevation, expected):
    assert flood_screening._screening_level(rainfall, elevation) == expected


def test_wind_forecast_returns_hourly_vectors_for_map_animation(monkeypatch):
    flood_screening._WIND_CACHE = None
    monkeypatch.setattr(flood_screening, "_wind_forecast_grid", lambda: ((10.0, 122.0),))

    async def fake_fetch_forecast_batch(_client, locations):
        return [
            {
                "latitude": latitude,
                "longitude": longitude,
                "forecast_times": [f"2026-11-08T{hour:02}:00" for hour in range(24)]
                + [f"2026-11-09T{hour:02}:00" for hour in range(24)]
                + [f"2026-11-10T{hour:02}:00" for hour in range(24)],
                "wind_speed_10m_mps": [10.0] * 72,
                "wind_direction_10m_deg": [90.0] * 72,
            }
            for latitude, longitude in locations
        ]

    monkeypatch.setattr(flood_screening, "_fetch_forecast_batch", fake_fetch_forecast_batch)
    response = TestClient(app).get("/api/v1/weather/wind-forecast")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "Open-Meteo"
    assert len(body["forecast_times"]) == 72
    assert body["features"][0]["geometry"]["coordinates"] == [122.0, 10.0]
    assert body["features"][0]["properties"]["wind_speed_10m_mps"][0] == 10.0
    assert body["features"][0]["properties"]["wind_direction_10m_deg"][0] == 90.0
    flood_screening._WIND_CACHE = None
