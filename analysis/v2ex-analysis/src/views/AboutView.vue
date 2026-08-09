<script setup lang="ts">
defineProps<{ dataScope: string }>()
</script>

<template>
  <section class="view-section about-view">
    <article class="about-document">
      <header class="about-document-header">
        <h2>关于本站</h2>
        <p>
          一个基于 <a href="https://www.v2ex.com/" target="_blank" rel="noreferrer">V2EX</a>
          公开数据构建的非官方社区观察项目，交流反馈请联系
          <a href="mailto:taifu@taifua.com">邮箱</a>。
        </p>
      </header>

      <section>
        <h2>看板内容</h2>
        <p class="about-scope">{{ dataScope }}</p>
        <div class="about-prose">
          <h3>社区概览</h3>
          <p>观察帖子、评论、成员与互动规模的长期变化，并提供月度和年度数据切片。</p>

          <h3>讨论演变</h3>
          <p>从话题、标题关键词和节点三个层面追踪社区关注方向，支持查看趋势、关联结构与代表帖子。</p>

          <h3>成员与互动</h3>
          <p>展示活跃成员的参与变化以及收藏、感谢、回复和点击等反馈，为部分高参与成员提供有限详情。</p>

          <h3>社区观察</h3>
          <p>结合长期数据、代表内容与已知社区事件形成离线点评，用于提示值得进一步查看的变化。</p>
        </div>
      </section>

      <section>
        <h2>数据说明</h2>
        <div class="about-prose">
          <h3>话题与标题关键词</h3>
          <ul class="about-definitions">
            <li><strong>话题。</strong>帖子携带的 V2EX 原始标签，是用户选择的结构化分类；标注较准确，但可能缺失或存在写法差异。</li>
            <li><strong>标题关键词。</strong>从帖子标题经分词、同义词归一和人工词表得到，用于补充产品、事件和新概念；不分析正文或评论语义。</li>
          </ul>
          <p>同一个词可能同时属于话题和标题关键词，两套数据分别计数，不能直接视为同一指标。</p>

          <h3>来源与处理</h3>
          <p>数据来自 V2EX 可访问的帖子、评论、节点、话题和成员公开页面。话题会归一同义写法，标题关键词还会过滤停用词和低信息量表达。</p>

          <h3>快照属性</h3>
          <p>浏览、收藏、感谢和回复是抓取时的累计快照，后续互动可能继续变化。默认分析范围排除尚未完整结束的月份。</p>

          <h3>覆盖限制</h3>
          <p>已删除、受限或暂时不可访问的内容可能缺失；未公开或未成功读取的互动值记为未知，不展示为负数，具体汇总处理按对应页面的指标说明执行。</p>

          <h3>解读边界</h3>
          <p>标题关键词反映提及频率，不直接代表观点、情绪或因果关系。观察页的文字解读用于提供线索，仍需结合原帖和现实背景判断。</p>
        </div>
      </section>

      <footer class="about-links">
        <a href="https://github.com/taifuer/v2ex_scrapy" target="_blank" rel="noreferrer">查看开源项目</a>
        <a href="https://www.v2ex.com/" target="_blank" rel="noreferrer">访问 V2EX</a>
      </footer>
    </article>
  </section>
</template>
