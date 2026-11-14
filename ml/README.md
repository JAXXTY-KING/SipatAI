# MindSpore Model

The ML package contains a MindSpore 2.10.0 ResNet-50 U-Net for binary flood segmentation and a weighted focal plus Dice loss. The model input contract is `[batch, channels, height, width]`, with channels in the order declared once in `configs/model_config.py`: VV, VH, NDVI, NDWI, red, NIR. The output contains two class logits per pixel in the configured class order.

Input tiles are 512 by 512 pixels. Do not change their size, channel order, classes, or loss parameters without updating the shared training and inference configuration. The loss requires explicit class weights and focal/Dice parameters; this repository does not invent training values that the strategy report did not specify.

## End-to-end pipeline

All commands run from the repository root with the ML environment (`ml\.venv\Scripts\python.exe`). Data comes from the public [Microsoft Planetary Computer](https://planetarycomputer.microsoft.com/) STAC API (Sentinel-1 RTC and Sentinel-2 L2A); no account is required.

1. **Build tiles and weak labels** (`ml/data/build_tiles.py`). Each 512 by 512, 10 m tile gets the six channels from `ml/data/features.py`. Labels are *weak*: radar-dark water (VV < -16 dB and VH < -22 dB), confirmed by NDWI where the optical scene is clear, minus water already present in a dry-season radar reference. They are not human-verified and will contain errors; the model card records this.

```powershell
ml\.venv\Scripts\python.exe -m ml.data.build_tiles --bbox 120.75 14.95 120.95 15.15 --flood-range 2024-07-26/2024-08-05 --flood-date 2024-07-30T00:00:00Z --optical-range 2024-07-26/2024-08-10 --dry-range 2024-02-01/2024-03-15 --max-tiles 20 --output-dir ml\artifacts\tiles\train
ml\.venv\Scripts\python.exe -m ml.data.build_tiles --bbox 120.55 14.85 120.75 15.05 --flood-range 2024-07-26/2024-08-05 --flood-date 2024-07-30T00:00:00Z --optical-range 2024-07-26/2024-08-10 --dry-range 2024-02-01/2024-03-15 --max-tiles 8 --output-dir ml\artifacts\tiles\val
```

2. **Train** with a spatially separate validation area; the best checkpoint by flooded-class IoU and `model_card.json` are written to the checkpoint directory.

```powershell
ml\.venv\Scripts\python.exe -m ml.training.train --manifest ml\artifacts\tiles\train\manifest.csv --val-manifest ml\artifacts\tiles\val\manifest.csv --checkpoint-dir ml\artifacts\checkpoints --epochs 6 --batch-size 2 --learning-rate 0.0005 --optimizer adam --class-weights 1 4 --focal-gamma 2 --dice-weight 1 --label-source "weak labels: Sentinel-1 RTC water thresholds + Sentinel-2 NDWI, minus dry-season water"
```

3. **Serve** with `backend/requirements-ml.txt` installed. The backend loads `ml/artifacts/checkpoints/sipatai-best.ckpt` (override with `SIPATAI_MODEL_CHECKPOINT`) and exposes `GET /api/v1/model/status` and `POST /api/v1/model/analyze`; the map's "MindSpore flood AI" panel calls them.
   At inference the backend also removes permanent water (sea, rivers, ponds) using a dry-season Sentinel-1 reference, mirroring how the training labels were built. Points over open sea return "no radar scene" because Sentinel-1 RTC covers land only.
4. **Deploy to Huawei Cloud** by exporting MindIR with `ml/export/export_model.py` and hosting it on ModelArts (see `docs/huawei_cloud.md`). Ascend execution is not validated here.

Checkpoints and tiles are git-ignored (`ml/artifacts/`) because a checkpoint is about 160 MB.

The model architecture is not trained and does not contain pretrained weights in the repository. Weights are produced by the pipeline below.

Training manifests are CSV files with `image_path` and `mask_path` columns. Each image path points to one NumPy tile shaped `[6, 512, 512]`; each mask path points to one integer-label tile shaped `[512, 512]`. Paths may be relative to the manifest. The dataset reads tiles on demand, not complete satellite scenes. `ml/data/build_tiles.py` produces these tiles.

The local ML environment uses MindSpore 2.10.0 and NumPy 1.26.4. The latter avoids a binary compatibility warning in the Windows CPU runtime. The package was smoke-tested on CPU with a 64 by 64 input; full 512 by 512 training and Huawei Ascend execution still require validation on the selected ModelArts runtime.

Install the official MindSpore package for a supported platform and Python 3.10 through 3.12. The Windows x64 option is listed by MindSpore; production training and inference should use the compatible ModelArts runtime and hardware selected for deployment: https://www.mindspore.cn/install/en.
