<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { ChevronLeft, ChevronRight, Maximize2, Minimize2, Search } from "@lucide/vue"

type AboutSummary = {
  startPeriod: string
  endPeriod: string
  participants: number
  topics: number
  comments: number
  coverage: { topics: number; contentTerms: number; nodes: number; members: number }
}

type Slide = { id: string; eyebrow: string; title: string }

const props = defineProps<{
  observations: any
  summary: AboutSummary
  nodeLabel: (node: string) => string
}>()
const emit = defineEmits<{ openSearch: [restoreTo: HTMLElement] }>()

const stage = ref<HTMLElement | null>(null)
const current = ref(0)
const fullscreen = ref(false)

const slides: Slide[] = [
  { id: "cover", eyebrow: "V2EX 社区数据观察", title: "从百万条讨论，看见社区如何变化" },
  { id: "community", eyebrow: "规模与成员", title: "社区正从规模扩张转向存量讨论" },
  { id: "topics", eyebrow: "话题结构", title: "技术仍是主线，但讨论重心已经改变" },
  { id: "ai", eyebrow: "话题与标题关键词", title: "AI 讨论从产品名走向模型与智能体" },
  { id: "nodes", eyebrow: "节点结构", title: "问答与交易是社区最大的两个入口" },
  { id: "value", eyebrow: "互动反馈", title: "收藏与感谢代表两种内容价值" },
  { id: "rhythm", eyebrow: "活跃与回应", title: "讨论发生在工作时间，也结束得很快" },
  { id: "explore", eyebrow: "继续探索", title: "固定结论之外，更多变化由你发现" },
]

const slide = computed(() => slides[current.value])
const presentation = computed(() => props.observations.presentation || {})
const scope = computed(() => ({
  start_period: props.summary.startPeriod,
  end_period: props.summary.endPeriod,
  participants: props.summary.participants,
  topics: props.summary.topics,
  comments: props.summary.comments,
  complete_months: 0,
  comments_per_topic: props.summary.topics ? props.summary.comments / props.summary.topics : 0,
  coverage: {
    topics: props.summary.coverage.topics,
    content_terms: props.summary.coverage.contentTerms,
    nodes: props.summary.coverage.nodes,
    members: props.summary.coverage.members,
  },
  ...(presentation.value.scope || {}),
}))
const community = computed(() => presentation.value.community || {})
const topicShifts = computed(() => presentation.value.topic_shifts || {})
const ai = computed(() => presentation.value.ai || {})
const nodes = computed(() => presentation.value.nodes || [])
const interaction = computed(() => presentation.value.interaction || {})
const rhythm = computed(() => presentation.value.rhythm || {})
const maxNodeTopics = computed(() => Math.max(1, ...nodes.value.map((item: any) => Number(item.topics || 0))))
const topNodeShare = computed(() => nodes.value.reduce((total: number, item: any) => total + Number(item.share || 0), 0))

function formatNumber(value: number) {
  return Number(value || 0).toLocaleString("zh-CN")
}

function formatCompact(value: number) {
  if (value < 10_000) return formatNumber(value)
  return `${(Math.floor(value / 1_000) / 10).toFixed(1)}万`
}

function signed(value: number) {
  return `${Number(value || 0) > 0 ? "+" : ""}${Number(value || 0).toFixed(1)}%`
}

function monthIndex(period: string) {
  const [year, month] = String(period || "").split("-").map(Number)
  return year * 12 + month - 1
}

function aiTimelinePosition(period: string) {
  const start = monthIndex("2022-12")
  const end = monthIndex(scope.value.end_period || "2026-08")
  return Math.max(2, Math.min(98, (monthIndex(period) - start) / Math.max(1, end - start) * 100))
}

function move(offset: number) {
  current.value = Math.min(slides.length - 1, Math.max(0, current.value + offset))
}

function openSearch(event: MouseEvent) {
  emit("openSearch", event.currentTarget as HTMLElement)
}

function handleKeydown(event: KeyboardEvent) {
  if ((event.target as HTMLElement)?.closest("button, a, input, select")) return
  if (event.key === "ArrowRight" || event.key === "PageDown") {
    event.preventDefault()
    move(1)
  } else if (event.key === "ArrowLeft" || event.key === "PageUp") {
    event.preventDefault()
    move(-1)
  } else if (event.key === "Home") {
    current.value = 0
  } else if (event.key === "End") {
    current.value = slides.length - 1
  }
}

async function toggleFullscreen() {
  if (!document.fullscreenElement) await stage.value?.requestFullscreen()
  else await document.exitFullscreen()
}

function handleFullscreenChange() {
  fullscreen.value = document.fullscreenElement === stage.value
}

onMounted(() => {
  window.addEventListener("keydown", handleKeydown)
  document.addEventListener("fullscreenchange", handleFullscreenChange)
})

onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleKeydown)
  document.removeEventListener("fullscreenchange", handleFullscreenChange)
})
</script>

