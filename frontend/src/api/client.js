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

export async function searchSatelliteScenes(search) {
  const response = await request('/api/v1/scenes/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(search),
  })
  return response.json()
}

export async function downloadAssessmentReport() {
  const response = await request('/api/v1/reports', {
    method: 'POST',
  })
  return response.blob()
}
