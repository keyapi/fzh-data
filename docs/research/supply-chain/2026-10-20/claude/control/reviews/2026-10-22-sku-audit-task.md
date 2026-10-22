---
okf: v0.1
type: Plan
title: 通途-EN SKU 匹配只读审计任务书（C）
date: 2026-10-22
owner: claude-worker
---

# 通途-EN SKU 匹配只读审计（C）

## 背景

决策 Codex 定：先 C（SKU 匹配只读审计），再 B（ETA/Cover/UOM）。
目标是把“未匹配”拆成可执行的类别，**不自动认领、不改生产**。

## 输入（全部只读）

- `D:/Work/fzh-order-store/order_store.duckdb`：
  - `gs_orders`（`sku_tongtool`、`order_id`、`month`、`sale_date`、`qty`）
  - `sku_map`（`tongtool_sku` → `item_code`，来自 EN `Item Customer Detail.ref_code`）
  - `orders_unified`、`en_orders`（EN 侧订单，2,733 行）
- `D:/Work/fzh-order-store/sku_map.tsv`
- 现行规则：**精确等值** `ref_code == tongtool_sku`；无后缀容错。

## 口径说明（必须写进报告）

- 旧口径“6,549 行未匹配”来自 EN 订单/同步侧，本次用本地 DuckDB 复算：
  GS 订单侧 **297 个唯一 SKU / 4,115 行**未在 `sku_map` 命中。
- 两者**分母不同**，不能相加或互相替代；报告须单列，不得硬凑旧数字。

## 分类（输入 = 各类之和，逐条可追溯）

1. `base_candidate`：去掉已知后缀（`-N`、`-Cover`、`-Foam`、`-ALL`、Shopify 变体后缀等）
   后的基础码在 `sku_map` 有命中；**只列为候选**，附基础码与命中的 item_code。
2. `duplicate_mapping`：同一 `ref_code` 映射到多个 `item_code`，或同一 SKU 多个候选。
3. `true_missing`：基础码也无任何登记。
4. `insufficient_evidence`：编码异常/空值/无法按规则拆分。

每类给出：唯一 SKU 数、订单行数、首末月份、示例 10 条、可追溯的原始行键。

## 深度审计（最多 100 个唯一 SKU）

- 按订单行数排序取前 100，确保四类都有覆盖。
- 每个 SKU 输出：原始码、候选基础码、候选 item_code、命中/未命中证据、
  订单行数与首末月份、建议动作（`no_action` / `manual_review` / `register_candidate`）。
- `register_candidate` 仅表示“建议人工登记”，**不得自动写入 EN**。

## 交付

- `out/sku_match_audit/unmatched_all.csv`（全部未匹配行，含分类）
- `out/sku_match_audit/categories.json`（计数对账）
- `out/sku_match_audit/deep100.md`（深度表）
- `control/reviews/2026-10-22-sku-match-audit.md`（结论、口径、缺口）
- 不提交原始订单明细到仓库；CSV 仅本地，报告只放聚合与示例。

## 验收

- 卡片计数：输入行/唯一 SKU = 四类之和；无静默丢弃。
- 每个候选有基础码 + 命中证据；无“模糊认领”。
- 旧命中的映射不被修改；冲突单列。
- 100 个深审 SKU 覆盖四类；每个都有建议动作与证据。
- 90 分钟内完成；超时交缺口表，不延长。

## 禁止

- 不访问通途/EN 生产；不改 EN 数据；不改 `sku_map`；不做模糊匹配直接认领；
  不扩 family；不合并 PR。
