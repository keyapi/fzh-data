---
okf: v0.1
type: Reference
title: 从 Jack 分支引入的供应组件（原样搬运）
description: receipt_buckets / supply_row / overlap_gates 的来源 commit、引入方式与未引入内容
tags: [supply-chain, provenance, supply-row, overlap-gates, receipt-buckets]
date: 2026-10-27
module: supply_chain_visibility
status: verified
---

# 从 Jack 分支引入的供应组件

本目录的以下几个文件**不是本分支原创**，而是从其它分支用 `git show` 原样搬入，
用于供给净额层（`supply_netting/`）复用。内容逐字未改，方便日后与上游合并时对齐。

| 文件 | 来源 commit | 来源分支 | 说明 |
|---|---|---|---|
| `receipt_buckets.py` | `b08acc054cb12e7a4b0aa902fbb4d06a2d054910` | `Codex/supply-receipt-buckets` | 已获准自由供应的可售时间分桶纯函数 |
| `tests/test_receipt_buckets.py` | `b08acc05` | 同上 | 11 个合成用例 |
| `supply_row.py` | `6d37408566a3e209c60d4eb9f845c2c619ea8d67` | `origin/feature/en-native-supply-report-plan` | PO/库存/在途/入库统一行与校验 |
| `overlap_gates.py` | `6d374085` | 同上 | 重叠/单位/FBA/角色有序 gate |
| `tests/test_supply_row.py`、`tests/test_overlap_gates.py` | `6d374085` | 同上 | 上游自带用例 |

引入命令（可复现）：

```bash
git show b08acc05:supply_chain_visibility/receipt_buckets.py                 > supply_chain_visibility/receipt_buckets.py
git show b08acc05:supply_chain_visibility/tests/test_receipt_buckets.py      > supply_chain_visibility/tests/test_receipt_buckets.py
git show 6d374085:supply_chain_visibility/supply_row.py                      > supply_chain_visibility/supply_row.py
git show 6d374085:supply_chain_visibility/overlap_gates.py                   > supply_chain_visibility/overlap_gates.py
git show 6d374085:supply_chain_visibility/tests/test_supply_row.py           > supply_chain_visibility/tests/test_supply_row.py
git show 6d374085:supply_chain_visibility/tests/test_overlap_gates.py        > supply_chain_visibility/tests/test_overlap_gates.py
```

## 没有引入的内容

- `receipt_bridge.py` / `receipt_coverage.py` / `receipt_reconciliation.py` / `supply_integration.py`：
  本轮净额层不需要，且它们自带实验期口径。
- `docs/research/*` 与 `key_test/*`：属于 Jack 的报表/调研产物，不复制。
- 旧实验脚本里的 `compute_row`（首桶塞全部供应）与 `harvest_total`（按运单号去重）**明确不复用**。

## 维护约定

1. 这些文件保持逐字一致；需要改口径时先在 `supply_netting/` 写适配层，不要就地改上游文件。
2. 上游合并进 main 后，本目录的副本应被上游版本替换（内容相同，冲突可忽略）。
3. 与 `b08acc05` 同批的 `docs/reference/receipt-buckets.md` 尚未引入；口径以本文件与
   `supply_netting/docs/reference/netting-engine.md` 为准。
