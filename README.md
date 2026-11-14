# SipatAI

SipatAI is an agricultural flood-assessment system using Sentinel imagery, MindSpore, Huawei ModelArts, GaussDB/PostGIS, FastAPI, and Vue with Mapbox.

The application does not seed or serve synthetic assessment records. Database-based agricultural metrics, completed-assessment map overlays, and assessment PDFs require a real completed database assessment; unavailable services return explicit unavailable states. The dashboard and report center also show separate, clearly labeled rainfall-screening data that does not claim farm damage.

Agricultural parcel boundaries are system data, not an end-user upload task. A controlled command-line importer now supports inspecting, validating, and loading authorized GeoJSON, Shapefile, and GeoPackage datasets into GaussDB/PostGIS. The workflow has not yet been verified against an authorized farm-parcel dataset or a live Huawei database. Sentinel preprocessing and flood inference are still not connected end to end.

The map uses Mapbox Streets and a single weather-type selector to switch between prototype rainfall/elevation screening, recent JMA Himawari-9 cloud imagery, animated 72-hour Open-Meteo wind forecasts, and color-coded Open-Meteo temperature, precipitation, and pressure forecast grids. These forecast overlays do not require an OpenWeatherMap API key. Only the selected weather visualization is shown; farm parcels, completed assessments, and administrative boundaries remain optional reference layers. Unvalidated historical flood imagery and duplicate city-observation markers are not shown on the map. The screening and weather visualizations are not a PAGASA feed, official warning, flood probability, or flood boundary. Consult PAGASA for official advisories.

The map explorer is the landing page. Search for a Philippine place to center the map and see current weather, or select a point on the map and check its weather. Use **Map layers → Weather type** to switch the map between rainfall screening, satellite clouds, wind, temperature, precipitation, and pressure. Temperature and pressure show the first forecast hour; precipitation shows the next six-hour total. Farm/reference layers and source notes are grouped separately. The assessment dashboard remains available from the navigation and ranks the five highest forecast-rainfall grid cells, with links that focus each approximate cell center on the map. These are model grid points, not named communities, farms, or confirmed flood locations.

## Project layout

- `frontend/`: Vue 3 application deployed as a Vite site.
- `backend/`: FastAPI application and report service.
- `ml/`, `preprocessing/`, `deploy/`, and `docs/`: architecture configuration and implementation notes.
- `docs/setup_windows.md`: Windows prerequisites and first-run instructions.

## Prerequisites

Install Node.js 22 LTS and Python 3.12 from the official links in `docs/setup_windows.md`. MindSpore 2.10.0 and NumPy 1.26.4 are listed separately for the ML environment in `ml/requirements.txt`. To run the MindSpore model inside the backend, install `backend/requirements-ml.txt` into the backend environment and see [ml/README.md](ml/README.md) for the training pipeline.

## Run locally

Follow the exact Windows steps in `docs/setup_windows.md`. The frontend runs separately from the backend. Add a Mapbox public access token to `frontend/.env.local` to enable the interactive map; the dashboard and API can be explored without one.

## API

- `GET /health`
- `GET /api/v1/barangay/summary`
- `GET /api/v1/damage-map`
- `GET /api/v1/parcels/map?west=<longitude>&south=<latitude>&east=<longitude>&north=<latitude>` (imported parcels within the current map viewport)
- `POST /api/v1/analyze` (requires a configured ModelArts endpoint)
- `GET /api/v1/model/status` (local MindSpore model readiness, provenance and held-out validation metrics)
- `POST /api/v1/model/analyze` (runs the local MindSpore ResNet-50 U-Net on real Sentinel-1/2 data for a 5 km tile around `latitude`/`longitude`, optional `date`; returns a map overlay and flooded area; requires `backend/requirements-ml.txt` and a trained checkpoint)
- `POST /api/v1/scenes/search` (Copernicus Data Space Sentinel catalogue)
- `POST /api/v1/scenes/download` (copies a Sentinel product to OBS; requires Copernicus and OBS credentials)
- `GET /api/v1/weather/locations?q=<Philippine place name>` (Open-Meteo geocoding; no provider key required)
- `GET /api/v1/weather/overview` (live observations at reference Philippine cities, cached 10 minutes; API context, not displayed as duplicate map markers)
- `GET /api/v1/weather/flood-screening` (coarse nationwide 72-hour rainfall and low-elevation screening; cached 1 hour, retried on provider throttling, and the last good forecast is served if the provider is briefly unavailable; not a typhoon track or verified flood forecast)
- `GET /api/v1/weather/wind-forecast` (coarse regional hourly 10 m wind speed/direction for 72 hours, same caching as above; Open-Meteo model output, not a PAGASA live feed)
- `GET /api/v1/weather/himawari/tile-frames` (latest 12 JMA full-disk observation times, oldest first, for cloud playback)
- `GET /api/v1/weather/himawari/tiles/{time_code}/{z}/{x}/{y}.png` (transparent cloud-only tiles derived from JMA Himawari-9 infrared imagery, zoom 3-5; cached 30 minutes)
- `GET /api/v1/weather/himawari/frames?band=<b03|b13|cve|ngt|dms|arm>` (older single-image endpoint: latest 12 JMA frame timestamps)
- `GET /api/v1/weather/himawari/latest.jpg?band=<b03|b13|cve|ngt|dms|arm>&time_code=<JMA frame>` (older single-image endpoint: JMA Himawari-9 Southeast Asia image; cached 5 minutes)
- `POST /api/v1/reports/flood-screening` (PDF brief of the screening data; explicitly not a farm-damage report and does not require the assessment database)
- `POST /api/v1/reports` (PDF of the latest completed database assessment; requires configured GaussDB/PostGIS)
- `POST /api/v1/weather/current` (current Open-Meteo model conditions for selected coordinates; no provider key required)
- `GET /api/v1/weather/tiles/{layer}/{z}/{x}/{y}.png` (backend-proxied current weather map layer)
- `POST /api/v1/reports`

Interactive API documentation is available at `/docs` while the backend is running.
The [production readiness checklist](docs/production_readiness.md) lists the authorized data, approved methodology, and Huawei service access still required before an operational agricultural assessment can be completed.
GaussDB setup and migration instructions are in [docs/gaussdb_postgis.md](docs/gaussdb_postgis.md).
Parcel dataset inspection, validation, import, and verification steps are documented in [docs/gaussdb_postgis.md](docs/gaussdb_postgis.md).
The parcel importer records provider/source/license attribution; the additive `002_parcel_source_attribution.sql` migration is applied through the standard migration runner.
Huawei OBS and ModelArts settings are documented in [docs/huawei_cloud.md](docs/huawei_cloud.md).
The current implementation status, consolidated work history, verified parcel-source findings, and next steps are in [docs/doc.md](docs/doc.md).
For a short teammate briefing, see [docs/team_briefing.md](docs/team_briefing.md).
