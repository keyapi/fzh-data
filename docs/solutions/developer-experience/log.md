---
okf: v0.1
type: Log
title: developer-experience — 变更日志
tags: [solutions, developer-experience, log]
---

# developer-experience 变更日志

## 2026-10-29

- **新增**: `erpnext-wayfair-sync-timezone-pitfalls.md` — Frappe `now_datetime()` 是站点本地 naive（当 UTC 会偏 8h）；tz-aware 时间进 MariaDB 报 1292、进 DuckDB TIMESTAMP 被转本地时区；Parquet 去重要让本次覆盖历史；`json.dumps(Path)`、Single 新字段默认值不回填、`bulk_insert` 需补系统字段；远程用 `exec(open(...))` + 写 JSON 结果。

## 2026-10-28

- **新增**: `gitignore-sensitive-pattern-hides-source-module.md` — `.gitignore` 的 `*token*` 会静默漏掉正常源码与测试（本次 `token_cache.py`）；本地测试与增量部署都正常，干净 clone 才暴露。用 `git check-ignore -v` / `git ls-files` / clean-tree import 检查。
