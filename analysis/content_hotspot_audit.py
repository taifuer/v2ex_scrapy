import json
from pathlib import Path


def load_json(path: Path):
    with path.open(encoding="utf-8") as fp:
        return json.load(fp)


def review_reasons(detail: dict) -> list[str]:
    total = max(1, int(detail.get("total", 0)))
    reasons = []
    if detail.get("authors") and detail["authors"][0][1] / total >= 0.15:
        reasons.append("头部作者占比不低于 15%")
    if detail.get("nodes") and detail["nodes"][0][1] / total >= 0.75:
        reasons.append("头部节点占比不低于 75%")
    return reasons


def markdown_text(public_dir: Path) -> str:
    index = load_json(public_dir / "dynamic-content-hotspots-index.json")
    details = []
    shard_cache = {}
    for term, entry in index["terms"].items():
        bucket = entry["bucket"]
        if bucket not in shard_cache:
            shard_cache[bucket] = load_json(
                public_dir / f"dynamic-content-term-details-{bucket}.json"
            )["details"]
        details.append(shard_cache[bucket][term])
    details.sort(key=lambda item: (-item["total"], item["term"].casefold(), item["term"]))

    def cell(value) -> str:
        return str(value).replace("|", "\\|").replace("\n", " ")

    def examples(detail: dict) -> str:
        return "；".join(cell(post["title"][:48]) for post in detail.get("posts", [])[:2]) or "-"

    lines = [
        "# 标题热词质量审查",
        "",
        f"数据截至 {index['metadata']['default_end_period']}，共审查 {len(details)} 个内容热词。",
        "高集中度只用于提示人工查看，不代表该词应被过滤。标题样例取近期代表帖子。",
        "",
        "## 高频热词",
        "",
        "| 热词 | 标题数 | 独立作者 | 节点数 | 头部作者占比 | 头部节点占比 | 标题样例 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for detail in details[:50]:
        total = max(1, detail["total"])
        top_author = detail.get("authors", [["", 0]])[0][1] / total * 100
        top_node = detail.get("nodes", [["", 0]])[0][1] / total * 100
        lines.append(
            f"| {cell(detail['term'])} | {detail['total']:,} | {detail['author_total']:,} | "
            f"{detail['node_total']:,} | {top_author:.1f}% | {top_node:.1f}% | {examples(detail)} |"
        )

    flagged = [(detail, review_reasons(detail)) for detail in details]
    flagged = [(detail, reasons) for detail, reasons in flagged if reasons]
    lines.extend([
        "",
        "## 待人工复核",
        "",
        "| 热词 | 原因 | 标题数 | 标题样例 |",
        "| --- | --- | ---: | --- |",
    ])
    for detail, reasons in flagged:
        lines.append(
            f"| {cell(detail['term'])} | {'；'.join(reasons)} | {detail['total']:,} | {examples(detail)} |"
        )
    if not flagged:
        lines.append("| - | 暂无高集中度项 | 0 | - |")
    return "\n".join(lines) + "\n"


def write_content_hotspot_audit(public_dir: Path, output_path: Path):
    text = markdown_text(public_dir)
    temp_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(output_path)
