<template>
  <div class="process-log">
    <div v-for="entry in items" :key="`${entry.time}-${entry.message}`" class="log-entry">
      <time>{{ new Date(entry.time).toLocaleTimeString() }}</time>
      <span>{{ entry.message }}</span>
    </div>
  </div>
</template>

<script setup>
defineProps({
  items: { type: Array, default: () => [] },
});
</script>
