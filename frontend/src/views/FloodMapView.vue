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
        <p><strong>Context, not a forecast.</strong> Weather and historical flood layers are not damage assessments.</p>
      </div>
    </aside>
    <div class="map-stage">
      <ParcelMap ref="parcelMap" @location-selected="weatherCoordinates = $event" />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import ParcelMap from '../components/ParcelMap.vue'
import WeatherContextPanel from '../components/WeatherContextPanel.vue'

const weatherCoordinates = ref(null)
const parcelMap = ref(null)

function focusLocation(coordinates) {
  parcelMap.value?.focusLocation(coordinates)
}
</script>
