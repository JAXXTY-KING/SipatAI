<template>
  <div class="page-view map-page">
    <header class="page-heading">
      <div><p class="eyebrow">SPATIAL REVIEW</p><h1>Parcel and flood map</h1><p class="page-description">Imported farm parcels, administrative references, and the full-footprint historical flood sample</p></div>
    </header>
    <p class="parcel-map-intro">
      Explore imported parcel boundaries on the map. Click a parcel to view its source and recorded attributes.
      The optional PhilSA historical flood sample is a reference overlay, not a SipatAI assessment.
      Parcel-impact colors appear only when a completed assessment is available.
    </p>
    <section class="map-workflow" aria-label="How parcel data is used in SipatAI">
      <article>
        <span>1</span>
        <div><strong>Farm parcel boundaries</strong><p>Appear after a parcel dataset is imported. The region overlay is reference only.</p></div>
      </article>
      <article>
        <span>2</span>
        <div><strong>Satellite flood detection</strong><p>A trained model must produce flood polygons.</p></div>
      </article>
      <article>
        <span>3</span>
        <div><strong>Spatial impact assessment</strong><p>PostGIS measures overlap; parcels alone do not imply damage.</p></div>
      </article>
    </section>
    <WeatherContextPanel :coordinates="weatherCoordinates" />
    <ParcelMap @location-selected="weatherCoordinates = $event" />
  </div>
</template>

<script setup>
import ParcelMap from '../components/ParcelMap.vue'
import WeatherContextPanel from '../components/WeatherContextPanel.vue'
import { ref } from 'vue'

const weatherCoordinates = ref(null)
</script>
