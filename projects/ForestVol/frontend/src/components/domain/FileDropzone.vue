<template>
  <label class="dropzone" :class="{ active: isDragging }" @dragover.prevent="isDragging = true" @dragleave="isDragging = false" @drop.prevent="onDrop">
    <input type="file" multiple accept=".jpg,.jpeg,.png,image/jpeg,image/png" @change="onInput" />
    <el-icon><UploadFilled /></el-icon>
    <strong>Seleccionar o soltar imagenes</strong>
    <span>JPG/PNG, minimo 10 fotografias para iniciar el proceso</span>
  </label>
</template>

<script setup>
import { ref } from "vue";
import { UploadFilled } from "@element-plus/icons-vue";

const emit = defineEmits(["change"]);
const isDragging = ref(false);

function emitFiles(files) {
  emit("change", Array.from(files || []));
}

function onInput(event) {
  emitFiles(event.target.files);
}

function onDrop(event) {
  isDragging.value = false;
  emitFiles(event.dataTransfer.files);
}
</script>
