# Repository Guidelines

## Project Structure

Crawler code lives in `v2ex_scrapy/`. Spiders are under `v2ex_scrapy/spiders/`, SQLite persistence is in `DB.py`, parsing is in `v2ex_parser.py`, and environment handling is in `config.py`. Operational scripts belong in `scripts/`; focused unit tests belong in `tests/`. `analysis/build_analytics.py` reads the root `v2ex.sqlite`, writes ignored `analysis/analytics.sqlite`, and exports compact JSON to `analysis/v2ex-analysis/public/`. The Vue/Vite dashboard source is in `analysis/v2ex-analysis/src/`.

## Development Commands

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/scrapy crawl v2ex -a start_id=1 -a end_id=10
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python analysis/build_analytics.py
cd analysis/v2ex-analysis && npm install && npm run build
```

Use bounded crawl ranges for validation. Full crawls are slow and may trigger rate limits.

## Style and Testing

Use Python 3.10+, 4-space indentation, explicit imports, `snake_case` functions and variables, and `PascalCase` classes. Vue files use TypeScript and PascalCase component names. Keep data transformations in the offline builder; the browser should consume preaggregated JSON. Add `unittest` coverage for parser, configuration, range handling, and aggregation helpers. Run the Python suite and dashboard production build before committing.

## Commits and Pull Requests

Use short imperative commit subjects. Configure every commit author as `taifu <taifu@taifua.com>`. Agent-assisted commits must include this exact trailer in the commit message body:

```text
Co-Authored-By: Codex (GPT-5.6 Sol) <noreply@openai.com>
```

Pull requests should describe crawler/dashboard behavior, database or schema impact, commands run, and screenshots for visible UI changes.

## Security and Data

Never commit cookies, proxies, `.env`, `*.sqlite`, or logs. Use `V2EX_COOKIES_FILE` for credentials outside the repository. Treat `-1` interaction values and inaccessible topics as unknown data, not valid zero-value observations, unless the analysis explicitly documents normalization.
