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
        return "帖子数量减少，但单帖评论更集中；帖子规模和讨论强度应分开观察。"
    if current_topics > previous_topics and current_density < previous_density:
        return "帖子数量增加，但单帖评论减少；发帖增长不等于每篇帖子获得更多讨论。"
    return "帖子规模与单帖评论共同反映参与变化，不能只凭其中一个指标判断社区活跃度。"
