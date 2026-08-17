# V2EX 看板

V2EX 全站帖子、评论和成员爬虫，附带按时间、话题、标题关键词、节点、成员和互动指标分析的 Vue 仪表盘。看板支持可分享 URL、规模分布、月度与年度数据、事件注释、重点活跃成员详情和离线社区观察。数据保存到根目录 `v2ex.sqlite`。本项目为非官方社区数据项目。

当前本地数据完整覆盖截至 2026-07-31：帖子 ID 已覆盖 `1..1231354`，完整分析月内有有效帖子 1,197,069 条、评论 17,419,282 条；成员表另有 247,049 条档案记录。删除、登录可见或受限帖子会以占位记录保留，因此 ID 数量不等于有效帖子数。

指标定义、分析方法、当前数据观察及使用限制见 [数据分析说明](docs/DATA_ANALYSIS.md)；抓取、离线构建、分词、数据分片和前端实现见 [技术架构与功能实现](docs/ARCHITECTURE.md)；项目演进、取舍和可复用经验见 [项目复盘](docs/PROJECT_RETROSPECTIVE.md)；已评估但尚未全部交付的工作见 [路线图](docs/ROADMAP.md)。

界面将 V2EX 帖子携带的原始标签统一称为“话题”；从帖子标题提取的词项统一称为“标题关键词”。两者独立统计，标题关键词不代表正文或评论语义。

## 界面预览

### 概览

![V2EX 看板](demo/dashboard-demo.png)

### 话题演变

![V2EX 帖子](demo/dashboard-topics.png)

### 社区观察

![V2EX 社区观察](demo/dashboard-observations.png)

更多视图：[全局搜索](demo/dashboard-search.png) · [月度数据](demo/dashboard-monthly.png) · [年度数据](demo/dashboard-annual.png) · [标题关键词演变与详情](demo/dashboard-content-hotspots.png) · [节点分布](demo/dashboard-nodes.png) · [节点详情](demo/dashboard-node-detail.png) · [成员趋势](demo/dashboard-members.png) · [互动分析](demo/dashboard-engagement.png)

## 环境与配置

需要 Python 3.10+ 和 Node.js 18+：

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
set -a; source .env; set +a
```

环境变量包括 `V2EX_COOKIES_FILE`、`V2EX_PROXIES`、`V2EX_USER_AGENT`、抓取并发/延迟、AutoThrottle 和限流退避参数，配置示例见 `.env.example`。

## 爬取与补抓

优先使用小范围验证：

```bash
.venv/bin/scrapy crawl v2ex -a start_id=1231000 -a end_id=1231354
.venv/bin/scrapy crawl v2ex -a topic_ids=100-120,205 -a force_update=true
.venv/bin/scrapy crawl v2ex-node -a node=python
.venv/bin/scrapy crawl v2ex-member -a start_id=1 -a end_id=100
```

扫描并补抓指定上限内的缺失帖子：

```bash
.venv/bin/python scripts/backfill_missing_topics.py --end-id 1231354
```

审计源库并定向修复高置信评论分页缺口：

```bash
.venv/bin/python scripts/audit_source_quality.py
.venv/bin/python scripts/backfill_missing_topics.py --end-id 1231354 --mode comments
```

评论补抓会强制重读候选帖的全部评论分页，并以评论 ID 幂等更新；帖子抓取状态和任务结果分别记录在 `topic_fetch_state` 与 `crawl_run`。确认不可恢复的历史异常写入 `analysis/source_quality_baseline.json`，发布检查只在异常数量超过基线时失败。爬虫会跳过完整记录，并补抓缺失帖子、空节点或评论数不足的帖子。

默认配置使用可识别的项目 User-Agent、遵守 `robots.txt`、单域名单并发、随机延迟和 AutoThrottle。HTTP 403/429 会读取 `Retry-After` 或指数退避，连续受限时主动停止任务。需要兼容登录态时可通过 `V2EX_USER_AGENT` 覆盖请求标识；提高速率前应先确认站点规则和实际响应，不要用高并发绕过限制。

## 数据分析

更新数据库后生成只读聚合库和前端 JSON。数据库首次启用分析变更跟踪时会扫描帖子、评论和成员表建立基线；此后 `--if-changed` 直接读取触发器维护的轻量修订号，HTTP 日志或帖子正文单独变化不会触发分析。仅评论或成员变化时复用标题关键词、话题和节点详情；帖子、Schema 或相关词表变化时重建依赖产物。标题分词结果持久化在忽略的 `analysis/content_tokens.sqlite` 中：新增或改名帖子单独处理，词典、同义词和停用词变化只重算标题中可能受影响的记录，分词引擎或缓存 Schema 变化才清空全部缓存：

```bash
.venv/bin/python analysis/build_analytics.py --if-changed
cd analysis/v2ex-analysis
npm install
npm run dev -- --host 0.0.0.0
```

仅更新热门帖子 Top 200 和热门评论 Top 500，无需重建其他聚合数据：

```bash
.venv/bin/python analysis/build_analytics.py --engagement-only
```

仅更新成员月度/年度 Top 30 排名：

```bash
.venv/bin/python analysis/build_analytics.py --community-only
```

仅更新成员详情分片：

```bash
.venv/bin/python analysis/build_analytics.py --member-profiles-only
```

更新话题关联详情，并重建达到收录门槛的节点详情：

```bash
.venv/bin/python analysis/build_analytics.py --tag-details-only
```

仅更新节点详情索引与分片：

```bash
.venv/bin/python analysis/build_analytics.py --node-details-only
```

节点中文名称来自 V2EX 官方节点接口的本地快照。需要同步官方名称时运行：

```bash
.venv/bin/python scripts/update_node_labels.py
```

兼容入口：重建话题详情、分年度 Top 10 及分月自适应代表帖子（相关帖子不少于 100 个的月份 Top 10、不少于 20 个的月份 Top 5，其余月份 Top 3，均排除推广节点）：

```bash
.venv/bin/python analysis/build_analytics.py --representative-only
```

仅更新月度帖子四指标 Top 100 和感谢评论 Top 100 年度分片：

```bash
.venv/bin/python analysis/build_analytics.py --monthly-rankings-only
```

仅根据现有聚合 JSON 更新离线观察与点评：

```bash
.venv/bin/python analysis/build_analytics.py --observations-only
```

仅重建标题分词与标题关键词切片：

```bash
.venv/bin/python analysis/build_analytics.py --content-hotspots-only
```

需要审计分词遗漏时，可选安装 PKUSEG/HanLP，并在固定样本上与生产分词结果比较：

```bash
.venv/bin/pip install -r requirements-nlp.txt
.venv/bin/python scripts/audit_title_tokenizers.py --backend pkuseg --sample-size 20000
```

首次使用模型可能下载权重；生产或离线环境应通过 `--pkuseg-model`、`--hanlp-model` 指定本地模型，并加 `--offline`。报告写入忽略的 `analysis/tokenizer_audits/`，只作为人工复核候选，不会自动修改词表。

词表修改前后应先运行人工回归集；需要从全量标题发现可能遗漏的新词时，再生成候选报告人工复核：

```bash
.venv/bin/python scripts/evaluate_title_keywords.py
.venv/bin/python scripts/audit_title_keyword_candidates.py
```

回归集用于阻止已知样例退化，不代表全量标题达到相同准确率。候选工具输出出现频次、近期份额变化、活跃与峰值周期、作者/节点集中度、既有关键词重合度和示例标题，不会自动修改生产词表。

访问 `http://localhost:5173/`。仪表盘默认显示截至最近完整月的 5 年数据，并排除进行中的月份。生产构建：

