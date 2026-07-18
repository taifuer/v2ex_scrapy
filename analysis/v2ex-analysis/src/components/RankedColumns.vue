<script setup lang="ts">
type RankedItem = {
  key: string | number
  label: string
  value: string
  href?: string
  action?: string
  active?: boolean
}

type RankedColumn = {
  key: string
  title: string
  items: RankedItem[]
}

defineProps<{ columns: RankedColumn[] }>()
const emit = defineEmits<{ select: [item: RankedItem, column: RankedColumn] }>()
</script>

<template>
  <div class="ranked-columns">
    <section v-for="column in columns" :key="column.key" class="ranked-column">
      <h3>{{ column.title }}</h3>
      <div class="ranked-item-grid">
        <a
          v-for="(item, index) in column.items"
          v-if="column.items.some((item) => item.href)"
          :key="item.key"
          class="ranked-item"
          :class="{ active: item.active }"
          :href="item.href"
          target="_blank"
          rel="noreferrer"
        >
          <span>{{ index + 1 }}</span><strong>{{ item.label }}</strong><em>{{ item.value }}</em>
        </a>
        <button
          v-for="(item, index) in column.items"
          v-else
          :key="item.key"
          class="ranked-item"
          :class="{ active: item.active }"
          @click="emit('select', item, column)"
        >
          <span>{{ index + 1 }}</span><strong>{{ item.label }}</strong><em>{{ item.value }}</em>
        </button>
      </div>
    </section>
  </div>
</template>
