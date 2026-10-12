"""Direction-aware wording for descriptive comparisons, not causal claims."""


def change_text(current: float, previous: float) -> str:
    if previous <= 0:
        return "仍为零" if current == 0 else "基期为零，不计算增幅"
    change = (current - previous) / previous * 100
    if abs(change) < 0.05:
        return "基本持平"
    direction = "增加" if change > 0 else "减少"
    return f"{direction} {abs(change):.1f}%"


def discussion_interpretation(current_topics: float, previous_topics: float,
                              current_density: float, previous_density: float) -> str:
    if current_topics < previous_topics and current_density > previous_density:
        return "帖子数量减少，但同期评论与发帖之比提高；评论可能来自更早发布的帖子，不能据此判断单帖讨论更集中。"
    if current_topics > previous_topics and current_density < previous_density:
        return "帖子数量增加，但同期评论与发帖之比降低；这不是同一批帖子的平均评论量。"
    return "帖子与评论分别按各自发布时间统计；同期评论与发帖之比不能解释为单帖平均评论数。"
