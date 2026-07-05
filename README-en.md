# V2EX Scrapy

[中文](README.md)

A Scrapy crawler for V2EX topics, comments, and members, with a Vue dashboard for time, topic, node, member, lifecycle, and engagement analysis. Data is stored in `v2ex.sqlite` at the repository root.

## Screenshots

### Overview

![V2EX community dashboard](docs/dashboard-demo.png)

### Topic analysis

![V2EX topic analysis](docs/dashboard-topics.png)

## Setup

Python 3.10+ and Node.js 18+ are required.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
set -a; source .env; set +a
```

## Crawl

Start with a bounded range:

```bash
.venv/bin/scrapy crawl v2ex -a start_id=1224000 -a end_id=1225000
.venv/bin/scrapy crawl v2ex -a topic_ids=100-120,205 -a force_update=true
.venv/bin/scrapy crawl v2ex-node -a node=python
.venv/bin/scrapy crawl v2ex-member -a start_id=1 -a end_id=100
```

Backfill missing topic IDs:

```bash
.venv/bin/python scripts/backfill_missing_topics.py --end-id 1225000
```

Keep concurrency conservative. Stop and wait if persistent 403 or 429 responses appear.

## Dashboard

```bash
.venv/bin/python analysis/build_analytics.py
cd analysis/v2ex-analysis
npm install
npm run dev -- --host 0.0.0.0
```

Open `http://localhost:5173/`. The dashboard defaults to the five years ending at the latest complete month and excludes the in-progress month. Favorites, thanks, and votes are snapshots grouped by content publication month, not timestamped interaction events.

## Verification

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
cd analysis/v2ex-analysis && npm run build
```

## Origin and Maintenance

This project is maintained and extended from [oldshensheep/v2ex_scrapy](https://github.com/oldshensheep/v2ex_scrapy). Codex (GPT-5.5) assisted with the current crawler reliability improvements, historical backfill tooling, analytics aggregation, and visualization dashboard.
