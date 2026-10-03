<template>
  <div class="severity-legend" aria-label="Damage severity legend">
    <span v-for="(color, severity) in severityColors" :key="severity" class="legend-item">
      <i :style="{ backgroundColor: color }" aria-hidden="true"></i>{{ severity }}
    </span>
  </div>
</template>

<script setup>
import { severityColors } from '../map/severity'
</script>
