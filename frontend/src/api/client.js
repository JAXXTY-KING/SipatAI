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

export async function downloadAssessmentReport() {
  const response = await request('/api/v1/reports', {
    method: 'POST',
  })
  return response.blob()
}
