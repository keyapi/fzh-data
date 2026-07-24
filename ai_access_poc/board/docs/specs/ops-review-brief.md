---
okf: v0.1
type: Spec
title: 板 PoC 运营审阅简报
description: 双 PoC 技术绿后，运营对照偏差清单与候选 CSV 的签字前审阅清单（计划 §4）
tags: [spec, ops-review, board-poc, sellfox]
timestamp: 2026-07-24
depends_on:
  - docs/research/2026-07-24-unified-ai-access-poc-plan.md
  - ai_access_poc/board/docs/specs/b1-b6-checklist.md
  - ai_access_poc/board/docs/reference/deviations.md
---

# 运营审阅简报（签字前）

> **状态**：壳 #113 + 板 #116 已合并；技术验收 B1–B6 / S1–S4 绿。  
> **本简报目的**：组织运营负责人完成计划 §4「运营校验」——**签字前不得把候选当自动执行依据**。

## 审什么

| 材料 | 路径 | 说明 |
|------|------|------|
| 偏差清单 | `ai_access_poc/board/docs/reference/deviations.md` | D1–D6；阈值与归因窗口 |
| 候选 CSV | `ai_access_poc/board/out/candidates.csv`（本地，gitignore） | 否词 / 收割建议 |
| 候选 JSON | `ai_access_poc/board/out/candidates.json` | 含阈值与 `write_blocked` |
| 列映射 | `ai_access_poc/board/docs/reference/column-mapping.md` | 赛狐 xlsx ↔ 优化器 |

## 标定跑通快照（2026-07-24）

| 项 | 值 |
|----|-----|
| 店铺 | TOODDLY-Daneey-US |
| 窗口 | 2026-07-17 → 2026-07-23（7 天整窗 aggregate） |
| 规范化行 | 1922 → 唯一搜索词 1389 |
| 候选 | **19**（否词 17 / 收割 2） |
| 阈值（IvyeaOps 默认） | 否词 ≥15 点击且 0 单；收割 ≥3 单且 ACOS ≤30% |
| 写路径 | **硬禁** — 仅导出 CSV，人工去赛狐后台 |

重跑（仓库根目录）：

```text
uv run python ai_access_poc/board/scripts/sellfox_board_poc.py --xlsx ai_access_poc/open_webui/reports/SearchTerm_TOODDLY-Daneey-US_2026-07-17_2026-07-23.xlsx
```

## 请运营标三类（每条候选或整体阈值）

1. **可直接用** — 对照后台合理，阈值可沿用  
2. **阈值要改** — 写明新阈值（点击 / 订单 / 目标 ACOS），回填 `deviations.md`  
3. **不适用家纺** — 说明原因；此类杠杆本阶段关掉或改规则

## 审完后代码侧才可开

- Portal：nginx `/chat` + `/ops` + 钉钉（**新专题，需确认启动**）  
- 扩展 READ_DATASETS；赛狐广告写 API 上线后再谈 operate  

## 明确不做（本阶段）

自动否词/加词执行、全量看板、未签字候选当真理。
