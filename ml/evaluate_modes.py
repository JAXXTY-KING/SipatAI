"""Choose the flood threshold on validation data only, then report test and Bolivia in both input modes."""
import csv
import json
import sys
from pathlib import Path

import mindspore as ms
import numpy as np

from ml.configs.model_config import OPTICAL_CHANNEL_INDEXES, OPTICAL_MISSING_VALUE
from ml.inference.predictor import load_network

checkpoint = Path(sys.argv[1])
output = Path(sys.argv[2])
thresholds = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
ms.set_device("CPU")
ms.set_context(mode=ms.PYNATIVE_MODE)
network = load_network(checkpoint)


def probability(tile):
    logits = network(ms.Tensor(tile[None], ms.float32)).asnumpy()[0]
    exponent = np.exp(logits - logits.max(0, keepdims=True))
    return (exponent / exponent.sum(0, keepdims=True))[1]


def evaluate(split):
    results = {mode: {t: [0, 0, 0] for t in thresholds} for mode in ("full", "radar_only")}
    root = Path(f"ml/artifacts/sen1floods11/{split}")
    for row in csv.DictReader(open(root / "manifest.csv")):
        image = np.load(root / row["image_path"]).astype(np.float32)
        mask = np.load(root / row["mask_path"])
        valid, flooded = mask >= 0, mask == 1
        radar_image = image.copy()
        radar_image[list(OPTICAL_CHANNEL_INDEXES)] = OPTICAL_MISSING_VALUE
        for mode, tile in (("full", image), ("radar_only", radar_image)):
            probabilities = probability(tile)
            for t in thresholds:
                predicted = (probabilities >= t) & valid
                counts = results[mode][t]
                counts[0] += int((predicted & flooded).sum())
                counts[1] += int((predicted & ~flooded).sum())
                counts[2] += int((~predicted & flooded).sum())
    return {
        mode: {
            str(t): {
                "iou": round(c[0] / max(sum(c), 1), 4),
                "precision": round(c[0] / max(c[0] + c[1], 1), 4),
                "recall": round(c[0] / max(c[0] + c[2], 1), 4),
            }
            for t, c in by_threshold.items()
        }
        for mode, by_threshold in results.items()
    }


report = {}
for split in ("valid", "test", "bolivia"):
    report[split] = evaluate(split)
    print(split, {m: {t: v["iou"] for t, v in d.items()} for m, d in report[split].items()}, flush=True)
valid = report["valid"]
best = max(thresholds, key=lambda t: valid["full"][str(t)]["iou"] + valid["radar_only"][str(t)]["iou"])
report["chosen_threshold"] = best
report["note"] = "Threshold maximises the mean of full and radar-only IoU on the validation split only."
output.write_text(json.dumps(report, indent=1))
print("chosen threshold", best, flush=True)
