<template>
  <div class="page-view">
    <header class="page-heading">
      <div>
        <p class="eyebrow">ASSESSMENT OVERVIEW</p>
        <h1>Flood monitoring dashboard</h1>
        <p class="page-description" v-if="assessment">{{ assessment.event_name }} · {{ assessment.municipality }}</p>
        <p class="page-description" v-else>Forecast screening and verified assessment status</p>
      </div>
      <div class="dashboard-actions">
        <RouterLink class="button" to="/scenes">Search satellite scenes</RouterLink>
        <RouterLink class="button button-primary" to="/reports">Open report center</RouterLink>
      </div>
    </header>

    <section class="data-section screening-dashboard" aria-labelledby="screening-heading">
      <div class="section-heading">
        <div><p class="eyebrow">NATIONWIDE · 72-HOUR MODEL FORECAST</p><h2 id="screening-heading">Rainfall &amp; elevation screening</h2></div>
        <RouterLink class="text-link" to="/">Open screening map</RouterLink>
      </div>
      <p v-if="screeningLoading" class="connection-note" role="status">Loading the latest forecast screening…</p>
      <p v-else-if="screeningMessage" class="connection-note" role="status">{{ screeningMessage }}</p>
      <template v-else-if="screening">
        <div class="metric-grid" aria-label="Forecast screening grid summary">
          <article class="metric">
            <span class="metric-label">Grid cells screened</span>
            <strong>{{ screening.features.length.toLocaleString() }}</strong>
            <span class="metric-unit">coarse forecast cells · not parcels</span>
          </article>
          <article class="metric">
            <span class="metric-label">Elevated screening tier</span>
            <strong>{{ screeningCounts.elevated }}</strong>
            <span class="metric-unit">cells meeting the prototype threshold</span>
          </article>
          <article class="metric">
            <span class="metric-label">Watch screening tier</span>
            <strong>{{ screeningCounts.watch }}</strong>
            <span class="metric-unit">cells meeting the prototype threshold</span>
          </article>
          <article class="metric">
            <span class="metric-label">Peak 24-hour rainfall</span>
            <strong>{{ peakRainfall ? `${peakRainfall.properties.rainfall_24h_mm.toFixed(1)} mm` : 'Not available' }}</strong>
            <span class="metric-unit" v-if="peakRainfall">grid center {{ peakRainfall.properties.latitude }}, {{ peakRainfall.properties.longitude }}</span>
          </article>
        </div>
        <p class="screening-attribution">
          Provider: {{ screening.provider }} · fetched {{ formatTime(screening.fetched_at) }}.
          These are screening grid-cell counts, not hectares, farms, flood probabilities, typhoon detections, or official warnings.
          Thresholds are prototype-only and unvalidated.
          <a href="https://www.pagasa.dost.gov.ph/" target="_blank" rel="noreferrer">Consult PAGASA for official advisories.</a>
        </p>
        <section class="screening-hotspots" aria-labelledby="hotspots-heading">
          <div class="section-heading">
            <div>
              <p class="eyebrow">MODEL FORECAST · GRID-CELL CENTERS</p>
              <h3 id="hotspots-heading">Highest forecast rainfall</h3>
            </div>
            <RouterLink class="text-link" to="/">Open screening map</RouterLink>
          </div>
          <p class="connection-note">
            Ranked by the highest rolling 24-hour rainfall total in the 72-hour forecast. Select a row to inspect its grid cell on the map.
          </p>
          <div v-if="topRainfallCells.length" class="table-wrap">
            <table>
              <thead>
                <tr><th>Rank</th><th>24-hour peak</th><th>72-hour total</th><th>Elevation</th><th>Screening tier</th><th>Location</th></tr>
              </thead>
              <tbody>
                <tr v-for="(feature, index) in topRainfallCells" :key="`${feature.properties.latitude}-${feature.properties.longitude}`">
                  <td data-label="Rank">{{ index + 1 }}</td>
                  <td data-label="24-hour peak"><strong>{{ feature.properties.rainfall_24h_mm.toFixed(1) }} mm</strong></td>
                  <td data-label="72-hour total">{{ feature.properties.rainfall_72h_mm.toFixed(1) }} mm</td>
                  <td data-label="Elevation">{{ feature.properties.elevation_m == null ? 'Not available' : `${feature.properties.elevation_m.toFixed(0)} m` }}</td>
                  <td data-label="Screening tier">
                    <span class="severity-tag" :class="`screening-tier-${feature.properties.screening_level}`">
                      {{ feature.properties.screening_level }}
                    </span>
                  </td>
                  <td data-label="Location">
                    <RouterLink
                      class="text-link screening-map-link"
                      :to="{ name: 'flood-map', query: { lat: feature.properties.latitude, lon: feature.properties.longitude } }"
                    >
                      Inspect {{ formatCoordinates(feature.properties.latitude, feature.properties.longitude) }}
                    </RouterLink>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="connection-note">No forecast grid cells are available to rank.</p>
          <p class="screening-attribution">
            Coordinates identify approximate forecast grid-cell centers, not administrative place names or parcel locations. Rainfall and elevation thresholds are unvalidated prototype screening criteria.
          </p>
        </section>
      </template>
    </section>

    <section class="data-section assessment-status-panel" aria-labelledby="assessment-status-heading">
      <div class="section-heading">
        <div><p class="eyebrow">DATABASE ASSESSMENT</p><h2 id="assessment-status-heading">Completed agricultural assessment</h2></div>
        <span class="service-state" :class="assessment ? 'service-state-configured' : 'service-state-not_configured'">
          {{ assessment ? 'Completed assessment available' : 'Not available' }}
        </span>
      </div>
      <p v-if="loading" class="connection-note" role="status">Checking the latest completed assessment…</p>
      <p v-else-if="apiMessage" class="connection-note" role="status">{{ apiMessage }}</p>
      <p v-else class="connection-note">Assessment data is available from the configured database. The forecast screening above remains separate from measured farm damage.</p>
    </section>

    <template v-if="assessment">
    <section class="metric-grid" aria-label="Assessment summary">
      <article class="metric">
        <span class="metric-label">Affected agricultural area</span>
        <strong>{{ formatArea(assessment.total_affected_hectares) }}</strong>
        <span class="metric-unit">hectares</span>
      </article>
      <article class="metric">
        <span class="metric-label">Estimated crop damage</span>
        <strong>{{ formatCurrency(assessment.estimated_damage_php) }}</strong>
        <span class="metric-unit">Philippine pesos</span>
      </article>
      <article class="metric">
        <span class="metric-label">Affected barangays</span>
        <strong>{{ assessment.affected_barangays }}</strong>
        <span class="metric-unit">in completed assessment</span>
      </article>
    </section>

    <section class="data-section">
      <div class="section-heading">
        <div><p class="eyebrow">SPATIAL REVIEW</p><h2>Damage by barangay</h2></div>
        <RouterLink class="text-link" to="/flood-map">View flood map</RouterLink>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Barangay</th><th>Crop</th><th>Affected area</th><th>Damage estimate</th><th>Severity</th></tr></thead>
          <tbody>
            <tr v-for="row in assessment.assessments" :key="row.barangay">
              <td data-label="Barangay">{{ row.barangay }}</td>
              <td data-label="Crop">{{ row.crop }}</td>
              <td data-label="Affected area">{{ formatArea(row.affected_hectares) }} ha</td>
              <td data-label="Damage estimate">Not calculated</td>
              <td data-label="Severity"><span class="severity-tag" :class="`severity-${(row.severity ?? 'unclassified').toLowerCase()}`">{{ row.severity ?? 'Not classified' }} · {{ row.damage_percent }}%</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { fetchDashboardSummary, fetchFloodScreening } from '../api/client'

