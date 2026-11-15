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
        <p class="map-tools-heading">HOW TO USE</p>
        <ol class="map-quick-start">
          <li>Pick a layer below.</li>
          <li>Click anywhere on the map for a flood report on that spot.</li>
          <li>Open “How MindSpore works here” to see what the AI does.</li>
        </ol>
        <p class="map-tools-heading">FLOOD PREDICTION</p>
        <div class="weather-type-grid" role="radiogroup" aria-label="Flood prediction layers">
          <button
            v-for="layer in floodLayers"
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
        <p class="map-tools-heading">WEATHER</p>
        <div class="weather-type-grid" role="radiogroup" aria-label="Weather layers">
          <button
            v-for="layer in plainWeatherLayers"
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
        <label v-if="isRainfallScreeningActive" class="map-layer-toggle">
          <input v-model="showImerg" type="checkbox" @change="updateFieldLayers">
          <span>Observed rain · NASA satellite<small v-if="imerg"> · {{ imerg.time.slice(11, 16) }} UTC, {{ imerg.age_hours }} h old</small><small v-else-if="imergError"> · unavailable</small></span>
        </label>
        <p v-if="isPressureActive" class="weather-layer-description">
          <strong>How to read this:</strong> air pressure is the weight of the air above you. <b>L</b> marks the lowest-pressure area (rising air, clouds and rain, and where storms form);
          <b>H</b> marks high pressure (sinking air, usually clear and calm). Lines (isobars) join equal pressure; closely packed lines mean strong wind.
        </p>
        <p v-if="isGridWeatherMode && floodScreeningStatus" class="parcel-map-status" role="status" aria-live="polite">{{ floodScreeningStatus }}</p>
        <button
          v-if="isGridWeatherMode"
          class="parcel-refresh-button"
          type="button"
          :disabled="isLoadingFloodScreening"
          @click="loadFloodScreening"
        >
          {{ isLoadingFloodScreening ? 'Refreshing forecast…' : isOutlookActive ? 'Refresh flood outlook' : isRainfallScreeningActive ? 'Refresh rainfall screening' : 'Refresh weather forecast' }}
        </button>

        <div class="flood-layer-toggles" role="group" aria-label="MindSpore flood layers">
          <p class="map-tools-heading">WHAT MINDSPORE ADDS TO THE MAP</p>
          <label class="map-layer-toggle">
            <input v-model="showProne" type="checkbox" :disabled="!susceptibilityStatus?.ready" @change="refreshProneOverlays">
            <span class="prone-swatch"></span>
            <span>Flood-prone land<small> · terrain model{{ susceptibilityStatus?.heldout_auc ? `, AUC ${susceptibilityStatus.heldout_auc.toFixed(2)} on regions it never saw` : '' }}</small></span>
          </label>
          <label v-if="isOutlookActive || isRainfallScreeningActive" class="map-layer-toggle">
            <input v-model="showForecast" type="checkbox" :disabled="!rainFloodStatus?.ready" @change="refreshProneOverlays">
            <span class="forecast-swatch"></span>
            <span>Predicted flooding from rain<small> · rain model{{ rainFloodStatus?.rain_auc ? `, AUC ${rainFloodStatus.rain_auc.toFixed(2)} on flood events it never saw` : '' }}</small></span>
          </label>
          <label v-if="(isOutlookActive || isRainfallScreeningActive) && showForecast" class="weather-layer-select">
            Rain for the flood prediction
            <select v-model="scenarioRain" aria-label="Rain used for the MindSpore flood prediction" @change="refreshProneOverlays">
              <option value="0">Real forecast (today)</option>
              <option value="50">What if: 50 mm in a day (heavy rain)</option>
              <option value="100">What if: 100 mm in a day (very heavy)</option>
              <option value="200">What if: 200 mm in a day (typhoon-level)</option>
            </select>
          </label>
          <small v-if="scenarioRain !== '0' && (isOutlookActive || isRainfallScreeningActive)" class="parcel-map-attribution">
            Scenario, not a forecast: the same {{ scenarioRain }} mm of rain is assumed over the whole country to show where the MindSpore rain model expects water to collect.
          </small>
          <label class="map-layer-toggle">
            <input v-model="showScan" type="checkbox" @change="refreshScanOverlays">
            <span class="scan-swatch"></span>
            <span>Floods seen by satellite<small v-if="scanSummary"> · radar scan, {{ scanSummary.tiles_scanned.toLocaleString() }} of {{ scanSummary.tiles_total.toLocaleString() }} areas checked{{ scanSummary.flooded_km2 ? `, ${scanSummary.flooded_km2.toLocaleString()} km² of water found` : '' }}</small></span>
          </label>
          <label class="map-layer-toggle">
            <input v-model="show3d" type="checkbox" @change="setTerrain3d">
            <span>3D terrain<small> · real elevation, tilt the map to see valleys and floodplains</small></span>
          </label>
          <small class="parcel-map-attribution">Areas the satellite scan has not reached yet are left blank. Blank does not mean “no flood”. The scan runs in the background, wettest provinces first.</small>
        </div>

        <details class="map-tools-group">
          <summary>How MindSpore works here</summary>
          <div class="map-tools-group-content mindspore-explainer">
            <p><strong>1 · Reads the satellite.</strong> A ResNet-50 U-Net reads Sentinel-1 radar (it sees through cloud) and Sentinel-2 images and outlines land that is under water right now. It scored {{ aiModelStatus?.test_metrics ? aiModelStatus.test_metrics.radar_optical.iou.toFixed(2) : '0.76' }} IoU (a 0–1 overlap score) on floods it had never seen.</p>
            <p><strong>2 · Learns which land floods.</strong> A second network learned from satellite elevation and 36 years of Landsat water history which terrain tends to go under water. It scored AUC {{ susceptibilityStatus?.heldout_auc ? susceptibilityStatus.heldout_auc.toFixed(2) : '0.97' }} on regions held out from training. These are the blue areas.</p>
            <p><strong>3 · Predicts flooding from rain.</strong> A third network takes that terrain plus the forecast rain and predicts where water will collect. It learned from {{ rainFloodStatus?.events ?? 11 }} real floods and scored AUC {{ rainFloodStatus?.rain_auc ? rainFloodStatus.rain_auc.toFixed(2) : '0.86' }} on floods it never saw. These are the yellow-to-red areas.</p>
            <small>All three run on MindSpore on an ordinary CPU, using only real public data. They have not been run on Huawei Ascend hardware or validated against Philippine flood records, so treat them as decision support, not as an official warning.</small>
          </div>
        </details>

        <details class="map-tools-group susceptibility-group">
          <summary>Report for the marked spot</summary>
          <div class="map-tools-group-content">
            <p v-if="susceptibilityStatus && !susceptibilityStatus.ready" class="parcel-map-status" role="status">{{ susceptibilityStatus.reason }}</p>
            <button
              class="parcel-refresh-button"
              type="button"
              :disabled="isPredicting || !susceptibilityStatus?.ready"
              @click="runSusceptibility"
            >
              {{ isPredicting ? 'Checking…' : 'Get a report for the marked spot' }}
            </button>
            <p v-if="susceptibilityError" class="parcel-map-status ai-flood-error" role="alert">{{ susceptibilityError }}</p>
            <div v-if="susceptibilityResult" class="ai-flood-result susceptibility-result" :class="`watch-${susceptibilityResult.watch.level}`" role="status">
              <strong>Flood {{ susceptibilityResult.watch.level === 'none' ? 'outlook: no warning' : susceptibilityResult.watch.level }}</strong>
              <span>{{ susceptibilityResult.watch.message }}</span>
              <span>
                Terrain within {{ susceptibilityResult.local.radius_km }} km: {{ susceptibilityResult.watch.terrain }} flood-proneness
                ({{ (susceptibilityResult.local.land_share_high * 100).toFixed(0) }}% high)
              </span>
              <template v-if="susceptibilityResult.forecast">
                <small>
                  {{ susceptibilityResult.forecast.name }} forecast · rain {{ susceptibilityResult.forecast.precipitation_6h_mm }} mm next 6 h ·
                  {{ susceptibilityResult.forecast.rainfall_24h_mm }} mm wettest 24 h · {{ susceptibilityResult.forecast.rainfall_72h_mm }} mm over 72 h ·
                  {{ susceptibilityResult.forecast.temperature_2m_c }} °C · {{ susceptibilityResult.forecast.pressure_msl_hpa }} hPa
                </small>
              </template>
              <span v-if="susceptibilityResult.rain_model" class="rain-model-verdict">
                Rain model (MindSpore):
                <b>{{ { none: 'no rain-driven flooding expected', advisory: 'flood advisory', watch: 'flood watch', warning: 'flood warning' }[susceptibilityResult.rain_model.level] }}</b>
                · {{ Math.round(susceptibilityResult.rain_model.probability_nearby * 100) }}% flood likelihood within 1 km
              </span>
              <small>The blue terrain result and the rain model are trained MindSpore networks. The overall level above links forecast rain to terrain with a stated rule (rain band × terrain), not a learned or official forecast.</small>
              <button class="parcel-refresh-button" type="button" @click="clearSusceptibility">Clear</button>
            </div>
          </div>
        </details>


        <details class="map-tools-group ai-flood-group">
          <summary>
            Scan a spot with satellite radar
            <span class="ai-flood-badge" :class="aiModelStatus?.ready ? 'ai-flood-badge-ready' : 'ai-flood-badge-off'">
              {{ aiModelStatus?.ready ? 'Model ready' : 'Not ready' }}
            </span>
          </summary>
          <div class="map-tools-group-content">
            <p class="parcel-map-attribution">
              Reads real Sentinel-1 radar and Sentinel-2 images for a 5 km square around the marked spot (or the map centre) and outlines water with a MindSpore ResNet-50 U-Net.
              Experimental: not an official flood boundary.
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
              {{ isAnalyzingFlood ? 'Reading Sentinel data & running MindSpore…' : 'Scan this area now' }}
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
          <summary>Farms &amp; boundaries</summary>
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
        <span v-if="isOutlookActive"><i class="flood-screening-legend-mark"></i> Blue: land that tends to flood (MindSpore terrain model) · yellow, orange, red: flooding the MindSpore rain model expects from the forecast rain, from advisory to warning</span>
        <span v-if="isRainfallScreeningActive"><i class="flood-screening-legend-mark"></i> Satellite clouds · satellite-measured rain (green to red) · forecast rain, next 6 h (purple) · MindSpore flood prediction (yellow to red) on top</span>
        <span v-if="isPressureActive"><i class="weather-legend-mark"></i> Sea-level pressure: blue lower, red higher · lines join equal pressure · L / H mark the lowest and highest</span>
        <span v-if="isSatelliteImageActive"><i class="satellite-image-legend-mark"></i> Live cloud-only Himawari-9 imagery</span>
        <span v-if="isWindForecastActive"><i class="wind-forecast-legend-mark"></i> Forecast wind direction and speed · Open-Meteo</span>
        <span v-if="isWeatherGridActive"><i class="weather-legend-mark"></i> {{ selectedWeatherLayerLabel }} · by province · Open-Meteo forecast</span>
      </div>
      <div v-if="isWeatherGridActive || isRainfallScreeningActive" class="weather-map-scale" :class="`weather-scale-${selectedWeatherLayer}`">
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
import { analyzeFloodArea, fetchDamageMap, fetchFloodModelStatus, fetchHimawariTileFrames, fetchLatestImerg, fetchParcelMap, fetchPressureIsobars, fetchProvinceForecast, fetchRainFloodStatus, fetchScanOverlays, fetchScanSummary, fetchSusceptibilityChunks, fetchSusceptibilityStatus, fetchWindForecast, floodContextUrl, floodForecastUrl, forecastFieldUrl, himawariTileTemplate, imergImageUrl, predictFloodProneAreas, scanOverlayUrl, susceptibilityChunkUrl } from '../api/client'
import { severityColors } from '../map/severity'

