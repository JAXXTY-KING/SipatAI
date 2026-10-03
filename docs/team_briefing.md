# SipatAI Team Briefing

**Prepared:** 2026-10-04

## Purpose

SipatAI is intended to detect flood extent from Sentinel imagery, measure impacts on authorized agricultural parcels, and produce assessment reports. It is **not yet operational end to end**. The application does not invent or display sample assessment results.

## Implemented

- Vue dashboard, flood map, report center, and satellite-scene search.
- FastAPI backend with health, assessment, report, ModelArts, and scene-search routes.
- Live Copernicus Data Space search for Sentinel-1 GRD and Sentinel-2 L2A over the Philippines, by date, with optional Sentinel-2 cloud filtering. Real catalog results were verified.
- MindSpore 2.10.0 ResNet-50 U-Net, shared input/class configuration, weighted focal-Dice loss, tile reader, training entry point, and MindIR exporter. CPU model/loss and dataset smoke tests passed.
- Backend integration code for ModelArts inference and Huawei OBS storage.
- Versioned GaussDB/PostGIS schema and spatial queries for flood/parcel intersection and affected area calculations.
- Reports read from the latest completed database assessment; they do not accept client-supplied assessment totals.

## Still Needed

1. **National parcel data:** The Geoportal LMB “Parcel data” layer is conditional-download and covers selected Metro Manila areas, not confirmed nationwide coverage. Request authorized national farm/cadastral boundaries from LMB, DA, or local governments. Do not include farmer personal data unless formally authorized.
2. **Huawei resources:** Provision a private OBS bucket, PostGIS-enabled GaussDB instance, and ModelArts workspace/online endpoint. Choose the Huawei region and confirm PostGIS support there.
3. **Copernicus download:** Scene search works, but authenticated product downloads to OBS are not implemented. A Copernicus account/token is needed for downloads; keep credentials in backend environment settings only.
4. **Preprocessing:** Implement SNAP/GDAL calibration, noise removal, terrain correction, raster alignment, and GeoTIFF/tile output. Preserve CRS and use the configured six-channel order: VV, VH, NDVI, NDWI, RED, NIR.
5. **Training:** Obtain labeled flood masks and approve class weights, optimizer, learning rate, epochs, and evaluation criteria. The model code has no trained weights yet.
6. **Inference and reporting rules:** Deploy MindIR to ModelArts and verify the endpoint payload. Obtain approved damage-severity thresholds and crop valuation rules before reporting severity or monetary losses.
7. **End-to-end validation:** Import authorized parcels, run a real event from satellite search through report generation, and verify CRS, coverage, and results before operational use.

## Next Work Session

Start the authenticated Copernicus download-to-OBS implementation while requesting nationwide parcel coverage from LMB/DA. No cloud passwords, access keys, or Copernicus tokens should be sent in chat or committed to the repository.

## Local App

- Website: http://127.0.0.1:5173/
- API documentation: http://127.0.0.1:8000/docs
- Detailed handover and implementation notes: [doc.md](doc.md)
