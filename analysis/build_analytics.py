import argparse
import hashlib
import heapq
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = ROOT / "analysis"
SOURCE_DB = ROOT / "v2ex.sqlite"
ANALYTICS_DB = ANALYSIS_DIR / "analytics.sqlite"
PUBLIC_DIR = ANALYSIS_DIR / "v2ex-analysis" / "public"
MIN_VALID_CREATE_AT = 1262304000
LOCAL_TIMEZONE = timezone(timedelta(hours=8))
TOP_TAG_LIMIT = 500
REPRESENTATIVE_POSTS_PER_MONTH = 30
INTERACTION_POST_RANKING_LIMIT = 200
COMMENT_RANKING_LIMIT = 500
FIRST_REPLY_BUCKETS = ("10m", "1h", "6h", "24h", "3d", "7d", "none")
COMMENT_AGE_BUCKETS = ("10m", "1h", "6h", "24h", "3d", "7d")
EXCLUDED_THANK_USERS = frozenset({"usdc"})
EXCLUDED_REPRESENTATIVE_NODES = frozenset({"promotions"})
MEMBER_RANKING_LIMIT = 30
MEMBER_PROFILE_LIMIT = 2500
MEMBER_PROFILE_DEFAULT_MONTHS = 60
MEMBER_PROFILE_MIN_ANNUAL_APPEARANCES = 3
MEMBER_PROFILE_BUCKET_COUNT = 16
MEMBER_PROFILE_LIST_LIMIT = 15
MEMBER_PROFILE_POST_LIMIT = 8
TAG_DETAIL_BUCKET_COUNT = 16
TAG_DETAIL_LIST_LIMIT = 15
ANALYTICS_SCHEMA_VERSION = 5


class CommentTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        if tag in {"br", "div", "p", "li"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str):
        if tag in {"div", "p", "li"}:
            self.parts.append("\n")

    def handle_data(self, data: str):
        self.parts.append(data)

    def text(self) -> str:
        return "\n".join(
            line for line in (" ".join(part.split()) for part in "".join(self.parts).splitlines())
            if line
        )


def comment_text(content: str | None) -> str:
    parser = CommentTextParser()
    parser.feed(content or "")
    parser.close()
    return parser.text()


def load_json(path: Path):
    with path.open(encoding="utf-8") as fp:
        return json.load(fp)


def write_json(path: Path, payload):
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, separators=(",", ":"))
    temp_path.replace(path)


def source_fingerprint() -> dict[str, int]:
    stat = SOURCE_DB.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def write_manifest(component: str, full_build: bool = False):
    manifest_path = PUBLIC_DIR / "dynamic-manifest.json"
    manifest = load_json(manifest_path) if manifest_path.exists() else {
        "schema_version": ANALYTICS_SCHEMA_VERSION,
        "components": {},
    }
    generated_at = datetime.now(LOCAL_TIMEZONE).isoformat(timespec="seconds")
    manifest["schema_version"] = ANALYTICS_SCHEMA_VERSION
    manifest["generated_at"] = generated_at
    manifest["components"][component] = generated_at
    if full_build:
        manifest["full_build_source"] = source_fingerprint()
    manifest["files"] = {
        path.name: path.stat().st_size
        for path in sorted(PUBLIC_DIR.glob("dynamic-*.json"))
        if path.name != manifest_path.name
    }
    write_json(manifest_path, manifest)


def source_unchanged_since_full_build() -> bool:
    manifest_path = PUBLIC_DIR / "dynamic-manifest.json"
    if not manifest_path.exists():
        return False
    manifest = load_json(manifest_path)
    return (
        manifest.get("schema_version") == ANALYTICS_SCHEMA_VERSION
        and manifest.get("full_build_source") == source_fingerprint()
    )


def synonym_map() -> dict[str, str]:
    result: dict[str, str] = {}
    for canonical, variants in load_json(ANALYSIS_DIR / "tag_synonyms.json").items():
        result[canonical.casefold()] = canonical
        for variant in variants:
            result[str(variant).casefold()] = canonical
    return result


def canonical_tag(tag: str, synonyms: dict[str, str]) -> str:
    value = tag.strip()
    return synonyms.get(value.casefold(), value)


def normalize_tags(raw_tags, synonyms: dict[str, str], stopwords: set[str]) -> set[str]:
    normalized = {
        canonical_tag(str(tag), synonyms) for tag in raw_tags if str(tag).strip()
    }
    return {tag for tag in normalized if tag.casefold() not in stopwords}


def month_for(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, LOCAL_TIMEZONE).strftime("%Y-%m")


def first_reply_bucket(delay: int | None) -> str:
    if delay is None:
        return "none"
    for label, upper_bound in (("10m", 600), ("1h", 3600), ("6h", 21600),
                               ("24h", 86400), ("3d", 259200), ("7d", 604800)):
        if delay < upper_bound:
            return label
    return "none"


def comment_age_bucket(delay: int) -> str | None:
    for label, upper_bound in (("10m", 600), ("1h", 3600), ("6h", 21600),
                               ("24h", 86400), ("3d", 259200), ("7d", 604800)):
        if delay < upper_bound:
            return label
    return None


def matches_group(title: str, node: str, tags: set[str], group: dict) -> bool:
    title_folded = title.casefold()
    node_folded = node.casefold()
    tag_values = {tag.casefold() for tag in tags}
    if node_folded in {item.casefold() for item in group.get("nodes", [])}:
        return True
    return any(
        keyword.casefold() in title_folded or keyword.casefold() in tag_values
        for keyword in group.get("keywords", [])
    )


def engagement_score(row: sqlite3.Row) -> float:
    return (
        max(0, row["reply_count"])
        + max(0, row["favorite_count"]) * 3
        + max(0, row["thank_count"]) * 5
        + max(0, row["votes"]) * 2
        + math.log1p(max(0, row["clicks"]))
    )


def tag_detail_bucket(tag: str) -> str:
    return hashlib.sha1(tag.encode("utf-8")).hexdigest()[0]


def member_profile_bucket(username: str) -> str:
    return hashlib.sha1(username.encode("utf-8")).hexdigest()[0]


def percent_change(current: float, previous: float) -> float:
    return ((current - previous) / previous * 100) if previous else 0.0


