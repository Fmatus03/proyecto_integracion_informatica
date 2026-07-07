<template>
  <div class="app-shell">
    <aside class="sidebar">
      <router-link class="brand" to="/">
        <span class="brand-mark">FV</span>
        <span>
          <strong>ForestVol</strong>
          <small>Consola MVP</small>
        </span>
      </router-link>

      <nav class="nav-list">
        <router-link v-for="item in navItems" :key="item.to" :to="item.to" class="nav-link">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </router-link>
      </nav>
    </aside>

    <div class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">Procesamiento fotogrametrico</p>
          <h1>{{ route.meta.title || "ForestVol" }}</h1>
        </div>
        <el-tag :type="healthType" effect="light">{{ healthLabel }}</el-tag>
      </header>

      <main class="content">
        <slot />
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { Box, DataAnalysis, Files, UploadFilled } from "@element-plus/icons-vue";
import { checkHealth } from "@/services/processService";

const route = useRoute();
const health = ref("checking");

const navItems = [
  { to: "/", label: "Dashboard", icon: DataAnalysis },
  { to: "/upload", label: "Carga", icon: UploadFilled },
  { to: "/process", label: "Procesos", icon: Files },
  { to: "/visualization", label: "Visualizacion", icon: Box },
];

const healthLabel = computed(() => {
  if (health.value === "ok") return "Backend disponible";
  if (health.value === "error") return "Backend sin respuesta";
  return "Verificando backend";
});

const healthType = computed(() => {
  if (health.value === "ok") return "success";
  if (health.value === "error") return "danger";
  return "warning";
});

onMounted(async () => {
  try {
    await checkHealth();
    health.value = "ok";
  } catch {
    health.value = "error";
  }
});
</script>
