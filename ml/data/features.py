import numpy as np
from scipy.ndimage import median_filter

from ml.configs.model_config import INPUT_CHANNEL_COUNT

EPSILON = 1e-6
SAR_VV_WATER_DB = -16.0
SAR_VH_WATER_DB = -22.0
OPTICAL_NDWI_WATER = 0.1


def linear_to_db(backscatter: np.ndarray) -> np.ndarray:
    """Convert linear SAR backscatter to decibels after a 3 by 3 median speckle filter."""
    filtered = median_filter(np.nan_to_num(backscatter, nan=0.0), size=3)
    return 10.0 * np.log10(np.clip(filtered, 1e-4, None))


def normalised_difference(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    """Return (first - second) / (first + second) with a safe denominator."""
    return (first - second) / (first + second + EPSILON)


def build_feature_stack(
    vv: np.ndarray,
    vh: np.ndarray,
    red: np.ndarray,
    nir: np.ndarray,
    green: np.ndarray,
) -> np.ndarray:
    """Create the model input [VV, VH, NDVI, NDWI, RED, NIR] with fixed, documented scaling.

    SAR inputs are linear backscatter; optical inputs are surface reflectance in 0..1.
    """
    vv_db = linear_to_db(vv)
    vh_db = linear_to_db(vh)
    red = np.clip(np.nan_to_num(red, nan=0.0), 0.0, 1.0)
    nir = np.clip(np.nan_to_num(nir, nan=0.0), 0.0, 1.0)
    green = np.clip(np.nan_to_num(green, nan=0.0), 0.0, 1.0)
    stack = np.stack(
        (
            np.clip((vv_db + 30.0) / 30.0, 0.0, 1.0),
            np.clip((vh_db + 35.0) / 30.0, 0.0, 1.0),
            normalised_difference(nir, red),
            normalised_difference(green, nir),
            red,
            nir,
        )
    ).astype(np.float32)
    if stack.shape[0] != INPUT_CHANNEL_COUNT:
        raise ValueError("Feature stack does not match the configured channel count.")
    return stack


def sar_water_mask(vv: np.ndarray, vh: np.ndarray) -> np.ndarray:
    """Open-water mask from calm-water radar darkness in both polarisations."""
    return (linear_to_db(vv) < SAR_VV_WATER_DB) & (linear_to_db(vh) < SAR_VH_WATER_DB)


def weak_flood_labels(
    vv: np.ndarray,
    vh: np.ndarray,
    ndwi: np.ndarray,
    optical_clear: np.ndarray,
    reference_vv: np.ndarray | None = None,
    reference_vh: np.ndarray | None = None,
) -> np.ndarray:
    """Derive weak flood labels from radar and optical water indices.

    Water is radar-dark and, where the optical scene is cloud-free, also water in NDWI.
    When a dry-season radar reference is supplied, pixels that were already water then
    (rivers, ponds, sea) are removed so the label means "newly inundated".
    """
    water = sar_water_mask(vv, vh) & (~optical_clear | (ndwi > OPTICAL_NDWI_WATER))
    if reference_vv is not None and reference_vh is not None:
        water &= ~sar_water_mask(reference_vv, reference_vh)
    return water.astype(np.int32)
