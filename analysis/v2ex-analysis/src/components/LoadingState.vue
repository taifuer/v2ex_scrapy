<script setup lang="ts">
import { RefreshCw } from "@lucide/vue"

withDefaults(defineProps<{ label?: string; retry?: boolean }>(), {
  label: "正在加载数据",
  retry: false,
})
const emit = defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="loading">
    <div class="loading-card">
      <span class="loading-spinner" aria-hidden="true"></span>
      <strong>{{ label }}</strong>
      <button v-if="retry" class="command icon-command" type="button" @click="emit('retry')">
        <RefreshCw :size="15" aria-hidden="true" />刷新
      </button>
    </div>
  </div>
</template>
