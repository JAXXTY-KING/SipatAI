<template>
  <section class="map-frame parcel-map-frame" aria-label="Live satellite clouds, rainfall screening, wind forecast, and farm assessment map">
    <div v-if="mapToken" ref="mapElement" class="map-canvas"></div>
    <canvas v-if="mapToken" ref="windCanvas" class="wind-forecast-canvas" aria-hidden="true"></canvas>
    <div v-if="!mapToken" class="map-message" role="status">
      <strong>Map service not configured</strong>
      <span>Set a restricted public Mapbox token in frontend/.env.local to display the map.</span>
    </div>
    <p v-if="mapError" class="map-error-banner" role="alert">{{ mapError }}</p>

    <details v-if="mapToken" class="parcel-map-tools" aria-label="Map layers and data">
      <summary>Map layers <span aria-hidden="true">＋</span></summary>
      <div class="map-tools-content">
        <p class="map-tools-heading">WEATHER &amp; FLOOD MONITORING</p>
        <label class="weather-layer-select">
          Weather type
          <select v-model="selectedWeatherLayer" aria-label="Weather display" @change="updateWeatherLayer">
            <option v-for="layer in weatherLayers" :key="layer.value" :value="layer.value">{{ layer.label }}</option>
          </select>
        </label>
        <p class="weather-layer-description">{{ selectedWeatherLayerDescription }}</p>
        <p v-if="isGridWeatherMode && floodScreeningStatus" class="parcel-map-status" role="status" aria-live="polite">{{ floodScreeningStatus }}</p>
        <button
          v-if="isGridWeatherMode"
          class="parcel-refresh-button"
          type="button"
          :disabled="isLoadingFloodScreening"
          @click="loadFloodScreening"
        >
          {{ isLoadingFloodScreening ? 'Refreshing forecast…' : isRainfallScreeningActive ? 'Refresh rainfall screening' : 'Refresh weather forecast' }}
        </button>

        <details class="map-tools-group">
          <summary>Farm data &amp; reference</summary>
          <div class="map-tools-group-content">
            <label class="map-layer-toggle">
              <input v-model="showParcels" type="checkbox" @change="setParcelVisibility">
              <span class="parcel-swatch"></span>
              Farm parcels
            </label>
            <label class="map-layer-toggle">
              <input v-model="showDamage" type="checkbox" :disabled="!hasDamageFeatures" @change="setDamageVisibility">
              <span class="damage-swatch"></span>
              Completed assessment
            </label>
            <label class="map-layer-toggle">
              <input v-model="showRegions" type="checkbox" @change="setRegionVisibility">
              <span class="region-swatch"></span>
              Administrative boundaries
            </label>
            <button
              class="parcel-refresh-button"
              type="button"
              :disabled="isLoadingParcels"
              @click="loadParcels"
            >
              {{ isLoadingParcels ? 'Refreshing parcels…' : 'Refresh farm parcels' }}
            </button>
            <p class="parcel-map-status" role="status" aria-live="polite">{{ parcelStatus }}</p>
            <p v-if="damageStatus" class="parcel-map-status" role="status">{{ damageStatus }}</p>
          </div>
        </details>

        <details class="map-tools-group map-source-details">
          <summary>Sources &amp; limitations</summary>
          <div class="map-tools-group-content">
            <p class="parcel-map-attribution">
              Rainfall screening: <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Open-Meteo</a> 72-hour model forecast and elevation.
              Prototype thresholds are unvalidated; this is not a flood boundary, probability, typhoon track, or official warning.
              Consult <a href="https://www.pagasa.dost.gov.ph/" target="_blank" rel="noreferrer">PAGASA</a> for official advisories.
            </p>
            <p class="parcel-map-attribution">
              Satellite clouds: <a href="https://www.data.jma.go.jp/mscweb/data/himawari/sat_img.php?area=se1" target="_blank" rel="noreferrer">JMA Himawari-9</a>, Southeast Asia sector; recent timestamped frames refresh every 10 minutes.
            </p>
            <p class="parcel-map-attribution">
              Wind: <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Open-Meteo</a> model forecast, not an official PAGASA feed.
            </p>
            <p class="parcel-map-attribution">
              Temperature, precipitation, pressure, rainfall screening, and wind: <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Open-Meteo</a> forecast model. Grid colors show model guidance, not ground observations.
            </p>
            <p class="parcel-map-attribution">
              Administrative boundaries: <a href="https://simplemaps.com/gis/country/ph" target="_blank" rel="noreferrer">SimpleMaps</a>, CC BY 4.0; not farm parcels.
            </p>
          </div>
        </details>
      </div>
    </details>

    <aside
      v-if="mapToken && isSatelliteImageActive"
      class="satellite-live-status"
      :class="{ 'satellite-live-status-error': satelliteImageStatus.startsWith('Animation unavailable:') }"
      role="status"
      aria-live="polite"
    >
      <span class="satellite-live-indicator" aria-hidden="true"></span>
      <span>
        <strong>Live satellite clouds</strong>
        <small>{{ satelliteImageStatus }}</small>
      </span>
      <button type="button" :disabled="isLoadingSatelliteImage || satelliteFrames.length < 2" @click="toggleSatellitePlayback">
        {{ isSatellitePlaying ? 'Pause' : 'Play' }}
      </button>
      <button type="button" :disabled="isLoadingSatelliteImage" @click="loadSatelliteImage">
        {{ isLoadingSatelliteImage ? 'Loading…' : 'Refresh' }}
      </button>
      <a href="https://www.data.jma.go.jp/mscweb/data/himawari/sat_img.php?area=se1" target="_blank" rel="noreferrer">JMA</a>
    </aside>

    <aside v-if="mapToken && isWindForecastActive" class="wind-forecast-controls" aria-label="Wind forecast playback">
      <div class="wind-forecast-heading">
        <strong>Wind · {{ windForecastValidTime }}</strong>
        <button type="button" :disabled="isLoadingWindForecast || windForecastTimes.length < 2" @click="toggleWindForecastPlayback">
          {{ isWindForecastPlaying ? 'Pause' : 'Play' }}
        </button>
      </div>
      <input
        v-model.number="windForecastIndex"
        type="range"
        min="0"
        :max="Math.max(0, windForecastTimes.length - 1)"
        :disabled="isLoadingWindForecast || windForecastTimes.length < 2"
        aria-label="Forecast hour"
        @input="drawWindForecast"
      >
      <small>{{ windForecastStatus }}</small>
      <div class="wind-forecast-scale"><span>Light</span><i></i><span>Strong</span></div>
    </aside>

    <details v-if="mapToken" class="map-legend parcel-legend">
      <summary>Legend</summary>
      <div class="parcel-legend-items">
        <span v-if="showRegions"><i class="region-legend-mark"></i> Administrative region · reference only</span>
        <span v-if="showParcels"><i class="parcel-legend-mark"></i> Imported farm parcel</span>
        <span v-if="showDamage && hasDamageFeatures"><i class="damage-legend-mark"></i> Completed flood assessment</span>
        <span v-if="isRainfallScreeningActive"><i class="flood-screening-legend-mark"></i> Watch / elevated rainfall screening · prototype</span>
        <span v-if="isSatelliteImageActive"><i class="satellite-image-legend-mark"></i> Live cloud-only Himawari-9 imagery</span>
        <span v-if="isWindForecastActive"><i class="wind-forecast-legend-mark"></i> Forecast wind direction and speed · Open-Meteo</span>
        <span v-if="isWeatherGridActive"><i class="weather-legend-mark"></i> {{ selectedWeatherLayerLabel }} · Open-Meteo forecast grid</span>
      </div>
      <div v-if="isWeatherGridActive" class="weather-map-scale" :class="`weather-scale-${selectedWeatherLayer}`">
        <strong>{{ weatherScaleTitle }}</strong>
        <div class="weather-map-gradient"></div>
        <div class="weather-map-scale-labels">
          <span>{{ weatherScaleMinimum }}</span>
          <span>{{ weatherScaleMaximum }}</span>
        </div>
      </div>
    </details>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import mapboxgl from 'mapbox-gl'