def build_observation_output(
    overview: dict,
    topics: dict,
    nodes: dict,
    lifecycle: dict,
) -> dict:
    complete = [
        row for row in overview["periods"]
        if row["period"] <= overview["metadata"]["default_end_period"]
    ]
    current = complete[-60:]
    previous = complete[-120:-60]
    current_periods = {row["period"] for row in current}
    current_start, current_end = current[0]["period"], current[-1]["period"]
    previous_start, previous_end = previous[0]["period"], previous[-1]["period"]

    def total(rows: list[dict], key: str) -> int:
        return sum(int(row[key]) for row in rows)

    current_topics = total(current, "topic_count")
    previous_topics = total(previous, "topic_count")
    current_comments = total(current, "comment_count")
    previous_comments = total(previous, "comment_count")
    topic_change = percent_change(current_topics, previous_topics)
    comment_change = percent_change(current_comments, previous_comments)
    current_density = current_comments / current_topics
    previous_density = previous_comments / previous_topics

    invitation_period = "2024-05"
    invitation_index = next(
        index for index, row in enumerate(complete) if row["period"] == invitation_period
    )
    invitation_before = complete[invitation_index - 12:invitation_index]
    invitation_after = complete[invitation_index:invitation_index + 12]

    def average(rows: list[dict], key: str) -> float:
        return total(rows, key) / len(rows)

    members_before = average(invitation_before, "member_count")
    members_after = average(invitation_after, "member_count")
    topics_after_change = percent_change(
        average(invitation_after, "topic_count"), average(invitation_before, "topic_count")
    )
    comments_after_change = percent_change(
        average(invitation_after, "comment_count"), average(invitation_before, "comment_count")
    )

    recent_12 = complete[-12:]
    prior_12 = complete[-24:-12]
    recent_periods = {row["period"] for row in recent_12}
    prior_periods = {row["period"] for row in prior_12}

    def tag_count(tag: str, periods: set[str]) -> int:
        return sum(
            int(row[2]) for row in topics["rows"]
            if row[0] in periods and row[1] == tag
        )

    recent_topic_total = total(recent_12, "topic_count")
    prior_topic_total = total(prior_12, "topic_count")
    ai_recent = tag_count("AI", recent_periods)
    ai_prior = tag_count("AI", prior_periods)
    ai_recent_share = ai_recent / recent_topic_total * 100
    ai_prior_share = ai_prior / prior_topic_total * 100
    claude_delta = (
        tag_count("Claude", recent_periods) / recent_topic_total
        - tag_count("Claude", prior_periods) / prior_topic_total
    ) * 100
    model_delta = (
        tag_count("模型", recent_periods) / recent_topic_total
        - tag_count("模型", prior_periods) / prior_topic_total
    ) * 100

    activity_rows = [row for row in overview["activity"] if row[0] in current_periods]
    work_topics = sum(row[3] for row in activity_rows if row[1] < 5 and 9 <= row[2] < 18)
    work_comments = sum(row[4] for row in activity_rows if row[1] < 5 and 9 <= row[2] < 18)
    activity_topics = sum(row[3] for row in activity_rows)
    activity_comments = sum(row[4] for row in activity_rows)
    topic_slots = defaultdict(int)
    comment_slots = defaultdict(int)
    for row in activity_rows:
        topic_slots[(row[1], row[2])] += row[3]
        comment_slots[(row[1], row[2])] += row[4]
    weekday_names = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
    topic_peak = max(topic_slots, key=topic_slots.get)
    comment_peak = max(comment_slots, key=comment_slots.get)

    first_cutoff = lifecycle["metadata"]["first_reply_complete_through"]
    tail_cutoff = lifecycle["metadata"]["long_tail_complete_through"]
    first_rows = [
        row for row in lifecycle["first_reply_rows"]
        if current_start <= row[0] <= min(current_end, first_cutoff)
    ]
    first_counts = defaultdict(int)
    for row in first_rows:
        first_counts[row[1]] += row[2]
    eligible_topics = sum(first_counts.values())
    within_1h = first_counts["10m"] + first_counts["1h"]
    within_24h = within_1h + first_counts["6h"] + first_counts["24h"]
    response_rate = (eligible_topics - first_counts["none"]) / eligible_topics * 100
    tail_rows = [
        row for row in lifecycle["long_tail_rows"]
        if current_start <= row[0] <= min(current_end, tail_cutoff)
    ]
    comments_30d = sum(row[1] for row in tail_rows)
    comments_after_7d = sum(row[3] for row in tail_rows)
    after_7d_share = comments_after_7d / comments_30d * 100

    node_totals = defaultdict(lambda: [0, 0])
    for row in nodes["rows"]:
        if row[0] not in current_periods:
            continue
        node_totals[row[1]][0] += row[2]
        node_totals[row[1]][1] += row[3]
    top_nodes = sorted(node_totals, key=lambda node: node_totals[node][0], reverse=True)
    top_three_share = sum(node_totals[node][0] for node in top_nodes[:3]) / current_topics * 100

    def node_intensity(node: str) -> float:
        return node_totals[node][1] / node_totals[node][0]

    def link(tab: str, label: str, view: str | None = None, **params) -> dict:
        query = {"tab": tab, "from": current_start, "to": current_end, **params}
        if view:
            query["view"] = view
        href = "?" + "&".join(f"{key}={value}" for key, value in query.items())
        return {"label": label, "href": href}

    observations = [
        {
            "id": "discussion-density",
            "category": "规模与参与",
            "title": "发帖减少，但讨论没有等比例降温",
            "summary": (
                f"近 5 年主题数较此前 5 年下降 {abs(topic_change):.1f}%，评论数只下降 "
                f"{abs(comment_change):.1f}%；平均每个主题的评论从 {previous_density:.1f} 条升至 "
                f"{current_density:.1f} 条。"
            ),
            "interpretation": "社区产出的主题更少，但留下来的主题承载了更密集的讨论。它更接近参与结构变化，而不是讨论活动同步收缩。",
            "evidence": "数据事实",
            "confidence": "高",
            "stats": [
                {"value": f"{current_topics:,}", "label": "近 5 年主题"},
                {"value": f"{current_comments:,}", "label": "近 5 年评论"},
                {"value": f"{current_density:.1f}", "label": "评论 / 主题"},
            ],
            "links": [link("overview", "查看规模变化")],
        },
        {
            "id": "invitation-system",
            "category": "成员变化",
            "title": "邀请码制度构成清晰的成员增长断点",
            "summary": (
                f"邀请码实施前 12 个月平均每月新增 {members_before:,.0f} 人，之后 12 个月为 "
                f"{members_after:,.0f} 人，下降 {abs(percent_change(members_after, members_before)):.1f}%。"
            ),
            "interpretation": (
                f"同期主题和评论月均值仅分别变化 {topics_after_change:.1f}% 和 {comments_after_change:.1f}%。"
                "新增成员断崖式减少与 2024-05-06 生效的邀请码机制时间高度吻合，也说明存量成员仍维持了大部分社区活动；"
                "观察数据支持强关联，但不能证明这是唯一原因。"
            ),
            "evidence": "事实 + 背景推断",
            "confidence": "较高",
            "stats": [
                {"value": f"{members_before:,.0f}", "label": "实施前月均新增"},
                {"value": f"{members_after:,.0f}", "label": "实施后月均新增"},
                {"value": f"{percent_change(members_after, members_before):.1f}%", "label": "新增变化"},
            ],
            "source": {
                "label": "V2EX：20240505 - 邀请码系统",
                "url": "https://www.v2ex.com/t/1037849",
                "date": "2024-05-06 生效",
            },
            "links": [
                {
                    "label": "查看成员变化",
                    "href": "?tab=community&from=2023-05&to=2025-04",
                }
            ],
        },
        {
            "id": "ai-shift",
            "category": "话题迁移",
            "title": "AI 已从技术支线变成显著的社区主线",
            "summary": (
                f"最近 12 个完整月，AI 标签覆盖 {ai_recent:,} 个主题，占全部主题 {ai_recent_share:.2f}%；"
                f"此前 12 个月为 {ai_prior_share:.2f}%，份额增加 {ai_recent_share - ai_prior_share:.2f} 个百分点。"
            ),
            "interpretation": (
                f"增长并非只来自一个标签：Claude 和“模型”的主题份额也分别增加 {claude_delta:.2f} 和 "
                f"{model_delta:.2f} 个百分点，讨论正从泛化的 AI 概念转向模型、工具和具体产品。"
            ),
            "evidence": "数据事实",
            "confidence": "高",
            "stats": [
                {"value": f"{ai_recent:,}", "label": "近 12 月 AI 主题"},
                {"value": f"{ai_recent_share:.2f}%", "label": "当前主题份额"},
                {"value": f"+{ai_recent_share - ai_prior_share:.2f}pp", "label": "份额变化"},
            ],
            "links": [link("content", "查看 AI 话题", tag="AI")],
        },
        {
            "id": "workday-community",
            "category": "活跃节律",
            "title": "V2EX 的社区节律与工作日高度重合",
            "summary": (
                f"近 5 年有 {work_topics / activity_topics * 100:.1f}% 的主题和 "
                f"{work_comments / activity_comments * 100:.1f}% 的评论发生在工作日 9:00–17:00。"
            ),
            "interpretation": (
                f"发帖峰值位于{weekday_names[topic_peak[0]]} {topic_peak[1]} 时，评论峰值位于"
                f"{weekday_names[comment_peak[0]]} {comment_peak[1]} 时。社区更像嵌入工作与技术协作场景的信息网络，而不是只在晚间活跃的休闲论坛。"
            ),
            "evidence": "数据事实",
            "confidence": "高",
            "stats": [
                {"value": f"{work_topics / activity_topics * 100:.1f}%", "label": "工作时段主题"},
                {"value": f"{work_comments / activity_comments * 100:.1f}%", "label": "工作时段评论"},
                {"value": f"{weekday_names[comment_peak[0]]} {comment_peak[1]} 时", "label": "评论峰值"},
            ],
            "links": [link("overview", "查看活跃时段")],
        },
        {
            "id": "short-discussion-window",
            "category": "讨论生命周期",
            "title": "回应很快，但多数讨论的有效窗口很短",
            "summary": (
                f"具备完整观察窗口的主题中，{within_1h / eligible_topics * 100:.1f}% 在 1 小时内获得首条回复，"
                f"{within_24h / eligible_topics * 100:.1f}% 在 24 小时内获得回复。"
            ),
            "interpretation": (
                f"7 日内总体回复覆盖率为 {response_rate:.1f}%，但发布 7 天后产生的评论只占 30 日评论的 "
                f"{after_7d_share:.1f}%。V2EX 擅长快速反馈，长期持续讨论则属于少数。"
            ),
            "evidence": "数据事实",
            "confidence": "高",
            "stats": [
                {"value": f"{within_1h / eligible_topics * 100:.1f}%", "label": "1 小时内首回"},
                {"value": f"{within_24h / eligible_topics * 100:.1f}%", "label": "24 小时内首回"},
                {"value": f"{after_7d_share:.1f}%", "label": "7 天后评论"},
            ],
            "links": [link("content", "查看生命周期", view="lifecycle")],
        },
        {
            "id": "node-modes",
            "category": "节点结构",
            "title": "高流量节点承担的是不同类型的社区功能",
            "summary": (
                f"问与答、二手交易和程序员三个节点贡献了近 5 年 {top_three_share:.1f}% 的主题，"
                "但发帖规模并不等于讨论深度。"
            ),
            "interpretation": (
                f"二手交易平均每主题 {node_intensity('all4all'):.1f} 条回复，程序员为 "
                f"{node_intensity('programmer'):.1f} 条，生活节点达到 {node_intensity('life'):.1f} 条。"
                "交易节点偏向高频信息撮合，技术与生活议题更容易形成长讨论。"
            ),
            "evidence": "数据事实 + 结构解读",
            "confidence": "较高",
            "stats": [
                {"value": f"{top_three_share:.1f}%", "label": "前三节点主题份额"},
                {"value": f"{node_intensity('all4all'):.1f}", "label": "二手交易回复 / 主题"},
                {"value": f"{node_intensity('programmer'):.1f}", "label": "程序员回复 / 主题"},
            ],
            "links": [link("content", "查看节点分布", view="nodes")],
        },
    ]

    return {
        "metadata": {
            "generated_at": datetime.now(LOCAL_TIMEZONE).isoformat(timespec="seconds"),
            "generated_by": "Codex 离线数据解读",
            "analysis_start": current_start,
            "analysis_end": current_end,
            "comparison_start": previous_start,
            "comparison_end": previous_end,
            "recent_start": recent_12[0]["period"],
            "recent_end": recent_12[-1]["period"],
        },
        "headline": {
            "title": "社区在收缩中保持讨论密度，AI 成为最明显的新变量",
            "summary": (
                "过去五年的主题、新增成员均较此前周期减少，但评论下降更慢；邀请码制度改变了新成员进入速度，"
                "存量成员仍维持主要讨论活动。与此同时，AI 及模型相关话题快速进入社区主线。"
            ),
            "metrics": [
                {"value": f"{topic_change:.1f}%", "label": "近 5 年主题变化"},
                {"value": f"{current_density:.1f}", "label": "评论 / 主题"},
                {"value": f"{percent_change(members_after, members_before):.1f}%", "label": "邀请码后新增变化"},
                {"value": f"{ai_recent_share:.2f}%", "label": "AI 近 12 月份额"},
            ],
        },
        "observations": observations,
        "notes": [
            "点评基于聚合数据离线生成，默认使用最近 60 个完整月份；变化不自动代表因果关系。",
            "邀请码时间线引用 V2EX 官方主题；成员注册数据可能受到档案抓取完整度影响。",
            "收藏、感谢、点击和投票是抓取时累计快照，不用于判断互动发生时间。",
        ],
    }


