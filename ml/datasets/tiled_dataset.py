import csv
from pathlib import Path

import mindspore.dataset as ds
import numpy as np

from ml.configs.model_config import (
    CLASS_COUNT,
    INPUT_CHANNEL_COUNT,
    INPUT_SIZE,
    OPTICAL_CHANNEL_INDEXES,
    OPTICAL_MISSING_VALUE,
)

POSITIVE_CROP_PROBABILITY = 0.5
# Training simulates cloud: whole-crop optical loss, or cloud-like blocks of lost optical pixels.
FULL_OPTICAL_LOSS_PROBABILITY = 0.35
PATCH_OPTICAL_LOSS_PROBABILITY = 0.25


class TiledFloodDataset:
    """Load aligned image and mask tiles from a CSV manifest on demand."""

    def __init__(self, manifest_path: Path, crop_size: int | None = None, radar_only: bool = False) -> None:
        self.manifest_path = manifest_path.resolve()
        self.crop_size = crop_size
        self.radar_only = radar_only
        self._random = np.random.default_rng()
        with self.manifest_path.open("r", newline="", encoding="utf-8") as manifest_file:
            rows = list(csv.DictReader(manifest_file))

        if not rows or not {"image_path", "mask_path"}.issubset(rows[0]):
            raise ValueError("Manifest must contain image_path and mask_path columns with at least one row.")

        self.samples = [
            (
                self._resolve_path(row["image_path"]),
                self._resolve_path(row["mask_path"]),
            )
            for row in rows
        ]

    def __len__(self) -> int:
        """Return the number of paired image and mask tiles."""
        return len(self.samples)

    def __getitem__(self, index: int) -> tuple[np.ndarray, np.ndarray]:
        """Read and validate one tile pair without loading a full satellite scene."""
        image_path, mask_path = self.samples[index]
        image_mapping = np.load(image_path, mmap_mode="r", allow_pickle=False)
        mask_mapping = None
        try:
            mask_mapping = np.load(mask_path, mmap_mode="r", allow_pickle=False)
            expected_image_shape = (INPUT_CHANNEL_COUNT, *INPUT_SIZE)
            if image_mapping.shape != expected_image_shape:
                raise ValueError(f"{image_path} must have shape {expected_image_shape} in configured channel order.")
            if mask_mapping.shape != INPUT_SIZE:
                raise ValueError(f"{mask_path} must have shape {INPUT_SIZE}.")
            if not np.issubdtype(mask_mapping.dtype, np.integer):
                raise ValueError(f"{mask_path} must contain integer class labels.")
            if not np.isfinite(image_mapping).all():
                raise ValueError(f"{image_path} contains non-finite pixel values.")
            if not np.isin(mask_mapping, np.arange(-1, CLASS_COUNT)).all():
                raise ValueError(f"{mask_path} contains labels outside the configured class range (-1 means no data).")

            image_tile = np.array(image_mapping, dtype=np.float32, copy=True)
            mask_tile = np.array(mask_mapping, dtype=np.int32, copy=True)
            if self.crop_size is not None:
                row, column = self._crop_origin(mask_tile)
                window = (slice(row, row + self.crop_size), slice(column, column + self.crop_size))
                image_tile = image_tile[(slice(None), *window)]
                mask_tile = mask_tile[window]
                image_tile, mask_tile = self._augment(image_tile, mask_tile)
                image_tile = self._simulate_cloud(image_tile)
            if self.radar_only:
                image_tile[list(OPTICAL_CHANNEL_INDEXES)] = OPTICAL_MISSING_VALUE
            return image_tile, mask_tile
        finally:
            for mapping in (image_mapping, mask_mapping):
                mmap_handle = getattr(mapping, "_mmap", None)
                if mmap_handle is not None:
                    mmap_handle.close()

    def _augment(self, image_tile: np.ndarray, mask_tile: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Apply the same random flip and 90-degree rotation to a crop and its mask."""
        if self._random.random() < 0.5:
            image_tile, mask_tile = image_tile[:, :, ::-1], mask_tile[:, ::-1]
        rotations = int(self._random.integers(4))
        image_tile = np.rot90(image_tile, rotations, axes=(1, 2))
        mask_tile = np.rot90(mask_tile, rotations)
        return np.ascontiguousarray(image_tile), np.ascontiguousarray(mask_tile)

    def _simulate_cloud(self, image_tile: np.ndarray) -> np.ndarray:
        """Randomly remove optical information so the model also works from radar alone."""
        draw = self._random.random()
        optical = list(OPTICAL_CHANNEL_INDEXES)
        if draw < FULL_OPTICAL_LOSS_PROBABILITY:
            image_tile[optical] = OPTICAL_MISSING_VALUE
        elif draw < FULL_OPTICAL_LOSS_PROBABILITY + PATCH_OPTICAL_LOSS_PROBABILITY:
            size = image_tile.shape[-1]
            for _ in range(int(self._random.integers(1, 4))):
                height, width = (int(self._random.integers(size // 5, size // 2 + 1)) for _ in range(2))
                top = int(self._random.integers(0, size - height + 1))
                left = int(self._random.integers(0, size - width + 1))
                image_tile[optical, top : top + height, left : left + width] = OPTICAL_MISSING_VALUE
        return image_tile

    def _crop_origin(self, mask_tile: np.ndarray) -> tuple[int, int]:
        """Choose a crop origin, favouring windows that contain flooded pixels.

        Flooded pixels are rare, so most random crops would contain none; centring a
        share of crops on a flooded pixel keeps both classes visible during training.
        """
        limit_row = INPUT_SIZE[0] - self.crop_size
        limit_column = INPUT_SIZE[1] - self.crop_size
        flooded = np.argwhere(mask_tile == 1)
        if len(flooded) and self._random.random() < POSITIVE_CROP_PROBABILITY:
            centre_row, centre_column = flooded[int(self._random.integers(len(flooded)))]
            half = self.crop_size // 2
            return (
                int(np.clip(centre_row - half, 0, limit_row)),
                int(np.clip(centre_column - half, 0, limit_column)),
            )
        return int(self._random.integers(0, limit_row + 1)), int(self._random.integers(0, limit_column + 1))

    def _resolve_path(self, sample_path: str) -> Path:
        """Resolve manifest paths relative to the manifest's location."""
        path = Path(sample_path)
        return path if path.is_absolute() else self.manifest_path.parent / path


def create_dataset(
    manifest_path: Path,
    batch_size: int,
    shuffle: bool,
    crop_size: int | None = None,
    radar_only: bool = False,
) -> ds.Dataset:
    """Create a MindSpore Dataset that reads only the current batch of tiles.

    A crop size draws a random square window from each tile and simulates cloud (training only).
    radar_only hides all optical channels, to measure performance under full cloud cover.
    """
    if batch_size < 1:
        raise ValueError("Batch size must be at least one.")
    if crop_size is not None and not 0 < crop_size <= min(INPUT_SIZE):
        raise ValueError("Crop size must be positive and no larger than the tile.")

    source = TiledFloodDataset(manifest_path, crop_size, radar_only)
    dataset = ds.GeneratorDataset(
        source=source,
        column_names=["image", "mask"],
        shuffle=shuffle,
    )
    return dataset.batch(batch_size, drop_remainder=False)
