import argparse
from pathlib import Path

import mindspore as ms
from mindspore import nn
from mindspore.train.serialization import save_checkpoint

from ml.datasets.tiled_dataset import create_dataset
from ml.losses.weighted_focal_dice import WeightedFocalDiceLoss
from ml.models.resnet_unet import ResNet50UNet


def train_model(arguments: argparse.Namespace) -> None:
    """Train the segmentation model from aligned, labeled tile manifests."""
    ms.set_device(arguments.device_target)
    ms.set_context(mode=ms.GRAPH_MODE)
    network = ResNet50UNet()
    loss = WeightedFocalDiceLoss(
        class_weights=tuple(arguments.class_weights),
        focal_gamma=arguments.focal_gamma,
        dice_weight=arguments.dice_weight,
    )

    if arguments.optimizer == "adam":
        optimizer = nn.Adam(network.trainable_params(), learning_rate=arguments.learning_rate)
    else:
        if arguments.momentum is None:
            raise ValueError("The momentum optimizer requires --momentum.")
        optimizer = nn.Momentum(
            network.trainable_params(),
            learning_rate=arguments.learning_rate,
            momentum=arguments.momentum,
        )

    training_step = nn.TrainOneStepCell(nn.WithLossCell(network, loss), optimizer)
    training_data = create_dataset(arguments.manifest, arguments.batch_size, shuffle=True)
    arguments.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, arguments.epochs + 1):
        network.set_train(True)
        epoch_losses = []
        for batch in training_data.create_dict_iterator(output_numpy=False):
            loss_value = training_step(batch["image"], batch["mask"])
            epoch_losses.append(float(loss_value.asnumpy()))

        if not epoch_losses:
            raise ValueError("Training manifest produced no batches.")
        checkpoint_path = arguments.checkpoint_dir / f"sipatai-epoch-{epoch}.ckpt"
        save_checkpoint(network, str(checkpoint_path))
        mean_loss = sum(epoch_losses) / len(epoch_losses)
        print(f"Epoch {epoch}/{arguments.epochs}: mean loss {mean_loss:.6f}")


def parse_arguments() -> argparse.Namespace:
    """Parse required dataset and training parameters."""
    parser = argparse.ArgumentParser(description="Train the SipatAI MindSpore flood segmentation model.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--device-target", choices=("Ascend", "GPU", "CPU"), default="CPU")
    parser.add_argument("--epochs", type=int, required=True)
    parser.add_argument("--batch-size", type=int, required=True)
    parser.add_argument("--learning-rate", type=float, required=True)
    parser.add_argument("--optimizer", choices=("adam", "momentum"), required=True)
    parser.add_argument("--momentum", type=float)
    parser.add_argument("--class-weights", type=float, nargs=2, required=True)
    parser.add_argument("--focal-gamma", type=float, required=True)
    parser.add_argument("--dice-weight", type=float, required=True)
    arguments = parser.parse_args()

    if arguments.epochs < 1 or arguments.batch_size < 1 or arguments.learning_rate <= 0:
        parser.error("Epochs and batch size must be positive, and learning rate must be greater than zero.")
    if any(weight <= 0 for weight in arguments.class_weights):
        parser.error("Class weights must be greater than zero.")
    if arguments.focal_gamma < 0 or arguments.dice_weight < 0:
        parser.error("Focal gamma and Dice weight must be non-negative.")
    if arguments.optimizer == "momentum" and arguments.momentum is None:
        parser.error("The momentum optimizer requires --momentum.")
    return arguments


def main() -> None:
    """Run model training from command-line configuration."""
    train_model(parse_arguments())


if __name__ == "__main__":
    main()