def update_observations(write_component: bool = True):
    output = build_observation_output(
        load_json(PUBLIC_DIR / "dynamic-overview.json"),
        load_json(PUBLIC_DIR / "dynamic-topics.json"),
        load_json(PUBLIC_DIR / "dynamic-nodes.json"),
        load_json(PUBLIC_DIR / "dynamic-lifecycle.json"),
    )
    write_json(PUBLIC_DIR / "dynamic-observations.json", output)
    if write_component:
        write_manifest("observations")
    print(f"Updated offline observations: {len(output['observations'])} findings")


def build_member_profile_candidates(
    community: dict,
    limit: int = MEMBER_PROFILE_LIMIT,
    min_annual_appearances: int = MEMBER_PROFILE_MIN_ANNUAL_APPEARANCES,
    default_periods: set[str] | None = None,
) -> list[str]:
    leaders = []
    seen = set()
    for key in ("top_topic_authors", "top_commenters", "top_thanked"):
        for member in community.get(key, []):
            username = member.get("username", "")
            if not username or username.casefold() in EXCLUDED_THANK_USERS or username in seen:
                continue
            seen.add(username)
            leaders.append(username)

    recent_values = defaultdict(int)
    recent_appearances = defaultdict(int)
    years = defaultdict(set)
    annual_values = defaultdict(int)
    for row in community.get("rank_rows", []):
        if not row[4] or str(row[4]).casefold() in EXCLUDED_THANK_USERS:
            continue
        if row[0] == "month" and default_periods and row[1] in default_periods:
            recent_appearances[row[4]] += 1
            recent_values[row[4]] += int(row[5])
            continue
        if row[0] != "year":
            continue
        years[row[4]].add(row[1])
        annual_values[row[4]] += int(row[5])
    recent = sorted(
        (username for username in recent_values if username not in seen),
        key=lambda username: (
            -recent_appearances[username], -recent_values[username], username.casefold()
        ),
    )
    seen.update(recent)
    recurring = sorted(
        (
            username for username, active_years in years.items()
            if len(active_years) >= min_annual_appearances and username not in seen
        ),
        key=lambda username: (-len(years[username]), -annual_values[username], username.casefold()),
    )
    return (leaders + recent + recurring)[:limit]


