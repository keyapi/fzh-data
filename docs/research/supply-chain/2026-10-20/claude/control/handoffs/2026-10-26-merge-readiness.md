---
okf: v0.1
type: Handoff
title: W1 合并就绪清单（#311 / #312）
date: 2026-10-26
owner: claude-foreman
channel: docs/jack-w1-channel
---

# W1 合并就绪清单

> 给负责审核/合并的会话用。**两个 PR 都还是 draft，未合并。**
> 一句话：**先合 #311（docs/contracts），再 rebase #312，最后合 #312（code）**。

## 1. 顺序

1. **#311** `docs/jack-w1-channel` → `main`：docs/contracts，无代码、无 CSV。
2. 合并后，`main` 有 `experiments/sc14/`；**rebase #312** 到最新 `main`。
3. **#312** `feature/jack-supply-timeline` → `main`：W1 代码；rebase 后跑测试。
4. 最后合并 #312。

> 反过来合 #312 会让 `test_canonical_matches` 继续依赖 docs 分支/网络 fetch。

## 2. #311 检查

| 项 | 状态 |
|---|---|
| 文件数 | 63，docs/contracts |
| 业务 CSV | 无 |
| `check_secrets.py` | 零输出 |
| SC14 canonical | 已含 `experiments/sc14/`（21 用例） |
| 9 SKU / 问答 / 数据地图 | 已含 |
| #291 履约入口 | 已在 main，不重复 |
| D33 | 无行级数量 JSON；Markdown 聚合/样本表已审 |

## 3. #312 检查

| 项 | 状态 |
|---|---|
| 文件 | 16 个，`experiments/supply_timeline/` |
| 行级数量 JSON | 无；`frozen`/`wo_audit` 值在本地 `local/`（gitignore） |
| 标识/映射 JSON | `sample_skus.json` / `warehouse_map.json`，用户已确认保留（无数量） |
| SC14 | 21/21；离线 unittest 无 canonical 时 1 skip 是预期 |
| 同步测试 | `tests/run_canonical_tests.py` → 19 passed / 0 skip（rebase 后应 0 skip） |
| W1 | 233 行；B_min 1,212；B_max 2,762 + 433 个 |
| SC04 | 39 DN / 47 号 / 4,279 行 / FBA 17，差 0 |
| 核心逻辑 | A11 diff 不含 `w1_supply_timeline.py`，数字沿用 v0 |

## 4. 业务确认（不阻塞技术合并）

| 项 | 当前处理 | 确认后 |
|---|---|---|
| PO `status=4` 语义 | 只进 B_max，`semantics=unproven` | 若确认未结/已结，调整 B_min/B_max |
| `FZH-DANEEY-成品仓/半成品仓` 运营方 | `warehouse_scope=own`，`confidence=assumed` | 若 DANEEY 3PL 运营，改 `3pl` |
| `WayfairCG-Cranbury` | `3pl`，`assumed` | 归属确认后升级 |
| 波兰 `FZHPoland-covers` | `own`，`assumed` | EN 映射确认后升级 |

> 下游 `supply_own_*` 用 **`scope=in_house`** 判断“我方库存”，**不要用 `warehouse_scope=own`**；
> `warehouse_scope` 只用于运营方展示。

## 5. 不要做

- **不要合 #300**：含 32 个业务 CSV。
- **不要先合 #312**：SC14 同步测试会 skip。
- **不要 push 行级 CSV/JSON**：值在本地 `out/` / `local/`，已 gitignore。
- **不要在未确认状态语义前把 PO021735 当已关闭**。

## 6. 合并后

- `main` 上跑 `experiments/sc14/test_contract.py`（21/21）与 `supply_timeline/tests/run_canonical_tests.py`（19/0）。
- 把 W1 结果接入 SC09/W3 时，仍按 `scope=in_house` / `conversion_assumed` / `coverage` 规则；不直接当采购量。
