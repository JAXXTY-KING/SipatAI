<template>
  <section class="map-frame parcel-map-frame" aria-label="Farm parcel, administrative reference, historical flood sample, and assessment map">
    <div v-if="mapToken" ref="mapElement" class="map-canvas"></div>
    <div v-if="!mapToken" class="map-message" role="status">
      <strong>Map service not configured</strong>
      <span>Set a restricted public Mapbox token in frontend/.env.local to display the map.</span>
    </div>

    <div v-if="mapToken" class="parcel-map-tools" aria-label="Map layers and parcel status">
      <label class="map-layer-toggle">
        <input v-model="showRegions" type="checkbox" @change="setRegionVisibility">
        <span class="region-swatch"></span>
        Administrative regions (reference only)
      </label>
      <label class="map-layer-toggle">
        <input v-model="showParcels" type="checkbox" @change="setLayerVisibility('farm-parcel-fill', showParcels)">
        <span class="parcel-swatch"></span>
        Imported parcels
      </label>
      <label class="map-layer-toggle">
        <input v-model="showDamage" type="checkbox" :disabled="!hasDamageFeatures" @change="setDamageVisibility">
        <span class="damage-swatch"></span>
        Completed flood assessment
      </label>
      <label class="map-layer-toggle">
        <input v-model="showFloodReference" type="checkbox" @change="setFloodReferenceVisibility">
        <span class="flood-reference-swatch"></span>
        PhilSA flood sample (full source footprint) · 6 Jul 2025
      </label>
      <button
        class="parcel-refresh-button"
        type="button"
        :disabled="isLoadingParcels"
        @click="loadParcels"
      >
        {{ isLoadingParcels ? 'Refreshing parcels…' : 'Refresh parcels' }}
      </button>
      <p class="parcel-map-status" role="status" aria-live="polite">{{ parcelStatus }}</p>
      <p v-if="damageStatus" class="parcel-map-status" role="status">{{ damageStatus }}</p>
      <p class="parcel-map-attribution">
        Historical sample:
        <a href="https://data.humdata.org/dataset/e3cbe3fc-82b5-46df-8b04-0f90333975cc" target="_blank" rel="noreferrer">PhilSA via HDX</a> ·
        <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a>.
        Full source footprint (119.86–122.52°E, 11.83–19.54°N; not nationwide);
        reference raster, not ground-truth validated or an assessment.
      </p>
      <p class="parcel-map-attribution">
        Regions: <a href="https://simplemaps.com/gis/country/ph" target="_blank" rel="noreferrer">SimpleMaps</a> ·
        <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a>;
        administrative boundaries, not parcels.
      </p>
    </div>

    <details v-if="mapToken" class="map-legend parcel-legend" open>
      <summary>Legend</summary>
      <div class="parcel-legend-items">
        <span v-if="showRegions"><i class="region-legend-mark"></i> Administrative region · reference only</span>
        <span v-if="showParcels"><i class="parcel-legend-mark"></i> Imported farm parcel</span>
        <span v-if="showDamage && hasDamageFeatures"><i class="damage-legend-mark"></i> Completed flood assessment</span>
        <span v-if="showFloodReference"><i class="flood-reference-legend-mark"></i> PhilSA observed flood reference · not an assessment</span>
      </div>
    </details>
  </section>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import mapboxgl from 'mapbox-gl'
import { fetchDamageMap, fetchParcelMap } from '../api/client'
import { severityColors } from '../map/severity'

const mapToken = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN
const FLOOD_REFERENCE_EXTENT = {
  west: 119.86289120572579,
  south: 11.825563019671437,
  east: 122.52297657464638,
  north: 19.54358448800242,
}
const mapElement = ref(null)
const parcelStatus = ref('Waiting for parcel data…')
const damageStatus = ref('')
const showRegions = ref(true)
const showParcels = ref(true)
const showDamage = ref(true)
const showFloodReference = ref(false)
const isLoadingParcels = ref(false)
const hasDamageFeatures = ref(false)
let map
let resizeObserver
let moveTimer
let mapStartupTimer
let requestSequence = 0
let mapLayersInitialized = false

function setLayerVisibility(layerId, visible) {
  if (map?.getLayer(layerId)) {
    map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none')
  }
}

function setDamageVisibility() {
  setLayerVisibility('flood-damage-fill', showDamage.value)
  setLayerVisibility('flood-damage-outline', showDamage.value)
}

function setRegionVisibility() {
  setLayerVisibility('admin-region-fill', showRegions.value)
  setLayerVisibility('admin-region-outline', showRegions.value)
}

