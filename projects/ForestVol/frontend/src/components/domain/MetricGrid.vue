<template>
  <div class="metric-grid">
    <article class="metric-tile">
      <span>Estado</span>
      <strong><StatusBadge :state="result?.pipeline_state" /></strong>
    </article>
    <article class="metric-tile">
      <span>Volumen estimado</span>
      <strong>{{ formatNumber(result?.volume_m3, " m3") }}</strong>
    </article>
    <article class="metric-tile">
      <span>Confianza</span>
      <strong>{{ confidence }}</strong>
    </article>
    <article class="metric-tile">
      <span>Modelo</span>
      <strong>{{ result?.mesh_glb_path || result?.mesh_ply_path ? "Disponible" : "--" }}</strong>
    </article>
  </div>
</template>

<script setup>
import { computed } from "vue";
import StatusBadge from "@/components/common/StatusBadge.vue";
import { confidenceLabels, formatNumber } from "@/utils/labels";

const props = defineProps({
  result: { type: Object, default: null },
});

const confidence = computed(() => {
  if (!props.result || props.result.confidence_score === null || props.result.confidence_score === undefined) return "--";
  const label = confidenceLabels[String(props.result.confidence_level || "").toUpperCase()] || props.result.confidence_level || "";
  return `${formatNumber(props.result.confidence_score)} ${label}`.trim();
});
</script>
