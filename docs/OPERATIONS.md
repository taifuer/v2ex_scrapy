# 运行与维护

本文集中记录抓取、分析构建、验证和部署命令。首次操作前先安装依赖并加载 `.env`：

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
set -a; source .env; set +a
```

## 抓取

修改请求、解析或数据库逻辑后，先做有界验证：

```bash
.venv/bin/scrapy crawl v2ex -a start_id=1231000 -a end_id=1231010
.venv/bin/scrapy crawl v2ex -a topic_ids=100-120,205 -a force_update=true
.venv/bin/scrapy crawl v2ex-node -a node=python
.venv/bin/scrapy crawl v2ex-member -a start_id=1 -a end_id=100
```

按日期增量抓取使用统一入口。它会验证日期上界、保存 JOBDIR，并生成可重试清单：

```bash
V2EX_COOKIES_FILE=/root/.v2 \
  .venv/bin/python scripts/run_incremental_crawl.py --through 2026-08-20
.venv/bin/python scripts/run_incremental_crawl.py status --through 2026-08-20
.venv/bin/python scripts/run_incremental_crawl.py report --through 2026-08-20
```

默认单并发、1 秒间隔。需要提高并发时显式传入 `--concurrency`，出现 403、429 或持续超时后恢复单并发。报告仍有失败项时，不复用原 JOBDIR，按清单强制刷新：

```bash
V2EX_COOKIES_FILE=/root/.v2 \
  .venv/bin/scrapy crawl v2ex \
  -a topic_ids_file=.crawl-jobs/through-2026-08-20/retry-topic-ids.txt \
  -a force_update=true -a crawl_purpose=incremental-retry
```

完整月份结束并等待 7 天后，可重读该月可访问帖子、互动快照和全部评论分页：

```bash
.venv/bin/python scripts/run_monthly_close.py --month 2026-07 --dry-run
V2EX_COOKIES_FILE=/root/.v2 \
  .venv/bin/python scripts/run_monthly_close.py --month 2026-07
.venv/bin/python scripts/run_monthly_close.py report --month 2026-07
```

月度封账只形成更成熟的累计快照，不提供互动发生时间。抓取记录分别保存在 `crawl_run` 和 `topic_fetch_state`。

## 质量复核

```bash
.venv/bin/python scripts/audit_source_quality.py
.venv/bin/python scripts/backfill_missing_topics.py --end-id 1231354
.venv/bin/python scripts/backfill_missing_topics.py --end-id 1231354 --mode comments
```

评论补抓会重读候选帖的全部分页并按评论 ID 幂等更新。V2EX 累计回复数可能包含已删除回复，数据库评论数较少只是复核候选，不自动等同于漏抓。

## 分析构建

常规更新使用：

```bash
.venv/bin/python analysis/build_analytics.py --if-changed
```

构建器会读取 SQLite 变更状态，未变化时直接跳过；完整构建会打印各阶段耗时。可按影响范围执行子任务：

```bash
.venv/bin/python analysis/build_analytics.py --engagement-only
.venv/bin/python analysis/build_analytics.py --community-only
.venv/bin/python analysis/build_analytics.py --member-profiles-only
.venv/bin/python analysis/build_analytics.py --tag-details-only
.venv/bin/python analysis/build_analytics.py --node-details-only
.venv/bin/python analysis/build_analytics.py --period-rankings-only
.venv/bin/python analysis/build_analytics.py --observations-only
.venv/bin/python analysis/build_analytics.py --content-hotspots-only
```

`--representative-only` 是重建话题详情和按期代表帖的兼容入口。同步 V2EX 官方节点中文名称运行 `.venv/bin/python scripts/update_node_labels.py`。

标题关键词规则修改后先运行回归和候选审计：

```bash
.venv/bin/python scripts/evaluate_title_keywords.py
.venv/bin/python scripts/audit_title_keyword_candidates.py
```

可选安装 PKUSEG/HanLP 做离线分词对照；审计结果只作为人工复核候选：

```bash
.venv/bin/pip install -r requirements-nlp.txt
.venv/bin/python scripts/audit_title_tokenizers.py --backend pkuseg --sample-size 20000
```

## 前端与验证

```bash
cd analysis/v2ex-analysis
npm install
npm run dev -- --host 0.0.0.0
npm run build
npm run test:budget
npm run test:e2e
```

首次执行 Playwright 前运行 `npx playwright install chromium`。完整发布前检查：

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python scripts/evaluate_title_keywords.py
.venv/bin/python scripts/audit_source_quality.py --fail-on-regression
.venv/bin/python scripts/validate_analytics.py
scripts/preflight_dashboard.sh
```

更新演示图时启动开发服务，再执行：

```bash
cd analysis/v2ex-analysis
DASHBOARD_URL=http://127.0.0.1:5180 npm run capture:demos
```

## 数据与部署

没有本地分析数据时，从锁定的 Release 安装：

```bash
.venv/bin/python scripts/fetch_dashboard_data.py
```

数据包的发布与恢复步骤见 [看板数据发布](DATA_RELEASE.md)。本机源码部署使用 `./scripts/deploy_dashboard.sh`。

远程服务器只需要接收构建后的 `dist/`，不需要 Git、Node.js 或源码：

```bash
.venv/bin/python scripts/deploy_dashboard_remote.py \
  --remote root@example.com --port 22 \
  --remote-dir /srv/v2ex-dashboard
```

远程脚本在本地构建并检查预算，上传带 SHA-256 的归档后原子替换目录、重建容器并执行健康检查；失败时恢复上一版本。服务器专用统计与 CSP 配置不会进入仓库或被静态产物覆盖。
