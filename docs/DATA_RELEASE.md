# 看板数据发布

`analysis/v2ex-analysis/public/dynamic-*.json` 由离线分析器生成，体积约 490 MB，不进入 Git。代码仓库只跟踪 `analysis/dashboard-data.lock.json`，静态数据以 GitHub Release 资产独立发布。

## 安装锁定数据

新克隆没有本地 `v2ex.sqlite` 时，先安装锁定的数据版本：

```bash
.venv/bin/python scripts/fetch_dashboard_data.py
```

下载器只接受本仓库的 HTTPS Release URL，验证归档大小和 SHA-256，并在暂存目录校验文件清单后原子替换 `public/` 中的旧数据。归档缓存在忽略的 `dist/dashboard-data/`；`--offline` 可复用已验证缓存，`--check` 只检查当前安装。

## 发布新数据

1. 更新源库并构建、校验分析数据。
2. 使用唯一 Release 标签打包，并同步生成锁文件。
3. 提交并推送代码和锁文件。
4. 创建 Release，上传归档及 SHA-256 sidecar。

```bash
.venv/bin/python analysis/build_analytics.py --if-changed
.venv/bin/python scripts/validate_analytics.py
.venv/bin/python scripts/package_dashboard_data.py \
  --release-tag dashboard-data-YYYY-MM-vSCHEMA-YYYYMMDD \
  --lock-output analysis/dashboard-data.lock.json

gh release create dashboard-data-YYYY-MM-vSCHEMA-YYYYMMDD \
  dist/v2ex-dashboard-data-YYYY-MM-schema-vSCHEMA.tar.gz \
  dist/v2ex-dashboard-data-YYYY-MM-schema-vSCHEMA.tar.gz.sha256 \
  --repo taifuer/v2ex_scrapy --title "Dashboard data YYYY-MM (schema vSCHEMA)"
```

Release 标签和资产视为不可变。修正同一月份的数据时创建新标签并更新锁文件，不覆盖已有资产。回滚只需恢复上一版锁文件并重新安装、构建和部署；完整 SQLite 数据库仍不随 Release 分发。
