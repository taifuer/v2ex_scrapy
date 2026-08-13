#!/usr/bin/env python3
import argparse
import json
import random
import sqlite3
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from analysis.content_hotspots import TitleTokenizer  # noqa: E402


ANALYSIS_DIR = ROOT / "analysis"
SOURCE_DB = ROOT / "v2ex.sqlite"
DEFAULT_OUTPUT = ANALYSIS_DIR / "tokenizer_audits" / "latest.json"
LOCAL_TIMEZONE = timezone(timedelta(hours=8))
MIN_VALID_CREATE_AT = 1262304000


def sample_titles(
    source_db: Path,
    sample_size: int,
    start_period: str | None,
    end_period: str | None,
    seed: int,
) -> list[dict]:
    conditions = ["clicks >= 0", "create_at >= ?", "title != ''"]
    parameters: list[object] = [MIN_VALID_CREATE_AT]
    if start_period:
        conditions.append("strftime('%Y-%m', create_at, 'unixepoch', '+8 hours') >= ?")
        parameters.append(start_period)
    if end_period:
        conditions.append("strftime('%Y-%m', create_at, 'unixepoch', '+8 hours') <= ?")
        parameters.append(end_period)

    source = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
    rows = source.execute(
        f"""
        SELECT id, title, create_at
        FROM topic
        WHERE {' AND '.join(conditions)}
        ORDER BY id
        """,
        parameters,
    )
    rng = random.Random(seed)
    sample: list[tuple[int, str, int]] = []
    seen = 0
    for row in rows:
        seen += 1
        if len(sample) < sample_size:
            sample.append(row)
            continue
        replacement = rng.randrange(seen)
        if replacement < sample_size:
            sample[replacement] = row
    source.close()
    sample.sort(key=lambda row: row[0])
    return [
        {
            "id": int(topic_id),
            "title": title,
            "period": datetime.fromtimestamp(create_at, LOCAL_TIMEZONE).strftime("%Y-%m"),
        }
        for topic_id, title, create_at in sample
    ]


def write_pkuseg_dictionary(tokenizer: TitleTokenizer, path: Path):
    terms = sorted(
        {*tokenizer.dictionary_terms, *tokenizer.supplemental_terms},
        key=lambda term: (-len(term), term.casefold(), term),
    )
    path.write_text("\n".join(terms) + "\n", encoding="utf-8")


class PkusegBackend:
    name = "pkuseg"

    def __init__(self, model: str, dictionary_path: Path):
        try:
            import spacy_pkuseg
        except ImportError as exc:
            raise RuntimeError(
                "PKUSEG audit requires: .venv/bin/pip install spacy-pkuseg==1.0.1"
            ) from exc
        self.version = getattr(spacy_pkuseg, "__version__", "unknown")
        self.model = model
        self.segmenter = spacy_pkuseg.pkuseg(
            model_name=model,
            user_dict=str(dictionary_path),
        )

    def segment(self, titles: list[str], batch_size: int) -> list[list[str]]:
        return [self.segmenter.cut(title) for title in titles]


class HanlpBackend:
    name = "hanlp"

    def __init__(self, model: str | None):
        try:
            import hanlp
        except ImportError as exc:
            raise RuntimeError(
                "HanLP audit requires: .venv/bin/pip install hanlp==2.1.3"
            ) from exc
        self.version = getattr(hanlp, "__version__", "unknown")
        self.model = model or hanlp.pretrained.tok.COARSE_ELECTRA_SMALL_ZH
        self.segmenter = hanlp.load(self.model)

    def segment(self, titles: list[str], batch_size: int) -> list[list[str]]:
        output = []
        for offset in range(0, len(titles), batch_size):
            output.extend(self.segmenter(titles[offset:offset + batch_size]))
        return output


def normalized_backend_tokens(
    values: list,
    tokenizer: TitleTokenizer,
    title: str,
) -> set[str]:
    result = set()
    folded_title = title.casefold()
    for value in values:
        if isinstance(value, (tuple, list)):
            value = value[0]
        token = tokenizer.canonical(str(value))
        if (
            tokenizer.should_drop(token, check_stopwords=False)
            or tokenizer.segment_re.fullmatch(token) is None
        ):
            continue
        folded = token.casefold()
        offset = folded_title.find(folded)
        boundary_match = False
        while offset >= 0:
            before = folded_title[offset - 1] if offset else ""
            after_offset = offset + len(folded)
            after = folded_title[after_offset] if after_offset < len(folded_title) else ""
            starts_cleanly = not (
                token[0].isascii() and token[0].isalnum() and before.isascii() and before.isalnum()
            )
            ends_cleanly = not (
                token[-1].isascii() and token[-1].isalnum() and after.isascii() and after.isalnum()
            )
            if starts_cleanly and ends_cleanly:
                boundary_match = True
                break
            offset = folded_title.find(folded, offset + 1)
        if boundary_match:
            result.add(token)
    return result


def _ranked_candidates(
    counts: Counter,
    examples: dict[str, list[dict]],
    minimum_count: int,
    limit: int,
) -> list[dict]:
    return [
        {"term": term, "titles": count, "examples": examples.get(term, [])}
        for term, count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0].casefold(), item[0])
        )
        if count >= minimum_count
    ][:limit]


