<template>
  <div class="page-view">
    <header class="page-heading">
      <div>
        <p class="eyebrow">ASSESSMENT OVERVIEW</p>
        <h1>Flood damage dashboard</h1>
        <p class="page-description" v-if="assessment">{{ assessment.event_name }} · {{ assessment.municipality }}</p>
        <p class="page-description" v-else>Latest completed assessment from the spatial database</p>
      </div>
      <RouterLink class="button button-primary" to="/reports">Open report center</RouterLink>
    </header>

    <p v-if="loading" class="connection-note" role="status">Loading the latest completed assessment…</p>
    <p v-else-if="apiMessage" class="connection-note" role="status">{{ apiMessage }}</p>

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
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { fetchDashboardSummary } from '../api/client'

const assessment = ref(null)
const apiMessage = ref('')
const loading = ref(true)

const formatArea = (value) => value == null ? 'Not available' : new Intl.NumberFormat('en-PH', { maximumFractionDigits: 1 }).format(value)
const formatCurrency = (value) => value == null ? 'Not calculated' : new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP', maximumFractionDigits: 0 }).format(value)

onMounted(async () => {
  try {
    assessment.value = await fetchDashboardSummary()
    apiMessage.value = ''
  } catch {
    apiMessage.value = 'No completed assessment is available. Configure GaussDB/PostGIS and run a real assessment.'
  } finally {
    loading.value = false
  }
})
</script>
