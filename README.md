# SipatAI

SipatAI is an agricultural flood-assessment system using Sentinel imagery, MindSpore, Huawei ModelArts, GaussDB/PostGIS, FastAPI, and Vue with Mapbox.

The application does not seed or serve synthetic assessment records. Dashboard, map, and report routes require a completed database assessment; unconfigured services return unavailable states instead of fabricated results.

Agricultural parcel boundaries are system data, not an end-user upload task. A controlled command-line importer now supports inspecting, validating, and loading authorized GeoJSON, Shapefile, and GeoPackage datasets into GaussDB/PostGIS. The workflow has not yet been verified against an authorized farm-parcel dataset or a live Huawei database. Sentinel preprocessing and flood inference are still not connected end to end.

The map uses Mapbox Streets and includes a separately labeled SimpleMaps administrative-region reference overlay and the full-footprint PhilSA historical observed-flood sample, rasterized for map display. Neither is farm-parcel data or a SipatAI damage assessment; the flood sample is explicitly marked as not ground-truth validated.

## Project layout

- `frontend/`: Vue 3 application deployed as a Vite site.
- `backend/`: FastAPI application and report service.
- `ml/`, `preprocessing/`, `deploy/`, and `docs/`: architecture configuration and implementation notes.
- `docs/setup_windows.md`: Windows prerequisites and first-run instructions.

## Prerequisites

Install Node.js 22 LTS and Python 3.12 from the official links in `docs/setup_windows.md`. MindSpore 2.10.0 and NumPy 1.26.4 are listed separately for the ML environment in `ml/requirements.txt`.

## Run locally

Follow the exact Windows steps in `docs/setup_windows.md`. The frontend runs separately from the backend. Add a Mapbox public access token to `frontend/.env.local` to enable the interactive map; the dashboard and API can be explored without one.

## API

- `GET /health`
- `GET /api/v1/barangay/summary`
- `GET /api/v1/damage-map`
- `GET /api/v1/parcels/map?west=<longitude>&south=<latitude>&east=<longitude>&north=<latitude>` (imported parcels within the current map viewport)
- `POST /api/v1/analyze` (requires a configured ModelArts endpoint)
- `POST /api/v1/scenes/search` (Copernicus Data Space Sentinel catalogue)
- `POST /api/v1/reports`

Interactive API documentation is available at `/docs` while the backend is running.
GaussDB setup and migration instructions are in [docs/gaussdb_postgis.md](docs/gaussdb_postgis.md).
Parcel dataset inspection, validation, import, and verification steps are documented in [docs/gaussdb_postgis.md](docs/gaussdb_postgis.md).
The parcel importer records provider/source/license attribution; the additive `002_parcel_source_attribution.sql` migration is applied through the standard migration runner.
Huawei OBS and ModelArts settings are documented in [docs/huawei_cloud.md](docs/huawei_cloud.md).
The current implementation status, consolidated work history, verified parcel-source findings, and next steps are in [docs/doc.md](docs/doc.md).
For a short teammate briefing, see [docs/team_briefing.md](docs/team_briefing.md).
