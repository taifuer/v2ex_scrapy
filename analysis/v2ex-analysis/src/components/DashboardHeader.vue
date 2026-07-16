<script setup lang="ts">
import {
  ChartNoAxesCombined,
  HeartHandshake,
  MessageSquareText,
  Telescope,
  Users,
} from "@lucide/vue"

type TabItem = { id: string; label: string }

defineProps<{
  activeTab: string
  tabs: TabItem[]
  dataScope: string
}>()

const emit = defineEmits<{ select: [id: string] }>()
const tabIcons: Record<string, any> = {
  overview: ChartNoAxesCombined,
  content: MessageSquareText,
  community: Users,
  engagement: HeartHandshake,
  observations: Telescope,
}
</script>

<template>
  <header class="dashboard-header">
    <div class="dashboard-header-inner">
      <div class="dashboard-brand">
        <a class="brand-link" href="./" aria-label="刷新 V2EX 社区看板首页">
          <span class="brand-mark">V2</span>
          <span><strong>V2EX 社区看板</strong><small class="data-scope">{{ dataScope }}</small></span>
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
          <component :is="tabIcons[tab.id]" :size="16" :stroke-width="1.8" aria-hidden="true" />
          <span>{{ tab.label }}</span>
        </button>
      </nav>
    </div>
  </header>
</template>
