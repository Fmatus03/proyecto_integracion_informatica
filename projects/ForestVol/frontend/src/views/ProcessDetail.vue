<template>
  <section class="page-grid">
    <el-card shadow="never">
      <template #header>Consulta de proceso</template>
      <el-form class="lookup-form" @submit.prevent>
        <el-input v-model="sessionId" placeholder="Identificador del proceso" clearable />
        <el-button type="primary" :icon="Search" :loading="loading" @click="load">Consultar</el-button>
        <el-button :icon="Timer" :disabled="!result" @click="startPolling">Seguimiento</el-button>
      </el-form>
    </el-card>

    <MetricGrid :result="result" />

    <div class="detail-grid">
      <el-card shadow="never">
        <template #header>Pipeline</template>
        <PipelineSteps :state="result?.pipeline_state" />
        <el-progress v-if="result?.progress_percentage !== null && result?.progress_percentage !== undefined" :percentage="result.progress_percentage" />
      </el-card>

      <el-card shadow="never">
        <template #header>Exportaciones</template>
        <div class="button-grid">
          <el-button :disabled="!result" :icon="Document" @click="openExport('json')">Reporte JSON</el-button>
          <el-button :disabled="!result" :icon="Tickets" @click="openExport('csv')">Reporte CSV</el-button>
          <el-button :disabled="!hasModel" type="primary" plain :icon="Box" @click="$router.push(`/visualization/${sessionId}`)">Ver modelo</el-button>
        </div>
      </el-card>
    </div>

    <el-card shadow="never">
      <template #header>Resumen tecnico</template>
      <ResultSummary v-if="result" :result="result" />
      <EmptyState v-else title="Proceso no cargado" message="Ingresa un identificador para consultar el backend." />
    </el-card>

    <el-card shadow="never">
      <template #header>Validaciones de calidad</template>
      <QualityGateTable :gates="result?.quality_gates || []" />
    </el-card>

    <el-card shadow="never">
      <template #header>Diagnostico</template>
      <ul v-if="result?.diagnostic?.length" class="diagnostic-list">
        <li v-for="item in result.diagnostic" :key="item">{{ item }}</li>
      </ul>
      <EmptyState v-else title="Sin diagnostico" message="No hay advertencias registradas para esta sesion." />
    </el-card>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { ElMessage } from "element-plus";
import { Box, Document, Search, Tickets, Timer } from "@element-plus/icons-vue";
import EmptyState from "@/components/common/EmptyState.vue";
import MetricGrid from "@/components/domain/MetricGrid.vue";
import PipelineSteps from "@/components/domain/PipelineSteps.vue";
import QualityGateTable from "@/components/domain/QualityGateTable.vue";
import ResultSummary from "@/components/domain/ResultSummary.vue";
import { exportUrl, getResults } from "@/services/processService";
import { rememberSession } from "@/stores/sessionStore";
import { canPoll, isTerminalState } from "@/utils/labels";

const route = useRoute();
const sessionId = ref(route.params.sessionId || "");
const result = ref(null);
const loading = ref(false);
let timer = null;

const hasModel = computed(() => Boolean(result.value?.mesh_glb_path || result.value?.mesh_ply_path));

async function load() {
  if (!sessionId.value) {
    ElMessage.warning("Ingresa un identificador de proceso.");
    return;
  }
  loading.value = true;
  try {
    result.value = await getResults(sessionId.value);
    rememberSession(sessionId.value, result.value);
    if (canPoll(result.value.pipeline_state) && !timer) startPolling();
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

function startPolling() {
  if (!sessionId.value) return;
  stopPolling();
  timer = setInterval(async () => {
    await load();
    if (isTerminalState(result.value?.pipeline_state)) stopPolling();
  }, 3500);
  ElMessage.success("Seguimiento automatico activo.");
}

function stopPolling() {
  if (timer) clearInterval(timer);
  timer = null;
}

function openExport(format) {
  if (!sessionId.value) return;
  window.open(exportUrl(sessionId.value, format), "_blank", "noopener,noreferrer");
}

onMounted(() => {
  if (sessionId.value) load();
});
onBeforeUnmount(stopPolling);
</script>
