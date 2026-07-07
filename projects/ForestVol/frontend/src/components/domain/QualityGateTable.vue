<template>
  <el-table v-if="gates.length" :data="gates" class="quality-table">
    <el-table-column label="Estado" width="130">
      <template #default="{ row }">
        <el-tag :type="tagType(row.status)" effect="light">{{ gateLabels[row.status] || row.status || "--" }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column prop="name" label="Validacion" min-width="180">
      <template #default="{ row }">{{ row.name || row.gate || "--" }}</template>
    </el-table-column>
    <el-table-column label="Metrica" min-width="160">
      <template #default="{ row }">{{ row.metric || "--" }}: {{ row.value ?? "--" }}</template>
    </el-table-column>
    <el-table-column prop="explanation" label="Explicacion" min-width="240" />
  </el-table>
  <EmptyState v-else title="Sin validaciones" message="Las validaciones apareceran cuando existan resultados del pipeline." />
</template>

<script setup>
import EmptyState from "@/components/common/EmptyState.vue";
import { gateLabels } from "@/utils/labels";

defineProps({
  gates: { type: Array, default: () => [] },
});

function tagType(status) {
  if (["PASS", "passed"].includes(status)) return "success";
  if (["WARNING", "warning"].includes(status)) return "warning";
  if (["FAIL", "failed"].includes(status)) return "danger";
  return "info";
}
</script>
