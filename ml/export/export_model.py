import argparse
from pathlib import Path

import numpy as np
import mindspore as ms
from mindspore import Tensor
from mindspore.train.serialization import export, load_checkpoint, load_param_into_net

from ml.configs.model_config import INPUT_CHANNEL_COUNT, INPUT_SIZE
from ml.models.resnet_unet import ResNet50UNet


def export_mindir(checkpoint_path: Path, output_path: Path, device_target: str) -> Path:
    """Export trained segmentation weights to MindIR for ModelArts deployment."""
    ms.set_device(device_target)
    ms.set_context(mode=ms.GRAPH_MODE)
    network = ResNet50UNet()
    checkpoint_parameters = load_checkpoint(str(checkpoint_path))
    unmatched_parameters, _ = load_param_into_net(network, checkpoint_parameters)
    if unmatched_parameters:
        raise ValueError("Checkpoint does not contain all parameters required by ResNet50UNet.")

    network.set_train(False)
    example_input = Tensor(
        np.zeros((1, INPUT_CHANNEL_COUNT, *INPUT_SIZE), dtype=np.float32),
        ms.float32,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mindir_path = output_path.with_suffix("")
    export(network, example_input, file_name=str(mindir_path), file_format="MINDIR")
    return mindir_path.with_suffix(".mindir")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a trained SipatAI model to MindIR.")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device-target", choices=("Ascend", "GPU", "CPU"), default="Ascend")
    arguments = parser.parse_args()

    exported_path = export_mindir(arguments.checkpoint, arguments.output, arguments.device_target)
    print(f"MindIR exported to {exported_path}")


if __name__ == "__main__":
    main()