import { fetchDamageMap, fetchFloodScreening, fetchHimawariFrames, fetchHimawariImage, fetchParcelMap, fetchWindForecast } from '../api/client'
import { severityColors } from '../map/severity'

const props = defineProps({
  initialLocation: { type: Object, default: null },
})
const emit = defineEmits(['location-selected'])
const mapToken = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN
const weatherLayers = [
  { value: 'rainfall', label: 'Rainfall screening', description: '72-hour model rainfall and low-elevation screening.' },
  { value: 'clouds', label: 'Clouds · live satellite', description: 'Recent JMA Himawari cloud imagery with playback.' },
  { value: 'wind', label: 'Wind · 72-hour forecast', description: 'Animated Open-Meteo wind speed and direction forecast.' },
  { value: 'precipitation', label: 'Precipitation · next 6 hours', description: 'Open-Meteo forecast precipitation total for the next six hours.' },
  { value: 'temperature', label: 'Temperature · forecast', description: 'Open-Meteo 2 m air temperature for the first forecast hour.' },
  { value: 'pressure', label: 'Pressure · forecast', description: 'Open-Meteo mean sea-level pressure for the first forecast hour.' },
]
const mapElement = ref(null)
const windCanvas = ref(null)
const parcelStatus = ref('Waiting for parcel data…')
const mapError = ref('')
const damageStatus = ref('')
const showRegions = ref(false)
const showParcels = ref(true)
const showDamage = ref(true)
const satelliteObservedAt = ref('')
const satelliteImageBandLabel = ref('')
const satelliteImageStatus = ref('Connecting to JMA…')
const isLoadingSatelliteImage = ref(false)
const satelliteFrames = ref([])
const isSatellitePlaying = ref(false)
const satellitePlaybackEnabled = ref(true)
const windForecastStatus = ref('Loading hourly wind forecast…')
const isLoadingWindForecast = ref(false)
const windForecastTimes = ref([])
const windForecastIndex = ref(0)
const isWindForecastPlaying = ref(true)
const windForecastValidTime = computed(() => {
  const forecastTime = windForecastTimes.value[windForecastIndex.value]
  return forecastTime
    ? new Date(forecastTime).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    : 'loading'
})
const floodScreeningCollection = ref(null)
const floodScreeningError = ref('')
const isLoadingFloodScreening = ref(false)
const selectedWeatherLayer = ref('rainfall')
const isRainfallScreeningActive = computed(() => selectedWeatherLayer.value === 'rainfall')
const isSatelliteImageActive = computed(() => selectedWeatherLayer.value === 'clouds')
const isWindForecastActive = computed(() => selectedWeatherLayer.value === 'wind')
const isWeatherGridActive = computed(() => (
  ['precipitation', 'temperature', 'pressure'].includes(selectedWeatherLayer.value)
))
const isGridWeatherMode = computed(() => (
  isRainfallScreeningActive.value || isWeatherGridActive.value
))
const floodScreeningStatus = computed(() => {
  if (isLoadingFloodScreening.value) return 'Loading nationwide model forecast grid…'
  if (floodScreeningError.value) return floodScreeningError.value
  const collection = floodScreeningCollection.value
  if (!collection) return ''

  const updatedAt = new Date(collection.fetched_at).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })
  if (isRainfallScreeningActive.value) {
    const screeningCells = collection.features.filter((feature) => (
      ['watch', 'elevated'].includes(feature.properties?.screening_level)
    )).length
    return `${screeningCells} watch/elevated cells shown · updated ${updatedAt} · refreshes every 15 min`
  }
  const gridCells = collection.features.length
  const resolution = collection.grid_resolution_degrees
  const forecastStart = collection.features[0]?.properties?.forecast_start
  return `${gridCells} forecast cells${resolution ? ` · ${resolution}° grid` : ''} · from ${forecastStart} UTC · updated ${updatedAt}`
})
const selectedWeatherLayerLabel = computed(() => (
  weatherLayers.find((layer) => layer.value === selectedWeatherLayer.value)?.label ?? 'weather'
))
const selectedWeatherLayerDescription = computed(() => (
  weatherLayers.find((layer) => layer.value === selectedWeatherLayer.value)?.description ?? ''
))
const weatherScaleTitle = computed(() => ({
  precipitation: 'Precipitation · next 6 h (mm)',
  temperature: 'Air temperature · °C',
  pressure: 'Sea-level pressure · hPa',
}[selectedWeatherLayer.value] ?? ''))
const weatherScaleMinimum = computed(() => ({
  precipitation: '0 mm',
  temperature: '−5 °C',
  pressure: '980 hPa',
}[selectedWeatherLayer.value] ?? ''))
const weatherScaleMaximum = computed(() => ({
  precipitation: '50+ mm',
  temperature: '40 °C',
  pressure: '1040 hPa',
}[selectedWeatherLayer.value] ?? ''))
const isLoadingParcels = ref(false)
const hasDamageFeatures = ref(false)
let map
let selectionMarker
let resizeObserver
let moveTimer
let mapStartupTimer
let requestSequence = 0
let floodScreeningRequestSequence = 0
let satelliteRequestSequence = 0
let windForecastRequestSequence = 0
let satelliteRefreshTimer
let satelliteAnimationTimer
let satelliteImageUrls = []
let mapLayersInitialized = false
let windForecast
let windParticles = []
let windAnimationFrame
let windForecastTimer
let windPlaybackTimer

