import argparse
import json
from pathlib import Path

import mindspore as ms
from mindspore import nn
from mindspore.train.serialization import load_checkpoint, load_param_into_net, save_checkpoint

from ml.datasets.tiled_dataset import create_dataset
from ml.losses.weighted_focal_dice import WeightedFocalDiceLoss
from ml.models.resnet_unet import ResNet50UNet


def evaluate(network: nn.Cell, validation_data) -> dict[str, float]:
    """Compute flooded-class IoU, precision, recall and F1 on held-out tiles."""
    network.set_train(False)
    true_positive = false_positive = false_negative = 0
    for batch in validation_data.create_dict_iterator(output_numpy=True):
        logits = network(ms.Tensor(batch["image"], ms.float32)).asnumpy()
        valid = batch["mask"] >= 0
        predicted = (logits.argmax(axis=1) == 1) & valid
        actual = batch["mask"] == 1
        true_positive += int((predicted & actual).sum())
        false_positive += int((predicted & ~actual).sum())
        false_negative += int((~predicted & actual).sum())
    union = true_positive + false_positive + false_negative
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    return {
        "iou": true_positive / max(union, 1),
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / max(precision + recall, 1e-12),
    }


def train_model(arguments: argparse.Namespace) -> None:
    """Train the segmentation model from aligned, labeled tile manifests."""
    ms.set_device(arguments.device_target)
    ms.set_context(mode=ms.GRAPH_MODE)
    network = ResNet50UNet()
    if arguments.resume:
        unmatched, _ = load_param_into_net(network, load_checkpoint(str(arguments.resume)))
        if unmatched:
            raise ValueError("Resume checkpoint does not match ResNet50UNet.")
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
    training_data = create_dataset(
        arguments.manifest, arguments.batch_size, shuffle=True, crop_size=arguments.crop_size
    )
    validation_data = (
        create_dataset(arguments.val_manifest, arguments.batch_size, shuffle=False)
        if arguments.val_manifest
        else None
    )
    arguments.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    best_iou = -1.0
    history = []

    for epoch in range(1, arguments.epochs + 1):
        network.set_train(True)
        epoch_losses = []
        for batch in training_data.create_dict_iterator(output_numpy=False):
            loss_value = training_step(batch["image"], batch["mask"])
            epoch_losses.append(float(loss_value.asnumpy()))

        if not epoch_losses:
            raise ValueError("Training manifest produced no batches.")
        mean_loss = sum(epoch_losses) / len(epoch_losses)
        entry = {"epoch": epoch, "train_loss": mean_loss}
        if validation_data is not None and (epoch % arguments.val_every == 0 or epoch == arguments.epochs):
            metrics = evaluate(network, validation_data)
            entry["validation"] = metrics
            if metrics["iou"] > best_iou:
                best_iou = metrics["iou"]
                save_checkpoint(network, str(arguments.checkpoint_dir / "sipatai-best.ckpt"))
                entry["best"] = True
            print(f"Epoch {epoch}/{arguments.epochs}: mean loss {mean_loss:.6f}, validation {metrics}")
            history.append(entry)
            write_model_card(arguments, history)
        else:
            print(f"Epoch {epoch}/{arguments.epochs}: mean loss {mean_loss:.6f}")
            history.append(entry)

    if validation_data is None:
        save_checkpoint(network, str(arguments.checkpoint_dir / "sipatai-best.ckpt"))
    write_model_card(arguments, history)


def write_model_card(arguments: argparse.Namespace, history: list[dict]) -> None:
    """Record training provenance next to the checkpoint; rewritten after each validation."""
    card = {
        "model": "ResNet50UNet (MindSpore)",
        "mindspore_version": ms.__version__,
        "label_source": arguments.label_source,
        "training_manifest": str(arguments.manifest),
        "validation_manifest": str(arguments.val_manifest) if arguments.val_manifest else None,
        "hyperparameters": {
            "epochs": arguments.epochs,
            "batch_size": arguments.batch_size,
            "crop_size": arguments.crop_size,
            "learning_rate": arguments.learning_rate,
            "optimizer": arguments.optimizer,
            "class_weights": list(arguments.class_weights),
            "focal_gamma": arguments.focal_gamma,
            "dice_weight": arguments.dice_weight,
        },
        "history": history,
    }
    (arguments.checkpoint_dir / "model_card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")


def parse_arguments() -> argparse.Namespace:
    """Parse required dataset and training parameters."""
    parser = argparse.ArgumentParser(description="Train the SipatAI MindSpore flood segmentation model.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--val-manifest", type=Path, help="Held-out tiles used to select the best checkpoint.")
    parser.add_argument("--crop-size", type=int, help="Train on random square crops of this size (validation uses full tiles).")
    parser.add_argument("--val-every", type=int, default=1, help="Validate every N epochs (and after the last).")
    parser.add_argument("--resume", type=Path, help="Continue from an existing checkpoint.")
    parser.add_argument(
        "--label-source",
        default="human-verified labels",
        help="Describe how the masks were produced; recorded in the model card.",
    )
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
