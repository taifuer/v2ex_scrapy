<script setup lang="ts">
withDefaults(defineProps<{
  label: string
  value: string
  note: string
  down?: boolean
  compact?: boolean
}>(), {
  down: false,
  compact: false,
})
</script>

<template>
  <article class="metric" :class="{ 'metric-compact': compact }">
    <span>{{ label }}</span>
    <strong>{{ value }}</strong>
    <em :class="{ down }">{{ note }}</em>
  </article>
</template>
