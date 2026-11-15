import numpy as np

from app.services.weather_fields import outlook_rgba


def _samples(rain):
    return [{"longitude": 120.0 + i * 0.5, "latitude": 14.0 + j * 0.5, "rainfall_24h_mm": rain} for i in range(4) for j in range(4)]


def _inputs():
    scores = np.zeros((60, 60), dtype=np.uint8)
    scores[:30] = 255  # high flood-prone
    scores[30:] = 160  # moderate flood-prone (about 0.63)
    base = np.zeros((60, 60, 4), dtype=np.uint8)
    base[..., 3] = 200
    return base, scores


def test_outlook_recolours_only_where_forecast_rain_meets_flood_prone_terrain():
    base, scores = _inputs()
    heavy = outlook_rgba(base, scores, 121, 14, _samples(60.0))
    assert tuple(heavy[10, 10, :3]) == (200, 62, 62)  # heavy rain over high terrain: warning
    assert tuple(heavy[50, 10, :3]) == (238, 138, 43)  # heavy rain over moderate terrain: watch

    light = outlook_rgba(base, scores, 121, 14, _samples(2.0))
    level_colours = [(240, 201, 58), (238, 138, 43), (200, 62, 62)]
    assert not any((light[..., :3] == colour).all(axis=-1).any() for colour in level_colours)


def test_outlook_leaves_undrawn_pixels_transparent():
    base, scores = _inputs()
    base[..., 3] = 0
    assert outlook_rgba(base, scores, 121, 14, _samples(120.0))[..., 3].max() == 0