const HIMAWARI_SECTOR_COORDINATES = [
  [80, 60],
  [150, 60],
  [150, -10],
  [80, -10],
]

function currentSatelliteBand() {
  const philippineHour = (new Date().getUTCHours() + 8) % 24
  return philippineHour >= 6 && philippineHour < 18 ? 'b03' : 'b13'
}

async function makeCloudOnlyImage(imageBlob) {
  const imageBitmap = await createImageBitmap(imageBlob)
  try {
    const canvas = document.createElement('canvas')
    canvas.width = imageBitmap.width
    canvas.height = imageBitmap.height
    const context = canvas.getContext('2d', { willReadFrequently: true })
    if (!context) throw new Error('Cloud transparency could not be prepared.')
    context.drawImage(imageBitmap, 0, 0)
    const imageData = context.getImageData(0, 0, canvas.width, canvas.height)
    const pixels = imageData.data
    const luminanceMap = new Float32Array(canvas.width * canvas.height)
    const cloudMask = new Uint8Array(canvas.width * canvas.height)
    for (let y = 0; y < canvas.height; y += 1) {
      for (let x = 0; x < canvas.width; x += 1) {
        const index = (y * canvas.width + x) * 4
        const red = pixels[index]
        const green = pixels[index + 1]
        const blue = pixels[index + 2]
        const pixelIndex = y * canvas.width + x
        const luminance = (red * 0.299) + (green * 0.587) + (blue * 0.114)
        luminanceMap[pixelIndex] = luminance
        cloudMask[pixelIndex] = green > red * 1.15 && green > blue * 1.12 && green - red > 14 ? 1 : 0
        if (x < 10 || y < 10 || x >= canvas.width - 10 || y >= canvas.height - 18) {
          pixels[index + 3] = 0
        }
      }
    }
    const gridRows = new Uint8Array(canvas.height)
    const gridColumns = new Uint8Array(canvas.width)
    for (let y = 2; y < canvas.height - 2; y += 1) {
      let edgeStrength = 0
      for (let x = 4; x < canvas.width - 4; x += 1) {
        edgeStrength += Math.abs(luminanceMap[y * canvas.width + x] - luminanceMap[(y - 1) * canvas.width + x])
      }
      gridRows[y] = edgeStrength / (canvas.width - 8) > 60 ? 1 : 0
    }
    for (let x = 2; x < canvas.width - 2; x += 1) {
      let edgeStrength = 0
      for (let y = 4; y < canvas.height - 4; y += 1) {
        edgeStrength += Math.abs(luminanceMap[y * canvas.width + x] - luminanceMap[y * canvas.width + x - 1])
      }
      gridColumns[x] = edgeStrength / (canvas.height - 8) > 60 ? 1 : 0
    }
    for (let y = 1; y < canvas.height - 1; y += 1) {
      for (let x = 1; x < canvas.width - 1; x += 1) {
        const pixelIndex = y * canvas.width + x
        const index = pixelIndex * 4
        let neighborhood = 0
        for (let offsetY = -1; offsetY <= 1; offsetY += 1) {
          for (let offsetX = -1; offsetX <= 1; offsetX += 1) {
            neighborhood += luminanceMap[(y + offsetY) * canvas.width + x + offsetX]
          }
        }
        const average = neighborhood / 9
        const sharpened = Math.max(0, Math.min(255, luminanceMap[pixelIndex] + ((luminanceMap[pixelIndex] - average) * 1.8)))
        const cloudContrast = Math.max(0, Math.min(255, (sharpened - 38) * 1.8))
        const cloudStrength = Math.max(0, Math.min(1, (cloudContrast - 24) / 130))
        const cloudOpacity = Math.min(0.97, Math.pow(cloudStrength, 0.52))
        const isImageEdge = x < 10 || y < 10 || x >= canvas.width - 10 || y >= canvas.height - 18
        const isGridLine = gridRows[y - 1] || gridRows[y] || gridRows[y + 1]
          || gridColumns[x - 1] || gridColumns[x] || gridColumns[x + 1]
        if (cloudMask[pixelIndex] || isImageEdge || isGridLine) {
          pixels[index + 3] = 0
          continue
        }
        const cloudTone = Math.min(255, 52 + cloudContrast * 0.78)
        pixels[index] = cloudTone
        pixels[index + 1] = cloudTone
        pixels[index + 2] = cloudTone
        pixels[index + 3] = Math.round(cloudOpacity * 255)
      }
    }
    context.putImageData(imageData, 0, 0)
    const transparentBlob = await new Promise((resolve, reject) => {
      canvas.toBlob((blob) => {
        if (blob) resolve(blob)
        else reject(new Error('Cloud transparency could not be encoded.'))
      }, 'image/png')
    })
    return transparentBlob
  } finally {
    imageBitmap.close()
  }
}