```bash
npm run build
```

收藏、感谢和投票只有当前快照，没有互动发生时间；相关趋势按内容发布时间分组，不代表对应月份实际发生的互动。

主要视图包括：

- 概览：帖子、成员、互动和活跃时段的全局变化；规模分布统计帖子、评论、话题、节点和参与用户的累计量级；月度与年度视图提供可选择的周期切片。
- 帖子：话题演变与详情、标题关键词演变与详情、节点分布与详情、话题板块、关键词板块和生命周期。话题板块只依据 V2EX 原始话题与节点，展示十个板块的时间范围规模、同期帖子占比趋势、话题覆盖率和主要话题；关键词板块只依据标题分词，按相同规则汇总 AI、开发创造、基础设施、Apple、硬件、网络服务、职场、金融、城市消费和平台内容。板块允许交叉，因此趋势使用折线而非堆叠。两类视图分别回答“社区如何分类讨论”和“标题提到了什么”，不共用命中规则。话题详情与标题关键词详情都从当前实体的相关帖子中每年保留综合互动 Top 10，并可按年份查看该年 Top 10；按月查看时，根据相关帖子数保留 Top 3、Top 5 或 Top 10，阈值分别为 20 和 100。推广节点不进入候选。标题关键词按匹配该词或关键词组的帖子数展示每月或每年 Top 10/20/30；GPT、Agent 等关键词组在主排名中按帖子去重聚合，组内关键词仍可独立搜索、比较和查看详情。人工确认的领域词与稳定详情词达到频次、作者和节点要求后可用于详情搜索，但不改变演变榜单。构建同时输出作者和节点集中度审计报告。话题与标题关键词详情的代表评论同样按当前时间范围逐年保留感谢 Top 10 后合并；节点详情按全部历史逐年合并并最多展示 100 条。选中年份时展示该年 Top 10，选中月份时按相关帖子数展示 Top 3/5/10；评论只收录至少获得 1 次感谢的内容，并按所属帖子的发布时间归期。生命周期使用统一 7 日窗口呈现参与用户数、每人评论数、楼主参与率和 `@` 提及率。节点仅在累计达到 50 个有效帖子时收录详情，名称取自 V2EX 官方节点元数据；较小节点保留名称但不提供看板内跳转。节点详情按需加载主要话题、主要标题关键词、活跃用户及综合 Top 100 代表帖子，并支持从趋势点查看该月 Top 3/5/10 或该年 Top 10。
- 成员：成员增长、参与结构、各期成员演变、累计贡献榜，以及部分活跃成员的参与节点、发帖话题、标题关键词、代表帖子和获感谢评论。
- 互动：点击、收藏、感谢、投票及换算后的互动效率。
- 观察：基于固定比较窗口生成离线点评，将规模、成员、话题、标题关键词、互动和生命周期中的关键变化组织为可打开详情的结论。

