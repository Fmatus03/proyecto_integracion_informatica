<template>
  <section class="page-grid">
    <el-card shadow="never">
      <template #header>Modelo 3D</template>
      <el-form class="lookup-form" @submit.prevent>
        <el-input v-model="sessionId" placeholder="Identificador del proceso" clearable />
        <el-button type="primary" :icon="Search" :loading="loading" @click="load">Cargar modelo</el-button>
        <el-button :disabled="!modelAvailable" :icon="Download" @click="downloadModel">Descargar</el-button>
      </el-form>
    </el-card>

    <MetricGrid v-if="result" :result="result" />

    <ModelViewer :url="viewerUrl" :file-name="fileName" @error="onViewerError" />

    <el-card shadow="never">
      <template #header>Informacion del resultado</template>
      <ResultSummary v-if="result" :result="result" />
      <EmptyState v-else title="Sin modelo cargado" message="Consulta una sesion completada para visualizar o descargar el artefacto 3D." />
    </el-card>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import { Download, Search } from "@element-plus/icons-vue";
import EmptyState from "@/components/common/EmptyState.vue";
import MetricGrid from "@/components/domain/MetricGrid.vue";
import ModelViewer from "@/components/domain/ModelViewer.vue";
import ResultSummary from "@/components/domain/ResultSummary.vue";
import { getResults, modelUrl } from "@/services/processService";
import { rememberSession } from "@/stores/sessionStore";

const route = useRoute();
const sessionId = ref(route.params.sessionId || "");
const result = ref(null);
const loading = ref(false);

const modelAvailable = computed(() => Boolean(result.value?.mesh_glb_path || result.value?.mesh_ply_path));
const viewerUrl = computed(() => (sessionId.value && modelAvailable.value ? modelUrl(sessionId.value) : ""));
const fileName = computed(() => {
  const path = result.value?.mesh_glb_path || result.value?.mesh_ply_path || "";
  return path.split(/[\\/]/).pop();
});

async function load() {
  if (!sessionId.value) {
    ElMessage.warning("Ingresa un identificador de proceso.");
    return;
  }
  loading.value = true;
  try {
    result.value = await getResults(sessionId.value);
    rememberSession(sessionId.value, result.value);
    if (!modelAvailable.value) ElMessage.warning("La sesion aun no tiene modelo 3D disponible.");
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

function downloadModel() {
  window.open(modelUrl(sessionId.value), "_blank", "noopener,noreferrer");
}

function onViewerError(error) {
  ElMessage.error(`No se pudo cargar el modelo: ${error.message}`);
}

onMounted(() => {
  if (sessionId.value) load();
});
</script>
