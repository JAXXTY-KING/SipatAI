from fastapi.testclient import TestClient

from app.api.routes import reports
from app.main import app


def test_flood_screening_report_does_not_require_assessment_database(monkeypatch):
    async def fake_screening():
        return {
            "provider": "Open-Meteo",
            "fetched_at": "2026-11-08T05:00:00+00:00",
            "forecast_period_hours": 72,
            "grid_resolution_degrees": 0.5,
            "method": {
                "elevated": "100 mm and low elevation",
                "watch": "50 mm or 25 mm and low elevation",
                "lower": "below the screening threshold",
            },
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [122.0, 10.0]},
                "properties": {
                    "screening_level": "elevated",
                    "rainfall_24h_mm": 120.0,
                    "rainfall_72h_mm": 250.0,
                    "latitude": 10.0,
                    "longitude": 122.0,
                    "elevation_m": 12,
                },
            }],
        }

    monkeypatch.setattr(reports, "get_nationwide_flood_screening", fake_screening)
    response = TestClient(app).post("/api/v1/reports/flood-screening")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
