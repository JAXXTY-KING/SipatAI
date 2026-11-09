<template>
  <div class="map-workspace">
    <aside class="explore-panel" aria-label="Map exploration">
      <div class="explore-intro">
        <p class="eyebrow">SIPATAI MAP EXPLORER</p>
        <h1>See the bigger picture.</h1>
        <p>Explore weather, land and flood context across the Philippines.</p>
      </div>
      <WeatherContextPanel
        :coordinates="weatherCoordinates"
        @location-selected="focusLocation"
      />
      <div class="explore-note">
        <span class="explore-note-icon" aria-hidden="true">i</span>
        <p><strong>Screening, not a prediction.</strong> Forecast rain and elevation provide a coarse prototype view, not a typhoon track, official warning, or flood boundary.</p>
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
