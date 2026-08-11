#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "analysis" / "node_labels.json"
SOURCE_URL = "https://www.v2ex.com/api/nodes/all.json"


def read_nodes(input_path: Path | None) -> list[dict]:
    if input_path:
        with input_path.open(encoding="utf-8") as source:
            return json.load(source)
    request = Request(SOURCE_URL, headers={"User-Agent": "v2ex-dashboard-node-labels/1.0"})
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description="Refresh V2EX node display names")
    parser.add_argument("--input", type=Path, help="Read a downloaded nodes/all.json file")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    labels = {}
    for node in read_nodes(args.input):
        name = str(node.get("name") or "").strip()
        title = " ".join(str(node.get("title") or "").split())
        if name and title:
            labels[name] = title
    if not labels:
        raise ValueError("official node response contained no labels")

    payload = {"source_url": SOURCE_URL, "labels": dict(sorted(labels.items()))}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as target:
        json.dump(payload, target, ensure_ascii=False, indent=2)
        target.write("\n")
    print(f"Updated {args.output}: {len(labels)} node labels")


if __name__ == "__main__":
    main()
