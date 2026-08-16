<script setup lang="ts">
type AboutSummary = {
  startPeriod: string
  endPeriod: string
  generatedAt: string
  codeVersion: string
  schemaVersion: number
  configHash: string
  participants: number
  topics: number
  comments: number
  coverage: {
    topics: number
    contentTerms: number
    nodes: number
    members: number
  }
}

defineProps<{ summary: AboutSummary }>()
const emit = defineEmits<{ catalog: [] }>()

function formatCompactNumber(value: number) {
  if (value < 10_000) return value.toLocaleString("zh-CN")
  return `${(value / 10_000).toLocaleString("zh-CN", { maximumFractionDigits: 1 })} 万`
}

function formatDateTime(value: string) {
  if (!value) return "-"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })
}
</script>

<template>
  <section class="view-section about-view">
    <article class="about-document">
      <header class="about-document-header">
        <h2>关于本站</h2>
        <p>
          本站是一个基于 <a href="https://www.v2ex.com/" target="_blank" rel="noreferrer">V2EX</a>
          公开数据构建的非官方社区观察项目，交流反馈请联系
          <a href="mailto:taifu@taifua.com">邮箱</a>。
        </p>
      </header>

      <section>
        <h2>看板内容</h2>
        <div class="about-summary-grid">
          <div>
            <h3>数据概况</h3>
            <ul class="about-definitions about-summary-list">
              <li><strong>数据范围：</strong>{{ summary.startPeriod }} 至 {{ summary.endPeriod }}</li>
              <li><strong>看板生成：</strong>{{ formatDateTime(summary.generatedAt) }}</li>
              <li><strong>参与用户：</strong>{{ formatCompactNumber(summary.participants) }}</li>
              <li><strong>有效帖子：</strong>{{ formatCompactNumber(summary.topics) }}</li>
              <li><strong>评论：</strong>{{ formatCompactNumber(summary.comments) }}</li>
              <li v-if="summary.schemaVersion"><strong>分析版本：</strong>schema v{{ summary.schemaVersion }} · 代码 {{ summary.codeVersion }} · 规则 {{ summary.configHash.slice(0, 12) }}</li>
            </ul>
          </div>
          <div>
            <h3>分析覆盖</h3>
            <ul class="about-definitions about-summary-list">
              <li><strong>重点话题：</strong>{{ summary.coverage.topics.toLocaleString("zh-CN") }} 个</li>
              <li><strong>可检索标题关键词：</strong>{{ summary.coverage.contentTerms.toLocaleString("zh-CN") }} 个</li>
              <li><strong>收录节点：</strong>{{ summary.coverage.nodes.toLocaleString("zh-CN") }} 个</li>
              <li><strong>成员详情：</strong>{{ summary.coverage.members.toLocaleString("zh-CN") }} 位</li>
            </ul>
          </div>
        </div>
        <p class="about-scope">参与用户按公开发帖或评论记录去重；节点需累计至少 50 个有效帖子才收录详情，较小节点仅显示名称。分析覆盖不代表 V2EX 全部注册或分类数据。</p>
        <div class="about-prose">
          <h3>社区概览</h3>
          <p>观察帖子、评论、成员与互动规模的长期变化，并提供月度和年度汇总。</p>

          <h3>讨论演变</h3>
          <p>从话题、标题关键词和节点三个层面追踪社区关注方向，支持查看趋势、相关话题、节点、用户与代表帖子。</p>

          <h3>成员与互动</h3>
          <p>展示活跃成员的参与变化，以及收藏、感谢、回复和点击等反馈；部分高参与成员还可查看详细数据。</p>

          <h3>社区观察</h3>
          <p>结合长期数据、代表内容与已知社区事件形成离线点评，帮助发现值得继续查看的变化。</p>
        </div>
      </section>

      <section>
        <h2>数据说明</h2>
        <div class="about-prose">
          <h3>话题与标题关键词</h3>
          <ul class="about-definitions">
            <li><strong>话题。</strong>帖子携带的 V2EX 原始标签，是用户选择的结构化分类；标注较准确，但可能缺失或存在写法差异。</li>
            <li><strong>标题关键词。</strong>通过标题分词、同义写法合并和人工词表得到，用于补充产品、事件和新概念；不分析正文或评论语义。</li>
            <li><strong>关键词过滤。</strong>综合出现频次、作者与节点覆盖筛选候选词，再通过人工停用词表去除问句、语气、数量和指向不明确的通用操作词。普通词至少出现 20 次；人工复核的 AI 与理财实体可放宽到 10 次，但仍需跨作者、跨节点，少于 10 次不予收录。歧义词只保留“中国移动”“Google Drive”等语义完整的组合。</li>
          </ul>
          <p>同一个词可能同时属于话题和标题关键词，两套数据分别计数，不能直接视为同一指标。</p>

          <h3>来源与处理</h3>
          <p>数据来自 V2EX 中可访问的帖子、评论、节点、话题和成员公开页面。话题的同义写法会合并，标题关键词还会过滤停用词和低信息量表达。</p>

          <h3>快照属性</h3>
          <p>浏览、收藏、感谢和回复是抓取时的累计快照，后续互动可能继续变化。默认分析范围排除尚未完整结束的月份。</p>

          <h3>覆盖限制</h3>
          <p>已删除、受限或暂时不可访问的内容可能缺失；未公开或未成功读取的互动值记为未知，不展示为负数，具体汇总处理按对应页面的指标说明执行。</p>

          <h3>解读边界</h3>
          <p>标题关键词反映提及频率，不直接代表观点、情绪或因果关系。观察页的文字解读用于提供线索，仍需结合原帖和现实背景判断。</p>

          <h3>公开数据与使用边界</h3>
          <p>成员详情只覆盖达到公开活跃标准的部分账号，并以月度或年度聚合为主；本站不推断政治、健康、收入等敏感属性，也不将统计结果用于个人评价。需要更正或移除相关展示时，可通过页面顶部邮箱联系。</p>

          <h3>许可与访问统计</h3>
          <p>仓库的 MIT 许可仅适用于项目源代码，不改变 V2EX 原始内容及数据的权利归属。线上演示站使用百度统计了解访问量，统计脚本仅由服务器配置注入，不参与社区数据分析或公开数据集构建。</p>
        </div>
      </section>

      <footer class="about-links">
        <a href="?tab=about&about=catalog" @click.prevent="emit('catalog')">查看收录数据</a>
        <a href="https://github.com/taifuer/v2ex_scrapy" target="_blank" rel="noreferrer">查看开源项目</a>
        <a href="https://www.v2ex.com/" target="_blank" rel="noreferrer">访问 V2EX</a>
      </footer>
    </article>
  </section>
</template>
