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
        <div class="weather-type-grid" role="radiogroup" aria-label="Weather display">
          <button
            v-for="layer in weatherLayers"
            :key="layer.value"
            type="button"
            role="radio"
            class="weather-type-chip"
            :class="{ 'weather-type-chip-active': selectedWeatherLayer === layer.value }"
            :aria-checked="selectedWeatherLayer === layer.value"
            @click="selectWeatherLayer(layer.value)"
          >
            <span class="weather-type-icon" aria-hidden="true">{{ layer.icon }}</span>
            <span>{{ layer.short }}</span>
          </button>
        </div>
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

        <details class="map-tools-group susceptibility-group" open>
          <summary>
            Flood-prone areas · prediction
            <span class="ai-flood-badge" :class="susceptibilityStatus?.ready ? 'ai-flood-badge-ready' : 'ai-flood-badge-off'">
              {{ susceptibilityStatus?.ready ? 'Model ready' : 'Not ready' }}
            </span>
          </summary>
          <div class="map-tools-group-content">
            <p class="parcel-map-attribution">
              A MindSpore model learned where water collects from real terrain (Copernicus DEM) and 36 years of Landsat water history,
              so it works anywhere in the Philippines. Combined with the real rainfall forecast for the province.
            </p>
            <p v-if="susceptibilityStatus && !susceptibilityStatus.ready" class="parcel-map-status" role="status">{{ susceptibilityStatus.reason }}</p>
            <p v-else-if="susceptibilityStatus?.heldout_province_auc" class="parcel-map-status">
              Held-out provinces: AUC {{ susceptibilityStatus.heldout_province_auc.toFixed(2) }}
              <template v-if="susceptibilityStatus.observed_flood_validation"> · vs satellite-observed floods: AUC {{ susceptibilityStatus.observed_flood_validation.auc.toFixed(2) }}</template>
            </p>
            <button
              class="parcel-refresh-button"
              type="button"
              :disabled="isPredicting || !susceptibilityStatus?.ready"
              @click="runSusceptibility"
            >
              {{ isPredicting ? 'Reading terrain & running MindSpore…' : 'Show flood-prone areas here' }}
            </button>
            <p v-if="susceptibilityError" class="parcel-map-status ai-flood-error" role="alert">{{ susceptibilityError }}</p>
            <div v-if="susceptibilityResult" class="ai-flood-result susceptibility-result" role="status">
              <strong>{{ susceptibilityResult.statistics.high_km2 }} km² high · {{ susceptibilityResult.statistics.moderate_km2 }} km² moderate susceptibility</strong>
              <span>of {{ susceptibilityResult.statistics.land_km2 }} km² land in this {{ susceptibilityResult.statistics.tile_km2 }} km² area</span>
              <span v-if="susceptibilityResult.forecast">
                Forecast for {{ susceptibilityResult.forecast.province }}: {{ susceptibilityResult.forecast.rainfall_24h_mm }} mm in the wettest 24 h,
                {{ susceptibilityResult.forecast.rainfall_72h_mm }} mm over 72 h
              </span>
              <small><b>{{ susceptibilityResult.outlook }}</b></small>
              <small>Red = high, amber = moderate susceptibility. A relative score from terrain and water history, not a flood warning or a measured depth.</small>
              <button class="parcel-refresh-button" type="button" @click="clearSusceptibility">Clear overlay</button>
            </div>
          </div>
        </details>

        <details class="map-tools-group scan-group" open>
          <summary>
            Nationwide satellite scan
            <span class="ai-flood-badge" :class="scanSummary?.tiles_scanned ? 'ai-flood-badge-ready' : 'ai-flood-badge-off'">
              {{ scanSummary ? `${(scanSummary.coverage_fraction * 100).toFixed(1)}% scanned` : 'loading' }}
            </span>
          </summary>
          <div class="map-tools-group-content">
            <p v-if="scanSummary?.tiles_scanned" class="parcel-map-status" role="status">
              {{ scanSummary.tiles_scanned.toLocaleString() }} of {{ scanSummary.tiles_total.toLocaleString() }} Philippine land tiles scanned by MindSpore ·
              {{ scanSummary.flooded_km2.toLocaleString() }} km² of flood water detected in {{ scanSummary.tiles_with_flooding }} tiles ·
              Sentinel-1 passes {{ scanSummary.radar_dates[0] }} to {{ scanSummary.radar_dates[1] }}
            </p>
            <p v-else class="parcel-map-status" role="status">No tiles scanned yet. Scans run from the backend job (see README).</p>
            <label class="map-layer-toggle">
              <input v-model="showScan" type="checkbox" @change="refreshScanOverlays">
              <span class="scan-swatch"></span>
              Show detected floods (scanned tiles)
            </label>
            <small class="parcel-map-attribution">
              Newest real Sentinel-1 radar pass per tile. Areas not yet scanned are blank, not “no flood”.
              Radar-only tiles (cloud cover) are less accurate.
            </small>
          </div>
        </details>

        <details class="map-tools-group ai-flood-group" open>
          <summary>
            MindSpore flood AI
            <span class="ai-flood-badge" :class="aiModelStatus?.ready ? 'ai-flood-badge-ready' : 'ai-flood-badge-off'">
              {{ aiModelStatus?.ready ? 'Model ready' : 'Not ready' }}
            </span>
          </summary>
          <div class="map-tools-group-content">
            <p class="parcel-map-attribution">
              Runs a MindSpore ResNet-50 U-Net on real Sentinel-1 radar and Sentinel-2 optical imagery for a 5 km tile at the selected point
              (or the map centre). Experimental: not an official flood boundary.
            </p>
            <p v-if="aiModelStatus && !aiModelStatus.ready" class="parcel-map-status" role="status">{{ aiModelStatus.reason }}</p>
            <p v-else-if="aiModelStatus?.test_metrics" class="parcel-map-status">
              Trained on human-labelled Sen1Floods11 floods. Unseen test floods, IoU:
              {{ aiModelStatus.test_metrics.radar_optical.iou.toFixed(2) }} with optical imagery ·
              {{ aiModelStatus.test_metrics.radar_only.iou.toFixed(2) }} radar-only (under cloud)
            </p>
            <label class="weather-layer-select">
              Event date (optional, for past floods)
              <input v-model="aiEventDate" type="date" :max="todayIso" aria-label="Flood event date">
            </label>
            <button
              class="parcel-refresh-button"
              type="button"
              :disabled="isAnalyzingFlood || !aiModelStatus?.ready"
              @click="runFloodAnalysis"
            >
              {{ isAnalyzingFlood ? 'Reading Sentinel data & running MindSpore…' : 'Analyse flood extent here' }}
            </button>
            <p v-if="aiAnalysisError" class="parcel-map-status ai-flood-error" role="alert">{{ aiAnalysisError }}</p>
            <div v-if="aiResult" class="ai-flood-result" role="status">
              <strong>{{ aiResult.statistics.flooded_area_km2 }} km² flooded</strong>
              <span>{{ (aiResult.statistics.flooded_fraction * 100).toFixed(1) }}% of the {{ aiResult.statistics.tile_area_km2 }} km² tile</span>
              <span v-if="aiResult.cropland" class="ai-flood-cropland">
                🌾 {{ aiResult.cropland.flooded_cropland_km2 }} km² of {{ aiResult.cropland.cropland_area_km2 }} km² cropland flooded
                <template v-if="aiResult.cropland.flooded_share_of_cropland !== null">({{ (aiResult.cropland.flooded_share_of_cropland * 100).toFixed(1) }}%)</template>
              </span>
              <small v-if="aiResult.cropland">Blue = flooded land · orange = flooded cropland (ESA WorldCover 2021)</small>
              <div v-if="aiResult.field_summary" class="ai-field-summary">
                <strong>{{ aiResult.field_summary.fields_affected }} of {{ aiResult.field_summary.fields_analysed }} mapped fields affected</strong>
                <span>{{ aiResult.field_summary.flooded_field_area_ha }} ha flooded of {{ aiResult.field_summary.field_area_ha }} ha of fields</span>
                <span class="ai-field-counts">
                  <i class="ai-dot" :style="{ background: severityColors.Severe }"></i>Severe {{ aiResult.field_summary.severity_counts.Severe }}
                  <i class="ai-dot" :style="{ background: severityColors.Moderate }"></i>Moderate {{ aiResult.field_summary.severity_counts.Moderate }}
                  <i class="ai-dot" :style="{ background: severityColors.Light }"></i>Light {{ aiResult.field_summary.severity_counts.Light }}
                </span>
                <small>Field outlines: Fields of The World {{ aiResult.field_summary.field_year }} (CC-BY-4.0), detected from Sentinel-2, not legal parcels. Click a field for details. Classes are by flooded share (60%+, 30–60%, 10–30%), a prototype display scale, not a damage grade.</small>
              </div>
              <small>Saved as assessment #{{ aiResult.assessment_id }} · see Dashboard and Report center.</small>
              <small>Radar {{ aiResult.observations.sentinel_1.datetime.slice(0, 10) }} ·
                <template v-if="aiResult.observations.sentinel_2.used">Optical {{ aiResult.observations.sentinel_2.datetime.slice(0, 10) }} ({{ aiResult.observations.sentinel_2.cloud_cover_percent }}% cloud)</template>
                <template v-else>no usable optical scene (radar only)</template></small>
              <small v-for="warning in aiResult.warnings" :key="warning">⚠ {{ warning }}</small>
              <button class="parcel-refresh-button" type="button" @click="clearFloodOverlay">Clear overlay</button>
            </div>
          </div>
        </details>

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
              Satellite clouds: <a href="https://www.jma.go.jp/bosai/himawari/" target="_blank" rel="noreferrer">JMA Himawari-9</a> infrared tiles (Japan Meteorological Agency), shown as cloud-only imagery; the latest two hours of 10-minute frames play back and refresh every 10 minutes.
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
        <span v-if="isRainfallScreeningActive"><i class="flood-screening-legend-mark"></i> Rainfall screening by province: lower (green) · watch (amber) · elevated (red)</span>
        <span v-if="isSatelliteImageActive"><i class="satellite-image-legend-mark"></i> Live cloud-only Himawari-9 imagery</span>
        <span v-if="isWindForecastActive"><i class="wind-forecast-legend-mark"></i> Forecast wind direction and speed · Open-Meteo</span>
        <span v-if="isWeatherGridActive"><i class="weather-legend-mark"></i> {{ selectedWeatherLayerLabel }} · by province · Open-Meteo forecast</span>
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
import { analyzeFloodArea, fetchDamageMap, fetchFloodModelStatus, fetchHimawariTileFrames, fetchParcelMap, fetchProvinceForecast, fetchScanOverlays, fetchScanSummary, fetchSusceptibilityStatus, fetchWindForecast, himawariTileTemplate, predictFloodProneAreas, scanOverlayUrl } from '../api/client'
import { severityColors } from '../map/severity'