def compare_backend(
    rows: list[dict],
    segmented: list[list[str]],
    tokenizer: TitleTokenizer,
    minimum_count: int,
    candidate_limit: int,
) -> dict:
    if len(rows) != len(segmented):
        raise ValueError("tokenizer returned a different number of rows")
    missing_counts = Counter()
    filtered_counts = Counter()
    current_only_counts = Counter()
    examples: dict[str, list[dict]] = defaultdict(list)
    filtered_examples: dict[str, list[dict]] = defaultdict(list)
    exact_matches = 0
    for row, raw_tokens in zip(rows, segmented):
        current = tokenizer.tokenize(row["title"])
        alternative = normalized_backend_tokens(raw_tokens, tokenizer, row["title"])
        if current == {term for term in alternative if term.casefold() not in tokenizer.stopwords}:
            exact_matches += 1
        for term in alternative - current:
            if any(
                term.casefold() in current_term.casefold()
                for current_term in current
                if term.casefold() != current_term.casefold()
            ):
                continue
            target_counts = (
                filtered_counts if term.casefold() in tokenizer.stopwords else missing_counts
            )
            target_examples = (
                filtered_examples if term.casefold() in tokenizer.stopwords else examples
            )
            target_counts[term] += 1
            if len(target_examples[term]) < 3:
                target_examples[term].append(
                    {
                        "id": row["id"],
                        "title": row["title"],
                        "current": sorted(current),
                        "alternative": sorted(alternative),
                    }
                )
        current_only_counts.update(
            current - {term for term in alternative if term.casefold() not in tokenizer.stopwords}
        )
    return {
        "sampled_titles": len(rows),
        "exact_match_titles": exact_matches,
        "exact_match_rate": round(exact_matches / max(1, len(rows)), 4),
        "candidate_terms": _ranked_candidates(
            missing_counts, examples, minimum_count, candidate_limit
        ),
        "filtered_term_candidates": _ranked_candidates(
            filtered_counts, filtered_examples, minimum_count, candidate_limit
        ),
        "current_only_terms": [
            {"term": term, "titles": count}
            for term, count in current_only_counts.most_common(candidate_limit)
            if count >= minimum_count
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare the production title tokenizer with optional offline NLP models"
    )
    parser.add_argument(
        "--backend",
        choices=("pkuseg", "hanlp", "both"),
        default="pkuseg",
    )
    parser.add_argument("--source-db", type=Path, default=SOURCE_DB)
    parser.add_argument("--analysis-dir", type=Path, default=ANALYSIS_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sample-size", type=int, default=5000)
    parser.add_argument("--start-period")
    parser.add_argument("--end-period")
    parser.add_argument("--seed", type=int, default=20260813)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--minimum-count", type=int, default=3)
    parser.add_argument("--candidate-limit", type=int, default=100)
    parser.add_argument("--pkuseg-model", default="spacy_ontonotes")
    parser.add_argument("--hanlp-model")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Require every selected model to be an existing local path",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.sample_size <= 0 or args.batch_size <= 0:
        raise ValueError("sample size and batch size must be positive")
    backend_names = ["pkuseg", "hanlp"] if args.backend == "both" else [args.backend]
    model_values = {
        "pkuseg": args.pkuseg_model,
        "hanlp": args.hanlp_model,
    }
    if args.offline:
        for backend_name in backend_names:
            model = model_values[backend_name]
            if not model or not Path(model).exists():
                raise ValueError(
                    f"--offline requires a local --{backend_name}-model path"
                )

    tokenizer = TitleTokenizer(args.analysis_dir)
    rows = sample_titles(
        args.source_db,
        args.sample_size,
        args.start_period,
        args.end_period,
        args.seed,
    )
    titles = [row["title"] for row in rows]
    report = {
        "metadata": {
            "source_db": str(args.source_db),
            "sample_size": len(rows),
            "start_period": min((row["period"] for row in rows), default=None),
            "end_period": max((row["period"] for row in rows), default=None),
            "seed": args.seed,
            "minimum_count": args.minimum_count,
            "method": (
                "Alternative-only terms are review candidates, not automatic dictionary changes; "
                "filtered candidates are terms currently excluded by the production stopword list."
            ),
        },
        "backends": {},
    }
    with tempfile.TemporaryDirectory(prefix="v2ex-tokenizer-audit-") as temp_dir:
        dictionary_path = Path(temp_dir) / "pkuseg_user_dict.txt"
        write_pkuseg_dictionary(tokenizer, dictionary_path)
        for name in backend_names:
            backend = (
                PkusegBackend(args.pkuseg_model, dictionary_path)
                if name == "pkuseg"
                else HanlpBackend(args.hanlp_model)
            )
            segmented = backend.segment(titles, args.batch_size)
            report["backends"][name] = {
                "version": backend.version,
                "model": str(backend.model),
                **compare_backend(
                    rows,
                    segmented,
                    tokenizer,
                    args.minimum_count,
                    args.candidate_limit,
                ),
            }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote tokenizer audit for {len(rows)} titles to {args.output}")


if __name__ == "__main__":
    main()
