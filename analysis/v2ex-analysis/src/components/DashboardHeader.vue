<script setup lang="ts">
type TabItem = { id: string; label: string }

defineProps<{
  activeTab: string
  tabs: TabItem[]
  dataScope: string
  compactDataScope: string
  narrowDataScope: string
}>()

const emit = defineEmits<{ select: [id: string] }>()
</script>

<template>
  <header class="dashboard-header">
    <div class="dashboard-header-inner">
      <div class="dashboard-brand">
        <a class="brand-link" href="./" aria-label="刷新 V2EX 社区看板首页">
          <span class="brand-mark">V2</span>
          <span>
            <h1>V2EX 社区看板</h1>
            <small class="data-scope data-scope-full">{{ dataScope }}</small>
            <small class="data-scope-compact">{{ compactDataScope }}</small>
            <small class="data-scope-narrow">{{ narrowDataScope }}</small>
          </span>
        </a>
      </div>
      <nav class="tab-list" aria-label="分析视图">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          :class="{ active: activeTab === tab.id }"
          :aria-current="activeTab === tab.id ? 'page' : undefined"
          @click="emit('select', tab.id)"
        >
          <span>{{ tab.label }}</span>
        </button>
      </nav>
      <div class="dashboard-tools"><slot name="tools" /></div>
    </div>
  </header>
</template>
