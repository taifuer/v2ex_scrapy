import hashlib
import heapq
import json
import math
import re
import sqlite3
import zlib
from collections import Counter, defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jieba


LOCAL_TIMEZONE = timezone(timedelta(hours=8))
RANKING_LIMIT = 30
DETAIL_BUCKET_COUNT = 64
POSTS_PER_TERM_YEAR = 10
GLOBAL_CANDIDATE_LIMIT = 1500
PERIOD_CANDIDATE_LIMIT = 120
ANNUAL_CANDIDATE_LIMIT = 180
MIN_GLOBAL_COUNT = 20
MIN_MONTHLY_COUNT = 8
MIN_MONTHLY_AUTHORS = 5
MIN_ANNUAL_COUNT = 30
MIN_ANNUAL_AUTHORS = 15
EXCLUDED_NODES = frozenset({"promotions"})
TOKEN_CACHE_SCHEMA_VERSION = 1

URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
NUMERIC_RE = re.compile(r"[\d\W_]+", re.UNICODE)


def _load_json(path: Path):
    with path.open(encoding="utf-8") as fp:
        return json.load(fp)


def _write_json(path: Path, payload):
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, separators=(",", ":"))
    temp_path.replace(path)


def _load_word_set(path: Path) -> set[str]:
    with path.open(encoding="utf-8") as fp:
        return {
            line.strip().casefold()
            for line in fp
            if line.strip() and not line.lstrip().startswith("#")
        }


def _dictionary_terms(path: Path) -> list[str]:
    terms = []
    with path.open(encoding="utf-8") as fp:
        for raw_line in fp:
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.rsplit(maxsplit=2)
            term = parts[0] if len(parts) >= 2 and parts[-2].isdigit() else line
            if term:
                terms.append(term)
    return terms


def _known_term_pattern(term: str) -> str:
    pattern = re.escape(term)
    if term[0].isascii() and term[0].isalpha():
        pattern = rf"(?<![A-Za-z]){pattern}"
    if term[-1].isascii() and term[-1].isalpha():
        pattern = rf"{pattern}(?![A-Za-z])"
    return pattern


class TitleTokenizer:
    def __init__(self, analysis_dir: Path):
        self.stopwords = _load_word_set(analysis_dir / "content_stopwords.txt")
        synonym_config = _load_json(analysis_dir / "content_synonyms.json")
        self.synonyms: dict[str, str] = {}
        for canonical, variants in synonym_config.items():
            self.synonyms[canonical.casefold()] = canonical
            for variant in variants:
                self.synonyms[str(variant).casefold()] = canonical

        dictionary_path = analysis_dir / "content_user_dict.txt"
        self.dictionary_terms = _dictionary_terms(dictionary_path)
        self.canonical_terms = {term.casefold(): term for term in self.dictionary_terms}
        self.tokenizer = jieba.Tokenizer()
        with dictionary_path.open(encoding="utf-8") as dictionary:
            self.tokenizer.load_userdict(dictionary)
        for term in self.dictionary_terms:
            if " " not in term:
                self.tokenizer.add_word(term, freq=100000)

        known = sorted(
            {term for term in [*self.dictionary_terms, *self.synonyms] if len(term) >= 2},
            key=len,
            reverse=True,
        )
        known_pattern = "|".join(_known_term_pattern(term) for term in known)
        generic_pattern = (
            r"[A-Za-z]+[\u4e00-\u9fff]+|[\u4e00-\u9fff]+[A-Za-z]+|"
            r"[\u4e00-\u9fff]{2,}|\.[A-Za-z][A-Za-z0-9+#._-]*|"
            r"[A-Za-z][A-Za-z0-9+#]*(?:[._-][A-Za-z0-9+#]+)*"
        )
        self.segment_re = re.compile(
            f"{known_pattern}|{generic_pattern}" if known_pattern else generic_pattern,
            re.IGNORECASE,
        )

    def canonical(self, value: str) -> str:
        token = " ".join(value.strip().split())
        folded = token.casefold()
        if folded in self.synonyms:
            return self.synonyms[folded]
        if folded in self.canonical_terms:
            return self.canonical_terms[folded]
        if token.isascii():
            if token.isupper() or any(char.isdigit() for char in token):
                return token
            return token[:1].upper() + token[1:]
        return token

    def should_drop(self, token: str) -> bool:
        folded = token.casefold()
        if not folded or folded in self.stopwords or len(token) < 2 or len(token) > 40:
            return True
        if NUMERIC_RE.fullmatch(token):
            return True
        if not re.search(r"[A-Za-z\u4e00-\u9fff]", token):
            return True
        if re.fullmatch(r"[A-Za-z]{1}", token):
            return True
        if re.fullmatch(r"[\u4e00-\u9fff]{2}", token) and all(
            char in "这个那个什么怎么是否有点一下现在可以还是不是没有"
            for char in token
        ):
            return True
        return False

    def tokenize(self, title: str | None) -> set[str]:
        cleaned = EMAIL_RE.sub(" ", URL_RE.sub(" ", title or ""))
        result = set()
        for match in self.segment_re.finditer(cleaned):
            segment = match.group(0).strip()
            if not segment:
                continue
            if re.fullmatch(r"[\u4e00-\u9fff]{2,}", segment):
                candidates = self.tokenizer.cut(segment, cut_all=False)
            else:
                candidates = (segment,)
            for candidate in candidates:
                token = self.canonical(candidate)
                if not self.should_drop(token):
                    result.add(token)
        return result


