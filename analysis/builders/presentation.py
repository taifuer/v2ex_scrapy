"""Build the presentation from existing aggregates and a few primary-key lookups."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .common import LOCAL_TIMEZONE, comment_prose_text, comment_text, month_for
from .rankings import percent_change
from .topics import matches_topic_group, matching_group_topics


# Excerpts are emitted only when the locally stored body still contains them.
_POST_CASES = {
    920519: (
        "API 接入", "新接口发布后，社区很快出现可直接试用的网站。",
        "群里有大佬基于新的 API 搞了个网站",
    ),
    1022439: (
        "知识库", "从聊天扩展到内部文档、知识库管理与调用成本统计。",
        "作为自己的专属内部 AI 知识库来使用",
    ),
    1233409: (
        "额度与重置", "作者已把编码工具用于工作，额度何时恢复成为实际安排的一部分。",
        "这种随机导致工作量根本无法提前安排",
    ),
    1052339: (
        "家庭与稳定性", "被裁后经历外包与事业编选择，同时考虑妻儿团聚和住房风险。",
        "但至少让孩子可以不当留守儿童",
    ),
    1109560: (
        "转栈求职", "前端开发转向 Java，困惑从学什么延伸到如何面试与证明能力。",
        "微服务现在只是会用，原理不懂",
    ),
    969697: (
        "交易疑问", "交易策略落到具体操作时，手续费就成了一道现实约束。",
        "需要 1.5%的手续费； 显然不适合频繁买卖；",
    ),
    1117738: (
        "寻找博主", "除了讨论买什么，用户也在寻找可以跟随的信息来源。",
        "还是专业的事交给专业的人, 抄作业得了",
    ),
    985269: (
        "月供变化", "宏观利率调整，在这位用户的账单上变成每月少付 1000 元。",
        "25 号转完浮动调成 4.2 ，月省 1000",
    ),
    1114692: (
        "租金与居住证", "比较约 200 元租金差，也关心房东能否配合办理居住证。",
        "自如平均贵个 200 块",
    ),
    931949: (
        "课程清单", "把分散的视频课程整理成清单，省下后来者寻找与筛选的时间。",
        "我自己在日常会整理、收藏一些比较有质量的课程",
    ),
    1030463: (
        "办事记录", "把一次开户经历写成流程与注意事项，留下可供查阅的经验。",
        "开了 6 张卡，一天内开了 5 张",
    ),
    1031215: (
        "租房指南", "从宽带到暴雨等居住细节，一份指南记录了租房时容易遗漏的问题。",
        "我想在深圳租到一个能痛快上网的房子。",
    ),
    473163: (
        "公共资料整理", "从公示资料收集到 CSV 整理和可视化，作者把调查过程与数据一起公开。",
        "单单是去检索，下载的过程，就足足花了 7 个多小时。",
    ),
    1102126: (
        "创作过程", "不只展示成品，也把开发取舍、发行过程与踩过的坑留给后来者。",
        "我将按时间线索将整个游戏制作和发行过程展现出来",
    ),
}

_KEYWORD_STAGES = (
    ("2014-01", "2014-12", "移动开发与招聘", ("iOS", "Android", "工程师", "招聘")),
    ("2020-01", "2021-12", "疫情、硬件与远程", ("疫情", "M1", "MacBook", "远程")),
    ("2022-01", "2023-12", "生成式 AI 的产品与接口", ("ChatGPT", "OpenAI", "API", "模型")),
    ("2025-01", "2025-12", "模型与编码工具", ("DeepSeek", "Cursor", "Claude Code", "Agent")),
    ("2026-01", None, "编码工具与使用限制", ("Codex", "Agent", "Claude Code", "额度")),
)


def _ratio(count: float, denominator: float, scale: int = 1, digits: int = 1) -> float:
    return round(count / denominator * scale, digits) if denominator else 0.0


def _known(value) -> int | None:
    return int(value) if value is not None and int(value) >= 0 else None


def _window(periods: list[str]) -> str:
    return f"{periods[0]} 至 {periods[-1]}" if periods else "无完整月份"


def _counts(rows: list[list], periods: set[str]) -> dict:
    result = defaultdict(int)
    for period, name, count, *_ in rows:
        if period in periods:
            result[period, name] += int(count)
    return result


def _annual(counts: dict) -> dict:
    result = defaultdict(int)
    for (period, name), count in counts.items():
        result[period[:4], name] += count
    return result


def _chart(
    kind: str,
    categories: list[str],
    series: list[dict],
    axis_name: str,
    unit: str,
    *,
    partial=(),
    annotations=(),
    **extra,
) -> dict:
    if any(len(item["values"]) != len(categories) for item in series):
        raise ValueError("presentation series must match categories")
    return {
        "kind": kind, "categories": categories, "series": series,
        "axis_name": axis_name, "unit": unit,
        "partial": [category for category in partial if category in categories],
        "annotations": [item for item in annotations if item["category"] in categories],
        **extra,
    }


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _codex_cooccurrence(public_dir: Path, periods: set[str]) -> dict:
    index = _read_json(public_dir / "dynamic-content-hotspots-index.json")
    entry = index.get("terms", {}).get("Codex", {})
    bucket = entry.get("bucket")
    if not bucket:
        return {}
    detail = _read_json(public_dir / f"dynamic-content-term-details-{bucket}.json")
    detail = detail.get("details", {}).get("Codex", {})
    rows = detail.get("rows", [])
    # related_terms is an all-period aggregate, not a monthly series. Never
    # relabel it as cutoff-safe if the shard also contains excluded months.
    if not rows or any(row[0] not in periods for row in rows):
        return {}
    total = sum(int(row[2]) for row in rows)
    if total != detail.get("total"):
        return {}
    related = dict(detail.get("related_terms", []))
    if not all(term in related for term in ("额度", "重置")):
        return {}
    return {"total": total, "额度": int(related["额度"]), "重置": int(related["重置"])}


def _load_posts(source_db, periods: set[str], groups: dict) -> dict[int, dict]:
    if not periods or source_db is None:
        return {}
    owns_connection = not isinstance(source_db, sqlite3.Connection)
    if owns_connection:
        path = Path(source_db)
        if not path.is_file():
            return {}
        source = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    else:
        source = source_db
    try:
        ids = sorted(_POST_CASES)
        cursor = source.execute(
            f"""SELECT id, title, node, tag, content, create_at, clicks,
                       favorite_count, thank_count, reply_count
                FROM topic WHERE id IN ({','.join('?' for _ in ids)})""",
            ids,
        )
        columns = [column[0] for column in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor]
    finally:
        if owns_connection:
            source.close()
    posts = {}
    for row in rows:
        timestamp = row["create_at"]
        if not timestamp or month_for(timestamp) not in periods or not row["title"]:
            continue
        topic_id = row["id"]
        badge, note, excerpt = _POST_CASES[topic_id]
        prose = " ".join(comment_prose_text(comment_text(row["content"])).split())
        verified = excerpt in prose
        if not verified:
            note = "仅保留标题与互动快照，当前本地正文未能核实选定摘录。"
        if topic_id in {969697, 1117738}:
            tags = set(json.loads(row["tag"] or "[]"))
            group = groups.get("finance", {})
            if not matches_topic_group(row["node"], tags, group):
                continue
            matched = sorted(matching_group_topics(tags, group))
            basis = "原始话题 " + "、".join(matched) if matched else f"节点 {row['node']}"
            note = f"{note}（{basis}）"
        post = {
            "id": topic_id, "title": row["title"], "node": row["node"],
            "date": datetime.fromtimestamp(timestamp, LOCAL_TIMEZONE).strftime("%Y-%m-%d"),
            "clicks": _known(row["clicks"]), "favorites": _known(row["favorite_count"]),
            "thanks": _known(row["thank_count"]), "replies": _known(row["reply_count"]),
            "url": f"https://www.v2ex.com/t/{topic_id}", "badge": badge,
            "selection": "人工选取", "note": note,
        }
        if verified:
            post["excerpt"] = excerpt
        posts[topic_id] = post
    return posts


def _record_period(record: dict) -> str:
    if record.get("create_at"):
        return month_for(record["create_at"])
    return record.get("period", record.get("date", "")[:7])


def build_presentation(
    overview: dict,
    topics: dict,
    nodes: dict,
    lifecycle: dict,
    engagement: dict,
    content_rows: list[list],
    source_db: Path | str | sqlite3.Connection | None,
    public_dir: Path | str,
) -> dict:
    metadata = overview["metadata"]
    end = metadata["default_end_period"]
    start = metadata["start_period"]
    incomplete = set(metadata.get("incomplete_periods", []))
    complete = sorted(
        (row for row in overview["periods"]
         if start <= row["period"] <= end and row["period"] not in incomplete),
        key=lambda row: row["period"],
    )
    periods = [row["period"] for row in complete]
    if not periods:
        raise ValueError("presentation requires at least one complete month")
    period_set = set(periods)
    analysis_periods = periods[-120:]
    analysis_period_set = set(analysis_periods)
    previous_periods, current_periods = periods[-120:-60], periods[-60:]
    overview_by_period = {row["period"]: row for row in complete}

    def total(selected, key):
        return sum(int(overview_by_period[period][key]) for period in selected)

    def average(selected, key):
        return total(selected, key) / len(selected) if selected else 0.0

    tag_counts = _counts(topics.get("rows", []), period_set)
    group_counts = _counts(topics.get("group_rows", []), period_set)
    node_counts = _counts(nodes.get("rows", []), period_set)
    content_counts = _counts(content_rows, period_set)
    annual_tags, annual_groups = _annual(tag_counts), _annual(group_counts)
    annual_nodes, annual_content = _annual(node_counts), _annual(content_counts)
    year_periods = defaultdict(list)
    for period in periods:
        year_periods[period[:4]].append(period)
    years = sorted(year_periods)
    year_topics = {year: total(year_periods[year], "topic_count") for year in years}
    partial = [year for year in years if len(year_periods[year]) < 12]

    def year_label(year):
        months = year_periods.get(year, [])
        if not months:
            return f"{year} 年未覆盖"
        if year not in partial:
            return f"{year} 全年"
        first, last = int(months[0][5:]), int(months[-1][5:])
        if len(months) == last - first + 1:
            return f"{year} 年 {first}-{last} 月"
        return f"{year} 年 {len(months)} 个完整月份"

    year_annotations = [{"category": year, "label": year_label(year)} for year in partial]
    annual_note = f"{_window(periods)}。"
    if years[-1] in partial:
        annual_note += year_label(years[-1]) + "。"
    full_note = f"{_window(periods)}，{len(periods)} 个完整月份。"
    snapshot_note = "案例经人工选取并核对本地正文；互动为抓取时累计快照，未知值留空。"
    group_definitions = {group["name"]: group for group in topics.get("groups", [])}
    group_labels = {name: group["label"] for name, group in group_definitions.items()}

    def count(counter, name, selected):
        return sum(counter.get((period, name), 0) for period in selected)

    def annual_series(counter, names, scale=10_000, labels=None):
        return [
            {"name": (labels or {}).get(name, name), "values": [
                _ratio(counter.get((year, name), 0), year_topics[year], scale,
                       2 if scale == 100 else 1) for year in years
            ]} for name in names
        ]

    def monthly_series(counter, names, selected):
        return [
            {"name": name, "values": [counter.get((period, name), 0) for period in selected]}
            for name in names
        ]

    def peak(counter, name):
        value, period = max((counter.get((period, name), 0), period) for period in periods)
        return {"period": period, "count": value}

    def annual_rate_peak(counter, name):
        return max(years, key=lambda year: (
            counter.get((year, name), 0) / year_topics[year] if year_topics[year] else 0
        ))

    def recent_peak_share(name):
        windows = [periods[index - 11:index + 1] for index in range(11, len(periods))]
        maximum = max((count(tag_counts, name, window) for window in windows), default=0)
        return _ratio(count(tag_counts, name, periods[-12:]), maximum, 100)

    current_topics = total(current_periods, "topic_count")
    previous_topics = total(previous_periods, "topic_count")
    current_comments = total(current_periods, "comment_count")
    previous_comments = total(previous_periods, "comment_count")
    all_topics, all_comments = total(periods, "topic_count"), total(periods, "comment_count")
    invitation_period = "2024-05"
    before = [period for period in periods if "2023-05" <= period < invitation_period]
    after = [period for period in periods if invitation_period <= period <= "2025-04"]
    window_size = min(len(before), len(after))
    before, after = (before[-window_size:], after[:window_size]) if window_size else ([], [])
    members_before, members_after = average(before, "member_count"), average(after, "member_count")
    community = {
        "topic_change": round(percent_change(current_topics, previous_topics), 1),
        "comment_change": round(percent_change(current_comments, previous_comments), 1),
        "previous_density": _ratio(previous_comments, previous_topics),
        "current_density": _ratio(current_comments, current_topics),
        "invitation_period": invitation_period,
        "members_before": round(members_before), "members_after": round(members_after),
        "member_change": round(percent_change(members_after, members_before), 1),
        "topics_after_change": round(percent_change(
            average(after, "topic_count"), average(before, "topic_count")
        ), 1),
        "comments_after_change": round(percent_change(
            average(after, "comment_count"), average(before, "comment_count")
        ), 1),
    }
    comparison_groups = ("apple", "engineering", "ai", "home", "career", "creation")
    topic_shifts = {
        "previous_start": previous_periods[0] if previous_periods else "",
        "previous_end": previous_periods[-1] if previous_periods else "",
        "current_start": current_periods[0], "current_end": current_periods[-1],
        **{f"{name}_change": round(percent_change(
            count(group_counts, name, current_periods), count(group_counts, name, previous_periods)
        ), 1) for name in ("engineering", "career", "ai", "creation", "home")},
        "apple_share": _ratio(
            count(group_counts, "apple", analysis_periods),
            total(analysis_periods, "topic_count"), 100, 2,
        ),
        "subscription": {name: {
            "previous": count(tag_counts, name, previous_periods),
            "current": count(tag_counts, name, current_periods),
        } for name in ("拼车", "88vip", "订阅")},
    }
    node_totals = defaultdict(int)
    for (_, node), value in node_counts.items():
        node_totals[node] += value
    top_nodes = [
        {"node": node, "topics": value, "share": _ratio(value, all_topics, 100, 2)}
        for node, value in sorted(node_totals.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]

    def ranked_posts(metric):
        return [
            post for post in engagement.get("top_posts", {}).get(metric, [])
            if _record_period(post) in period_set
            and _known(post.get(metric, post.get("value"))) is not None
        ][:20]

    favorites, thanked = ranked_posts("favorite_count"), ranked_posts("thank_count")
    overlap = len({post["id"] for post in favorites} & {post["id"] for post in thanked})
    comments = [comment for comment in engagement.get("top_comments", [])
                if _record_period(comment) in period_set][:100]
    response_comments = []
    for comment in comments:
        if comment.get("id") != 5432223 or comment.get("topic_id") != 437760:
            continue
        prose = " ".join(comment_prose_text(comment.get("content")).split())
        excerpt = "我相信大多数 v 友遇到这种情况都会和我一样的做法"
        thanks = _known(comment.get("thank_count"))
        if excerpt in prose and thanks is not None and comment.get("create_at"):
            response_comments.append({
                "id": comment["id"], "topic_id": comment["topic_id"],
                "username": comment["commenter"], "thanks": thanks, "text": excerpt,
                "date": datetime.fromtimestamp(comment["create_at"], LOCAL_TIMEZONE).strftime("%Y-%m-%d"),
                "url": f"https://www.v2ex.com/t/{comment['topic_id']}#r_{comment['id']}",
                "note": "转错款被主动退回后，收款人在评论中回应了大家的感谢。",
            })
    lengths = sorted(len(comment_prose_text(comment.get("content"))) for comment in comments)

    def ranking_leader(posts):
        if not posts:
            return {}
        return {"id": posts[0]["id"], "title": posts[0].get("title", ""),
                "value": _known(posts[0].get("value"))}

    interaction = {
        "ranking_size": 20, "overlap": overlap,
        "favorite_post": ranking_leader(favorites), "thanked_post": ranking_leader(thanked),
        "comment_median_length": lengths[len(lengths) // 2] if lengths else 0,
        "short_comments": sum(length <= 30 for length in lengths),
        "comment_sample_size": len(comments),
        "comment_top_thanks": _known(comments[0].get("thank_count")) if comments else None,
        "favorite_programmer_count": sum(post.get("node") == "programmer" for post in favorites),
        "thanked_life_count": sum(post.get("node") == "life" for post in thanked),
    }
    activity = [row for row in overview.get("activity", []) if row[0] in analysis_period_set]
    hourly_topics, hourly_comments = [0] * 24, [0] * 24
    for _, _, hour, topic_count, comment_count, *_ in activity:
        hourly_topics[int(hour)] += int(topic_count)
        hourly_comments[int(hour)] += int(comment_count)
    activity_topics, activity_comments = sum(hourly_topics), sum(hourly_comments)
    first_cutoff = min(end, lifecycle.get("metadata", {}).get("first_reply_complete_through", end))
    tail_cutoff = min(end, lifecycle.get("metadata", {}).get("long_tail_complete_through", end))
    first_counts = defaultdict(int)
    for period, bucket, value in lifecycle.get("first_reply_rows", []):
        if period in analysis_period_set and period <= first_cutoff:
            first_counts[bucket] += int(value)
    eligible_topics = sum(first_counts.values())
    within_1h = first_counts["10m"] + first_counts["1h"]
    within_24h = within_1h + first_counts["6h"] + first_counts["24h"]
    tail = [
        row for row in lifecycle.get("long_tail_rows", [])
        if row[0] in analysis_period_set and row[0] <= tail_cutoff
    ]
    rhythm = {
        "workday_topic_share": _ratio(
            sum(row[3] for row in activity if row[1] < 5 and 9 <= row[2] < 18),
            activity_topics, 100,
        ),
        "workday_comment_share": _ratio(
            sum(row[4] for row in activity if row[1] < 5 and 9 <= row[2] < 18),
            activity_comments, 100,
        ),
        "within_1h_share": _ratio(within_1h, eligible_topics, 100),
        "within_24h_share": _ratio(within_24h, eligible_topics, 100),
        "response_share": _ratio(eligible_topics - first_counts["none"], eligible_topics, 100),
        "after_7d_share": _ratio(sum(row[3] for row in tail), sum(row[1] for row in tail), 100),
    }
    overview_keys = (("帖子", "topic_count"), ("评论", "comment_count"), ("新增成员", "member_count"))
    annual_overview = [
        {"name": name, "values": [round(average(year_periods[year], key)) for year in years]}
        for name, key in overview_keys
    ]
    overview_peaks = {
        name: max((average(year_periods[year], key), year) for year in years)
        for name, key in overview_keys
    }
    ai_periods = [period for period in periods if period >= "2022-12"]
    tool_periods = [period for period in periods if period >= "2024-01"]
    member_periods = [period for period in periods if "2023-05" <= period <= "2025-04"]
    node_names = ("qna", "all4all", "jobs", "create", "life", "programmer")
    charts = {
        "overview": _chart(
            "small_multiples", years, annual_overview, "年度月均", "/月",
            partial=partial, annotations=year_annotations,
        ),
        "members": _chart(
            "line", member_periods,
            [{"name": "新增成员", "values": [total([period], "member_count") for period in member_periods]}],
            "新增成员", "人", annotations=[{"category": invitation_period, "label": "邀请码制度公布"}],
        ),
        "topic_comparison": _chart(
            "grouped_bar", [group_labels.get(name, name) for name in comparison_groups],
            [{"name": label, "values": [
                _ratio(count(group_counts, name, selected), denominator, 100, 2)
                for name in comparison_groups
            ]} for label, selected, denominator in (
                ("前五年", previous_periods, previous_topics), ("后五年", current_periods, current_topics)
            )],
            "同期帖子占比", "%",
        ),
        "ai_topics": _chart(
            "line", ai_periods, monthly_series(tag_counts, ("ChatGPT", "AI", "模型"), ai_periods),
            "原始话题帖子数", "帖",
        ),
        "ai_tools": _chart(
            "line", tool_periods,
            monthly_series(content_counts, ("Codex", "Agent", "Claude Code", "Cursor", "DeepSeek"), tool_periods),
            "命中关键词的标题数", "帖",
        ),
        "node_totals": _chart(
            "horizontal_bar", [item["node"] for item in top_nodes],
            [{"name": "帖子", "values": [item["topics"] for item in top_nodes]}],
            "帖子数", "帖", category_kind="node",
        ),
        "node_evolution": _chart(
            "line", years, annual_series(annual_nodes, node_names, 100), "同期帖子占比", "%",
            partial=partial, annotations=year_annotations, series_kind="node",
        ),
        "activity": _chart(
            "line", [f"{hour:02d}:00" for hour in range(24)],
            [{"name": name, "values": [_ratio(value, sum(values), 100, 2) for value in values]}
             for name, values in (("帖子", hourly_topics), ("评论", hourly_comments))],
            "时段占比", "%",
        ),
    }
    for key, names in (("career", ("招聘", "面试", "裁员", "失业")),
                       ("housing", ("买房", "房价", "房贷", "租房")),
                       ("subscriptions", ("拼车", "88vip", "订阅"))):
        charts[key] = _chart(
            "line", years, annual_series(annual_tags, names), "每万帖中的话题帖子", "帖/万帖",
            partial=partial, annotations=year_annotations,
        )
    charts["finance"] = _chart(
        "line", years, annual_series(annual_groups, ("finance", "crypto"), 100, group_labels),
        "同期帖子占比", "%", partial=partial, annotations=year_annotations,
    )

    cases = _load_posts(source_db, period_set, group_definitions)

    def posts(*ids):
        return [cases[topic_id] for topic_id in ids if topic_id in cases]

    milestones = []
    for first, last, title, terms in _KEYWORD_STAGES:
        selected = [period for period in periods if first <= period <= (last or end)]
        milestones.append({
            "period": _window(selected), "title": title,
            "items": [{"label": term, "count": count(content_counts, term, selected)} for term in terms
                      if count(content_counts, term, selected) > 0],
        })
    cooccurrence = _codex_cooccurrence(Path(public_dir), period_set)
    cooccurrence_metrics = [{
        "value": f"{cooccurrence[name]:,}", "label": f"Codex + {name}",
        "detail": f"全期 {cooccurrence['total']:,} 个 Codex 标题中的共现",
    } for name in ("额度", "重置")] if cooccurrence else []
    cooccurrence_note = (
        "共现为同一标题同时出现 Codex 与该词，未计算两项的并集。"
        if cooccurrence else "未展示超出当前完整月份范围的共现计数。"
    )
    current_year = years[-1]
    finance_metrics = [{
        "value": f"{annual_groups[year, 'finance']:,}", "label": f"{year_label(year)} 投资与经济帖",
        "detail": f"占同期 {_ratio(annual_groups[year, 'finance'], year_topics[year], 100, 2):.2f}%",
    } for year in ("2022", "2025") if year in years]
    model_comparison = (
        f"2023→2025：模型话题 {annual_tags['2023', '模型']:,}→{annual_tags['2025', '模型']:,}，"
        f"标题关键词 {annual_content['2023', '模型']:,}→{annual_content['2025', '模型']:,}；标签下降不等于领域下降。"
        if all(year in years and year not in partial for year in ("2023", "2025"))
        else "原始话题与标题关键词口径不同；标签频率变化不能直接解释为领域规模变化。"
    )
    career_peaks = [
        {"value": f"{max(item['values']):.1f}", "label": f"{item['name']}峰值 / 万帖",
         "detail": year_label(annual_rate_peak(annual_tags, item["name"]))}
        for item in charts["career"]["series"] if item["name"] in ("裁员", "失业")
    ]
    baseline_year = "2016" if "2016" in years else years[0]
    node_metrics = [{
        "value": (
            f"{_ratio(annual_nodes[baseline_year, node], year_topics[baseline_year], 100, 2):.2f}% → "
            f"{_ratio(annual_nodes[current_year, node], year_topics[current_year], 100, 2):.2f}%"
        ),
        "label": label, "detail": f"{year_label(baseline_year)} → {year_label(current_year)}",
    } for node, label in (("qna", "问与答"), ("create", "分享创造"))]
    member_metrics = [{
        "value": f"{community[key]:+.1f}%", "label": label,
        "detail": f"前后各 {window_size} 个完整月份的月均变化",
    } for key, label in (("member_change", "新增成员"), ("topics_after_change", "帖子"), ("comments_after_change", "评论"))] if window_size else []
    coverage = dict(metadata.get("analysis_coverage", {}))
    search_coverage = {
        "topics": len({name for _, name in tag_counts}),
        "content_terms": len({name for _, name in content_counts}),
        "nodes": sum(value >= 50 for value in node_totals.values()),
    }

    def slide(slide_id, slide_type, chapter, eyebrow, title, summary, note, **extra):
        return {"id": slide_id, "type": slide_type, "chapter": chapter, "eyebrow": eyebrow,
                "title": title, "summary": summary, "note": note, **extra}

    slides = [
        slide("cover", "cover", "社区全景", "社区数据故事", "V2EX 看板",
              "从社区规模到讨论变迁，再到一篇值得留下的帖子。", full_note,
              metrics=[{"value": f"{all_topics / 10_000:.1f} 万", "label": "帖子"},
                       {"value": f"{all_comments / 10_000:.1f} 万", "label": "评论"},
                       {"value": f"{metadata.get('participant_count', 0) / 10_000:.1f} 万", "label": "用户"}],
              definitions=[
                  {"title": "社区如何变化", "text": "新成员进入速度、发帖规模与讨论强度，描绘出不同的变化曲线。"},
                  {"title": "大家在关心什么", "text": "从 AI 工具到工作、投资与住房，标题和话题保留了关注点的变迁。"},
                  {"title": "哪些内容被留下", "text": "课程清单、生活指南、创作过程与互助回应，留下不同的收藏和感谢。"},
              ]),
        slide("scope", "facts", "社区全景", "数据范围", "一份跨越十六年的社区记录",
              "同一份数据，既能看规模与趋势，也能回到具体的讨论。",
              full_note + "仅含已采集有效记录；索引对象按本窗口出现情况计数，不代表全站完整覆盖。",
              metrics=[{"value": f"{metadata.get('participant_count', 0):,}", "label": "参与用户"},
                       {"value": f"{all_topics:,}", "label": "有效帖子"},
                       {"value": f"{all_comments:,}", "label": "评论"},
                       {"value": f"{search_coverage['topics']:,}", "label": "原始话题"},
                       {"value": f"{search_coverage['content_terms']:,}", "label": "标题关键词"},
                       {"value": f"{search_coverage['nodes']:,}", "label": "至少 50 帖的节点"}],
              definitions=[{"title": "话题", "text": "帖子原有标签经同义归并；板块按标签或节点命中，同组去重、跨组可重叠。"},
                           {"title": "标题关键词", "text": "复用已有标题分词，同一帖子对同一词只计一次，不是全文检索。"},
                           {"title": "节点", "text": "帖子发布版面，每帖一个节点；版面迁移和归类习惯会影响分布。"}]),
        slide("overview", "chart", "社区全景", "年度规模", "帖子、评论与新增成员并不同步",
              "年度月均峰值：" + "；".join(f"{name} {value[1]}" for name, value in overview_peaks.items()) + "。",
              annual_note + "月均除以已覆盖月份，不消除季节性；三图纵轴独立。", chart="overview",
              metrics=[{
                  "value": f"{overview_peaks[name][0]:,.0f}", "label": f"{name}月均峰值",
                  "detail": year_label(overview_peaks[name][1]),
              } for name in ("帖子", "评论")]),
        slide("members", "chart", "社区全景", "成员增长断点", "邀请码制度后，新成员骤减，讨论仍在继续",
              f"月均新增成员从 {members_before:,.0f} 降至 {members_after:,.0f}；同期帖子和评论的降幅远小于新增成员。",
              f"前窗 {_window(before)}；后窗 {_window(after)}。制度公告 #1037849，2024-05 公布；时间关联不等于唯一因果，档案覆盖也影响计数。",
              chart="members", metrics=member_metrics),
        slide("topic-structure", "chart", "话题演变", "两个五年窗口", "Apple 长期在场，AI、生活与创造扩大了份额",
              "后五年中，传统编程与职场板块的占比回落；讨论重心正向更多方向展开。",
              f"前窗 {_window(previous_periods)}；后窗 {_window(current_periods)}。同组去重、跨组可重叠，不能相加为 100%。",
              chart="topic_comparison"),
        slide("keyword-timeline", "timeline", "话题演变", "精选标题窗口", "从移动开发到编码工具，标题记录了技术现场",
              "同一个社区，先后讨论招聘、疫情、新硬件，以及走进日常工作的 AI 工具。",
              full_note + "各窗口精选关键词，数字为命中标题数，不是完整排名；窗口长度不同，不直接比较总量。",
              milestones=milestones),
        slide("ai-topics", "chart", "AI 与工具", "原始话题", "ChatGPT 的首轮热潮之后，AI 成了更常见的说法",
              f"ChatGPT 在 {peak(tag_counts, 'ChatGPT')['period']} 达到 {peak(tag_counts, 'ChatGPT')['count']:,} 帖的月度峰值；随后，AI 这一更宽泛的话题名持续扩张。",
              f"{_window(ai_periods)}；原始话题月度帖数，同帖可命中多条曲线。" + model_comparison,
              chart="ai_topics"),
        slide("ai-tools", "chart", "AI 与工具", "标题关键词", "标题里出现了更多模型与编码工具名",
              "从模型名称到 Agent 和编码工具，讨论正延伸到如何把能力接入实际工作。",
              f"{_window(tool_periods)}；每帖每词计一次，Agent 含同义词；不代表工具使用量。",
              chart="ai_tools", metrics=[{
                  "value": f"{annual_content[current_year, name]:,}",
                  "label": f"{name} 标题", "detail": year_label(current_year),
              } for name in ("Codex", "Agent")]),
        slide("ai-practice", "posts", "AI 与工具", "具体使用场景", "当工具进入工作，额度也成了生产安排",
              "从试用接口、搭建知识库到等待额度恢复，三篇帖子呈现了能力之外的使用细节。",
              full_note + cooccurrence_note + snapshot_note,
              posts=posts(920519, 1022439, 1233409), metrics=cooccurrence_metrics),
        slide("career", "chart", "工作与生活", "工作话题", "求职讨论里，技能之外还有家庭与稳定性",
              "面试话题在 2020 年出现高峰，裁员与失业在近年更常被提及；个体选择还牵涉转栈与团聚。",
              annual_note + "分母为同期全站帖子，话题可重叠；案例不都命中图中标签。",
              chart="career", metrics=career_peaks, posts=posts(1052339, 1109560)),
        slide("finance", "chart", "工作与生活", "投资与加密", "理财讨论升温，但投资与加密并不同步",
              "投资与经济板块的占比从 2022 年起明显抬升；加密讨论在 2025 年冲高，随后回落。",
              annual_note + "板块按话题或节点匹配并在组内去重；占比为同期全站帖子比例，不代表收益或市场情绪。",
              chart="finance", metrics=finance_metrics, posts=posts(969697, 1117738)),
        slide("housing", "chart", "工作与生活", "住房话题", "住房讨论里，同时存在价格、月供与居住选择",
              "房贷话题在 2023 年更突出，买房与房价在 2025 年再现高点；租房则长期保持讨论。",
              annual_note + "每万帖中的话题帖子数；曲线反映讨论，不是房价或租金指数。",
              chart="housing", posts=posts(985269, 1114692)),
        slide("subscriptions", "chart", "工作与生活", "数字消费", "会员与订阅，成了新的日常消费话题",
              "拼车与 88vip 在 2024 年明显增加，订阅在 2026 年更突出：数字服务也有成本、权益与共享的讨论。",
              annual_note + "原始话题每万帖频率；拼车含不同服务，不能全部归因于 AI 订阅。",
              chart="subscriptions", metrics=[{
                  "value": f"{annual_tags[year, name]:,}", "label": f"{name} 话题帖",
                  "detail": year_label(year),
              } for year, name in (("2024", "88vip"), (current_year, "订阅")) if year in years]),
        slide("node-totals", "chart", "社区入口", "累计规模", "问答、交易与技术构成主要发帖入口",
              "问与答、二手交易和程序员是长期积累的大节点，也承载着不同的发帖目的。",
              full_note + "节点按发帖归属计数，每帖一个节点。", chart="node_totals",
              metrics=[{"value": f"{_ratio(sum(item['topics'] for item in top_nodes), all_topics, 100, 2):.2f}%", "label": "前十节点合计占比"}]),
        slide("node-evolution", "chart", "社区入口", "年度份额", "从提问到分享创造，社区入口也在迁移",
              "问与答和招聘的发帖份额下降，分享创造更突出；累计大节点不一定仍是增长最明显的入口。",
              annual_note + "分母为同期全站帖子；节点规则与归类习惯也影响变化。",
              chart="node_evolution", metrics=node_metrics),
        slide("favorites", "posts", "互动与节律", "收藏案例", "值得反复查阅的内容，常常省下别人的时间",
              "高收藏案例中，有课程清单、办事记录和租房指南：它们的共同点，是把分散的经验整理成资料。",
              full_note + snapshot_note + "办事与租房经验有时效性。",
              posts=posts(931949, 1030463, 1031215), metrics=[{"value": f"{overlap} / 20", "label": "收藏与感谢 Top 20 重合"}]),
        slide("thanks", "posts", "互动与节律", "感谢案例", "感谢留给投入，也留给善意",
              "公开资料的整理、创作过程的分享，以及一次主动退回的转账，呈现了不同的感谢理由。",
              full_note + snapshot_note + "感谢数不等于事实核验或质量评分。",
              posts=posts(473163, 1102126), comments=response_comments),
        slide("rhythm", "chart", "互动与节律", "24 小时时段", "发帖与评论共享日间节律，首回通常较快",
              f"工作日 9-17 时贡献了 {rhythm['workday_topic_share']:.1f}% 的帖子与 {rhythm['workday_comment_share']:.1f}% 的评论；讨论常随日常作息展开。",
              f"近 10 年 {_window(analysis_periods)}，北京时间、全部星期。首回至 {first_cutoff}，仅含完整 7 日观察窗。",
              chart="activity", metrics=[
                  {"value": f"{rhythm[key]:.1f}%", "label": label} for key, label in
                  (("within_1h_share", "1 小时内首回"), ("within_24h_share", "24 小时内首回"))
              ] if eligible_topics else []),
        slide("conclusion", "conclusion", "回到全局", "三条观察", "社区变得怎样，藏在规模之外",
              "新成员、技术工具和互助经验，组成了这份社区记录中的三条线索。", full_note + "以上为描述性观察，案例用于理解语境。",
              takeaways=[
                  {"number": "01", "title": "入口收紧，讨论仍有延续", "text": (
                      f"邀请码制度前后，月均新增成员变化 {community['member_change']:+.1f}%，"
                      f"帖子 {community['topics_after_change']:+.1f}%，评论 {community['comments_after_change']:+.1f}%。"
                      "新成员变少，并不意味着讨论按相同比例消失。"
                  )},
                  {"number": "02", "title": "技术变化，也改变了日常问题", "text": (
                      "从 ChatGPT 到编码工具，讨论不只关心模型能力，也涉及知识库、调用成本与额度。"
                      "与此同时，工作、投资和住房始终构成真实生活的另一面。"
                  )},
                  {"number": "03", "title": "经验与善意，留下不同的互动痕迹", "text": (
                      f"收藏与感谢 Top 20 只重合 {overlap} 帖。"
                      "可复用的指南、公开的创作过程和互助回应，各自都有值得留下的理由。"
                  )},
              ]),
        slide("explore", "explore", "继续探索", "更多线索", "你的下一个发现，从一个词开始",
              "这里展示的是几条线索。更多产品、职业与生活的变化，留待你在看板中继续发现。",
              full_note + "搜索覆盖已收录的聚合对象，不是 V2EX 全文搜索。",
              metrics=[{"value": f"{search_coverage[key]:,}", "label": label} for key, label in (("topics", "话题"), ("content_terms", "标题关键词"), ("nodes", "至少 50 帖的节点"))]),
    ]
    return {
        "scope": {"start_period": start, "end_period": end, "complete_months": len(periods),
                  "participants": metadata.get("participant_count", 0), "topics": all_topics,
                  "comments": all_comments, "comments_per_topic": _ratio(all_comments, all_topics),
                  "coverage": coverage},
        "nodes": top_nodes, "community": community, "topic_shifts": topic_shifts,
        "ai": {"chatgpt_peak": peak(tag_counts, "ChatGPT"), "ai_peak": peak(tag_counts, "AI"),
               "model_peak": peak(tag_counts, "模型"),
               "codex_recent": count(content_counts, "Codex", periods[-12:]),
               "agent_recent": count(content_counts, "Agent", periods[-12:]),
               "claude_code_recent": count(content_counts, "Claude Code", periods[-12:]),
               "java_recent_peak_share": recent_peak_share("Java"),
               "python_recent_peak_share": recent_peak_share("Python")},
        "interaction": interaction, "rhythm": rhythm, "slides": slides, "charts": charts,
    }