async function loadSatelliteImage() {
  const currentRequest = ++satelliteRequestSequence
  const requestedBand = currentSatelliteBand()
  isLoadingSatelliteImage.value = true
  satelliteImageStatus.value = 'Loading recent JMA satellite frames…'
  try {
    stopSatellitePlayback()
    const response = await fetchHimawariFrames(requestedBand)
    const frames = Array.isArray(response.frames) ? response.frames : []
    if (frames.length < 2) throw new Error('JMA has not provided enough recent frames for animation.')
    const loadedFrames = await Promise.all(frames.map(async (frame) => ({
      ...frame,
      image: await makeCloudOnlyImage((await fetchHimawariImage(requestedBand, frame.time_code)).image),
    })))
    if (currentRequest !== satelliteRequestSequence) return

    const nextUrls = loadedFrames.map((frame) => URL.createObjectURL(frame.image))
    const chronologicalFrames = loadedFrames.reverse()
    const chronologicalUrls = nextUrls.reverse()
    if (!map?.getSource('himawari-live')) {
      if (!map?.getLayer('admin-region-fill')) {
        chronologicalUrls.forEach((url) => URL.revokeObjectURL(url))
        throw new Error('The map is not ready to display satellite imagery.')
      }
      map.addSource('himawari-live', {
        type: 'image',
        url: chronologicalUrls[0],
        coordinates: HIMAWARI_SECTOR_COORDINATES,
      })
      map.addLayer({
        id: 'himawari-live-image',
        type: 'raster',
        source: 'himawari-live',
        layout: { visibility: isSatelliteImageActive.value ? 'visible' : 'none' },
        paint: {
          'raster-opacity': 0.88,
          'raster-fade-duration': 0,
        },
      })
    } else {
      const oldImageUrls = satelliteImageUrls
      map.getSource('himawari-live').updateImage({
        url: chronologicalUrls[0],
        coordinates: HIMAWARI_SECTOR_COORDINATES,
      })
      if (oldImageUrls.length) map.once('idle', () => oldImageUrls.forEach((url) => URL.revokeObjectURL(url)))
    }
    satelliteFrames.value = chronologicalFrames
    satelliteImageUrls = chronologicalUrls
    satelliteFrameIndex.value = 0
    satelliteObservedAt.value = chronologicalFrames[0].observed_at || 'Timestamp unavailable'
    satelliteImageBandLabel.value = requestedBand === 'b03' ? 'Visible cloud detail' : 'Infrared cloud detail'
    satelliteImageStatus.value = `${satelliteImageBandLabel.value} · ${chronologicalFrames[0].observed_at} · ready to play`
    if (isSatelliteImageActive.value && satellitePlaybackEnabled.value) startSatellitePlayback()
  } catch (error) {
    if (currentRequest !== satelliteRequestSequence) return
    satelliteImageStatus.value = `Animation unavailable: ${error instanceof Error ? error.message : 'service error'}`
  } finally {
    if (currentRequest === satelliteRequestSequence) isLoadingSatelliteImage.value = false
  }
}

