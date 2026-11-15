import mindspore as ms
from mindspore import nn

from ml.susceptibility.features import FEATURE_NAMES

RAIN_FEATURES = ("rain_wettest_day", "rain_72h")
INPUT_NAMES = (*FEATURE_NAMES, *RAIN_FEATURES)
RAIN_SCALE = (300.0, 600.0)  # mm; rain inputs are log-scaled to about 0-1


def encode_rain(wettest_day_mm, rain_72h_mm):
    """Log-scale the two rain inputs (numpy arrays in mm) to the range the network was trained on."""
    import numpy as np

    return np.stack(
        (np.log1p(np.clip(wettest_day_mm, 0, RAIN_SCALE[0])) / np.log1p(RAIN_SCALE[0]),
         np.log1p(np.clip(rain_72h_mm, 0, RAIN_SCALE[1])) / np.log1p(RAIN_SCALE[1])),
        axis=-1,
    ).astype("float32")


class RainFloodNet(nn.Cell):
    """Per-cell MLP: terrain context plus the rain of the last 72 hours in, flood logit out."""

    def __init__(self, inputs: int = len(INPUT_NAMES), hidden: int = 64) -> None:
        super().__init__()
        self.layers = nn.SequentialCell(
            [nn.Dense(inputs, hidden), nn.ReLU(), nn.Dense(hidden, hidden), nn.ReLU(), nn.Dense(hidden, 1)]
        )

    def construct(self, value):
        return self.layers(value)


def load_rain_flood_net(checkpoint_path) -> RainFloodNet:
    network = RainFloodNet()
    unmatched, _ = ms.load_param_into_net(network, ms.load_checkpoint(str(checkpoint_path)))
    if unmatched:
        raise ValueError("Checkpoint does not match RainFloodNet.")
    network.set_train(False)
    return network