const props = defineProps({
  initialLocation: { type: Object, default: null },
})
const emit = defineEmits(['location-selected'])
const mapToken = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN
const weatherLayers = [
  { value: 'rainfall', short: 'Rain watch', icon: '🌧', label: 'Rainfall screening', description: 'Wettest 24 hours in the next 72 h, by province. Screening only, not a flood prediction.' },
  { value: 'clouds', short: 'Clouds', icon: '☁', label: 'Clouds · live satellite', description: 'Live JMA Himawari-9 cloud imagery with playback.' },
  { value: 'wind', short: 'Wind', icon: '💨', label: 'Wind · 72-hour forecast', description: 'Animated wind speed and direction forecast.' },
  { value: 'precipitation', short: 'Next 6 h', icon: '💧', label: 'Precipitation · next 6 hours', description: 'Forecast rain total for the next six hours, by province.' },
  { value: 'temperature', short: 'Temperature', icon: '🌡', label: 'Temperature · forecast', description: 'Forecast air temperature at 2 m, by province.' },
  { value: 'pressure', short: 'Pressure', icon: '◎', label: 'Pressure · forecast', description: 'Forecast mean sea-level pressure, by province.' },
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
  if (isLoadingFloodScreening.value) return 'Loading the province forecast…'
  if (floodScreeningError.value) return floodScreeningError.value
  const collection = floodScreeningCollection.value
  if (!collection) return ''

  const updatedAt = new Date(collection.fetched_at).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })
  if (isRainfallScreeningActive.value) {
    const screeningAreas = collection.features.filter((feature) => (
      ['watch', 'elevated'].includes(feature.properties?.screening_level)
    )).length
    return `${screeningAreas} of ${collection.features.length} provinces on watch or elevated · updated ${updatedAt}`
  }
  return `${collection.features.length} provinces · Open-Meteo forecast · updated ${updatedAt}`
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
const aiModelStatus = ref(null)
const aiEventDate = ref('')
const aiResult = ref(null)
const aiAnalysisError = ref('')
const isAnalyzingFlood = ref(false)
const todayIso = new Date().toISOString().slice(0, 10)
const SUSCEPTIBILITY_ID = 'ai-susceptibility-overlay'
const susceptibilityStatus = ref(null)
const susceptibilityResult = ref(null)
const susceptibilityError = ref('')
const isPredicting = ref(false)

