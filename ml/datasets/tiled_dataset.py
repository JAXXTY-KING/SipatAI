import csv
from pathlib import Path

import mindspore.dataset as ds
import numpy as np

from ml.configs.model_config import CLASS_COUNT, INPUT_CHANNEL_COUNT, INPUT_SIZE


class TiledFloodDataset:
    """Load aligned image and mask tiles from a CSV manifest on demand."""

    def __init__(self, manifest_path: Path) -> None:
        self.manifest_path = manifest_path.resolve()
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
            if not np.isin(mask_mapping, np.arange(CLASS_COUNT)).all():
                raise ValueError(f"{mask_path} contains labels outside the configured class range.")

            image_tile = np.array(image_mapping, dtype=np.float32, copy=True)
            mask_tile = np.array(mask_mapping, dtype=np.int32, copy=True)
            return image_tile, mask_tile
        finally:
            for mapping in (image_mapping, mask_mapping):
                mmap_handle = getattr(mapping, "_mmap", None)
                if mmap_handle is not None:
                    mmap_handle.close()

    def _resolve_path(self, sample_path: str) -> Path:
        """Resolve manifest paths relative to the manifest's location."""
        path = Path(sample_path)
        return path if path.is_absolute() else self.manifest_path.parent / path


def create_dataset(
    manifest_path: Path,
    batch_size: int,
    shuffle: bool,
) -> ds.Dataset:
    """Create a MindSpore Dataset that reads only the current batch of tiles."""
    if batch_size < 1:
        raise ValueError("Batch size must be at least one.")

    source = TiledFloodDataset(manifest_path)
    dataset = ds.GeneratorDataset(
        source=source,
        column_names=["image", "mask"],
        shuffle=shuffle,
    )
    return dataset.batch(batch_size, drop_remainder=False)
