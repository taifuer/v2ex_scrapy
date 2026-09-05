# V2EX 看板

V2EX 全站帖子、评论和成员爬虫，以及基于 Vue 3、Vite 与 ECharts 的静态数据看板。项目从公开页面构建事实库，再离线聚合话题、标题关键词、节点、成员、互动与生命周期数据；浏览器只读取按视图拆分的 JSON。

当前本地数据完整覆盖截至 2026-08-31：帖子 ID 已覆盖 `1..1238527`，完整分析月内有 1,204,199 个有效帖子、17,523,315 条评论；成员表另有 248,043 条档案记录。删除、登录可见或受限帖子会以占位记录保留，因此 ID 数量不等于有效帖子数。

“话题”专指帖子携带的 V2EX 原始标签；“标题关键词”来自标题分词与人工词表。两者独立统计，均不分析正文或评论语义，也不把字面匹配解释为立场、情绪或因果关系。

## 界面预览

### 概览

![V2EX 看板概览](demo/dashboard-demo.png)

### 话题演变

![V2EX 话题演变](demo/dashboard-topics.png)

### 社区观察

![V2EX 社区观察](demo/dashboard-observations.png)

更多视图：[数据演示](demo/dashboard-presentation.png) · [全局搜索](demo/dashboard-search.png) · [月度数据](demo/dashboard-monthly.png) · [年度数据](demo/dashboard-annual.png) · [标题关键词](demo/dashboard-content-hotspots.png) · [节点](demo/dashboard-nodes.png) · [成员](demo/dashboard-members.png) · [互动](demo/dashboard-engagement.png)

## 快速开始

需要 Python 3.10+ 和 Node.js 18+：

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
set -a; source .env; set +a
```

先用有限 ID 范围验证爬虫：

```bash
.venv/bin/scrapy crawl v2ex -a start_id=1 -a end_id=10
```

生成分析数据并启动看板：

```bash
.venv/bin/python analysis/build_analytics.py --if-changed
cd analysis/v2ex-analysis
npm install
npm run dev -- --host 0.0.0.0
```

没有本地分析数据时，可在前端目录执行 `npm run data:install`，从仓库锁定的 Release 下载并校验静态数据。开发服务默认访问 `http://localhost:5173/`；`npm run dev:latest` 可显式预览尚未完整的最新月份。

完整的增量抓取、月度封账、定向补抓、分析子任务、数据发布和部署命令见 [运行与维护](docs/OPERATIONS.md)。环境变量及抓取限速示例见 [.env.example](.env.example)。

## 看板内容

- **概览**：社区规模、参与用户、帖子互动、活跃时段、累计规模分布，以及可选择的月度和年度数据。
- **帖子**：话题和标题关键词演变与详情、节点结构与详情、聚合板块和帖子生命周期。
- **成员**：发帖/评论 Top 10 演变、Top 10/50/100 参与占比，以及部分活跃成员的年度参与方向。
- **互动**：按点击、收藏、感谢和回复查看热门帖子，并查看高感谢评论。
- **观察**：离线数据解读与 20 页 HTML 数据演示，从社区规模、话题和关键词演变，延伸到节点变化、具体帖子与评论。演示支持章节目录、全屏和页码链接。

详情趋势支持最多 5 个对象对比，并可从月份或年份查看对应代表帖子。话题、标题关键词、节点、成员和评论详情均使用索引与稳定哈希分片按需加载。月度和年度页直接展示该期指标、排名及代表内容，不额外生成重复的“观察”摘要。

收藏、感谢、投票和浏览量只有抓取时累计快照，没有互动发生时间。按内容发布时间分组的结果表示“该时期发布内容最终积累的互动”，不是互动在该时期发生。

## 文档

- [数据分析说明](docs/DATA_ANALYSIS.md)：指标定义、当前结果和使用限制。
- [指标与筛选口径](docs/METRIC_POLICY.md)：代表内容、收录门槛和异常值处理。
- [技术架构](docs/ARCHITECTURE.md)：抓取、离线构建、分词、数据契约和前端加载。
- [运行与维护](docs/OPERATIONS.md)：抓取、重建、测试、发布和部署手册。
- [看板数据发布](docs/DATA_RELEASE.md)：独立数据资产的打包、校验和恢复。
- [项目复盘](docs/PROJECT_RETROSPECTIVE.md)：演进过程、取舍、踩坑和可复用经验。
- [路线图](docs/ROADMAP.md)：仍待验证的后续工作。

## 验证

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python scripts/evaluate_title_keywords.py
.venv/bin/python scripts/audit_source_quality.py --fail-on-regression
.venv/bin/python scripts/validate_analytics.py
cd analysis/v2ex-analysis
npm run build
npm run test:budget
npm run test:e2e
```

提交或部署前也可运行 `scripts/preflight_dashboard.sh`。首次运行浏览器测试前执行 `npx playwright install chromium`。

`v2ex.sqlite`、`analysis/analytics.sqlite`、标题分词缓存和 `public/dynamic-*.json` 均为本地或发布产物，不进入 Git。安全问题、隐私或公开数据更正方式见 [SECURITY.md](SECURITY.md)。

## 来源

本项目基于 [oldshensheep/v2ex_scrapy](https://github.com/oldshensheep/v2ex_scrapy) 继续维护和扩展。当前版本的抓取可靠性、历史补抓、离线分析及可视化看板由 Codex (GPT-5.6 Sol) 协助重构与实现。
