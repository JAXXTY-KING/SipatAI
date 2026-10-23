import time

import pytest
from fastapi.testclient import TestClient

from app.integrations import openweathermap_client as owm
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
