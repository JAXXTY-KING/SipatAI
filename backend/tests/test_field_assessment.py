import numpy as np
from affine import Affine
from fastapi.testclient import TestClient
from shapely.geometry import box
from shapely.ops import transform as transform_geometry
from pyproj import Transformer

from app.db import assessment_store
from app.integrations.ftw_fields_client import FieldPolygon, field_year_for
from app.main import app
from app.services.field_assessment_service import assess_fields, severity_for


def _field(field_id: str, west: float, south: float, east: float, north: float) -> FieldPolygon:
    return FieldPolygon(field_id, box(west, south, east, north).wkb, 98.0, 0.0)


def test_field_years_pick_the_closest_available_mapping():
    assert field_year_for(None) == 2025
    assert field_year_for(2024) == 2024
    assert field_year_for(2019) == 2024
    assert field_year_for(2030) == 2025


def test_severity_breaks():
    assert [severity_for(share) for share in (0.0, 0.1, 0.3, 0.6, 1.0)] == [
        "Unaffected", "Light", "Moderate", "Severe", "Severe",
    ]


def test_field_assessment_measures_flooded_share_per_field():
    # 100 x 100 pixel grid of 10 m in UTM 51N, with the top-left corner at a known longitude/latitude
    to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True)
    left, top = to_utm.transform(120.80, 15.10)
    transform = Affine(10, 0, left, 0, -10, top)
    to_wgs = Transformer.from_crs("EPSG:32651", "EPSG:4326", always_xy=True).transform

    def utm_box(x0, y0, x1, y1):  # pixel coordinates -> lon/lat polygon
        return transform_geometry(to_wgs, box(left + x0 * 10, top - y1 * 10, left + x1 * 10, top - y0 * 10))

    flooded = np.zeros((100, 100), dtype=bool)
    flooded[:, :50] = True  # left half of the tile is flooded
    fields = [
        FieldPolygon("flooded", utm_box(5, 5, 30, 30).wkb, 99.0, 0.0),
        FieldPolygon("half", utm_box(40, 40, 60, 60).wkb, 99.0, 0.0),
        FieldPolygon("dry", utm_box(70, 70, 90, 90).wkb, 99.0, 0.0),
    ]

    result = assess_fields(fields, flooded, "EPSG:32651", transform, 2024)
    by_id = {feature["properties"]["field_id"]: feature["properties"] for feature in result["geojson"]["features"]}

    assert by_id["flooded"]["severity"] == "Severe" and by_id["flooded"]["flooded_share"] == 1.0
    assert by_id["dry"]["severity"] == "Unaffected" and by_id["dry"]["flooded_ha"] == 0.0
    assert 0.4 <= by_id["half"]["flooded_share"] <= 0.6 and by_id["half"]["severity"] == "Moderate"
    summary = result["summary"]
    assert summary["fields_analysed"] == 3 and summary["fields_affected"] == 2
    assert summary["severity_counts"] == {"Severe": 1, "Moderate": 1, "Light": 0, "Unaffected": 1}


def test_saved_assessments_round_trip_and_report(monkeypatch, tmp_path):
    monkeypatch.setattr(assessment_store, "DATABASE_PATH", tmp_path / "assessments.sqlite")
    summary = {
        "statistics": {"flooded_area_km2": 1.0, "tile_area_km2": 26.2, "flooded_fraction": 0.04},
        "cropland": None,
        "field_summary": None,
        "observations": {
            "sentinel_1": {"id": "S1A_test", "datetime": "2024-07-30T10:00:00Z"},
            "sentinel_2": {"id": "S2A_test", "datetime": "2024-08-04T02:00:00Z", "cloud_cover_percent": 10.0},
        },
        "warnings": [],
    }
    identifier = assessment_store.save_assessment(15.0, 120.6, "2024-07-30", summary)
    client = TestClient(app)

    listing = client.get("/api/v1/model/assessments").json()["assessments"]
    assert listing[0]["id"] == identifier and listing[0]["statistics"]["flooded_area_km2"] == 1.0
    report = client.post(f"/api/v1/reports/satellite-assessment/{identifier}")
    assert report.status_code == 200 and report.content.startswith(b"%PDF")
    assert client.post("/api/v1/reports/satellite-assessment/9999").status_code == 404