function stopSatellitePlayback() {
  window.clearInterval(satelliteAnimationTimer)
  isSatellitePlaying.value = false
}

function startSatellitePlayback() {
  if (!map || satelliteFrames.value.length < 2 || !satelliteImageUrls.length) return
  stopSatellitePlayback()
  isSatellitePlaying.value = true
  satelliteAnimationTimer = window.setInterval(() => {
    if (!map || !isSatelliteImageActive.value) {
      stopSatellitePlayback()
      return
    }
    const nextIndex = (satelliteFrameIndex.value + 1) % satelliteFrames.value.length
    satelliteFrameIndex.value = nextIndex
    map.getSource('himawari-live')?.updateImage({
      url: satelliteImageUrls[nextIndex],
      coordinates: HIMAWARI_SECTOR_COORDINATES,
    })
    satelliteObservedAt.value = satelliteFrames.value[nextIndex].observed_at
    satelliteImageStatus.value = `${satelliteImageBandLabel.value} · ${satelliteObservedAt.value}`
  }, 800)
}

function toggleSatellitePlayback() {
  satellitePlaybackEnabled.value = !isSatellitePlaying.value
  if (satellitePlaybackEnabled.value) startSatellitePlayback()
  else stopSatellitePlayback()
}

function setSatelliteImageVisibility() {
  window.clearInterval(satelliteRefreshTimer)
  if (!isSatelliteImageActive.value) {
    stopSatellitePlayback()
    setLayerVisibility('himawari-live-image', false)
    return
  }
  setLayerVisibility('himawari-live-image', true)
  if (satelliteFrames.value.length && satellitePlaybackEnabled.value) startSatellitePlayback()
  else if (!satelliteFrames.value.length) void loadSatelliteImage()
  satelliteRefreshTimer = window.setInterval(() => void loadSatelliteImage(), 10 * 60 * 1000)
}

const satelliteFrameIndex = ref(0)

function setLayerVisibility(layerId, visible) {
  if (map?.getLayer(layerId)) {
    map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none')
  }
}

function setParcelVisibility() {
  setLayerVisibility('farm-parcel-fill', showParcels.value)
  setLayerVisibility('farm-parcel-outline', showParcels.value)
}

function focusLocation(coordinates) {
  if (!map) return
  const lngLat = [coordinates.longitude, coordinates.latitude]
  selectionMarker?.remove()
  selectionMarker = new mapboxgl.Marker({ color: '#277ca5' }).setLngLat(lngLat).addTo(map)
  map.flyTo({ center: lngLat, zoom: Math.max(map.getZoom(), 10), duration: 1200 })
}

watch(() => props.initialLocation, (coordinates) => {
  if (coordinates && map?.loaded()) focusLocation(coordinates)
})

defineExpose({ focusLocation })

function setDamageVisibility() {
  setLayerVisibility('flood-damage-fill', showDamage.value)
  setLayerVisibility('flood-damage-outline', showDamage.value)
}

function setRegionVisibility() {
  setLayerVisibility('admin-region-fill', showRegions.value)
  setLayerVisibility('admin-region-outline', showRegions.value)
}

