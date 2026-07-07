<template>
  <div class="summary-grid">
    <div>
      <span class="label">Caja delimitadora</span>
      <p>{{ boundingBox }}</p>
    </div>
    <div>
      <span class="label">Metodo</span>
      <p>{{ result?.volume_method || "--" }}</p>
    </div>
    <div>
      <span class="label">Error vs referencia</span>
      <p>{{ formatNumber(result?.error_percentage, "%") }}</p>
    </div>
    <div>
      <span class="label">Malla</span>
      <p>{{ meshState }}</p>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { formatNumber } from "@/utils/labels";

const props = defineProps({
  result: { type: Object, default: null },
});

const boundingBox = computed(() => {
  const box = props.result?.bounding_box_m;
  if (!box) return "--";
  const labels = { length_m: "largo", width_m: "ancho", height_m: "alto" };
  return Object.entries(box)
    .map(([key, value]) => `${labels[key] || key}: ${formatNumber(value, " m")}`)
    .join(" / ");
});

const meshState = computed(() => {
  if (!props.result?.mesh_glb_path && !props.result?.mesh_ply_path) return "--";
  if (props.result.mesh_watertight === true) return "Cerrada";
  if (props.result.mesh_repair_applied) return "Reparada";
  return "Generada";
});
</script>