function setFloodReferenceVisibility() {
  setLayerVisibility('philsa-flood-reference-fill', showFloodReference.value)
  if (showFloodReference.value) {
    fitFloodReferenceExtent()
  }
}

function fitFloodReferenceExtent() {
  map?.fitBounds(
    [
      [FLOOD_REFERENCE_EXTENT.west, FLOOD_REFERENCE_EXTENT.south],
      [FLOOD_REFERENCE_EXTENT.east, FLOOD_REFERENCE_EXTENT.north],
    ],
    { padding: 48, maxZoom: 6.5, duration: 900 },
  )
}

function addParcelLayer() {
  map.addSource('farm-parcels', {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  })
  map.addLayer({
    id: 'farm-parcel-fill',
    type: 'fill',
    source: 'farm-parcels',
    paint: {
      'fill-color': '#347c5e',
      'fill-opacity': 0.16,
    },
  })
  map.addLayer({
    id: 'farm-parcel-outline',
    type: 'line',
    source: 'farm-parcels',
    paint: {
      'line-color': '#245c4b',
      'line-width': ['interpolate', ['linear'], ['zoom'], 6, 0.5, 14, 2],
      'line-opacity': 0.9,
    },
  })
  map.on('click', 'farm-parcel-fill', (event) => {
    const feature = event.features?.[0]
    if (!feature) return

    const properties = feature.properties ?? {}
    const popupContent = document.createElement('div')
    const heading = document.createElement('strong')
    heading.textContent = `Parcel ${properties.parcel_id || 'ID not recorded'}`
    popupContent.append(heading)
    for (const [label, value] of [
      ['Source', properties.source_dataset],
      ['Attribution', properties.source_attribution],
      ['Barangay', properties.barangay],
      ['Crop', properties.crop],
    ]) {
      if (!value) continue
      const detail = document.createElement('p')
      detail.textContent = `${label}: ${value}`
      popupContent.append(detail)
    }
    new mapboxgl.Popup({ maxWidth: '18rem' })
      .setLngLat(event.lngLat)
      .setDOMContent(popupContent)
      .addTo(map)
  })
  map.on('mouseenter', 'farm-parcel-fill', () => {
    map.getCanvas().style.cursor = 'pointer'
  })
  map.on('mouseleave', 'farm-parcel-fill', () => {
    map.getCanvas().style.cursor = ''
  })
}

function addAdministrativeRegionLayer() {
  map.addSource('administrative-regions', {
    type: 'geojson',
    data: '/data/ph_admin1.geojson',
  })
  map.addLayer({
    id: 'admin-region-fill',
    type: 'fill',
    source: 'administrative-regions',
    paint: {
      'fill-color': '#8ca6a0',
      'fill-opacity': 0.035,
    },
  })
  map.addLayer({
    id: 'admin-region-outline',
    type: 'line',
    source: 'administrative-regions',
    paint: {
      'line-color': '#647d76',
      'line-width': ['interpolate', ['linear'], ['zoom'], 3, 0.7, 7, 1.2],
      'line-opacity': 0.72,
    },
  })
  map.on('click', 'admin-region-fill', (event) => {
    if (map.queryRenderedFeatures(event.point, { layers: ['farm-parcel-fill'] }).length) return
    const regionName = event.features?.[0]?.properties?.name
    if (!regionName) return
    const content = document.createElement('strong')
    content.textContent = `${regionName} administrative region`
    new mapboxgl.Popup({ maxWidth: '18rem' })
      .setLngLat(event.lngLat)
      .setDOMContent(content)
      .addTo(map)
  })
  setRegionVisibility()
}

function addFloodReferenceLayer() {
  map.addSource('philsa-flood-reference', {
    type: 'image',
    url: '/data/philsa_flood_20250706_reference.png',
    coordinates: [
      [FLOOD_REFERENCE_EXTENT.west, FLOOD_REFERENCE_EXTENT.north],
      [FLOOD_REFERENCE_EXTENT.east, FLOOD_REFERENCE_EXTENT.north],
      [FLOOD_REFERENCE_EXTENT.east, FLOOD_REFERENCE_EXTENT.south],
      [FLOOD_REFERENCE_EXTENT.west, FLOOD_REFERENCE_EXTENT.south],
    ],
  })
  map.addLayer({
    id: 'philsa-flood-reference-fill',
    type: 'raster',
    source: 'philsa-flood-reference',
    layout: {
      visibility: showFloodReference.value ? 'visible' : 'none',
    },
    paint: {
      'raster-opacity': 0.92,
    },
  })
  if (showFloodReference.value) fitFloodReferenceExtent()
}

