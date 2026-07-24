<script setup lang="ts">
defineProps<{ items: Array<{ id: string; label: string }> }>()
</script>

<template>
  <nav class="view-section-nav" aria-label="当前视图区域">
    <span>快速定位</span>
    <a v-for="item in items" :key="item.id" :href="`#${item.id}`">{{ item.label }}</a>
  </nav>
</template>
