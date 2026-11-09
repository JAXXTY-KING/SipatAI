# Production Readiness Checklist

The current local demo can display a coarse rainfall-and-elevation screening, search the Copernicus Sentinel catalog, and generate a screening brief. It is **not** an operational typhoon detector or an agricultural flood-damage assessment. Complete and verify the items below before describing it as production-ready.

## 1. Confirm the operational study

- [ ] Name the initial province/municipality coverage and event period. A nationwide coarse overview does not provide operational local flood detail.
- [ ] Identify the authorized data owner and responsible reviewer for the flood warning and agricultural-impact workflow.
- [ ] Obtain written approval for the data uses, retention, redistribution, and report recipients.

## 2. Supply authorized agricultural parcels

- [ ] Obtain farm-parcel polygons for the target AOI and written authorization/license terms.
- [ ] Include a data dictionary with stable parcel ID, barangay/municipality names, source CRS, crop/use fields where available, and update date.
- [ ] Identify personal or sensitive fields and exclude them unless their processing is explicitly authorized and necessary.
- [ ] Check the coverage and geometry against an authoritative boundary. Do not treat administrative regions, cadastral lots without agricultural attributes, or the PhilSA sample as farm parcels.
- [ ] Configure the PostGIS-capable GaussDB service, network/TLS access, and backend-only `GAUSSDB_DSN`; run migrations, import via the documented CLI, and verify counts, CRS, and geometry.

## 3. Approve the flood method and validation

- [ ] Obtain event-dated Sentinel-1/Sentinel-2 imagery and authoritative flood extent labels with permissions and provenance.
- [ ] Agree on the model input contract, preprocessing, flood classes, severity rules, and crop-loss valuation with the data owner and domain reviewer.
- [ ] Define independent held-out events, validation metrics, acceptable error rates, and review/sign-off criteria before training.
- [ ] Train and evaluate the segmentation model; preserve its training-data lineage, metrics, model version, and failure cases.
- [ ] Confirm the trained model endpoint's exact payload/output contract; deploy and test MindIR on the chosen ModelArts hardware.
- [ ] Validate the complete path from source scenes through preprocessing, inference, geospatial intersection, map output, and report against independent observations.

## 4. Configure cyclone and cloud services

- [ ] Select an official, permitted tropical-cyclone advisory/track source (prefer PAGASA for Philippine warnings); document update cadence and stale-data behavior.
- [ ] Do not infer typhoon identity or official warning level from general rainfall forecasts.
- [ ] Provision and test private Huawei OBS, ModelArts, and GaussDB/PostGIS services in the approved region.
- [ ] Store private settings only in backend environment files/secret management: `GAUSSDB_DSN`, `MODELARTS_INFERENCE_URL`, `MODELARTS_INFERENCE_TOKEN`, OBS configuration, and any Copernicus credentials.
- [ ] Verify runtime connectivity, TLS, least privilege, timeouts, retries, quotas, and audit/retention rules. A configured variable alone is not proof of working service access.

## 5. Production acceptance

- [ ] Exercise one authorized historical event end to end and independently verify coordinates, units, parcel coverage, model output, and report totals.
- [ ] Show source, observation/forecast issue time, retrieval time, model version, AOI, uncertainty, and missing-data warnings on every operational result.
- [ ] Keep forecast-screening summaries and measured flood assessments distinct in the UI and downloadable reports.
- [ ] Run backend tests, frontend production build, security/privacy review, and desktop/mobile acceptance with the production configuration.
- [ ] Obtain sign-off from the data owner and agricultural/flood domain reviewer before use in preparedness or response decisions.

## Keep credentials private

Do not paste passwords, access keys, bearer tokens, private URLs containing credentials, or personal parcel data into chat or source control. Configure secrets in the approved local secret manager or backend environment file, and share only redacted connection/test outcomes.
