# SipatAI Team Briefing

**Prepared:** 2026-10-10

## Purpose

SipatAI is intended to detect flood extent from Sentinel imagery, measure impacts on authorized agricultural parcels, and produce assessment reports. It is **not yet operational end to end**. The application does not invent or display sample assessment results.

## Implemented

- Vue dashboard, flood map, report center, and satellite-scene search.
- FastAPI backend with health, assessment, report, ModelArts, and scene-search routes.
- Live Copernicus Data Space search for Sentinel-1 GRD and Sentinel-2 L2A over the Philippines, by date, with optional Sentinel-2 cloud filtering. Real catalog results were verified.
- MindSpore 2.10.0 ResNet-50 U-Net, shared input/class configuration, weighted focal-Dice loss, tile reader, training entry point, and MindIR exporter. CPU model/loss and dataset smoke tests passed.
- Backend integration code for ModelArts inference and Huawei OBS storage.
- Versioned GaussDB/PostGIS schema and spatial queries for flood/parcel intersection and affected area calculations.
- Source-configurable parcel inspect/validate/import/verify CLI for GeoJSON, Shapefile, and GeoPackage, including area-filtered imports, required source attribution, dry-run, and transactional writes. It is not yet verified with authorized parcel data or a live GaussDB instance.
- `/flood-map` has an optional PhilSA Sentinel-1 historical flood reference rasterized from all 61,774 polygons in the 2025-07-06 source dataset. It is licensed CC BY 4.0, is not a farm-parcel layer or SipatAI result, and is not validated against ground truth. Fifteen thousand seven hundred five invalid source geometries were repaired before rendering.
- The map uses Mapbox Streets as its colored basemap and keeps administrative regions, imported parcels, the PhilSA historical layer, and completed database assessments as distinct layers.
- Reports read from the latest completed database assessment; they do not accept client-supplied assessment totals.

## Still Needed

1. **Parcel data:** No parcel extract is cleared for import. Geoportal's LMB cadastral layer metadata describes 57,150 polygons in selected Metro Manila areas, but the catalogue has `download: null`, the export form did not offer it, and direct feature requests timed out. A public Midori Highlands FeatureServer returns commercial subdivision geometry, but its license field is blank; do not reuse it without the publisher's written permission. PHIVOLCS layers remain unverified; the reviewed public NAMRIA directory exposed no parcel layer. No nationwide, Luzon, Ilocos Norte, or Bacarra farm-parcel coverage is established. Request authorized sample data and terms from LMB/DA/DAR/Bacarra LGU.
2. **Huawei resources:** Provision a private OBS bucket, PostGIS-enabled GaussDB instance, and ModelArts workspace/online endpoint. Choose the Huawei region and confirm PostGIS support there.
3. **Copernicus download:** Scene search works, but authenticated product downloads to OBS are not implemented. A Copernicus account/token is needed for downloads; keep credentials in backend environment settings only.
4. **Preprocessing:** Implement SNAP/GDAL calibration, noise removal, terrain correction, raster alignment, and GeoTIFF/tile output. Preserve CRS and use the configured six-channel order: VV, VH, NDVI, NDWI, RED, NIR.
5. **Training:** Obtain labeled flood masks and approve class weights, optimizer, learning rate, epochs, and evaluation criteria. The model code has no trained weights yet.
6. **Inference and reporting rules:** Deploy MindIR to ModelArts and verify the endpoint payload. Obtain approved damage-severity thresholds and crop valuation rules before reporting severity or monetary losses.
7. **End-to-end validation:** Import authorized parcels, run a real event from satellite search through report generation, and verify CRS, coverage, and results before operational use.

## Next Work Session

Obtain written authorization for a small farm-parcel dataset and validate/import/verify it with the documented CLI before moving on to Sentinel download work. No cloud passwords, access keys, farmer personal data, or Copernicus tokens should be sent in chat or committed to the repository. Source evidence and a reusable LMB request are in [doc.md](doc.md#farm-parcels).

## Local App

- Website: http://127.0.0.1:5173/
- API documentation: http://127.0.0.1:8000/docs
- Detailed handover and implementation notes: [doc.md](doc.md)

## Presentation Demo

On `/flood-map`, enable **PhilSA historical flood reference · 6 Jul 2025** to see the full source-data footprint (approximately 119.86–122.52°E, 11.83–19.54°N). The overlay is a transparent display raster derived from all 61,774 source polygons; it is not an administrative boundary or an assessment. The source metadata states that the mapped extent was not validated against ground truth. Cite Philippine Space Agency (PhilSA) via [HDX](https://data.humdata.org/dataset/e3cbe3fc-82b5-46df-8b04-0f90333975cc), CC BY 4.0. Collapse or expand the map legend with its **Legend** toggle.

Do not report parcel damage, affected farms, or assessment statistics from this layer. It is independent of authorized farm parcels and completed PostGIS assessments.
