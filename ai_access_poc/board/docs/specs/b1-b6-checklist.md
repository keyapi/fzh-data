---
okf: v0.1
type: Spec
title: 板 PoC B1–B6 验收清单
description: 对照统一 AI 接入计划板成功标准
tags: [spec, board-poc, ivyeaops, sellfox]
timestamp: 2026-07-24
depends_on:
  - docs/research/2026-07-24-unified-ai-access-poc-plan.md
---

# B1–B6 Checklist

| ID | 任务 | 验收 | 状态 |
|----|------|------|------|
| B1 | clone IvyeaOps → `d:\Work\赛狐\IvyeaOps-sellfox`，分支 `sellfox-readonly-poc` | 目录存在；`README_SELLFOX_POC.md` | **Pass** |
| B2 | `sellfox_openapi` + probe 店铺列表 | proxy `count=99`（2026-07-24） | **Pass** |
| B3 | sellers 规范化 sid/shop_id | `list_sellers_rows` 含 name/shop_id | **Pass** |
| B4 | createTask/xlsx→规范化 cache；aggregate | 1922 行 → `board/cache/sp_search_term_report__poc.json` | **Pass** |
| B5 | optimizer 搜索词杠杆；operate 硬禁 | 候选 19（否词 17 / 收割 2）；confirm_ticket 禁写 | **Pass** |
| B6 | TOODDLY-Daneey-US + 偏差清单 | `out/candidates.csv` + `reference/deviations.md` | **Pass** |

## 证据路径

- 独立跑通：`uv run python ai_access_poc/board/scripts/sellfox_board_poc.py --xlsx …17_2026-07-23.xlsx`
- 输出：`ai_access_poc/board/out/candidates.json`（gitignore）
- IvyeaOps 适配：`sellfox_openapi.py` / `sellfox_ingest.py` + data/optimizer/operate 补丁

## 成功标准（总）

赛狐代理通；sellers + 规范化搜索词可读；否词/收割候选非空；写路径禁用；密钥/xlsx 不进 git。
