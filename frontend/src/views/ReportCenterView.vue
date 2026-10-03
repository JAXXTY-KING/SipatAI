<template>
  <div class="page-view">
    <header class="page-heading">
      <div><p class="eyebrow">DOCUMENTS</p><h1>Report center</h1><p class="page-description">Generate a report from the latest completed assessment.</p></div>
    </header>

    <p v-if="loading" class="connection-note" role="status">Loading the latest completed assessment…</p>
    <p v-else-if="message" class="connection-note" role="status">{{ message }}</p>

    <section v-if="assessment" class="report-summary">
      <div class="section-heading"><div><p class="eyebrow">READY TO GENERATE</p><h2>{{ assessment.event_name }}</h2></div></div>
      <dl class="report-fields">
        <div><dt>Municipality</dt><dd>{{ assessment.municipality }}</dd></div>
        <div><dt>Affected agricultural area</dt><dd>{{ assessment.total_affected_hectares.toLocaleString('en-PH') }} hectares</dd></div>
        <div><dt>Estimated damage</dt><dd>{{ formatCurrency(assessment.estimated_damage_php) }}</dd></div>
        <div><dt>Affected barangays</dt><dd>{{ assessment.affected_barangays }}</dd></div>
      </dl>
      <button class="button button-primary" type="button" :disabled="isGenerating" @click="generateReport">
        {{ isGenerating ? 'Generating…' : 'Download assessment PDF' }}
      </button>
      <p class="report-disclaimer">Damage valuation is shown only when configured for the assessment.</p>
    </section>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { downloadAssessmentReport, fetchDashboardSummary } from '../api/client'

const assessment = ref(null)
const isGenerating = ref(false)
const message = ref('')
const loading = ref(true)

const formatCurrency = (value) => value == null ? 'Not calculated' : new Intl.NumberFormat('en-PH', { style: 'currency', currency: 'PHP', maximumFractionDigits: 0 }).format(value)

onMounted(async () => {
  try {
    assessment.value = await fetchDashboardSummary()
  } catch {
    message.value = 'No completed assessment is available. Configure GaussDB/PostGIS and run a real assessment.'
  } finally {
    loading.value = false
  }
})

async function generateReport() {
  isGenerating.value = true
  message.value = ''
  try {
    const pdf = await downloadAssessmentReport()
    const url = URL.createObjectURL(pdf)
    const link = document.createElement('a')
    link.href = url
    link.download = `sipatai-assessment-${assessment.value.assessment_id}.pdf`
    link.click()
    URL.revokeObjectURL(url)
  } catch {
    message.value = 'The assessment report could not be generated.'
  } finally {
    isGenerating.value = false
  }
}
</script>
