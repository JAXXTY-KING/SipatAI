# Huawei Cloud Configuration

Huawei ModelArts inference, OBS storage, and GaussDB/PostGIS data access run through backend integrations. Huawei credentials stay in the backend environment and are never exposed to the browser.

## ModelArts

Set `MODELARTS_INFERENCE_URL` to the HTTPS prediction endpoint for the deployed MindIR model. Set `MODELARTS_INFERENCE_TOKEN` in the backend environment only. The `/api/v1/analyze` route forwards the model-specific JSON payload to that endpoint. Endpoint configuration is not proof that the service is reachable; run an authorized inference after deployment to verify it.

## OBS

Use the endpoint for the region containing your bucket and its bucket name. For an application deployed on Huawei ECS, prefer an ECS agency with least-privilege access and set:

```text
OBS_ENDPOINT=https://obs.<region>.myhuaweicloud.com
OBS_BUCKET=<your-private-bucket-name>
OBS_USE_ECS_ROLE=true
```

For local development, set `OBS_USE_ECS_ROLE=false` and supply `OBS_ACCESS_KEY_ID` and `OBS_SECRET_ACCESS_KEY` through the backend process environment. Temporary credentials can also use `OBS_SECURITY_TOKEN`. Never put these values in frontend variables, tracked files, or chat. The OBS integration supports checking bucket metadata and uploading processed artifacts with the official Huawei Python SDK.

The local `.env.example` contains placeholders only. Do not copy a real credential CSV into the repository. Production OBS bucket permissions should be private and limited to the backend ECS role.

Official references: [Huawei OBS Python SDK installation](https://support.huaweicloud.com/intl/en-us/sdk-python-devg-obs/obs_22_0400.html), [ObsClient initialization and ECS credentials](https://support.huaweicloud.com/intl/en-us/sdk-python-devg-obs/obs_22_0601.html), and [OBS endpoints](https://developer.huaweicloud.com/intl/en-us/endpoint?OBS).

## GaussDB/PostGIS

Set `GAUSSDB_DSN` in the backend environment after provisioning a PostGIS-enabled Huawei GaussDB instance. Keep the database password private. Apply schema changes only through the migration runner documented in [gaussdb_postgis.md](gaussdb_postgis.md).

## OpenWeatherMap

The backend reads `OPENWEATHERMAP_API_KEY` from `backend/.env` or the ignored `backend/.env.local` file. `GET /api/v1/weather/locations?q=<place>` searches Philippine place names; `POST /api/v1/weather/current` returns normalized current conditions for the selected coordinates. The map can select coordinates, and users can also search by place name or enter coordinates manually. The map also provides current precipitation, cloud, temperature, wind, and pressure tiles through `GET /api/v1/weather/tiles/{layer}/{z}/{x}/{y}.png`; the backend proxies these tiles so the provider key stays private. Weather layers are contextual only, not flood extent or satellite observations, and are not MindSpore model inputs.

The key previously shared in chat is exposed; rotate it in the OpenWeatherMap account and replace it only in `backend/.env.local`. Never put the key in frontend variables, tracked files, or chat. `.env.local` is excluded by `.gitignore`.