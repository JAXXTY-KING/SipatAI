import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import susceptibility_service as service


def _local(high_share):
    return {"point_score": 0.5, "radius_km": 5.0, "land_share_high": high_share, "land_share_moderate_or_high": high_share}


def _forecast(rain_24h):
    return {"name": "X", "rainfall_24h_mm": rain_24h, "rainfall_72h_mm": rain_24h, "precipitation_6h_mm": 0.0,
            "temperature_2m_c": 28.0, "pressure_msl_hpa": 1008.0, "forecast_start": "t", "sample_points": 1}


@pytest.mark.parametrize(
    ("share", "rain", "level"),
    [(0.5, 1.0, "none"), (0.5, 30.0, "watch"), (0.5, 60.0, "warning"), (0.5, 120.0, "warning"),
     (0.01, 120.0, "watch"), (0.1, 30.0, "advisory"), (0.01, 60.0, "advisory")],
)
def test_flood_watch_combines_terrain_and_forecast_rain(share, rain, level):
    assert service.flood_watch(_local(share), _forecast(rain))["level"] == level


def test_flood_watch_is_honest_without_a_forecast():
    watch = service.flood_watch(_local(0.5), None)
    assert watch["level"] == "unknown" and watch["terrain"] == "high"


def test_susceptibility_api_rejects_bad_chunk_ids_and_serves_status(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "NATIONAL_DIRECTORY", tmp_path)
    client = TestClient(app)
    assert client.get("/api/v1/model/susceptibility/status").json()["ready"] is False
    assert client.get("/api/v1/model/susceptibility/chunk/..%2Fsecret.png").status_code == 404
    assert client.get("/api/v1/model/susceptibility/chunk/121E_14N.png").status_code == 404
    assert client.get("/api/v1/model/susceptibility/chunks?west=120&south=14&east=121&north=15").status_code == 503
