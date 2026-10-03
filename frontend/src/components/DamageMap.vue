<template>
  <section class="map-frame" aria-label="Flood damage map">
    <div v-if="mapToken" ref="mapElement" class="map-canvas"></div>
    <div v-if="!mapToken || mapMessage" class="map-message" role="status">
      <strong>{{ mapToken ? 'Assessment unavailable' : 'Map service not configured' }}</strong>
      <span>{{ mapToken ? mapMessage : 'A restricted public Mapbox token is required to display map tiles.' }}</span>
    </div>
    <SeverityLegend v-if="mapToken && !mapMessage" class="map-legend" />
  </section>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import mapboxgl from 'mapbox-gl'
import { fetchDamageMap } from '../api/client'
import { severityColors } from '../map/severity'
import SeverityLegend from './SeverityLegend.vue'

const mapToken = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN
const mapElement = ref(null)
const mapMessage = ref('')
let map
let resizeObserver

onMounted(async () => {
  if (!mapToken || !mapElement.value) return

  mapboxgl.accessToken = mapToken
  map = new mapboxgl.Map({
    container: mapElement.value,
    style: 'mapbox://styles/mapbox/light-v11',
    center: [121.774, 12.8797],
    zoom: 5,
    attributionControl: true,
  })
  map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'top-right')
  async function loadAssessmentLayer() {
    try {
      const collection = await fetchDamageMap()
      if (!collection.features?.length) {
        mapMessage.value = 'No completed assessment is available in the spatial database.'
        return
      }

      const addAssessmentLayer = () => {
        if (!map || !map.isStyleLoaded()) return
        map.addSource('damage-assessment', { type: 'geojson', data: collection })
        map.addLayer({
          id: 'damage-polygons',
          type: 'fill',
          source: 'damage-assessment',
          paint: {
            'fill-color': [
              'match', ['get', 'severity'],
              'Severe', severityColors.Severe,
              'Moderate', severityColors.Moderate,
              'Light', severityColors.Light,
              '#6b7280',
            ],
            'fill-opacity': 0.56,
            'fill-outline-color': '#ffffff',
          },
        })
        const bounds = new mapboxgl.LngLatBounds()
        for (const feature of collection.features) {
          const polygons = feature.geometry.type === 'Polygon'
            ? [feature.geometry.coordinates]
            : feature.geometry.coordinates
          for (const polygon of polygons) {
            for (const ring of polygon) {
              for (const coordinate of ring) bounds.extend(coordinate)
            }
          }
        }
        if (!bounds.isEmpty()) map.fitBounds(bounds, { padding: 72, maxZoom: 10, duration: 0 })
      }

      if (map?.isStyleLoaded()) addAssessmentLayer()
      else map?.once('load', addAssessmentLayer)
    } catch (error) {
      mapMessage.value = error instanceof Error
        ? error.message
        : 'Assessment data is unavailable. Check the database and API configuration.'
    }
  }

  void loadAssessmentLayer()

  resizeObserver = new ResizeObserver(() => map?.resize())
  resizeObserver.observe(mapElement.value)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  map?.remove()
  map = undefined
})
</script>