const assessment = ref(null)
const screening = ref(null)
const apiMessage = ref('')
const screeningMessage = ref('')
const loading = ref(true)
const screeningLoading = ref(true)

const formatArea = (value) => value == null ? 'Not available' : new Intl.NumberFormat('en-PH', { maximumFractionDigits: 1 }).format(value)
const formatCurrency = (value) => value == null ? 'Not calculated' : new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP', maximumFractionDigits: 0 }).format(value)
const formatTime = (value) => value ? new Intl.DateTimeFormat('en-PH', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : 'unknown'
const formatCoordinates = (latitude, longitude) => `${Number(latitude).toFixed(2)}°, ${Number(longitude).toFixed(2)}°`
const screeningCounts = ref({ elevated: 0, watch: 0, lower: 0 })
const peakRainfall = ref(null)
const topRainfallCells = computed(() => (screening.value?.features ?? [])
  .filter((feature) => Number.isFinite(feature.properties?.rainfall_24h_mm))
  .slice()
  .sort((left, right) => right.properties.rainfall_24h_mm - left.properties.rainfall_24h_mm)
  .slice(0, 5))

onMounted(() => {
  void fetchDashboardSummary()
    .then((result) => {
      assessment.value = result
    })
    .catch(() => {
      apiMessage.value = 'No completed agricultural assessment is available. GaussDB/PostGIS and a real, validated assessment are required; forecast screening is not a substitute.'
    })
    .finally(() => { loading.value = false })

  void fetchFloodScreening()
    .then((result) => {
      screening.value = result
      screeningCounts.value = result.features.reduce((counts, feature) => {
        const tier = feature.properties?.screening_level
        if (tier && Object.hasOwn(counts, tier)) counts[tier] += 1
        return counts
      }, { elevated: 0, watch: 0, lower: 0 })
      peakRainfall.value = result.features.reduce((peak, feature) => (
        !peak || feature.properties.rainfall_24h_mm > peak.properties.rainfall_24h_mm ? feature : peak
      ), null)
    })
    .catch((error) => {
      screeningMessage.value = `Forecast screening is unavailable: ${error instanceof Error ? error.message : 'service error'}`
    })
    .finally(() => { screeningLoading.value = false })
})
</script>
