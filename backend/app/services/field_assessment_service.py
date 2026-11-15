from typing import Any

import numpy as np
import shapely
from pyproj import Transformer
from rasterio.features import rasterize
from shapely import wkb
from shapely.geometry import mapping
from shapely.ops import transform as transform_geometry

from app.integrations.ftw_fields_client import FieldPolygon

PIXEL_AREA_HA = 0.01  # one 10 m pixel
MIN_FIELD_PIXELS = 3
MAX_FEATURES = 4000
SIMPLIFY_DEGREES = 0.00002  # about 2 m
# Prototype display classes by flooded share of a field; not an agronomic damage grade.
SEVERITY_BREAKS = ((0.6, "Severe"), (0.3, "Moderate"), (0.1, "Light"))
SEVERITY_ORDER = ("Severe", "Moderate", "Light", "Unaffected")


def severity_for(flooded_share: float) -> str:
    for minimum, label in SEVERITY_BREAKS:
        if flooded_share >= minimum:
            return label
    return "Unaffected"


def assess_fields(
    fields: list[FieldPolygon],
    flooded: np.ndarray,
    grid_crs: str,
    grid_transform,
    field_year: int,
) -> dict[str, Any]:
    """Measure how much of each real field polygon the MindSpore flood mask covers.

    Fields cut by the tile edge are measured only inside the tile.
    """
    to_grid = Transformer.from_crs("EPSG:4326", grid_crs, always_xy=True).transform
    geometries = [wkb.loads(field.wkb) for field in fields]
    shapes = [
        (transform_geometry(to_grid, geometry), index + 1)
        for index, geometry in enumerate(geometries)
        if not geometry.is_empty
    ]
    labels = rasterize(shapes, out_shape=flooded.shape, transform=grid_transform, fill=0, dtype="int32") if shapes else np.zeros(flooded.shape, dtype="int32")

    count = len(fields) + 1
    pixels = np.bincount(labels.ravel(), minlength=count)
    flooded_pixels = np.bincount(labels[flooded], minlength=count)

    features: list[dict[str, Any]] = []
    totals = {label: 0 for label in SEVERITY_ORDER}
    field_ha = flooded_ha = 0.0
    for index, field in enumerate(fields, start=1):
        if pixels[index] < MIN_FIELD_PIXELS:
            continue
        share = float(flooded_pixels[index] / pixels[index])
        severity = severity_for(share)
        totals[severity] += 1
        field_ha += pixels[index] * PIXEL_AREA_HA
        flooded_ha += flooded_pixels[index] * PIXEL_AREA_HA
        if len(features) < MAX_FEATURES:
            geometry = shapely.set_precision(geometries[index - 1].simplify(SIMPLIFY_DEGREES), 1e-6)
            features.append(
                {
                    "type": "Feature",
                    "geometry": mapping(geometry),
                    "properties": {
                        "field_id": field.field_id,
                        "area_ha": round(float(pixels[index] * PIXEL_AREA_HA), 3),
                        "flooded_ha": round(float(flooded_pixels[index] * PIXEL_AREA_HA), 3),
                        "flooded_share": round(share, 3),
                        "severity": severity,
                        "confidence": round(field.confidence, 1),
                    },
                }
            )

    analysed = sum(totals.values())
    affected = analysed - totals["Unaffected"]
    return {
        "geojson": {"type": "FeatureCollection", "features": features},
        "summary": {
            "fields_analysed": analysed,
            "fields_affected": affected,
            "severity_counts": totals,
            "field_area_ha": round(field_ha, 2),
            "flooded_field_area_ha": round(flooded_ha, 2),
            "field_year": field_year,
            "features_returned": len(features),
            "source": "Fields of The World (CC-BY-4.0): Sentinel-2 field-boundary predictions, not legal parcels",
        },
    }
