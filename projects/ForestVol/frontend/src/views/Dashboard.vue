<template>
  <section class="page-grid">
    <el-card class="hero-panel" shadow="never">
      <div class="hero-copy">
        <p class="eyebrow">Flujo oficial</p>
        <h2>Volumetria PDI desde imagenes RGB</h2>
        <p>Gestiona carga, calibracion espacial, reconstruccion NodeODM, validaciones de calidad y exportaciones desde una consola unica.</p>
        <div class="hero-actions">
          <el-button type="primary" :icon="UploadFilled" @click="$router.push('/upload')">Nuevo proceso</el-button>
          <el-button :icon="Search" @click="$router.push('/process')">Consultar proceso</el-button>
        </div>
      </div>
    </el-card>

    <div class="dashboard-grid">
      <el-card shadow="never">
        <template #header>Estado del backend</template>
        <el-skeleton v-if="loading" :rows="3" animated />
        <el-alert v-else-if="healthError" type="error" :closable="false" title="Backend sin respuesta" :description="healthError" />
        <div v-else class="health-block">
          <el-result icon="success" title="Servicio disponible" sub-title="FastAPI respondio correctamente." />
          <p><strong>Version:</strong> {{ health.version }}</p>
          <p><strong>NodeODM:</strong> {{ health.nodeodm_reachable ? "alcanzable" : "no disponible" }}</p>
        </div>
      </el-card>

      <el-card shadow="never">
        <template #header>Procesos recientes</template>
        <el-table v-if="sessionStore.recentSessions.length" :data="sessionStore.recentSessions">
          <el-table-column prop="sessionId" label="Sesion" min-width="210" />
          <el-table-column label="Estado" width="150">
            <template #default="{ row }"><StatusBadge :state="row.state" /></template>
          </el-table-column>
          <el-table-column label="Accion" width="130">
            <template #default="{ row }">
              <el-button text type="primary" @click="$router.push(`/process/${row.sessionId}`)">Abrir</el-button>
            </template>
          </el-table-column>
        </el-table>
        <EmptyState v-else title="Sin procesos recientes" message="Carga imagenes o consulta una sesion existente para comenzar." />
      </el-card>
    </div>
  </section>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { Search, UploadFilled } from "@element-plus/icons-vue";
import EmptyState from "@/components/common/EmptyState.vue";
import StatusBadge from "@/components/common/StatusBadge.vue";
import { checkHealth } from "@/services/processService";
import { sessionStore } from "@/stores/sessionStore";

const loading = ref(true);
const health = ref({});
const healthError = ref("");

onMounted(async () => {
  try {
    health.value = await checkHealth();
  } catch (error) {
    healthError.value = error.message;
  } finally {
    loading.value = false;
  }
});
</script>