function addDamageLayer(collection) {
  if (!collection.features?.length || map.getSource('flood-damage')) return
  map.addSource('flood-damage', { type: 'geojson', data: collection })
  map.addLayer({
    id: 'flood-damage-fill',
    type: 'fill',
    source: 'flood-damage',
    paint: {
      'fill-color': [
        'match', ['get', 'severity'],
        'Severe', severityColors.Severe,
        'Moderate', severityColors.Moderate,
        'Light', severityColors.Light,
        '#71559a',
      ],
      'fill-opacity': 0.58,
    },
  })
  map.addLayer({
    id: 'flood-damage-outline',
    type: 'line',
    source: 'flood-damage',
    paint: {
      'line-color': '#47356b',
      'line-width': 1,
    },
  })
  setDamageVisibility()
}

async function loadParcels() {
  const currentRequest = ++requestSequence
  isLoadingParcels.value = true
  parcelStatus.value = 'Loading parcels for this map area…'
  try {
    const collection = await fetchParcelMap(map.getBounds())
    if (currentRequest !== requestSequence || !map) return
    const parcelSource = map.getSource('farm-parcels')
    if (!parcelSource) return
    parcelSource.setData(collection)

    if (collection.truncated) {
      parcelStatus.value = `More than 2,500 parcels are in view. Zoom in to load them safely.`
    } else if (!collection.features.length) {
      parcelStatus.value = 'No imported parcels in this area. Import authorized parcel data, then move or zoom the map.'
    } else {
      const sources = collection.source_datasets?.length
        ? ` · ${collection.source_datasets.join(', ')}`
        : ''
      parcelStatus.value = `${collection.features.length.toLocaleString()} parcel${collection.features.length === 1 ? '' : 's'} in view${sources}`
    }
  } catch (error) {
    if (currentRequest !== requestSequence) return
    parcelStatus.value = error instanceof Error
      ? `Parcel data unavailable: ${error.message}`
      : 'Parcel data is unavailable. Check the API and database configuration.'
  } finally {
    if (currentRequest === requestSequence) isLoadingParcels.value = false
  }
}

function scheduleParcelRefresh() {
  window.clearTimeout(moveTimer)
  moveTimer = window.setTimeout(() => void loadParcels(), 250)
}

function initializeMapLayers(styleReady = false) {
  if (!map || mapLayersInitialized || (!styleReady && !map.isStyleLoaded())) return
  mapLayersInitialized = true
  try {
    addAdministrativeRegionLayer()
    addFloodReferenceLayer()
    addParcelLayer()
    map.on('moveend', scheduleParcelRefresh)
    void loadParcels()
    void fetchDamageMap()
      .then((collection) => {
        if (!map) return
        hasDamageFeatures.value = Boolean(collection.features?.length)
        addDamageLayer(collection)
        if (!collection.features?.length) {
          damageStatus.value = 'No completed flood assessment is available; parcel data status is shown separately.'
        }
      })
      .catch(() => {
        damageStatus.value = 'Flood assessment unavailable. Only reference layers remain visible.'
      })
  } catch (error) {
    mapLayersInitialized = false
    parcelStatus.value = error instanceof Error
      ? `Map layers could not be initialized: ${error.message}`
      : 'Map layers could not be initialized.'
  }
}

onMounted(() => {
  if (!mapToken || !mapElement.value) return

  mapboxgl.accessToken = mapToken
  map = new mapboxgl.Map({
    container: mapElement.value,
    style: 'mapbox://styles/mapbox/streets-v12',
    center: [121.774, 12.8797],
    zoom: 5,
    attributionControl: true,
  })
  map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'top-right')
  map.once('load', () => {
    window.clearTimeout(mapStartupTimer)
    initializeMapLayers(true)
  })
  initializeMapLayers()
  mapStartupTimer = window.setTimeout(() => {
    if (!mapLayersInitialized) {
      parcelStatus.value = 'Map tiles did not load. Check the Mapbox token and network connection.'
    }
  }, 12000)
  resizeObserver = new ResizeObserver(() => map?.resize())
  resizeObserver.observe(mapElement.value)
})

onBeforeUnmount(() => {
  window.clearTimeout(moveTimer)
  window.clearTimeout(mapStartupTimer)
  requestSequence += 1
  resizeObserver?.disconnect()
  map?.remove()
  map = undefined
})
</script>
