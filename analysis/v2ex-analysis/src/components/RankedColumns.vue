<script setup lang="ts">
import { ref } from "vue"
import { ChevronDown } from "@lucide/vue"
import type { RankedColumn, RankedItem } from "../types/analytics"

defineProps<{ columns: RankedColumn[] }>()
const emit = defineEmits<{ select: [item: RankedItem, column: RankedColumn] }>()
const expandedColumns = ref<Set<string>>(new Set())

function toggleColumn(key: string) {
  const next = new Set(expandedColumns.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expandedColumns.value = next
}
</script>

<template>
  <div class="ranked-columns" :class="`ranked-columns-${columns.length}`">
    <section v-for="column in columns" :key="column.key" class="ranked-column" :class="{ expanded: expandedColumns.has(column.key) }">
      <h3>{{ column.title }}</h3>
      <div class="ranked-item-grid">
        <template v-for="(item, index) in column.items" :key="item.key">
          <a
            v-if="item.href"
            class="ranked-item"
            :class="{ active: item.active, 'mobile-ranked-overflow': index >= 10 }"
            :href="item.href"
            target="_blank"
            rel="noreferrer"
          >
            <span>{{ index + 1 }}</span><strong>{{ item.label }}</strong><em>{{ item.value }}</em>
          </a>
          <button
            v-else
            class="ranked-item"
            :class="{ active: item.active, 'mobile-ranked-overflow': index >= 10 }"
            @click="emit('select', item, column)"
          >
            <span>{{ index + 1 }}</span><strong>{{ item.label }}</strong><em>{{ item.value }}</em>
          </button>
        </template>
      </div>
      <button
        v-if="column.items.length > 10"
        type="button"
        class="ranked-column-toggle"
        :aria-expanded="expandedColumns.has(column.key)"
        @click="toggleColumn(column.key)"
      >
        {{ expandedColumns.has(column.key) ? "收起至 10 项" : `展开全部 ${column.items.length} 项` }}
        <ChevronDown :size="15" :class="{ expanded: expandedColumns.has(column.key) }" aria-hidden="true" />
      </button>
    </section>
  </div>
</template>
