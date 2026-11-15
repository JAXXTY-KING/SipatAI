<template>
  <section class="data-section nationwide-scan" aria-labelledby="nationwide-scan-heading">
    <div class="section-heading">
      <div>
        <p class="eyebrow">MINDSPORE · NEWEST SENTINEL-1 PASS PER TILE</p>
        <h2 id="nationwide-scan-heading">Nationwide satellite flood scan</h2>
      </div>
      <RouterLink class="text-link" to="/">Open on the map</RouterLink>
    </div>
    <p v-if="loading" class="connection-note" role="status">Loading scan coverage…</p>
    <p v-else-if="message" class="connection-note" role="status">{{ message }}</p>
    <template v-else-if="summary">
      <div class="metric-grid" aria-label="Nationwide scan summary">
        <article class="metric">
          <span class="metric-label">Land tiles scanned</span>
          <strong>{{ summary.tiles_scanned.toLocaleString() }}</strong>
          <span class="metric-unit">of {{ summary.tiles_total.toLocaleString() }} · {{ (summary.coverage_fraction * 100).toFixed(2) }}% of the Philippines</span>
        </article>
        <article class="metric">
          <span class="metric-label">Flood water detected</span>
          <strong>{{ summary.flooded_km2.toLocaleString() }}</strong>
          <span class="metric-unit">km² in {{ summary.tiles_with_flooding }} tiles</span>
        </article>
        <article class="metric">
          <span class="metric-label">With clear optical imagery</span>
          <strong>{{ summary.tiles_with_optical.toLocaleString() }}</strong>
          <span class="metric-unit">remaining tiles used radar only</span>
        </article>
      </div>
      <div v-if="summary.provinces.length" class="table-wrap">
        <table>
          <thead><tr><th>Province</th><th>Tiles scanned</th><th>Tiles with flooding</th><th>Flood water</th></tr></thead>
          <tbody>
            <tr v-for="row in summary.provinces.slice(0, 15)" :key="row.province">
              <td data-label="Province">{{ row.province }}</td>
              <td data-label="Tiles scanned">{{ row.tiles_scanned }} of {{ row.tiles_total }}</td>
              <td data-label="Tiles with flooding">{{ row.tiles_with_flooding }}</td>
              <td data-label="Flood water"><strong>{{ row.flooded_km2 }} km²</strong></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p class="screening-attribution">
        Last scan {{ summary.last_scan ?? 'never' }} · Sentinel-1 passes {{ summary.radar_dates[0] ?? '–' }} to {{ summary.radar_dates[1] ?? '–' }}.
        Provinces not listed have not been scanned yet, which is not the same as no flooding. Flood water includes irrigated paddies and
        fishponds that look like water to radar; results are estimates, not an official flood boundary.
      </p>
    </template>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { fetchScanSummary } from '../api/client'

const summary = ref(null)
const loading = ref(true)
const message = ref('')

onMounted(() => {
  void fetchScanSummary()
    .then((result) => { summary.value = result })
    .catch((error) => {
      message.value = `Scan summary is unavailable: ${error instanceof Error ? error.message : 'service error'}`
    })
    .finally(() => { loading.value = false })
})
</script>