function updateWeatherLayer() {
  const isGridMode = isGridWeatherMode.value
  setLayerVisibility('flood-screening-fill', isGridMode)
  setLayerVisibility('flood-screening-outline', isGridMode)
  setFloodScreeningDisplay()
  setSatelliteImageVisibility()
  setWindForecastVisibility()
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

function setFloodScreeningDisplay() {
  const fillLayer = 'flood-screening-fill'
  const outlineLayer = 'flood-screening-outline'
  if (!map?.getLayer(fillLayer)) return

  if (isRainfallScreeningActive.value) {
    const screeningFilter = ['in', ['get', 'screening_level'], ['literal', ['watch', 'elevated']]]
    map.setFilter(fillLayer, screeningFilter)
    map.setFilter(outlineLayer, screeningFilter)
    map.setPaintProperty(fillLayer, 'fill-color', [
      'match', ['get', 'screening_level'],
      'elevated', '#c83e3e',
      'watch', '#f0b52c',
      '#719b86',
    ])
    map.setPaintProperty(fillLayer, 'fill-opacity', 0.5)
    map.setPaintProperty(outlineLayer, 'line-opacity', 0.55)
    return
  }

  map.setFilter(fillLayer, null)
  map.setFilter(outlineLayer, null)
  const fieldAndStops = {
    precipitation: [
      'precipitation_6h_mm',
      [0, '#f2f7fa'], [0.1, '#8be0f2'], [1, '#30a9d8'],
      [5, '#4169e1'], [15, '#7b2cbf'], [30, '#e53935'], [50, '#8e0000'],
    ],
    temperature: [
      'temperature_2m_c',
      [-5, '#313695'], [0, '#4575b4'], [10, '#74add1'], [20, '#abd9e9'],
      [25, '#ffffbf'], [30, '#fdae61'], [35, '#f46d43'], [40, '#d73027'],
    ],
    pressure: [
      'pressure_msl_hpa',
      [980, '#762a83'], [990, '#af8dc3'], [1000, '#e7d4e8'], [1010, '#f7f7f7'],
      [1020, '#b8e186'], [1030, '#7fbc41'], [1040, '#276419'],
    ],
  }[selectedWeatherLayer.value]
  if (!fieldAndStops) return

  const [property, ...stops] = fieldAndStops
  map.setPaintProperty(fillLayer, 'fill-color', [
    'interpolate', ['linear'], ['to-number', ['get', property], 0],
    ...stops.flat(),
  ])
  map.setPaintProperty(fillLayer, 'fill-opacity', 0.6)
  map.setPaintProperty(outlineLayer, 'line-opacity', 0.2)
}

function addFloodScreeningLayer(collection) {
  if (!map || map.getSource('flood-screening')) return
  map.addSource('flood-screening', { type: 'geojson', data: collection })
  map.addLayer({
    id: 'flood-screening-fill',
    type: 'fill',
    source: 'flood-screening',
    layout: { visibility: isGridWeatherMode.value ? 'visible' : 'none' },
    paint: {
      'fill-color': [
        'match', ['get', 'screening_level'],
        'elevated', '#c83e3e',
        'watch', '#f0b52c',
        '#719b86',
      ],
      'fill-opacity': 0.5,
    },
    filter: ['in', ['get', 'screening_level'], ['literal', ['watch', 'elevated']]],
  }, 'admin-region-outline')
  map.addLayer({
    id: 'flood-screening-outline',
    type: 'line',
    source: 'flood-screening',
    layout: { visibility: isGridWeatherMode.value ? 'visible' : 'none' },
    paint: {
      'line-color': '#ffffff',
      'line-width': 0.35,
      'line-opacity': 0.55,
    },
    filter: ['in', ['get', 'screening_level'], ['literal', ['watch', 'elevated']]],
  }, 'admin-region-outline')
  map.on('click', 'flood-screening-fill', (event) => {
    const feature = event.features?.[0]
    if (!feature) return
    event.originalEvent.stopPropagation()
    const properties = feature.properties ?? {}
    const content = document.createElement('div')
    const heading = document.createElement('strong')
    heading.textContent = selectedWeatherLayer.value === 'rainfall'
      ? `${properties.screening_level === 'elevated' ? 'Higher' : properties.screening_level === 'watch' ? 'Watch' : 'Lower'} screening level`
      : `${selectedWeatherLayerLabel.value} forecast`
    content.append(heading)
    const details = selectedWeatherLayer.value === 'temperature'
      ? [['Air temperature (first forecast hour)', `${Number(properties.temperature_2m_c).toFixed(1)} °C`]]
      : selectedWeatherLayer.value === 'precipitation'
        ? [['Precipitation (next 6 hours)', `${Number(properties.precipitation_6h_mm).toFixed(1)} mm`]]
        : selectedWeatherLayer.value === 'pressure'
          ? [['Mean sea-level pressure (first forecast hour)', `${Number(properties.pressure_msl_hpa).toFixed(1)} hPa`]]
          : [
              ['Peak 24-hour rain (next 72 h)', `${Number(properties.rainfall_24h_mm).toFixed(1)} mm`],
              ['Forecast rain (next 72 h)', `${Number(properties.rainfall_72h_mm).toFixed(1)} mm`],
              ['Model elevation', properties.elevation_m == null ? 'Unavailable' : `${Number(properties.elevation_m).toFixed(0)} m`],
            ]
    for (const [label, value] of [...details, ['Forecast time (UTC)', properties.forecast_start]]) {
      const detail = document.createElement('p')
      detail.textContent = `${label}: ${value}`
      content.append(detail)
    }
    const note = document.createElement('small')
    note.textContent = selectedWeatherLayer.value === 'rainfall'
      ? 'Coarse prototype screening, not a flood prediction or official warning.'
      : 'Coarse model forecast grid; not a station observation.'
    content.append(note)
    new mapboxgl.Popup({ maxWidth: '18rem' })
      .setLngLat(event.lngLat)
      .setDOMContent(content)
      .addTo(map)
  })
  map.on('mouseenter', 'flood-screening-fill', () => { map.getCanvas().style.cursor = 'pointer' })
  map.on('mouseleave', 'flood-screening-fill', () => { map.getCanvas().style.cursor = '' })
  setFloodScreeningDisplay()
}

async function loadFloodScreening() {
  const currentRequest = ++floodScreeningRequestSequence
  isLoadingFloodScreening.value = true
  floodScreeningError.value = ''
  try {
    const collection = await fetchFloodScreening()
    if (currentRequest !== floodScreeningRequestSequence || !map) return
    if (!collection.features?.length) throw new Error('The forecast returned no map cells.')
    floodScreeningCollection.value = collection
    const screeningSource = map.getSource('flood-screening')
    if (screeningSource) screeningSource.setData(collection)
    else addFloodScreeningLayer(collection)
    setFloodScreeningDisplay()
  } catch (error) {
    if (currentRequest !== floodScreeningRequestSequence) return
    floodScreeningError.value = `Forecast unavailable: ${error instanceof Error ? error.message : 'service error'}`
  } finally {
    if (currentRequest === floodScreeningRequestSequence) isLoadingFloodScreening.value = false
  }
}

async function loadWindForecast() {
  const currentRequest = ++windForecastRequestSequence
  isLoadingWindForecast.value = true
  windForecastStatus.value = 'Loading hourly model wind forecast…'
  try {
    const collection = await fetchWindForecast()
    if (currentRequest !== windForecastRequestSequence || !map) return
    if (!collection.features?.length || !collection.forecast_times?.length) {
      throw new Error('The forecast returned no hourly wind data.')
    }
    windForecast = collection
    windForecastTimes.value = collection.forecast_times
    windForecastIndex.value = 0
    windParticles = []
    const fetched = new Date(collection.fetched_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    windForecastStatus.value = `${collection.features.length} grid points · updated ${fetched}`
    resizeWindCanvas()
    startWindParticleAnimation()
  } catch (error) {
    if (currentRequest !== windForecastRequestSequence) return
    windForecastStatus.value = `Wind forecast unavailable: ${error instanceof Error ? error.message : 'service error'}`
  } finally {
    if (currentRequest === windForecastRequestSequence) isLoadingWindForecast.value = false
  }
}

function resizeWindCanvas() {
  const canvas = windCanvas.value
  if (!canvas) return
  const ratio = window.devicePixelRatio || 1
  canvas.width = Math.round(canvas.clientWidth * ratio)
  canvas.height = Math.round(canvas.clientHeight * ratio)
  canvas.getContext('2d')?.setTransform(ratio, 0, 0, ratio, 0, 0)
}

function createWindParticle(bounds) {
  const intersectsForecastArea = bounds.getEast() > 114
    && bounds.getWest() < 130
    && bounds.getNorth() > 1.5
    && bounds.getSouth() < 25.5
  const west = intersectsForecastArea ? Math.max(bounds.getWest(), 114) : 114
  const east = intersectsForecastArea ? Math.min(bounds.getEast(), 130) : 130
  const south = intersectsForecastArea ? Math.max(bounds.getSouth(), 1.5) : 1.5
  const north = intersectsForecastArea ? Math.min(bounds.getNorth(), 25.5) : 25.5
  return {
    longitude: west + Math.random() * Math.max(east - west, 0.1),
    latitude: south + Math.random() * Math.max(north - south, 0.1),
  }
}

function nearestWindPoint(longitude, latitude) {
  const features = windForecast?.features
  if (!features?.length) return null
  let nearest = features[0]
  let nearestDistance = Number.POSITIVE_INFINITY
  for (const feature of features) {
    const [pointLongitude, pointLatitude] = feature.geometry.coordinates
    const longitudeDistance = (longitude - pointLongitude) * Math.cos(latitude * Math.PI / 180)
    const latitudeDistance = latitude - pointLatitude
    const distance = (longitudeDistance * longitudeDistance) + (latitudeDistance * latitudeDistance)
    if (distance < nearestDistance) {
      nearestDistance = distance
      nearest = feature
    }
  }
  return nearest
}

function windParticleColor(speed) {
  if (speed >= 17) return '#f03b43'
  if (speed >= 11) return '#ff8b38'
  if (speed >= 5) return '#ffd94d'
  return '#5bd4dd'
}

function drawWindForecastFrame(timestamp, deltaMilliseconds = 16) {
  const canvas = windCanvas.value
  const context = canvas?.getContext('2d')
  if (!map || !context || !windForecast || !isWindForecastActive.value) return
  const bounds = map.getBounds()
  const width = canvas.clientWidth
  const height = canvas.clientHeight
  context.clearRect(0, 0, width, height)
  if (!windParticles.length) {
    const particleCount = Math.min(420, Math.max(220, Math.round((width * height) / 1900)))
    windParticles = Array.from({ length: particleCount }, () => createWindParticle(bounds))
  }

  const hourIndex = Math.min(windForecastIndex.value, windForecastTimes.value.length - 1)
  const delta = Math.min(deltaMilliseconds, 40)
  context.lineWidth = 1.9
  context.lineCap = 'round'
  context.shadowBlur = 2
  for (let index = 0; index < windParticles.length; index += 1) {
    const particle = windParticles[index]
    if (!bounds.contains([particle.longitude, particle.latitude])) {
      windParticles[index] = createWindParticle(bounds)
      continue
    }
    const feature = nearestWindPoint(particle.longitude, particle.latitude)
    if (!feature) continue
    const properties = feature.properties
    const speed = Number(properties.wind_speed_10m_mps[hourIndex] ?? 0)
    const fromDirection = Number(properties.wind_direction_10m_deg[hourIndex] ?? 0)
    const direction = (fromDirection + 180) * Math.PI / 180
    const distance = speed * delta * 0.00008
    const oldLongitude = particle.longitude
    const oldLatitude = particle.latitude
    particle.longitude += Math.sin(direction) * distance / Math.max(0.25, Math.cos(oldLatitude * Math.PI / 180))
    particle.latitude += Math.cos(direction) * distance
    if (
      particle.longitude < 114 || particle.longitude > 130
      || particle.latitude < 1.5 || particle.latitude > 25.5
    ) {
      windParticles[index] = createWindParticle(bounds)
      continue
    }
    const start = map.project([oldLongitude, oldLatitude])
    const end = map.project([particle.longitude, particle.latitude])
    const screenDistance = Math.hypot(end.x - start.x, end.y - start.y)
    if (screenDistance < 0.01) continue
    const trailLength = 8 + Math.min(speed, 30) * 0.5
    const unitX = (end.x - start.x) / screenDistance
    const unitY = (end.y - start.y) / screenDistance
    context.strokeStyle = windParticleColor(speed)
    context.globalAlpha = 0.9
    context.shadowColor = '#12202c'
    context.beginPath()
    context.moveTo(end.x - (unitX * trailLength), end.y - (unitY * trailLength))
    context.lineTo(end.x, end.y)
    context.stroke()
  }
  context.globalAlpha = 1
  context.shadowBlur = 0
}

function startWindParticleAnimation() {
  if (!isWindForecastActive.value || !windForecast || !windCanvas.value || windAnimationFrame) return
  let previousTimestamp = 0
  const animate = (timestamp) => {
    drawWindForecastFrame(timestamp, previousTimestamp ? timestamp - previousTimestamp : 16)
    previousTimestamp = timestamp
    windAnimationFrame = window.requestAnimationFrame(animate)
  }
  windAnimationFrame = window.requestAnimationFrame(animate)
}

function setWindForecastVisibility() {
  if (!isWindForecastActive.value) {
    window.cancelAnimationFrame(windAnimationFrame)
    windAnimationFrame = undefined
    const context = windCanvas.value?.getContext('2d')
    if (context && windCanvas.value) context.clearRect(0, 0, windCanvas.value.clientWidth, windCanvas.value.clientHeight)
    return
  }
  if (windForecast) startWindParticleAnimation()
  else void loadWindForecast()
}

function toggleWindForecastPlayback() {
  isWindForecastPlaying.value = !isWindForecastPlaying.value
}

function drawWindForecast() {
  if (windCanvas.value) drawWindForecastFrame(performance.now())
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
    addParcelLayer()
    if (isSatelliteImageActive.value) setSatelliteImageVisibility()
    void loadFloodScreening()
    if (isWindForecastActive.value) {
      void loadWindForecast()
    }
    windForecastTimer = window.setInterval(() => {
      if (isWindForecastActive.value) void loadWindForecast()
    }, 15 * 60 * 1000)
    windPlaybackTimer = window.setInterval(() => {
      if (!isWindForecastActive.value || !isWindForecastPlaying.value || windForecastTimes.value.length < 2) return
      windForecastIndex.value = (windForecastIndex.value + 1) % windForecastTimes.value.length
      drawWindForecast()
    }, 1600)
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
    mapError.value = parcelStatus.value
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
  map.on('click', (event) => {
    selectionMarker?.remove()
    selectionMarker = new mapboxgl.Marker({ color: '#277ca5' }).setLngLat(event.lngLat).addTo(map)
    emit('location-selected', {
      latitude: Number(event.lngLat.lat.toFixed(6)),
      longitude: Number(event.lngLat.lng.toFixed(6)),
    })
  })
  map.once('load', () => {
    window.clearTimeout(mapStartupTimer)
    mapError.value = ''
    initializeMapLayers(true)
    if (props.initialLocation) focusLocation(props.initialLocation)
  })
  initializeMapLayers()
  mapStartupTimer = window.setTimeout(() => {
    if (!mapLayersInitialized) {
      mapError.value = 'Map tiles did not load. Check the Mapbox token and network connection.'
      parcelStatus.value = mapError.value
    }
  }, 12000)
  resizeObserver = new ResizeObserver(() => {
    map?.resize()
    resizeWindCanvas()
  })
  resizeObserver.observe(mapElement.value)
})

onBeforeUnmount(() => {
  window.clearTimeout(moveTimer)
  window.clearTimeout(mapStartupTimer)
  window.clearInterval(satelliteRefreshTimer)
  window.clearInterval(windForecastTimer)
  window.clearInterval(windPlaybackTimer)
  requestSequence += 1
  floodScreeningRequestSequence += 1
  satelliteRequestSequence += 1
  windForecastRequestSequence += 1
  window.cancelAnimationFrame(windAnimationFrame)
  satelliteImageUrls.forEach((url) => URL.revokeObjectURL(url))
  satelliteImageUrls = []
  resizeObserver?.disconnect()
  map?.remove()
  map = undefined
})
</script>
