<script setup lang="ts">
type AboutSummary = {
  startPeriod: string
  endPeriod: string
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
        <h2>可以观察什么</h2>
        <div class="about-summary-grid">
          <div>
            <h3>数据概况</h3>
            <ul class="about-definitions about-summary-list">
              <li><strong>数据范围：</strong>{{ summary.startPeriod }} 至 {{ summary.endPeriod }}</li>
              <li><strong>参与用户：</strong>{{ formatCompactNumber(summary.participants) }}</li>
              <li><strong>有效帖子：</strong>{{ formatCompactNumber(summary.topics) }}</li>
              <li><strong>评论：</strong>{{ formatCompactNumber(summary.comments) }}</li>
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
        <ul class="about-question-list">
          <li><a href="?tab=overview&overview=trend">社区规模如何变化？</a><span>查看帖子、评论、成员和互动规模的长期趋势，以及月度、年度汇总。</span></li>
          <li><a href="?tab=content&view=topics">社区在讨论什么？</a><span>从 V2EX 原始话题、标题关键词和节点观察关注方向与结构迁移。</span></li>
          <li><a href="?tab=content&view=lifecycle">讨论如何展开？</a><span>查看回复覆盖、首条回复速度、参与用户、楼主参与和讨论强度。</span></li>
          <li><a href="?tab=engagement">哪些内容获得更多反馈？</a><span>比较热门帖子、热门评论，并在话题、标题关键词和节点详情中查看代表内容。</span></li>
          <li><a href="?tab=observations">哪些变化值得继续追踪？</a><span>结合长期数据、代表内容与已知社区事件阅读离线点评。</span></li>
        </ul>
      </section>

      <section>
        <h2>数据说明</h2>
        <div class="about-prose">
          <h3>话题与标题关键词</h3>
          <ul class="about-definitions">
            <li><strong>话题。</strong>帖子携带的 V2EX 原始标签，是用户选择的结构化分类；标注较准确，但可能缺失或存在写法差异。</li>
            <li><strong>标题关键词。</strong>通过标题分词、同义写法合并和人工词表得到，用于补充产品、事件和新概念；不分析正文或评论语义。</li>
            <li><strong>关键词过滤。</strong>频次只作为候选门槛；是否收录还会检查语义一致性、时间变化、作者与节点覆盖、推广集中度，以及与既有关键词的重合程度，再用人工停用词表排除指向不明确的泛词。普通词至少出现 20 次；人工复核的 AI 与理财实体可放宽到 10 次，但仍需跨作者、跨节点。歧义词优先保留“中国移动”“云原生”等语义完整的组合。</li>
            <li><strong>代表评论。</strong>话题和标题关键词按当前范围逐年保留感谢 Top 10 后合并，节点按全部历史逐年合并并最多展示 100 条；只收录至少获得 1 次感谢的评论，并保留原文、作者、时间和来源帖子。</li>
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
