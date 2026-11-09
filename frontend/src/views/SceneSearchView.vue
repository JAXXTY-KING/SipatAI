<template>
  <div class="page-view">
    <header class="page-heading">
      <div>
        <p class="eyebrow">COPERNICUS DATA SPACE</p>
        <h1>Satellite scenes</h1>
        <p class="page-description">Find real Sentinel acquisitions for a selected Philippine area and event window. Search results are imagery, not flood detections.</p>
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
      <label>
        West longitude
        <input v-model.number="bbox.west" type="number" min="116.9" max="126.6" step="any" required />
      </label>
      <label>
        South latitude
        <input v-model.number="bbox.south" type="number" min="4.5" max="21.2" step="any" required />
      </label>
      <label>
        East longitude
        <input v-model.number="bbox.east" type="number" min="116.9" max="126.6" step="any" required />
      </label>
      <label>
        North latitude
        <input v-model.number="bbox.north" type="number" min="4.5" max="21.2" step="any" required />
      </label>
      <label v-if="collection === 'sentinel-2-l2a'">
        Maximum cloud cover (%)
        <input v-model.number="maxCloudCover" type="number" min="0" max="100" step="1" />
      </label>
      <div class="scene-search-actions">
        <button class="button button-primary" type="submit" :disabled="isSearching || !validSearch">
          {{ isSearching ? 'Searching…' : 'Search scenes' }}
        </button>
        <button class="button" type="button" @click="resetSearchArea">Use full Philippines</button>
      </div>
    </form>

    <p class="scene-source-note">
      Catalogue: Copernicus Data Space STAC · WGS 84 coordinates · Sentinel-1 radar or Sentinel-2 optical.
      Product download to OBS requires backend-only Copernicus and OBS credentials. Preprocessing and flood inference are not performed by this search.
    </p>
    <p v-if="message" class="connection-note" role="status">{{ message }}</p>

    <section v-if="features.length" class="data-section scene-results" aria-label="Satellite scenes">
      <div class="section-heading">
        <div><p class="eyebrow">COPERNICUS DATA SPACE</p><h2>{{ features.length }} scenes (up to 100)</h2></div>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Product</th><th>Acquired</th><th>Cloud cover</th><th>Footprint (W,S,E,N)</th><th>Archive</th></tr></thead>
          <tbody>
            <tr v-for="scene in features" :key="scene.id">
              <td data-label="Product">
                <strong>{{ scene.id }}</strong>
                <span class="scene-product-meta">{{ scene.properties?.platform || 'Platform not supplied' }} · {{ scene.properties?.['sar:instrument_mode'] || scene.properties?.['s2:product_type'] || collection }}</span>
              </td>
              <td data-label="Acquired">{{ formatDate(scene.properties?.datetime) }}</td>
              <td data-label="Cloud cover">{{ cloudCover(scene) }}</td>
              <td data-label="Footprint">{{ formatBounds(scene.bbox) }}</td>
              <td data-label="Archive">
                <button class="button scene-download-button" type="button" :disabled="downloadingScene === scene.id" @click="archiveScene(scene)">
                  {{ downloadingScene === scene.id ? 'Archiving…' : 'Copy to OBS' }}
                </button>
                <span v-if="downloadMessages[scene.id]" class="scene-download-status" role="status">{{ downloadMessages[scene.id] }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { downloadSatelliteScene, searchSatelliteScenes } from '../api/client'

const PHILIPPINES_BBOX = [116.9, 4.5, 126.6, 21.2]
const collection = ref('sentinel-1-grd')
const endDate = ref(toDateInput(new Date()))
const initialStart = new Date()
initialStart.setDate(initialStart.getDate() - 14)
const startDate = ref(toDateInput(initialStart))
const maxCloudCover = ref(40)
const bbox = ref({
  west: PHILIPPINES_BBOX[0],
  south: PHILIPPINES_BBOX[1],
  east: PHILIPPINES_BBOX[2],
  north: PHILIPPINES_BBOX[3],
})
const features = ref([])
const message = ref('')
const isSearching = ref(false)
const downloadingScene = ref('')
const downloadMessages = ref({})
const validSearch = computed(() => (
  startDate.value
  && endDate.value
  && startDate.value <= endDate.value
  && bbox.value.west >= PHILIPPINES_BBOX[0]
  && bbox.value.south >= PHILIPPINES_BBOX[1]
  && bbox.value.east <= PHILIPPINES_BBOX[2]
  && bbox.value.north <= PHILIPPINES_BBOX[3]
  && bbox.value.west < bbox.value.east
  && bbox.value.south < bbox.value.north
))

function toDateInput(date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function resetSearchArea() {
  bbox.value = {
    west: PHILIPPINES_BBOX[0],
    south: PHILIPPINES_BBOX[1],
    east: PHILIPPINES_BBOX[2],
    north: PHILIPPINES_BBOX[3],
  }
}

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
  downloadMessages.value = {}
  try {
    const search = await searchSatelliteScenes({
      collection: collection.value,
      bbox: [bbox.value.west, bbox.value.south, bbox.value.east, bbox.value.north],
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

async function archiveScene(scene) {
  downloadingScene.value = scene.id
  downloadMessages.value = { ...downloadMessages.value, [scene.id]: '' }
  try {
    const result = await downloadSatelliteScene({
      collection: collection.value,
      productName: scene.id,
    })
    downloadMessages.value = { ...downloadMessages.value, [scene.id]: `Copied to OBS: ${result.object_key}` }
  } catch (error) {
    downloadMessages.value = {
      ...downloadMessages.value,
      [scene.id]: error instanceof Error ? error.message : 'Scene could not be copied to OBS.',
    }
  } finally {
    downloadingScene.value = ''
  }
}
</script>
