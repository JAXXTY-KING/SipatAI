"""Map images and isobars interpolated between the real Open-Meteo forecast points (no invented data).

The forecast points are about 0.5 degrees (50 km) apart, so these fields are smooth model-resolution
pictures, not station or radar observations.
"""
import io
from typing import Any

import numpy as np
from PIL import Image
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator
from scipy.ndimage import gaussian_filter, maximum_filter, minimum_filter, zoom
from scipy.spatial import cKDTree

from app.integrations.province_forecast_client import get_forecast_samples

WEST, SOUTH, EAST, NORTH = 116.5, 4.5, 127.0, 21.5
RESOLUTION = 0.05

RAIN_STOPS = (0.0, 0.1, 1.0, 3.0, 8.0, 15.0, 30.0)
RAIN_COLOURS = ((199, 182, 240), (160, 130, 232), (120, 84, 222), (98, 52, 206), (140, 40, 190), (190, 30, 150), (214, 30, 90))
RAIN_ALPHA = (0, 120, 150, 170, 185, 200, 215)
PRESSURE_COLOURS = ((58, 76, 192), (235, 235, 235), (214, 96, 77))
LEVEL_COLOURS = {1: ((240, 201, 58), 150), 2: ((238, 138, 43), 185), 3: ((200, 62, 62), 215)}
_cache: dict[tuple, Any] = {}


def _interpolate(samples: list[dict[str, Any]], key: str, longitudes: np.ndarray, latitudes: np.ndarray):
    """Linear interpolation between forecast points; `inside` marks pixels within ~0.45 degrees of a real point."""
    points = np.array([[sample["longitude"], sample["latitude"]] for sample in samples], dtype=float)
    values = np.array([sample[key] for sample in samples], dtype=float)
    linear = LinearNDInterpolator(points, values)(longitudes, latitudes)
    filled = np.where(np.isnan(linear), NearestNDInterpolator(points, values)(longitudes, latitudes), linear)
    distance, _ = cKDTree(points).query(np.column_stack([longitudes.ravel(), latitudes.ravel()]))
    return filled, distance.reshape(longitudes.shape) <= 0.45


def _grid() -> tuple[np.ndarray, np.ndarray]:
    longitudes = np.arange(WEST, EAST, RESOLUTION) + RESOLUTION / 2
    latitudes = np.arange(NORTH, SOUTH, -RESOLUTION) - RESOLUTION / 2
    return np.meshgrid(longitudes, latitudes)


def _ramp_rgba(values: np.ndarray, stops, colours, alphas) -> np.ndarray:
    rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
    for channel in range(3):
        rgba[..., channel] = np.interp(values, stops, [colour[channel] for colour in colours])
    rgba[..., 3] = np.interp(values, stops, alphas)
    return rgba


