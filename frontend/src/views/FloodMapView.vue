<template>
  <div class="map-workspace">
    <aside class="explore-panel" aria-label="Map exploration">
      <div class="explore-intro">
        <p class="eyebrow">SIPATAI MAP EXPLORER</p>
        <h1>Where could it flood next?</h1>
        <p>Real satellite images, real weather and three MindSpore AI models, brought together on one map of the Philippines.</p>
      </div>
      <WeatherContextPanel
        :coordinates="weatherCoordinates"
        @location-selected="focusLocation"
      />
      <div class="explore-note">
        <span class="explore-note-icon" aria-hidden="true">i</span>
        <p><strong>A research prototype, not an official warning.</strong> Predictions come from AI models trained on past floods and tested on floods they had not seen. Always follow PAGASA and your local disaster office.</p>
      </div>
    </aside>
    <div class="map-stage">
      <ParcelMap
        ref="parcelMap"
        :initial-location="initialLocation"
        @location-selected="weatherCoordinates = $event"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import ParcelMap from '../components/ParcelMap.vue'
import WeatherContextPanel from '../components/WeatherContextPanel.vue'

const weatherCoordinates = ref(null)
const parcelMap = ref(null)
const route = useRoute()
const initialLocation = computed(() => {
  const latitude = Number(route.query.lat)
  const longitude = Number(route.query.lon)
  if (
    !Number.isFinite(latitude)
    || !Number.isFinite(longitude)
    || latitude < 4.5
    || latitude > 21.2
    || longitude < 116.9
    || longitude > 126.6
  ) return null
  return { latitude, longitude }
})

function focusLocation(coordinates) {
  parcelMap.value?.focusLocation(coordinates)
}
</script>
