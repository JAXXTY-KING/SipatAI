# SipatAI Project Handover

**Status date:** 2026-10-04

## Project Goal

SipatAI is intended to assess agricultural flood damage across the Philippines. The planned workflow is:

1. Find Sentinel-1 and Sentinel-2 scenes for an area and event period.
2. Download and preprocess satellite data into aligned model inputs.
3. Run the trained MindSpore flood-segmentation model through Huawei ModelArts.
4. Intersect flood polygons with authorized farm parcels in Huawei GaussDB/PostGIS.
5. Show verified assessment results in the Vue/Mapbox application and generate reports.
6. Store source and processed files in Huawei OBS.

The system must not replace unavailable operational data with fabricated assessment results. There is no end-user parcel upload feature; parcel data is managed by the backend.

## Current State

### Implemented and checked

- Vue 3/Vite application with dashboard, flood map, report center, and satellite-scene search screens.
- FastAPI routes: `GET /health`, `GET /api/v1/barangay/summary`, `GET /api/v1/damage-map`, `POST /api/v1/analyze`, `POST /api/v1/scenes/search`, and `POST /api/v1/reports`.
- Copernicus Data Space STAC search for Sentinel-1 GRD and Sentinel-2 L2A. Searches use a Philippines bounding box, selected dates, and optional Sentinel-2 cloud-cover filtering. Live searches returned real catalog results.
- MindSpore 2.10.0 ResNet-50 U-Net implementation, shared model configuration, weighted focal-Dice loss, tiled dataset reader, training entry point, and MindIR exporter. A CPU forward pass, a gradient/training step, and a 512x512 dataset batch were tested.
- GaussDB/PostGIS migration files, connection handling, spatial queries, and database-backed assessment/report services.
- Huawei ModelArts HTTP client and Huawei OBS SDK integration. OBS supports a bucket metadata check and backend artifact upload. Credentials are read only by the backend.
- The UI and APIs fail closed: without a completed GaussDB assessment, summary/map/report requests return an unavailable response rather than sample results.
- The Geoportal Map Viewer was checked. Its LMB "Parcel data" layer metadata describes cadastral polygons in selected Metro Manila areas. The August 2026 inventory marks download as conditional. It is not verified as nationwide farm-parcel coverage.

### Not yet operational

- No Huawei OBS bucket, ModelArts inference endpoint, or GaussDB/PostGIS instance is configured.
- There is no authorized nationwide farm-parcel dataset loaded into the database.
- Sentinel scene search is implemented, but authenticated product download to OBS is not yet implemented.
- SNAP/GDAL preprocessing is not implemented end to end.
- The MindSpore model has no trained weights. Training requires labeled tiles and approved hyperparameters.
- ModelArts has no deployed MindIR model. The `/api/v1/analyze` payload must be matched to the deployed model's actual request/response contract.
- Crop valuation rules and official damage-severity thresholds have not been supplied. Damage amounts and severity must not be invented.

## External Data Findings

### Sentinel imagery

The official Copernicus Data Space Ecosystem provides Sentinel-1 and Sentinel-2 catalog search. Scene search is working through the official STAC API. Product downloads require a Copernicus account and an access token. Do not put the account password or access token in source code or chat.

