# 运行与维护

本文集中记录抓取、分析构建、验证和部署命令。首次操作前先安装依赖并加载 `.env`：

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
set -a; source .env; set +a
```

## 抓取

先只读检查登录状态，不启动爬虫、不写数据库，也不输出 Cookie：

```bash
V2EX_COOKIES_FILE=/root/.v2 \
  .venv/bin/python scripts/run_incremental_crawl.py check
```

检查要求设置页返回已登录的退出入口，公开页面返回 200 不代表登录有效。Cloudflare 验证页、403、429、登录重定向和网络错误都会停止启动；验证页只说明访问受阻，不直接判定 Cookie 过期。探测不跟随重定向，避免向其他地址转发凭据。先在浏览器确认正常登录和访问，再更新 Cookie 重试，不要持续请求验证页。

如果浏览器正常而程序被拦截，可在浏览器网络面板将成功的 V2EX GET 请求“复制为 cURL（bash）”，保存到仓库外。`V2EX_BROWSER_REQUEST_FILE` 让预检、Scrapy 和 API 使用同一份浏览器请求配置：

```bash
V2EX_BROWSER_REQUEST_FILE=/root/.v2-req \
  .venv/bin/python scripts/run_incremental_crawl.py check
V2EX_BROWSER_REQUEST_FILE=/root/.v2-req \
  .venv/bin/python scripts/run_incremental_crawl.py --through 2026-09-26
```

也可使用 `--request-file`；后台任务只接收文件路径。此文件含 Cookie 和可能存在的令牌，应按凭据保护。程序只解析 GET 请求和允许的请求头，不执行 cURL、shell 或文件引用；导出的 Authorization 永不用于网页抓取，API 仍从独立令牌文件读取。此模式优先使用导出的 Cookie、User-Agent 和浏览器请求头，不需要修改全局代理。遇到验证页仍停止，不自动求解挑战。

修改请求、解析或数据库逻辑后，先做有界验证：

```bash
.venv/bin/scrapy crawl v2ex -a start_id=1231000 -a end_id=1231010
.venv/bin/scrapy crawl v2ex -a topic_ids=100-120,205 -a force_update=true
.venv/bin/scrapy crawl v2ex-node -a node=python
.venv/bin/scrapy crawl v2ex-member -a start_id=1 -a end_id=100
```

按日期增量抓取使用统一入口。新计划和恢复任务都先检查登录，再验证日期上界、保存 JOBDIR，并生成可重试清单：

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

后台任务通过临时 systemd 服务脱离终端运行，但不会跨 WSL 关闭或系统重启自动恢复。重启后先运行 `status` 检查；若结束原因为 `shutdown`，使用相同截止日期和请求配置再次运行启动命令，保留原计划与 JOBDIR 继续抓取，不要加 `--refresh-plan`。完成后运行 `report` 检查已失败且不再位于队列中的请求；确认无待重试项后再补抓旧月份、重建看板。任务状态文件可能停留在关机前的阶段，不能代替服务状态与抓取报告。

直接使用 `scrapy crawl` 不经过上述登录预检，请先执行 `check`；爬虫运行期间仍保留连续 403/429 的退避与停止机制。日期边界探测遇到验证页或服务异常也立即停止，不把访问受阻当作帖子不存在。

完整月份结束并等待 7 天后，可重读该月可访问帖子、互动快照和全部评论分页：

```bash
.venv/bin/python scripts/run_monthly_close.py --month 2026-07 --dry-run
V2EX_COOKIES_FILE=/root/.v2 \
  .venv/bin/python scripts/run_monthly_close.py --month 2026-07
.venv/bin/python scripts/run_monthly_close.py report --month 2026-07
```

月度封账只形成更成熟的累计快照，不提供互动发生时间。抓取记录分别保存在 `crawl_run` 和 `topic_fetch_state`。

若只需补齐月底新帖的后续互动，可使用 `--last-days 7`，如 8 月 25 日至 31 日。它强制刷新该范围内的帖子及全部评论分页，保留独立计划、JOBDIR 和报告，不复用整月任务：

```bash
.venv/bin/python scripts/run_monthly_close.py --month 2026-08 --last-days 7 --dry-run
V2EX_COOKIES_FILE=/root/.v2 \
  .venv/bin/python scripts/run_monthly_close.py --month 2026-08 --last-days 7
.venv/bin/python scripts/run_monthly_close.py report --month 2026-08 --last-days 7
```

月度 `--dry-run` 只读取本地数据生成计划，不需要 Cookie；实际启动或恢复时仍重新检查登录。先完成下一月增量抓取，再运行月底刷新，确保源数据已越过月界；两项任务串行执行。补抓后核对报告再统一构建，不把未结束月份作为完整月发布。

### 官方 API 验证

[API 2.0](https://edge.v2ex.com/help/api) 使用独立 Personal Access Token，不使用网页 Cookie。在 [令牌管理](https://www.v2ex.com/settings/tokens) 创建普通令牌，存放在仓库外，通过 `V2EX_API_TOKEN_FILE` 指定；不要把令牌写进命令行或提交到仓库。

```bash
V2EX_API_TOKEN_FILE=/root/.v2-api-token \
  .venv/bin/python scripts/check_v2ex_api.py --topic-id 1231374 --latest
