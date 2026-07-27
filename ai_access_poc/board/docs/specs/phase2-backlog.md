---
okf: v0.1
type: Spec
title: Phase2 待办 — 跟上游 / 五杠杆 / 规则包
description: 体验优先 Phase1 之后的扩能力清单（写广告仍禁）
tags: [ivyeaops, sellfox, phase2, backlog]
timestamp: 2026-07-27
---

# Phase2 backlog（写路径仍硬禁）

## 1. 紧跟上游 IvyeaOps

```text
cd d:\Work\赛狐\IvyeaOps-sellfox
git remote add upstream https://github.com/Hector-xue/IvyeaOps.git   # 一次
git fetch upstream
git merge upstream/main
```

冲突优先落在：`lingxing_data.py` / `lingxing_optimizer.py` / `lingxing_operate.py`。  
新文件 `sellfox_openapi.py` / `sellfox_ingest.py` 一般无冲突。  
**不要**把 AGPL 整树 vendoring 进 fzh-data。

## 2. 更多赛狐报表 → 五杠杆

| 杠杆 | 需要的数据集 | Phase1 |
|------|----------------|--------|
| 否词 / 收割 | `sp_search_term_report` | 已通 |
| 降 bid / 加 bid | `sp_keyword_report` (+ keywords 实体) | 未接 |
| 加预算 | `sp_campaign_report` | 未接 |
| 目标 ACOS 按毛利 | `asin_profit` / product ads | 未接（现用默认 30%） |

做法：查赛狐 OpenAPI 是否有对等报表 → 扩展 `sellfox_ingest` → `fetch_dataset` 分支 → 再跑 Optimizer。仍保持 `confirm_ticket` 硬禁。

## 3. 百家之长（本地 overlay，不 PR 上游）

放在 **fzh-data**（非 AGPL 公开仓义务）：

- 老板提示词 / 运营原则 → `ai_access_poc/board/rules/`（YAML/JSON rule pack，待建）
- 外部 skill 灵感（含 fork 内 `skills/amazon/zach-search-term-report-analyzer`）→ 提炼阈值，校准 `deviations.md`
- Portal 落地页链到 `http://127.0.0.1:8001`（仍不嵌 SPA）

## 4. 明确继续不做

- 赛狐广告写 API 未开放前的自动否词/改价  
- 运营审强制签字（仍 DEFERRED）  
- DeepWiki 当唯一真相（以 GitHub / 本地 fork 为准）  
