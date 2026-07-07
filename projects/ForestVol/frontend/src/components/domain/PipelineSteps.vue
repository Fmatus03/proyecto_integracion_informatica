<template>
  <el-steps :active="activeIndex" finish-status="success" process-status="process" align-center>
    <el-step v-for="step in steps" :key="step.code" :title="step.label" :status="stepStatus(step.code)" />
  </el-steps>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  state: { type: String, default: "" },
});

const steps = [
  { code: "VALIDATED", label: "Carga" },
  { code: "CALIBRATED", label: "Calibracion" },
  { code: "RECONSTRUCTING", label: "Reconstruccion" },
  { code: "COMPLETED", label: "Resultados" },
];

const stateIndexes = {
  VALIDATED: 0,
  CALIBRATION_PENDING: 1,
  CALIBRATED: 1,
  RECONSTRUCTION_PENDING: 2,
  RECONSTRUCTING: 2,
  POINT_CLOUD_READY: 2,
  MESH_PENDING: 2,
  COMPLETED: 3,
};

const activeIndex = computed(() => stateIndexes[props.state] ?? -1);

function stepStatus(code) {
  if (props.state === "FAILED") return "error";
  if (props.state === code) return "success";
  return undefined;
}
</script>
