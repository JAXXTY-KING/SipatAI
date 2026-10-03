# GaussDB and PostGIS

The dashboard, map, and report APIs require `GAUSSDB_DSN` and a completed database assessment. Without them, the API returns an unavailable response instead of synthetic or stale values.

## Huawei Cloud prerequisite

GaussDB instance types and regional capabilities vary. Before creating or purchasing an instance, confirm with Huawei Cloud or the database administrator that the selected instance and region support PostGIS, the `postgis` extension can be enabled, and the backend host can connect to it over TLS.

- [Huawei GaussDB documentation](https://support.huaweicloud.com/intl/en-us/gaussdb/index.html)
- [Buying a GaussDB instance](https://support.huaweicloud.com/intl/en-us/usermanual-gaussdb/gaussdb_01_080.html)
- [Connecting to a GaussDB instance](https://support.huaweicloud.com/intl/en-us/usermanual-gaussdb/gaussdb_01_083.html)

## Schema and coordinates

`backend/migrations/001_spatial_assessment.sql` creates the parcel, flood polygon, assessment, and parcel damage tables and their spatial indexes. The migration requires permission to enable PostGIS. Apply schema changes through the migration runner; do not create or alter application tables manually.

Stored map geometries use EPSG:4326. Source CRS values are recorded separately. Data must be reprojected explicitly in the preprocessing pipeline before it is stored; this database schema does not silently transform coordinates. Parcel damage areas use PostGIS geography calculations and are recorded in hectares. Damage severity stays unset until official classification thresholds are agreed.

## Configure a connected environment

The backend reads `GAUSSDB_DSN` from its process environment. Keep the DSN private and do not put real credentials in `.env.example`, source control, frontend variables, or chat. Include `sslmode=require` in the DSN when required by the Huawei instance configuration.

From a VS Code terminal in the `backend/` folder, set `GAUSSDB_DSN` for that terminal session to the private connection string supplied by the database administrator. Do not put the password in a command you intend to share. Then apply the migration:

```powershell
.\.venv\Scripts\python.exe -m scripts.migrate
```

The command prints `Applied database migration 001_spatial_assessment.sql.` when the migration succeeds. If PostGIS cannot be enabled or the connection fails, ask the Huawei/database administrator to confirm the instance, extension permissions, TLS settings, and network access before running an assessment.