```

同样支持 `--request-file /root/.v2-req` 或 `V2EX_BROWSER_REQUEST_FILE`；导出请求的域名必须与 API 目标域名一致。

此入口只验证身份、帖子及一页评论/最新帖的 JSON 字段，不写数据库，不输出令牌、账户资料或帖子原文。默认请求官方 `www.v2ex.com`；`--host edge.v2ex.com` 对应文档示例域名，不自动切换域名或代理重试。

官方默认每 IP 每小时 600 请求。验证器至少间隔 7 秒，返回更低配额时继续降速；配额耗尽、429、非 JSON 页面或认证错误立即停止。403 HTML 验证页不是令牌过期的充分证据，404 HTML 也不能当作帖子不存在。

API 尚未替换现有网页抓取。接入前必须实测原始话题、浏览、收藏、主题感谢、评论感谢、附言和分页覆盖；文档没有给出完整字段契约。缺失字段保留未知状态，不能补成 0 或覆盖旧快照。`topics/latest` 文档明确排除已删除和隐藏节点主题，不能用它证明所有 ID 均已覆盖。

2026-09 实测主题 `1231374`：API 返回 `stars`、`thanks`、正文、作者、节点和附言列表，但未返回浏览量或原始话题；第一页回复返回 20 条，未包含评论感谢。因而当前主抓取仍使用网页解析，API 用于只读验证和后续补充，不能直接替代全部看板数据。

## 质量复核

```bash
.venv/bin/python scripts/audit_source_quality.py
.venv/bin/python scripts/backfill_missing_topics.py --end-id 1231354
.venv/bin/python scripts/backfill_missing_topics.py --end-id 1231354 --mode comments
```

评论补抓会重读候选帖的全部分页并按评论 ID 幂等更新。V2EX 累计回复数可能包含已删除回复，数据库评论数较少只是复核候选，不自动等同于漏抓。

质量门禁同时比较异常数量和具体记录 ID：新异常不能被旧异常减少抵消，同一帖回复快照差额扩大也会报告。`analysis/source_quality_baseline.json` 保留已知异常和核对记录，不应为了通过检查而自动重写。`--output` 可保存本次审计；`--initialize-identities` 仅供旧的纯数量基线一次性迁移，要求所有数量指标未退化，不能覆盖已有 ID 基线。登记既有异常并不代表已证明其来源。

附言时间单独审计，不纳入当前公开趋势。2026-10-02 本地有 197,244 / 199,721 条附言时间未知。解析器现在只读取附言自己的时间属性；后续重抓时，只替换同帖、同内容、时间为零的旧记录，不猜测时间、不覆盖已有非零时间，也不将有时间自动视为准确。

## 分析构建

常规更新使用：

```bash
.venv/bin/python analysis/build_analytics.py --if-changed
```

构建器会读取 SQLite 变更状态，未变化时直接跳过；完整构建会打印各阶段耗时。可按影响范围执行子任务：

跳过判断包含当前月份、完整月边界和配置指纹，不能仅凭数据库文件未变化就跳过跨月更新。分词词表修改可定向失效缓存，但依赖该词表的完整聚合仍可能扫描源数据；不要将“没有全量重新分词”理解成“所有分析都是实体级增量”。

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

HTML 数据演示的统计与案例由 `analysis/builders/presentation.py` 组织。调整演示后运行 `--observations-only` 即可更新，复用现有聚合数据并按主键读取精选帖子，不需要全量重建或重新分词。演示链接中的 `slide` 指定页面，例如 `?tab=observations&observation=presentation&slide=housing`；未收录的页码会回到开场。

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

GitHub Release 仅发布代码，不提供分析数据下载。首次运行需从本地抓取库构建：

```bash
.venv/bin/python analysis/build_analytics.py --if-changed
.venv/bin/python scripts/validate_analytics.py
```

已有本地数据归档时可通过 `scripts/install_dashboard_data.py` 恢复，步骤见 [本地数据与部署](DATA_RELEASE.md)。缺少数据时部署直接报错，不自动联网下载。本机源码部署使用 `./scripts/deploy_dashboard.sh`。

远程服务器只需要接收构建后的 `dist/`，不需要 Git、Node.js 或源码：

```bash
.venv/bin/python scripts/deploy_dashboard_remote.py \
  --remote root@example.com --port 22 \
  --remote-dir /srv/v2ex-dashboard
```

远程脚本在本地构建并检查预算，上传带 SHA-256 的归档后原子替换目录、重建容器并执行健康检查；失败时恢复上一版本。服务器专用统计与 CSP 配置不会进入仓库或被静态产物覆盖。
