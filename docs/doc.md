# SipatAI Project Handover

**Status date:** 2026-10-10

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
- FastAPI routes: `GET /health`, `GET /api/v1/barangay/summary`, `GET /api/v1/damage-map`, `GET /api/v1/parcels/map`, `POST /api/v1/analyze`, `POST /api/v1/scenes/search`, and `POST /api/v1/reports`.
- Copernicus Data Space STAC search for Sentinel-1 GRD and Sentinel-2 L2A. Searches use a Philippines bounding box, selected dates, and optional Sentinel-2 cloud-cover filtering. Live searches returned real catalog results.
- MindSpore 2.10.0 ResNet-50 U-Net implementation, shared model configuration, weighted focal-Dice loss, tiled dataset reader, training entry point, and MindIR exporter. A CPU forward pass, a gradient/training step, and a 512x512 dataset batch were tested.
- GaussDB/PostGIS migration files, connection handling, spatial queries, and database-backed assessment/report services.
- A source-agnostic command-line parcel workflow can inspect and validate GeoJSON, Shapefile, and GeoPackage files, then import authorized data into `farm_parcels` with explicit CRS/field mapping, area-filtered chunks, required source attribution, duplicate protection, transactional writes, dry-run, and read-only verification. It has not yet been tested against an authorized parcel dataset or a live Huawei GaussDB instance.
- The map shows SimpleMaps' 17 first-level administrative regions as an attributed, optional context layer only; these boundaries are not farm parcels and are not used in assessments.
- The map also has a separately attributed PhilSA historical Sentinel-1 observed-flood reference (2025-07-06, CC BY 4.0). The full 61,774-feature source footprint is rasterized for map display; 15,705 invalid source geometries were repaired before rasterization. The source warns it was not validated against ground truth. It is not a SipatAI assessment, farm parcel, or damage statistic.
- Huawei ModelArts HTTP client and Huawei OBS SDK integration. OBS supports a bucket metadata check and backend artifact upload. Credentials are read only by the backend.
- The UI and APIs fail closed: without a completed GaussDB assessment, summary/map/report requests return an unavailable response rather than sample results.
- The Mapbox background style is Mapbox Streets (`streets-v12`) for clearer roads, water, and land colors. This changes presentation only, not data or analysis.
- The Geoportal Map Viewer was checked. Its LMB "Parcel data" layer metadata describes selected Metro Manila cadastral polygons. The catalogue gives `download: null`; its download form did not offer an export during review, and direct WMS/WFS requests timed out. It is not verified as downloadable or as nationwide farm-parcel coverage.

### Not yet operational

- No Huawei OBS bucket, ModelArts inference endpoint, or GaussDB/PostGIS instance is configured.
- There is no authorized nationwide farm-parcel dataset loaded into the database.
- No parcel dataset is currently cleared for import into this project. Geoportal/LMB is a verified cadastral-data lead but its available footprint is selected Metro Manila, not the Ilocos Norte study area; the portal has not provided an extract. An ArcGIS Online service for Midori Highlands in Clark returns subdivision polygons, but its license field is blank and its sample attributes label the feature commercial, not agricultural; public query access is not a reuse license. PHIVOLCS metadata remains inaccessible, the public NAMRIA REST inventory did not expose a parcel layer, and SimpleMaps provides administrative regions rather than lots.
- Sentinel scene search is implemented. `POST /api/v1/scenes/download` streams a product from Copernicus (using `COPERNICUS_USERNAME`/`COPERNICUS_PASSWORD`) into OBS under `raw/<collection>/`. It is unit-tested for validation and fail-closed behavior only; it has not been run against live Copernicus or OBS.
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

The best verified official parcel-data lead is LMB's Geoportal layer, but it does not meet the project's area, use, and download requirements yet:

- [Geoportal layer record/configuration](https://geoportal.gov.ph/layers/fetchlayerconfig/denr_parcel_data/ParcelData) identifies the publisher as the Land Management Bureau (LMB) and the layer as `denr_parcel_data` / “Parcel data”.
- Its embedded FGDC metadata describes cadastral parcel polygons in **selected Metro Manila areas**, with a stated 57,150 polygon features and a bounding box of 120.85786–121.100809°E, 14.617931–14.798865°N. Listed fields include `ogc_fid`, `lotnumber`, `shape_length`, and `shape_area`; no crop or farm-use field is listed.
- The catalogue advertises a WMS-backed map layer but reports `download: null`. Geoportal's Download form did not offer this layer in the checked session. Direct WMS/WFS feature requests to `https://geoserver.geoportal.gov.ph/geoserver/geoportal/` timed out, so a working vector-download URL and actual feature query were not verified. The metadata's “None” access/use-constraint text is not a separate open-data license grant. Request an extract and written reuse terms from LMB before importing or redistributing it.
- The geographic footprint does not include Bacarra/Ilocos Norte, and the service is cadastral rather than confirmed agricultural inventory. It might support a separately described cadastral visualization after access approval, but it must not be labelled farm parcels or used for crop-damage calculations without agricultural attributes and authorization.

A second, technically queryable ArcGIS item is [Midori Highlands Parcels](https://services7.arcgis.com/yiuFazTjHE8F5gzQ/arcgis/rest/services/Midori_Highlands_Parcels/FeatureServer/1), published by a non-government ArcGIS account ([item metadata](https://www.arcgis.com/sharing/rest/content/items/0fe446101a264d878dffb5a57c2de963?f=pjson)). For example, the [GeoJSON query](https://services7.arcgis.com/yiuFazTjHE8F5gzQ/arcgis/rest/services/Midori_Highlands_Parcels/FeatureServer/1/query?where=1%3D1&outFields=OBJECTID%2Cname%2Carea_sqm%2Carea_ha%2Cland_use&returnGeometry=true&outSR=4326&resultRecordCount=2&f=geojson) returns polygon geometry and `OBJECTID`, `name`, `area_sqm`, `area_ha`, and `land_use`. Its published extent is a small subdivision in Clark, Pampanga; a returned example is “Aqua Planet”, `land_use: Commercial`. The ArcGIS item has blank `licenseInfo` and `accessInformation`. It is not an agricultural dataset, is not in the target municipality, and has no stated permission for copying or rehosting; do not import it without the publisher's written permission.

The PHIVOLCS HAS_PARCELS MapServer/FeatureServer and `testparcel1` FeatureServer endpoints returned HTML/error responses instead of usable service metadata in checks. NAMRIA's public REST directory lists map services, but no parcel layer was found in its public listing; its `Database` service folder requires a token. NAMRIA's public downloads page did not identify parcel geometry. SimpleMaps is licensed CC BY 4.0, but its 17 first-level administrative-region polygons are not individual lots. The DA RSBSA public site did not expose an open national parcel download.

**Conclusion:** there is no verified, licensed parcel extract ready to import. Nationwide, Luzon, Ilocos Norte, and Bacarra agricultural-parcel coverage remain unverified. Do not use a commercial subdivision, administrative boundary, land-cover polygon, or flood extent as a substitute.

**Next request:** ask LMB's Land Surveys Management Information Section for a small Bacarra/Ilocos Norte sample if available, otherwise the selected Metro Manila parcel layer only for a clearly labelled cadastral demo. Request stable IDs, CRS, field dictionary, current extent, an export/service endpoint, and written terms that explicitly allow local storage in SipatAI's PostGIS database, analysis, map display, and any presentation/republication. For actual farm impact analysis, ask the DA, DAR, and Bacarra/Municipal Agriculture Office for an authorized farm-parcel dataset without unnecessary landowner personal information. Do not use the LMB item or ArcGIS sample until permissions and access are confirmed.

Suggested request text:

> **Subject: Request for authorized parcel polygon sample for SipatAI**
>
> Dear Land Management Bureau,
>
> Our student team is developing SipatAI, a flood-exposure research prototype. We found the Geoportal “Parcel data” layer attributed to LMB and its metadata describes selected Metro Manila coverage. Could you advise whether an authorized parcel polygon extract is available for Bacarra or elsewhere in Ilocos Norte? If not, may we request a small sample from the existing Metro Manila layer for a clearly attributed, non-commercial demonstration?
>
> Please provide the geographic coverage, CRS, stable parcel-ID field and data dictionary, update date, and a vector download or query procedure. Please state in writing whether we may store the sample in our project PostGIS database, analyze it, display it in a student presentation, and redistribute derived or source geometries. We do not need owner names or other personal information.
>
> Sincerely, SipatAI project team

The command-line workflow is documented in [gaussdb_postgis.md](gaussdb_postgis.md). Request authorized farm-parcel polygons from LMB, DA, DAR, or relevant local governments. Ask for coverage, CRS, file format, stable field identifiers, update date, permitted use, and a version without landowner personal data. Do not treat land-cover or administrative maps as cadastral parcel boundaries.

## Ordered Work Plan

1. **Resolve parcel data access.** Request nationwide agricultural/cadastral parcel coverage and terms from LMB/DA. If no national source exists, document geographic gaps and establish authorized government data-sharing agreements. Do not claim whole-country parcel-level coverage until verified.
2. **Provision Huawei resources.** Select the Huawei region and create/obtain an OBS bucket, a PostGIS-enabled GaussDB instance, and a ModelArts workspace/online inference endpoint. For ECS deployments, use a least-privilege agency for OBS rather than permanent access keys where available.
3. **Configure secrets privately.** Set backend environment variables on the development machine/ECS. Keep real values out of `.env.example`, Git, frontend `VITE_` variables, screenshots, and chat. The frontend Mapbox token is public and should be domain-restricted.
4. **Implement Sentinel download to OBS.** Use the Copernicus access token server-side, select products by validated AOI and acquisition time, download only required scenes, record product IDs/checksums, and store source files privately in OBS. Never download all national scenes indiscriminately.
5. **Implement SNAP/GDAL preprocessing.** Preserve the required order: SAR calibration, noise removal, geo-referencing/terrain correction, raster alignment, then GeoTIFF output. Derive optical channels only from suitable Sentinel-2 scenes. Record source and target CRS explicitly; do not reproject silently.
6. **Produce aligned labeled training tiles.** The current model contract is 512x512 pixels, channel order `VV, VH, NDVI, NDWI, RED, NIR`, and classes `not_flooded, flooded`. Confirm these against the strategy/training data before creating the production dataset. Obtain flood labels and define class weights, focal gamma, Dice weight, optimizer, learning rate, and evaluation criteria with the ML lead.
7. **Train and evaluate MindSpore.** Train with the repository's MindSpore Dataset and U-Net code on the selected compatible ModelArts hardware. Evaluate against held-out labeled events and document model version/metrics before deployment.
8. **Export and deploy MindIR.** Export the trained checkpoint, deploy it through ModelArts, confirm its input/output JSON schema, and configure the backend endpoint URL/token. Exercise `/api/v1/analyze` with a real prepared tile.
9. **Load parcels and compute damage in PostGIS.** Import only authorized parcel data through `python -m scripts.import_parcels` as documented in [gaussdb_postgis.md](gaussdb_postgis.md). Verify coverage, SRID, geometry validity, and duplicate IDs. The existing `compute_parcel_damage()` query remains unconnected to the assessment lifecycle; wire it only after real flood polygons are produced. Apply severity and crop-valuation rules only after the responsible agency approves those rules.
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

Get a small, authorized parcel dataset and its data dictionary from LMB, DA, DAR, or a local government. Inspect and validate its real CRS, fields, stable identifiers, geometry, and coverage with the documented parcel workflow, then run a database dry-run and load it into a provisioned PostGIS-compatible GaussDB instance. Do not move on to authenticated Sentinel downloads until parcel import and verification have been demonstrated with authorized data.

## Consolidated Change History

This section records the work added during the SipatAI parcel-data and demonstration work, in order. It is a project handover summary, not a claim that every feature in the repository originated in this work.

1. **Reviewed the existing spatial design and data sources.** Confirmed the existing `farm_parcels`, flood polygon, assessment-run, and parcel-damage PostGIS design; examined assessment, damage-map, migration, route, setup, and project documentation. Confirmed that the reviewed NAMRIA, PHIVOLCS, SimpleMaps, and Geoportal sources did not initially establish an authorized farm-parcel download.
2. **Repaired and extended the parcel database workflow.** Fixed the missing comma in the fresh-install spatial migration. Added the additive source-attribution migration. Added a controlled GeoJSON/Shapefile/GeoPackage CLI to inspect, validate, explicitly transform CRS, filter by a selected study area, require stable provider IDs and attribution, perform dry-runs and transactional/idempotent imports, and verify stored data. It never fabricates IDs, crop values, or boundaries. Existing migration history is not reset or rewritten for a database that already recorded a migration.
3. **Connected stored parcels to the application.** Added a viewport-bounded `GET /api/v1/parcels/map` endpoint and a Mapbox parcel layer in `/flood-map`, with source/attribute popups, layer controls, and explicit API/database-unavailable messages. Parcel display depends on authorized data being imported and GaussDB/PostGIS being configured.
4. **Added an administrative reference layer.** Bundled SimpleMaps' 17 first-level region polygons under CC BY 4.0. They are identified as administrative regions, not parcels, and are not used in impact calculations.
5. **Added a historical flood reference for a non-fabricated map demonstration.** Bundled an attributed, transparent raster made from the Philippine Space Agency's 2025-07-06 Sentinel-1 flood-extent Shapefile distributed through HDX under CC BY 4.0. The source contains 61,774 polygon features, covers only its supplied extent (about 119.86–122.52°E, 11.83–19.54°N), and warns it was not validated against ground truth; 15,705 invalid source geometries were repaired during raster preparation. The UI calls this a historical observed-flood reference, not a SipatAI prediction, assessment, or parcel layer.
6. **Improved map presentation and documentation.** Switched the Mapbox basemap from the pale Light style to Streets; retained separate overlays, legends, source links, and no-data labels. Added automated checks for importer behavior, API behavior, and the raster's extent/attribution/caveat.

**Verification status:** the recorded local checks include 19 backend unit tests, Python compile/dependency checks, PostGIS SQL parsing, and successful frontend production builds. The static PhilSA raster was served locally and its asset assertions passed. A local API health check passed, but parcel and assessment routes returned 503 because `GAUSSDB_DSN` is not configured. No real parcel has been imported; no live PostGIS parcel response or end-to-end SipatAI flood assessment has been verified.