“月度”和“年度”位于概览的二级视图。月度支持环比与同比；当前年达到 2 个完整月份后，年度默认当前年并按相同月份范围同比，否则回退最近完整年。两类视图都展示热门话题、热门标题关键词和热门节点 Top 20，以及从对应周期全量数据中独立计算的四类帖子 Top 100 和感谢评论 Top 100。周期摘要只展示超过统计阈值的同比或结构变化；未满年度不与完整年度榜单直接比较。

前端主包与 ECharts 图表运行时独立构建，规模分布、标题关键词、互动、观察、数据索引、节点详情、生命周期和概览趋势也拆为独立视图代码块。规模分布的约 3 KB 聚合结果只在进入对应子页时读取；月度和年度榜单仅加载当前所选周期及必要的同比基线，活跃时段、话题、标题关键词和节点趋势按年份读取，标题关键词、话题、节点和成员详情分别从 64 个哈希分片中按需加载。话题、标题关键词和节点的按期代表帖子拆为 256 个惰性分片；代表评论正文另拆为 2048 桶实体分片，进入相应详情时只读取一片，并在切换时间点时复用。基础加载会读取约 31 KB 的官方节点名称与可跳转节点名单；全局搜索的四类实体索引和近期候选仅在首次打开搜索时加载。空输入合并展示最近 12 个完整月份的 5 个热门话题和 5 个不重名标题关键词。“关于本站”内的数据索引复用话题、标题关键词和节点索引，支持按数量、名称和相关板块浏览；桌面端展示完整筛选结果，移动端仍在完整索引中搜索，但每次只追加渲染 60 项。移动端默认收起全局筛选，每栏榜单先展示 10 项并可展开；热力图使用固定宽度和 ECharts 范围缩放，避免长时间区间生成超宽 Canvas。

使用仓库内的 Nginx 配置构建静态站点容器：

```bash
./scripts/deploy_dashboard.sh
```

脚本会按需安装依赖、重新生成 `dist`、构建并替换带 Git 短版本标签的容器，再检查首页、manifest 和详情分片。健康检查失败时会恢复部署前镜像。容器仅监听 `127.0.0.1:3090`，由宿主机 Web 服务反向代理。JSON 请求自动携带分析清单版本：带版本的 JSON 与哈希前端资源使用长期不可变缓存，未带版本的 JSON 保留 5 分钟校验缓存；镜像预生成 Gzip 文件并由 Nginx 直接发送。

需要独立备份或传递静态分析数据时，可按 manifest 打包并在目标目录校验安装：

```bash
.venv/bin/python scripts/package_dashboard_data.py
.venv/bin/python scripts/install_dashboard_data.py dist/v2ex-dashboard-data-*.tar.gz --target /path/to/public
```

部署时也可设置 `DASHBOARD_DATA_ARCHIVE=/path/to/archive.tar.gz`，在构建镜像前校验并安装独立数据归档。现阶段仓库仍保留线上演示所需 JSON；只有稳定发布并验证归档下载链路后，才应将大体积生成数据移出 Git。

更新 README 和分享预览图时，先启动本地开发服务，再运行：

```bash
cd analysis/v2ex-analysis
DASHBOARD_URL=http://127.0.0.1:5180 npm run capture:demos
```

线上演示站使用百度统计记录访问量；统计脚本仅在服务器部署时注入，不进入仓库构建，也不参与看板分析数据。

## 测试

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python scripts/evaluate_title_keywords.py
.venv/bin/python scripts/audit_source_quality.py --fail-on-regression
.venv/bin/python scripts/validate_analytics.py
cd analysis/v2ex-analysis
npx playwright install chromium  # 首次运行
npm run build
npm run test:e2e
```

提交或部署前可运行统一检查；源数据库有变化时会先重建分析数据：

```bash
scripts/preflight_dashboard.sh
```

浏览器测试覆盖桌面和移动端交互、URL 恢复、按需加载、截图回归及 Axe 严重级无障碍检查。

安全问题、隐私或公开数据更正方式见 [安全与数据报告](SECURITY.md)。

完整数据库约 5.4 GB，不纳入 Git，当前也不随项目 Release 分发。

## 来源与维护说明

本项目基于 [oldshensheep/v2ex_scrapy](https://github.com/oldshensheep/v2ex_scrapy) 继续维护和扩展。当前版本的爬取可靠性改进、历史数据补抓工具、分析聚合及可视化看板由 Codex (GPT-5.6 Sol) 协助重构与实现。