<template>
  <section class="view-section deck-view">
    <div class="deck-toolbar">
      <div><strong>数据演示</strong><span class="deck-iteration">持续迭代中</span><span>{{ current + 1 }} / {{ slides.length }}</span></div>
      <div>
        <button type="button" class="icon-button" aria-label="上一页" title="上一页" :disabled="current === 0" @click="move(-1)"><ChevronLeft :size="18" /></button>
        <button type="button" class="icon-button" aria-label="下一页" title="下一页" :disabled="current === slides.length - 1" @click="move(1)"><ChevronRight :size="18" /></button>
        <button type="button" class="icon-button deck-fullscreen" :aria-label="fullscreen ? '退出全屏' : '全屏演示'" :title="fullscreen ? '退出全屏' : '全屏演示'" @click="toggleFullscreen">
          <Minimize2 v-if="fullscreen" :size="17" /><Maximize2 v-else :size="17" />
        </button>
      </div>
    </div>

    <article ref="stage" class="deck-stage" :class="`deck-${slide.id}`" aria-live="polite">
      <span class="deck-page-number">{{ String(current + 1).padStart(2, "0") }}</span>

      <template v-if="slide.id === 'cover'">
        <header class="deck-cover-copy">
          <span>{{ slide.eyebrow }}</span>
          <h2>V2EX 看板</h2>
          <p>{{ slide.title }}。这里既有基础统计，也有话题、标题关键词、节点与互动背后的变化线索。</p>
          <small>{{ scope.start_period }} 至 {{ scope.end_period }} · {{ scope.complete_months }} 个完整月份</small>
          <a class="deck-primary-link" href="?tab=overview">进入数据概览</a>
        </header>
        <section class="deck-purpose" aria-label="看板分析内容">
          <p><b>01</b><span><strong>社区如何变化</strong>帖子、评论、成员与互动规模</span></p>
          <p><b>02</b><span><strong>大家讨论什么</strong>话题、标题关键词与节点结构</span></p>
          <p><b>03</b><span><strong>内容如何被回应</strong>代表帖子、热门评论与生命周期</span></p>
        </section>
        <div class="deck-cover-metrics">
          <div><strong>{{ formatCompact(scope.participants) }}</strong><span>参与用户</span></div>
          <div><strong>{{ formatCompact(scope.topics) }}</strong><span>有效帖子</span></div>
          <div><strong>{{ formatCompact(scope.comments) }}</strong><span>评论</span></div>
        </div>
      </template>

      <template v-else-if="slide.id === 'community'">
        <header class="deck-heading"><span>{{ slide.eyebrow }}</span><h2>{{ slide.title }}</h2><p>最近十年的后五年，帖子减少得更明显，评论下降较慢；更少的帖子承载了更集中的讨论。</p></header>
        <div class="deck-community-body">
          <section class="deck-change-bars">
            <h3>前五年 = 100</h3>
            <div class="deck-change-group">
              <strong>帖子</strong>
              <p><span>前五年</span><i><b style="width:100%"></b></i><em>100</em></p>
              <p><span>后五年</span><i><b :style="{ width: `${100 + Number(community.topic_change || 0)}%` }"></b></i><em>{{ (100 + Number(community.topic_change || 0)).toFixed(1) }}</em></p>
            </div>
            <div class="deck-change-group comments">
              <strong>评论</strong>
              <p><span>前五年</span><i><b style="width:100%"></b></i><em>100</em></p>
              <p><span>后五年</span><i><b :style="{ width: `${100 + Number(community.comment_change || 0)}%` }"></b></i><em>{{ (100 + Number(community.comment_change || 0)).toFixed(1) }}</em></p>
            </div>
          </section>
          <section class="deck-invite-event">
            <span>{{ community.invitation_period }} · 邀请码制度生效</span>
            <div><strong>{{ formatNumber(community.members_before) }}</strong><i>→</i><strong>{{ formatNumber(community.members_after) }}</strong></div>
            <p>实施前后各 12 个月的月均新增成员，下降 <b>{{ Math.abs(Number(community.member_change || 0)).toFixed(1) }}%</b>。同期活动没有同比例消失，存量成员仍维持大部分讨论。</p>
            <a href="?tab=community&from=2023-05&to=2025-04">查看成员变化</a>
          </section>
        </div>
        <footer class="deck-fact-row">
          <span>平均每帖评论</span><strong>{{ community.previous_density }} <i>→</i> {{ community.current_density }}</strong><p>帖子变化 {{ signed(community.topic_change) }} · 评论变化 {{ signed(community.comment_change) }}</p>
        </footer>
      </template>

      <template v-else-if="slide.id === 'topics'">
        <header class="deck-heading"><span>{{ slide.eyebrow }}</span><h2>{{ slide.title }}</h2><p>技术内容没有消失，但社区已经从通用开发和求职问题，扩展到 AI 工具、产品实践与生活经验。</p></header>
        <div class="deck-shift-columns">
          <section class="deck-shift down">
            <h3>讨论回落</h3>
            <div><span>工作与职场</span><strong>{{ signed(topicShifts.career_change) }}</strong></div>
            <div><span>编程与工程</span><strong>{{ signed(topicShifts.engineering_change) }}</strong></div>
          </section>
          <section class="deck-shift up">
            <h3>讨论增长</h3>
            <div><span>产品与创造</span><strong>{{ signed(topicShifts.creation_change) }}</strong></div>
            <div><span>城市与生活</span><strong>{{ signed(topicShifts.home_change) }}</strong></div>
            <div class="highlight"><span>AI 与智能体</span><strong>{{ signed(topicShifts.ai_change) }}</strong></div>
          </section>
        </div>
        <section class="deck-subscription-evidence">
          <span>数字协作也成为日常</span>
          <div v-for="term in ['拼车', '88vip', '订阅']" :key="term">
            <b>{{ term === '88vip' ? '88VIP' : term }}</b>
            <strong>{{ formatNumber(topicShifts.subscription?.[term]?.previous) }} <i>→</i> {{ formatNumber(topicShifts.subscription?.[term]?.current) }}</strong>
          </div>
          <small>前五年 → 后五年</small>
        </section>
        <footer class="deck-topic-footer">
          <div><strong>{{ Number(topicShifts.apple_share || 0).toFixed(2) }}%</strong><span>Apple 生态近十年帖子占比，仍是稳定主线</span></div>
          <a href="?tab=content&view=topics&from=2016-09&to=2026-08">查看话题演变</a>
        </footer>
      </template>

      <template v-else-if="slide.id === 'ai'">
        <header class="deck-heading"><span>{{ slide.eyebrow }}</span><h2>{{ slide.title }}</h2><p>原始话题反映用户主动标注，标题关键词补充产品名和新概念；两者结合才能看到完整迁移。</p></header>
        <div class="deck-ai-body">
          <section class="deck-ai-timeline">
            <div class="deck-timeline-line"></div>
            <div class="deck-ai-point" :style="{ left: `${aiTimelinePosition(ai.chatgpt_peak?.period)}%` }"><time>{{ ai.chatgpt_peak?.period }}</time><strong>ChatGPT</strong><span>{{ formatNumber(ai.chatgpt_peak?.count) }} 帖/月</span></div>
            <div class="deck-ai-point" :style="{ left: `${aiTimelinePosition(ai.ai_peak?.period)}%` }"><time>{{ ai.ai_peak?.period }}</time><strong>AI</strong><span>{{ formatNumber(ai.ai_peak?.count) }} 帖/月</span></div>
            <div class="deck-ai-point end" :style="{ left: `${aiTimelinePosition(ai.model_peak?.period)}%` }"><time>{{ ai.model_peak?.period }}</time><strong>模型</strong><span>{{ formatNumber(ai.model_peak?.count) }} 帖/月</span></div>
          </section>
          <section class="deck-ai-keywords">
            <span>最近 12 个月标题关键词</span>
            <a href="?tab=content&view=content-detail&term=Codex"><strong>{{ formatNumber(ai.codex_recent) }}</strong><small>Codex</small></a>
            <a href="?tab=content&view=content-detail&term=Agent"><strong>{{ formatNumber(ai.agent_recent) }}</strong><small>Agent</small></a>
            <a href="?tab=content&view=content-detail&term=Claude%20Code"><strong>{{ formatNumber(ai.claude_code_recent) }}</strong><small>Claude Code</small></a>
          </section>
        </div>
        <footer class="deck-context">同期 Java、Python 话题量分别只有各自滚动峰值的 <b>{{ ai.java_recent_peak_share }}%</b> 和 <b>{{ ai.python_recent_peak_share }}%</b>。这表示讨论重心变化，不等同于技术使用量。</footer>
      </template>

      <template v-else-if="slide.id === 'nodes'">
        <header class="deck-heading"><span>{{ slide.eyebrow }}</span><h2>{{ slide.title }}</h2><p>最大的节点不是某种编程语言，而是解决问题和交换资源的日常场景。</p></header>
        <div class="deck-node-bars">
          <a v-for="(item, index) in nodes" :key="item.node" :href="`?tab=content&view=node-detail&node=${encodeURIComponent(item.node)}`">
            <b>{{ String(Number(index) + 1).padStart(2, "0") }}</b>
            <span>{{ nodeLabel(item.node) }}</span>
            <i><em :style="{ width: `${item.topics / maxNodeTopics * 100}%` }"></em></i>
            <strong>{{ formatNumber(item.topics) }}</strong>
            <small>{{ Number(item.share).toFixed(2) }}%</small>
          </a>
        </div>
        <footer class="deck-node-footer"><strong>{{ topNodeShare.toFixed(2) }}%</strong><span>帖子集中在前五个节点；问答、交易、工作与分享共同构成社区日常。</span><a href="?tab=content&view=nodes">查看节点结构</a></footer>
      </template>

      <template v-else-if="slide.id === 'value'">
        <header class="deck-heading"><span>{{ slide.eyebrow }}</span><h2>{{ slide.title }}</h2><p>一个回答“以后还会不会用”，另一个回答“当下是否值得认可”；单一榜单无法概括内容价值。</p></header>
        <div class="deck-value-head"><strong>{{ interaction.overlap }} / {{ interaction.ranking_size }}</strong><span>收藏 Top 20 与感谢 Top 20 的重合帖子</span></div>
        <div class="deck-value-grid">
          <a :href="`https://www.v2ex.com/t/${interaction.favorite_post?.id}`" target="_blank" rel="noreferrer">
            <span>收藏榜首</span><strong>{{ formatNumber(interaction.favorite_post?.value) }}</strong><h3>{{ interaction.favorite_post?.title }}</h3><p>收藏更偏向工具、教程、资源清单和可复用经验。</p>
          </a>
          <a :href="`https://www.v2ex.com/t/${interaction.thanked_post?.id}`" target="_blank" rel="noreferrer">
            <span>感谢榜首</span><strong>{{ formatNumber(interaction.thanked_post?.value) }}</strong><h3>{{ interaction.thanked_post?.title }}</h3><p>感谢更多流向原创投入、公共信息与真实经历。</p>
          </a>
        </div>
        <footer class="deck-comment-facts">
          <div><strong>{{ interaction.comment_median_length }}</strong><span>热门评论正文长度中位数</span></div>
          <div><strong>{{ interaction.short_comments }} / {{ interaction.comment_sample_size }}</strong><span>正文不超过 30 字</span></div>
          <div><strong>{{ formatNumber(interaction.comment_top_thanks) }}</strong><span>榜首评论感谢</span></div>
        </footer>
      </template>

      <template v-else-if="slide.id === 'rhythm'">
        <header class="deck-heading"><span>{{ slide.eyebrow }}</span><h2>{{ slide.title }}</h2><p>社区节律与工作场景重合，发布后的前几个小时决定了多数帖子的讨论规模。</p></header>
        <div class="deck-rhythm-grid">
          <section class="deck-worktime">
            <h3>工作日 9:00–17:00</h3>
            <div><span>帖子</span><i><b :style="{ width: `${rhythm.workday_topic_share}%` }"></b></i><strong>{{ rhythm.workday_topic_share }}%</strong></div>
            <div><span>评论</span><i><b :style="{ width: `${rhythm.workday_comment_share}%` }"></b></i><strong>{{ rhythm.workday_comment_share }}%</strong></div>
            <p>社区更像嵌入工作与技术协作场景的信息网络，而不只是晚间活跃的休闲论坛。</p>
          </section>
          <section class="deck-response">
            <h3>帖子获得首条回复</h3>
            <div><i :style="{ width: `${rhythm.within_1h_share}%` }"></i><strong>{{ rhythm.within_1h_share }}%</strong><span>1 小时内</span></div>
            <div><i :style="{ width: `${rhythm.within_24h_share}%` }"></i><strong>{{ rhythm.within_24h_share }}%</strong><span>24 小时内</span></div>
            <div><i :style="{ width: `${rhythm.response_share}%` }"></i><strong>{{ rhythm.response_share }}%</strong><span>7 日内</span></div>
            <p>7 天后产生的评论只占 30 日评论的 <b>{{ rhythm.after_7d_share }}%</b>。</p>
          </section>
        </div>
        <footer class="deck-link-footer"><a href="?tab=overview">查看活跃时段</a><a href="?tab=content&view=lifecycle">查看帖子生命周期</a></footer>
      </template>

      <template v-else>
        <header class="deck-heading"><span>{{ slide.eyebrow }}</span><h2>{{ slide.title }}</h2><p>固定点评只能展示少数线索。选择时间范围，从任意对象继续查看趋势、关联关系与代表内容。</p></header>
        <div class="deck-coverage">
          <div><strong>{{ formatNumber(scope.coverage.topics) }}</strong><span>收录话题</span></div>
          <div><strong>{{ formatNumber(scope.coverage.content_terms) }}</strong><span>标题关键词</span></div>
          <div><strong>{{ formatNumber(scope.coverage.nodes) }}</strong><span>收录节点</span></div>
          <div><strong>{{ formatNumber(scope.coverage.members) }}</strong><span>重点活跃成员</span></div>
        </div>
        <button type="button" class="deck-search" aria-label="打开全站搜索" @click="openSearch">
          <Search :size="18" aria-hidden="true" />
          <span><strong>打开全站搜索</strong><small>检索已收录的话题、标题关键词、节点和部分活跃成员</small></span>
          <b>打开</b>
        </button>
        <div class="deck-suggestions">
          <a href="?tab=content&view=topic-detail&tag=AI">AI</a>
          <a href="?tab=content&view=topic-detail&tag=Apple">Apple</a>
          <a href="?tab=content&view=content-detail&term=Codex">Codex</a>
          <a href="?tab=content&view=content-detail&term=裁员">裁员</a>
          <a href="?tab=content&view=node-detail&node=qna">问与答</a>
          <a href="?tab=content&view=node-detail&node=programmer">程序员</a>
        </div>
        <div class="deck-explore-questions">
          <a href="?tab=content&view=topic-detail&tag=AI"><span>话题迁移</span><strong>AI 与 ChatGPT 的峰值同步吗？</strong></a>
          <a href="?tab=content&view=content-detail&term=裁员"><span>内容变化</span><strong>“裁员”在什么时候集中出现？</strong></a>
          <a href="?tab=content&view=node-detail&node=qna"><span>社区结构</span><strong>问答节点由哪些用户和内容推动？</strong></a>
        </div>
      </template>

      <div class="deck-progress"><i :style="{ width: `${(current + 1) / slides.length * 100}%` }"></i></div>
    </article>

    <div class="deck-dots" aria-label="演示页码">
      <button v-for="(item, index) in slides" :key="item.id" type="button" :class="{ active: index === current }" :aria-label="`第 ${index + 1} 页：${item.title}`" :aria-current="index === current ? 'page' : undefined" @click="current = index"><span>{{ index + 1 }}</span></button>
    </div>
  </section>