function clearSusceptibility() {
  if (map?.getLayer(SUSCEPTIBILITY_ID)) map.removeLayer(SUSCEPTIBILITY_ID)
  if (map?.getSource(SUSCEPTIBILITY_ID)) map.removeSource(SUSCEPTIBILITY_ID)
  susceptibilityResult.value = null
}

async function loadSusceptibilityStatus() {
  try {
    susceptibilityStatus.value = await fetchSusceptibilityStatus()
  } catch (error) {
    susceptibilityStatus.value = { ready: false, reason: error instanceof Error ? error.message : 'Status unavailable.' }
  }
}

async function runSusceptibility() {
  if (!map || isPredicting.value) return
  const target = selectionMarker?.getLngLat() ?? map.getCenter()
  isPredicting.value = true
  susceptibilityError.value = ''
  try {
    const result = await predictFloodProneAreas({
      latitude: Number(target.lat.toFixed(6)),
      longitude: Number(target.lng.toFixed(6)),
    })
    if (!map) return
    clearSusceptibility()
    map.addSource(SUSCEPTIBILITY_ID, { type: 'image', url: result.overlay.image, coordinates: result.overlay.coordinates })
    map.addLayer({ id: SUSCEPTIBILITY_ID, type: 'raster', source: SUSCEPTIBILITY_ID, paint: { 'raster-opacity': 0.9, 'raster-fade-duration': 0 } })
    const longitudes = result.overlay.coordinates.map((corner) => corner[0])
    const latitudes = result.overlay.coordinates.map((corner) => corner[1])
    map.fitBounds(
      [[Math.min(...longitudes), Math.min(...latitudes)], [Math.max(...longitudes), Math.max(...latitudes)]],
      { padding: 40, duration: 1200 },
    )
    susceptibilityResult.value = result
  } catch (error) {
    susceptibilityError.value = error instanceof Error ? error.message : 'Prediction failed.'
  } finally {
    isPredicting.value = false
  }
}

