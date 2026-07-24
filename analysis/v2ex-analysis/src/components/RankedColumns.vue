<script setup lang="ts">
import type { RankedColumn, RankedItem } from "../types/analytics"

defineProps<{ columns: RankedColumn[] }>()
const emit = defineEmits<{ select: [item: RankedItem, column: RankedColumn] }>()
</script>

<template>
  <div class="ranked-columns" :class="`ranked-columns-${columns.length}`">
    <section v-for="column in columns" :key="column.key" class="ranked-column">
      <h3>{{ column.title }}</h3>
      <div class="ranked-item-grid">
        <template v-for="(item, index) in column.items" :key="item.key">
          <a
            v-if="item.href"
            class="ranked-item"
            :class="{ active: item.active }"
            :href="item.href"
            target="_blank"
            rel="noreferrer"
          >
            <span>{{ index + 1 }}</span><strong>{{ item.label }}</strong><em>{{ item.value }}</em>
          </a>
          <button
            v-else
            class="ranked-item"
            :class="{ active: item.active }"
            @click="emit('select', item, column)"
          >
            <span>{{ index + 1 }}</span><strong>{{ item.label }}</strong><em>{{ item.value }}</em>
          </button>
        </template>
      </div>
    </section>
  </div>
</template>
