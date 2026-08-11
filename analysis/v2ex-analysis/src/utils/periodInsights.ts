type RankingItem = { name: string; value: number }
type RankingSummary = { tags?: RankingItem[]; nodes?: RankingItem[] }
type MetricSnapshot = { value: number; yearDelta: number | null }

export type PeriodInsight = {
  title: string
  description: string
  tone: "rise" | "fall" | "new" | "neutral"
  action?: { type: "tag" | "node"; value: string }
}

type InsightOptions = {
  metrics: Record<string, MetricSnapshot>
  currentSummary: RankingSummary
  baselineSummary: RankingSummary
  currentTopics: number
  baselineTopics: number
  periodType: "month" | "year"
  comparableRankings: boolean
  nodeLabel: (node: string) => string
}

function formatNumber(value: number) {
  return Number(value || 0).toLocaleString("zh-CN")
}

function rankedShareMover(
  currentItems: RankingItem[],
  baselineItems: RankingItem[],
  currentTotal: number,
  baselineTotal: number,
  minimumCurrent: number,
  minimumBaseline: number,
  minimumPointChange: number,
) {
  if (!currentTotal || !baselineTotal) return null
  const baseline = new Map(baselineItems.map(item => [item.name, Number(item.value || 0)]))
  return currentItems
    .map(item => {
      const currentValue = Number(item.value || 0)
      const baselineValue = Number(baseline.get(item.name) || 0)
      const currentShare = (currentValue / currentTotal) * 100
      const baselineShare = (baselineValue / baselineTotal) * 100
      return { ...item, currentValue, baselineValue, currentShare, baselineShare, pointChange: currentShare - baselineShare }
    })
    .filter(item => (
      item.currentValue >= minimumCurrent
      && item.baselineValue >= minimumBaseline
      && Math.abs(item.pointChange) >= minimumPointChange
    ))
    .sort((a, b) => Math.abs(b.pointChange) - Math.abs(a.pointChange))[0] || null
}

export function buildPeriodInsights({
  metrics,
  currentSummary,
  baselineSummary,
  currentTopics,
  baselineTopics,
  periodType,
  comparableRankings,
  nodeLabel,
}: InsightOptions): PeriodInsight[] {
  const insights: PeriodInsight[] = []
  const metricLabels: Record<string, string> = {
    topics: "帖子数", comments: "评论数", members: "新增成员", authors: "发帖用户", commenters: "评论用户",
  }
  const strongestMetric = Object.entries(metricLabels)
    .map(([key, label]) => ({ label, delta: metrics[key]?.yearDelta, value: metrics[key]?.value || 0 }))
    .filter(item => item.delta !== null && item.delta !== undefined && Math.abs(item.delta) >= 15)
    .sort((a, b) => Math.abs(Number(b.delta)) - Math.abs(Number(a.delta)))[0]
  if (strongestMetric) {
    const rising = Number(strongestMetric.delta) > 0
    insights.push({
      title: `${strongestMetric.label}同比${rising ? "上升" : "下降"}`,
      description: `${periodType === "month" ? "当月" : "本年同期"}${strongestMetric.label}为 ${formatNumber(strongestMetric.value)}，同比${rising ? "+" : ""}${Number(strongestMetric.delta).toFixed(1)}%。`,
      tone: rising ? "rise" : "fall",
    })
  }

  const currentTags = currentSummary.tags || []
  const currentNodes = currentSummary.nodes || []
  if (!comparableRankings) {
    if (currentTags[0]) insights.push({
      title: `${currentTags[0].name} 是当期首要话题`,
      description: `涉及 ${formatNumber(currentTags[0].value)} 个帖子，占当期帖子数的 ${currentTopics ? (currentTags[0].value / currentTopics * 100).toFixed(1) : "0.0"}%。`,
      tone: "neutral",
      action: { type: "tag", value: currentTags[0].name },
    })
    if (currentNodes[0]) insights.push({
      title: `${nodeLabel(currentNodes[0].name)} 是最活跃节点`,
      description: `当期发布 ${formatNumber(currentNodes[0].value)} 个帖子，占当期帖子数的 ${currentTopics ? (currentNodes[0].value / currentTopics * 100).toFixed(1) : "0.0"}%。`,
      tone: "neutral",
      action: { type: "node", value: currentNodes[0].name },
    })
    return insights.slice(0, 4)
  }

  const baselineTags = baselineSummary.tags || []
  const baselineNodes = baselineSummary.nodes || []
  const baselineTopNames = new Set(baselineTags.slice(0, 20).map(item => item.name))
  const entrantThreshold = periodType === "month" ? 50 : 300
  const entrant = currentTags.slice(0, 10).find(item => Number(item.value) >= entrantThreshold && !baselineTopNames.has(item.name))
  if (entrant) insights.push({
    title: `${entrant.name} 进入热门话题前十`,
    description: `涉及 ${formatNumber(entrant.value)} 个帖子，上年同期未进入前 20。`,
    tone: "new",
    action: { type: "tag", value: entrant.name },
  })

  const topicMover = rankedShareMover(
    currentTags, baselineTags, currentTopics, baselineTopics,
    periodType === "month" ? 50 : 300, periodType === "month" ? 30 : 200, 0.12,
  )
  if (topicMover) {
    const rising = topicMover.pointChange > 0
    insights.push({
      title: `${topicMover.name} 话题占比${rising ? "上升" : "下降"}`,
      description: `相关帖子占比由 ${topicMover.baselineShare.toFixed(1)}% 变为 ${topicMover.currentShare.toFixed(1)}%，同比${rising ? "+" : ""}${topicMover.pointChange.toFixed(1)} 个百分点。`,
      tone: rising ? "rise" : "fall",
      action: { type: "tag", value: topicMover.name },
    })
  }

  const nodeMover = rankedShareMover(
    currentNodes, baselineNodes, currentTopics, baselineTopics,
    periodType === "month" ? 100 : 500, periodType === "month" ? 80 : 350, 0.25,
  )
  if (nodeMover) {
    const rising = nodeMover.pointChange > 0
    insights.push({
      title: `${nodeLabel(nodeMover.name)}节点占比${rising ? "上升" : "下降"}`,
      description: `帖子占比由 ${nodeMover.baselineShare.toFixed(1)}% 变为 ${nodeMover.currentShare.toFixed(1)}%，同比${rising ? "+" : ""}${nodeMover.pointChange.toFixed(1)} 个百分点。`,
      tone: rising ? "rise" : "fall",
      action: { type: "node", value: nodeMover.name },
    })
  }
  return insights.slice(0, 4)
}
