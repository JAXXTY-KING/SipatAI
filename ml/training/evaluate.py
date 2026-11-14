import argparse
import json
from pathlib import Path

import mindspore as ms

from ml.datasets.tiled_dataset import create_dataset
from ml.inference.predictor import CheckpointError, load_network
from ml.training.train import evaluate


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a SipatAI checkpoint on labelled tile manifests.")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, help="Write the metrics as JSON.")
    parser.add_argument("--record-test", action="store_true", help="Store the metrics under 'test' in the model card.")
    arguments = parser.parse_args()

    ms.set_device("CPU")
    ms.set_context(mode=ms.PYNATIVE_MODE)
    try:
        network = load_network(arguments.checkpoint)
    except CheckpointError as error:
        parser.error(str(error))

    results = {}
    for manifest in arguments.manifest:
        results[str(manifest)] = evaluate(network, create_dataset(manifest, batch_size=1, shuffle=False))
        print(manifest, results[str(manifest)], flush=True)
    if arguments.output:
        arguments.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    card_path = arguments.checkpoint.with_name("model_card.json")
    if arguments.record_test and card_path.is_file():
        card = json.loads(card_path.read_text(encoding="utf-8"))
        card["test"] = {Path(path).parent.name: metrics for path, metrics in results.items()}
        card_path.write_text(json.dumps(card, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
