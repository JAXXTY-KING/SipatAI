<template>
  <div class="page-view">
    <header class="page-heading">
      <div><p class="eyebrow">DOCUMENTS</p><h1>Report center</h1><p class="page-description">Download a forecast-screening brief or a report from a completed database assessment.</p></div>
    </header>

    <p v-if="screeningLoading" class="connection-note" role="status">Checking forecast screening availability…</p>
    <p v-else-if="screeningMessage" class="connection-note" role="status">{{ screeningMessage }}</p>

    <section v-else-if="screening" class="report-summary screening-report-card">
      <div class="section-heading">
        <div><p class="eyebrow">PUBLIC FORECAST DATA · {{ screening.provider }}</p><h2>Rainfall &amp; elevation screening brief</h2></div>
      </div>
      <p class="page-description">
        {{ screening.features.length }} coarse grid cells · fetched {{ formatTime(screening.fetched_at) }} · {{ screening.forecast_period_hours }}-hour forecast horizon.
      </p>
      <p class="report-disclaimer">
        This is a prototype screening summary, not a typhoon track, official warning, flood boundary, affected-farm estimate, or damage assessment.
        No parcel data is used.
      </p>
      <button class="button button-primary" type="button" :disabled="isGeneratingScreening" @click="generateScreeningReport">
        {{ isGeneratingScreening ? 'Generating…' : 'Download screening brief (PDF)' }}
      </button>
    </section>

    <section class="report-summary assessment-report-card">
      <template v-if="loading">
        <p class="connection-note" role="status">Checking for a completed database assessment…</p>
      </template>
      <template v-else-if="assessment">
        <div class="section-heading"><div><p class="eyebrow">COMPLETED DATABASE ASSESSMENT</p><h2>{{ assessment.event_name }}</h2></div></div>
        <dl class="report-fields">
          <div><dt>Municipality</dt><dd>{{ assessment.municipality }}</dd></div>
          <div><dt>Affected agricultural area</dt><dd>{{ assessment.total_affected_hectares.toLocaleString('en-PH') }} hectares</dd></div>
          <div><dt>Estimated damage</dt><dd>{{ formatCurrency(assessment.estimated_damage_php) }}</dd></div>
          <div><dt>Affected barangays</dt><dd>{{ assessment.affected_barangays }}</dd></div>
        </dl>
        <button class="button button-primary" type="button" :disabled="isGeneratingAssessment" @click="generateAssessmentReport">
          {{ isGeneratingAssessment ? 'Generating…' : 'Download assessment PDF' }}
        </button>
        <p class="report-disclaimer">Damage valuation is shown only when configured for the assessment.</p>
      </template>
      <template v-else>
        <div class="section-heading"><div><p class="eyebrow">DATABASE-BASED REPORT</p><h2>No completed agricultural assessment</h2></div></div>
        <p class="connection-note">{{ assessmentMessage }}</p>
        <p class="report-disclaimer">This is intentionally separate from the forecast screening brief. Do not treat rainfall-screening cells as farms, affected hectares, or crop losses.</p>
      </template>
    </section>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { downloadAssessmentReport, downloadFloodScreeningReport, fetchDashboardSummary, fetchFloodScreening } from '../api/client'

const assessment = ref(null)
const screening = ref(null)
const isGeneratingAssessment = ref(false)
const isGeneratingScreening = ref(false)
const screeningMessage = ref('')
const assessmentMessage = ref('')
const loading = ref(true)
const screeningLoading = ref(true)

const formatCurrency = (value) => value == null ? 'Not calculated' : new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP', maximumFractionDigits: 0 }).format(value)
const formatTime = (value) => new Intl.DateTimeFormat('en-PH', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))

onMounted(() => {
  void fetchDashboardSummary()
    .then((result) => { assessment.value = result })
    .catch(() => {
      assessmentMessage.value = 'No completed assessment is available. Configure GaussDB/PostGIS and complete a real, validated assessment.'
    })
    .finally(() => { loading.value = false })

  void fetchFloodScreening()
    .then((result) => { screening.value = result })
    .catch((error) => {
      screeningMessage.value = `Forecast screening is unavailable: ${error instanceof Error ? error.message : 'service error'}`
    })
    .finally(() => { screeningLoading.value = false })
})

function downloadPdf(pdf, filename) {
  const url = URL.createObjectURL(pdf)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

async function generateScreeningReport() {
  isGeneratingScreening.value = true
  screeningMessage.value = ''
  try {
    const pdf = await downloadFloodScreeningReport()
    downloadPdf(pdf, 'sipatai-rainfall-screening-brief.pdf')
  } catch (error) {
    screeningMessage.value = error instanceof Error ? error.message : 'The forecast-screening brief could not be generated.'
  } finally {
    isGeneratingScreening.value = false
  }
}

async function generateAssessmentReport() {
  isGeneratingAssessment.value = true
  assessmentMessage.value = ''
  try {
    const pdf = await downloadAssessmentReport()
    downloadPdf(pdf, `sipatai-assessment-${assessment.value.assessment_id}.pdf`)
  } catch (error) {
    assessmentMessage.value = error instanceof Error ? error.message : 'The assessment report could not be generated.'
  } finally {
    isGeneratingAssessment.value = false
  }
}
</script>
