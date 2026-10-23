import pytest
from fastapi.testclient import TestClient

from app.integrations.sentinel_download import build_object_key, normalise_product_name
from app.main import app


def test_normalise_adds_safe_suffix():
    assert normalise_product_name("S2A_MSIL2A_20250706") == "S2A_MSIL2A_20250706.SAFE"


@pytest.mark.parametrize("name", ["../etc/passwd", "a b", "x'; drop", ""])
def test_normalise_rejects_unsafe_names(name):
    with pytest.raises(ValueError):
        normalise_product_name(name)


def test_object_key_is_relative():
    assert build_object_key("sentinel-2-l2a", "S2A_X.SAFE") == "raw/sentinel-2-l2a/S2A_X.zip"


def test_download_requires_credentials(monkeypatch):
    monkeypatch.delenv("COPERNICUS_USERNAME", raising=False)
    monkeypatch.delenv("COPERNICUS_PASSWORD", raising=False)
    response = TestClient(app).post(
        "/api/v1/scenes/download",
        json={"collection": "sentinel-2-l2a", "product_name": "S2A_MSIL2A_20250706T0000"},
    )
    assert response.status_code == 503


def test_download_rejects_invalid_name():
    response = TestClient(app).post(
        "/api/v1/scenes/download",
        json={"collection": "sentinel-2-l2a", "product_name": "../../bad-name-here"},
    )
    assert response.status_code == 422
