# 本地数据与部署

GitHub Release 仅发布代码，不附带 SQLite 数据库、分析 JSON、数据归档或 `dist`。历史数据 Release、对应标签和下载入口已移除，不再通过 GitHub 自动下载分析数据。

## 生成分析数据

从本地抓取库 `v2ex.sqlite` 构建并校验：

```bash
.venv/bin/python analysis/build_analytics.py --if-changed
.venv/bin/python scripts/validate_analytics.py
```

JSON 写入忽略的 `analysis/v2ex-analysis/public/`。新克隆只有代码，需自行准备本地数据；缺少分析数据时，部署脚本会明确报错，不再请求已失效的 Release 地址。

## 本地归档与恢复

保留基于 manifest 的打包、SHA-256 校验及原子恢复工具，仅用于本地数据迁移或恢复，不自动上传：

```bash
.venv/bin/python scripts/package_dashboard_data.py --output dist/dashboard-data-local.tar.gz
.venv/bin/python scripts/install_dashboard_data.py dist/dashboard-data-local.tar.gz
```

恢复时需同时保留 `.tar.gz.sha256` 校验文件。归档包含 schema、规则哈希、生成时间与源记录数，不包含原始 SQLite 数据库。归档和分析 JSON 均不进入 Git。

## 线上部署

本地完成前端构建和检查后，只上传 `analysis/v2ex-analysis/dist/` 的压缩归档到服务器，不上传源码、Git 目录或 SQLite 数据库。操作步骤与回滚说明见 [运行与维护](OPERATIONS.md)。
