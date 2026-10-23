<template>
  <section class="weather-context" aria-labelledby="weather-title">
    <div class="weather-heading">
      <div>
        <p class="eyebrow">WEATHER CONTEXT</p>
        <h2 id="weather-title">Current conditions</h2>
      </div>
    </div>
    <p class="connection-note">Search a Philippine city or municipality, or select a point on the map.</p>
    <form class="weather-search-form" @submit.prevent="searchLocations">
      <label>
        Place name
        <input v-model.trim="query" type="search" minlength="2" maxlength="120" placeholder="For example, Bacarra, Ilocos Norte" required />
      </label>
      <button class="button button-primary" type="submit" :disabled="isSearching || query.trim().length < 2">
        {{ isSearching ? 'Searching…' : 'Search places' }}
      </button>
    </form>
    <p v-if="message" class="connection-note" role="status">{{ message }}</p>
    <ul v-if="locations.length" class="weather-location-results" aria-label="Matching places">
      <li v-for="location in locations" :key="locationKey(location)">
        <button class="weather-location-option" type="button" @click="selectLocation(location)">
          <strong>{{ location.name }}</strong>
          <span>{{ [location.state, location.country].filter(Boolean).join(', ') }}</span>
        </button>
      </li>
    </ul>
    <div v-if="coordinates" class="weather-selected-location">
      <p>Selected: {{ selectedLocationLabel }}</p>
      <button class="button" type="button" :disabled="isLoading" @click="loadWeather">
        {{ isLoading ? 'Checking…' : 'Check current weather' }}
      </button>
    </div>
    <details class="weather-coordinate-fallback">
      <summary>Enter coordinates manually</summary>
      <form class="weather-form" @submit.prevent="useManualCoordinates">
        <label>
          Latitude
          <input v-model="latitudeInput" type="number" min="-90" max="90" step="any" required />
        </label>
        <label>
          Longitude
          <input v-model="longitudeInput" type="number" min="-180" max="180" step="any" required />
        </label>
        <button class="button" type="submit" :disabled="!manualCoordinatesReady || isLoading">
          {{ isLoading ? 'Checking…' : 'Use coordinates' }}
        </button>
      </form>
    </details>
    <dl v-if="weather" class="weather-values">
      <div><dt>Location</dt><dd>{{ weather.location_name || `${weather.latitude}, ${weather.longitude}` }}</dd></div>
      <div><dt>Observed (UTC)</dt><dd>{{ formatTime(weather.observed_at) }}</dd></div>
      <div><dt>Condition</dt><dd>{{ weather.condition }} · {{ weather.description }}</dd></div>
      <div><dt>Temperature</dt><dd>{{ weather.temperature_c }} °C</dd></div>
      <div><dt>Humidity</dt><dd>{{ weather.humidity_percent }}%</dd></div>
      <div><dt>Rain (last hour)</dt><dd>{{ weather.precipitation_1h_mm }} mm</dd></div>
    </dl>
    <p v-if="weather" class="weather-disclaimer">Weather is contextual information only; it is not a flood-model input or damage assessment.</p>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { fetchCurrentWeather, searchWeatherLocations } from '../api/client'

const props = defineProps({ coordinates: { type: Object, default: null } })
const query = ref('')
const locations = ref([])
const selectedLocation = ref(null)
const coordinates = ref(null)
const weather = ref(null)
const message = ref('')
const isLoading = ref(false)
const isSearching = ref(false)
const latitudeInput = ref('')
const longitudeInput = ref('')
const manualCoordinatesReady = computed(() => {
  const latitude = Number(latitudeInput.value)
  const longitude = Number(longitudeInput.value)
  return latitudeInput.value !== ''
    && longitudeInput.value !== ''
    && Number.isFinite(latitude)
    && Number.isFinite(longitude)
    && latitude >= -90
    && latitude <= 90
    && longitude >= -180
    && longitude <= 180
})

watch(() => props.coordinates, () => {
  if (props.coordinates) {
    latitudeInput.value = String(props.coordinates.latitude)
    longitudeInput.value = String(props.coordinates.longitude)
    coordinates.value = props.coordinates
    selectedLocation.value = null
  }
  weather.value = null
  message.value = ''
})

const selectedLocationLabel = computed(() => selectedLocation.value
  ? [selectedLocation.value.name, selectedLocation.value.state, selectedLocation.value.country].filter(Boolean).join(', ')
  : `${coordinates.value.latitude}, ${coordinates.value.longitude}`)

function locationKey(location) {
  return `${location.name}-${location.state ?? ''}-${location.latitude}-${location.longitude}`
}

function selectLocation(location) {
  selectedLocation.value = location
  coordinates.value = { latitude: location.latitude, longitude: location.longitude }
  weather.value = null
  message.value = ''
}

async function searchLocations() {
  if (query.value.trim().length < 2) return
  isSearching.value = true
  locations.value = []
  weather.value = null
  message.value = ''
  try {
    const result = await searchWeatherLocations(query.value.trim())
    locations.value = result.locations ?? []
    if (!locations.value.length) message.value = 'No matching Philippine places were found.'
  } catch (error) {
    message.value = error instanceof Error ? error.message : 'Place search is unavailable.'
  } finally {
    isSearching.value = false
  }
}

function useManualCoordinates() {
  if (!manualCoordinatesReady.value) return
  selectedLocation.value = null
  coordinates.value = {
    latitude: Number(latitudeInput.value),
    longitude: Number(longitudeInput.value),
  }
  weather.value = null
  message.value = ''
  void loadWeather()
}

function formatTime(value) {
  return new Intl.DateTimeFormat('en-PH', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(new Date(value))
}

async function loadWeather() {
  if (!coordinates.value) return
  isLoading.value = true
  message.value = ''
  try {
    weather.value = await fetchCurrentWeather(coordinates.value)
  } catch (error) {
    weather.value = null
    message.value = error instanceof Error ? error.message : 'Current weather is unavailable.'
  } finally {
    isLoading.value = false
  }
}
</script>
