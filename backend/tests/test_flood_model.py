import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.services import flood_model_service as service


def test_status_reports_missing_checkpoint(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "get_flood_model_checkpoint", lambda: tmp_path / "missing.ckpt")
    body = TestClient(app).get("/api/v1/model/status").json()
    assert body["framework"] == "MindSpore"
    assert body["ready"] is False
    assert body["reason"]


def test_analyze_returns_503_without_checkpoint(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "get_flood_model_checkpoint", lambda: tmp_path / "missing.ckpt")
    monkeypatch.setattr(service, "_predictor", None)
    response = TestClient(app).post("/api/v1/model/analyze", json={"latitude": 15.1, "longitude": 120.85})
    assert response.status_code == 503


def test_analyze_rejects_coordinates_outside_the_philippines():
    response = TestClient(app).post("/api/v1/model/analyze", json={"latitude": 48.8, "longitude": 2.3})
    assert response.status_code == 422


def test_event_date_ranges_bracket_the_requested_day():
    radar, optical, target = service._date_ranges("2024-07-30")
    assert radar == "2024-07-23/2024-08-06"
    assert optical == "2024-07-18/2024-08-11"
    assert target == "2024-07-30T00:00:00Z"


def test_overlay_is_transparent_where_dry():
    probability = np.zeros((4, 4), dtype=np.float32)
    probability[1, 1] = 0.9
    assert service._overlay_png(probability).startswith("data:image/png;base64,")


def test_cropland_statistics_count_only_flooded_cropland():
    flooded = np.zeros((10, 10), dtype=bool)
    flooded[:5] = True
    cropland = np.zeros((10, 10), dtype=bool)
    cropland[3:8] = True
    stats = service._cropland_statistics(flooded, cropland, pixel_area_km2=0.0001)
    assert stats["cropland_area_km2"] == 0.005
    assert stats["flooded_cropland_km2"] == 0.002
    assert stats["flooded_share_of_cropland"] == 0.4
    assert service._cropland_statistics(flooded, None, 0.0001) is None