- [Copernicus Data Space](https://dataspace.copernicus.eu/)
- [Official Sentinel collection catalog](https://dataspace.copernicus.eu/data-collections/copernicus-sentinel-missions)
- [Official STAC documentation](https://documentation.dataspace.copernicus.eu/APIs/STAC.html)
- [Official product-download/token documentation](https://documentation.dataspace.copernicus.eu/APIs/OData.html)

### Farm parcels

The Geoportal inventory lists LMB "Parcel data" as conditionally downloadable. The layer's metadata describes selected Metro Manila areas, not the whole Philippines. Its exact downloadable extent and permitted use still need confirmation from the Land Management Bureau (LMB). The DA RSBSA site requires login and does not expose an open national parcel download in its public pages.

Request authorized farm-parcel polygons from LMB, the Department of Agriculture, or relevant local governments. Ask for coverage, CRS, file format, field definitions, update date, permitted use, and a version without landowner personal data. Do not treat land-cover maps as cadastral parcel boundaries.

## Ordered Work Plan

1. **Resolve parcel data access.** Request nationwide agricultural/cadastral parcel coverage and terms from LMB/DA. If no national source exists, document geographic gaps and establish authorized government data-sharing agreements. Do not claim whole-country parcel-level coverage until verified.
2. **Provision Huawei resources.** Select the Huawei region and create/obtain an OBS bucket, a PostGIS-enabled GaussDB instance, and a ModelArts workspace/online inference endpoint. For ECS deployments, use a least-privilege agency for OBS rather than permanent access keys where available.
3. **Configure secrets privately.** Set backend environment variables on the development machine/ECS. Keep real values out of `.env.example`, Git, frontend `VITE_` variables, screenshots, and chat. The frontend Mapbox token is public and should be domain-restricted.
4. **Implement Sentinel download to OBS.** Use the Copernicus access token server-side, select products by validated AOI and acquisition time, download only required scenes, record product IDs/checksums, and store source files privately in OBS. Never download all national scenes indiscriminately.
5. **Implement SNAP/GDAL preprocessing.** Preserve the required order: SAR calibration, noise removal, geo-referencing/terrain correction, raster alignment, then GeoTIFF output. Derive optical channels only from suitable Sentinel-2 scenes. Record source and target CRS explicitly; do not reproject silently.
6. **Produce aligned labeled training tiles.** The current model contract is 512x512 pixels, channel order `VV, VH, NDVI, NDWI, RED, NIR`, and classes `not_flooded, flooded`. Confirm these against the strategy/training data before creating the production dataset. Obtain flood labels and define class weights, focal gamma, Dice weight, optimizer, learning rate, and evaluation criteria with the ML lead.
7. **Train and evaluate MindSpore.** Train with the repository's MindSpore Dataset and U-Net code on the selected compatible ModelArts hardware. Evaluate against held-out labeled events and document model version/metrics before deployment.
8. **Export and deploy MindIR.** Export the trained checkpoint, deploy it through ModelArts, confirm its input/output JSON schema, and configure the backend endpoint URL/token. Exercise `/api/v1/analyze` with a real prepared tile.
9. **Load parcels and compute damage in PostGIS.** Import only authorized parcel data through a controlled backend ingestion job. Preserve source CRS metadata. Run spatial intersection and geodesic hectare calculations in PostGIS. Apply severity and crop-valuation rules only after the responsible agency approves those rules.
10. **Verify an end-to-end event.** Search/download a real event's scenes, preprocess, run ModelArts, intersect in PostGIS, inspect map output, and generate a report. Verify data provenance, units, CRS, coverage gaps, and mobile/desktop behavior before calling it operational.

## Huawei Configuration

See [huawei_cloud.md](huawei_cloud.md) for ModelArts, OBS, and GaussDB variable names and security guidance. See [gaussdb_postgis.md](gaussdb_postgis.md) for PostGIS prerequisites and the migration command. These settings are placeholders until the resources actually exist.

The backend uses these private settings:

- `MODELARTS_INFERENCE_URL` and `MODELARTS_INFERENCE_TOKEN`
- `OBS_ENDPOINT`, `OBS_BUCKET`, and either an ECS role or backend-only OBS credentials
- `GAUSSDB_DSN`
- `CORS_ALLOWED_ORIGINS` for approved frontend origins

Environment settings alone do not prove network connectivity. OBS bucket access and PostGIS availability are checked with read-only requests when configured. ModelArts configuration is not considered verified until an inference request succeeds.

## Local Development

- Windows setup: [setup_windows.md](setup_windows.md)
- Frontend: `frontend/`, Node.js 22, Vite
- Backend: `backend/`, Python 3.12 virtual environment
- ML: `ml/`, separate Python 3.12 environment with MindSpore 2.10.0 and NumPy 1.26.4
- Local URLs when the development servers are running: `http://127.0.0.1:5173/` and `http://127.0.0.1:8000/docs`

The backend Psycopg package imports and runs in `backend/.venv`; Pylance has previously shown a stale unresolved-import diagnostic for Psycopg. Runtime checks passed. The MindSpore CPU smoke test used a small input; full-size training and Huawei Ascend execution still require validation on the deployment runtime.

## First Task for the Next Work Session

Continue the real Sentinel pipeline by implementing authenticated Copernicus product download into OBS. Before using download credentials, keep the Copernicus token in the backend environment only. In parallel, request the nationwide parcel-data coverage and access terms from LMB/DA.