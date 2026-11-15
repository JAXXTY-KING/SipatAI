# MindSpore Model

The ML package contains a MindSpore 2.10.0 ResNet-50 U-Net for binary flood segmentation and a weighted focal plus Dice loss. The model input contract is `[batch, channels, height, width]`, with channels in the order declared once in `configs/model_config.py`: VV, VH, NDVI, NDWI, red, NIR. The output contains two class logits per pixel in the configured class order.

Input tiles are 512 by 512 pixels. Do not change their size, channel order, classes, or loss parameters without updating the shared training and inference configuration. The loss requires explicit class weights and focal/Dice parameters; this repository does not invent training values that the strategy report did not specify.

## End-to-end pipeline

All commands run from the repository root with the ML environment (`ml\.venv\Scripts\python.exe`).

### Current model: trained on human-labelled floods

The served model is trained on [Sen1Floods11](https://github.com/cloudtostreet/Sen1Floods11) hand-labelled flood chips (446 chips from 11 real flood events, public, no account). Its Sentinel-1 radar and Sentinel-2 optical bands are converted to the same six channels used at inference, and the official train / validation / test / Bolivia splits are kept separate. Labels mark water in the flood image, so the backend subtracts permanent water at inference to report flooding.

| Split | IoU (threshold 0.5) | IoU (threshold 0.6) |
|---|---|---|
| Validation (used to pick the threshold) | 0.72 | 0.73 |
| Test (unseen chips) | 0.75 | 0.77 |
| Bolivia (unseen flood event) | 0.76 | 0.79 |

The decision threshold (0.6) was chosen on the validation split alone and is stored in `model_card.json`; the backend reads it. Test-time flip averaging was tried and added only about 0.003 IoU for three times the compute, so it is not used.

The earlier model, trained only on 16 automatically labelled tiles, scored IoU 0.32 on its own validation tiles.

```powershell
ml\.venv\Scripts\python.exe -m ml.data.sen1floods11 --output-dir ml\artifacts\sen1floods11
ml\.venv\Scripts\python.exe -m ml.training.train --manifest ml\artifacts\sen1floods11\train\manifest.csv --val-manifest ml\artifacts\sen1floods11\valid\manifest.csv --checkpoint-dir ml\artifacts\checkpoints --crop-size 128 --epochs 20 --val-every 5 --batch-size 8 --learning-rate 0.0005 --optimizer adam --class-weights 1 2 --focal-gamma 2 --dice-weight 1 --label-source "Sen1Floods11 human-labelled flood chips"
ml\.venv\Scripts\python.exe -m ml.training.evaluate --checkpoint ml\artifacts\checkpoints\sipatai-best.ckpt --manifest ml\artifacts\sen1floods11\valid\manifest.csv ml\artifacts\sen1floods11\test\manifest.csv ml\artifacts\sen1floods11\bolivia\manifest.csv --record-test
```

Training uses random 128-pixel crops with flips and 90-degree rotations, ignores no-data pixels (label -1), and keeps the checkpoint with the best validation IoU. The training run used about 6 GB of RAM; the final run stopped after epoch 19 when Windows ran out of memory, and the epoch-15 checkpoint was kept. Domain note: Sen1Floods11 uses Sentinel-2 top-of-atmosphere reflectance and sigma-naught radar, while live inference uses Sentinel-2 L2A and RTC radar from Planetary Computer, so small shifts are expected.

### Optional: weak-label tiles from any area

For areas without human labels, `ml/data/build_tiles.py` can create tiles from the public [Microsoft Planetary Computer](https://planetarycomputer.microsoft.com/) STAC API (Sentinel-1 RTC and Sentinel-2 L2A). Labels are *weak*: radar-dark water (VV < -16 dB and VH < -22 dB), confirmed by NDWI where the optical scene is clear, minus water already present in a dry-season radar reference. They are not human-verified and will contain errors.

```powershell
ml\.venv\Scripts\python.exe -m ml.data.build_tiles --bbox 120.75 14.95 120.95 15.15 --flood-range 2024-07-26/2024-08-05 --flood-date 2024-07-30T00:00:00Z --optical-range 2024-07-26/2024-08-10 --dry-range 2024-02-01/2024-03-15 --max-tiles 20 --output-dir ml\artifacts\tiles\train
```

Pass the resulting manifests to `ml.training.train` as above, with a `--label-source` describing them.

### Serving and deployment

3. **Serve** with `backend/requirements-ml.txt` installed. The backend loads `ml/artifacts/checkpoints/sipatai-best.ckpt` (override with `SIPATAI_MODEL_CHECKPOINT`) and exposes `GET /api/v1/model/status` and `POST /api/v1/model/analyze`; the map's "MindSpore flood AI" panel calls them.
   At inference the backend also removes permanent water (sea, rivers, ponds) using a dry-season Sentinel-1 reference, and reports flooded cropland using ESA WorldCover 2021 (class 40, 10 m, public on Planetary Computer).
   **Fields:** no parcel dataset is connected, so per-field results use the open [Fields of The World](https://fieldsofthe.world/) global field-boundary dataset (CC-BY-4.0, 2024 and 2025 predictions, anonymous read from Source Cooperative). The backend range-reads only the polygons inside the tile from the 2 GB Philippines GeoParquet with DuckDB, keeps those with confidence 50 or higher, and measures how much of each field the flood mask covers. Fields are Sentinel-2-detected field units, not legal parcels or farm ownership. Their Light / Moderate / Severe classes (flooded share 10-30%, 30-60%, 60%+) are a prototype display scale, not an agronomic damage grade or loss estimate. Every analysis is saved (numbers only) so the dashboard and PDF reports work without GaussDB. If real parcels (for example RSBSA or DA data) become available, they can replace the field polygons.
   Points over open sea return "no radar scene" because Sentinel-1 RTC covers land only. Irrigated paddies and fishponds can look like water, so results are not an official flood boundary.
4. **Deploy to Huawei Cloud** by exporting MindIR with `ml/export/export_model.py` and hosting it on ModelArts (see `docs/huawei_cloud.md`). Ascend execution is not validated here.

Checkpoints and tiles are git-ignored (`ml/artifacts/`) because a checkpoint is about 160 MB.

The model architecture is not trained and does not contain pretrained weights in the repository. Weights are produced by the pipeline above.

Training manifests are CSV files with `image_path` and `mask_path` columns. Each image path points to one NumPy tile shaped `[6, 512, 512]`; each mask path points to one integer-label tile shaped `[512, 512]`. Paths may be relative to the manifest. The dataset reads tiles on demand, not complete satellite scenes. `ml/data/build_tiles.py` produces these tiles.

The local ML environment uses MindSpore 2.10.0 and NumPy 1.26.4. The latter avoids a binary compatibility warning in the Windows CPU runtime. The package was smoke-tested on CPU with a 64 by 64 input; full 512 by 512 training and Huawei Ascend execution still require validation on the selected ModelArts runtime.

Install the official MindSpore package for a supported platform and Python 3.10 through 3.12. The Windows x64 option is listed by MindSpore; production training and inference should use the compatible ModelArts runtime and hardware selected for deployment: https://www.mindspore.cn/install/en.
