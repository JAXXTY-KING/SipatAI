const apiBaseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ?? ''

async function request(path, options = {}) {
  if (!apiBaseUrl) {
    throw new Error('Set VITE_API_BASE_URL in frontend/.env.local to connect the API.')
  }

  const response = await fetch(`${apiBaseUrl}${path}`, options)
  if (!response.ok) {
    const errorBody = await response.json().catch(() => null)
    const details = Array.isArray(errorBody?.detail)
      ? errorBody.detail.map((item) => item.msg).join(' ')
      : errorBody?.detail
    throw new Error(details || `API request failed (${response.status}).`)
  }
  return response
}

export async function fetchDashboardSummary() {
  const response = await request('/api/v1/barangay/summary')
  return response.json()
}

export async function fetchDamageMap() {
  const response = await request('/api/v1/damage-map')
  return response.json()
}

export async function fetchParcelMap(bounds) {
  const parameters = new URLSearchParams({
    west: String(bounds.getWest()),
    south: String(bounds.getSouth()),
    east: String(bounds.getEast()),
    north: String(bounds.getNorth()),
  })
  const response = await request(`/api/v1/parcels/map?${parameters}`)
  return response.json()
}

export async function searchSatelliteScenes(search) {
  const response = await request('/api/v1/scenes/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(search),
  })
  return response.json()
}

export function weatherTileTemplate(layer) {
  return `${apiBaseUrl}/api/v1/weather/tiles/${layer}/{z}/{x}/{y}.png`
}

export async function fetchWeatherOverview() {
  const response = await request('/api/v1/weather/overview')
  return response.json()
}

export async function fetchFloodScreening() {
  const response = await request('/api/v1/weather/flood-screening')
  return response.json()
}

export async function fetchProvinceForecast() {
  const response = await request('/api/v1/weather/province-forecast')
  return response.json()
}

export async function fetchWindForecast() {
  const response = await request('/api/v1/weather/wind-forecast')
  return response.json()
}

export async function fetchHimawariTileFrames() {
  const response = await request('/api/v1/weather/himawari/tile-frames')
  return response.json()
}

export function himawariTileTemplate(timeCode) {
  return `${apiBaseUrl}/api/v1/weather/himawari/tiles/${timeCode}/{z}/{x}/{y}.png`
}

export async function fetchCurrentWeather(coordinates) {
  const response = await request('/api/v1/weather/current', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      latitude: coordinates.latitude,
      longitude: coordinates.longitude,
    }),
  })
  return response.json()
}

export async function searchWeatherLocations(query) {
  const parameters = new URLSearchParams({ q: query })
  const response = await request(`/api/v1/weather/locations?${parameters}`)
  return response.json()
}

export async function fetchFloodModelStatus() {
  const response = await request('/api/v1/model/status')
  return response.json()
}

export async function analyzeFloodArea({ latitude, longitude, date }) {
  const response = await request('/api/v1/model/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ latitude, longitude, date: date || null }),
  })
  return response.json()
}

export async function fetchSusceptibilityStatus() {
  const response = await request('/api/v1/model/susceptibility/status')
  return response.json()
}

export async function predictFloodProneAreas({ latitude, longitude }) {
  const response = await request('/api/v1/model/susceptibility', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ latitude, longitude }),
  })
  return response.json()
}

function viewportParameters(bounds) {
  const clamp = (value, low, high) => Math.min(high, Math.max(low, value))
  return new URLSearchParams({
    west: String(clamp(bounds.getWest(), 110, 130)),
    south: String(clamp(bounds.getSouth(), 0, 25)),
    east: String(clamp(bounds.getEast(), 110, 130)),
    north: String(clamp(bounds.getNorth(), 0, 25)),
  })
}

export async function fetchSusceptibilityChunks(bounds) {
  const response = await request(`/api/v1/model/susceptibility/chunks?${viewportParameters(bounds)}`)
  return response.json()
}

export function susceptibilityChunkUrl(chunkId) {
  return `${apiBaseUrl}/api/v1/model/susceptibility/chunk/${chunkId}.png`
}

export async function fetchScanSummary() {
  const response = await request('/api/v1/scan/summary')
  return response.json()
}

export async function fetchScanOverlays(bounds) {
  const response = await request(`/api/v1/scan/overlays?${viewportParameters(bounds)}`)
  return response.json()
}

export function scanOverlayUrl(tileId) {
  return `${apiBaseUrl}/api/v1/scan/overlay/${tileId}.png`
}

export async function fetchSatelliteAssessments() {
  const response = await request('/api/v1/model/assessments')
  return response.json()
}

export async function downloadSatelliteAssessmentReport(assessmentId) {
  const response = await request(`/api/v1/reports/satellite-assessment/${assessmentId}`, {
    method: 'POST',
  })
  return response.blob()
}

export async function downloadAssessmentReport() {
  const response = await request('/api/v1/reports', {
    method: 'POST',
  })
  return response.blob()
}

export async function downloadFloodScreeningReport() {
  const response = await request('/api/v1/reports/flood-screening', {
    method: 'POST',
  })
  return response.blob()
}

export async function downloadSatelliteScene(scene) {
  const response = await request('/api/v1/scenes/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      collection: scene.collection,
      product_name: scene.productName,
    }),
  })
  return response.json()
}
