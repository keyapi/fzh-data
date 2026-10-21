---
okf: v0.1
type: Review-Response
title: 对 Codex #301 `862f77d1` family SO PoC 复审的修复记录
description: S01–S04 修复、同窗 SO 重跑结果与 pending 解释
date: 2026-10-21
tags: [supply-chain, family-poc, codex, review, round5]
---

# 对 Codex #301 `862f77d1` family SO PoC 复审的修复记录

> U01 与前轮 T 项不重做；本轮修 S01–S04，并用同一 2026-04..09 窗口重跑 SO PoC。

| ID | 修复 | 证据 |
|---|---|---|
| S01 | **统一日期口径**：`--date-basis delivery|transaction`，默认 `delivery_date`；group、item_code、pilot 三类来源全部用同一日期字段过滤，不再混算；pilot 客户码也带日期过滤 | manifest `date_basis=delivery_date`，三类 source 都有 pages/complete |
| S02 | **family manifest 真正接入**：BOM 969 个 KS item（KS0001/KS0248）、1,486 个客户码、2,907 个查询码（KS + PK# + ND#）；行级角色 `KS/PK/ND/group/customer`；PK#/ND# 但 base 不在 family 的记 `pending`，不直接算 non-family | `family_manifest_sha256`；`line_roles`：PK 813 / KS 132 / ND 565 / unknown_prefix 392 / other 122 |
| S03 | **不再静默截断**：`candidate_sos`、`selected_sos`、`truncated`、`max_sos` 入 manifest；超限 `status=partial`、exit 1；本批 52<500 未截断 | `candidate_sos=52, selected_sos=52, truncated=false` |
| S04 | **partial/逐行状态**：`detail_failed`、`line_dispositions`、`status/status_reasons`、`out_sha256`、`script_sha256`、`run_id` 入 manifest；缺详情不当作成功 | `detail_failed=[]`，`status=complete` |

## 同窗 SO 重跑结果（2026-04..09，delivery_date）

| 项 | 数值 |
|---|---:|
| 候选 / 选中 SO | 52 / 52 |
| family 行 | 1,510 |
| pending 行 | 392 |
| out_of_scope 行 | 122 |
| group 来源 | 132 行 / 2 页 |
| item_code 来源 | 945 行 / 75 页 |
| pilot 来源 | 89 行 / 10 页 |
| 10 个试点客户码 | 10/10 命中 |
| run status | `complete` |

- `line_roles`：PK 813、KS 132、ND 565、unknown_prefix 392、other 122。
- 392 `pending` 是 **PK#/ND# 但 base 不在 KS0001/KS0248** 的行；按 E01 不直接判 non-family，
  需 family manifest 版本/历史角色再裁定。
- **1,510 是 SO 行，不是 33,719 终端出库件数**；SO 窗口/交付日期与终端出库窗口不能直接对等。

## 仍然未做

- pending 392 的逐行裁定（历史角色/包装组件/别名）。
- DN/WO/JC/SE 段；`modified` 水位/tombstone/失败重跑回归；同单位守恒。
- 当前 status=complete 只表示本次 SO 批次自身完整，不是 G1 验收。
- Wayfair/旧仓迁移继续 pending。

## 复现

```bash
uv run python en_family_poc.py --date-from 2026-04-01 --date-to 2026-09-30 \
  --date-basis delivery --out out/family_poc/family_so_lines_v3.jsonl
```

manifest：`out/family_poc/family_poc_manifest.json`（本地，不入库）。
