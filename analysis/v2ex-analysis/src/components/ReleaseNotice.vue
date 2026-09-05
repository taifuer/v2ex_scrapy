<script setup lang="ts">
import { RefreshCw, X } from "@lucide/vue"
import { releaseUpdated, resourceLoadFailed } from "../services/releaseState"

function reload() { window.location.reload() }
function dismiss() { releaseUpdated.value = false; resourceLoadFailed.value = false }
</script>

<template>
  <aside v-if="releaseUpdated || resourceLoadFailed" class="release-notice" role="status" aria-live="polite">
    <p>{{ releaseUpdated ? '站点已更新，刷新页面后可继续查看。当前筛选会保留。' : '页面资源加载失败，请检查网络后重新加载。' }}</p>
    <button class="subtle-command" @click="reload"><RefreshCw :size="15" aria-hidden="true" />{{ releaseUpdated ? '更新页面' : '重新加载' }}</button>
    <button class="release-notice-close" aria-label="关闭更新提示" title="关闭更新提示" @click="dismiss"><X :size="16" aria-hidden="true" /></button>
  </aside>
</template>

<style scoped>
.release-notice { display: flex; align-items: center; gap: 12px; position: sticky; top: 8px; z-index: 45; margin: 12px 0; padding: 12px 16px; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; box-shadow: 0 4px 14px #17212f14; }
.release-notice p { flex: 1; min-width: 0; margin: 0; color: #344054; font-size: 13px; line-height: 1.6; }
.release-notice .subtle-command { display: inline-flex; align-items: center; gap: 6px; flex: 0 0 auto; min-height: 36px; }
.release-notice-close { display: grid; place-items: center; flex: 0 0 32px; width: 32px; height: 32px; padding: 0; border: 0; background: transparent; color: #475467; cursor: pointer; }
@media (max-width: 680px) {
  .release-notice { flex-wrap: wrap; gap: 8px; padding: 12px; }
  .release-notice p { flex-basis: calc(100% - 48px); }
  .release-notice .subtle-command { order: 3; }
}
</style>
