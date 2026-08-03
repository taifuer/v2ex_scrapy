<script setup lang="ts">
defineProps<{ year: number }>()
</script>

<template>
  <footer class="dashboard-footer">
    <div class="dashboard-footer-inner">
      <span class="dashboard-footer-item">
        © {{ year }}
        <a href="https://github.com/taifuer/v2ex_scrapy" target="_blank" rel="noreferrer">V2EX Dashboard</a>
      </span>
      <span class="dashboard-footer-separator" aria-hidden="true">·</span>
      <span class="dashboard-footer-item">非官方项目，数据来源 <a href="https://v2ex.com/" target="_blank" rel="noreferrer">V2EX</a></span>
      <span class="dashboard-footer-separator" aria-hidden="true">·</span>
      <span class="dashboard-footer-item">仅供观察参考，交流反馈请联系 <a href="mailto:taifu@taifua.com">邮箱</a></span>
    </div>
  </footer>
</template>
