<template>
  <el-tag :type="type" effect="light">{{ label }}</el-tag>
</template>

<script setup>
import { computed } from "vue";
import { stateLabel } from "@/utils/labels";

const props = defineProps({
  state: { type: String, default: "" },
});

const label = computed(() => stateLabel(props.state));
const type = computed(() => {
  if (props.state === "COMPLETED") return "success";
  if (props.state === "FAILED") return "danger";
  if (["RECONSTRUCTING", "MESH_PENDING", "POINT_CLOUD_READY"].includes(props.state)) return "warning";
  return "info";
});
</script>
