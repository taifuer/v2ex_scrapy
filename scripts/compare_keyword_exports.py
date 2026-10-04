#!/usr/bin/env python3
"""Compare archived keyword indices without scanning the source database."""

import argparse
import json
from pathlib import Path


def compare(before: dict, after: dict) -> dict:
    old, new = before["terms"], after["terms"]
    return {
        "before_end": before["metadata"].get("preview_end_period"),
        "after_end": after["metadata"].get("preview_end_period"),
        "same_population": before.get("period_totals") == after.get("period_totals"),
        "added": {key: new[key]["total"] for key in sorted(new.keys() - old.keys())},
        "removed": {key: old[key]["total"] for key in sorted(old.keys() - new.keys())},
        "changed": sorted([
            {"term": key, "before": old[key]["total"], "after": new[key]["total"], "delta": new[key]["total"] - old[key]["total"]}
            for key in old.keys() & new.keys() if old[key]["total"] != new[key]["total"]
        ], key=lambda row: (-abs(row["delta"]), row["term"])),
        "note": "A matching population size alone does not prove identical source facts. Compare the same source snapshot to isolate rule changes.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(json.loads(args.before.read_text()), json.loads(args.after.read_text())), ensure_ascii=False, indent=2))