const props = defineProps({
  initialLocation: { type: Object, default: null },
})
const emit = defineEmits(['location-selected'])
const mapToken = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN
const weatherLayers = [
  { value: 'outlook', short: 'Flood outlook', icon: '🌊', label: 'Flood outlook · MindSpore', description: 'Where floods are likely, on real terrain. Blue is land that tends to flood. Yellow, orange and red is where the MindSpore rain model expects water to collect from the forecast rain. Updates itself.' },
  { value: 'rainfall', short: 'Rain watch', icon: '🌧', label: 'Rain watch', description: 'Where it is raining, and what that rain could flood. Satellite clouds (Himawari-9) and satellite-measured rain (NASA, green to red) show what is happening; forecast rain (purple) shows the next 6 hours; the MindSpore flood prediction sits on top.' },
  { value: 'clouds', short: 'Clouds', icon: '☁', label: 'Clouds · live satellite', description: 'Live JMA Himawari-9 cloud imagery with playback.' },
  { value: 'wind', short: 'Wind', icon: '💨', label: 'Wind · 72-hour forecast', description: 'Animated wind speed and direction forecast.' },
  { value: 'precipitation', short: 'Rain next 6 h', icon: '💧', label: 'Precipitation · next 6 hours', description: 'Forecast rain total for the next six hours, by province.' },
  { value: 'temperature', short: 'Temperature', icon: '🌡', label: 'Temperature · forecast', description: 'Forecast air temperature at 2 m, by province.' },
  { value: 'pressure', short: 'Pressure', icon: '◎', label: 'Pressure · forecast', description: 'Forecast sea-level air pressure: blue is lower than the rest of the country, red is higher.' },
]
const floodLayers = weatherLayers.filter((layer) => ['outlook', 'rainfall'].includes(layer.value))
const plainWeatherLayers = weatherLayers.filter((layer) => !['outlook', 'rainfall'].includes(layer.value))
const FIELD_COORDINATES = [[116.5, 21.5], [127, 21.5], [127, 4.5], [116.5, 4.5]]
const showImerg = ref(true)
const imerg = ref(null)
const imergError = ref(false)
const pressureScale = ref(null)
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
const selectedWeatherLayer = ref('outlook')
const isOutlookActive = computed(() => selectedWeatherLayer.value === 'outlook')
const isRainfallScreeningActive = computed(() => selectedWeatherLayer.value === 'rainfall')
const isSatelliteImageActive = computed(() => selectedWeatherLayer.value === 'clouds')
const isCloudBaseActive = computed(() => ['clouds', 'rainfall'].includes(selectedWeatherLayer.value))
const isPressureActive = computed(() => selectedWeatherLayer.value === 'pressure')
const isWindForecastActive = computed(() => selectedWeatherLayer.value === 'wind')
const isWeatherGridActive = computed(() => (
  ['precipitation', 'temperature', 'pressure'].includes(selectedWeatherLayer.value)
))
const isGridWeatherMode = computed(() => (
  isOutlookActive.value || isRainfallScreeningActive.value || isWeatherGridActive.value
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
  if (isOutlookActive.value) {
    const wettest = collection.features.reduce((best, feature) => (
      Number(feature.properties?.rainfall_24h_mm) > Number(best.properties?.rainfall_24h_mm) ? feature : best
    ), collection.features[0])
    const peak = Number(wettest.properties.rainfall_24h_mm)
    return peak < 10
      ? `Light rain only: the heaviest forecast is ${peak.toFixed(0)} mm in 24 h (${wettest.properties.name}), so the rain model draws no new flooding. Blue shows land that floods when heavy rain comes · updated ${updatedAt}`
      : `Heaviest forecast rain: ${peak.toFixed(0)} mm in 24 h over ${wettest.properties.name}. Yellow to red shows where the MindSpore rain model expects water to collect · updated ${updatedAt}`
  }
  if (isRainfallScreeningActive.value) {
    const raining = collection.features.filter((feature) => Number(feature.properties?.precipitation_6h_mm) >= 0.1).length
    return `Rain expected in ${raining} of ${collection.features.length} provinces in the next 6 h · forecast updated ${updatedAt}`
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
  rainfall: 'Forecast rain · next 6 h (mm)',
  precipitation: 'Precipitation · next 6 h (mm)',
  temperature: 'Air temperature · °C',
  pressure: 'Sea-level pressure · hPa',
}[selectedWeatherLayer.value] ?? ''))
const weatherScaleMinimum = computed(() => ({
  rainfall: '0.1 mm',
  precipitation: '0 mm',
  temperature: '−5 °C',
  pressure: pressureScale.value ? `Lower · ${pressureScale.value.min} hPa` : 'Lower',
}[selectedWeatherLayer.value] ?? ''))
const weatherScaleMaximum = computed(() => ({
  rainfall: '30+ mm',
  precipitation: '50+ mm',
  temperature: '40 °C',
  pressure: pressureScale.value ? `Higher · ${pressureScale.value.max} hPa` : 'Higher',
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
const showProne = ref(true)
const showForecast = ref(true)
const scenarioRain = ref('0')
const show3d = ref(false)
const rainFloodStatus = ref(null)
const proneChunkIds = new Set()
let proneRefreshTimer
let proneRequestSequence = 0

let proneVariant = 'plain'

function removeProneChunk(chunkId) {
  for (const layerId of [`prone-${chunkId}`, `forecast-${chunkId}`]) {
    if (map?.getLayer(layerId)) map.removeLayer(layerId)
    if (map?.getSource(layerId)) map.removeSource(layerId)
  }
  proneChunkIds.delete(chunkId)
}

async function refreshProneOverlays() {
  if (!map) return
  const currentRequest = ++proneRequestSequence
  // With rain on screen the flood-prone land turns blue and the MindSpore rain model draws the predicted flooding on top.
  const variant = isOutlookActive.value || isRainfallScreeningActive.value ? 'outlook' : 'plain'
  const signature = `${variant}-${showProne.value}-${showForecast.value}-${scenarioRain.value}`
  if (signature !== proneVariant) {
    for (const chunkId of [...proneChunkIds]) removeProneChunk(chunkId)
    proneVariant = signature
  }
  if (!susceptibilityStatus.value?.ready || (!showProne.value && !(variant === 'outlook' && showForecast.value))) {
    for (const chunkId of [...proneChunkIds]) removeProneChunk(chunkId)
    return
  }
  try {
    const { chunks } = await fetchSusceptibilityChunks(map.getBounds())
    if (currentRequest !== proneRequestSequence || !map) return
    const wanted = new Set(chunks.map((chunk) => chunk.id))
    for (const chunkId of [...proneChunkIds]) if (!wanted.has(chunkId)) removeProneChunk(chunkId)
    for (const chunk of chunks) {
      if (proneChunkIds.has(chunk.id)) continue
      const coordinates = [[chunk.west, chunk.north], [chunk.east, chunk.north], [chunk.east, chunk.south], [chunk.west, chunk.south]]
      const beforeLayer = map.getLayer(AI_OVERLAY_LAYER) ? AI_OVERLAY_LAYER : undefined
      const paint = { 'raster-opacity': 0.95, 'raster-resampling': 'linear', 'raster-fade-duration': 0 }
      if (showProne.value) {
        const layerId = `prone-${chunk.id}`
        map.addSource(layerId, {
          type: 'image',
          url: variant === 'outlook' ? floodContextUrl(chunk.id) : susceptibilityChunkUrl(chunk.id),
          coordinates,
        })
        map.addLayer({ id: layerId, type: 'raster', source: layerId, paint }, beforeLayer)
      }
      if (variant === 'outlook' && showForecast.value) {
        const layerId = `forecast-${chunk.id}`
        map.addSource(layerId, { type: 'image', url: floodForecastUrl(chunk.id, Number(scenarioRain.value)), coordinates })
        map.addLayer({ id: layerId, type: 'raster', source: layerId, paint }, beforeLayer)
      }
      proneChunkIds.add(chunk.id)
    }
  } catch {
    // The prediction layer is optional; the rest of the map keeps working.
  }
}

function scheduleProneRefresh() {
  window.clearTimeout(proneRefreshTimer)
  proneRefreshTimer = window.setTimeout(() => void refreshProneOverlays(), 450)
}

function clearSusceptibility() {
  susceptibilityResult.value = null
}

async function loadSusceptibilityStatus() {
  try {
    susceptibilityStatus.value = await fetchSusceptibilityStatus()
  } catch (error) {
    susceptibilityStatus.value = { ready: false, reason: error instanceof Error ? error.message : 'Status unavailable.' }
  }
  void refreshProneOverlays()
}

async function runSusceptibility() {
  if (!map || isPredicting.value) return
  const target = selectionMarker?.getLngLat() ?? map.getCenter()
  isPredicting.value = true
  susceptibilityError.value = ''
  try {
    susceptibilityResult.value = await predictFloodProneAreas({
      latitude: Number(target.lat.toFixed(6)),
      longitude: Number(target.lng.toFixed(6)),
    })
  } catch (error) {
    susceptibilityResult.value = null
    susceptibilityError.value = error instanceof Error ? error.message : 'Assessment failed.'
  } finally {
    isPredicting.value = false
  }
}

const AI_OVERLAY_ID = 'ai-flood-overlay'
const AI_OVERLAY_LAYER = AI_OVERLAY_ID
const scanSummary = ref(null)
const showScan = ref(true)
const scanTileIds = new Set()
let scanRefreshTimer
let scanPollTimer
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

function ensureScanMarkers() {
  if (map.getSource('scan-markers')) return
  map.addSource('scan-markers', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
  // A soft glow marks where the radar scan found water; real flood outlines take over when you zoom in.
  map.addLayer({
    id: 'scan-glow',
    type: 'heatmap',
    source: 'scan-markers',
    paint: {
      'heatmap-weight': ['interpolate', ['linear'], ['get', 'flooded_km2'], 0, 0.35, 5, 0.7, 25, 1],
      'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 4, 16, 8, 38],
      'heatmap-intensity': 1.1,
      'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(37,99,235,0)', 0.25, 'rgba(96,165,250,0.45)', 0.6, 'rgba(37,99,235,0.7)', 1, 'rgba(23,37,140,0.9)'],
      'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 8, 0.95, 10, 0],
    },
  })
  map.addLayer({
    id: 'scan-markers',
    type: 'circle',
    source: 'scan-markers',
    paint: { 'circle-radius': 12, 'circle-color': '#2563eb', 'circle-opacity': 0.01 },
  })
  map.on('click', 'scan-markers', (event) => {
    const properties = event.features?.[0]?.properties
    if (!properties) return
    event.originalEvent.stopPropagation()
    const content = document.createElement('div')
    const heading = document.createElement('strong')
    heading.textContent = `Satellite radar check · ${properties.province}`
    content.append(heading)
    for (const text of [
      `Water found: ${Number(properties.flooded_km2).toFixed(1)} km² (${Math.round(Number(properties.flooded_fraction) * 100)}% of this 5 km square)`,
      `Radar picture taken: ${properties.s1_date}`,
      `Checked with: ${properties.mode === 'radar+optical' ? 'radar and a clear optical image' : 'radar only (cloudy)'}`,
    ]) {
      const line = document.createElement('p')
      line.textContent = text
      content.append(line)
    }
    const note = document.createElement('small')
    note.textContent = 'MindSpore marks surface water that was not there in the dry season. Rice paddies and fishponds can look like flood, so confirm before acting.'
    content.append(note)
    new mapboxgl.Popup({ maxWidth: '18rem' }).setLngLat(event.lngLat).setDOMContent(content).addTo(map)
  })
  map.on('mouseenter', 'scan-markers', () => { map.getCanvas().style.cursor = 'pointer' })
  map.on('mouseleave', 'scan-markers', () => { map.getCanvas().style.cursor = '' })
}

async function refreshScanOverlays() {
  if (!map) return
  const currentRequest = ++scanRequestSequence
  ensureScanMarkers()
  if (!showScan.value) {
    for (const tileId of [...scanTileIds]) removeScanTile(tileId)
    map.getSource('scan-markers').setData({ type: 'FeatureCollection', features: [] })
    return
  }
  try {
    const { tiles } = await fetchScanOverlays(map.getBounds())
    if (currentRequest !== scanRequestSequence || !map) return
    map.getSource('scan-markers').setData({
      type: 'FeatureCollection',
      features: tiles.map((tile) => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [tile.longitude, tile.latitude] },
        properties: {
          province: tile.province, flooded_km2: tile.flooded_km2, flooded_fraction: tile.flooded_fraction,
          s1_date: tile.s1_date, mode: tile.mode,
        },
      })),
    })
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
let placePopup
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
      map.setPaintProperty(layerId, 'raster-opacity', layerIndex === index ? (isSatelliteImageActive.value ? SATELLITE_CLOUD_OPACITY : 0.6) : 0)
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
        layout: { visibility: isCloudBaseActive.value ? 'visible' : 'none' },
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
  const visible = isCloudBaseActive.value
  satelliteLayerIds.forEach((layerId) => setLayerVisibility(layerId, visible))
  if (!visible) {
    stopSatellitePlayback()
    return
  }
  if (!satelliteFrames.value.length) void loadSatelliteImage()
  else if (isSatelliteImageActive.value && satellitePlaybackEnabled.value) startSatellitePlayback()
  else {
    stopSatellitePlayback()
    showSatelliteFrame(satelliteFrames.value.length - 1)
  }
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

function addFieldImage(id, url, opacity) {
  if (map.getSource(id)) return
  map.addSource(id, { type: 'image', url, coordinates: FIELD_COORDINATES })
  map.addLayer({
    id,
    type: 'raster',
    source: id,
    layout: { visibility: 'none' },
    paint: { 'raster-opacity': opacity, 'raster-resampling': 'linear', 'raster-fade-duration': 0 },
  }, 'admin-region-fill')
}

function addIsobarLayers(collection) {
  if (map.getSource('pressure-isobars')) {
    map.getSource('pressure-isobars').setData(collection)
    return
  }
  map.addSource('pressure-isobars', { type: 'geojson', data: collection })
  const visibility = { visibility: 'none' }
  map.addLayer({
    id: 'pressure-isobar-lines', type: 'line', source: 'pressure-isobars', filter: ['has', 'hpa'], layout: { ...visibility, 'line-join': 'round' },
    paint: { 'line-color': '#2f3b4c', 'line-width': 1.1, 'line-opacity': 0.75 },
  })
  map.addLayer({
    id: 'pressure-isobar-labels', type: 'symbol', source: 'pressure-isobars', filter: ['has', 'hpa'],
    layout: { ...visibility, 'symbol-placement': 'line', 'text-field': ['get', 'label'], 'text-size': 11, 'text-font': ['DIN Pro Medium', 'Arial Unicode MS Regular'] },
    paint: { 'text-color': '#1f2a37', 'text-halo-color': '#ffffff', 'text-halo-width': 1.5 },
  })
  map.addLayer({
    id: 'pressure-centres', type: 'symbol', source: 'pressure-isobars', filter: ['has', 'kind'],
    layout: { ...visibility, 'text-field': ['get', 'label'], 'text-size': 17, 'text-font': ['DIN Pro Bold', 'Arial Unicode MS Bold'], 'text-allow-overlap': true },
    paint: { 'text-color': ['match', ['get', 'kind'], 'L', '#2430a0', '#b3261e'], 'text-halo-color': '#ffffff', 'text-halo-width': 2 },
  })
}

async function updateFieldLayers() {
  if (!map?.getLayer('admin-region-fill')) return
  const raining = isRainfallScreeningActive.value
  const pressure = isPressureActive.value
  addFieldImage('rain-field', forecastFieldUrl('rain'), 0.85)
  addFieldImage('pressure-field', forecastFieldUrl('pressure'), 0.8)
  setLayerVisibility('rain-field', raining)
  setLayerVisibility('pressure-field', pressure)
  for (const layerId of ['pressure-isobar-lines', 'pressure-isobar-labels', 'pressure-centres']) setLayerVisibility(layerId, pressure)
  if (pressure) {
    try {
      const collection = await fetchPressureIsobars()
      pressureScale.value = { min: collection.scale_min_hpa, max: collection.scale_max_hpa }
      if (!map) return
      addIsobarLayers(collection)
      for (const layerId of ['pressure-isobar-lines', 'pressure-isobar-labels', 'pressure-centres']) setLayerVisibility(layerId, isPressureActive.value)
    } catch {
      // The pressure picture still shows without isobars.
    }
  }
  const showObserved = raining && showImerg.value
  if (showObserved && !imerg.value && !imergError.value) {
    try {
      imerg.value = await fetchLatestImerg()
    } catch {
      imergError.value = true
    }
  }
  if (!map) return
  if (imerg.value && !map.getSource('imerg-rain')) {
    map.addSource('imerg-rain', { type: 'image', url: imergImageUrl(), coordinates: imerg.value.coordinates })
    map.addLayer({ id: 'imerg-rain', type: 'raster', source: 'imerg-rain', layout: { visibility: 'none' }, paint: { 'raster-opacity': 0.9, 'raster-resampling': 'linear', 'raster-fade-duration': 0 } }, 'admin-region-fill')
  }
  setLayerVisibility('imerg-rain', showObserved)
}

function refreshFieldImages() {
  for (const [id, variable] of [['rain-field', 'rain'], ['pressure-field', 'pressure']]) {
    map?.getSource(id)?.updateImage({ url: forecastFieldUrl(variable), coordinates: FIELD_COORDINATES })
  }
  if (isPressureActive.value) void updateFieldLayers()
}

function updateWeatherLayer() {
  const isGridMode = isGridWeatherMode.value
  setLayerVisibility('flood-screening-fill', isGridMode)
  setLayerVisibility('flood-screening-outline', isGridMode)
  setLayerVisibility('flood-screening-hover', isGridMode)
  setFloodScreeningDisplay()
  setSatelliteImageVisibility()
  setWindForecastVisibility()
  void updateFieldLayers()
  void refreshProneOverlays()
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

function addTerrainRelief() {
  // Mapbox's own elevation tiles are rate-limited for this token, so relief comes from the open AWS Terrain Tiles (Terrarium).
  map.addSource('mapbox-dem', {
    type: 'raster-dem',
    tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
    encoding: 'terrarium',
    tileSize: 256,
    maxzoom: 12,
    attribution: 'Terrain: Mapzen / AWS Terrain Tiles (SRTM, USGS 3DEP, GMTED)',
  })
  const beforeLayerId = map.getStyle()?.layers?.find((layer) => layer.type === 'symbol')?.id
  map.addLayer({
    id: 'terrain-hillshade',
    type: 'hillshade',
    source: 'mapbox-dem',
    paint: { 'hillshade-exaggeration': 0.5, 'hillshade-shadow-color': '#26342f', 'hillshade-highlight-color': '#ffffff', 'hillshade-accent-color': '#3d5a50' },
  }, beforeLayerId)
}

function setTerrain3d() {
  if (!map) return
  if (show3d.value) {
    map.setTerrain({ source: 'mapbox-dem', exaggeration: 1.6 })
    map.easeTo({ pitch: 58, duration: 900 })
  } else {
    map.setTerrain(null)
    map.easeTo({ pitch: 0, duration: 700 })
  }
}

async function loadRainFloodStatus() {
  try {
    rainFloodStatus.value = await fetchRainFloodStatus()
  } catch {
    rainFloodStatus.value = { ready: false }
  }
  void refreshProneOverlays()
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

function pressureMeaning(hpa) {
  if (hpa < 1000) return 'Very low · typhoon-level pressure, storms likely'
  if (hpa < 1008) return 'Low · unsettled weather, showers likely'
  if (hpa < 1018) return 'Near normal (average is about 1013 hPa)'
  return 'High · calm, mostly clear weather'
}

const VERDICTS = {
  warning: ['Strong model signal here', 'warning'],
  watch: ['Model signal here', 'watch'],
  advisory: ['Weak model signal nearby', 'advisory'],
  none: ['No model signal here', 'none'],
}

function reportRow(parent, label, value) {
  const row = document.createElement('p')
  row.className = 'place-report-row'
  const name = document.createElement('span')
  name.textContent = label
  const text = document.createElement('b')
  text.textContent = value
  row.append(name, text)
  parent.append(row)
}

function reportSection(parent, title) {
  const heading = document.createElement('h4')
  heading.textContent = title
  parent.append(heading)
}

function fillPlaceReport(content, province, result, error) {
  content.replaceChildren()
  const title = document.createElement('strong')
  title.className = 'place-report-title'
  title.textContent = province?.name ? `${province.name}` : 'Selected spot'
  content.append(title)
  if (!result) {
    const message = document.createElement('p')
    message.className = 'place-report-note'
    message.textContent = province
      ? (error || 'The flood models could not be reached.')
      : `No Philippine province was found at this spot, so it may be open sea or outside the country. The flood models only cover Philippine land.${error ? ` (${error})` : ''}`
    content.append(message)
    return
  }
  const level = result.rain_model?.level ?? 'none'
  const [headline, tone] = VERDICTS[level]
  const verdict = document.createElement('div')
  verdict.className = `place-report-verdict place-report-${tone}`
  verdict.textContent = headline
  content.append(verdict)
  const why = document.createElement('p')
  why.className = 'place-report-note'
  const terrain = result.watch.terrain
  why.textContent = level === 'none'
    ? 'Our experimental models show no flood signal for this spot under the current forecast. That is not a guarantee of safety: the models were not validated on Philippine floods and can miss real flooding.'
    : 'Our experimental MindSpore rain model sees terrain and rain here that could let water collect. This is a model score, not a confirmed flood.'
  content.append(why)

  reportSection(content, 'Weather here')
  const forecast = result.forecast ?? province
  const layer = selectedWeatherLayer.value
  if (layer === 'temperature' && forecast?.temperature_2m_c !== undefined) reportRow(content, 'Air temperature', `${Number(forecast.temperature_2m_c).toFixed(1)} °C`)
  if (layer === 'pressure' && forecast?.pressure_msl_hpa !== undefined) {
    reportRow(content, 'Air pressure', `${Number(forecast.pressure_msl_hpa).toFixed(0)} hPa`)
    reportRow(content, 'What it means', pressureMeaning(Number(forecast.pressure_msl_hpa)).split(' · ')[0])
  }
  if (forecast) {
    reportRow(content, 'Rain, next 6 hours', `${Number(forecast.precipitation_6h_mm).toFixed(1)} mm`)
    reportRow(content, 'Rain, wettest day ahead', `${Number(forecast.rainfall_24h_mm).toFixed(0)} mm`)
    reportRow(content, 'Rain, next 3 days', `${Number(forecast.rainfall_72h_mm).toFixed(0)} mm`)
  }

  reportSection(content, 'Flood risk (MindSpore)')
  const flood = { high: 'High', moderate: 'Moderate', low: 'Low' }[terrain] ?? terrain
  reportRow(content, 'Flood-prone land', `${flood} · ${(result.local.land_share_high * 100).toFixed(0)}% of land within ${result.local.radius_km} km`)
  if (result.rain_model) {
    reportRow(content, 'Rain model score (within 1 km)', `${Math.round(result.rain_model.probability_nearby * 100)} of 100 · not a probability`)
  }

  const note = document.createElement('small')
  note.className = 'place-report-note'
  note.textContent = 'Research prototype using satellite data and experimental AI models. It is not validated on Philippine floods, can miss real flooding, and is not an official warning. Check PAGASA for advisories.'
  content.append(note)
}

async function openPlaceReport(event) {
  if (!map) return
  const styleReady = map.isStyleLoaded()
  const blocked = styleReady ? ['farm-parcel-fill', 'scan-markers', AI_FIELDS_FILL_ID].filter((layerId) => map.getLayer(layerId)) : []
  if (blocked.length && map.queryRenderedFeatures(event.point, { layers: blocked }).length) return
  const provinces = styleReady && map.getLayer('flood-screening-fill') ? map.queryRenderedFeatures(event.point, { layers: ['flood-screening-fill'] }) : []
  const province = provinces[0]?.properties ?? null
  const content = document.createElement('div')
  content.className = 'place-report'
  content.tabIndex = 0
  content.setAttribute('role', 'region')
  content.setAttribute('aria-label', 'Location report')
  const loading = document.createElement('p')
  loading.className = 'place-report-note'
  loading.textContent = 'Checking this spot with the MindSpore models…'
  content.append(loading)
  placePopup?.remove()
  const popup = new mapboxgl.Popup({ maxWidth: 'min(20rem, calc(100cqw - 1rem))', className: 'place-report-popup' }).setLngLat(event.lngLat).setDOMContent(content).addTo(map)
  placePopup = popup
  try {
    const result = await predictFloodProneAreas({
      latitude: Number(event.lngLat.lat.toFixed(6)),
      longitude: Number(event.lngLat.lng.toFixed(6)),
    })
    fillPlaceReport(content, province, result, '')
  } catch (error) {
    const offLand = province === null
    fillPlaceReport(content, province, null, offLand ? '' : (error instanceof Error ? error.message : 'The flood models could not be reached.'))
  } finally {
    if (placePopup === popup && popup.isOpen()) popup.setLngLat(event.lngLat)
  }
}

function setFloodScreeningDisplay() {
  const fillLayer = 'flood-screening-fill'
  const outlineLayer = 'flood-screening-outline'
  if (!map?.getLayer(fillLayer)) return

  if (isOutlookActive.value || isRainfallScreeningActive.value || isPressureActive.value) {
    // The picture is drawn by the raster layers; provinces stay as faint, clickable outlines.
    map.setFilter(fillLayer, null)
    map.setFilter(outlineLayer, null)
    map.setPaintProperty(fillLayer, 'fill-color', '#12372a')
    map.setPaintProperty(fillLayer, 'fill-opacity', 0.01)
    map.setPaintProperty(outlineLayer, 'line-opacity', 0.4)
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
    refreshFieldImages()
    if (proneVariant === 'outlook') {
      proneVariant = ''
      void refreshProneOverlays()
    }
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
    addTerrainRelief()
    addParcelLayer()
    void loadRainFloodStatus()
    if (isCloudBaseActive.value) setSatelliteImageVisibility()
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
    map.on('moveend', scheduleProneRefresh)
    void loadScanSummary()
    void refreshScanOverlays()
    scanPollTimer = window.setInterval(() => {
      void loadScanSummary()
      void refreshScanOverlays()
    }, 120000)
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
    void openPlaceReport(event)
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
  window.clearTimeout(proneRefreshTimer)
  window.clearTimeout(mapStartupTimer)
  window.clearInterval(scanPollTimer)
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