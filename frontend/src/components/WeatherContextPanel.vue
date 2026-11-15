<template>
  <section class="weather-context" aria-labelledby="weather-title">
    <div class="weather-heading">
      <div>
        <p class="eyebrow">SEARCH</p>
        <h2 id="weather-title">Find a place</h2>
      </div>
    </div>
    <p class="connection-note">Type a city or town, or click anywhere on the map. You get the weather and the flood report for that spot.</p>
    <form class="weather-search-form" @submit.prevent="searchLocations">
      <label>
        <span class="visually-hidden">Place name</span>
        <input v-model.trim="query" type="search" minlength="2" maxlength="120" placeholder="Search a place in the Philippines" required />
      </label>
      <button class="button button-primary" type="submit" :disabled="isSearching || query.trim().length < 2">
        {{ isSearching ? 'Searching…' : 'Search places' }}
      </button>
    </form>
    <p v-if="message" class="connection-note" role="status">{{ message }}</p>
    <p v-if="locations.length" class="connection-note">Select a result to show it on the map.</p>
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
      <div><dt>Model time (UTC)</dt><dd>{{ formatTime(weather.observed_at) }}</dd></div>
      <div><dt>Condition</dt><dd>{{ weather.condition }} · {{ weather.description }}</dd></div>
      <div><dt>Temperature</dt><dd>{{ weather.temperature_c }} °C</dd></div>
      <div><dt>Humidity</dt><dd>{{ weather.humidity_percent }}%</dd></div>
      <div><dt>Rain (last hour)</dt><dd>{{ weather.precipitation_1h_mm }} mm</dd></div>
    </dl>
    <p v-if="weather" class="weather-disclaimer">Open-Meteo model conditions are contextual guidance, not a local station observation, flood-model input, or damage assessment.</p>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { fetchCurrentWeather, searchWeatherLocations } from '../api/client'

const props = defineProps({ coordinates: { type: Object, default: null } })
const emit = defineEmits(['location-selected'])
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
let weatherRequestSequence = 0
let searchRequestSequence = 0
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
  weatherRequestSequence += 1
  isLoading.value = false
  if (props.coordinates) {
    latitudeInput.value = String(props.coordinates.latitude)
    longitudeInput.value = String(props.coordinates.longitude)
    coordinates.value = props.coordinates
    selectedLocation.value = null
  }
  weather.value = null
  message.value = ''
})

watch(query, () => {
  searchRequestSequence += 1
  locations.value = []
  isSearching.value = false
  message.value = ''
})

const selectedLocationLabel = computed(() => selectedLocation.value
  ? [selectedLocation.value.name, selectedLocation.value.state, selectedLocation.value.country].filter(Boolean).join(', ')
  : `${coordinates.value.latitude}, ${coordinates.value.longitude}`)

function locationKey(location) {
  return `${location.name}-${location.state ?? ''}-${location.latitude}-${location.longitude}`
}

function selectLocation(location) {
  weatherRequestSequence += 1
  selectedLocation.value = location
  coordinates.value = { latitude: location.latitude, longitude: location.longitude }
  latitudeInput.value = String(location.latitude)
  longitudeInput.value = String(location.longitude)
  weather.value = null
  message.value = ''
  locations.value = []
  emit('location-selected', coordinates.value)
  void loadWeather()
}

async function searchLocations() {
  if (query.value.trim().length < 2) return
  const requestId = ++searchRequestSequence
  const searchQuery = query.value.trim()
  isSearching.value = true
  locations.value = []
  message.value = ''
  try {
    const result = await searchWeatherLocations(searchQuery)
    if (requestId !== searchRequestSequence) return
    locations.value = result.locations ?? []
    if (!locations.value.length) message.value = 'No matching Philippine places were found.'
  } catch (error) {
    if (requestId === searchRequestSequence) {
      message.value = error instanceof TypeError
        ? 'Could not reach the API. Check that the backend is running and try again.'
        : error instanceof Error ? error.message : 'Place search is unavailable.'
    }
  } finally {
    if (requestId === searchRequestSequence) isSearching.value = false
  }
}

function useManualCoordinates() {
  if (!manualCoordinatesReady.value) return
  weatherRequestSequence += 1
  selectedLocation.value = null
  coordinates.value = {
    latitude: Number(latitudeInput.value),
    longitude: Number(longitudeInput.value),
  }
  weather.value = null
  message.value = ''
  emit('location-selected', coordinates.value)
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
  const requestId = ++weatherRequestSequence
  isLoading.value = true
  message.value = ''
  try {
    const result = await fetchCurrentWeather(coordinates.value)
    if (requestId === weatherRequestSequence) weather.value = result
  } catch (error) {
    if (requestId === weatherRequestSequence) {
      weather.value = null
      message.value = error instanceof Error ? error.message : 'Current weather is unavailable.'
    }
  } finally {
    if (requestId === weatherRequestSequence) isLoading.value = false
  }
}
</script>
