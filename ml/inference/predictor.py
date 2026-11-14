import json
import threading
from pathlib import Path

import mindspore as ms
import numpy as np
from mindspore import Tensor
from mindspore.train.serialization import load_checkpoint, load_param_into_net

from ml.configs.model_config import INPUT_CHANNEL_COUNT, INPUT_SIZE
from ml.models.resnet_unet import ResNet50UNet

FLOODED_CLASS_INDEX = 1


class CheckpointError(RuntimeError):
    """Raised when a trained checkpoint is missing or incompatible with the network."""


class FloodPredictor:
    """Run the trained MindSpore ResNet-50 U-Net on one 512 by 512 feature tile."""

    def __init__(self, checkpoint_path: Path, device_target: str = "CPU") -> None:
        if not checkpoint_path.is_file():
            raise CheckpointError(f"Checkpoint not found: {checkpoint_path}")
        ms.set_device(device_target)
        ms.set_context(mode=ms.PYNATIVE_MODE)
        self.network = ResNet50UNet()
        unmatched, _ = load_param_into_net(self.network, load_checkpoint(str(checkpoint_path)))
        if unmatched:
            raise CheckpointError("Checkpoint does not contain all parameters required by ResNet50UNet.")
        self.network.set_train(False)
        self.checkpoint_path = checkpoint_path
        self._lock = threading.Lock()

    def predict_probability(self, features: np.ndarray) -> np.ndarray:
        """Return the per-pixel flooded probability for a [channels, height, width] tile."""
        expected = (INPUT_CHANNEL_COUNT, *INPUT_SIZE)
        if features.shape != expected:
            raise ValueError(f"Expected features shaped {expected}, received {features.shape}.")
        batch = Tensor(features[np.newaxis].astype(np.float32), ms.float32)
        with self._lock:
            logits = self.network(batch).asnumpy()[0]
        shifted = np.exp(logits - logits.max(axis=0, keepdims=True))
        return (shifted / shifted.sum(axis=0, keepdims=True))[FLOODED_CLASS_INDEX]


def read_model_card(checkpoint_path: Path) -> dict:
    """Read the training provenance written next to a checkpoint, if present."""
    card_path = checkpoint_path.with_name("model_card.json")
    if not card_path.is_file():
        return {}
    return json.loads(card_path.read_text(encoding="utf-8"))
