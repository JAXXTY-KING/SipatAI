from fastapi.testclient import TestClient

from app.db import scan_store
from app.main import app
from app.services.nationwide_grid import land_tiles, tiles_by_province


def test_land_tiles_cover_every_province_on_real_boundaries():
    tiles = land_tiles()
    assert 12_000 < len(tiles) < 15_500
    assert len({tile.tile_id for tile in tiles}) == len(tiles)
    assert all(4.0 < tile.latitude < 21.5 and 114.0 < tile.longitude < 127.5 for tile in tiles)
    assert len(tiles_by_province()) == 87


def _use_temporary_store(monkeypatch, tmp_path):
    monkeypatch.setattr(scan_store, "DATA_DIRECTORY", tmp_path)
    monkeypatch.setattr(scan_store, "SCAN_DATABASE_PATH", tmp_path / "scans.sqlite")
    monkeypatch.setattr(scan_store, "OVERLAY_DIRECTORY", tmp_path / "overlays")


def _record(tile_id, province, flooded_km2, fraction, mode="radar-only"):
    return {
        "tile_id": tile_id, "latitude": 15.0, "longitude": 120.6, "province": province, "status": "ok",
        "s1_date": "2026-11-06", "mode": mode, "flooded_km2": flooded_km2, "flooded_fraction": fraction,
        "corners": [[120.58, 15.02], [120.62, 15.02], [120.62, 14.98], [120.58, 14.98]],
    }


def test_scan_summary_and_viewport_query(monkeypatch, tmp_path):
    _use_temporary_store(monkeypatch, tmp_path)
    scan_store.save_scan(_record("15.000_120.600", "Pampanga", 2.0, 0.08, "radar+optical"))
    scan_store.save_scan(_record("16.000_121.600", "Cagayan", 0.0, 0.0))
    scan_store.save_scan({"tile_id": "9.000_125.000", "latitude": 9.0, "longitude": 125.0, "province": "Bohol",
                          "status": "no_data", "message": "No Sentinel-1 scene"})

    summary = scan_store.scan_summary({"Pampanga": 10, "Cagayan": 10, "Bohol": 10})
    assert summary["tiles_total"] == 30 and summary["tiles_scanned"] == 2 and summary["tiles_failed"] == 1
    assert summary["flooded_km2"] == 2.0 and summary["tiles_with_flooding"] == 1 and summary["tiles_with_optical"] == 1
    assert summary["provinces"][0]["province"] == "Pampanga"

    inside = scan_store.overlays_in_bbox(120.0, 14.5, 121.0, 15.5)
    assert [tile["tile_id"] for tile in inside] == ["15.000_120.600"]  # unflooded and failed tiles are not drawn
    assert scan_store.overlays_in_bbox(130.0 - 5, 0.0, 130.0 - 4, 1.0) == []


def test_scan_api_serves_summary_and_rejects_bad_overlay_ids(monkeypatch, tmp_path):
    _use_temporary_store(monkeypatch, tmp_path)
    client = TestClient(app)
    assert client.get("/api/v1/scan/summary").json()["tiles_scanned"] == 0
    assert client.get("/api/v1/scan/overlay/..%2Fsecret.png").status_code == 404
    assert client.get("/api/v1/scan/overlay/1.000_2.000.png").status_code == 404
    path = scan_store.overlay_path("15.000_120.600")
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    assert client.get("/api/v1/scan/overlay/15.000_120.600.png").status_code == 200
