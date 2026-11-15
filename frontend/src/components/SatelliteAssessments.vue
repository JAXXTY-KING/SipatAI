<template>
  <section class="data-section satellite-assessments" aria-labelledby="satellite-assessments-heading">
    <div class="section-heading">
      <div>
        <p class="eyebrow">MINDSPORE · REAL SENTINEL-1/2 IMAGERY</p>
        <h2 id="satellite-assessments-heading">Satellite flood assessments</h2>
      </div>
      <RouterLink class="text-link" to="/">Analyse another area</RouterLink>
    </div>
    <p v-if="loading" class="connection-note" role="status">Loading saved assessments…</p>
    <p v-else-if="message" class="connection-note" role="status">{{ message }}</p>
    <p v-else-if="!assessments.length" class="connection-note">
      No assessments yet. Open the map, choose a place, and press “Analyse flood extent here” in the MindSpore flood AI panel; each result is saved here.
    </p>
    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>#</th><th>Location</th><th>Imagery</th><th>Flooded land</th><th>Flooded cropland</th><th>Fields affected</th><th v-if="withReports">Report</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="record in assessments" :key="record.id">
            <td data-label="#">{{ record.id }}</td>
            <td data-label="Location">
              <RouterLink class="text-link" :to="{ name: 'flood-map', query: { lat: record.latitude, lon: record.longitude } }">
                {{ record.latitude.toFixed(3) }}°, {{ record.longitude.toFixed(3) }}°
              </RouterLink>
            </td>
            <td data-label="Imagery">
              Radar {{ record.observations.sentinel_1.datetime.slice(0, 10) }}<br>
              Optical {{ record.observations.sentinel_2.datetime.slice(0, 10) }} · {{ record.observations.sentinel_2.cloud_cover_percent }}% cloud
            </td>
            <td data-label="Flooded land">
              <strong>{{ record.statistics.flooded_area_km2 }} km²</strong>
              ({{ (record.statistics.flooded_fraction * 100).toFixed(1) }}%)
            </td>
            <td data-label="Flooded cropland">
              <template v-if="record.cropland">{{ record.cropland.flooded_cropland_km2 }} of {{ record.cropland.cropland_area_km2 }} km²</template>
              <template v-else>Not available</template>
            </td>
            <td data-label="Fields affected">
              <template v-if="record.field_summary">
                {{ record.field_summary.fields_affected }} of {{ record.field_summary.fields_analysed }}
                <small>({{ record.field_summary.severity_counts.Severe }} severe)</small>
              </template>
              <template v-else>Not available</template>
            </td>
            <td v-if="withReports" data-label="Report">
              <button class="button" type="button" :disabled="busyId === record.id" @click="downloadReport(record.id)">
                {{ busyId === record.id ? 'Generating…' : 'PDF' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="screening-attribution">
      Flood extent comes from the MindSpore ResNet-50 U-Net on live Sentinel imagery; cropland is ESA WorldCover 2021; fields are Fields of The World
      detections (not legal parcels). Estimates only, not an official flood boundary or damage valuation.
    </p>
    <p v-if="reportError" class="connection-note" role="alert">{{ reportError }}</p>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { downloadSatelliteAssessmentReport, fetchSatelliteAssessments } from '../api/client'

defineProps({
  withReports: { type: Boolean, default: false },
})

const assessments = ref([])
const loading = ref(true)
const message = ref('')
const busyId = ref(null)
const reportError = ref('')

onMounted(() => {
  void fetchSatelliteAssessments()
    .then((result) => { assessments.value = result.assessments })
    .catch((error) => {
      message.value = `Saved assessments are unavailable: ${error instanceof Error ? error.message : 'service error'}`
    })
    .finally(() => { loading.value = false })
})

async function downloadReport(assessmentId) {
  busyId.value = assessmentId
  reportError.value = ''
  try {
    const pdf = await downloadSatelliteAssessmentReport(assessmentId)
    const url = URL.createObjectURL(pdf)
    const link = document.createElement('a')
    link.href = url
    link.download = `sipatai-satellite-assessment-${assessmentId}.pdf`
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    reportError.value = error instanceof Error ? error.message : 'The report could not be generated.'
  } finally {
    busyId.value = null
  }
}
</script>
