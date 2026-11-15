import mindspore as ms
from mindspore import nn

from ml.susceptibility.features import FEATURE_NAMES


class SusceptibilityNet(nn.Cell):
    """Per-pixel MLP: terrain context in, relative flood susceptibility (logit) out."""

    def __init__(self, hidden: int = 64) -> None:
        super().__init__()
        self.layers = nn.SequentialCell(
            [
                nn.Dense(len(FEATURE_NAMES), hidden),
                nn.ReLU(),
                nn.Dense(hidden, hidden),
                nn.ReLU(),
                nn.Dense(hidden, 1),
            ]
        )

    def construct(self, value):
        return self.layers(value)


def load_susceptibility_net(checkpoint_path) -> SusceptibilityNet:
    network = SusceptibilityNet()
    unmatched, _ = ms.load_param_into_net(network, ms.load_checkpoint(str(checkpoint_path)))
    if unmatched:
        raise ValueError("Checkpoint does not match SusceptibilityNet.")
    network.set_train(False)
    return network