const AI_OVERLAY_ID = 'ai-flood-overlay'
const scanSummary = ref(null)
const showScan = ref(true)
const scanTileIds = new Set()
let scanRefreshTimer
let scanRequestSequence = 0

async function loadScanSummary() {
  try {
    scanSummary.value = await fetchScanSummary()
  } catch {
    scanSummary.value = { tiles_scanned: 0, tiles_total: 0, coverage_fraction: 0 }
  }
}

function removeScanTile(tileId) {
  const layerId = `scan-${tileId}`
  if (map?.getLayer(layerId)) map.removeLayer(layerId)
  if (map?.getSource(layerId)) map.removeSource(layerId)
  scanTileIds.delete(tileId)
}

async function refreshScanOverlays() {
  if (!map) return
  const currentRequest = ++scanRequestSequence
  if (!showScan.value) {
    for (const tileId of [...scanTileIds]) removeScanTile(tileId)
    return
  }
  try {
    const { tiles } = await fetchScanOverlays(map.getBounds())
    if (currentRequest !== scanRequestSequence || !map) return
    const wanted = new Set(tiles.map((tile) => tile.tile_id))
    for (const tileId of [...scanTileIds]) if (!wanted.has(tileId)) removeScanTile(tileId)
    for (const tile of tiles) {
      if (scanTileIds.has(tile.tile_id)) continue
      const layerId = `scan-${tile.tile_id}`
      map.addSource(layerId, { type: 'image', url: scanOverlayUrl(tile.tile_id), coordinates: tile.corners })
      map.addLayer({ id: layerId, type: 'raster', source: layerId, paint: { 'raster-opacity': 0.85, 'raster-fade-duration': 0 } })
      scanTileIds.add(tile.tile_id)
    }
  } catch {
    // The scan layer is optional; the rest of the map keeps working.
  }
}

function scheduleScanRefresh() {
  window.clearTimeout(scanRefreshTimer)
  scanRefreshTimer = window.setTimeout(() => void refreshScanOverlays(), 450)
}
const AI_FIELDS_ID = 'ai-flood-fields'
const AI_FIELDS_FILL_ID = 'ai-flood-fields-fill'
const AI_FIELDS_OUTLINE_ID = 'ai-flood-fields-outline'

