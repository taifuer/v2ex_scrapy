#!/usr/bin/env python3
import argparse
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analysis.content_hotspots import TitleTokenizer  # noqa: E402


ANALYSIS_DIR = ROOT / "analysis"
DEFAULT_GOLD = ANALYSIS_DIR / "title_keyword_gold.jsonl"


def load_gold(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as fp:
        for line_number, raw_line in enumerate(fp, 1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            row = json.loads(line)
            if not isinstance(row.get("title"), str):
                raise ValueError(f"invalid gold row at {path}:{line_number}")
            has_expected = isinstance(row.get("expected"), list)
            has_constraints = isinstance(row.get("required"), list) or isinstance(
                row.get("forbidden"), list
            )
            if has_expected == has_constraints:
                raise ValueError(
                    f"gold row must define expected or required/forbidden at {path}:{line_number}"
                )
            for field in ("expected", "required", "forbidden"):
                if field not in row:
                    continue
                values = [str(term) for term in row.get(field, [])]
                if len(values) != len(set(values)):
                    raise ValueError(
                        f"duplicate {field} term at {path}:{line_number}"
                    )
                row[field] = values
            row.setdefault("id", f"line-{line_number}")
            row.setdefault("category", "uncategorized")
            rows.append(row)
    if not rows:
        raise ValueError(f"gold dataset is empty: {path}")
    return rows


def evaluate(rows: list[dict], tokenizer: TitleTokenizer) -> dict:
    true_positive = false_positive = false_negative = exact = exact_rows = 0
    constraint_rows = constraint_passes = 0
    categories: dict[str, Counter] = {}
    differences = []
    for row in rows:
        actual = tokenizer.tokenize(row["title"])
        expected = set(row.get("expected", []))
        required = set(row.get("required", []))
        forbidden = set(row.get("forbidden", []))
        if "expected" in row:
            tp = len(expected & actual)
            fp = len(actual - expected)
            fn = len(expected - actual)
            true_positive += tp
            false_positive += fp
            false_negative += fn
            is_exact = actual == expected
            exact += int(is_exact)
            exact_rows += 1
            missing = expected - actual
            unexpected = actual - expected
        else:
            tp = fp = fn = 0
            constraint_rows += 1
            missing = required - actual
            unexpected = forbidden & actual
            is_exact = not missing and not unexpected
            constraint_passes += int(is_exact)
        category = categories.setdefault(row["category"], Counter())
        category.update({"rows": 1, "exact": int(is_exact), "tp": tp, "fp": fp, "fn": fn})
        if not is_exact:
            differences.append(
                {
                    "id": row["id"],
                    "category": row["category"],
                    "title": row["title"],
                    "missing": sorted(missing),
                    "unexpected": sorted(unexpected),
                }
            )

    precision = true_positive / max(1, true_positive + false_positive)
    recall = true_positive / max(1, true_positive + false_negative)
    f1 = 2 * precision * recall / max(1e-12, precision + recall)
    return {
        "rows": len(rows),
        "exact_labeled_rows": exact_rows,
        "exact_rows": exact,
        "exact_rate": round(exact / max(1, exact_rows), 4),
        "constraint_rows": constraint_rows,
        "constraint_pass_rate": round(
            constraint_passes / max(1, constraint_rows), 4
        ),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "categories": {
            name: {
                "rows": values["rows"],
                "exact_rate": round(values["exact"] / values["rows"], 4),
            }
            for name, values in sorted(categories.items())
        },
        "differences": differences,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate production title keywords against a reviewed JSONL corpus"
    )
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--analysis-dir", type=Path, default=ANALYSIS_DIR)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-precision", type=float, default=0.97)
    parser.add_argument("--min-recall", type=float, default=0.95)
    parser.add_argument("--min-exact-rate", type=float, default=0.90)
    parser.add_argument("--min-constraint-pass-rate", type=float, default=1.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = evaluate(load_gold(args.gold), TitleTokenizer(args.analysis_dir))
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temp_path = args.output.with_suffix(f"{args.output.suffix}.tmp")
        temp_path.write_text(encoded + "\n", encoding="utf-8")
        temp_path.replace(args.output)
    print(encoded)
    if (
        report["precision"] < args.min_precision
        or report["recall"] < args.min_recall
        or report["exact_rate"] < args.min_exact_rate
        or report["constraint_pass_rate"] < args.min_constraint_pass_rate
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