def update_member_profiles():
    community = load_json(PUBLIC_DIR / "dynamic-community.json")
    overview = load_json(PUBLIC_DIR / "dynamic-overview.json")
    default_end = overview["metadata"]["default_end_period"]
    default_periods = {
        row["period"] for row in overview["periods"] if row["period"] <= default_end
    }
    default_periods = set(sorted(default_periods)[-MEMBER_PROFILE_DEFAULT_MONTHS:])
    candidates = build_member_profile_candidates(community, default_periods=default_periods)
    profiles = {
        username: {
            "periods": defaultdict(lambda: [0, 0, 0, 0]),
            "topic_nodes": defaultdict(int),
            "comment_nodes": defaultdict(int),
            "tags": defaultdict(int),
            "posts": [],
            "registered_at": 0,
        }
        for username in candidates
    }
    if not candidates:
        raise ValueError("member profile candidate set is empty")

    placeholders = ",".join("?" for _ in candidates)
    synonyms = synonym_map()
    tag_stopwords = {
        str(tag).casefold() for tag in load_json(ANALYSIS_DIR / "tag_stopwords.json")
    }
    source = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row

    for row in source.execute(
        f"""
        SELECT id, author, title, node, tag, create_at, clicks, reply_count,
               favorite_count, thank_count, votes
        FROM topic
        WHERE clicks >= 0 AND create_at >= ? AND author IN ({placeholders})
        ORDER BY id
        """,
        (MIN_VALID_CREATE_AT, *candidates),
    ):
        profile = profiles[row["author"]]
        period = month_for(row["create_at"])
        values = profile["periods"][period]
        values[0] += 1
        values[2] += max(0, row["thank_count"])
        node = row["node"] or "未分类"
        profile["topic_nodes"][node] += 1
        try:
            raw_tags = json.loads(row["tag"] or "[]")
        except json.JSONDecodeError:
            raw_tags = []
        normalized_tags = normalize_tags(raw_tags, synonyms, tag_stopwords)
        for tag in normalized_tags:
            profile["tags"][tag] += 1
        score = engagement_score(row)
        post = {
            "id": row["id"], "title": row["title"], "node": node,
            "tags": sorted(normalized_tags), "create_at": row["create_at"],
            "reply_count": row["reply_count"], "favorite_count": row["favorite_count"],
            "thank_count": row["thank_count"], "score": round(score, 3),
        }
        item = (score, row["id"], post)
        heap = profile["posts"]
        if len(heap) < MEMBER_PROFILE_POST_LIMIT:
            heapq.heappush(heap, item)
        elif item > heap[0]:
            heapq.heapreplace(heap, item)

    for row in source.execute(
        f"""
        SELECT c.commenter,
               strftime('%Y-%m', c.create_at, 'unixepoch', '+8 hours') AS period,
               COALESCE(t.node, '未分类') AS node,
               COUNT(*) AS comment_count,
               SUM(MAX(0, c.thank_count)) AS thank_count
        FROM comment c
        JOIN topic t ON t.id = c.topic_id
        WHERE c.create_at >= ? AND c.commenter IN ({placeholders})
        GROUP BY c.commenter, period, node
        """,
        (MIN_VALID_CREATE_AT, *candidates),
    ):
        profile = profiles[row["commenter"]]
        values = profile["periods"][row["period"]]
        values[1] += int(row["comment_count"])
        values[3] += int(row["thank_count"] or 0)
        profile["comment_nodes"][row["node"]] += int(row["comment_count"])

    for row in source.execute(
        f"SELECT username, create_at FROM member WHERE username IN ({placeholders})",
        candidates,
    ):
        profiles[row["username"]]["registered_at"] = max(0, int(row["create_at"] or 0))
    source.close()

    buckets = {
        format(index, "x"): {"profiles": {}}
        for index in range(MEMBER_PROFILE_BUCKET_COUNT)
    }
    index_output = {
        "criteria": {
            "limit": MEMBER_PROFILE_LIMIT,
            "default_months": MEMBER_PROFILE_DEFAULT_MONTHS,
            "default_start_period": min(default_periods),
            "default_end_period": max(default_periods),
            "minimum_annual_appearances": MEMBER_PROFILE_MIN_ANNUAL_APPEARANCES,
            "includes_overall_leaders": True,
            "includes_default_range_top_30": True,
        },
        "members": {},
    }
    for username in candidates:
        profile = profiles[username]
        periods = [
            [period, *values]
            for period, values in sorted(profile["periods"].items())
        ]
        topic_count = sum(row[1] for row in periods)
        comment_count = sum(row[2] for row in periods)
        topic_thanks = sum(row[3] for row in periods)
        comment_thanks = sum(row[4] for row in periods)
        detail = {
            "username": username,
            "registered_at": profile["registered_at"],
            "totals": {
                "topics": topic_count,
                "comments": comment_count,
                "topic_thanks": topic_thanks,
                "comment_thanks": comment_thanks,
            },
            "periods": periods,
            "topic_nodes": sorted(profile["topic_nodes"].items(), key=lambda item: (-item[1], item[0]))[:MEMBER_PROFILE_LIST_LIMIT],
            "comment_nodes": sorted(profile["comment_nodes"].items(), key=lambda item: (-item[1], item[0]))[:MEMBER_PROFILE_LIST_LIMIT],
            "tags": sorted(profile["tags"].items(), key=lambda item: (-item[1], item[0]))[:MEMBER_PROFILE_LIST_LIMIT],
            "posts": [post for _, __, post in sorted(profile["posts"], reverse=True)],
        }
        bucket = member_profile_bucket(username)
        buckets[bucket]["profiles"][username] = detail
        index_output["members"][username] = {
            "bucket": bucket,
            "topics": topic_count,
            "comments": comment_count,
        }

    write_json(PUBLIC_DIR / "dynamic-member-profile-index.json", index_output)
    for bucket, payload in buckets.items():
        write_json(PUBLIC_DIR / f"dynamic-member-profiles-{bucket}.json", payload)
    write_manifest("member_profiles")
    print(f"Updated member profiles: {len(candidates)} members across {len(buckets)} shards")


def update_tag_details():
    topics_path = PUBLIC_DIR / "dynamic-topics.json"
    topics_output = load_json(topics_path)
    tag_totals = {item["tag"]: int(item["total"]) for item in topics_output["tags"]}
    selected_tags = set(tag_totals)
    synonyms = synonym_map()
    tag_stopwords = {
        str(tag).casefold() for tag in load_json(ANALYSIS_DIR / "tag_stopwords.json")
    }
    related = defaultdict(lambda: defaultdict(int))
    nodes = defaultdict(lambda: defaultdict(int))
    authors = defaultdict(lambda: defaultdict(int))

    source = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    for row in source.execute(
        """
        SELECT author, node, tag
        FROM topic
        WHERE clicks >= 0 AND create_at >= ?
        ORDER BY id
        """,
        (MIN_VALID_CREATE_AT,),
    ):
        try:
            raw_tags = json.loads(row["tag"] or "[]")
        except json.JSONDecodeError:
            raw_tags = []
        normalized_tags = normalize_tags(raw_tags, synonyms, tag_stopwords)
        detail_tags = normalized_tags & selected_tags
        if not detail_tags:
            continue
        node = row["node"] or "未分类"
        for tag in detail_tags:
            nodes[tag][node] += 1
            if row["author"]:
                authors[tag][row["author"]] += 1
            for other in detail_tags:
                if other != tag:
                    related[tag][other] += 1
    source.close()

    buckets = {format(index, "x"): {"details": {}} for index in range(TAG_DETAIL_BUCKET_COUNT)}
    index_output = {"tags": {}}
    for tag in sorted(selected_tags):
        bucket = tag_detail_bucket(tag)
        detail = {
            "tag": tag,
            "total": tag_totals[tag],
            "related": sorted(related[tag].items(), key=lambda item: (-item[1], item[0]))[:TAG_DETAIL_LIST_LIMIT],
            "nodes": sorted(nodes[tag].items(), key=lambda item: (-item[1], item[0]))[:TAG_DETAIL_LIST_LIMIT],
            "authors": sorted(authors[tag].items(), key=lambda item: (-item[1], item[0]))[:TAG_DETAIL_LIST_LIMIT],
        }
        buckets[bucket]["details"][tag] = detail
        index_output["tags"][tag] = {"bucket": bucket, "total": tag_totals[tag]}

    write_json(PUBLIC_DIR / "dynamic-tag-detail-index.json", index_output)
    for bucket, payload in buckets.items():
        write_json(PUBLIC_DIR / f"dynamic-tag-details-{bucket}.json", payload)
    write_manifest("tag_details")
    print(f"Updated tag details: {len(selected_tags)} tags across {len(buckets)} shards")


