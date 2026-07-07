<template>
  <section class="workflow-grid">
    <div class="left-stack">
      <el-card shadow="never">
        <template #header>Entrada RGB</template>
        <FileDropzone @change="setFiles" />
        <p class="hint">{{ fileSummary }}</p>

        <el-form label-position="top" class="control-form">
          <el-form-item label="Identificador del proceso">
            <el-input v-model="sessionId" placeholder="Se crea al cargar imagenes" clearable />
          </el-form-item>
          <el-form-item label="Escala manual px/cm">
            <el-input-number v-model="manualScale" :min="0" :precision="2" :step="0.1" placeholder="Opcional" />
          </el-form-item>
        </el-form>

        <el-button class="wide-action" type="primary" size="large" :loading="busy" :disabled="!hasEnoughFiles" @click="runFullPipeline">
          Procesar volumen
        </el-button>
      </el-card>

      <el-card shadow="never">
        <template #header>Controles avanzados</template>
        <div class="button-grid">
          <el-button :icon="Upload" @click="upload">Solo cargar</el-button>
          <el-button type="primary" plain :icon="Aim" @click="calibrate">Solo calibrar</el-button>
          <el-button type="primary" :icon="Cpu" @click="reconstruct">Solo reconstruir</el-button>
          <el-button :icon="Refresh" @click="loadResults()">Consultar</el-button>
          <el-button :icon="Timer" @click="startPolling">Seguimiento</el-button>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header>Registro</template>
        <ProcessLog :items="logItems" />
      </el-card>
    </div>

    <div class="right-stack">
      <MetricGrid :result="result" />
      <el-card shadow="never">
        <template #header>Pipeline</template>
        <PipelineSteps :state="result?.pipeline_state" />
      </el-card>
      <el-card shadow="never">
        <template #header>Resumen tecnico</template>
        <ResultSummary v-if="result" :result="result" />
        <EmptyState v-else title="Sin proceso iniciado" message="Selecciona imagenes y ejecuta el flujo completo o usa un identificador existente." />
      </el-card>
      <el-card shadow="never">
        <template #header>Validaciones de calidad</template>
        <QualityGateTable :gates="result?.quality_gates || []" />
      </el-card>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";
import { Aim, Cpu, Refresh, Timer, Upload } from "@element-plus/icons-vue";
import EmptyState from "@/components/common/EmptyState.vue";
import FileDropzone from "@/components/domain/FileDropzone.vue";
import MetricGrid from "@/components/domain/MetricGrid.vue";
import PipelineSteps from "@/components/domain/PipelineSteps.vue";
import ProcessLog from "@/components/domain/ProcessLog.vue";
import QualityGateTable from "@/components/domain/QualityGateTable.vue";
import ResultSummary from "@/components/domain/ResultSummary.vue";
import { usePipeline } from "@/composables/usePipeline";

const {
  selectedFiles,
  validFiles,
  hasEnoughFiles,
  sessionId,
  manualScale,
  result,
  busy,
  logItems,
  setFiles,
  upload,
  calibrate,
  reconstruct,
  loadResults,
  runFullPipeline,
  startPolling,
} = usePipeline();

const fileSummary = computed(() => {
  const total = selectedFiles.value.length;
  if (!total) return "Sin imagenes seleccionadas.";
  return `${validFiles.value.length}/${total} imagenes JPG/PNG listas.`;
});
</script>