</template>

<style scoped>
.deck-view { min-height: 0; }
.deck-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 10px; }
.deck-toolbar > div { display: flex; align-items: center; gap: 8px; }
.deck-toolbar strong { font-size: 14px; }
.deck-toolbar span { color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }
.deck-toolbar .deck-iteration { border-left: 1px solid var(--line); padding-left: 8px; }
.deck-toolbar .icon-button:disabled { opacity: .38; cursor: default; }
.deck-stage { position: relative; display: flex; width: 100%; height: clamp(540px, calc(100vh - 340px), 600px); min-height: 540px; flex-direction: column; overflow: hidden; border: 1px solid #d7dee7; border-radius: 8px; background: #fff; box-shadow: var(--shadow-md); padding: 36px 50px 40px; }
.deck-stage:fullscreen { width: 100vw; height: 100vh; min-height: 0; border: 0; border-radius: 0; padding: 6vh 6vw; }
.deck-stage a { color: inherit; text-decoration: none; }
.deck-page-number { position: absolute; top: 18px; right: 22px; color: #98a2b3; font-size: 11px; font-weight: 700; }
.deck-progress { position: absolute; right: 0; bottom: 0; left: 0; height: 4px; background: #edf0f3; }
.deck-progress i { display: block; height: 100%; background: var(--accent); transition: width 180ms ease; }
.deck-heading > span, .deck-cover-copy > span { display: block; margin-bottom: 7px; color: var(--accent); font-size: 11px; font-weight: 750; }
.deck-heading h2 { margin: 0; font-size: 29px; line-height: 1.28; }
.deck-heading p { max-width: 1020px; margin: 9px 0 0; color: #475467; font-size: 14px; line-height: 1.6; }
.deck-primary-link, .deck-link-footer a { display: inline-flex; align-items: center; justify-content: center; border-radius: 5px; background: #17212f; color: #fff !important; padding: 9px 14px; font-size: 12px; font-weight: 700; }
.deck-cover { display: grid; grid-template-columns: minmax(0, 1.05fr) minmax(330px, .95fr); grid-template-rows: minmax(0, 1fr) auto; align-items: center; gap: 30px 56px; background: #fbfcfe; }
.deck-cover-copy h2 { margin: 0; font-size: 56px; line-height: 1.05; }
.deck-cover-copy p { max-width: 690px; margin: 16px 0 12px; color: #344054; font-size: 18px; line-height: 1.6; }
.deck-cover-copy small { display: block; color: #667085; font-size: 12px; }
.deck-cover-copy .deck-primary-link { margin-top: 22px; }
.deck-purpose { border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.deck-purpose p { display: grid; grid-template-columns: 34px minmax(0, 1fr); gap: 12px; margin: 0; border-bottom: 1px solid var(--line); padding: 17px 0; }
.deck-purpose p:last-child { border-bottom: 0; }
.deck-purpose b { color: var(--accent); font-size: 11px; }
.deck-purpose strong, .deck-purpose span { display: block; }
.deck-purpose strong { margin-bottom: 4px; color: #17212f; font-size: 15px; }
.deck-purpose span { color: #667085; font-size: 12px; }
.deck-cover-metrics { display: grid; grid-column: 1 / -1; grid-template-columns: repeat(3, minmax(0, 1fr)); border-top: 1px solid var(--line); }
.deck-cover-metrics div { border-right: 1px solid var(--line); padding: 17px 22px 0; }
.deck-cover-metrics div:first-child { padding-left: 0; }
.deck-cover-metrics div:last-child { border-right: 0; }
.deck-cover-metrics strong, .deck-cover-metrics span { display: block; }
.deck-cover-metrics strong { font-size: 27px; font-variant-numeric: tabular-nums; }
.deck-cover-metrics span { margin-top: 3px; color: #667085; font-size: 11px; }
.deck-community-body { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(310px, .75fr); flex: 1; align-items: center; gap: 50px; margin-top: 22px; }
.deck-change-bars { border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); padding: 18px 0; }
.deck-change-bars h3 { margin: 0 0 10px; color: #667085; font-size: 11px; }
.deck-change-group { display: grid; grid-template-columns: 48px minmax(0, 1fr); gap: 0 12px; align-items: center; }
.deck-change-group + .deck-change-group { margin-top: 9px; }
.deck-change-group > strong { grid-row: 1 / span 2; font-size: 12px; }
.deck-change-group p { display: grid; grid-template-columns: 52px minmax(0, 1fr) 42px; align-items: center; gap: 9px; min-height: 32px; margin: 0; }
.deck-change-bars span, .deck-change-bars em { color: #475467; font-size: 11px; font-style: normal; }
.deck-change-bars i { height: 13px; background: #edf0f3; }
.deck-change-bars b { display: block; height: 100%; background: #df3d36; }
.deck-change-bars .comments b { background: #4e79a7; }
.deck-invite-event { border-left: 3px solid #df3d36; background: #f8fafc; padding: 22px 24px; }
.deck-invite-event > span { color: #c4322d; font-size: 11px; font-weight: 700; }
.deck-invite-event > div { display: flex; align-items: center; gap: 12px; margin: 14px 0 10px; }
.deck-invite-event > div strong { font-size: 29px; }
.deck-invite-event i { color: #98a2b3; font-style: normal; }
.deck-invite-event p { margin: 0; color: #475467; font-size: 12px; line-height: 1.65; }
.deck-invite-event a, .deck-topic-footer a, .deck-node-footer a { display: inline-block; margin-top: 14px; border-bottom: 1px solid #17212f; padding-bottom: 2px; font-size: 12px; font-weight: 700; }
.deck-fact-row { display: grid; grid-template-columns: 110px auto minmax(0, 1fr); align-items: center; gap: 18px; border-top: 1px solid var(--line); padding-top: 16px; }
.deck-fact-row span, .deck-fact-row p { color: #667085; font-size: 12px; }
.deck-fact-row strong { font-size: 22px; }
.deck-fact-row i { color: #98a2b3; font-style: normal; }
.deck-fact-row p { margin: 0; text-align: right; }
.deck-shift-columns { display: grid; grid-template-columns: .8fr 1.2fr; flex: 1; align-items: center; gap: 46px; margin-top: 20px; }
.deck-shift { border-top: 3px solid #98a2b3; }
.deck-shift.up { border-color: #2f8f83; }
.deck-shift h3 { margin: 0; border-bottom: 1px solid var(--line); color: #667085; padding: 12px 0; font-size: 12px; }
.deck-shift > div { display: flex; align-items: baseline; justify-content: space-between; gap: 20px; border-bottom: 1px solid var(--line); padding: 17px 0; }
.deck-shift span { color: #344054; font-size: 14px; font-weight: 650; }
.deck-shift strong { color: #667085; font-size: 23px; font-variant-numeric: tabular-nums; }
.deck-shift.up strong { color: #247d73; }
.deck-shift .highlight strong { color: #df3d36; font-size: 30px; }
.deck-subscription-evidence { display: grid; grid-template-columns: 165px repeat(3, minmax(0, 1fr)) auto; align-items: center; gap: 14px; border-top: 1px solid var(--line); padding: 13px 0; }
.deck-subscription-evidence > span, .deck-subscription-evidence small { color: #667085; font-size: 10px; font-weight: 700; }
.deck-subscription-evidence div { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.deck-subscription-evidence b { font-size: 11px; }
.deck-subscription-evidence strong { font-size: 12px; font-variant-numeric: tabular-nums; }
.deck-subscription-evidence i { color: #98a2b3; font-style: normal; }
.deck-topic-footer { display: flex; align-items: center; gap: 14px; border-top: 1px solid var(--line); padding-top: 16px; }
.deck-topic-footer > div { display: flex; align-items: baseline; gap: 10px; }
.deck-topic-footer strong { font-size: 25px; }
.deck-topic-footer span { color: #667085; font-size: 12px; }
.deck-topic-footer a { margin: 0 0 0 auto; }
.deck-ai-body { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(250px, .45fr); flex: 1; align-items: center; gap: 46px; margin-top: 22px; }
.deck-ai-timeline { position: relative; height: 150px; margin: 0 3%; }
.deck-timeline-line { position: absolute; top: 54px; right: 0; left: 0; height: 2px; background: #cfd6df; }
.deck-ai-point { position: absolute; top: 46px; min-width: 120px; transform: translateX(-18%); }
.deck-ai-point.end { transform: translateX(-100%); text-align: right; }
.deck-ai-point::before { display: block; width: 13px; height: 13px; margin-bottom: 10px; border: 3px solid #fff; border-radius: 50%; background: #df3d36; box-shadow: 0 0 0 1px #df3d36; content: ""; }
.deck-ai-point.end::before { margin-left: auto; }
.deck-ai-point time, .deck-ai-point strong, .deck-ai-point span { display: block; }
.deck-ai-point time { color: #df3d36; font-size: 10px; }
.deck-ai-point strong { margin-top: 3px; font-size: 18px; }
.deck-ai-point span { margin-top: 3px; color: #667085; font-size: 11px; }
.deck-ai-keywords { display: grid; gap: 7px; align-items: stretch; }
.deck-ai-keywords > span { display: flex; align-items: center; margin-bottom: 2px; color: #667085; font-size: 11px; font-weight: 700; }
.deck-ai-keywords a { border-left: 3px solid #2f8f83; background: #f4f9f8; padding: 12px 15px; }
.deck-ai-keywords strong, .deck-ai-keywords small { display: block; }
.deck-ai-keywords strong { font-size: 21px; }
.deck-ai-keywords small { margin-top: 3px; color: #667085; font-size: 11px; }
.deck-context { margin-top: 18px; border-top: 1px solid var(--line); color: #667085; padding-top: 13px; font-size: 11px; line-height: 1.6; }
.deck-node-bars { display: grid; flex: 1; align-content: center; gap: 16px; margin-top: 18px; }
.deck-node-bars a { display: grid; grid-template-columns: 26px 120px minmax(0, 1fr) 78px 54px; align-items: center; gap: 12px; }
.deck-node-bars b { color: #98a2b3; font-size: 10px; }
.deck-node-bars span { font-size: 13px; font-weight: 700; }
.deck-node-bars i { height: 17px; background: #edf0f3; }
.deck-node-bars em { display: block; height: 100%; background: #4e79a7; }
.deck-node-bars strong, .deck-node-bars small { text-align: right; font-variant-numeric: tabular-nums; }
.deck-node-bars strong { font-size: 12px; }
.deck-node-bars small { color: #667085; font-size: 10px; }
.deck-node-footer { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 14px; border-top: 1px solid var(--line); padding-top: 15px; }
.deck-node-footer > strong { color: #2f8f83; font-size: 24px; }
.deck-node-footer > span { color: #667085; font-size: 12px; }
.deck-node-footer a { margin: 0; }
.deck-value-head { display: flex; align-items: baseline; gap: 10px; margin-top: 18px; border-bottom: 1px solid var(--line); padding-bottom: 12px; }
.deck-value-head strong { color: #df3d36; font-size: 28px; }
.deck-value-head span { color: #667085; font-size: 12px; }
.deck-value-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); flex: 1; }
.deck-value-grid > a { display: grid; align-content: center; border-right: 1px solid var(--line); padding: 18px 32px 18px 0; }
.deck-value-grid > a:last-child { border-right: 0; padding: 18px 0 18px 32px; }
.deck-value-grid > a > span { color: var(--accent); font-size: 11px; font-weight: 700; }
.deck-value-grid > a > strong { margin-top: 5px; font-size: 31px; }
.deck-value-grid h3 { margin: 8px 0; font-size: 16px; line-height: 1.4; }
.deck-value-grid p { margin: 0; color: #667085; font-size: 12px; line-height: 1.6; }
.deck-comment-facts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border-top: 1px solid var(--line); }
.deck-comment-facts div { border-right: 1px solid var(--line); padding: 13px 18px 0; }
.deck-comment-facts div:first-child { padding-left: 0; }
.deck-comment-facts div:last-child { border-right: 0; }
.deck-comment-facts strong, .deck-comment-facts span { display: block; }
.deck-comment-facts strong { font-size: 19px; }
.deck-comment-facts span { margin-top: 2px; color: #667085; font-size: 10px; }
.deck-rhythm-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); flex: 1; align-items: center; gap: 48px; margin-top: 20px; }
.deck-rhythm-grid h3 { margin: 0 0 18px; font-size: 13px; }
.deck-worktime > div, .deck-response > div { display: grid; grid-template-columns: 54px minmax(0, 1fr) 54px; align-items: center; gap: 10px; min-height: 42px; }
.deck-worktime span, .deck-response span { color: #667085; font-size: 11px; }
.deck-worktime i, .deck-response > div::before { height: 14px; background: #edf0f3; }
.deck-worktime b { display: block; height: 100%; background: #2f8f83; }
.deck-worktime strong, .deck-response strong { text-align: right; font-size: 13px; }
.deck-worktime p, .deck-response p { margin: 16px 0 0; color: #667085; font-size: 11px; line-height: 1.6; }
.deck-response > div { position: relative; grid-template-columns: minmax(0, 1fr) 54px 70px; }
.deck-response > div::before { position: absolute; z-index: 0; top: 50%; right: 144px; left: 0; transform: translateY(-50%); content: ""; }
.deck-response i { z-index: 1; height: 14px; background: #4e79a7; }
.deck-response strong, .deck-response span { z-index: 1; }
.deck-link-footer { display: flex; justify-content: flex-end; gap: 8px; border-top: 1px solid var(--line); padding-top: 14px; }
.deck-link-footer a:first-child { background: #f1f4f7; color: #344054 !important; }
.deck-coverage { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); margin-top: 26px; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.deck-coverage div { border-right: 1px solid var(--line); padding: 18px 20px; }
.deck-coverage div:first-child { padding-left: 0; }
.deck-coverage div:last-child { border-right: 0; }
.deck-coverage strong, .deck-coverage span { display: block; }
.deck-coverage strong { font-size: 25px; }
.deck-coverage span { margin-top: 3px; color: #667085; font-size: 11px; }
.deck-search { display: grid; width: 100%; grid-template-columns: 22px minmax(0, 1fr) auto; align-items: center; gap: 10px; margin-top: 28px; border: 1px solid #cfd6df; border-radius: 6px; background: #fbfcfe; color: inherit; padding: 10px 12px; font: inherit; text-align: left; transition: border-color 150ms ease, background 150ms ease; }
.deck-search:hover { border-color: #98a2b3; background: #f4f7fa; }
.deck-search svg { color: #667085; }
.deck-search span, .deck-search strong, .deck-search small { display: block; }
.deck-search strong { color: #17212f; font-size: 12px; }
.deck-search small { margin-top: 2px; color: #667085; font-size: 10px; }
.deck-search b { border-radius: 4px; background: #17212f; color: #fff; padding: 8px 14px; font-size: 11px; text-align: center; }
.deck-suggestions { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 12px; }
.deck-suggestions a { border: 1px solid #d7dee7; border-radius: 5px; background: #fff; padding: 7px 10px; font-size: 11px; font-weight: 700; }
.deck-explore-questions { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); margin-top: auto; border-top: 1px solid var(--line); }
.deck-explore-questions a { border-right: 1px solid var(--line); padding: 16px 20px 0; }
.deck-explore-questions a:first-child { padding-left: 0; }
.deck-explore-questions a:last-child { border-right: 0; padding-right: 0; }
.deck-explore-questions span, .deck-explore-questions strong { display: block; }
.deck-explore-questions span { color: var(--accent); font-size: 10px; font-weight: 700; }
.deck-explore-questions strong { margin-top: 5px; font-size: 12px; line-height: 1.45; }
.deck-dots { display: flex; justify-content: center; gap: 4px; margin-top: 10px; }
.deck-dots button { display: grid; width: 36px; height: 32px; place-items: center; border: 0; border-radius: 5px; background: transparent; color: #98a2b3; padding: 0; font-size: 11px; }
.deck-dots button:hover { background: #edf0f3; }
.deck-dots button.active { background: #17212f; color: #fff; }

@media (max-width: 680px) {
  .deck-fullscreen { display: none; }
  .deck-stage { height: auto; min-height: 0; overflow: hidden; padding: 32px 17px 36px; }
  .deck-stage:fullscreen { height: auto; overflow-y: auto; padding: 38px 18px; }
  .deck-page-number { top: 12px; right: 14px; }
  .deck-heading h2 { font-size: 23px; }
  .deck-heading p { font-size: 13px; }
  .deck-cover { display: block; }
  .deck-cover-copy h2 { font-size: 38px; }
  .deck-cover-copy p { font-size: 16px; }
  .deck-purpose { margin-top: 24px; }
  .deck-purpose p { padding: 13px 0; }
  .deck-cover-metrics { margin-top: 22px; }
  .deck-cover-metrics div { padding: 13px 8px 0; }
  .deck-cover-metrics strong { font-size: 20px; }
  .deck-community-body, .deck-shift-columns, .deck-rhythm-grid { grid-template-columns: 1fr; gap: 22px; }
  .deck-community-body { margin-top: 20px; }
  .deck-invite-event { padding: 18px; }
  .deck-fact-row { grid-template-columns: auto 1fr; }
  .deck-fact-row p { grid-column: 1 / -1; text-align: left; }
  .deck-shift-columns { align-items: start; }
  .deck-shift > div { padding: 12px 0; }
  .deck-topic-footer { align-items: flex-start; flex-direction: column; }
  .deck-topic-footer a { margin-left: 0; }
  .deck-subscription-evidence { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
  .deck-subscription-evidence > span, .deck-subscription-evidence small { grid-column: 1 / -1; }
  .deck-subscription-evidence div { align-items: flex-start; flex-direction: column; gap: 3px; }
  .deck-ai-body { grid-template-columns: 1fr; gap: 8px; margin-top: 20px; }
  .deck-ai-timeline { display: grid; height: auto; gap: 0; margin: 20px 0 0 6px; border-left: 2px solid #cfd6df; padding-left: 20px; }
  .deck-timeline-line { display: none; }
  .deck-ai-point, .deck-ai-point.end { position: relative; top: auto; left: auto !important; min-width: 0; transform: none; padding: 0 0 16px; text-align: left; }
  .deck-ai-point::before, .deck-ai-point.end::before { position: absolute; top: 4px; left: -27px; width: 11px; height: 11px; margin: 0; }
  .deck-ai-keywords { grid-template-columns: repeat(3, minmax(0, 1fr)); margin-top: 5px; }
  .deck-ai-keywords > span { grid-column: 1 / -1; }
  .deck-ai-keywords a { padding: 10px; }
  .deck-ai-keywords strong { font-size: 16px; }
  .deck-node-bars { margin-top: 20px; }
  .deck-node-bars a { grid-template-columns: 20px 76px minmax(0, 1fr) 62px; gap: 7px; }
  .deck-node-bars small { display: none; }
  .deck-node-footer { grid-template-columns: auto minmax(0, 1fr); }
  .deck-node-footer a { grid-column: 1 / -1; justify-self: start; }
  .deck-value-grid { grid-template-columns: 1fr; }
  .deck-value-grid > a, .deck-value-grid > a:last-child { border-right: 0; border-bottom: 1px solid var(--line); padding: 15px 0; }
  .deck-comment-facts div { padding: 12px 8px 0; }
  .deck-comment-facts strong { font-size: 16px; }
  .deck-rhythm-grid { align-items: start; }
  .deck-link-footer { justify-content: flex-start; }
  .deck-coverage { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .deck-coverage div, .deck-coverage div:first-child, .deck-coverage div:last-child { border-right: 0; border-bottom: 1px solid var(--line); padding: 13px 8px; }
  .deck-coverage div:nth-child(odd) { border-right: 1px solid var(--line); padding-left: 0; }
  .deck-coverage div:nth-child(even) { padding-right: 0; }
  .deck-coverage div:nth-last-child(-n+2) { border-bottom: 0; }
  .deck-search { grid-template-columns: 20px minmax(0, 1fr); }
  .deck-search b { grid-column: 1 / -1; text-align: center; }
  .deck-explore-questions { grid-template-columns: 1fr; margin-top: 22px; }
  .deck-explore-questions a, .deck-explore-questions a:first-child, .deck-explore-questions a:last-child { border-right: 0; border-bottom: 1px solid var(--line); padding: 12px 0; }
  .deck-explore-questions a:last-child { border-bottom: 0; }
  .deck-dots { justify-content: flex-start; overflow-x: auto; }
  .deck-dots button { width: 40px; height: 40px; flex: 0 0 40px; }
}
</style>
