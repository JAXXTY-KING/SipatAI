# SipatAI

**A nationwide flood-awareness map for the Philippines, powered by MindSpore, real satellite imagery and real weather data.**

SipatAI is a research prototype we built for the **Huawei ICT Competition 2026–2027 (Innovation Competition)**. It combines Sentinel-1 radar and Sentinel-2 optical satellite imagery, live weather observations and forecasts, and three MindSpore neural networks on one interactive map. The map shows where water is already standing, which land tends to flood, and where our experimental rain model expects water to collect.

> **Important:** SipatAI is a student research prototype. It is **not** an official warning system and it has **not** been validated against Philippine flood records. Always follow PAGASA, NDRRMC and your local disaster risk reduction office. Read the [Limitations](#14-limitations) before relying on anything on the map.

---

## Team  

We are students of **Mariano Marcos State University (MMSU)**, Philippines.

| Member | Role |
|---|---|
| Andrew D. Caditan | Student developer |
| Aldrich Jave O. Calonge | Student developer |
| Hanni Marie Dadia | Student developer |
| Renante Burgos | Instructor (the competition requires one instructor per team) |

---

## Table of contents

1. [Why we built SipatAI](#1-why-we-built-sipatai)
2. [What SipatAI does](#2-what-sipatai-does)
3. [Huawei ICT Competition: rules and how we address them](#3-huawei-ict-competition-rules-and-how-we-address-them)
4. [System architecture](#4-system-architecture)
5. [The three MindSpore models](#5-the-three-mindspore-models)
6. [Data sources](#6-data-sources)
7. [Map layers and user interface](#7-map-layers-and-user-interface)
8. [What we installed (technology stack)](#8-what-we-installed-technology-stack)
9. [What we built (repository guide)](#9-what-we-built-repository-guide)
10. [Installation and first run (Windows)](#10-installation-and-first-run-windows)
11. [Training and running the models](#11-training-and-running-the-models)
12. [API reference](#12-api-reference)
13. [Huawei Cloud integration status](#13-huawei-cloud-integration-status)
14. [Limitations](#14-limitations)
15. [Responsible use, privacy and security](#15-responsible-use-privacy-and-security)
16. [Testing](#16-testing)
17. [Roadmap](#17-roadmap)
18. [Data licences and acknowledgements](#18-data-licences-and-acknowledgements)
19. [Further documents](#19-further-documents)

---

## 1. Why we built SipatAI

The Philippines is hit by typhoons and monsoon rains every year, and farmland in low-lying river basins floods repeatedly. Official forecasts and warnings exist, but it is hard for a farmer, a student or a local office to see in one place:

- what the satellites currently show on the ground,
- which land is naturally prone to flooding, and
- how today's rain relates to both.

SipatAI tries to put those three views on a single map that anyone can open in a browser. We use MindSpore, Huawei's AI framework, for the parts of the problem that need machine learning: reading satellite images, learning which terrain collects water, and linking rainfall to flood-prone land.

The long-term scenario is agricultural flood assessment. We estimate how much of a field a flood covers, using open field boundaries, so that a municipal agriculture office could prioritise inspection after an event.

---

## 2. What SipatAI does

| Capability | What it gives you | Powered by |
|---|---|---|
| **Detected floods (satellite)** | Outlines of surface water found in a recent Sentinel-1/Sentinel-2 image, masked to Philippine land. | MindSpore ResNet-50 U-Net |
| **Flood-prone terrain** | A nationwide map of land that tends to collect water, drawn from elevation and 36 years of water history. | MindSpore terrain network |
| **Flood outlook** | An experimental map of where forecast rain may collect on flood-prone terrain. | MindSpore rain-aware network |
| **Rain watch** | Real satellite clouds, NASA satellite-measured rain and Open-Meteo forecast rain, drawn on the real province outlines. | NASA GIBS, JMA, Open-Meteo |
| **Wind, temperature, pressure, 6-hour rain** | Forecast layers drawn per province, plus animated wind. | Open-Meteo |
| **Click-anywhere place report** | Weather and model results for the exact spot you click. | Backend + all models |
| **Place search** | Search a Philippine city or town and jump to it. | Open-Meteo geocoding |
| **Per-field assessment** | For a scanned 5 km tile, how much of each open-data field boundary is under detected water. | MindSpore + Fields of The World |
| **Nationwide scan** | A background job that scans the country in 5.12 km tiles and stores the results. | MindSpore U-Net |
| **Dashboard and PDF reports** | Summary tables and downloadable PDF briefs. | FastAPI, ReportLab |

We do not seed or serve invented records. When a data source is unreachable, the app shows an explicit "unavailable" state instead of placeholder numbers. The only synthetic content is the clearly labelled **"What if"** rain scenarios in the Flood outlook (see [Limitations](#14-limitations)).

---

## 3. Huawei ICT Competition: rules and how we address them

We are entering the **Innovation Competition** of the Huawei ICT Competition 2026–2027 (theme "Connection Glory Future"). The summary below is drawn from the *Huawei ICT Competition Manual 2026–2027* we received. We will re-check the official competition portal before every submission, because dates and criteria can change.

### 3.1 Rules that apply to us

| Rule (from the manual) | What it means for our entry |
|---|---|
| Teams have **1 instructor and up to 3 students**, all full-time university students at registration. | We are three MMSU students, and our instructor is Renante Burgos. |
| Each contestant joins **only one track** and registers in **one region** only. | We are registered only in Innovation. |
| Entries must be **original, legal and IP-clear**, and must not discriminate or violate privacy. | All code is our own. Third-party data is public and credited in [section 18](#18-data-licences-and-acknowledgements). We collect no personal data. |
| **IP stays with the participants.** The organiser gets free rights to reproduce, show and disseminate entries. | We keep our IP. We have not yet chosen an open-source licence. |
| Innovation entries use **Huawei AI** (for example MindSpore, Ascend, Huawei Cloud) **combined with** generative AI, big data, cloud, mobile Internet or IoT. | We use MindSpore with large-scale open satellite and weather data. |
| Solutions must address a **real-world need**, show an **innovative scenario**, show **commercial potential** and have a **complete technical architecture**. | See [section 1](#1-why-we-built-sipatai), [section 2](#2-what-sipatai-does) and [section 4](#4-system-architecture). |
| Deliverables: **technical documents, code files, a demo video**, and an **onsite presentation** at the Regional and Global Finals. | See the [status table below](#32-our-honest-status-against-the-requirements). |
| Three levels: **National, Regional and Global Final** (Shenzhen, May 2027). | We will follow the national organiser's schedule. |
| Special awards include the **Green Development Award** (sustainability, SDGs) and the **TECH4ALL** inclusion award. | Our flood-awareness focus relates to climate resilience (SDG 13) and food security (SDG 2). We make no claim to any award. |

### 3.2 Our honest status against the requirements

| Requirement | Status | Notes |
|---|---|---|
| Uses MindSpore | **Met** | Three models on MindSpore 2.10.0: training, evaluation, MindIR export and live inference. |
| Uses Huawei Cloud (ModelArts, OBS, GaussDB) | **Partly met** | We wrote the ModelArts, OBS and GaussDB/PostGIS integrations, but we have **no Huawei Cloud resources or credits**. They are untested against live services. See [section 13](#13-huawei-cloud-integration-status). |
| Uses Ascend hardware | **Not met** | Everything ran on laptop CPU. Ascend execution is not validated. |
| Real-world problem | **Met** | Flood awareness for Philippine agriculture. |
| Complete technical architecture | **Met** | [Section 4](#4-system-architecture). |
| Technical documents | **Met (this README and `ml/README.md`)** | See [section 19](#19-further-documents). |
| Code files | **Met** | This repository. |
| Demo video | **Met** | Produced by our team. |
| Onsite presentation | **Not yet prepared** | Only needed if we advance. |
| Commercial potential | **Described, not proven** | We have not validated any market, pricing or customer. See [roadmap](#17-roadmap). |

---

## 4. System architecture

```
  Public data                     Backend (FastAPI, Python 3.12)                  Browser
  ───────────                     ─────────────────────────────                  ───────
  Sentinel-1 / Sentinel-2  ─┐     ┌───────────────────────────────────┐
  (Planetary Computer)      │     │  Satellite flood model            │
  Copernicus DEM, JRC water ├────►│  MindSpore ResNet-50 U-Net        │
  ESA WorldCover            │     │  Terrain susceptibility model     │      Vue 3 + Vite
  Sen1Floods11 (training)   │     │  MindSpore MLP                    │      Mapbox GL JS map
  Fields of The World       │     │  Rain-aware flood model           │◄────►  Layer panel
  (open field polygons)     │     │  MindSpore MLP                    │      Click place report
                            │     ├───────────────────────────────────┤      Dashboard, reports
  Open-Meteo forecast/ERA5  ├────►│  Weather services and clients     │
  NASA GIBS IMERG rain      │     │  Land mask (geoBoundaries ADM2)   │
  JMA Himawari-9 clouds     ┘     │  Nationwide scanner and auto-scan │
                                  │  SQLite store (scans, assessments)│
                                  │  PDF reports (ReportLab)          │
                                  ├───────────────────────────────────┤
                                  │  Optional Huawei Cloud adapters   │
                                  │  ModelArts · OBS · GaussDB/PostGIS│
                                  └───────────────────────────────────┘
```

**Typical request flow (click a place on the map):**

1. The browser sends the clicked coordinates to `POST /api/v1/model/susceptibility`.
2. The backend finds the province, reads its real Open-Meteo forecast, samples the terrain model's stored score and the rain model's result around the point, and returns a combined report.
3. The browser shows the report in a popup. Nothing is stored about the visitor.

**Typical scan flow (background job):**

1. Choose a 5.12 km land tile from the real province boundaries, wettest forecast provinces first.
2. Fetch the newest Sentinel-1 radar (and Sentinel-2 optical, if clear) from Microsoft Planetary Computer.
3. Run the MindSpore U-Net, remove permanent water, and mask to land with the province boundaries.
4. Save the result and overlay image to the local SQLite store. The map and dashboard read from it.

---

## 5. The three MindSpore models

All three run in MindSpore 2.10.0 on CPU. The weights are produced by our training scripts and are **not stored in the repository** (see [section 11](#11-training-and-running-the-models)).

### 5.1 Satellite flood segmentation (ResNet-50 U-Net)

| Item | Detail |
|---|---|
| Code | `ml/models/resnet_unet.py`, `ml/losses/weighted_focal_dice.py`, `ml/training/` |
| Task | Per-pixel segmentation: water in the flood image or not. |
| Input | 6 channels at 10 m: Sentinel-1 VV and VH, NDVI, NDWI, red, NIR. Tiles are 512×512 px at inference and 128×128 random crops in training. |
| Training data | [Sen1Floods11](https://github.com/cloudtostreet/Sen1Floods11): 446 hand-labelled chips from 11 real flood events. |
| Loss | Weighted focal loss plus Dice loss. Class weights 1 and 2, focal γ = 2, Dice weight 1. |
| Cloud handling | Optical channels were randomly removed during training. At inference, cloudy optical pixels are marked missing and the model falls back on radar. |
| Test result (unseen chips) | IoU **0.76** with optical imagery, **0.61** radar-only. IoU on an entirely unseen event (Bolivia): 0.78 and 0.64. |
| Post-processing | Permanent water is subtracted using a dry-season Sentinel-1 reference. Output is masked to Philippine land. Cropland share uses ESA WorldCover 2021. |

These scores are measured on Sen1Floods11 test data from other countries, **not on Philippine floods**.

### 5.2 Flood-prone terrain (MLP)

| Item | Detail |
|---|---|
| Code | `ml/susceptibility/` |
| Task | Score how likely a 90 m cell is to collect water. |
| Network | `SusceptibilityNet`, a 5→64→64→1 MLP. |
| Inputs | Copernicus DEM GLO-90 elevation, local relief at about 1 km and 3 km, slope, and distance to permanent water. |
| Label | [JRC Global Surface Water](https://global-surface-water.appspot.com/): land underwater for 3–60% of Landsat observations (1984–2020) versus land never underwater. |
| Result | AUC **0.9675** on 14 whole 1° regions never used in training. The network trained on 80 other Philippine 1° regions. |
| Coverage | 95 one-degree overlays covering the Philippines. |

The label is *historical water occurrence*. It includes paddies and wetlands. A high score means "water has tended to collect here", not "a flood is coming".

### 5.3 Rain-aware flood model (experimental MLP)

| Item | Detail |
|---|---|
| Code | `ml/rain_flood/`, `backend/app/services/rain_flood_service.py` |
| Task | Combine terrain with recent and forecast rain. |
| Network | `RainFloodNet`, a 7→64→64→1 MLP. |
| Inputs | The five terrain features plus the wettest-day and 72-hour rain totals (log-scaled). |
| Training data | Sen1Floods11 flood labels blocked to 90 m cells, with ERA5 rain from the Open-Meteo archive for the days up to each satellite pass. 11 events, **none in the Philippines**. |
| Result | Mean held-out-event AUC **0.8615** with rain, against 0.8476 for terrain alone, across 4 folds. |
| Operating points | At the three thresholds we display (advisory, watch, warning), precision is 0.35, 0.50 and 0.72, but **recall is only 0.08, 0.04 and 0.01**. |
| Live inputs | Open-Meteo rain over the past 48 hours plus the next 24 hours, for each province. |

This model is experimental. The metrics describe how well it ranks cells in other countries' flood events. They do not describe its accuracy in the Philippines, and its scores are **not calibrated probabilities**. The map only draws the model's output where forecast rain exceeds 10 mm in the wettest day (fading in over the next 20 mm). That is a display heuristic we chose, and it does not prove that an undrawn area is safe.

### 5.4 Rules that are not learned

The "watch level" on the click report (rain band × terrain class) is a fixed rule in `susceptibility_service.flood_watch`, not a trained model. Wind, temperature and pressure are displayed but **are not inputs to any model**.

---

## 6. Data sources

Every dataset is public. We use no private or purchased data, and we do not fabricate records.

| Purpose | Source | Access |
|---|---|---|
| Radar and optical satellite imagery | Sentinel-1 RTC and Sentinel-2 L2A via [Microsoft Planetary Computer](https://planetarycomputer.microsoft.com/) | Public STAC API |
| Scene catalogue search | [Copernicus Data Space](https://dataspace.copernicus.eu/) STAC | Public search; downloads need an account |
| Training labels | [Sen1Floods11](https://github.com/cloudtostreet/Sen1Floods11) | Public |
| Elevation | Copernicus DEM GLO-90 | Public (Planetary Computer) |
| Water history | JRC Global Surface Water | Public (Planetary Computer) |
| Land cover | ESA WorldCover 2021 | Public (Planetary Computer) |
| Field boundaries | [Fields of The World](https://fieldsofthe.world/), Philippines GeoParquet (CC BY 4.0) | Public; read with DuckDB |
| Province boundaries (land mask, weather map) | geoBoundaries ADM2, 87 provinces (CC BY 3.0 IGO) | Stored in `frontend/public/data/` |
| Region outlines | SimpleMaps (CC BY 4.0) | Optional context layer |
| Forecast weather | [Open-Meteo](https://open-meteo.com/) | Public API, no key |
| Training-period rain | ERA5 reanalysis via the Open-Meteo archive | Public API |
| Satellite-measured rain | NASA GPM IMERG via NASA GIBS | Public, about 4–6 hours behind real time |
| Satellite clouds | JMA Himawari-9 infrared imagery | Public |
| Basemap | Mapbox Streets | Public token, restricted by domain |
| Terrain relief on the map | AWS Terrain Tiles (Mapzen) | Public |

---

## 7. Map layers and user interface

The landing page is the map. The left panel offers place search and the layer selector.

| Layer | What you see | Source |
|---|---|---|
| **Flood outlook · MindSpore** (default) | Blue: flood-prone terrain. Yellow, orange, red: where the rain model expects water to collect. Refreshes itself. | Models 5.2 and 5.3 |
| **Rain watch** | Satellite clouds, NASA satellite-measured rain (green to red), forecast rain for 6 hours (purple), and the flood outlook on top. | JMA, NASA, Open-Meteo, MindSpore |
| **Clouds · live satellite** | Himawari-9 cloud imagery, playable over the last two hours. | JMA |
| **Wind · 72-hour forecast** | Animated particles for wind speed and direction. | Open-Meteo |
| **Precipitation · next 6 hours** | Forecast rain by province. | Open-Meteo |
| **Temperature · forecast** | 2 m air temperature by province. | Open-Meteo |
| **Pressure · forecast** | Sea-level pressure, blue lower and red higher than the rest of the country. | Open-Meteo |
| **Floods seen by satellite** (separate toggle) | Detected water from scanned tiles. Blank means *not scanned*, never "no flood". | Model 5.1 |

Other screens: **Dashboard** (rankings and scan statistics), **Satellite scenes** (Copernicus catalogue search), and **Report center** (PDF reports).

**How to use it:** pick a layer, click any spot for a place report, and open "How MindSpore works here" for a plain-language explanation of each model. You can also run the satellite model on a chosen spot with **Scan a spot with satellite radar**.

---

## 8. What we installed (technology stack)

### 8.1 Tools

| Tool | Version | Used for |
|---|---|---|
| Windows 10/11 x64 | | Development machine |
| Node.js | 22 LTS | Frontend build and dev server |
| Python | 3.12 | Backend and ML environments |
| Git and GitHub | | Version control |
| Visual Studio Code with GitHub Copilot | | Editor and AI-assisted development |

### 8.2 Machine learning (`ml/requirements.txt`)

| Package | Version | Purpose |
|---|---|---|
| **MindSpore** | 2.10.0 (CPU) | All three neural networks |
| NumPy | 1.26.4 | Array maths (pinned for MindSpore's Windows build) |
| SciPy | latest | Smoothing and resampling |
| rasterio | 1.4.3 | Reading GeoTIFF and satellite tiles |
| httpx | 0.28.1 | Downloading public datasets |
| pytest | latest | Tests |

### 8.3 Backend (`backend/requirements.txt`)

| Package | Version | Purpose |
|---|---|---|
| FastAPI | 0.115.6 | REST API |
| Uvicorn | 0.34.0 | ASGI server |
| httpx | 0.28.1 | Weather and satellite clients |
| ReportLab | 4.2.5 | PDF reports |
| DuckDB | 2.0.0 | Range-reading the field GeoParquet |
| Fiona, pyproj, Shapely | 1.10.1, 3.7.1, 2.0.7 | Geometry and parcel import |
| Pillow | 11–12 | Rendering map overlays |
| contourpy | latest | Pressure contour lines |
| psycopg | 3.2.3 | GaussDB/PostgreSQL connection |
| esdk-obs-python | 3.26.6 | Huawei OBS SDK |
| python-dotenv | 1.2.4 | Private settings |

`backend/requirements-ml.txt` adds MindSpore, NumPy, SciPy and rasterio so the backend can run the models directly.

### 8.4 Frontend (`frontend/package.json`)

| Package | Version | Purpose |
|---|---|---|
| Vue | ^3.5.13 | User interface |
| vue-router | ^4.5.0 | Pages |
| mapbox-gl | ^3.8.0 | Interactive map |
| Vite and @vitejs/plugin-vue | ^6.0.7, ^5.2.1 | Build and dev server |

---

## 9. What we built (repository guide)

```
SipatAI/
├── backend/
│   ├── app/
│   │   ├── main.py                 App entry point
│   │   ├── api/routes/             One file per resource (weather, flood_model, scan, reports, scenes ...)
│   │   ├── core/config.py          Settings from environment variables
│   │   ├── integrations/           Open-Meteo, IMERG, Himawari, Sentinel, FTW fields, ModelArts, OBS
│   │   ├── services/               Flood model, susceptibility, rain model, land mask, scanner, reports
│   │   ├── jobs/                   scan_philippines.py, remask_scans.py
│   │   ├── db/                     SQLite stores and the GaussDB session
│   │   └── schemas/                Request and response models
│   ├── tests/                      Backend tests
│   └── requirements*.txt
├── ml/
│   ├── models/                     ResNet-50 U-Net
│   ├── losses/                     Weighted focal and Dice loss
│   ├── datasets/ data/             Tile datasets, Sen1Floods11 and Planetary Computer builders
│   ├── training/                   Train and evaluate the U-Net
│   ├── susceptibility/             Terrain model: download, features, train, nationwide scoring
│   ├── rain_flood/                 Rain-aware model: dataset, train
│   ├── export/                     MindIR export
│   ├── inference/                  Tile predictor
│   └── tests/
├── frontend/
│   ├── src/components/ParcelMap.vue   Map, layers, overlays and click report
│   ├── src/views/                     Map, Dashboard, Scenes, Reports
│   ├── src/api/                       API client modules
│   └── public/data/                   Province boundaries
├── scripts/                        Parcel import and maintenance
```

**Main things we built ourselves:**

- A cloud-robust MindSpore flood segmentation pipeline with a validation-tuned decision threshold per input mode.
- A terrain susceptibility model scored nationwide into 95 map overlays.
- A rain-aware experimental flood model with real recent and forecast rainfall.
- A nationwide land-tile scanner and an optional background auto-scan.
- A province-boundary land mask so detections do not appear over the sea.
- Per-field flood assessment from open field boundaries.
- Real-data weather layers drawn per province, including NASA rain, Himawari clouds, wind and pressure contours.
- A click-anywhere place report, dashboards and PDF reports.

---

## 10. Installation and first run (Windows)

Complete steps are below. In short:

### 10.1 Prerequisites

1. Install **Node.js 22 LTS** and **Python 3.12** (tick *Add python.exe to PATH*).
2. Create a free [Mapbox](https://account.mapbox.com/) account and a **public** token restricted to your domains. Never use a secret token in the frontend.

### 10.2 Backend

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# To run the MindSpore models inside the backend as well:
.\.venv\Scripts\python.exe -m pip install -r requirements-ml.txt
$env:CORS_ALLOWED_ORIGINS = "http://localhost:5173"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Check `http://127.0.0.1:8000/health`. It should return `{"status":"ok"}`. Interactive API docs are at `/docs`.

### 10.3 Frontend

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
# Edit .env.local:
#   VITE_API_BASE_URL=http://127.0.0.1:8000
#   VITE_MAPBOX_ACCESS_TOKEN=<your public Mapbox token>
npm run dev
```

Open the **Local** address Vite prints, normally `http://localhost:5173`. Keep both terminals running.

### 10.4 Settings

Backend settings go in `backend/.env` or `backend/.env.local` (both git-ignored). See `backend/.env.example` for names. None are required to see weather and map layers.

| Variable | Purpose |
|---|---|
| `CORS_ALLOWED_ORIGINS` | Browser origins allowed to call the API |
| `SIPATAI_MODEL_CHECKPOINT` | Path to the U-Net checkpoint (default `ml/artifacts/checkpoints/sipatai-best.ckpt`) |
| `SIPATAI_AUTO_SCAN` | Set to `1` to scan tiles in the background, one at a time |
| `COPERNICUS_USERNAME`, `COPERNICUS_PASSWORD` | Only for downloading scenes to OBS |
| `OBS_*`, `MODELARTS_*`, `GAUSSDB_DSN` | Optional Huawei Cloud services |
| `OPENWEATHERMAP_API_KEY` | Optional; not needed for the main layers |

Never commit real keys. The frontend token is public by design and must be domain-restricted.

---

## 11. Training and running the models

The **trained weights, terrain caches, stored scans and the SQLite database are git-ignored** (`ml/artifacts/`, `backend/data/`). A fresh clone must recreate them, or you will see the "model not ready" state. All commands run from the repository root in the ML environment.

### 11.1 Create the ML environment

```powershell
py -3.12 -m venv ml\.venv
ml\.venv\Scripts\python.exe -m pip install -r ml\requirements.txt
```

### 11.2 Satellite flood model

```powershell
ml\.venv\Scripts\python.exe -m ml.data.sen1floods11 --output-dir ml\artifacts\sen1floods11
ml\.venv\Scripts\python.exe -m ml.training.train --manifest ml\artifacts\sen1floods11\train\manifest.csv --val-manifest ml\artifacts\sen1floods11\valid\manifest.csv --checkpoint-dir ml\artifacts\checkpoints --crop-size 128 --epochs 24 --val-every 4 --batch-size 8 --learning-rate 0.0004 --optimizer adam --class-weights 1 2 --focal-gamma 2 --dice-weight 1 --label-source "Sen1Floods11 human-labelled flood chips"
ml\.venv\Scripts\python.exe -m ml.training.evaluate --checkpoint ml\artifacts\checkpoints\sipatai-best.ckpt --manifest ml\artifacts\sen1floods11\valid\manifest.csv ml\artifacts\sen1floods11\test\manifest.csv ml\artifacts\sen1floods11\bolivia\manifest.csv --record-test
```

The training dataset hides the optical channels at random, which is what makes the model cloud-robust. To measure full and radar-only performance and pick a threshold per mode on validation data, use `ml.training.evaluate_modes`. See [ml/README.md](ml/README.md) for the full pipeline and weak-label tiles. Training used about 6 GB of RAM, and a Windows out-of-memory error stopped one run, so close other programs first.

### 11.3 Terrain and rain models

```powershell
ml\.venv\Scripts\python.exe -m ml.susceptibility.download        # one-off, about 400 MB of public terrain files
ml\.venv\Scripts\python.exe -m ml.susceptibility.national train-data
ml\.venv\Scripts\python.exe -m ml.susceptibility.train
ml\.venv\Scripts\python.exe -m ml.susceptibility.national score   # writes the 95 national overlays
ml\.venv\Scripts\python.exe -m ml.rain_flood.build_dataset        # training table: Sen1Floods11 labels + ERA5 rain
ml\.venv\Scripts\python.exe -m ml.rain_flood.train                # experimental rain model
ml\.venv\Scripts\python.exe -m ml.rain_flood.cache_features       # cache terrain features so forecasts score in seconds
```

`ml.rain_flood.build_dataset` downloads historical rain from the Open-Meteo archive, so it needs internet access and can be rate-limited.

### 11.4 Nationwide scan

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.jobs.scan_philippines --order rainfall --limit 200
```

One tile takes about a minute on a laptop CPU, and there are 13,594 land tiles. A full pass needs far stronger hardware, so **most tiles are unscanned**. Re-mask stored scans after changing the land mask with `python -m app.jobs.remask_scans`.

### 11.5 Export for Huawei ModelArts

```powershell
ml\.venv\Scripts\python.exe -m ml.export.export_model --checkpoint ml\artifacts\checkpoints\sipatai-best.ckpt --output ml\artifacts\export\sipatai --device-target CPU
```

This produces a MindIR file for deployment on ModelArts. The exporter defaults to `--device-target Ascend`. We exported only with the CPU target and have not deployed the result.

---

## 12. API reference

All routes are under `/api/v1` except `/health`. Full schemas are at `/docs` while the backend runs.

**MindSpore models** (`/model`)

| Route | Purpose |
|---|---|
| `GET /model/status` | Satellite model readiness, provenance and held-out metrics |
| `POST /model/analyze` | Run the U-Net on real Sentinel data for a 5 km tile around a point |
| `GET /model/assessments`, `/model/assessments/{id}` | Saved assessments |
| `GET /model/susceptibility/status`, `/chunks`, `/chunk/{id}.png` | Terrain model and overlays |
| `POST /model/susceptibility` | Point report combining terrain, rain model and province forecast |
| `GET /model/outlook/chunk/{id}.png`, `/context/chunk/{id}.png` | Flood outlook and context overlays |
| `GET /model/rain-flood/status`, `/chunk/{id}.png` | Rain-aware model |

**Nationwide scan** (`/scan`): `GET /scan/summary`, `/scan/overlays`, `/scan/overlay/{tile_id}.png`.

**Weather** (`/weather`): `GET /locations`, `/overview`, `/flood-screening`, `/province-forecast`, `/wind-forecast`, `/pressure-isobars`, `/imerg/latest`, `/imerg/image.png`, `/field/{variable}.png`, `/himawari/tile-frames`, `/himawari/tiles/{time}/{z}/{x}/{y}.png`; `POST /weather/current`.

**Scenes** (`/scenes`): `POST /search` (Copernicus catalogue), `POST /download` (copies a product to OBS; needs credentials).

**Reports** (`/reports`): `POST /satellite-assessment/{id}`, `POST /flood-screening`, `POST /` (database report; needs GaussDB).

**Other:** `GET /health`, `GET /barangay/summary`, `GET /damage-map`, `GET /parcels/map`, `POST /analyze` (needs a ModelArts endpoint).

Database-backed routes fail closed with an explicit message when the database is not configured. They never return invented data.

---

## 13. Huawei Cloud integration status

We have **not** used Huawei Cloud in practice. We did not receive Huawei Cloud credits, so everything runs locally.

| Service | What we built | Verified live? |
|---|---|---|
| **ModelArts** | HTTP client for an inference endpoint (`/api/v1/analyze`), and a MindIR exporter. | No. No endpoint is deployed. |
| **OBS** | Bucket metadata check, artifact upload and Sentinel product copy, using the official Python SDK. | No. No bucket is configured. |
| **GaussDB with PostGIS** | Migrations, spatial queries, a parcel importer and report services. | No. No instance is configured. |
| **Ascend** | Not used. | No. |

The plan for a funded deployment is: export the trained U-Net to MindIR and host it on ModelArts (set `MODELARTS_INFERENCE_URL` and `MODELARTS_INFERENCE_TOKEN`), keep Sentinel scenes and processed artifacts in a private OBS bucket (`OBS_ENDPOINT`, `OBS_BUCKET`, and an ECS agency or backend-only access keys), and store spatial results in a PostGIS-enabled GaussDB instance (`GAUSSDB_DSN`). Credentials stay in backend environment variables and are never sent to the browser. Setting these variables is not proof that a service is reachable, so each one must be tested against the live service before we call it working.

---

## 14. Limitations

We want to be clear about what SipatAI cannot do. **Please read this section before using or judging the project.**

### 14.1 Resources

- **No Huawei Cloud credits.** All training and inference ran on a laptop CPU. We could not use ModelArts, Ascend, OBS or GaussDB, so cloud scale, speed and cost are untested.
- **Limited memory and time.** One training run stopped at an out-of-memory error. The nationwide scan processes one tile per minute, so only a small share of the 13,594 tiles has been scanned.
- **External services.** We depend on free public APIs. Open-Meteo, NASA GIBS, Planetary Computer and Mapbox sometimes return errors or rate limits, which can leave layers blank or slow. Open-Meteo's free tier is for non-commercial use.

### 14.2 Model accuracy and validity

- **No validation against real Philippine flood records.** The satellite and rain models were trained and tested on flood labels from other countries (Sen1Floods11 events). The terrain model uses Philippine regions, but its label is historical water occurrence from JRC, not mapped flood events. We have not compared any output to PAGASA, NDRRMC, PhilSA or local flood records, so real-world accuracy in the Philippines is unknown.
- **Detected water is not always flooding.** The satellite model finds water. Irrigated paddies, fishponds, wetlands and radar shadows can be misclassified. We subtract permanent water but this is imperfect.
- **The land mask is approximate.** We mask to Philippine land using province outlines with a buffer of about 200 m, so some coastal water can remain. Re-masked stored scans compute their area from the visible pixels, which can differ slightly from the model's own count.
- **The terrain model shows history, not forecasts.** Its label is where water has collected before, and it includes paddies and wetlands. It has no flood depth.
- **The rain model is experimental and weak at our display thresholds.** Held-out AUC is 0.86, but recall at the displayed thresholds is only 0.08, 0.04 and 0.01, so it **misses most flooded cells**. Its scores are not probabilities. It was trained on rain that ended at a satellite pass, but we feed it the past 48 hours plus the next 24 hours of forecast, so the windows differ. Its training event dates were entered by hand and not independently verified. Missing archive rain may have been treated as zero. Resampling labels to 90 m cells adds error.
- **Silence is not safety.** When the Flood outlook draws nothing, it only means the experimental model showed no signal under our display rules. It does not mean flooding is impossible. The click report therefore says "No model signal here", shows the rain model's number as a score out of 100 (not a probability), and repeats that the models can miss real flooding.
- **What-if scenarios are hypothetical.** The 50, 100 and 200 mm scenarios exist only to let people see how the model responds. They are labelled and are not forecasts.
- **The watch level is a rule, not a model.** Rain band × terrain class thresholds are chosen by us.
- **Weather layers do not feed any model.** Wind, temperature and pressure are displayed only. Open-Meteo provides model forecasts, not PAGASA observations, and the weather grids are interpolated between provinces.
- **Rain watch timing.** NASA IMERG rain is published about 4–6 hours late, so it is not live.
- **Cloud cover.** Without clear optical imagery the satellite model uses radar only, and its IoU drops from 0.76 to 0.61.
- **Satellite revisit.** A scan uses the newest Sentinel-1 pass, which can be up to about two days old. A flood can rise and fall between passes.

### 14.3 Data coverage

- **Blank means not scanned.** Satellite detection layers are blank where no scan has run.
- **No authorised farm-parcel dataset.** We use open Fields of The World polygons, which are satellite-detected field units, **not legal parcels or ownership records**. Their Light, Moderate and Severe classes (flooded share 10–30%, 30–60%, 60%+) are a display scale we defined, not an agronomic damage grade. We computed no crop value or loss estimate.
- **No typhoon track or official warning feed.** We cannot tell whether rain is caused by a typhoon.
- **No SNAP or GDAL preprocessing pipeline.** We read ready-made radiometrically terrain-corrected Sentinel-1 and Sentinel-2 L2A products from Planetary Computer instead. Domain shifts are possible versus the Sen1Floods11 training products.

### 14.4 Software

- **Windows and CPU only.** We tested on Windows x64 with CPU MindSpore 2.10.0 and NumPy 1.26.4. Other platforms, GPUs and Ascend are untested.
- **Interface testing is limited.** Automated tests cover the backend and ML code. We tested the map by hand. Our automated browser could not load the Mapbox basemap, so some map interactions were not verified automatically.
- **Mapbox requirements.** The map needs a Mapbox token and internet access.
- **No authentication, rate limiting or production hardening.** The API is intended for local use or a controlled demo.

---

## 15. Responsible use, privacy and security

- **Not an official warning.** Do not use SipatAI to decide evacuation, insurance, loans or any safety-critical action.
- **No personal data.** We do not collect, store or sell personal information, and the place report keeps nothing about the visitor. Saved scans contain numbers and images only. We do not use landowner data.
- **Secrets stay private.** Keys and passwords live in git-ignored `.env` files on the backend. The Mapbox token in the frontend is public and domain-restricted. An OpenWeatherMap key was once shared in chat and **must stay rotated** and never be reused.
- **Attribution and licences.** We credit our data sources and respect their terms (see [section 18](#18-data-licences-and-acknowledgements)).
- **Honest reporting.** The interface says when data is unavailable, and it labels experimental and hypothetical content.

---

## 16. Testing

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q          # 83 tests

cd ..
ml\.venv\Scripts\python.exe -m pytest ml\tests -q  # 8 tests

cd frontend
npm run build
```

At the time of writing, all 83 backend tests and 8 ML tests pass and the frontend builds. The tests check API behaviour, fail-closed handling, the models' shapes and losses, and data utilities. **They do not prove forecast accuracy.**

---

## 17. Roadmap

1. **Validate on Philippine floods:** compare detections and outlooks against PAGASA, NDRRMC, PhilSA and local records for past typhoons.
2. **Retrain with Philippine labels** and add Philippine flood events to the rain model.
3. **Use Huawei Cloud:** train on ModelArts, run on Ascend, store imagery in OBS, and store spatial data in GaussDB with PostGIS.
4. **Complete the nationwide scan** on stronger hardware, with scheduled passes after each Sentinel-1 acquisition.
5. **Calibrate** the rain model so its scores are true probabilities, and replace the display heuristic with a validated one.
6. **Authorised parcel data** from DA, DAR or LMB, with severity and crop-value rules approved by the responsible agency.
7. **Add weather inputs to the models** (wind, pressure and other fields) once a flood-labelled weather archive is available.
8. **Typhoon track** integration from an official source.
9. **Local-language interface** (Filipino and Ilocano) and a phone-friendly layout.
10. **User feedback and a pilot** with a municipal agriculture office, to test real demand before claiming any commercial value.

---

## 18. Data licences and acknowledgements

SipatAI would not exist without these open resources. Licences are those stated by the providers. Please check the originals before reusing any data.

| Resource | Licence or terms |
|---|---|
| Sentinel-1 and Sentinel-2 (Copernicus, ESA) | Free, full and open Copernicus data policy |
| Microsoft Planetary Computer | Public STAC catalogue; each dataset keeps its own licence |
| Sen1Floods11 (Cloud to Street) | Check the dataset repository for terms |
| Copernicus DEM GLO-90 | Copernicus data terms |
| JRC Global Surface Water | Check the JRC terms; credit the European Commission JRC |
| ESA WorldCover 2021 | CC BY 4.0 |
| Fields of The World, Philippines | CC BY 4.0 |
| geoBoundaries ADM2 | CC BY 3.0 IGO |
| SimpleMaps regions | CC BY 4.0 |
| Open-Meteo forecast and archive | Free for non-commercial use; contains modified Copernicus Climate Change Service (ERA5) information |
| NASA GPM IMERG via GIBS | NASA open data |
| JMA Himawari-9 | Japan Meteorological Agency terms |
| Mapbox Streets | Mapbox terms of service |
| AWS Terrain Tiles (Mapzen) | See the Terrain Tiles attribution |

**Software:** MindSpore, FastAPI, Vue, Vite, Mapbox GL JS, DuckDB, rasterio, Shapely, Fiona, ReportLab and the other packages in [section 8](#8-what-we-installed-technology-stack) keep their own open-source licences.

**Our code:** We have not yet chosen a licence for our own code. Until then, all rights are reserved by the authors, with the usage rights the Huawei ICT Competition rules grant to the organiser.

We thank **Mariano Marcos State University**, our instructor **Renante Burgos**, the **Huawei ICT Competition** organisers and **Huawei ICT Academy** for the opportunity, and the open-data communities named above.

---

## 19. Further documents

| Document | What it covers |
|---|---|
| [ml/README.md](ml/README.md) | The full MindSpore pipeline and metrics |

We keep internal team notes outside this repository.

---

*Disclaimer: SipatAI is an academic research prototype. It is provided as is, with no warranty. It is not endorsed by PAGASA, NDRRMC, Huawei, or any data provider named above.*