def build_member_rank_rows(source: sqlite3.Connection, limit: int = MEMBER_RANKING_LIMIT) -> list[list]:
    source.execute("PRAGMA temp_store = FILE")
    source.executescript(
        f"""
        DROP TABLE IF EXISTS temp.member_topic_period;
        DROP TABLE IF EXISTS temp.member_comment_period;
        CREATE TEMP TABLE member_topic_period AS
        SELECT strftime('%Y-%m', create_at, 'unixepoch', '+8 hours') AS period,
               author AS username,
               COUNT(*) AS topic_count,
               SUM(CASE WHEN thank_count > 0 THEN thank_count ELSE 0 END) AS thank_count
        FROM topic
        WHERE clicks >= 0 AND create_at >= {MIN_VALID_CREATE_AT} AND author != ''
        GROUP BY 1, 2;
        CREATE TEMP TABLE member_comment_period AS
        SELECT strftime('%Y-%m', create_at, 'unixepoch', '+8 hours') AS period,
               commenter AS username,
               COUNT(*) AS comment_count,
               SUM(CASE WHEN thank_count > 0 THEN thank_count ELSE 0 END) AS thank_count
        FROM comment
        WHERE create_at >= {MIN_VALID_CREATE_AT} AND commenter != ''
        GROUP BY 1, 2;
        """
    )

    rows: list[list] = []

    def append_rankings(grain: str, metric: str, values_sql: str, parameters=()):
        ranking_sql = f"""
            WITH values_by_member AS ({values_sql}),
            ranked AS (
                SELECT period, username, value,
                       ROW_NUMBER() OVER (
                           PARTITION BY period
                           ORDER BY value DESC, username COLLATE NOCASE
                       ) AS position
                FROM values_by_member
                WHERE value > 0
            )
            SELECT period, position, username, value
            FROM ranked
            WHERE position <= ?
            ORDER BY period, position
        """
        rows.extend(
            [grain, period, metric, int(position), username, int(value)]
            for period, position, username, value in source.execute(
                ranking_sql, (*parameters, limit)
            )
        )

    current_period = datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m")
    for grain, period_sql, period_filter in (
        ("month", "period", ""),
        ("year", "substr(period, 1, 4)", f"WHERE period < '{current_period}'"),
    ):
        append_rankings(
            grain,
            "topics",
            f"""
                SELECT {period_sql} AS period, username, SUM(topic_count) AS value
                FROM member_topic_period
                {period_filter}
                GROUP BY 1, 2
            """,
        )
        append_rankings(
            grain,
            "comments",
            f"""
                SELECT {period_sql} AS period, username, SUM(comment_count) AS value
                FROM member_comment_period
                {period_filter}
                GROUP BY 1, 2
            """,
        )
        excluded = ",".join("?" for _ in EXCLUDED_THANK_USERS)
        thanks_period_filter = f"AND period < '{current_period}'" if grain == "year" else ""
        append_rankings(
            grain,
            "thanks",
            f"""
                SELECT {period_sql} AS period, username, SUM(thank_count) AS value
                FROM (
                    SELECT period, username, thank_count FROM member_topic_period
                    UNION ALL
                    SELECT period, username, thank_count FROM member_comment_period
                )
                WHERE LOWER(username) NOT IN ({excluded})
                  {thanks_period_filter}
                GROUP BY 1, 2
            """,
            tuple(EXCLUDED_THANK_USERS),
        )

    source.executescript(
        """
        DROP TABLE temp.member_topic_period;
        DROP TABLE temp.member_comment_period;
        """
    )
    return rows


