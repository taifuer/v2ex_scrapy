<script setup lang="ts">
defineProps<{ observations: any }>()
function displayIndex(index: string | number) { return Number(index) + 1 }
</script>

<template>
  <section class="view-section observations-view">
    <div class="observation-brief">
      <div class="observation-kicker">离线数据解读 · {{ observations.metadata.analysis_start }} 至 {{ observations.metadata.analysis_end }}</div>
      <h2>{{ observations.headline.title }}</h2>
      <p>{{ observations.headline.summary }}</p>
      <div class="observation-headline-metrics">
        <div v-for="metric in observations.headline.metrics" :key="metric.label">
          <strong>{{ metric.value }}</strong><span>{{ metric.label }}</span>
        </div>
      </div>
    </div>

    <div class="observation-grid">
      <article v-for="(item, index) in observations.observations" :key="item.id" class="observation-item">
        <header>
          <div class="observation-index">{{ String(displayIndex(index)).padStart(2, "0") }}</div>
          <div>
            <div class="observation-meta"><span>{{ item.category }}</span><span>{{ item.evidence }}</span><span>可信度 {{ item.confidence }}</span></div>
            <h3>{{ item.title }}</h3>
          </div>
        </header>
        <p class="observation-summary">{{ item.summary }}</p>
        <p class="observation-interpretation">{{ item.interpretation }}</p>
        <div class="observation-stats">
          <div v-for="stat in item.stats" :key="stat.label"><strong>{{ stat.value }}</strong><span>{{ stat.label }}</span></div>
        </div>
        <footer>
          <div class="observation-links">
            <a v-for="link in item.links" :key="link.href" :href="link.href">{{ link.label }}</a>
            <a v-if="item.source" :href="item.source.url" target="_blank" rel="noreferrer">{{ item.source.action || "查看来源" }}</a>
          </div>
          <span v-if="item.source" class="observation-source">{{ item.source.date }} · {{ item.source.label }}</span>
        </footer>
      </article>
    </div>

    <section class="observation-method">
      <header>
        <div><span>方法与边界</span><h3>解读口径</h3></div>
        <p>离线生成 · 固定窗口 · 可追溯证据</p>
      </header>
      <div class="observation-method-grid">
        <div v-for="(note, index) in observations.notes" :key="note">
          <span>{{ String(displayIndex(index)).padStart(2, "0") }}</span><p>{{ note }}</p>
        </div>
      </div>
      <footer>生成方式：{{ observations.metadata.generated_by }} · 核心窗口 {{ observations.metadata.analysis_start }} 至 {{ observations.metadata.analysis_end }} · 前后五年比较</footer>
    </section>
  </section>
</template>