function clearFloodOverlay() {
  for (const layerId of [AI_FIELDS_OUTLINE_ID, AI_FIELDS_FILL_ID, AI_OVERLAY_ID]) {
    if (map?.getLayer(layerId)) map.removeLayer(layerId)
  }
  for (const sourceId of [AI_FIELDS_ID, AI_OVERLAY_ID]) {
    if (map?.getSource(sourceId)) map.removeSource(sourceId)
  }
  aiResult.value = null
}

function addFieldLayers(fields) {
  map.addSource(AI_FIELDS_ID, { type: 'geojson', data: fields })
  const severityColor = [
    'match', ['get', 'severity'],
    'Severe', severityColors.Severe,
    'Moderate', severityColors.Moderate,
    'Light', severityColors.Light,
    '#4d8f6b',
  ]
  map.addLayer({
    id: AI_FIELDS_FILL_ID,
    type: 'fill',
    source: AI_FIELDS_ID,
    paint: { 'fill-color': severityColor, 'fill-opacity': ['match', ['get', 'severity'], 'Unaffected', 0.08, 0.55] },
  })
  map.addLayer({
    id: AI_FIELDS_OUTLINE_ID,
    type: 'line',
    source: AI_FIELDS_ID,
    paint: { 'line-color': severityColor, 'line-width': ['match', ['get', 'severity'], 'Unaffected', 0.6, 1.4] },
  })
  map.on('click', AI_FIELDS_FILL_ID, (event) => {
    const properties = event.features?.[0]?.properties
    if (!properties) return
    new mapboxgl.Popup({ closeButton: false })
      .setLngLat(event.lngLat)
      .setHTML(
        `<strong>${properties.severity}</strong><br>${properties.flooded_ha} of ${properties.area_ha} ha flooded `
        + `(${(properties.flooded_share * 100).toFixed(0)}%)<br><small>Detected field · confidence ${properties.confidence}%</small>`,
      )
      .addTo(map)
  })
}

async function loadFloodModelStatus() {
  try {
    aiModelStatus.value = await fetchFloodModelStatus()
  } catch (error) {
    aiModelStatus.value = { ready: false, reason: error instanceof Error ? error.message : 'Model status unavailable.' }
  }
}

async function runFloodAnalysis() {
  if (!map || isAnalyzingFlood.value) return
  const target = selectionMarker?.getLngLat() ?? map.getCenter()
  isAnalyzingFlood.value = true
  aiAnalysisError.value = ''
  try {
    const result = await analyzeFloodArea({
      latitude: Number(target.lat.toFixed(6)),
      longitude: Number(target.lng.toFixed(6)),
      date: aiEventDate.value,
    })
    if (!map) return
    clearFloodOverlay()
    map.addSource(AI_OVERLAY_ID, { type: 'image', url: result.overlay.image, coordinates: result.overlay.coordinates })
    map.addLayer({ id: AI_OVERLAY_ID, type: 'raster', source: AI_OVERLAY_ID, paint: { 'raster-opacity': 0.9, 'raster-fade-duration': 0 } })
    if (result.fields?.features?.length) addFieldLayers(result.fields)
    const longitudes = result.overlay.coordinates.map((corner) => corner[0])
    const latitudes = result.overlay.coordinates.map((corner) => corner[1])
    map.fitBounds(
      [[Math.min(...longitudes), Math.min(...latitudes)], [Math.max(...longitudes), Math.max(...latitudes)]],
      { padding: 60, duration: 1200 },
    )
    aiResult.value = result
  } catch (error) {
    aiAnalysisError.value = error instanceof Error ? error.message : 'Flood analysis failed.'
  } finally {
    isAnalyzingFlood.value = false
  }
}
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
let mapLayersInitialized = false
let windForecast
let windParticles = []
let windAnimationFrame
let windForecastTimer
let windPlaybackTimer

const HIMAWARI_TILE_MIN_ZOOM = 3
const HIMAWARI_TILE_MAX_ZOOM = 5
const SATELLITE_CLOUD_OPACITY = 0.9
const satelliteLayerIds = []
const satelliteSourceIds = []
const satelliteFrameIndex = ref(0)

function removeSatelliteLayers() {
  for (const layerId of satelliteLayerIds.splice(0)) {
    if (map?.getLayer(layerId)) map.removeLayer(layerId)
  }
  for (const sourceId of satelliteSourceIds.splice(0)) {
    if (map?.getSource(sourceId)) map.removeSource(sourceId)
  }
}

