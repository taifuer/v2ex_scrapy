import hashlib
import json
from pathlib import Path


EVOLUTION_FORMAT_VERSION = 1
RANKING_LIMIT = 30


def content_evolution_payload(payload: dict, terms: dict) -> dict:
    return {
        "counts": [
            row[:3] for row in payload.get("rows", [])
            if terms.get(row[1], {}).get("ranked") is not False
        ],
        "rows": [row for row in payload.get("rows", []) if 0 < row[9] <= RANKING_LIMIT],
        "annual_rows": [
            row for row in payload.get("annual_rows", []) if 0 < row[9] <= RANKING_LIMIT
        ],
        "stage_hotspots": payload.get("stage_hotspots", {"month": [], "year": []}),
    }


def export_evolution_shards(public_dir: Path, write_json) -> None:
    """Derive browser payloads from aggregates, without reading the source database."""
    for kind, index_name, source_key in (
        ("topic", "dynamic-topics.json", "row_shards"),
        ("content", "dynamic-content-hotspots-index.json", "year_shards"),
    ):
        index_path = public_dir / index_name
        if not index_path.exists():
            continue
        index = json.loads(index_path.read_text(encoding="utf-8"))
        terms_fingerprint = hashlib.sha256(json.dumps(
            {term: entry.get("ranked") for term, entry in index.get("terms", {}).items()},
            sort_keys=True,
        ).encode("utf-8")).hexdigest()[:16]
        evolution_shards = {}
        group_shards = {}
        for year, name in index.get(source_key, {}).items():
            source = public_dir / name
            evolution_name = f"dynamic-{kind}-evolution-{year}.json"
            group_name = f"dynamic-{kind}-groups-{year}.json"
            evolution_shards[year] = evolution_name
            group_shards[year] = group_name
            outputs = [public_dir / evolution_name, public_dir / group_name]
            if (
                index.get("evolution_format") == EVOLUTION_FORMAT_VERSION
                and index.get("evolution_terms_fingerprint") == terms_fingerprint
                and all(path.exists() and path.stat().st_mtime_ns >= source.stat().st_mtime_ns for path in outputs)
            ):
                continue
            payload = json.loads(source.read_text(encoding="utf-8"))
            if kind == "content":
                evolution = content_evolution_payload(payload, index.get("terms", {}))
                groups = {key: payload.get(key, []) for key in ("group_rows", "group_term_rows")}
            else:
                evolution = {
                    "rows": [row[:4] for row in payload.get("rows", [])],
                    "stage_hotspots": payload.get("stage_hotspots", {"month": [], "year": []}),
                }
                groups = {"group_topic_rows": payload.get("group_topic_rows", [])}
            write_json(outputs[0], evolution)
            write_json(outputs[1], groups)
        index.update(
            evolution_format=EVOLUTION_FORMAT_VERSION,
            evolution_terms_fingerprint=terms_fingerprint,
            evolution_shards=evolution_shards,
            group_shards=group_shards,
        )
        write_json(index_path, index)
        expected = {*evolution_shards.values(), *group_shards.values()}
        for pattern in (f"dynamic-{kind}-evolution-*.json", f"dynamic-{kind}-groups-*.json"):
            for path in public_dir.glob(pattern):
                if path.name not in expected:
                    path.unlink()
