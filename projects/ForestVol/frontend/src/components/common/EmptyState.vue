<template>
  <div class="empty-state">
    <el-icon><component :is="icon" /></el-icon>
    <strong>{{ title }}</strong>
    <p>{{ message }}</p>
  </div>
</template>

<script setup>
import { DataLine } from "@element-plus/icons-vue";

defineProps({
  title: { type: String, default: "Sin datos" },
  message: { type: String, default: "Aun no hay informacion disponible." },
  icon: { type: [Object, Function], default: DataLine },
});
</script>