def _png(rgba: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _pressure_range(values: np.ndarray, inside: np.ndarray) -> tuple[float, float]:
    """Colour scale of the current forecast, at least 6 hPa wide so small differences stay readable."""
    low, high = float(values[inside].min()), float(values[inside].max())
    if high - low < 6:
        centre = (low + high) / 2
        low, high = centre - 3, centre + 3
    return low, high


async def field_png(variable: str) -> tuple[bytes, str]:
    """PNG covering BOUNDS for 'rain' (next 6 h precipitation) or 'pressure' (mean sea-level pressure)."""
    samples, fetched_at = await get_forecast_samples()
    key = (variable, fetched_at)
    if key not in _cache:
        longitudes, latitudes = _grid()
        if variable == "rain":
            values, inside = _interpolate(samples, "precipitation_6h_mm", longitudes, latitudes)
            values = gaussian_filter(values, 2.0)
            rgba = _ramp_rgba(values, RAIN_STOPS, RAIN_COLOURS, RAIN_ALPHA)
        else:
            values, inside = _interpolate(samples, "pressure_msl_hpa", longitudes, latitudes)
            values = gaussian_filter(values, 4.0)
            low, high = _pressure_range(values, inside)
            middle = (low + high) / 2
            rgba = _ramp_rgba(values, (low, middle, high), PRESSURE_COLOURS, (170, 120, 170))
        rgba[..., 3] = np.where(gaussian_filter(inside.astype(float), 2.0) > 0.5, rgba[..., 3], 0)
        _cache.clear()
        _cache[key] = _png(rgba)
    return _cache[key], fetched_at


async def isobars() -> dict[str, Any]:
    """Isobars every 1 hPa plus the H and L centres, from the real forecast pressure."""
    from contourpy import contour_generator

    samples, fetched_at = await get_forecast_samples()
    longitudes, latitudes = _grid()
    values, inside = _interpolate(samples, "pressure_msl_hpa", longitudes, latitudes)
    values = gaussian_filter(values, 4.0)
    low, high = _pressure_range(values, inside)
    masked = np.ma.masked_array(values, mask=gaussian_filter(inside.astype(float), 2.0) <= 0.5)
    generator = contour_generator(longitudes, latitudes, masked)
    features = []
    for level in range(int(np.ceil(values[~masked.mask].min())), int(np.floor(values[~masked.mask].max())) + 1):
        for line in generator.lines(float(level)):
            if len(line) > 5:
                features.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": line.tolist()},
                                 "properties": {"hpa": level, "label": f"{level}"}})
    for kind, extreme in (("L", minimum_filter), ("H", maximum_filter)):
        centres = (values == extreme(values, size=61)) & ~masked.mask
        for row, column in zip(*np.nonzero(centres)):
            features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(longitudes[row, column]), float(latitudes[row, column])]},
                             "properties": {"kind": kind, "label": f"{kind} {values[row, column]:.0f}"}})
    return {"type": "FeatureCollection", "fetched_at": fetched_at, "scale_min_hpa": round(low), "scale_max_hpa": round(high), "features": features}


def field_bounds() -> list[list[float]]:
    return [[WEST, NORTH], [EAST, NORTH], [EAST, SOUTH], [WEST, SOUTH]]


def outlook_rgba(base: np.ndarray, scores: np.ndarray, west: int, south: int, samples: list[dict[str, Any]]) -> np.ndarray:
    """Recolour the MindSpore flood-prone pixels by the real forecast rain over them.

    Rain bands and terrain weights follow the documented flood_watch rule (rain band x terrain class).
    """
    height, width = scores.shape
    coarse = 48
    longitudes = west + (np.arange(coarse) + 0.5) / coarse
    latitudes = south + 1 - (np.arange(coarse) + 0.5) / coarse
    rain, _ = _interpolate(samples, "rainfall_24h_mm", *np.meshgrid(longitudes, latitudes))
    rain = zoom(rain, (height / coarse, width / coarse), order=1)[:height, :width]
    band = (rain >= 25).astype(int) + (rain >= 50) + (rain >= 100)
    terrain = np.where(scores >= 0.75 * 255, 3, np.where(scores >= 0.5 * 255, 2, 1))
    weight = band * terrain
    level = np.where(weight >= 6, 3, np.where(weight >= 3, 2, np.where(weight >= 2, 1, 0)))
    output = base.copy()
    drawn = base[..., 3] > 0
    # No flood expected: the same MindSpore areas in blue, darker where the terrain is more flood-prone.
    teal = np.clip((scores / 255.0 - 0.35) / 0.5, 0, 1)[..., None]
    output[..., :3] = np.where(drawn[..., None], (np.array([150, 200, 240]) * (1 - teal) + np.array([24, 80, 170]) * teal).astype(np.uint8), output[..., :3])
    for value, (colour, alpha) in LEVEL_COLOURS.items():
        mask = drawn & (level == value)
        output[mask, :3] = colour
        output[mask, 3] = np.maximum(base[mask, 3], alpha)
    return output
