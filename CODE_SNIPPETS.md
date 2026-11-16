# SipatAI: Key Technical Modules and Code Snippets

This document explains how SipatAI works by showing the real code behind each module. Every snippet is copied from this repository and the file it comes from is shown above it, so a reader can open the full file. Lines that are not needed for the explanation are replaced by a `...` comment.

It is a companion to the main [README](README.md), which describes the project, the data, the Huawei ICT Competition status and the limitations. The numbers quoted here (IoU, AUC, recall) come from our own training runs on public datasets from other countries. They are **not** validated against Philippine flood records. See [Limitations in the README](README.md#14-limitations).

## Contents

1. [Module overview](#module-overview)
2. [Module 1: Satellite flood segmentation (ResNet-50 U-Net)](#module-1-satellite-flood-segmentation-resnet-50-u-net)
3. [Module 2: Flood-prone terrain model (MLP)](#module-2-flood-prone-terrain-model-mlp)
4. [Module 3: Rain-aware flood outlook (experimental MLP)](#module-3-rain-aware-flood-outlook-experimental-mlp)
5. [Module 4: Real weather and satellite context data](#module-4-real-weather-and-satellite-context-data)
6. [Module 5: Land mask, nationwide scan and field assessment](#module-5-land-mask-nationwide-scan-and-field-assessment)
7. [Module 6: Backend API (FastAPI)](#module-6-backend-api-fastapi)
8. [Module 7: Frontend map (Vue 3 and Mapbox GL JS)](#module-7-frontend-map-vue-3-and-mapbox-gl-js)
9. [Module 8: Huawei Cloud adapters](#module-8-huawei-cloud-adapters)
10. [Where to find each file](#where-to-find-each-file)

---

## Module overview

| Module | What it does | Main code |
|---|---|---|
| **1. Satellite flood segmentation** | Reads Sentinel-1 radar and Sentinel-2 optical imagery and outlines water that is not normally there. | `ml/models/resnet_unet.py`, `ml/losses/weighted_focal_dice.py`, `ml/training/train.py` |
| **2. Flood-prone terrain model** | Scores every 90 m cell of the Philippines by how easily water collects there. | `ml/susceptibility/` |
| **3. Rain-aware flood outlook** | Adds recent and forecast rain to the terrain features. Experimental. | `ml/rain_flood/`, `backend/app/services/rain_flood_service.py` |
| **4. Real weather and satellite context** | Open-Meteo forecasts, JMA Himawari clouds, NASA IMERG rain and pressure contours. | `backend/app/integrations/`, `backend/app/services/weather_fields.py` |
| **5. Land mask, scan and fields** | Keeps detections on land, scans the country in tiles, and measures flooded farm fields. | `backend/app/services/` |
| **6. Backend API** | FastAPI routes that serve all of the above to the browser. | `backend/app/main.py`, `backend/app/api/routes/` |
| **7. Frontend map** | The interactive map, layers, colour key and click report. | `frontend/src/components/ParcelMap.vue` |
| **8. Huawei Cloud adapters** | ModelArts, OBS and GaussDB/PostGIS code, written but not run against live services. | `backend/app/integrations/`, `backend/migrations/`, `ml/export/` |

---

## Module 1: Satellite flood segmentation (ResNet-50 U-Net)

**Summary.** A MindSpore ResNet-50 encoder with a U-Net decoder labels every pixel as flooded or not flooded. The input has 6 channels at 10 m (Sentinel-1 VV and VH radar, then NDVI, NDWI, red and NIR from Sentinel-2). It is trained on Sen1Floods11, which has 446 hand-labelled chips from 11 flood events, with a weighted focal loss plus a Dice loss. Optical channels are randomly removed during training so the model still works under cloud. After prediction, permanent water is removed and the output is masked to Philippine land.

On unseen test chips it scored IoU 0.76 with optical imagery and 0.61 with radar only. These chips are from other countries.

### 1.1 The model contract

One file defines the channel order, the "missing optical" marker and the tile size. Training, inference and export all import it, so they cannot disagree.

**File:** `ml/configs/model_config.py`

```python
INPUT_CHANNEL_ORDER = ("VV", "VH", "NDVI", "NDWI", "RED", "NIR")
INPUT_CHANNEL_COUNT = len(INPUT_CHANNEL_ORDER)
# Optical channels are unusable under cloud; those pixels are set to a value outside the real range
# (NDVI/NDWI in [-1, 1], reflectance in [0, 1]) so the network can learn to rely on radar alone.
OPTICAL_CHANNEL_INDEXES = (2, 3, 4, 5)
OPTICAL_MISSING_VALUE = -2.0
INPUT_SIZE = (512, 512)
CLASS_NAMES = ("not_flooded", "flooded")
CLASS_COUNT = len(CLASS_NAMES)
```

### 1.2 Building the six input channels

Radar is converted from linear backscatter to decibels after a 3 by 3 median filter that reduces speckle. NDVI and NDWI are normalised differences. Every channel is scaled to a fixed, documented range.

**File:** `ml/data/features.py`

```python
def linear_to_db(backscatter: np.ndarray) -> np.ndarray:
    """Convert linear SAR backscatter to decibels after a 3 by 3 median speckle filter."""
    filtered = median_filter(np.nan_to_num(backscatter, nan=0.0), size=3)
    return 10.0 * np.log10(np.clip(filtered, 1e-4, None))


def normalised_difference(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    """Return (first - second) / (first + second) with a safe denominator."""
    return (first - second) / (first + second + EPSILON)
```

```python
    stack = np.stack(
        (
            np.clip((vv_db + 30.0) / 30.0, 0.0, 1.0),
            np.clip((vh_db + 35.0) / 30.0, 0.0, 1.0),
            normalised_difference(nir, red),
            normalised_difference(green, nir),
            red,
            nir,
        )
    ).astype(np.float32)
```

Open water is dark in radar, so a simple radar rule is also used to find permanent water (rivers, ponds, the sea):

**File:** `ml/data/features.py`

```python
def sar_water_mask(vv: np.ndarray, vh: np.ndarray) -> np.ndarray:
    """Open-water mask from calm-water radar darkness in both polarisations."""
    return (linear_to_db(vv) < SAR_VV_WATER_DB) & (linear_to_db(vh) < SAR_VH_WATER_DB)
```

### 1.3 The network

The encoder is a ResNet-50 built from bottleneck blocks (1×1, 3×3, 1×1 convolutions with a shortcut). The decoder upsamples with transposed convolutions and concatenates the matching encoder features ("skip connections"), which keeps thin flood edges sharp.

**File:** `ml/models/resnet_unet.py`

```python
class ResNetBottleneck(nn.Cell):
    expansion = 4

    def __init__(self, input_channels: int, channels: int, stride: int = 1) -> None:
        super().__init__()
        output_channels = channels * self.expansion
        self.conv1 = nn.Conv2d(input_channels, channels, kernel_size=1, has_bias=False)
        self.bn1 = nn.BatchNorm2d(channels)
        # ...
        self.conv3 = nn.Conv2d(channels, output_channels, kernel_size=1, has_bias=False)
        self.bn3 = nn.BatchNorm2d(output_channels)
        self.relu = nn.ReLU()
        self.shortcut = None
        # ...

    def construct(self, value):
        residual = value if self.shortcut is None else self.shortcut(value)
        output = self.relu(self.bn1(self.conv1(value)))
        output = self.relu(self.bn2(self.conv2(output)))
        output = self.bn3(self.conv3(output))
        return self.relu(output + residual)
```

```python
class ResNet50UNet(nn.Cell):
    """ResNet-50 encoder and U-Net decoder for two-class flood segmentation."""

    def __init__(self) -> None:
        super().__init__()
        self.input_channels = INPUT_CHANNEL_COUNT
        self.encoder_channels = 64
        # ...
        self.layer1 = self._make_layer(64, block_count=3, stride=1)
        self.layer2 = self._make_layer(128, block_count=4, stride=2)
        self.layer3 = self._make_layer(256, block_count=6, stride=2)
        self.layer4 = self._make_layer(512, block_count=3, stride=2)

        self.up4 = nn.Conv2dTranspose(2048, 512, kernel_size=2, stride=2, has_bias=False)
        self.decode4 = ConvNormRelu(512 + 1024, 512)
        # ...
        self.classifier = nn.Conv2d(64, CLASS_COUNT, kernel_size=1, has_bias=True)
```

```python
    def construct(self, value):
        stem = self.relu(self.bn1(self.conv1(value)))
        encoded = self.max_pool(stem)
        skip1 = self.layer1(encoded)
        skip2 = self.layer2(skip1)
        skip3 = self.layer3(skip2)
        encoded = self.layer4(skip3)

        decoded = self.decode4(ops.concat((self.up4(encoded), skip3), axis=1))
        decoded = self.decode3(ops.concat((self.up3(decoded), skip2), axis=1))
        decoded = self.decode2(ops.concat((self.up2(decoded), skip1), axis=1))
        decoded = self.decode1(ops.concat((self.up1(decoded), stem), axis=1))
        return self.classifier(self.up0(decoded))
```

### 1.4 The loss: weighted focal plus Dice

Flooded pixels are rare, so a plain loss would learn to say "not flooded" everywhere. The focal term focuses on hard pixels and weights the flooded class. The Dice term rewards overlap with the real flood shape. Pixels labelled `-1` ("no data") are ignored by both terms.

**File:** `ml/losses/weighted_focal_dice.py`

```python
    def construct(self, logits, target):
        labels = ops.cast(target, ms.int32)
        # Pixels labelled -1 are "no data": they contribute to neither loss term.
        valid = ops.cast(labels >= 0, ms.float32)
        valid_channel = ops.expand_dims(valid, 1)
        safe_labels = labels * ops.cast(valid, ms.int32)
        # ...
        probabilities = self.softmax(logits)
        clipped_probabilities = ops.clip_by_value(probabilities, 1e-7, 1.0)

        valid_pixels = ops.maximum(ops.sum(valid), 1.0)
        focal_loss = -ops.sum(
            one_hot_target
            * self.class_weights
            * ops.pow(1.0 - probabilities, self.focal_gamma)
            * ops.log(clipped_probabilities)
        ) / (valid_pixels * CLASS_COUNT)

        masked_probabilities = probabilities * valid_channel
        axes = (0, 2, 3)
        intersection = ops.sum(masked_probabilities * one_hot_target, dim=axes)
        cardinality = ops.sum(masked_probabilities + one_hot_target, dim=axes)
        dice_score = (2.0 * intersection + self.smooth) / (cardinality + self.smooth)
        dice_loss = 1.0 - ops.mean(dice_score)
        return focal_loss + self.dice_weight * dice_loss
```

### 1.5 Teaching the model to work under cloud

Typhoon-season optical images are often cloudy. During training, the dataset hides the optical channels for a whole crop (35% of the time) or in cloud-like blocks (25% of the time). It also flips and rotates crops, and it centres half of the crops on a flooded pixel so both classes are seen.

**File:** `ml/datasets/tiled_dataset.py`

```python
POSITIVE_CROP_PROBABILITY = 0.5
# Training simulates cloud: whole-crop optical loss, or cloud-like blocks of lost optical pixels.
FULL_OPTICAL_LOSS_PROBABILITY = 0.35
PATCH_OPTICAL_LOSS_PROBABILITY = 0.25
```

```python
    def _simulate_cloud(self, image_tile: np.ndarray) -> np.ndarray:
        """Randomly remove optical information so the model also works from radar alone."""
        draw = self._random.random()
        optical = list(OPTICAL_CHANNEL_INDEXES)
        if draw < FULL_OPTICAL_LOSS_PROBABILITY:
            image_tile[optical] = OPTICAL_MISSING_VALUE
        elif draw < FULL_OPTICAL_LOSS_PROBABILITY + PATCH_OPTICAL_LOSS_PROBABILITY:
            size = image_tile.shape[-1]
            for _ in range(int(self._random.integers(1, 4))):
                height, width = (int(self._random.integers(size // 5, size // 2 + 1)) for _ in range(2))
                top = int(self._random.integers(0, size - height + 1))
                left = int(self._random.integers(0, size - width + 1))
                image_tile[optical, top : top + height, left : left + width] = OPTICAL_MISSING_VALUE
        return image_tile
```

### 1.6 Training and evaluation

Training uses MindSpore's `TrainOneStepCell` with the Adam optimiser. After validation, the checkpoint with the best average of the full (radar plus optical) and radar-only IoU is kept, so a model that only works in clear weather is not selected.

**File:** `ml/training/train.py`

```python
def train_model(arguments: argparse.Namespace) -> None:
    """Train the segmentation model from aligned, labeled tile manifests."""
    ms.set_device(arguments.device_target)
    ms.set_context(mode=ms.GRAPH_MODE)
    network = ResNet50UNet()
    # ...
    loss = WeightedFocalDiceLoss(
        class_weights=tuple(arguments.class_weights),
        focal_gamma=arguments.focal_gamma,
        dice_weight=arguments.dice_weight,
    )

    if arguments.optimizer == "adam":
        optimizer = nn.Adam(network.trainable_params(), learning_rate=arguments.learning_rate)
    # ...
    training_step = nn.TrainOneStepCell(nn.WithLossCell(network, loss), optimizer)
```

```python
            metrics = evaluate(network, validation_data)
            radar_metrics = evaluate(network, validation_radar)
            entry["validation"] = metrics
            entry["validation_radar_only"] = radar_metrics
            score = (metrics["iou"] + radar_metrics["iou"]) / 2
            if score > best_score:
                best_score = score
                save_checkpoint(network, str(arguments.checkpoint_dir / "sipatai-best.ckpt"))
                entry["best"] = True
```

The scores are computed from pixel counts:

**File:** `ml/training/train.py`

```python
        predicted = (logits.argmax(axis=1) == 1) & valid
        actual = batch["mask"] == 1
        true_positive += int((predicted & actual).sum())
        false_positive += int((predicted & ~actual).sum())
        false_negative += int((~predicted & actual).sum())
    union = true_positive + false_positive + false_negative
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
```

Command used to train (run from the repository root):

```powershell
ml\.venv\Scripts\python.exe -m ml.training.train --manifest ml\artifacts\sen1floods11\train\manifest.csv --val-manifest ml\artifacts\sen1floods11\valid\manifest.csv --checkpoint-dir ml\artifacts\checkpoints --crop-size 128 --epochs 24 --val-every 4 --batch-size 8 --learning-rate 0.0004 --optimizer adam --class-weights 1 2 --focal-gamma 2 --dice-weight 1 --label-source "Sen1Floods11 human-labelled flood chips"
```

### 1.7 Reading real satellite scenes and hiding clouds

At inference time the backend reads Sentinel-1 and Sentinel-2 for a 5 km tile from Microsoft Planetary Computer. Cloudy and shadowed optical pixels, plus a 3 pixel margin around them, are set to the "missing" value so the model falls back on radar there. With no usable optical scene, the model runs on radar alone, which works under any cloud.

**File:** `ml/data/planetary_computer.py`

```python
def mask_unusable_optical(features: np.ndarray, optical_clear: np.ndarray) -> np.ndarray:
    """Mark optical channels as missing under cloud, cloud shadow and a 3 pixel margin around them."""
    unusable = binary_dilation(~optical_clear, iterations=3)
    for channel in OPTICAL_CHANNEL_INDEXES:
        features[channel][unusable] = OPTICAL_MISSING_VALUE
    return features
```

### 1.8 Prediction and post-processing

The predictor runs the network on a 512 by 512 tile and returns the per-pixel flooded probability. The backend then removes permanent water and anything outside the Philippine land mask before applying the decision threshold.

**File:** `ml/inference/predictor.py`

```python
    def predict_probability(self, features: np.ndarray) -> np.ndarray:
        """Return the per-pixel flooded probability for a [channels, height, width] tile."""
        expected = (INPUT_CHANNEL_COUNT, *INPUT_SIZE)
        if features.shape != expected:
            raise ValueError(f"Expected features shaped {expected}, received {features.shape}.")
        batch = Tensor(features[np.newaxis].astype(np.float32), ms.float32)
        with self._lock:
            logits = self.network(batch).asnumpy()[0]
        shifted = np.exp(logits - logits.max(axis=0, keepdims=True))
        return (shifted / shifted.sum(axis=0, keepdims=True))[FLOODED_CLASS_INDEX]
```

**File:** `backend/app/services/flood_model_service.py`

```python
    probability = predictor.predict_probability(scene.features)
    permanent_water = _permanent_water_mask(pc, grid, bbox, radar_target)
    from app.services.land_mask import land_mask

    # Flooding is only reported on land inside the Philippine province boundaries, never over the open sea.
    probability = np.where(permanent_water | ~land_mask(grid, bbox, probability.shape), 0.0, probability).astype(np.float32)
    threshold = _decision_threshold(float(scene.optical_clear.mean()))
    flooded = probability >= threshold
```

The threshold depends on the input mode. It was chosen on validation data only and is stored in the model card next to the checkpoint:

**File:** `backend/app/services/flood_model_service.py`

```python
    card = read_model_card(get_flood_model_checkpoint())
    thresholds = card.get("decision_thresholds")
    if thresholds:
        mostly_clear = optical_clear_fraction is not None and optical_clear_fraction >= 0.5
        value = thresholds.get("radar_optical" if mostly_clear else "radar_only")
```

### 1.9 Export to MindIR

The exporter produces a MindIR file that Huawei ModelArts can serve. We exported on CPU only and have not deployed it.

**File:** `ml/export/export_model.py`

```python
    network.set_train(False)
    example_input = Tensor(
        np.zeros((1, INPUT_CHANNEL_COUNT, *INPUT_SIZE), dtype=np.float32),
        ms.float32,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mindir_path = output_path.with_suffix("")
    export(network, example_input, file_name=str(mindir_path), file_format="MINDIR")
```

---

## Module 2: Flood-prone terrain model (MLP)

**Summary.** `SusceptibilityNet` is a small MindSpore multilayer perceptron (5 → 64 → 64 → 1) that scores each 90 m cell by how easily water collects there. Its inputs are Copernicus DEM GLO-90 elevation, local relief at about 1 km and 3 km, slope, and the distance to permanent water from JRC Global Surface Water. The label is land that JRC saw underwater only part of the time (3 to 60% of Landsat observations, 1984–2020) versus land never underwater. It scored AUC 0.9675 on 14 whole 1° regions never used in training, and the result is scored into 95 national overlays.

The label is *historical water occurrence*. It includes paddies and wetlands, so a high score means "water has tended to collect here", not "a flood is coming".

### 2.1 The five terrain features

All five channels are real and are scaled to about 0–1.

**File:** `ml/susceptibility/features.py`

```python
FEATURE_NAMES = ("elevation", "relief_1km", "relief_3km", "slope", "distance_to_permanent_water")
PERMANENT_WATER_OCCURRENCE = 80
TEMPORARY_WATER_RANGE = (3, 60)  # JRC occurrence (%) of land that is water only part of the time
```

```python
    cell_y, cell_x = cell_metres(latitude)
    slope_y, slope_x = np.gradient(elevation, cell_y, cell_x)
    slope = np.degrees(np.arctan(np.hypot(slope_x, slope_y)))
    relief_1km = elevation - minimum_filter(elevation, size=13, mode="nearest")
    relief_3km = elevation - minimum_filter(elevation, size=37, mode="nearest")
    permanent = np.nan_to_num(occurrence, nan=0.0) >= PERMANENT_WATER_OCCURRENCE
```

```python
    return np.stack(
        (
            np.log1p(np.clip(elevation, 0, 3000)) / np.log1p(3000),
            np.clip(relief_1km, 0, 100) / 100,
            np.clip(relief_3km, 0, 300) / 300,
            np.clip(slope, 0, 45) / 45,
            np.log1p(distance) / np.log1p(MAX_DISTANCE_METRES),
        )
    ).astype(np.float32)
```

### 2.2 The label from real water history

**File:** `ml/susceptibility/features.py`

```python
def history_labels(occurrence: np.ndarray, elevation: np.ndarray) -> np.ndarray:
    """1 = land that Landsat saw underwater only part of the time, 0 = never water, -1 = ignore."""
    low, high = TEMPORARY_WATER_RANGE
    observed = np.isfinite(occurrence)
    value = np.nan_to_num(occurrence, nan=0.0)
    labels = np.full(occurrence.shape, -1, dtype=np.int8)
    labels[observed & (value <= 1) & (elevation > 0.5)] = 0
    labels[observed & (value >= low) & (value < high)] = 1
    return labels
```

### 2.3 The network

**File:** `ml/susceptibility/model.py`

```python
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
```

### 2.4 Honest testing: hold out whole regions

Neighbouring pixels look alike, so testing on random pixels would flatter the model. Instead, about one in five 1° regions is chosen by a hash of its name and never used for training. The score is the area under the ROC curve (AUC), computed from ranks.

**File:** `ml/susceptibility/train.py`

```python
HOLDOUT_MODULUS = 5  # about 1 in 5 provinces never seen during training


def is_holdout(province: str) -> bool:
    return zlib.crc32(province.encode()) % HOLDOUT_MODULUS == 0
```

```python
def auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """Rank-based area under the ROC curve (probability a flood-prone pixel outranks a dry one)."""
    order = scores.argsort()
    ranks = np.empty(len(scores))
    ranks[order] = np.arange(1, len(scores) + 1)
    positives = labels == 1
    n_pos, n_neg = float(positives.sum()), float((~positives).sum())  # floats: int32 counts overflow on Windows
    return float((ranks[positives].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))
```

```python
    network = SusceptibilityNet()
    training_step = nn.TrainOneStepCell(
        nn.WithLossCell(network, nn.BCEWithLogitsLoss()), nn.Adam(network.trainable_params(), learning_rate=arguments.learning_rate)
    )
```

### 2.5 Scoring the whole country

Each 1° square is scored in batches and saved as a coloured PNG for the map and as an 8-bit score file for the click report. Permanent water and the sea are set to zero.

**File:** `ml/susceptibility/national.py`

```python
        logits = np.concatenate(
            [network(ms.Tensor(flat[i : i + 131072], ms.float32)).asnumpy()[:, 0] for i in range(0, len(flat), 131072)]
        )
        score = (1 / (1 + np.exp(-logits))).reshape(CORE, CORE).astype(np.float32)
        land = (elevation[core] > 0.5) & (np.nan_to_num(occurrence[core], nan=0.0) < terrain.PERMANENT_WATER_OCCURRENCE)
        score = np.where(land, score, 0.0)
```

### 2.6 A rule (not a model) that combines terrain and forecast rain

The "watch level" on the click report multiplies a rain band by a terrain class. This is a fixed rule we wrote, not a trained model, and the code says so.

**File:** `backend/app/services/susceptibility_service.py`

```python
def flood_watch(local: dict[str, Any], forecast: dict[str, Any] | None) -> dict[str, str]:
    """Combine local flood-proneness with the forecast rain. The rain-to-flood link is a documented rule, not learned."""
    share = local["land_share_high"]
    terrain = "high" if share >= 0.2 else "moderate" if share >= 0.05 else "low"
    if forecast is None:
        return {"level": "unknown", "terrain": terrain, "rain": "unavailable",
                "message": "Rainfall forecast unavailable. Showing flood-prone terrain only."}
    rain = _rain_band(forecast["rainfall_24h_mm"])
    score = {"light": 0, "moderate": 1, "heavy": 2, "extreme": 3}[rain] * {"low": 1, "moderate": 2, "high": 3}[terrain]
    level = "warning" if score >= 6 else "watch" if score >= 3 else "advisory" if score >= 2 else "none"
```

---

## Module 3: Rain-aware flood outlook (experimental MLP)

**Summary.** `RainFloodNet` (7 → 64 → 64 → 1) adds two rain inputs to the five terrain features: the wettest single day and the total rain over about three days. It is trained on Sen1Floods11 flood labels (blocked to 90 m cells, permanent water excluded) with ERA5 reanalysis rain from the Open-Meteo archive, for 11 real flood events, none of them in the Philippines. In held-out-event testing its mean AUC was 0.8615 with rain against 0.8476 with terrain alone.

**This module is experimental.** At the thresholds we display, recall is only 0.08, 0.04 and 0.01 for advisory, watch and warning, so it misses most flooded cells. Its scores are not calibrated probabilities. See [Limitations](README.md#14-limitations).

### 3.1 The rain input and the network

Rain is log-scaled so heavy storms do not swamp the small values.

**File:** `ml/rain_flood/model.py`

```python
RAIN_FEATURES = ("rain_wettest_day", "rain_72h")
INPUT_NAMES = (*FEATURE_NAMES, *RAIN_FEATURES)
RAIN_SCALE = (300.0, 600.0)  # mm; rain inputs are log-scaled to about 0-1


def encode_rain(wettest_day_mm, rain_72h_mm):
    """Log-scale the two rain inputs (numpy arrays in mm) to the range the network was trained on."""
    import numpy as np

    return np.stack(
        (np.log1p(np.clip(wettest_day_mm, 0, RAIN_SCALE[0])) / np.log1p(RAIN_SCALE[0]),
         np.log1p(np.clip(rain_72h_mm, 0, RAIN_SCALE[1])) / np.log1p(RAIN_SCALE[1])),
        axis=-1,
    ).astype("float32")
```

```python
class RainFloodNet(nn.Cell):
    """Per-cell MLP: terrain context plus the rain of the last 72 hours in, flood logit out."""

    def __init__(self, inputs: int = len(INPUT_NAMES), hidden: int = 64) -> None:
        super().__init__()
        self.layers = nn.SequentialCell(
            [nn.Dense(inputs, hidden), nn.ReLU(), nn.Dense(hidden, hidden), nn.ReLU(), nn.Dense(hidden, 1)]
        )
```

### 3.2 Building the training table from real data

Each Sen1Floods11 label chip is blocked from 10 m pixels into 90 m cells. Each cell gets terrain features and the ERA5 rain in the 72 hours up to the satellite pass.

**File:** `ml/rain_flood/build_dataset.py`

```python
BLOCK = 9  # 9 x 9 ten-metre pixels = one 90 m cell
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
```

```python
    blocks = label[: size * BLOCK, : size * BLOCK].reshape(size, BLOCK, size, BLOCK).transpose(0, 2, 1, 3).reshape(size, size, -1)
    valid = (blocks >= 0).mean(axis=2)
    water = (blocks == 1).sum(axis=2) / np.maximum((blocks >= 0).sum(axis=2), 1)
    keep = valid >= 0.6
```

```python
                response = httpx.get(ARCHIVE, params={
                    "latitude": ",".join(str(p[0]) for p in batch), "longitude": ",".join(str(p[1]) for p in batch),
                    "start_date": (day - timedelta(days=2)).isoformat(), "end_date": day.isoformat(),
                    "daily": "precipitation_sum", "timezone": "UTC",
                }, timeout=60.0)
```

```python
            values = [value or 0.0 for value in item["daily"]["precipitation_sum"]]
            rain[point] = (max(values), sum(values))
```

> Known weakness: a missing archive value becomes `0.0` on the line above. Event dates are typed in by hand (`EVENT_DATES`) and were not independently verified.

### 3.3 Testing on flood events the model never saw

The 11 events are split into 4 folds. In each fold, whole events are held out, and a terrain-only network is compared with a terrain-plus-rain network.

**File:** `ml/rain_flood/train.py`

```python
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
```

The display thresholds are the lowest scores that reach a target precision, and the model card records the recall each one gives:

**File:** `ml/rain_flood/train.py`

```python
    for level, precision in (("advisory", 0.35), ("watch", 0.5), ("warning", 0.7)):
        for threshold in np.arange(0.05, 0.99, 0.01):
            selected = probability >= threshold
            if selected.sum() > 500 and truth[selected].mean() >= precision:
                levels[level] = {"threshold": round(float(threshold), 2), "precision": round(float(truth[selected].mean()), 3),
                                 "recall": round(float(truth[selected].sum() / truth.sum()), 3)}
                break
```

### 3.4 Live rain inputs for the Philippines

Open-Meteo returns the last 72 hours of model rain plus a 72-hour forecast. The rain model uses the **past 48 hours plus the next 24 hours** per forecast point. This window is not identical to the one used in training, which is a known limitation.

**File:** `backend/app/integrations/flood_screening_client.py`

```python
        # Open-Meteo returns the last PAST_HOURS of rain (model analysis) before the 72 forecast hours.
        past_rain = values[:-72] if len(values) > 72 else []
        if past_rain:
            values, temperature_values, pressure_values = values[-72:], temperature_values[-72:], pressure_values[-72:]
            speeds, directions, times = speeds[-72:], directions[-72:], times[-72:]
        flood_window = past_rain[-48:] + values[:24]
        model_rain_24h = max(sum(flood_window[start:start + 24]) for start in range(max(1, len(flood_window) - 23)))
        model_rain_72h = sum(flood_window)
```

### 3.5 Running the model over a map chunk

For each land cell of a 1° square, the network is run twice: once with the forecast rain and once with no rain. The difference shows what the rain adds.

**File:** `backend/app/services/rain_flood_service.py`

```python
    probability = np.zeros(land.shape, dtype=np.float32)
    dry = np.zeros(land.shape, dtype=np.float32)
    rows, columns = np.nonzero(land)
    cells = features[:, rows, columns].T.astype(np.float32) / 255.0
    probability[rows, columns] = _probability(cells, wettest[rows, columns], total[rows, columns])
    no_rain = np.zeros(len(rows), dtype=np.float32)
    dry[rows, columns] = _probability(cells, no_rain, no_rain)
    return probability, dry, land, wettest
```

### 3.6 What the map draws (a display rule)

Nothing is drawn where the forecast rain is under 10 mm in the wettest 24 hours, and cells are drawn only where rain raises the score. This is a display rule we chose. It does **not** prove that an undrawn area is safe.

**File:** `backend/app/services/rain_flood_service.py`

```python
UPLIFT_MIN, UPLIFT_RAMP = 0.04, 0.08  # probability a cell must gain from rain before it is drawn, and how fast it fades in
MIN_RAIN_MM, RAIN_RAMP_MM = 10.0, 20.0  # forecast wettest-24 h rain below which nothing is drawn, and the fade-in range
DEFAULT_THRESHOLDS = {"advisory": 0.51, "watch": 0.65, "warning": 0.8}
COLOURS = {"advisory": (240, 201, 58), "watch": (238, 138, 43), "warning": (200, 62, 62), "extreme": (127, 29, 29)}
```

```python
        uplift = np.clip((gaussian_filter(probability - dry, 1.4) - UPLIFT_MIN) / UPLIFT_RAMP, 0, 1)
        uplift *= np.clip((gaussian_filter(wettest, 8.0) - MIN_RAIN_MM) / RAIN_RAMP_MM, 0, 1)
```

### 3.7 The verdict for one clicked point

**File:** `backend/app/services/rain_flood_service.py`

```python
    limits = thresholds()
    rain_drives = bool(wettest[row, column] >= MIN_RAIN_MM and probability[row, column] - dry[row, column] >= UPLIFT_MIN)
    level = "none"
    if rain_drives:
        level = next((name for name in ("warning", "watch", "advisory") if nearby >= limits[name]), "none")
```

---

## Module 4: Real weather and satellite context data

**Summary.** The map's weather layers use only real public data. Open-Meteo supplies forecasts, JMA Himawari-9 supplies cloud imagery, and NASA GIBS supplies satellite-measured rain (IMERG). Pressure contours are drawn from the real forecast points. Nothing in this module is invented. Wind, temperature and pressure are displayed only and are not inputs to any model.

### 4.1 Open-Meteo forecast with retries

The client asks for hourly rain, temperature, pressure and wind for batches of points, retries on rate limits and server errors, and serves the last good forecast if the provider is briefly down.

**File:** `backend/app/integrations/flood_screening_client.py`

```python
        "hourly": (
            "precipitation,temperature_2m,pressure_msl,"
            "wind_speed_10m,wind_direction_10m"
        ),
        "past_hours": PAST_HOURS,
        "forecast_hours": 72,
        "timezone": "UTC",
```

```python
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            response = await client.get(FORECAST_URL, params=request_params)
            response.raise_for_status()
            payload = response.json()
            break
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            if status not in RETRYABLE_STATUS_CODES or attempt == FETCH_ATTEMPTS:
                raise FloodScreeningError(f"Forecast provider returned HTTP {status}.") from error
```

```python
    except FloodScreeningError:
        if _SCREENING_CACHE:
            logger.warning("Serving the last rainfall forecast because the provider is unavailable.")
            return _SCREENING_CACHE[1]
        raise
```

### 4.2 Sharing one fetch between requests

Several browser requests can arrive at once. They share a single provider call. A fix we made after testing: a fetch started by another thread's event loop (the background scan) cannot be awaited from the API's loop, so it is replaced instead of reused.

**File:** `backend/app/integrations/flood_screening_client.py`

```python
async def _share_in_flight(key: str, start: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
    """Let simultaneous requests share one provider fetch instead of each calling it."""
    loop = asyncio.get_running_loop()
    task = _IN_FLIGHT.get(key)
    # A task started by another event loop (for example the background scan thread) cannot be awaited here.
    if task is None or task.done() or task.get_loop() is not loop:
        task = asyncio.ensure_future(start())
        _IN_FLIGHT[key] = task
```

### 4.3 From forecast points to provinces

The forecast points are about 0.5° apart. They are grouped by the real province boundaries. Rain shows the wettest point in a province, and temperature and pressure show the mean.

**File:** `backend/app/integrations/province_forecast_client.py`

```python
    result_features = []
    for index, feature in enumerate(features):
        group = [samples[position] for position in members[index]]
        peak = max(group, key=lambda sample: sample["rainfall_24h_mm"])
        elevations = [sample["elevation_m"] for sample in group if sample["elevation_m"] is not None]
        mean = lambda key: round(sum(sample[key] for sample in group) / len(group), 1)  # noqa: E731
```

### 4.4 Live clouds from JMA Himawari-9

JMA publishes grayscale infrared tiles. Warm ground and sea are dark and cold cloud tops are bright, so brightness is turned into a white cloud layer whose opacity grows with brightness. Clear sea and land stay transparent.

**File:** `backend/app/integrations/himawari_client.py`

```python
# Infrared brightness of clear sea and land is about 25-35; clouds are brighter.
CLOUD_BRIGHTNESS_FLOOR = 36
CLOUD_BRIGHTNESS_CEILING = 200
```

```python
    span = CLOUD_BRIGHTNESS_CEILING - CLOUD_BRIGHTNESS_FLOOR
    alpha_table = []
    tone_table = []
    for value in range(256):
        strength = min(1.0, max(0.0, (value - CLOUD_BRIGHTNESS_FLOOR) / span))
        alpha_table.append(min(255, round(255 * 0.92 * strength ** 0.7 / 8) * 8))
        tone_table.append(min(255, round((214 + 41 * strength) / 8) * 8))
    tone = brightness.point(tone_table)
    overlay = Image.merge("RGBA", (tone, tone, tone, brightness.point(alpha_table)))
```

### 4.5 Satellite-measured rain from NASA IMERG

The backend stitches real NASA tiles together and softens the edges so the rain looks like weather instead of blocks. The data is published about 4–6 hours late.

**File:** `backend/app/integrations/imerg_client.py`

```python
GIBS_TILE = (
    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/IMERG_Precipitation_Rate_30min/default/"
    "{time}/GoogleMapsCompatible_Level6/{z}/{y}/{x}.png"
)
```

```python
        rgba = np.array(canvas).astype(np.float32)
        alpha = rgba[..., 3:4] / 255.0
        premultiplied = np.concatenate([rgba[..., :3] * alpha, alpha], axis=-1)
        blurred = np.stack([gaussian_filter(premultiplied[..., channel], 3.0) for channel in range(4)], axis=-1)
        soft_alpha = np.clip(blurred[..., 3:4] * 1.35, 0, 1)
```

### 4.6 Smooth weather pictures between real points

Weather images are interpolated only between real forecast points, and pixels farther than about 0.45° from any real point are made transparent, so the map never shows a value that no forecast point supports.

**File:** `backend/app/services/weather_fields.py`

```python
def _interpolate(samples: list[dict[str, Any]], key: str, longitudes: np.ndarray, latitudes: np.ndarray):
    """Linear interpolation between forecast points; `inside` marks pixels within ~0.45 degrees of a real point."""
    points = np.array([[sample["longitude"], sample["latitude"]] for sample in samples], dtype=float)
    values = np.array([sample[key] for sample in samples], dtype=float)
    linear = LinearNDInterpolator(points, values)(longitudes, latitudes)
    filled = np.where(np.isnan(linear), NearestNDInterpolator(points, values)(longitudes, latitudes), linear)
    distance, _ = cKDTree(points).query(np.column_stack([longitudes.ravel(), latitudes.ravel()]))
    return filled, distance.reshape(longitudes.shape) <= 0.45
```

```python
RAIN_STOPS = (0.0, 0.1, 1.0, 3.0, 8.0, 15.0, 30.0)
RAIN_COLOURS = ((199, 182, 240), (160, 130, 232), (120, 84, 222), (98, 52, 206), (140, 40, 190), (190, 30, 150), (214, 30, 90))
```

### 4.7 Pressure contours

Contour lines (isobars) are drawn every 1 hPa from the interpolated pressure. The letters L and H mark the lowest and highest values in the country. The colour scale is relative to today's range and is at least 6 hPa wide.

**File:** `backend/app/services/weather_fields.py`

```python
    generator = contour_generator(longitudes, latitudes, masked)
    features = []
    for level in range(int(np.ceil(values[~masked.mask].min())), int(np.floor(values[~masked.mask].max())) + 1):
        for line in generator.lines(float(level)):
            if len(line) > 5:
                features.append({"type": "Feature", "geometry": {"type": "LineString", "coordinates": line.tolist()},
                                 "properties": {"hpa": level, "label": f"{level}"}})
```

```python
    low, high = float(values[inside].min()), float(values[inside].max())
    if high - low < 6:
        centre = (low + high) / 2
        low, high = centre - 3, centre + 3
    return low, high
```

### 4.8 The coarse screening level

This simple rule colours the older province screening values. It is a rule, not a model, and is not a flood probability.

**File:** `backend/app/integrations/flood_screening_client.py`

```python
def _screening_level(rainfall_24h_mm: float, elevation_m: float | None) -> str:
    low_lying = elevation_m is not None and elevation_m <= LOW_ELEVATION_METERS
    if rainfall_24h_mm >= 100 or (rainfall_24h_mm >= 50 and low_lying):
        return "elevated"
    if rainfall_24h_mm >= 50 or (rainfall_24h_mm >= 25 and low_lying):
        return "watch"
    return "lower"
```

---

## Module 5: Land mask, nationwide scan and field assessment

**Summary.** These services make the satellite model's output trustworthy on a map of the Philippines. A land mask built from real province boundaries stops detections appearing over the sea. A nationwide scanner covers the country in 5.12 km tiles. A field assessment measures how much of each open-data farm field the detected water covers.

### 5.1 Land mask from province boundaries

The 87 province outlines are buffered by about 200 m because the published coastline is generalised, then drawn into the same pixel grid as the satellite tile.

**File:** `backend/app/services/land_mask.py`

```python
COASTAL_BUFFER_DEGREES = 0.002


def land_mask(grid, bbox: tuple[float, float, float, float], shape: tuple[int, int]) -> np.ndarray:
    """True for pixels of a UTM tile grid that lie inside a Philippine province."""
    _, geometries = _provinces()
    area = box(*bbox).buffer(COASTAL_BUFFER_DEGREES * 2)
    shapes = [
        (transform_geom("EPSG:4326", grid.crs, mapping(geometry.buffer(COASTAL_BUFFER_DEGREES))), 1)
        for geometry in geometries
        if geometry.intersects(area)
    ]
    if not shapes:
        return np.zeros(shape, dtype=bool)
    return rasterize(shapes, out_shape=shape, transform=grid.transform, fill=0, dtype="uint8").astype(bool)
```

### 5.2 A lattice of 13,594 land tiles

A 5.12 km lattice is laid over the country, and a tile is kept when its centre is on land.

**File:** `backend/app/services/nationwide_grid.py`

```python
TILE_KILOMETRES = 5.12
KILOMETRES_PER_DEGREE = 111.32
COAST_MARGIN_DEGREES = 0.02
```

```python
    latitude_step = TILE_KILOMETRES / KILOMETRES_PER_DEGREE
    tiles: list[Tile] = []
    latitude = south + latitude_step / 2
    while latitude < north:
        longitude_step = latitude_step / math.cos(math.radians(latitude))
        longitude = west + longitude_step / 2
        while longitude < east:
            point = Point(longitude, latitude)
            if land.contains(point):
                owner = int(tree.query(point, predicate="intersects")[0])
                tiles.append(Tile(tile_id_for(latitude, longitude), round(latitude, 3), round(longitude, 3), names[owner]))
            longitude += longitude_step
        latitude += latitude_step
```

### 5.3 Scanning one tile

Each tile uses the newest Sentinel-1 pass. Optical imagery is used only when a clear Sentinel-2 scene exists near that date, so the scan falls back to radar only otherwise. Permanent water and the sea are removed, and a failed tile never stops a nationwide run.

**File:** `backend/app/services/scan_service.py`

```python
        radar_item = _newest_radar_item(pc, bbox, window_days, until)
        optical_item = _matching_optical_item(pc, bbox, radar_item)
        scene = pc.read_scene(grid, radar_item, optical_item)
        probability = predictor.predict_probability(scene.features)
        permanent = _permanent_water(pc, tile, grid, bbox, radar_item["properties"]["datetime"])
        land = land_mask(grid, bbox, probability.shape)
        probability = np.where(permanent | ~land, 0.0, probability).astype(np.float32)
        threshold = model_service._decision_threshold(float(scene.optical_clear.mean()))
        flooded = probability >= threshold
```

```python
    except pc.SceneUnavailableError as error:
        record.update(status="no_data", message=str(error))
    except Exception as error:  # a failed tile must not stop a nationwide run
        record.update(status="error", message=f"{type(error).__name__}: {error}"[:300])
    save_scan(record)
    return record
```

### 5.4 Wettest provinces first

**File:** `backend/app/jobs/scan_philippines.py`

```python
    if arguments.order == "rainfall":
        try:
            rain = rainfall_priority()
            tiles.sort(key=lambda tile: -rain.get(tile.province, 0.0))
```

One tile takes about a minute on a laptop CPU, so a full pass needs far stronger hardware. Most tiles are unscanned, and blank on the map means "not scanned", never "no flood".

### 5.5 Optional background scan

When `SIPATAI_AUTO_SCAN=1` the API starts a daemon thread that scans one batch at a time and pauses between rounds.

**File:** `backend/app/services/auto_scan.py`

```python
BATCH_TILES = 20
PAUSE_SECONDS = 15 * 60


def is_enabled() -> bool:
    return os.getenv("SIPATAI_AUTO_SCAN", "").strip().lower() in {"1", "true", "yes", "on"}
```

```python
    _stop.clear()
    _thread = threading.Thread(target=_run, name="sipatai-auto-scan", daemon=True)
    _thread.start()
    return True
```

### 5.6 Measuring flooded farm fields

Each field polygon from the open Fields of The World dataset is drawn into the same pixel grid, and the detected-flood pixels inside it are counted. The Light, Moderate and Severe classes are a display scale we defined, not an agronomic damage grade. The polygons are satellite-detected field units, not legal parcels.

**File:** `backend/app/services/field_assessment_service.py`

```python
PIXEL_AREA_HA = 0.01  # one 10 m pixel
MIN_FIELD_PIXELS = 3
MAX_FEATURES = 4000
SIMPLIFY_DEGREES = 0.00002  # about 2 m
# Prototype display classes by flooded share of a field; not an agronomic damage grade.
SEVERITY_BREAKS = ((0.6, "Severe"), (0.3, "Moderate"), (0.1, "Light"))
```

```python
    labels = rasterize(shapes, out_shape=flooded.shape, transform=grid_transform, fill=0, dtype="int32") if shapes else np.zeros(flooded.shape, dtype="int32")

    count = len(fields) + 1
    pixels = np.bincount(labels.ravel(), minlength=count)
    flooded_pixels = np.bincount(labels[flooded], minlength=count)
```

---

## Module 6: Backend API (FastAPI)

**Summary.** FastAPI exposes everything above as JSON and PNG routes. CPU-heavy model work runs in a thread pool so it never blocks the server. Services that are not configured fail closed with a clear message instead of returning invented data.

### 6.1 Application entry point

**File:** `backend/app/main.py`

```python
@asynccontextmanager
async def lifespan(_app: FastAPI):
    auto_scan.start()
    yield
    auto_scan.stop()


app = FastAPI(
    title="SipatAI API",
    description="Agricultural flood assessment API backed by configured data and inference services.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    expose_headers=["X-Himawari-Observation-Time", "X-Himawari-Band"],
)
```

```python
app.include_router(weather_router, prefix="/api/v1")
app.include_router(flood_model_router, prefix="/api/v1")
app.include_router(scan_router, prefix="/api/v1")
```

### 6.2 Routes for the MindSpore models

**File:** `backend/app/api/routes/flood_model.py`

```python
router = APIRouter(prefix="/model", tags=["mindspore"])


@router.get("/status")
async def model_status() -> dict[str, Any]:
    """Report whether the local MindSpore flood model is installed and trained."""
    return await run_in_threadpool(get_model_status)
```

```python
@router.post("/analyze")
async def analyze_flood_area(request: FloodModelRequest) -> dict[str, Any]:
    """Run MindSpore flood segmentation on real Sentinel-1/2 data around a point."""
    try:
        return await run_in_threadpool(analyze_area, request.longitude, request.latitude, request.date)
    except FloodModelUnavailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except FloodModelDataError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
```

### 6.3 One call for the click report

The click report combines the terrain result, the province forecast, the rule-based watch level and the rain model. If the rain model or forecast is unavailable, the terrain result is still returned.

**File:** `backend/app/services/susceptibility_service.py`

```python
async def assess_point(longitude: float, latitude: float) -> dict[str, Any]:
    from app.integrations.province_forecast_client import get_forecast_samples
    from app.services import rain_flood_service

    local = local_susceptibility(longitude, latitude)
    forecast = await _forecast_for(longitude, latitude)
    result = {"local": local, "forecast": forecast, "watch": flood_watch(local, forecast), "rain_model": None}
    try:
        samples, _ = await get_forecast_samples()
        result["rain_model"] = rain_flood_service.point_prediction(longitude, latitude, samples)
    except Exception:
        pass  # The terrain result is still returned if the rain model or forecast is unavailable.
    return result
```

### 6.4 Lazy-loading MindSpore once

The model is loaded the first time it is needed and then reused, behind a lock. If MindSpore or the checkpoint is missing, the API reports "unavailable" with a reason.

**File:** `backend/app/services/flood_model_service.py`

```python
def _load_predictor():
    global _predictor
    with _predictor_lock:
        if _predictor is None:
            try:
                from ml.inference.predictor import CheckpointError, FloodPredictor
            except ImportError as error:
                raise FloodModelUnavailableError(
                    "MindSpore is not installed in the backend environment. "
                    "Install backend/requirements-ml.txt."
                ) from error
```

---

## Module 7: Frontend map (Vue 3 and Mapbox GL JS)

**Summary.** The frontend is a Vue 3 single-page app built with Vite. The map is the main screen. Model results are PNG overlays draped onto the Mapbox map, so no flood boundary is drawn by hand.

### 7.1 API client

**File:** `frontend/src/api/client.js`

```javascript
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''

async function request(path, options = {}) {
  if (!apiBaseUrl) {
    throw new Error('Set VITE_API_BASE_URL in frontend/.env.local to connect the API.')
  }

  const response = await fetch(`${apiBaseUrl}${path}`, options)
  if (!response.ok) {
    const errorBody = await response.json().catch(() => null)
    const details = Array.isArray(errorBody?.detail)
      ? errorBody.detail.map((item) => item.msg).join(' ')
      : errorBody?.detail
    throw new Error(details || `API request failed (${response.status}).`)
  }
  return response
}
```

### 7.2 Creating the map

**File:** `frontend/src/components/ParcelMap.vue`

```javascript
  map = new mapboxgl.Map({
    container: mapElement.value,
    style: 'mapbox://styles/mapbox/streets-v12',
    center: [121.774, 12.8797],
    zoom: 5,
    attributionControl: true,
  })
```

### 7.3 Draping model output on the map

Each 1° chunk becomes an image source whose four corners are the chunk's real coordinates, and the map draws it as a raster layer. The terrain layer is added first, and the rain model's layer goes on top.

**File:** `frontend/src/components/ParcelMap.vue`

```javascript
      const coordinates = [[chunk.west, chunk.north], [chunk.east, chunk.north], [chunk.east, chunk.south], [chunk.west, chunk.south]]
      const beforeLayer = map.getLayer(AI_OVERLAY_LAYER) ? AI_OVERLAY_LAYER : undefined
      const paint = { 'raster-opacity': 0.95, 'raster-resampling': 'linear', 'raster-fade-duration': 0 }
      if (showProne.value) {
        const layerId = `prone-${chunk.id}`
        map.addSource(layerId, {
          type: 'image',
          url: variant === 'outlook' ? floodContextUrl(chunk.id) : susceptibilityChunkUrl(chunk.id),
          coordinates,
        })
        map.addLayer({ id: layerId, type: 'raster', source: layerId, paint }, beforeLayer)
      }
      if (variant === 'outlook' && showForecast.value) {
        const layerId = `forecast-${chunk.id}`
        map.addSource(layerId, { type: 'image', url: floodForecastUrl(chunk.id, Number(scenarioRain.value)), coordinates })
        map.addLayer({ id: layerId, type: 'raster', source: layerId, paint }, beforeLayer)
      }
```

### 7.4 Province colours from forecast values

The temperature and precipitation layers colour each real province by interpolating along a colour scale.

**File:** `frontend/src/components/ParcelMap.vue`

```javascript
    precipitation: [
      'precipitation_6h_mm',
      [0, '#f2f7fa'], [0.1, '#8be0f2'], [1, '#30a9d8'],
      [5, '#4169e1'], [15, '#7b2cbf'], [30, '#e53935'], [50, '#8e0000'],
    ],
```

```javascript
  const [property, ...stops] = fieldAndStops
  map.setPaintProperty(fillLayer, 'fill-color', [
    'interpolate', ['linear'], ['to-number', ['get', property], 0],
    ...stops.flat(),
  ])
```

### 7.5 Animated wind

Wind particles move in screen pixels, so the animation looks the same at every zoom level. The speed and direction come from the real hourly forecast of the nearest forecast point.

**File:** `frontend/src/components/ParcelMap.vue`

```javascript
    const speed = Number(properties.wind_speed_10m_mps[hourIndex] ?? 0)
    const fromDirection = Number(properties.wind_direction_10m_deg[hourIndex] ?? 0)
    const direction = (fromDirection + 180) * Math.PI / 180
    // Move in screen pixels so the motion looks the same at every zoom level.
    const pixels = (0.7 + Math.min(speed, 25) * 0.17) * frameScale
    const start = map.project([particle.longitude, particle.latitude])
    const end = { x: start.x + Math.sin(direction) * pixels, y: start.y - Math.cos(direction) * pixels }
    const next = map.unproject([end.x, end.y])
```

### 7.6 The colour key ("What the colours mean")

Each layer has its own key, built from the same colours the backend uses.

**File:** `frontend/src/components/ParcelMap.vue`

```javascript
const TERRAIN_KEY = {
  title: 'Flood-prone land · MindSpore terrain model',
  rows: [
    { colour: '#96c8f0', label: 'Light blue · water has gathered here in the past' },
    { colour: '#1850aa', label: 'Dark blue · floods most easily' },
  ],
  note: 'Based on land height, slope and 36 years of satellite water history. It shows where water tends to collect, not a forecast.',
}
const RAIN_MODEL_KEY = {
  title: 'Flood signal from rain · MindSpore rain model',
  rows: [
    { colour: '#f0c93a', label: 'Yellow · weak signal' },
    { colour: '#ee8a2b', label: 'Orange · medium signal' },
    { colour: '#c83e3e', label: 'Red · strong signal' },
    { colour: '#7f1d1d', label: 'Dark red · strongest signal' },
  ],
  note: 'Drawn only where the forecast rain is heavy (10 mm a day or more). No colour does not mean safe. Experimental, not an official warning.',
}
```

```javascript
const colourKey = computed(() => {
  const layer = selectedWeatherLayer.value
  const groups = []
  if (layer === 'outlook') groups.push(TERRAIN_KEY, RAIN_MODEL_KEY)
```

### 7.7 The click report

Clicking the map asks the backend for the models' answer at that spot. The wording is careful: "No model signal here" instead of "no flood", and the rain score is shown as a number out of 100 and not as a probability.

**File:** `frontend/src/components/ParcelMap.vue`

```javascript
  const level = result.rain_model?.level ?? 'none'
  const [headline, tone] = VERDICTS[level]
  const verdict = document.createElement('div')
  verdict.className = `place-report-verdict place-report-${tone}`
  verdict.textContent = headline
  content.append(verdict)
  const why = document.createElement('p')
  why.className = 'place-report-note'
  const terrain = result.watch.terrain
  why.textContent = level === 'none'
    ? 'Our experimental models show no flood signal for this spot under the current forecast. That is not a guarantee of safety: the models were not validated on Philippine floods and can miss real flooding.'
    : 'Our experimental MindSpore rain model sees terrain and rain here that could let water collect. This is a model score, not a confirmed flood.'
```

```javascript
    const result = await predictFloodProneAreas({
      latitude: Number(event.lngLat.lat.toFixed(6)),
      longitude: Number(event.lngLat.lng.toFixed(6)),
    })
    fillPlaceReport(content, province, result, '')
```

---

## Module 8: Huawei Cloud adapters

**Summary.** SipatAI has integration code for Huawei ModelArts (model serving), OBS (object storage) and GaussDB with PostGIS (spatial database). **We had no Huawei Cloud credits, so none of this code has been run against a live Huawei service.** It is written so that the browser never sees a credential, and so that a missing service gives a clear "not configured" message instead of invented data. See [Huawei Cloud integration status](README.md#13-huawei-cloud-integration-status).

### 8.1 ModelArts inference

The backend forwards a request to a deployed ModelArts endpoint. It requires HTTPS, does not follow redirects, and sends the token only from the server.

**File:** `backend/app/integrations/modelarts_client.py`

```python
    endpoint_url, endpoint_token = endpoint_config
    if urlsplit(endpoint_url).scheme != "https":
        raise ModelArtsConfigurationError("ModelArts inference endpoint must use HTTPS.")

    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
            response = await client.post(
                endpoint_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-Auth-Token": endpoint_token,
                },
            )
            response.raise_for_status()
            return response.json()
```

### 8.2 OBS object storage

On a Huawei ECS server the client can use the server's role instead of stored keys.

**File:** `backend/app/integrations/obs_client.py`

```python
def _create_client(config: dict[str, str | bool]) -> ObsClient:
    if config["use_ecs_role"]:
        return ObsClient(
            server=str(config["endpoint"]),
            security_provider_policy="ECS",
            ssl_verify=True,
        )
```

### 8.3 GaussDB with PostGIS

The schema stores farm parcels and flood polygons as validated PostGIS geometries with spatial indexes.

**File:** `backend/migrations/001_spatial_assessment.sql`

```sql
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS farm_parcels (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    source_dataset TEXT NOT NULL,
    source_parcel_id TEXT NOT NULL,
    barangay_name TEXT NOT NULL,
    crop_type TEXT,
    source_crs TEXT NOT NULL,
    geometry_crs TEXT NOT NULL DEFAULT 'EPSG:4326' CHECK (geometry_crs = 'EPSG:4326'),
    geom geometry(MultiPolygon, 4326) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT farm_parcels_source_identifier_unique
        UNIQUE (source_dataset, source_parcel_id),
    CONSTRAINT farm_parcels_valid_geometry CHECK (ST_IsValid(geom))
);

CREATE INDEX IF NOT EXISTS farm_parcels_geom_gix
    ON farm_parcels USING GIST (geom);
```

The damage query intersects each parcel with the union of the flood polygons and measures real hectares on the ground (`::geography`):

**File:** `backend/app/db/queries/assessment.py`

```sql
WITH flood_extent AS (
    SELECT ST_UnaryUnion(ST_Collect(geom)) AS geom
    FROM flood_polygons
    WHERE assessment_id = %s
), parcel_measurements AS (
    SELECT
        parcel.id AS parcel_id,
        ST_Area(parcel.geom::geography) / 10000.0 AS parcel_area_hectares,
        CASE
            WHEN ST_Intersects(parcel.geom, flood_extent.geom)
            THEN ST_Area(ST_Intersection(parcel.geom, flood_extent.geom)::geography) / 10000.0
            ELSE 0.0
        END AS flooded_area_hectares
    FROM farm_parcels AS parcel
    CROSS JOIN flood_extent
)
```

---

## Where to find each file

| Topic | Path |
|---|---|
| Model contract (channels, tile size) | `ml/configs/model_config.py` |
| Input channels, radar water rule | `ml/data/features.py` |
| Reading Sentinel scenes, cloud masking | `ml/data/planetary_computer.py` |
| Sen1Floods11 training data | `ml/data/sen1floods11.py` |
| U-Net, loss, dataset, training, evaluation | `ml/models/`, `ml/losses/`, `ml/datasets/`, `ml/training/` |
| Prediction and MindIR export | `ml/inference/predictor.py`, `ml/export/export_model.py` |
| Terrain model | `ml/susceptibility/` |
| Rain-aware model | `ml/rain_flood/`, `backend/app/services/rain_flood_service.py` |
| Forecast, cloud and rain clients | `backend/app/integrations/` |
| Weather pictures and pressure contours | `backend/app/services/weather_fields.py` |
| Land mask, scanner, fields | `backend/app/services/land_mask.py`, `scan_service.py`, `nationwide_grid.py`, `field_assessment_service.py` |
| API routes | `backend/app/api/routes/` |
| Map, layers, colour key, click report | `frontend/src/components/ParcelMap.vue` |
| Database schema | `backend/migrations/` |

*SipatAI is an academic research prototype by students of Mariano Marcos State University. It is not an official warning system. Always follow PAGASA and your local disaster risk reduction office.*
