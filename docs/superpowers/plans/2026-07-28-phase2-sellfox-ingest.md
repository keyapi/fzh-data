# Phase2 Sellfox 五杠杆 ingest 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把赛狐已验证可映射的源接到 IvyeaOps `fetch_dataset`，使 optimizer 五杠杆（否词/收割/降bid/加bid/加预算）在只读 PoC 下都能出候选；写路径仍硬禁。

**Architecture:** 扩展 `IvyeaOps-sellfox` 的 `sellfox_ingest`（xlsx/API → `sellfox_cache/{dataset}__{sid}.json`）+ `lingxing_data.fetch_dataset` 在 `SELLFOX_READONLY_POC=1` 时读缓存；fzh-data 只保留薄脚本/文档，不 vendor AGPL。

**Tech Stack:** Python 3.10+、pandas、Sellfox Proxy（`SELLFOX_API.client`）、现有 aggregate 窗模式。

**注意：** 五杠杆 ≠ advertise 五桶（Harvest/Negate/…）。见 `CONCEPTS.md`。

---

## File map

| 文件 | 职责 |
|------|------|
| `IvyeaOps-sellfox/server/app/services/sellfox_ingest.py` | 多 dataset normalize + cache R/W + pull |
| `IvyeaOps-sellfox/server/app/services/lingxing_data.py` | PoC 分支读各 dataset cache |
| `IvyeaOps-sellfox/server/app/services/sellfox_openapi.py` | 可选：manageData / profit 薄封装 |
| `ai_access_poc/board/scripts/ingest_sellfox_*.py` | 一键拉齐标定店 |
| `ai_access_poc/board/docs/specs/phase2-*` | 状态从「未接线」→「已接线」 |

---

### Task 1: 通用 cache + sp_keywords / sp_campaigns（实体）

**Files:**
- Modify: `sellfox_ingest.py`, `lingxing_data.py`

- [ ] **Step 1:** `dataset_cache_path(data_dir, dataset, sid)`；旧 search-term path 兼容
- [ ] **Step 2:** `paginate_manage_data(client, path, shop_id)` → 全量 `itemList`
- [ ] **Step 3:** normalize `spKeyword` → `{keyword_id, keyword_text, match_type, bid, state, campaign_id, ad_group_id}`
- [ ] **Step 4:** normalize `spCampaign` → `{campaign_id, name, state, daily_budget}`（`budget`→`daily_budget`）
- [ ] **Step 5:** `fetch_dataset` PoC：读 cache，按 `offset`/`length` 切片
- [ ] **Step 6:** 对 BJRYECLTD-US 实拉，打印 count + sample bid/budget；写简短 boil-lake 行数报告

---

### Task 2: sp_keyword_report（Targeting 过滤）+ sp_campaign_report

- [ ] **Step 1:** `pull` `adTargeringReport` / `adCampaignReport`（扩展 client 或复用 create_report_task）
- [ ] **Step 2:** Targeting：仅 `匹配类型 ∈ {广泛匹配,词组匹配,精确匹配,主题匹配}`；`广告投放ID`→`keyword_id`，`投放`→`keyword_text`，花费→`cost`
- [ ] **Step 3:** Campaign：`广告活动ID`→`campaign_id`，花费→`cost`
- [ ] **Step 4:** wire `fetch_dataset`；aggregate 模式返回全量（与 search term 一致）
- [ ] **Step 5:** 跑 optimizer 标定店，确认出现降bid/加bid/加预算候选（否词/收割已有）

---

### Task 3: asin_profit

- [ ] **Step 1:** `monthProfit/asin.json` → rows with `grossRate` from `grossProfitRate`（小数或百分数归一）
- [ ] **Step 2:** wire `fetch_dataset("asin_profit")`；meta 标注 cost caveat
- [ ] **Step 3:** 确认 `_store_margin` 不再 fallback 默认 30%（有数据时）

---

### Task 4: board 脚本 + 文档 + fzh-data commit

- [ ] 扩展 ingest 脚本（默认 BJRYECLTD-US）
- [ ] 更新 `phase2-dataset-gap.md` 四态；`log.md`
- [ ] commit（不含 xlsx/密钥）；IvyeaOps 侧单独 commit

---

## 不做

- 广告写 API / operate 放开
- SB/SD / 小时报告
- 上游 IvyeaOps merge、IvyeaAgent
