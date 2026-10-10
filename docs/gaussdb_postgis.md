# GaussDB and PostGIS

The dashboard, map, and report APIs require `GAUSSDB_DSN` and a completed database assessment. Without them, the API returns an unavailable response instead of synthetic or stale values.

## Huawei Cloud prerequisite

GaussDB instance types and regional capabilities vary. Before creating or purchasing an instance, confirm with Huawei Cloud or the database administrator that the selected instance and region support PostGIS, the `postgis` extension can be enabled, and the backend host can connect to it over TLS.

- [Huawei GaussDB documentation](https://support.huaweicloud.com/intl/en-us/gaussdb/index.html)
- [Buying a GaussDB instance](https://support.huaweicloud.com/intl/en-us/usermanual-gaussdb/gaussdb_01_080.html)
- [Connecting to a GaussDB instance](https://support.huaweicloud.com/intl/en-us/usermanual-gaussdb/gaussdb_01_083.html)

## Schema and coordinates

`backend/migrations/001_spatial_assessment.sql` creates the parcel, flood polygon, assessment, and parcel damage tables and their spatial indexes. The additive `002_parcel_source_attribution.sql` migration adds provenance to parcel records. The migrations require permission to enable PostGIS. Apply schema changes through the migration runner; do not create or alter application tables manually.

Stored map geometries use EPSG:4326. Source CRS values are recorded separately. Data must be reprojected explicitly in the preprocessing pipeline before it is stored; this database schema does not silently transform coordinates. Parcel damage areas use PostGIS geography calculations and are recorded in hectares. Damage severity stays unset until official classification thresholds are agreed.

The initial schema has a syntax fix in its `assessment_runs` definition. The migration runner skips migration filenames already recorded in `schema_migrations`; editing an already-applied migration does not update a shared database. The original migration cannot have been applied as written because that syntax is invalid. If a database administrator has a separately corrected version already applied, compare its schema before applying migrations. Do not reset a shared database.

### Parcel data workflow

The importer supports local GeoJSON, Shapefile, and GeoPackage vector datasets through Fiona/GDAL, Shapely geometry validation, and PyProj coordinate transformation. It does not download data from or assume field names from any agency. Obtain written access and use terms from the data owner before importing. As of 2026-10-10, no authorized parcel dataset has been provided or loaded into this project.

No parcel source has been verified as both suitable for SipatAI farm analysis and authorized for project storage/republication:

- PHIVOLCS [HAS_PARCELS MapServer](https://gisweb.phivolcs.dost.gov.ph/arcgis/rest/services/PHIVOLCS/HAS_PARCELS/MapServer), [HAS_PARCELS FeatureServer](https://gisweb.phivolcs.dost.gov.ph/arcgis/rest/services/PHIVOLCS/HAS_PARCELS/FeatureServer), and [testparcel1 FeatureServer](https://gisweb.phivolcs.dost.gov.ph/arcgis/rest/services/PHIVOLCS/testparcel1/FeatureServer) returned HTTP 200 but `text/html` challenge/error pages instead of ArcGIS JSON metadata. Their coverage, fields, access requirements, license, and intended use could not be verified.
- The working [Geoportal LMB layer record](https://geoportal.gov.ph/layers/fetchlayerconfig/denr_parcel_data/ParcelData) identifies “Parcel data” (`denr_parcel_data`) from LMB. Its embedded metadata describes 57,150 cadastral polygons in selected Metro Manila areas (bounding box 120.85786–121.100809°E, 14.617931–14.798865°N), with `ogc_fid`, `lotnumber`, `shape_length`, and `shape_area`. It does not provide crop attributes. The layer catalogue shows `download: null`; the Geoportal download form did not offer it in the checked session, and tested WMS/WFS requests timed out. Metadata fields that say access/use constraints “None” do not state an open-data license. Ask LMB for the vector extract and written permission. This coverage is not Ilocos Norte/Bacarra.
- A [public ArcGIS FeatureServer item for Midori Highlands](https://services7.arcgis.com/yiuFazTjHE8F5gzQ/arcgis/rest/services/Midori_Highlands_Parcels/FeatureServer/1) can return GeoJSON polygons for a Clark subdivision; its example includes commercial-use property and land-area fields. The [ArcGIS item record](https://www.arcgis.com/sharing/rest/content/items/0fe446101a264d878dffb5a57c2de963?f=pjson) is owned by a non-government account and has blank license and access-information fields. Do not import or rehost it without publisher permission; it is not agricultural parcel data or target-area coverage.
- [NAMRIA Downloads](https://namria.gov.ph/Downloads.aspx) loaded, but the reviewed page did not identify an agricultural parcel product, coverage, parcel attributes, or parcel-specific usage terms.
- [SimpleMaps Philippines GIS](https://simplemaps.com/gis/country/ph) exposes 17 first-level administrative-region polygons in WGS84, with `id` and `name` fields under CC BY 4.0. These are administrative regions, not farm lots; they contain no parcel IDs, crops, or barangay-level farm parcels. The frontend copy is reference only and is never imported into `farm_parcels` or used for damage calculations.

Nationwide, Luzon-wide, Ilocos Norte, and Bacarra farm-parcel coverage therefore remain unverified. Do not treat a queryable service as permission to reuse. Request a suitably located, licensed sample and data dictionary from LMB, DA, DAR, or Bacarra's local government; confirm coverage, stable IDs, CRS, permitted use, and personal-data restrictions before import. The detailed source assessment and draft LMB request are in [doc.md](doc.md#farm-parcels).

#### Input contract

- `--source-dataset` is a stable, human-readable dataset/version label used with the parcel ID for duplicate detection. Do not use one label for unrelated versions if their identifiers can collide.
- `--source-attribution` is required for database imports. Record the publisher, exact source URL, and license/access terms. It is stored on every imported parcel and returned with map features.
- A mapped parcel-ID field is required and must contain stable, non-empty string or integer IDs. The importer never makes up IDs or converts floating-point values into identifiers.
- A mapped barangay field is required because `farm_parcels.barangay_name` is non-null. Rows missing it are rejected; the importer does not invent a location.
- Crop field mapping is optional. Missing or blank crop values are stored as `NULL`.
- Source CRS must be present in the file or supplied with `--source-crs`. Coordinates are never assumed. Stored geometries are transformed to EPSG:4326, and the source CRS string is stored in `source_crs`.
- Only valid 2D Polygon/MultiPolygon features are accepted. Polygons are wrapped as MultiPolygons without changing their boundaries. Null, empty, invalid, 3D, non-polygon, missing-ID, duplicate-ID, missing-barangay, and out-of-study-area features are rejected with counts by reason. The optional study-area boundary must cover the entire parcel geometry for the parcel to be accepted.
- Additional source fields are reported during inspection but are not loaded into the current schema.

#### Inspect, validate, import, and verify on Windows

Run commands from `backend/`. Install the backend dependencies into the project virtual environment first:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Inspect the dataset before mapping fields. The report includes the extent in the source CRS and its transformed EPSG:4326 longitude/latitude extent. For a GeoPackage with multiple layers, add `--layer <layer-name>`:

```powershell
.\.venv\Scripts\python.exe -m scripts.import_parcels inspect --input "C:\data\authorized_parcels.gpkg"
```

Validate without database access or changes. Supply an override only when the source CRS is missing or demonstrably incorrect in its metadata:

```powershell
.\.venv\Scripts\python.exe -m scripts.import_parcels validate `
  --input "C:\data\authorized_parcels.gpkg" `
  --source-dataset "agency-parcels-2026-01" `
  --parcel-id-field "LOT_ID" `
  --barangay-field "BARANGAY" `
  --crop-field "CROP" `
  --study-area "C:\data\target_municipality.gpkg" `
  --source-crs "EPSG:32651"
```

Omit optional flags when not applicable. Use the CRS printed by `inspect`; do not copy the example CRS blindly. `--study-area-layer` and `--study-area-crs` can be used when needed. `validate` checks source records only and does not require GaussDB credentials.

After reviewing the validation results and configuring the private `GAUSSDB_DSN`, perform a database-backed dry run, then import:

```powershell
.\.venv\Scripts\python.exe -m scripts.import_parcels import `
  --input "C:\data\authorized_parcels.gpkg" `
  --source-dataset "agency-parcels-2026-01" `
  --source-attribution "Agency name; https://agency.example/data; license/access terms" `
  --parcel-id-field "LOT_ID" `
  --barangay-field "BARANGAY" `
  --crop-field "CROP" `
  --study-area "C:\data\target_municipality.gpkg" `
  --dry-run

.\.venv\Scripts\python.exe -m scripts.import_parcels import `
  --input "C:\data\authorized_parcels.gpkg" `
  --source-dataset "agency-parcels-2026-01" `
  --source-attribution "Agency name; https://agency.example/data; license/access terms" `
  --parcel-id-field "LOT_ID" `
  --barangay-field "BARANGAY" `
  --crop-field "CROP" `
  --study-area "C:\data\target_municipality.gpkg"
```

Imports run in a database transaction. By default, existing `(source_dataset, source_parcel_id)` rows are skipped, so rerunning the same import does not overwrite data. To deliberately replace fields and geometry for matching IDs, review the source/version and explicitly add `--update-existing`. The importer does not delete parcels. Validation failures are counted and skipped; a database or source-read failure aborts and rolls back the transaction.

Migration `002_parcel_source_attribution.sql` additively adds parcel provenance without changing stored geometry. Apply it with the migration runner before using updated importer or map queries. For incremental area imports, prepare an authorized local dataset for that area and pass its polygon with `--study-area`; only parcels fully covered by that boundary are accepted. Keep source labels and globally unique provider IDs stable across chunks. The CLI does not fetch remote ArcGIS services or bypass access controls.

Apply pending additive migrations before importing. This includes `002_parcel_source_attribution.sql` for existing databases:

```powershell
.\.venv\Scripts\python.exe -m scripts.migrate
```

Check database counts, per-source totals, SRIDs, extent, invalid/empty geometry totals, duplicate identifier groups, missing attribution, and (optionally) parcels not fully covered by a study-area boundary:

```powershell
.\.venv\Scripts\python.exe -m scripts.import_parcels verify `
  --source-dataset "agency-parcels-2026-01" `
  --study-area "C:\data\target_municipality.gpkg"
```

To verify all sources, omit `--source-dataset`. The command is read-only. A successful load should report SRID 4326, no invalid/empty geometries, no duplicate `(source_dataset, source_parcel_id)` groups, and no out-of-area parcels when a study area is supplied. Compare extent and row counts with the source's documented coverage and the import summary.

After parcels have been imported, the flood-map page calls `GET /api/v1/parcels/map` for its visible map bounds and draws returned parcel polygons. The API caps a response at 2,500 features; if more match the viewport, zoom in to request a smaller area. Click a parcel to see its parcel ID, source label, barangay, and crop value when supplied. The completed flood assessment is an optional separate layer; imported parcels remain visible even when there is no completed assessment. The map requires the backend API, `GAUSSDB_DSN`, and a restricted public Mapbox token configured in `frontend/.env.local`.

The frontend also contains the SimpleMaps first-level administrative-region GeoJSON from [its Philippines GIS page](https://simplemaps.com/gis/country/ph), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The data is used unchanged and attribution is displayed in the map. It contains 17 regions, not farm lots, cadastral parcels, barangays, or crop data. This is a geographic reference layer only and is not stored in `farm_parcels` or used to calculate flood damage.

Common errors: provide the exact field spelling from `inspect`; specify a layer for multi-layer GeoPackages; install the listed geospatial dependencies if Fiona cannot open a format; supply the true CRS if metadata is absent; fix source geometry rather than relying on automatic repair; and ask the database administrator to verify PostGIS extension, TLS, network access, and `GAUSSDB_DSN` if the database is unavailable.

The automated tests create small artificial polygons in temporary files to exercise the importer. Those fixtures are not cadastral records, are not retained as parcel data, and must not be used as Philippine boundary or agricultural information.

#### Database verification queries

These read-only queries may also be run in a SQL client after replacing the source label:

```sql
SELECT source_dataset, COUNT(*) AS parcel_count
FROM farm_parcels
GROUP BY source_dataset
ORDER BY source_dataset;

SELECT ST_SRID(geom) AS srid, COUNT(*) AS parcel_count,
       ST_Extent(geom) AS extent
FROM farm_parcels
WHERE source_dataset = 'agency-parcels-2026-01'
GROUP BY ST_SRID(geom);

SELECT
    SUM(CASE WHEN geom IS NULL OR ST_IsEmpty(geom) THEN 1 ELSE 0 END) AS empty_count,
    SUM(CASE WHEN geom IS NOT NULL AND NOT ST_IsValid(geom) THEN 1 ELSE 0 END) AS invalid_count,
    SUM(CASE WHEN source_attribution IS NULL OR BTRIM(source_attribution) = '' THEN 1 ELSE 0 END) AS missing_attribution_count
FROM farm_parcels
WHERE source_dataset = 'agency-parcels-2026-01';

SELECT source_dataset, source_parcel_id, COUNT(*) AS copies
FROM farm_parcels
GROUP BY source_dataset, source_parcel_id
HAVING COUNT(*) > 1;
```

The SQL uses PostGIS functions already required by the schema. Huawei GaussDB compatibility is instance/engine/version dependent: the project documentation does not prove that a particular provisioned GaussDB supports `postgis`, geometry/geography, `ST_Transform`, GiST, `ST_Covers`, `ON CONFLICT`, or all query features. Confirm the exact instance's PostGIS extension and function support with the database administrator and run the migration plus a test import/verification against that target before operational use. Unit tests do not require Huawei credentials.

## Configure a connected environment

The backend reads `GAUSSDB_DSN` from its process environment. Keep the DSN private and do not put real credentials in `.env.example`, source control, frontend variables, or chat. Include `sslmode=require` in the DSN when required by the Huawei instance configuration.

From a VS Code terminal in the `backend/` folder, set `GAUSSDB_DSN` for that terminal session to the private connection string supplied by the database administrator. Do not put the password in a command you intend to share. Then apply the migration:

```powershell
.\.venv\Scripts\python.exe -m scripts.migrate
```

The command prints `Applied database migration 001_spatial_assessment.sql.` when the migration succeeds. If PostGIS cannot be enabled or the connection fails, ask the Huawei/database administrator to confirm the instance, extension permissions, TLS settings, and network access before running an assessment.