def create_schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        DROP TABLE IF EXISTS period_metrics;
        DROP TABLE IF EXISTS activity_period;
        DROP TABLE IF EXISTS node_period;
        DROP TABLE IF EXISTS tag_period;
        DROP TABLE IF EXISTS title_token_period;
        DROP TABLE IF EXISTS topic_group_period;
        DROP TABLE IF EXISTS representative_post;
        DROP TABLE IF EXISTS first_reply_period;
        DROP TABLE IF EXISTS comment_age_period;
        DROP TABLE IF EXISTS long_tail_period;
        DROP TABLE IF EXISTS member_activity_period;
        DROP TABLE IF EXISTS engagement_period;

        CREATE TABLE period_metrics (
            period TEXT PRIMARY KEY,
            topic_count INTEGER NOT NULL,
            comment_count INTEGER NOT NULL,
            member_count INTEGER NOT NULL,
            reply_count INTEGER NOT NULL,
            zero_reply_count INTEGER NOT NULL,
            click_sum INTEGER NOT NULL,
            favorite_sum INTEGER NOT NULL,
            thank_sum INTEGER NOT NULL
        );
        CREATE TABLE activity_period (
            period TEXT NOT NULL,
            weekday INTEGER NOT NULL,
            hour INTEGER NOT NULL,
            topic_count INTEGER NOT NULL,
            comment_count INTEGER NOT NULL,
            PRIMARY KEY (period, weekday, hour)
        );
        CREATE TABLE node_period (
            period TEXT NOT NULL,
            node TEXT NOT NULL,
            topic_count INTEGER NOT NULL,
            reply_count INTEGER NOT NULL,
            click_sum INTEGER NOT NULL,
            PRIMARY KEY (period, node)
        );
        CREATE TABLE tag_period (
            period TEXT NOT NULL,
            tag TEXT NOT NULL,
            topic_count INTEGER NOT NULL,
            reply_count INTEGER NOT NULL,
            click_sum INTEGER NOT NULL,
            PRIMARY KEY (period, tag)
        );
        CREATE TABLE topic_group_period (
            period TEXT NOT NULL,
            group_name TEXT NOT NULL,
            topic_count INTEGER NOT NULL,
            reply_count INTEGER NOT NULL,
            PRIMARY KEY (period, group_name)
        );
        CREATE TABLE representative_post (
            id INTEGER PRIMARY KEY,
            period TEXT NOT NULL,
            title TEXT NOT NULL,
            node TEXT NOT NULL,
            tags TEXT NOT NULL,
            create_at INTEGER NOT NULL,
            clicks INTEGER NOT NULL,
            reply_count INTEGER NOT NULL,
            favorite_count INTEGER NOT NULL,
            thank_count INTEGER NOT NULL,
            score REAL NOT NULL
        );
        CREATE TABLE first_reply_period (
            period TEXT NOT NULL,
            bucket TEXT NOT NULL,
            topic_count INTEGER NOT NULL,
            PRIMARY KEY (period, bucket)
        );
        CREATE TABLE comment_age_period (
            period TEXT NOT NULL,
            bucket TEXT NOT NULL,
            comment_count INTEGER NOT NULL,
            PRIMARY KEY (period, bucket)
        );
        CREATE TABLE long_tail_period (
            period TEXT PRIMARY KEY,
            comment_30d_count INTEGER NOT NULL,
            after_24h_count INTEGER NOT NULL,
            after_7d_count INTEGER NOT NULL,
            eligible_topic_count INTEGER NOT NULL
        );
        CREATE TABLE member_activity_period (
            period TEXT PRIMARY KEY,
            new_member_count INTEGER NOT NULL,
            author_count INTEGER NOT NULL,
            commenter_count INTEGER NOT NULL
        );
        CREATE TABLE engagement_period (
            period TEXT PRIMARY KEY,
            topic_count INTEGER NOT NULL,
            click_count INTEGER NOT NULL,
            favorite_count INTEGER NOT NULL,
            topic_thank_count INTEGER NOT NULL,
            vote_count INTEGER NOT NULL,
            reply_count INTEGER NOT NULL,
            comment_count INTEGER NOT NULL,
            comment_thank_count INTEGER NOT NULL,
            thanked_comment_count INTEGER NOT NULL
        );
        """
    )


def build():
    groups = load_json(ANALYSIS_DIR / "topic_groups.json")
    synonyms = synonym_map()
    tag_stopwords = {
        str(tag).casefold() for tag in load_json(ANALYSIS_DIR / "tag_stopwords.json")
    }
    period_metrics = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
    topic_activity = defaultdict(int)
    nodes = defaultdict(lambda: [0, 0, 0])
    tags = defaultdict(lambda: [0, 0, 0])
    tag_totals = defaultdict(int)
    group_period = defaultdict(lambda: [0, 0])
    post_heaps: dict[str, list] = defaultdict(list)
    engagement_period = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
    interaction_heaps: dict[str, list] = defaultdict(list)

    source = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    query = source.execute(
        """
        SELECT id, author, title, node, tag, create_at, clicks, reply_count,
               favorite_count, thank_count, votes
        FROM topic
        WHERE clicks >= 0 AND create_at >= ?
        ORDER BY id
        """,
        (MIN_VALID_CREATE_AT,),
    )
    for row in query:
        period = month_for(row["create_at"])
        metrics = period_metrics[period]
        metrics[0] += 1
        metrics[1] += max(0, row["reply_count"])
        metrics[2] += int(row["reply_count"] == 0)
        metrics[3] += max(0, row["clicks"])
        metrics[4] += max(0, row["favorite_count"])
        metrics[5] += max(0, row["thank_count"])

        engagement = engagement_period[period]
        engagement[0] += 1
        engagement[1] += max(0, row["clicks"])
        engagement[2] += max(0, row["favorite_count"])
        engagement[3] += max(0, row["thank_count"])
        engagement[4] += max(0, row["votes"])
        engagement[5] += max(0, row["reply_count"])

        created = datetime.fromtimestamp(row["create_at"], LOCAL_TIMEZONE)
        topic_activity[(period, created.weekday(), created.hour)] += 1

        node = row["node"] or "未分类"
        node_metrics = nodes[(period, node)]
        node_metrics[0] += 1
        node_metrics[1] += max(0, row["reply_count"])
        node_metrics[2] += max(0, row["clicks"])

        try:
            raw_tags = json.loads(row["tag"] or "[]")
        except json.JSONDecodeError:
            raw_tags = []
        normalized_tags = normalize_tags(raw_tags, synonyms, tag_stopwords)
        for tag in normalized_tags:
            tag_metrics = tags[(period, tag)]
            tag_metrics[0] += 1
            tag_metrics[1] += max(0, row["reply_count"])
            tag_metrics[2] += max(0, row["clicks"])
            tag_totals[tag] += 1

        for group_name, group in groups.items():
            if matches_group(row["title"], node, normalized_tags, group):
                values = group_period[(period, group_name)]
                values[0] += 1
                values[1] += max(0, row["reply_count"])

        post = {
            "id": row["id"],
            "period": period,
            "title": row["title"],
            "node": node,
            "tags": sorted(normalized_tags),
            "create_at": row["create_at"],
            "clicks": row["clicks"],
            "reply_count": row["reply_count"],
            "favorite_count": row["favorite_count"],
            "thank_count": row["thank_count"],
            "votes": row["votes"],
            "author": row["author"],
        }
        score = engagement_score(row)
        if node.casefold() not in EXCLUDED_REPRESENTATIVE_NODES:
            heap = post_heaps[period]
            item = (score, row["id"], post)
            if len(heap) < REPRESENTATIVE_POSTS_PER_MONTH:
                heapq.heappush(heap, item)
            elif item > heap[0]:
                heapq.heapreplace(heap, item)

        for metric in ("clicks", "favorite_count", "thank_count", "votes"):
            metric_heap = interaction_heaps[metric]
            metric_item = (max(0, row[metric]), row["id"], post)
            if len(metric_heap) < INTERACTION_POST_RANKING_LIMIT:
                heapq.heappush(metric_heap, metric_item)
            elif metric_item > metric_heap[0]:
                heapq.heapreplace(metric_heap, metric_item)

    comment_stats = {
        period: (count, thank_count, thanked_count)
        for period, count, thank_count, thanked_count in source.execute(
            """
            SELECT strftime('%Y-%m', create_at, 'unixepoch', '+8 hours'),
                   COUNT(*), SUM(MAX(0, thank_count)),
                   SUM(CASE WHEN thank_count > 0 THEN 1 ELSE 0 END)
            FROM comment
            WHERE create_at >= ?
            GROUP BY 1
            """,
            (MIN_VALID_CREATE_AT,),
        )
    }
    comment_period = {period: values[0] for period, values in comment_stats.items()}
    member_period = dict(
        source.execute(
            """
            SELECT strftime('%Y-%m', create_at, 'unixepoch', '+8 hours'), COUNT(*)
            FROM member
            WHERE create_at >= ?
            GROUP BY 1
            """,
            (MIN_VALID_CREATE_AT,),
        )
    )
    author_period = dict(
        source.execute(
            """
            SELECT strftime('%Y-%m', create_at, 'unixepoch', '+8 hours'),
                   COUNT(DISTINCT author)
            FROM topic
            WHERE clicks >= 0 AND create_at >= ? AND author != ''
            GROUP BY 1
            """,
            (MIN_VALID_CREATE_AT,),
        )
    )
    commenter_period = dict(
        source.execute(
            """
            SELECT strftime('%Y-%m', create_at, 'unixepoch', '+8 hours'),
                   COUNT(DISTINCT commenter)
            FROM comment
            WHERE create_at >= ? AND commenter != ''
            GROUP BY 1
            """,
            (MIN_VALID_CREATE_AT,),
        )
    )
    comment_activity = {
        (period, int(weekday), int(hour)): count
        for period, weekday, hour, count in source.execute(
            """
            SELECT strftime('%Y-%m', create_at, 'unixepoch', '+8 hours'),
                   (CAST(strftime('%w', create_at, 'unixepoch', '+8 hours') AS INTEGER) + 6) % 7,
                   CAST(strftime('%H', create_at, 'unixepoch', '+8 hours') AS INTEGER),
                   COUNT(*)
            FROM comment
            WHERE create_at >= ?
            GROUP BY 1, 2, 3
            """,
            (MIN_VALID_CREATE_AT,),
        )
    }
    data_as_of = max(
        source.execute("SELECT MAX(create_at) FROM topic").fetchone()[0] or 0,
        source.execute("SELECT MAX(create_at) FROM comment").fetchone()[0] or 0,
    )
    seven_day_cutoff = data_as_of - 7 * 86400
    thirty_day_cutoff = data_as_of - 30 * 86400
    first_reply_period = defaultdict(int)
    for period, topic_created, first_comment in source.execute(
        """
        SELECT strftime('%Y-%m', t.create_at, 'unixepoch', '+8 hours'),
               t.create_at, MIN(c.create_at)
        FROM topic t
        LEFT JOIN comment c ON c.topic_id = t.id AND c.create_at >= t.create_at
        WHERE t.clicks >= 0 AND t.create_at >= ? AND t.create_at <= ?
        GROUP BY t.id
        """,
        (MIN_VALID_CREATE_AT, seven_day_cutoff),
    ):
        delay = None if first_comment is None else first_comment - topic_created
        first_reply_period[(period, first_reply_bucket(delay))] += 1

    comment_age_period = defaultdict(int)
    for period, bucket, count in source.execute(
        """
        SELECT period,
               CASE
                 WHEN delay < 600 THEN '10m'
                 WHEN delay < 3600 THEN '1h'
                 WHEN delay < 21600 THEN '6h'
                 WHEN delay < 86400 THEN '24h'
                 WHEN delay < 259200 THEN '3d'
                 ELSE '7d'
               END,
               COUNT(*)
        FROM (
          SELECT strftime('%Y-%m', t.create_at, 'unixepoch', '+8 hours') AS period,
                 c.create_at - t.create_at AS delay
          FROM comment c
          JOIN topic t ON t.id = c.topic_id
          WHERE t.clicks >= 0 AND t.create_at >= ? AND t.create_at <= ?
            AND c.create_at >= t.create_at AND c.create_at - t.create_at < 604800
        )
        GROUP BY 1, 2
        """,
        (MIN_VALID_CREATE_AT, seven_day_cutoff),
    ):
        comment_age_period[(period, bucket)] += count

    long_tail_period = {
        period: (comment_count, after_24h, after_7d, eligible_topics)
        for period, comment_count, after_24h, after_7d, eligible_topics in source.execute(
            """
            SELECT strftime('%Y-%m', t.create_at, 'unixepoch', '+8 hours'),
                   COUNT(c.id),
                   SUM(CASE WHEN c.create_at - t.create_at >= 86400 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN c.create_at - t.create_at >= 604800 THEN 1 ELSE 0 END),
                   COUNT(DISTINCT t.id)
            FROM topic t
            LEFT JOIN comment c ON c.topic_id = t.id
              AND c.create_at >= t.create_at AND c.create_at - t.create_at < 2592000
            WHERE t.clicks >= 0 AND t.create_at >= ? AND t.create_at <= ?
            GROUP BY 1
            """,
            (MIN_VALID_CREATE_AT, thirty_day_cutoff),
        )
    }
    author_stats = {
        username: {"topic_count": topic_count, "topic_thanks": topic_thanks or 0}
        for username, topic_count, topic_thanks in source.execute(
            """
            SELECT author, COUNT(*), SUM(MAX(0, thank_count))
            FROM topic
            WHERE clicks >= 0 AND create_at >= ? AND author != ''
            GROUP BY author
            """,
            (MIN_VALID_CREATE_AT,),
        )
    }
    commenter_stats = {
        username: {"comment_count": comment_count, "comment_thanks": comment_thanks or 0}
        for username, comment_count, comment_thanks in source.execute(
            """
            SELECT commenter, COUNT(*), SUM(MAX(0, thank_count))
            FROM comment
            WHERE create_at >= ? AND commenter != ''
            GROUP BY commenter
            """,
            (MIN_VALID_CREATE_AT,),
        )
    }
    member_stats = []
    for username in set(author_stats) | set(commenter_stats):
        author = author_stats.get(username, {})
        commenter = commenter_stats.get(username, {})
        member_stats.append(
            {
                "username": username,
                "topic_count": author.get("topic_count", 0),
                "comment_count": commenter.get("comment_count", 0),
                "topic_thanks": author.get("topic_thanks", 0),
                "comment_thanks": commenter.get("comment_thanks", 0),
                "total_thanks": author.get("topic_thanks", 0)
                + commenter.get("comment_thanks", 0),
            }
        )
    top_comments = [
        {
            "id": row[0], "topic_id": row[1], "commenter": row[2],
            "thank_count": row[3], "no": row[4], "topic_title": row[5],
            "content": comment_text(row[6]), "create_at": row[7],
        }
        for row in source.execute(
            f"""
            SELECT c.id, c.topic_id, c.commenter, c.thank_count, c.no, t.title,
                   c.content, c.create_at
            FROM comment c
            JOIN topic t ON t.id = c.topic_id
            WHERE c.thank_count > 0
              AND LOWER(c.commenter) NOT IN ({','.join('?' for _ in EXCLUDED_THANK_USERS)})
            ORDER BY c.thank_count DESC, c.id DESC
            LIMIT ?
            """,
            (*EXCLUDED_THANK_USERS, COMMENT_RANKING_LIMIT),
        )
    ]
    member_rank_rows = build_member_rank_rows(source)
    source.close()

    top_tags = {tag for tag, _ in sorted(tag_totals.items(), key=lambda x: x[1], reverse=True)[:TOP_TAG_LIMIT]}
    periods = sorted(period_metrics)
    analytics = sqlite3.connect(ANALYTICS_DB)
    create_schema(analytics)
    analytics.executemany(
        "INSERT INTO period_metrics VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                period,
                values[0],
                int(comment_period.get(period, 0)),
                int(member_period.get(period, 0)),
                values[1],
                values[2],
                values[3],
                values[4],
                values[5],
            )
            for period, values in sorted(period_metrics.items())
        ],
    )
    activity_keys = sorted(set(topic_activity) | set(comment_activity))
    analytics.executemany(
        "INSERT INTO activity_period VALUES (?, ?, ?, ?, ?)",
        [
            (*key, topic_activity.get(key, 0), comment_activity.get(key, 0))
            for key in activity_keys
        ],
    )
    analytics.executemany(
        "INSERT INTO node_period VALUES (?, ?, ?, ?, ?)",
        [(period, node, *values) for (period, node), values in sorted(nodes.items())],
    )
    analytics.executemany(
        "INSERT INTO tag_period VALUES (?, ?, ?, ?, ?)",
        [
            (period, tag, *values)
            for (period, tag), values in sorted(tags.items())
            if tag in top_tags
        ],
    )
    analytics.executemany(
        "INSERT INTO topic_group_period VALUES (?, ?, ?, ?)",
        [
            (period, group_name, *values)
            for (period, group_name), values in sorted(group_period.items())
        ],
    )
    representative_posts = []
    for heap in post_heaps.values():
        for score, _, post in heap:
            representative_posts.append({**post, "score": round(score, 3)})
    representative_posts.sort(key=lambda item: (item["period"], item["score"]), reverse=True)
    analytics.executemany(
        "INSERT INTO representative_post VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                post["id"], post["period"], post["title"], post["node"],
                json.dumps(post["tags"], ensure_ascii=False), post["create_at"],
                post["clicks"], post["reply_count"], post["favorite_count"],
                post["thank_count"], post["score"],
            )
            for post in representative_posts
        ],
    )
    analytics.executemany(
        "INSERT INTO first_reply_period VALUES (?, ?, ?)",
        [(period, bucket, count) for (period, bucket), count in sorted(first_reply_period.items())],
    )
    analytics.executemany(
        "INSERT INTO comment_age_period VALUES (?, ?, ?)",
        [(period, bucket, count) for (period, bucket), count in sorted(comment_age_period.items())],
    )
    analytics.executemany(
        "INSERT INTO long_tail_period VALUES (?, ?, ?, ?, ?)",
        [(period, *values) for period, values in sorted(long_tail_period.items())],
    )
    analytics.executemany(
        "INSERT INTO member_activity_period VALUES (?, ?, ?, ?)",
        [
            (period, int(member_period.get(period, 0)), int(author_period.get(period, 0)),
             int(commenter_period.get(period, 0)))
            for period in periods
        ],
    )
    analytics.executemany(
        "INSERT INTO engagement_period VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                period, *values,
                int(comment_stats.get(period, (0, 0, 0))[0]),
                int(comment_stats.get(period, (0, 0, 0))[1]),
                int(comment_stats.get(period, (0, 0, 0))[2]),
            )
            for period, values in sorted(engagement_period.items())
        ],
    )
    analytics.commit()

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    current_period = datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m")
    incomplete_periods = [period for period in periods if period >= current_period]
    complete_periods = [period for period in periods if period < current_period]
    first_reply_complete_through = max(
        period for period in periods if period < month_for(seven_day_cutoff)
    )
    long_tail_complete_through = max(
        period for period in periods if period < month_for(thirty_day_cutoff)
    )
    overview = {
        "metadata": {
            "generated_at": datetime.now(LOCAL_TIMEZONE).isoformat(timespec="seconds"),
            "start_period": periods[0],
            "end_period": periods[-1],
            "default_end_period": complete_periods[-1] if complete_periods else periods[-1],
            "incomplete_periods": incomplete_periods,
            "data_as_of": datetime.fromtimestamp(data_as_of, LOCAL_TIMEZONE).isoformat(timespec="seconds"),
        },
        "periods": [
            {
                "period": row[0], "topic_count": row[1], "comment_count": row[2],
                "member_count": row[3], "reply_count": row[4],
                "zero_reply_count": row[5], "click_sum": row[6],
                "favorite_sum": row[7], "thank_sum": row[8],
            }
            for row in analytics.execute("SELECT * FROM period_metrics ORDER BY period")
        ],
        "activity": [
            list(row) for row in analytics.execute("SELECT * FROM activity_period ORDER BY period, weekday, hour")
        ],
    }
    nodes_output = {
        "rows": [list(row) for row in analytics.execute("SELECT * FROM node_period ORDER BY period, node")]
    }
    topics_output = {
        "tags": [
            {"tag": tag, "total": total}
            for tag, total in sorted(tag_totals.items(), key=lambda x: x[1], reverse=True)[:TOP_TAG_LIMIT]
        ],
        "rows": [list(row) for row in analytics.execute("SELECT * FROM tag_period ORDER BY period, tag")],
        "groups": [
            {"name": name, "label": config["label"], "color": config["color"]}
            for name, config in groups.items()
        ],
        "group_rows": [list(row) for row in analytics.execute("SELECT * FROM topic_group_period ORDER BY period, group_name")],
    }
    representative_posts_output = {
        "representative_posts": representative_posts,
    }
    lifecycle_output = {
        "metadata": {
            "data_as_of": datetime.fromtimestamp(data_as_of, LOCAL_TIMEZONE).isoformat(timespec="seconds"),
            "first_reply_observation_days": 7,
            "long_tail_observation_days": 30,
            "first_reply_complete_through": first_reply_complete_through,
            "long_tail_complete_through": long_tail_complete_through,
        },
        "first_reply_buckets": list(FIRST_REPLY_BUCKETS),
        "comment_age_buckets": list(COMMENT_AGE_BUCKETS),
        "first_reply_rows": [
            list(row) for row in analytics.execute(
                "SELECT * FROM first_reply_period ORDER BY period, bucket"
            )
        ],
        "comment_age_rows": [
            list(row) for row in analytics.execute(
                "SELECT * FROM comment_age_period ORDER BY period, bucket"
            )
        ],
        "long_tail_rows": [
            list(row) for row in analytics.execute("SELECT * FROM long_tail_period ORDER BY period")
        ],
    }
    community_output = {
        "rows": [
            list(row) for row in analytics.execute(
                "SELECT * FROM member_activity_period ORDER BY period"
            )
        ],
        "top_topic_authors": sorted(
            member_stats, key=lambda item: item["topic_count"], reverse=True
        )[:30],
        "top_commenters": sorted(
            member_stats, key=lambda item: item["comment_count"], reverse=True
        )[:30],
        "top_thanked": sorted(
            (
                item for item in member_stats
                if item["username"].casefold() not in EXCLUDED_THANK_USERS
            ),
            key=lambda item: item["total_thanks"], reverse=True
        )[:30],
        "rank_rows": member_rank_rows,
    }
    engagement_output = {
        "rows": [
            list(row) for row in analytics.execute("SELECT * FROM engagement_period ORDER BY period")
        ],
        "top_posts": {
            metric: [
                {**post, "value": value}
                for value, _, post in sorted(heap, reverse=True)
            ]
            for metric, heap in interaction_heaps.items()
        },
        "top_comments": top_comments,
    }
    for name, payload in (
        ("dynamic-overview.json", overview),
        ("dynamic-nodes.json", nodes_output),
        ("dynamic-topics.json", topics_output),
        ("dynamic-representative-posts.json", representative_posts_output),
        ("dynamic-lifecycle.json", lifecycle_output),
        ("dynamic-community.json", community_output),
        ("dynamic-engagement.json", engagement_output),
    ):
        write_json(PUBLIC_DIR / name, payload)
    analytics.close()
    update_observations(write_component=False)
    update_tag_details()
    update_member_profiles()
    write_manifest("full", full_build=True)
    print(
        f"Built {ANALYTICS_DB}: {len(periods)} periods, "
        f"{len(nodes)} node rows, {len(top_tags)} tags, {len(representative_posts)} posts"
    )


def update_engagement_rankings(
    post_limit: int = INTERACTION_POST_RANKING_LIMIT,
    comment_limit: int = COMMENT_RANKING_LIMIT,
):
    output_path = PUBLIC_DIR / "dynamic-engagement.json"
    output = load_json(output_path)
    synonyms = synonym_map()
    tag_stopwords = {
        str(tag).casefold() for tag in load_json(ANALYSIS_DIR / "tag_stopwords.json")
    }
    source = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row

    top_posts = {}
    for metric in ("clicks", "favorite_count", "thank_count", "votes"):
        rows = source.execute(
            f"""
            SELECT id, author, title, node, tag, create_at, clicks, reply_count,
                   favorite_count, thank_count, votes
            FROM topic
            WHERE clicks >= 0 AND create_at >= ?
            ORDER BY MAX(0, {metric}) DESC, id DESC
            LIMIT ?
            """,
            (MIN_VALID_CREATE_AT, post_limit),
        )
        rankings = []
        for row in rows:
            try:
                raw_tags = json.loads(row["tag"] or "[]")
            except json.JSONDecodeError:
                raw_tags = []
            rankings.append({
                "id": row["id"],
                "period": month_for(row["create_at"]),
                "title": row["title"],
                "node": row["node"] or "未分类",
                "tags": sorted(normalize_tags(raw_tags, synonyms, tag_stopwords)),
                "create_at": row["create_at"],
                "clicks": row["clicks"],
                "reply_count": row["reply_count"],
                "favorite_count": row["favorite_count"],
                "thank_count": row["thank_count"],
                "votes": row["votes"],
                "author": row["author"],
                "value": max(0, row[metric]),
            })
        top_posts[metric] = rankings

    top_comments = [
        {
            "id": row[0], "topic_id": row[1], "commenter": row[2],
            "thank_count": row[3], "no": row[4], "topic_title": row[5],
            "content": comment_text(row[6]), "create_at": row[7],
        }
        for row in source.execute(
            f"""
            SELECT c.id, c.topic_id, c.commenter, c.thank_count, c.no, t.title,
                   c.content, c.create_at
            FROM comment c
            JOIN topic t ON t.id = c.topic_id
            WHERE c.thank_count > 0
              AND LOWER(c.commenter) NOT IN ({','.join('?' for _ in EXCLUDED_THANK_USERS)})
            ORDER BY c.thank_count DESC, c.id DESC
            LIMIT ?
            """,
            (*EXCLUDED_THANK_USERS, comment_limit),
        )
    ]
    source.close()
    output["top_posts"] = top_posts
    output["top_comments"] = top_comments
    write_json(output_path, output)
    write_manifest("engagement")
    print(f"Updated engagement rankings: {post_limit} posts per metric, {len(top_comments)} comments")


def update_representative_posts():
    synonyms = synonym_map()
    tag_stopwords = {
        str(tag).casefold() for tag in load_json(ANALYSIS_DIR / "tag_stopwords.json")
    }
    post_heaps: dict[str, list] = defaultdict(list)
    source = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    for row in source.execute(
        """
        SELECT id, author, title, node, tag, create_at, clicks, reply_count,
               favorite_count, thank_count, votes
        FROM topic
        WHERE clicks >= 0 AND create_at >= ?
        ORDER BY id
        """,
        (MIN_VALID_CREATE_AT,),
    ):
        node = row["node"] or "未分类"
        if node.casefold() in EXCLUDED_REPRESENTATIVE_NODES:
            continue
        try:
            raw_tags = json.loads(row["tag"] or "[]")
        except json.JSONDecodeError:
            raw_tags = []
        post = {
            "id": row["id"], "period": month_for(row["create_at"]),
            "title": row["title"], "node": node,
            "tags": sorted(normalize_tags(raw_tags, synonyms, tag_stopwords)),
            "create_at": row["create_at"], "clicks": row["clicks"],
            "reply_count": row["reply_count"], "favorite_count": row["favorite_count"],
            "thank_count": row["thank_count"], "votes": row["votes"],
            "author": row["author"],
        }
        score = engagement_score(row)
        heap = post_heaps[post["period"]]
        item = (score, row["id"], post)
        if len(heap) < REPRESENTATIVE_POSTS_PER_MONTH:
            heapq.heappush(heap, item)
        elif item > heap[0]:
            heapq.heapreplace(heap, item)
    source.close()

    representative_posts = [
        {**post, "score": round(score, 3)}
        for heap in post_heaps.values()
        for score, _, post in heap
    ]
    representative_posts.sort(key=lambda item: (item["period"], item["score"]), reverse=True)
    write_json(
        PUBLIC_DIR / "dynamic-representative-posts.json",
        {"representative_posts": representative_posts},
    )
    if ANALYTICS_DB.exists():
        analytics = sqlite3.connect(ANALYTICS_DB)
        analytics.execute("DELETE FROM representative_post")
        analytics.executemany(
            "INSERT INTO representative_post VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    post["id"], post["period"], post["title"], post["node"],
                    json.dumps(post["tags"], ensure_ascii=False), post["create_at"],
                    post["clicks"], post["reply_count"], post["favorite_count"],
                    post["thank_count"], post["score"],
                )
                for post in representative_posts
            ],
        )
        analytics.commit()
        analytics.close()
    write_manifest("representative_posts")
    print(f"Updated representative posts: {len(representative_posts)} posts, excluded {sorted(EXCLUDED_REPRESENTATIVE_NODES)}")


def update_community_rankings(limit: int = MEMBER_RANKING_LIMIT):
    output_path = PUBLIC_DIR / "dynamic-community.json"
    output = load_json(output_path)
    source = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    output["rank_rows"] = build_member_rank_rows(source, limit)
    source.close()
    write_json(output_path, output)
    write_manifest("community")
    update_member_profiles()
    print(f"Updated member rankings: {len(output['rank_rows'])} period ranking rows")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engagement-only", action="store_true")
    parser.add_argument("--community-only", action="store_true")
    parser.add_argument("--tag-details-only", action="store_true")
    parser.add_argument("--representative-only", action="store_true")
    parser.add_argument("--member-profiles-only", action="store_true")
    parser.add_argument("--observations-only", action="store_true")
    parser.add_argument("--if-changed", action="store_true")
    parser.add_argument("--interaction-limit", type=int, default=INTERACTION_POST_RANKING_LIMIT)
    parser.add_argument("--comment-limit", type=int, default=COMMENT_RANKING_LIMIT)
    parser.add_argument("--member-limit", type=int, default=MEMBER_RANKING_LIMIT)
    args = parser.parse_args()
    if args.engagement_only:
        update_engagement_rankings(args.interaction_limit, args.comment_limit)
    elif args.community_only:
        update_community_rankings(args.member_limit)
    elif args.tag_details_only:
        update_tag_details()
    elif args.representative_only:
        update_representative_posts()
    elif args.member_profiles_only:
        update_member_profiles()
    elif args.observations_only:
        update_observations()
    elif args.if_changed and source_unchanged_since_full_build():
        print("Source database unchanged; skipped full analytics build")
    else:
        build()