function showSatelliteFrame(index) {
  satelliteLayerIds.forEach((layerId, layerIndex) => {
    if (map?.getLayer(layerId)) {
      map.setPaintProperty(layerId, 'raster-opacity', layerIndex === index ? SATELLITE_CLOUD_OPACITY : 0)
    }
  })
  satelliteFrameIndex.value = index
  satelliteObservedAt.value = satelliteFrames.value[index].observed_at
  satelliteImageStatus.value = `Infrared clouds · ${satelliteObservedAt.value}`
}

async function loadSatelliteImage() {
  const currentRequest = ++satelliteRequestSequence
  isLoadingSatelliteImage.value = true
  if (!satelliteFrames.value.length) satelliteImageStatus.value = 'Loading recent JMA satellite frames…'
  try {
    const response = await fetchHimawariTileFrames()
    const frames = Array.isArray(response.frames) ? response.frames : []
    if (!frames.length) throw new Error('JMA has not provided recent satellite frames.')
    if (currentRequest !== satelliteRequestSequence || !map) return
    if (!map.getLayer('admin-region-fill')) throw new Error('The map is not ready to display satellite imagery.')

    const currentNewest = satelliteFrames.value.at(-1)?.time_code
    if (currentNewest === frames.at(-1).time_code && satelliteLayerIds.length === frames.length) return

    stopSatellitePlayback()
    removeSatelliteLayers()
    // Insert below map labels so place names and roads stay readable above the clouds.
    const beforeLayerId = map.getStyle()?.layers?.find((layer) => layer.type === 'symbol')?.id
    for (const frame of frames) {
      const id = `himawari-${frame.time_code}`
      map.addSource(id, {
        type: 'raster',
        tiles: [himawariTileTemplate(frame.time_code)],
        tileSize: 256,
        minzoom: HIMAWARI_TILE_MIN_ZOOM,
        maxzoom: HIMAWARI_TILE_MAX_ZOOM,
      })
      map.addLayer({
        id,
        type: 'raster',
        source: id,
        layout: { visibility: isSatelliteImageActive.value ? 'visible' : 'none' },
        paint: {
          'raster-opacity': 0,
          'raster-opacity-transition': { duration: 0 },
          'raster-fade-duration': 0,
        },
      }, beforeLayerId)
      satelliteSourceIds.push(id)
      satelliteLayerIds.push(id)
    }
    satelliteFrames.value = frames
    showSatelliteFrame(frames.length - 1)
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
  if (!map || satelliteFrames.value.length < 2 || !satelliteLayerIds.length) return
  stopSatellitePlayback()
  isSatellitePlaying.value = true
  satelliteAnimationTimer = window.setInterval(() => {
    if (!map || !isSatelliteImageActive.value) {
      stopSatellitePlayback()
      return
    }
    showSatelliteFrame((satelliteFrameIndex.value + 1) % satelliteFrames.value.length)
  }, 700)
}

function toggleSatellitePlayback() {
  satellitePlaybackEnabled.value = !isSatellitePlaying.value
  if (satellitePlaybackEnabled.value) startSatellitePlayback()
  else stopSatellitePlayback()
}

function setSatelliteImageVisibility() {
  window.clearInterval(satelliteRefreshTimer)
  const visible = isSatelliteImageActive.value
  satelliteLayerIds.forEach((layerId) => setLayerVisibility(layerId, visible))
  if (!visible) {
    stopSatellitePlayback()
    return
  }
  if (!satelliteFrames.value.length) void loadSatelliteImage()
  else if (satellitePlaybackEnabled.value) startSatellitePlayback()
  satelliteRefreshTimer = window.setInterval(() => void loadSatelliteImage(), 10 * 60 * 1000)
}

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

function selectWeatherLayer(value) {
  if (selectedWeatherLayer.value === value) return
  selectedWeatherLayer.value = value
  updateWeatherLayer()
}

function updateWeatherLayer() {
  const isGridMode = isGridWeatherMode.value
  setLayerVisibility('flood-screening-fill', isGridMode)
  setLayerVisibility('flood-screening-outline', isGridMode)
  setLayerVisibility('flood-screening-hover', isGridMode)
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
    // Show every cell so the layer is visibly active; only watch/elevated cells are emphasized.
    map.setFilter(fillLayer, null)
    map.setFilter(outlineLayer, null)
    map.setPaintProperty(fillLayer, 'fill-color', [
      'match', ['get', 'screening_level'],
      'elevated', '#c83e3e',
      'watch', '#f0b52c',
      '#5fa98a',
    ])
    map.setPaintProperty(fillLayer, 'fill-opacity', [
      'match', ['get', 'screening_level'],
      'elevated', 0.6,
      'watch', 0.55,
      0.22,
    ])
    map.setPaintProperty(outlineLayer, 'line-opacity', [
      'match', ['get', 'screening_level'],
      'elevated', 0.7,
      'watch', 0.65,
      0.3,
    ])
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
  }, 'admin-region-outline')
  map.addLayer({
    id: 'flood-screening-outline',
    type: 'line',
    source: 'flood-screening',
    layout: { visibility: isGridWeatherMode.value ? 'visible' : 'none', 'line-join': 'round' },
    paint: {
      'line-color': '#ffffff',
      'line-width': ['interpolate', ['linear'], ['zoom'], 4, 0.6, 9, 1.6],
      'line-opacity': 0.85,
    },
  }, 'admin-region-outline')
  map.addLayer({
    id: 'flood-screening-hover',
    type: 'line',
    source: 'flood-screening',
    filter: ['==', ['get', 'name'], ''],
    layout: { visibility: isGridWeatherMode.value ? 'visible' : 'none', 'line-join': 'round' },
    paint: { 'line-color': '#12372a', 'line-width': 2.2, 'line-opacity': 0.9 },
  }, 'admin-region-outline')
  map.on('click', 'flood-screening-fill', (event) => {
    const feature = event.features?.[0]
    if (!feature) return
    event.originalEvent.stopPropagation()
    const properties = feature.properties ?? {}
    const content = document.createElement('div')
    const heading = document.createElement('strong')
    heading.textContent = properties.name ?? 'Province'
    content.append(heading)
    const level = properties.screening_level === 'elevated' ? 'Elevated' : properties.screening_level === 'watch' ? 'Watch' : 'Lower'
    const details = selectedWeatherLayer.value === 'temperature'
      ? [['Air temperature', `${Number(properties.temperature_2m_c).toFixed(1)} °C`]]
      : selectedWeatherLayer.value === 'precipitation'
        ? [['Rain, next 6 hours', `${Number(properties.precipitation_6h_mm).toFixed(1)} mm`]]
        : selectedWeatherLayer.value === 'pressure'
          ? [['Sea-level pressure', `${Number(properties.pressure_msl_hpa).toFixed(1)} hPa`]]
          : [
              ['Screening level', level],
              ['Wettest 24 h (next 72 h)', `${Number(properties.rainfall_24h_mm).toFixed(1)} mm`],
              ['Rain, next 72 h', `${Number(properties.rainfall_72h_mm).toFixed(1)} mm`],
            ]
    for (const [label, value] of [...details, ['Forecast from (UTC)', properties.forecast_start]]) {
      const detail = document.createElement('p')
      detail.textContent = `${label}: ${value}`
      content.append(detail)
    }
    const note = document.createElement('small')
    note.textContent = `Open-Meteo model forecast, from ${properties.sample_points} point${Number(properties.sample_points) === 1 ? '' : 's'} in this province. `
      + (selectedWeatherLayer.value === 'rainfall' ? 'Screening only, not a flood prediction or official warning.' : 'Not a station observation.')
    content.append(note)
    new mapboxgl.Popup({ maxWidth: '18rem' })
      .setLngLat(event.lngLat)
      .setDOMContent(content)
      .addTo(map)
  })
  map.on('mousemove', 'flood-screening-fill', (event) => {
    map.getCanvas().style.cursor = 'pointer'
    map.setFilter('flood-screening-hover', ['==', ['get', 'name'], event.features?.[0]?.properties?.name ?? ''])
  })
  map.on('mouseleave', 'flood-screening-fill', () => {
    map.getCanvas().style.cursor = ''
    map.setFilter('flood-screening-hover', ['==', ['get', 'name'], ''])
  })
  setFloodScreeningDisplay()
}