def _month(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, LOCAL_TIMEZONE).strftime("%Y-%m")


def _hashed_bucket(value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
    return format(int(digest[:8], 16) % DETAIL_BUCKET_COUNT, "02x")


def _burst_score(
    count: int,
    total: int,
    baseline_count: int,
    baseline_total: int,
) -> float:
    if baseline_total <= 0:
        return 0.0
    current_rate = (count + 1.0) / (total + 500.0)
    baseline_rate = (baseline_count + 1.0) / (baseline_total + 500.0)
    return max(-6.0, min(6.0, math.log2(current_rate / baseline_rate)))


def _hot_score(count: int, authors: int, nodes: int, burst: float) -> float:
    author_ratio = min(1.0, authors / max(1, count))
    breadth = 0.82 + math.sqrt(author_ratio) * 0.18 + min(nodes, 12) * 0.012
    momentum = 1.0 + max(0.0, min(4.0, burst)) * 0.16
    return math.log1p(count) * breadth * momentum


def _rank_positions(counts: Counter) -> dict[str, int]:
    ranked = sorted(
        ((name, count) for name, count in counts.items() if count > 0),
        key=lambda item: (-item[1], item[0]),
    )
    return {name.casefold(): index for index, (name, _) in enumerate(ranked, 1)}


def _related_term_ranking(
    counts: Counter,
    allowed_terms: set[str],
    current_term: str,
    limit: int = 20,
) -> list[tuple[str, int]]:
    return sorted(
        (
            (term, count)
            for term, count in counts.items()
            if term in allowed_terms and term != current_term and count > 0
        ),
        key=lambda item: (-item[1], item[0].casefold(), item[0]),
    )[:limit]


def _engagement_score(row: sqlite3.Row) -> float:
    return (
        max(0, row["reply_count"])
        + max(0, row["favorite_count"]) * 3
        + max(0, row["thank_count"]) * 5
        + max(0, row["votes"]) * 2
        + math.log1p(max(0, row["clicks"]))
    )


def _push_top(heap: list, item: tuple, limit: int):
    if len(heap) < limit:
        heapq.heappush(heap, item)
    elif item > heap[0]:
        heapq.heapreplace(heap, item)


def _normalize_tags(raw: str | None, synonyms: dict[str, str], stopwords: set[str]) -> set[str]:
    try:
        values = json.loads(raw or "[]")
    except json.JSONDecodeError:
        values = []
    result = set()
    for value in values:
        tag = str(value).strip()
        canonical = synonyms.get(tag.casefold(), tag)
        if canonical and canonical.casefold() not in stopwords:
            result.add(canonical)
    return result


def _tag_config(analysis_dir: Path) -> tuple[dict[str, str], set[str]]:
    synonyms = {}
    for canonical, variants in _load_json(analysis_dir / "tag_synonyms.json").items():
        synonyms[canonical.casefold()] = canonical
        for variant in variants:
            synonyms[str(variant).casefold()] = canonical
    stopwords = {str(value).casefold() for value in _load_json(analysis_dir / "tag_stopwords.json")}
    return synonyms, stopwords


def _tokenizer_fingerprint(analysis_dir: Path) -> str:
    digest = hashlib.sha256(str(TOKEN_CACHE_SCHEMA_VERSION).encode("ascii"))
    for name in ("content_stopwords.txt", "content_synonyms.json", "content_user_dict.txt"):
        digest.update(name.encode("ascii"))
        digest.update((analysis_dir / name).read_bytes())
    return digest.hexdigest()


def sync_title_token_cache(
    source_db: Path,
    analysis_dir: Path,
    min_valid_create_at: int,
    cache_db: Path | None = None,
) -> dict[str, int]:
    cache_path = cache_db or analysis_dir / "content_tokens.sqlite"
    cache = sqlite3.connect(cache_path, uri=True)
    cache.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS title_tokens (
            topic_id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            tokens TEXT NOT NULL
        );
        """
    )
    fingerprint = _tokenizer_fingerprint(analysis_dir)
    cached_fingerprint = cache.execute(
        "SELECT value FROM metadata WHERE key = 'tokenizer_fingerprint'"
    ).fetchone()
    if cached_fingerprint is None or cached_fingerprint[0] != fingerprint:
        cache.execute("DELETE FROM title_tokens")
        cache.execute(
            "INSERT OR REPLACE INTO metadata VALUES ('tokenizer_fingerprint', ?)",
            (fingerprint,),
        )
        cache.commit()

    cache.execute("ATTACH DATABASE ? AS source", (f"file:{source_db}?mode=ro",))
    tokenizer = TitleTokenizer(analysis_dir)
    changed = cache.execute(
        """
        SELECT topic.id, topic.title
        FROM source.topic AS topic
        LEFT JOIN title_tokens AS cached ON cached.topic_id = topic.id
        WHERE topic.clicks >= 0 AND topic.create_at >= ? AND topic.title != ''
          AND (cached.topic_id IS NULL OR cached.title != topic.title)
        ORDER BY topic.id
        """,
        (min_valid_create_at,),
    )
    updated = 0
    batch = []
    for topic_id, title in changed:
        batch.append(
            (topic_id, title, json.dumps(sorted(tokenizer.tokenize(title)), ensure_ascii=False))
        )
        if len(batch) >= 5000:
            cache.executemany("INSERT OR REPLACE INTO title_tokens VALUES (?, ?, ?)", batch)
            updated += len(batch)
            batch.clear()
    if batch:
        cache.executemany("INSERT OR REPLACE INTO title_tokens VALUES (?, ?, ?)", batch)
        updated += len(batch)
    cache.commit()
    total = cache.execute("SELECT COUNT(*) FROM title_tokens").fetchone()[0]
    cache.close()
    return {"updated": updated, "total": total}


def _attach_token_cache(source: sqlite3.Connection, analysis_dir: Path):
    cache_path = analysis_dir / "content_tokens.sqlite"
    source.execute("ATTACH DATABASE ? AS token_cache", (f"file:{cache_path}?mode=ro",))


def _cached_tokens(row: sqlite3.Row) -> set[str]:
    return set(json.loads(row["cached_tokens"]))


def _candidate_terms(
    period_counts: dict[str, Counter],
    period_totals: dict[str, int],
    global_counts: Counter,
    periods: list[str],
) -> set[str]:
    candidates = {
        term for term, count in global_counts.most_common(GLOBAL_CANDIDATE_LIMIT)
        if count >= MIN_GLOBAL_COUNT
    }
    rolling_counts = Counter()
    rolling_totals = 0
    history: deque[tuple[str, Counter]] = deque()
    annual_counts: dict[str, Counter] = defaultdict(Counter)
    for period in periods:
        counts = period_counts[period]
        candidates.update(
            term for term, count in counts.most_common(PERIOD_CANDIDATE_LIMIT)
            if count >= MIN_MONTHLY_COUNT
        )
        burst_ranked = []
        for term, count in counts.items():
            if count < MIN_MONTHLY_COUNT or global_counts[term] < MIN_GLOBAL_COUNT:
                continue
            burst = _burst_score(count, period_totals[period], rolling_counts[term], rolling_totals)
            burst_ranked.append((burst * math.log1p(count), term))
        candidates.update(term for _, term in sorted(burst_ranked, reverse=True)[:PERIOD_CANDIDATE_LIMIT])
        annual_counts[period[:4]].update(counts)
        rolling_counts.update(counts)
        rolling_totals += period_totals[period]
        history.append((period, counts))
        if len(history) > 12:
            old_period, old_counts = history.popleft()
            rolling_counts.subtract(old_counts)
            rolling_totals -= period_totals[old_period]
    for counts in annual_counts.values():
        candidates.update(
            term for term, count in counts.most_common(ANNUAL_CANDIDATE_LIMIT)
            if count >= MIN_ANNUAL_COUNT
        )
    return candidates


def build_content_hotspots(
    source_db: Path,
    public_dir: Path,
    analysis_dir: Path,
    min_valid_create_at: int,
    default_end_period: str,
) -> dict:
    cache_summary = sync_title_token_cache(
        source_db, analysis_dir, min_valid_create_at
    )
    period_counts: dict[str, Counter] = defaultdict(Counter)
    period_tag_counts: dict[str, Counter] = defaultdict(Counter)
    period_totals: Counter = Counter()
    global_counts: Counter = Counter()
    tag_synonyms, tag_stopwords = _tag_config(analysis_dir)
    selected_topics = {
        item["tag"]
        for item in _load_json(public_dir / "dynamic-topics.json").get("tags", [])
    }

    source = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    _attach_token_cache(source, analysis_dir)
    rows = source.execute(
        """
        SELECT topic.title, topic.node, topic.tag, topic.create_at,
               cached.tokens AS cached_tokens
        FROM topic
        JOIN token_cache.title_tokens AS cached ON cached.topic_id = topic.id
        WHERE topic.clicks >= 0 AND topic.create_at >= ? AND topic.title != ''
        ORDER BY topic.id
        """,
        (min_valid_create_at,),
    )
    for row in rows:
        period = _month(row["create_at"])
        if period > default_end_period or (row["node"] or "").casefold() in EXCLUDED_NODES:
            continue
        period_totals[period] += 1
        tokens = _cached_tokens(row)
        period_counts[period].update(tokens)
        global_counts.update(tokens)
        period_tag_counts[period].update(
            tag.casefold() for tag in _normalize_tags(row["tag"], tag_synonyms, tag_stopwords)
        )

    periods = sorted(period_totals)
    candidates = _candidate_terms(period_counts, period_totals, global_counts, periods)
    author_sets: dict[tuple[str, str], set[int]] = defaultdict(set)
    node_sets: dict[tuple[str, str], set[int]] = defaultdict(set)
    node_counts: dict[str, Counter] = defaultdict(Counter)
    author_counts: dict[str, Counter] = defaultdict(Counter)
    term_author_sets: dict[str, set[int]] = defaultdict(set)
    term_node_sets: dict[str, set[int]] = defaultdict(set)
    topic_counts: dict[str, Counter] = defaultdict(Counter)
    post_heaps: dict[tuple[str, str], list] = defaultdict(list)
    rows = source.execute(
        """
        SELECT topic.id, topic.author, topic.title, topic.node, topic.tag,
               topic.create_at, topic.clicks, topic.reply_count,
               topic.favorite_count, topic.thank_count, topic.votes,
               cached.tokens AS cached_tokens
        FROM topic
        JOIN token_cache.title_tokens AS cached ON cached.topic_id = topic.id
        WHERE topic.clicks >= 0 AND topic.create_at >= ? AND topic.title != ''
        ORDER BY topic.id
        """,
        (min_valid_create_at,),
    )
    for row in rows:
        period = _month(row["create_at"])
        node = row["node"] or "未分类"
        if period > default_end_period or node.casefold() in EXCLUDED_NODES:
            continue
        tokens = _cached_tokens(row) & candidates
        if not tokens:
            continue
        author_hash = zlib.crc32((row["author"] or "").encode("utf-8"))
        node_hash = zlib.crc32(node.encode("utf-8"))
        tags = _normalize_tags(row["tag"], tag_synonyms, tag_stopwords)
        post = {
            "id": row["id"],
            "title": row["title"],
            "node": node,
            "tags": sorted(tags),
            "create_at": row["create_at"],
            "clicks": row["clicks"],
            "reply_count": row["reply_count"],
            "favorite_count": row["favorite_count"],
            "thank_count": row["thank_count"],
            "votes": row["votes"],
            "author": row["author"],
        }
        score = _engagement_score(row)
        post["score"] = round(score, 3)
        for term in tokens:
            key = (period, term)
            if row["author"]:
                author_sets[key].add(author_hash)
                author_counts[term][row["author"]] += 1
                term_author_sets[term].add(author_hash)
            node_sets[key].add(node_hash)
            node_counts[term][node] += 1
            term_node_sets[term].add(node_hash)
            topic_counts[term].update(tags & selected_topics)
            _push_top(post_heaps[(term, period[:4])], (score, row["id"], post), POSTS_PER_TERM_YEAR)
    source.close()

    rolling_counts = Counter()
    rolling_totals = 0
    history: deque[tuple[str, Counter]] = deque()
    monthly_rankings: dict[str, list] = {}
    monthly_rows: dict[tuple[str, str], list] = {}
    monthly_tag_ranks: dict[str, dict[str, int]] = {}
    for period in periods:
        eligible = []
        period_rows = []
        tag_ranks = _rank_positions(period_tag_counts[period])
        monthly_tag_ranks[period] = tag_ranks
        for term, count in period_counts[period].items():
            if term not in candidates or count < MIN_MONTHLY_COUNT:
                continue
            authors = len(author_sets[(period, term)])
            nodes = len(node_sets[(period, term)])
            burst = _burst_score(count, period_totals[period], rolling_counts[term], rolling_totals)
            share = count / max(1, period_totals[period]) * 100
            score = _hot_score(count, authors, nodes, burst)
            tag_count = period_tag_counts[period][term.casefold()]
            item = [
                term, count, authors, nodes, round(share, 4), round(burst, 3), round(score, 4),
                tag_count, 0, tag_ranks.get(term.casefold(), 0), rolling_counts[term] == 0,
            ]
            period_rows.append(item)
            if authors >= MIN_MONTHLY_AUTHORS and nodes >= 2:
                eligible.append(item)
        eligible.sort(key=lambda item: (-item[1], -item[6], item[0].casefold()))
        for rank, item in enumerate(eligible, 1):
            item[8] = rank
        for item in period_rows:
            monthly_rows[(period, item[0])] = item
        monthly_rankings[period] = eligible[:RANKING_LIMIT]
        rolling_counts.update(period_counts[period])
        rolling_totals += period_totals[period]
        history.append((period, period_counts[period]))
        if len(history) > 12:
            old_period, old_counts = history.popleft()
            rolling_counts.subtract(old_counts)
            rolling_totals -= period_totals[old_period]

    months_by_year: dict[str, list[str]] = defaultdict(list)
    for period in periods:
        months_by_year[period[:4]].append(period)
    annual_rankings: dict[str, list] = {}
    annual_rows: dict[str, dict[str, list]] = {}
    for year, year_periods in sorted(months_by_year.items()):
        counts = Counter()
        tag_counts_for_year = Counter()
        for period in year_periods:
            counts.update(period_counts[period])
            tag_counts_for_year.update(period_tag_counts[period])
        previous_periods = [f"{int(year) - 1}-{period[5:]}" for period in year_periods]
        previous_total = sum(period_totals.get(period, 0) for period in previous_periods)
        previous_counts = Counter()
        for period in previous_periods:
            previous_counts.update(period_counts.get(period, {}))
        total = sum(period_totals[period] for period in year_periods)
        tag_ranks = _rank_positions(tag_counts_for_year)
        eligible = []
        year_rows = {}
        for term, count in counts.items():
            if term not in candidates or count < MIN_ANNUAL_COUNT:
                continue
            authors = set().union(*(author_sets[(period, term)] for period in year_periods))
            nodes = set().union(*(node_sets[(period, term)] for period in year_periods))
            if len(authors) < MIN_ANNUAL_AUTHORS or len(nodes) < 2:
                continue
            burst = _burst_score(count, total, previous_counts[term], previous_total)
            share = count / max(1, total) * 100
            score = _hot_score(count, len(authors), len(nodes), burst)
            item = [
                term, count, len(authors), len(nodes), round(share, 4), round(burst, 3), round(score, 4),
                tag_counts_for_year[term.casefold()], 0, tag_ranks.get(term.casefold(), 0), previous_counts[term] == 0,
            ]
            year_rows[term] = item
            eligible.append(item)
        eligible.sort(key=lambda item: (-item[1], -item[6], item[0].casefold()))
        for rank, item in enumerate(eligible, 1):
            item[8] = rank
        annual_rows[year] = year_rows
        annual_rankings[year] = eligible[:RANKING_LIMIT]

    final_terms = {
        item[0]
        for ranking in [*monthly_rankings.values(), *annual_rankings.values()]
        for item in ranking
    }
    related_term_counts: dict[str, Counter] = defaultdict(Counter)
    source = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
    source.row_factory = sqlite3.Row
    _attach_token_cache(source, analysis_dir)
    rows = source.execute(
        """
        SELECT topic.title, topic.node, topic.create_at,
               cached.tokens AS cached_tokens
        FROM topic
        JOIN token_cache.title_tokens AS cached ON cached.topic_id = topic.id
        WHERE topic.clicks >= 0 AND topic.create_at >= ? AND topic.title != ''
        ORDER BY topic.id
        """,
        (min_valid_create_at,),
    )
    for row in rows:
        period = _month(row["create_at"])
        if period > default_end_period or (row["node"] or "").casefold() in EXCLUDED_NODES:
            continue
        tokens = _cached_tokens(row) & final_terms
        for term in tokens:
            related_term_counts[term].update(tokens - {term})
    source.close()

    rows_by_year: dict[str, list] = defaultdict(list)
    for period in periods:
        for term in final_terms:
            count = period_counts[period][term]
            if not count:
                continue
            item = monthly_rows.get((period, term))
            if item is None:
                authors = len(author_sets[(period, term)])
                nodes = len(node_sets[(period, term)])
                share = count / max(1, period_totals[period]) * 100
                item = [
                    term, count, authors, nodes, round(share, 4), 0.0,
                    round(_hot_score(count, authors, nodes, 0.0), 4),
                    period_tag_counts[period][term.casefold()], 0,
                    monthly_tag_ranks[period].get(term.casefold(), 0), False,
                ]
            rows_by_year[period[:4]].append([period, *item])

    public_dir.mkdir(parents=True, exist_ok=True)
    for path in public_dir.glob("dynamic-content-hotspots-*.json"):
        path.unlink()
    for path in public_dir.glob("dynamic-content-term-details-*.json"):
        path.unlink()
    year_shards = {}
    for year, rows in sorted(rows_by_year.items()):
        name = f"dynamic-content-hotspots-{year}.json"
        annual = [
            [year, *item] for term, item in annual_rows.get(year, {}).items()
            if term in final_terms
        ]
        _write_json(public_dir / name, {"year": year, "rows": sorted(rows), "annual_rows": sorted(annual)})
        year_shards[year] = name

    buckets = {format(index, "02x"): {"details": {}} for index in range(DETAIL_BUCKET_COUNT)}
    term_index = {}
    rows_by_term: dict[str, list] = defaultdict(list)
    for rows in rows_by_year.values():
        for row in rows:
            rows_by_term[row[1]].append(row)
    posts_by_term: dict[str, list] = defaultdict(list)
    for (term, _), heap in post_heaps.items():
        posts_by_term[term].extend(item[2] for item in sorted(heap, reverse=True))
    for term in sorted(final_terms, key=str.casefold):
        term_rows = rows_by_term[term]
        term_rows.sort(key=lambda row: row[0])
        bucket = _hashed_bucket(term)
        posts = posts_by_term[term]
        posts.sort(key=lambda post: (post["create_at"], post["score"]), reverse=True)
        details = {
            "term": term,
            "total": global_counts[term],
            "author_total": len(term_author_sets[term]),
            "node_total": len(term_node_sets[term]),
            "rows": term_rows,
            "annual_rows": [
                [year, *annual_rows[year][term]]
                for year in sorted(annual_rows)
                if term in annual_rows[year]
            ],
            "related_terms": _related_term_ranking(
                related_term_counts[term], final_terms, term
            ),
            "topics": sorted(
                topic_counts[term].items(),
                key=lambda item: (-item[1], item[0].casefold(), item[0]),
            )[:20],
            "nodes": node_counts[term].most_common(20),
            "authors": author_counts[term].most_common(20),
            "posts": posts,
        }
        buckets[bucket]["details"][term] = details
        term_index[term] = {
            "bucket": bucket,
            "total": global_counts[term],
            "first_period": term_rows[0][0],
            "last_period": term_rows[-1][0],
        }
    for bucket, payload in buckets.items():
        _write_json(public_dir / f"dynamic-content-term-details-{bucket}.json", payload)

    index = {
        "metadata": {
            "default_end_period": default_end_period,
            "eligible_topics": sum(period_totals.values()),
            "candidate_terms": len(candidates),
            "selected_terms": len(final_terms),
            "ranking_limit": RANKING_LIMIT,
            "baseline_months": 12,
            "representative_posts_per_year": POSTS_PER_TERM_YEAR,
            "excluded_nodes": sorted(EXCLUDED_NODES),
            "method": "包含热词的主题标题数、标题热词共现、关联话题、作者与节点覆盖、过去 12 个月相对热度",
        },
        "period_totals": dict(sorted(period_totals.items())),
        "year_shards": year_shards,
        "terms": term_index,
    }
    _write_json(public_dir / "dynamic-content-hotspots-index.json", index)
    latest = periods[-1]
    return {
        "periods": len(periods),
        "candidates": len(candidates),
        "terms": len(final_terms),
        "latest_period": latest,
        "latest_terms": [item[0] for item in monthly_rankings[latest][:10]],
        "token_cache_updated": cache_summary["updated"],
        "token_cache_total": cache_summary["total"],
    }
