"""Train the MindSpore flood-susceptibility model with whole provinces held out for testing.

    ml\\.venv\\Scripts\\python.exe -m ml.susceptibility.train
"""
import argparse
import json
import zlib
from pathlib import Path

import mindspore as ms
import numpy as np
from mindspore import Tensor, nn

from ml.susceptibility.features import FEATURE_NAMES, TEMPORARY_WATER_RANGE
from ml.susceptibility.model import SusceptibilityNet

HOLDOUT_MODULUS = 5  # about 1 in 5 provinces never seen during training


def is_holdout(province: str) -> bool:
    return zlib.crc32(province.encode()) % HOLDOUT_MODULUS == 0


def load_tiles(directory: Path):
    train, test = ([], [], []), ([], [], [])
    for path in sorted(directory.glob("*.npz")):
        data = np.load(path)
        bucket = test if is_holdout(str(data["province"])) else train
        bucket[0].append(data["x"])
        bucket[1].append(data["y"])
        bucket[2].append(str(data["province"]))
    pack = lambda bucket: (np.concatenate(bucket[0]), np.concatenate(bucket[1]).astype(np.float32), sorted(set(bucket[2])))  # noqa: E731
    return pack(train), pack(test)


def auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Rank-based area under the ROC curve (probability a flood-prone pixel outranks a dry one)."""
    order = scores.argsort()
    ranks = np.empty(len(scores))
    ranks[order] = np.arange(1, len(scores) + 1)
    positives = labels == 1
    n_pos, n_neg = positives.sum(), (~positives).sum()
    return float((ranks[positives].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def predict(network, features: np.ndarray, batch: int = 65536) -> np.ndarray:
    outputs = [network(Tensor(features[i : i + batch], ms.float32)).asnumpy()[:, 0] for i in range(0, len(features), batch)]
    return 1.0 / (1.0 + np.exp(-np.concatenate(outputs)))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tiles", type=Path, default=Path("ml/artifacts/susceptibility/tiles"))
    parser.add_argument("--output-dir", type=Path, default=Path("ml/artifacts/susceptibility"))
    parser.add_argument("--epochs", type=int, default=25)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--learning-rate", type=float, default=0.001)
    arguments = parser.parse_args()

    ms.set_device("CPU")
    ms.set_context(mode=ms.PYNATIVE_MODE)
    (x_train, y_train, train_provinces), (x_test, y_test, test_provinces) = load_tiles(arguments.tiles)
    print(f"train {len(x_train):,} pixels / {len(train_provinces)} provinces; "
          f"held-out {len(x_test):,} pixels / {len(test_provinces)} provinces", flush=True)

    network = SusceptibilityNet()
    training_step = nn.TrainOneStepCell(
        nn.WithLossCell(network, nn.BCEWithLogitsLoss()), nn.Adam(network.trainable_params(), learning_rate=arguments.learning_rate)
    )
    generator = np.random.default_rng(0)
    history = []
    for epoch in range(1, arguments.epochs + 1):
        network.set_train(True)
        order = generator.permutation(len(x_train))
        losses = []
        for start in range(0, len(order), arguments.batch_size):
            pick = order[start : start + arguments.batch_size]
            loss = training_step(Tensor(x_train[pick], ms.float32), Tensor(y_train[pick][:, None], ms.float32))
            losses.append(float(loss.asnumpy()))
        network.set_train(False)
        entry = {
            "epoch": epoch,
            "train_loss": round(float(np.mean(losses)), 4),
            "train_auc": round(auc(predict(network, x_train[:200_000]), y_train[:200_000]), 4),
            "heldout_province_auc": round(auc(predict(network, x_test), y_test), 4),
        }
        history.append(entry)
        print(entry, flush=True)

    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    ms.save_checkpoint(network, str(arguments.output_dir / "susceptibility.ckpt"))
    card = {
        "model": "SusceptibilityNet (MindSpore MLP, 5 -> 64 -> 64 -> 1)",
        "mindspore_version": ms.__version__,
        "features": list(FEATURE_NAMES),
        "label": f"JRC Global Surface Water occurrence {TEMPORARY_WATER_RANGE[0]}-{TEMPORARY_WATER_RANGE[1]}% (land underwater only part of the time, 1984-2020) vs never water",
        "inputs": "Copernicus DEM GLO-30 elevation; JRC GSW occurrence (distance to permanent water only)",
        "train_provinces": train_provinces,
        "heldout_provinces": test_provinces,
        "final": history[-1],
        "history": history,
    }
    (arguments.output_dir / "model_card.json").write_text(json.dumps(card, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
