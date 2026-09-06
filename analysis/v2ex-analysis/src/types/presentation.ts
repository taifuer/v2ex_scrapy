export type PresentationMetric = { value: string; label: string; detail?: string }

export type PresentationPost = {
  id: number
  title: string
  node: string
  date: string
  clicks: number | null
  favorites: number | null
  thanks: number | null
  replies: number | null
  url: string
  badge: string
  selection: string
  note: string
  excerpt?: string
  evidence?: string[]
  rank?: number
  ranking_metric?: "favorites" | "thanks"
}

export type PresentationSlide = {
  id: string
  type: "cover" | "facts" | "chart" | "timeline" | "posts" | "conclusion" | "summary" | "explore"
  chapter: string
  eyebrow: string
  title: string
  summary: string
  note?: string
  chart?: string
  panels?: { title: string; detail: string; chart: string }[]
  panel_layout?: "comparison"
  metrics?: PresentationMetric[]
  posts?: PresentationPost[]
  post_layout?: "strip"
  comments?: { id: number; topic_id: number; username: string; date: string; text: string; thanks: number | null; url: string; note: string; label?: string; topic_title?: string }[]
  definitions?: { title: string; text: string }[]
  findings?: { title: string; text: string }[]
  milestones?: { period: string; title: string; items: { label: string; count: number }[]; text?: string }[]
  takeaways?: { number: string; title: string; text: string; value?: string; href: string; link: string; chart?: string }[]
}
