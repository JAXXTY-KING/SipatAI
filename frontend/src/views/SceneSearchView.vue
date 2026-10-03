<template>
  <div class="page-view">
    <header class="page-heading">
      <div>
        <p class="eyebrow">COPERNICUS DATA SPACE</p>
        <h1>Satellite scenes</h1>
        <p class="page-description">Search Sentinel imagery intersecting the Philippines.</p>
      </div>
    </header>

    <form class="scene-search-form" @submit.prevent="searchScenes">
      <label>
        Satellite
        <select v-model="collection">
          <option value="sentinel-1-grd">Sentinel-1 GRD · radar</option>
          <option value="sentinel-2-l2a">Sentinel-2 L2A · optical</option>
        </select>
      </label>
      <label>
        Acquired from
        <input v-model="startDate" type="date" required />
      </label>
      <label>
        Acquired through
        <input v-model="endDate" type="date" required />
      </label>
      <label v-if="collection === 'sentinel-2-l2a'">
        Maximum cloud cover (%)
        <input v-model.number="maxCloudCover" type="number" min="0" max="100" step="1" />
      </label>
      <button class="button button-primary" type="submit" :disabled="isSearching">
        {{ isSearching ? 'Searching…' : 'Search scenes' }}
      </button>
    </form>

    <p v-if="message" class="connection-note" role="status">{{ message }}</p>

    <section v-if="features.length" class="data-section scene-results" aria-label="Satellite scenes">
      <div class="section-heading">
        <div><p class="eyebrow">SEARCH RESULTS</p><h2>{{ features.length }} scenes</h2></div>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Product</th><th>Acquired</th><th>Cloud cover</th><th>Footprint</th></tr></thead>
          <tbody>
            <tr v-for="scene in features" :key="scene.id">
              <td data-label="Product">{{ scene.id }}</td>
              <td data-label="Acquired">{{ formatDate(scene.properties?.datetime) }}</td>
              <td data-label="Cloud cover">{{ cloudCover(scene) }}</td>
              <td data-label="Footprint">{{ formatBounds(scene.bbox) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { searchSatelliteScenes } from '../api/client'

const PHILIPPINES_BBOX = [116.9, 4.5, 126.6, 21.2]
const collection = ref('sentinel-1-grd')
const startDate = ref('')
const endDate = ref('')
const maxCloudCover = ref(40)
const features = ref([])
const message = ref('')
const isSearching = ref(false)

function formatDate(value) {
  if (!value) return 'Not supplied'
  return new Intl.DateTimeFormat('en-PH', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'UTC',
  }).format(new Date(value)) + ' UTC'
}

function cloudCover(scene) {
  const value = scene.properties?.['eo:cloud_cover']
  return value == null ? 'Not applicable' : `${Number(value).toFixed(1)}%`
}

function formatBounds(bounds) {
  if (!Array.isArray(bounds)) return 'Not supplied'
  return bounds.slice(0, 4).map((coordinate) => Number(coordinate).toFixed(2)).join(', ')
}

async function searchScenes() {
  if (startDate.value > endDate.value) {
    message.value = 'The start date must be earlier than or equal to the end date.'
    return
  }

  isSearching.value = true
  message.value = ''
  features.value = []
  try {
    const search = await searchSatelliteScenes({
      collection: collection.value,
      bbox: PHILIPPINES_BBOX,
      start_datetime: `${startDate.value}T00:00:00Z`,
      end_datetime: `${endDate.value}T23:59:59Z`,
      limit: 100,
      ...(collection.value === 'sentinel-2-l2a' ? { max_cloud_cover: maxCloudCover.value } : {}),
    })
    features.value = search.features ?? []
    message.value = features.value.length
      ? ''
      : 'No scenes matched these dates and filters. Try a wider date range.'
  } catch (error) {
    message.value = error instanceof Error ? error.message : 'The satellite catalogue is unavailable.'
  } finally {
    isSearching.value = false
  }
}
</script>
