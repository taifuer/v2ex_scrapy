<script setup lang="ts">
defineProps<{
  title: string
  description: string
}>()
</script>

<template>
  <header class="section-toolbar page-header">
    <div><h2>{{ title }}</h2><p>{{ description }}</p></div>
    <slot />
  </header>
</template>