async function loadFloodScreening() {
  const currentRequest = ++floodScreeningRequestSequence
  isLoadingFloodScreening.value = true
  floodScreeningError.value = ''
  try {
    const collection = await fetchProvinceForecast()
    if (currentRequest !== floodScreeningRequestSequence || !map) return
    if (!collection.features?.length) throw new Error('The forecast returned no provinces.')
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

const WIND_PARTICLE_MAX_AGE = 120
let windViewKey = ''

function respawnWindParticle(bounds) {
  return { ...createWindParticle(bounds), age: 0 }
}

function drawWindForecastFrame(timestamp, deltaMilliseconds = 16) {
  const canvas = windCanvas.value
  const context = canvas?.getContext('2d')
  if (!map || !context || !windForecast || !isWindForecastActive.value) return
  const bounds = map.getBounds()
  const width = canvas.clientWidth
  const height = canvas.clientHeight
  const center = map.getCenter()
  const viewKey = `${center.lng.toFixed(4)}|${center.lat.toFixed(4)}|${map.getZoom().toFixed(3)}`
  if (viewKey !== windViewKey) {
    // Trails drawn for a previous view would smear across a moved map.
    context.clearRect(0, 0, width, height)
    windViewKey = viewKey
  }
  if (!windParticles.length) {
    const particleCount = Math.min(1100, Math.max(450, Math.round((width * height) / 1100)))
    windParticles = Array.from({ length: particleCount }, () => ({
      ...createWindParticle(bounds),
      age: Math.floor(Math.random() * WIND_PARTICLE_MAX_AGE),
    }))
  }

  context.globalCompositeOperation = 'destination-out'
  context.fillStyle = 'rgba(0, 0, 0, 0.06)'
  context.fillRect(0, 0, width, height)
  context.globalCompositeOperation = 'source-over'

  const hourIndex = Math.min(windForecastIndex.value, windForecastTimes.value.length - 1)
  const frameScale = Math.min(deltaMilliseconds, 40) / 16
  context.lineCap = 'round'
  for (let index = 0; index < windParticles.length; index += 1) {
    const particle = windParticles[index]
    particle.age += 1
    if (particle.age > WIND_PARTICLE_MAX_AGE || !bounds.contains([particle.longitude, particle.latitude])) {
      windParticles[index] = respawnWindParticle(bounds)
      continue
    }
    const feature = nearestWindPoint(particle.longitude, particle.latitude)
    if (!feature) continue
    const properties = feature.properties
    const speed = Number(properties.wind_speed_10m_mps[hourIndex] ?? 0)
    const fromDirection = Number(properties.wind_direction_10m_deg[hourIndex] ?? 0)
    const direction = (fromDirection + 180) * Math.PI / 180
    // Move in screen pixels so the motion looks the same at every zoom level.
    const pixels = (0.7 + Math.min(speed, 25) * 0.17) * frameScale
    const start = map.project([particle.longitude, particle.latitude])
    const end = { x: start.x + Math.sin(direction) * pixels, y: start.y - Math.cos(direction) * pixels }
    const next = map.unproject([end.x, end.y])
    particle.longitude = next.lng
    particle.latitude = next.lat
    if (
      particle.longitude < 114 || particle.longitude > 130
      || particle.latitude < 1.5 || particle.latitude > 25.5
    ) {
      windParticles[index] = respawnWindParticle(bounds)
      continue
    }
    const visibility = Math.min(1, particle.age / 8, (WIND_PARTICLE_MAX_AGE - particle.age) / 16)
    context.globalAlpha = 0.5 * visibility
    context.lineWidth = 3
    context.strokeStyle = '#102030'
    context.beginPath()
    context.moveTo(start.x, start.y)
    context.lineTo(end.x, end.y)
    context.stroke()
    context.globalAlpha = 0.95 * visibility
    context.lineWidth = 1.7
    context.strokeStyle = windParticleColor(speed)
    context.beginPath()
    context.moveTo(start.x, start.y)
    context.lineTo(end.x, end.y)
    context.stroke()
  }
  context.globalAlpha = 1
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
    map.on('moveend', scheduleScanRefresh)
    void loadScanSummary()
    void refreshScanOverlays()
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
  void loadFloodModelStatus()
  void loadSusceptibilityStatus()
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
  window.clearTimeout(scanRefreshTimer)
  window.clearTimeout(mapStartupTimer)
  window.clearInterval(satelliteRefreshTimer)
  window.clearInterval(windForecastTimer)
  window.clearInterval(windPlaybackTimer)
  requestSequence += 1
  floodScreeningRequestSequence += 1
  satelliteRequestSequence += 1
  windForecastRequestSequence += 1
  window.cancelAnimationFrame(windAnimationFrame)
  window.clearInterval(satelliteAnimationTimer)
  resizeObserver?.disconnect()
  map?.remove()
  map = undefined
})
</script>
