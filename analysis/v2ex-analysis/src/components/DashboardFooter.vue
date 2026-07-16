<script setup lang="ts">
defineProps<{ year: number }>()
</script>

<template>
  <footer class="dashboard-footer">
    <div class="dashboard-footer-inner">
      <span>© {{ year }}</span>
      <a href="https://github.com/taifuer/v2ex_scrapy" target="_blank" rel="noreferrer">
        V2EX Dashboard
      </a>
      <span aria-hidden="true">·</span>
      <span>数据来源 <a href="https://v2ex.com/" target="_blank" rel="noreferrer">V2EX</a></span>
      <span aria-hidden="true">·</span>
      <span>仅供学习交流，如有侵权请联系删除</span>
    </div>
  </footer>
</template>
