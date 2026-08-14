---
okf: v0.1
type: Reference
title: Google Sheet gspread 本地凭证
description: 从 Colab notebook 抽出 service account，本地 gitignore，供 Agent 读写 Google Sheet
tags: [gspread, google-sheet, credentials, gitignore]
resource: tongtool_order_cost/tongtool_order_cost/gsheets.py
timestamp: 2026-08-14
---

# Google Sheet 本地凭证

Colab notebook 第 0 格内嵌 `gspread.service_account_from_dict(credentials)`。项目标准是：**私钥只留本机**，与 `EN_API/.env`、`tongtool_api/.env` 相同分层。

## 文件

| 路径 | 是否入 git | 作用 |
|------|------------|------|
| `tongtool_order_cost/.env.example` | 是 | 指出 `GSPREAD_SERVICE_ACCOUNT_FILE` |
| `tongtool_order_cost/.env` | 否 | 本机路径覆盖 |
| `secrets/gsheets-service-account.json` | 否 | service account 全文 |
| `secrets/README.md` | 是 | 目录说明 |

## 一次性初始化

```bash
uv run python tongtool_order_cost/scripts/bootstrap_gsheets_credentials.py
```

默认读 Google Drive 同步的 20260706 特殊规则 notebook cell 0。可用环境变量 `COLAB_NOTEBOOK_PATH` 覆盖。脚本**不打印** `private_key`。

Service account 必须已被分享到目标 spreadsheet（例如「通途订单202606」「和财务部共享」），否则 `gc.open(title)` 会失败。

## Agent 用法

```python
from tongtool_order_cost.gsheets import client, gsheet2df
gc = client()
df = gsheet2df(gc, "通途订单202606", "写回2026年6月FBA订单和非FBA订单")
```

写回必须用户确认范围；用 `scripts/remap_gsheet_sku.py`（默认 dry-run）。

## 禁止

- 不要把 notebook 私钥粘进 SKILL / 文档 / commit
- 不要在 `~/.codex/config.toml` 或项目 `.cursor` 配置里再存一份可提交的 JSON
- PR 前扫描凭证（见根目录 `CONTRIBUTING.md`）
