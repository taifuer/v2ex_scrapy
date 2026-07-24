export type TabId = "overview" | "content" | "community" | "engagement" | "observations"
export type ContentView = "topics" | "topic-detail" | "nodes" | "node-detail" | "lifecycle"
export type OverviewView = "trend" | "month" | "year"
export type CommunityView = "trends" | "member-detail"
export type Grain = "month" | "year"
export type ValueMode = "count" | "share"
export type MemberRankingMetric = "topics" | "comments" | "thanks"
export type PaginationItem = number | "gap-start" | "gap-end"

export type PeriodMetric = {
  period: string
  topic_count: number
  comment_count: number
  member_count: number
  reply_count: number
  zero_reply_count: number
  click_sum: number
  favorite_sum: number
  thank_sum: number
}

export type RepresentativePost = {
  id: number
  period: string
  title: string
  node: string
  author?: string
  tags: string[]
  create_at: number
  clicks: number
  reply_count: number
  favorite_count: number
  thank_count: number
  votes?: number
  score: number
}

export type SearchOption = {
  value: string
  label: string
  meta?: string
}

export type RankedItem = {
  key: string | number
  label: string
  value: string
  href?: string
  action?: string
  active?: boolean
}

export type RankedColumn = {
  key: string
  title: string
  items: RankedItem[]
}
