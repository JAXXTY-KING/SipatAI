"""Train the rain-aware MindSpore flood model and test it on flood events it has never seen.

    ml\\.venv\\Scripts\\python.exe -m ml.rain_flood.train
"""
import json
from pathlib import Path

import mindspore as ms
import numpy as np
from mindspore import Tensor, nn

from ml.rain_flood.model import INPUT_NAMES, RainFloodNet, encode_rain
from ml.susceptibility.train import auc, predict

OUTPUT = Path("ml/artifacts/rain_flood")
FOLDS = 4
EPOCHS = 6
MAX_TRAIN = 500_000
MAX_TEST = 300_000


def table(data, indexes):
    rain = encode_rain(data["rain"][indexes, 0], data["rain"][indexes, 1])
    return np.concatenate([data["features"][indexes], rain], axis=1), data["label"][indexes].astype(np.float32)


def fit(x: np.ndarray, y: np.ndarray, columns: list[int], epochs: int = EPOCHS) -> RainFloodNet:
    network = RainFloodNet(inputs=len(columns))
    step = nn.TrainOneStepCell(nn.WithLossCell(network, nn.BCEWithLogitsLoss()), nn.Adam(network.trainable_params(), learning_rate=0.001))
    generator = np.random.default_rng(0)
    for _ in range(epochs):
        network.set_train(True)
        order = generator.permutation(len(x))
        for start in range(0, len(order), 4096):
            pick = order[start : start + 4096]
            step(Tensor(x[pick][:, columns], ms.float32), Tensor(y[pick][:, None], ms.float32))
    network.set_train(False)
    return network


def main() -> None:
    ms.set_device("CPU")
    ms.set_context(mode=ms.PYNATIVE_MODE)
    data = np.load(OUTPUT / "dataset.npz")
    events = sorted(set(data["event"]))
    generator = np.random.default_rng(1)
    print(f"{len(data['label']):,} cells in {len(events)} flood events; flooded share {data['label'].mean():.3f}", flush=True)

    all_columns = list(range(len(INPUT_NAMES)))
    terrain_columns = all_columns[:5]
    results = {"terrain_only": [], "terrain_and_rain": []}
    out_of_fold = {"p": [], "y": [], "event": []}
    for fold in range(FOLDS):
        held = {event for index, event in enumerate(events) if index % FOLDS == fold}
        held_mask = np.isin(data["event"], list(held))
        train_index = generator.permutation(np.nonzero(~held_mask)[0])[:MAX_TRAIN]
        test_index = generator.permutation(np.nonzero(held_mask)[0])[:MAX_TEST]
        x_train, y_train = table(data, train_index)
        x_test, y_test = table(data, test_index)
        for name, columns in (("terrain_only", terrain_columns), ("terrain_and_rain", all_columns)):
            network = fit(x_train, y_train, columns)
            probability = predict(network, x_test[:, columns])
            score = auc(probability, y_test)
            results[name].append(round(score, 4))
            if name == "terrain_and_rain":
                out_of_fold["p"].append(probability)
                out_of_fold["y"].append(y_test)
                out_of_fold["event"].append(data["event"][test_index])
        print(f"fold {fold} held-out events {sorted(held)}: terrain only {results['terrain_only'][-1]}, "
              f"terrain + rain {results['terrain_and_rain'][-1]}", flush=True)

    probability, truth = np.concatenate(out_of_fold["p"]), np.concatenate(out_of_fold["y"])
    levels = {}
    for level, precision in (("advisory", 0.35), ("watch", 0.5), ("warning", 0.7)):
        for threshold in np.arange(0.05, 0.99, 0.01):
            selected = probability >= threshold
            if selected.sum() > 500 and truth[selected].mean() >= precision:
                levels[level] = {"threshold": round(float(threshold), 2), "precision": round(float(truth[selected].mean()), 3),
                                 "recall": round(float(truth[selected].sum() / truth.sum()), 3)}
                break

    final_index = generator.permutation(len(data["label"]))[:MAX_TRAIN * 2]
    x_all, y_all = table(data, final_index)
    network = fit(x_all, y_all, all_columns, epochs=EPOCHS + 2)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    ms.save_checkpoint(network, str(OUTPUT / "rain_flood.ckpt"))

    # Rain response on the training terrain: mean flood probability as only the rain input changes.
    sample, _ = table(data, generator.permutation(len(data["label"]))[:100_000])
    response = {}
    for wettest, total in ((0, 0), (10, 15), (30, 60), (60, 120), (120, 250), (250, 500)):
        probe = sample.copy()
        probe[:, 5:] = encode_rain(np.full(len(probe), wettest, dtype=np.float32), np.full(len(probe), total, dtype=np.float32))
        response[f"{wettest} mm/day, {total} mm/72h"] = round(float(predict(network, probe).mean()), 3)
    print("mean flood probability by rain:", response, flush=True)

    card = {
        "model": "RainFloodNet (MindSpore MLP, 7 -> 64 -> 64 -> 1)",
        "mindspore_version": ms.__version__,
        "inputs": list(INPUT_NAMES),
        "label": "Hand-labelled Sentinel-1/Sentinel-2 flood water (Sen1Floods11) blocked to 90 m cells, permanent water excluded",
        "rain_source": "ERA5 reanalysis via Open-Meteo archive: wettest day and 72 h total up to the Sentinel-1 pass",
        "events": events,
        "cells": int(len(data["label"])),
        "flooded_share": round(float(data["label"].mean()), 4),
        "heldout_event_auc": {name: {"folds": values, "mean": round(float(np.mean(values)), 4)} for name, values in results.items()},
        "levels": levels,
        "rain_response": response,
        "note": "Trained on 11 flood events outside the Philippines; the share of cells flooded in those events is higher than in everyday conditions, so probabilities are relative flood likelihood, not calibrated Philippine frequencies.",
    }
    (OUTPUT / "model_card.json").write_text(json.dumps(card, indent=1), encoding="utf-8")
    print(json.dumps({key: card[key] for key in ("heldout_event_auc", "levels")}, indent=1), flush=True)


if __name__ == "__main__":
    main()
