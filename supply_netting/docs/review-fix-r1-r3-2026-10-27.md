---
okf: v0.1
type: Report
title: 第二轮复审 R1–R3 返修与 r5 复算（2026-10-27）
description: 合法拆分谱系、混合未知期初、预测哈希校验；r5 数字未变
tags: [acceptance, netting, forecast, review-fix, r5]
date: 2026-10-27
status: verified
---

# 第二轮复审返修（R1–R3）

来源：`C:/Users/zhang/.agent-ops/fzh-data/reviews/supply-review2-36453827.md`（verdict=reject）。
在 `36453827` tip 上继续，保留 F1–F4 与 r5，不 push、不写生产。

## 1. 修复

### R1（P1）合法同批拆分被去重误删

根因：`split_balance` 写了 `split_of`，但 `Tranche`/`SupplyRow` 没保留谱系，
`apply_batch_quota` 按 `sku/仓/UOM/batch_key` 每组只留一个 best，把 6+4 拆成 6。

修法：

- `StageBalance` / `Tranche` 增加 `split_of`；`StageBalance` 增加 `split_total`（父余额数量）。
- `split_balance` 写入 `split_of` 与 `split_total`；`validate_stage_balances` 校验
  同一父的子额度合计必须等于 `split_total`（不一致直接报错）。
- `tranches_to_supply_rows` 把子额度身份写进 `document_key = "split-quota:<balance_id>"`。
- `apply_batch_quota` 分组键改为 `(sku, 仓, UOM, batch_key, 额度身份)`：
  - 同一父的 6/4 是不同额度 → 各自保留数量与日期；
  - **没有**拆分谱系的同批跨阶段观察/重放仍是同一额度 → 只计一次；
  - 同一批次同时出现「拆分」与「整批观察」时两侧都保留（不能静默丢弃已证数量），
    但按批次上报 `batch_split_conflicts`，进 manifest 的 `checks`。

回归（`tests/test_review2_r1_r3.py::R1SplitLineage`）：

- 已证批次 6+4 → `expected protect receipts=10, gap=0`（不是 6/4）；
- 两个子额度保留各自的可售日；
- 篡改 `split_total` → validator 报「父余额声明不一致」；
- 无谱系同批跨阶段 → 仍只计 10；
- 拆分 + 整批观察 → 两侧保留、`batch_split_conflicts=1`。

### R2（P2）混合已知 + 未证期初被当成精确小计

根因：`opening_basis` 只要有一条 included 就返回小计，`qty=None` 的 excluded 被静默隐去。

修法：把 excluded 分成「明确不计（FBA/重放/身份冲突）」与「可能属于基准但未证」：

- 存在后者 → `opening=None`、`reason=opening_partially_unproven`，
  并给出 `opening_lower_bound`（已知部分合计）；
- 桶行 `gap` 保持 `null`（`status=unknown`），不再报出「精确缺口 10」；
- 只有明确排除行时才是 0（`all_opening_excluded`）；
- 完全无基准行时 `opening=None`、下界 `null`。

`opening_lower_bound` 同时写进逐桶明细与 `replenishment_review`，
manifest `checks` 增加 `opening_rows_unproven`。

回归（`R2MixedOpening`）：已知 10 + 未知 null → `opening=null`、下界 10、`gap=null`；
纯未知 → 下界 0；已知 10 + FBA 4 → 仍是精确 10。

### R3（P2）预测入口未校验上游 manifest 声明

修法：`load_forecast` 在消费前按**准确文件名**读取
`forecast_manifest.outputs` 的 `sha256` 与 `rows`：

- 未声明该文件 / 重复声明 / sha256 缺失 → `ForecastContractError`；
- 实测哈希或行数与声明不符 → `ForecastContractError`（带两侧哈希）；
- 新增 `--forecast-manifest-sha256`，可固定上游 manifest 本身；
- 校验结果写进 manifest：`windows_sha256_verified=true`、`manifest_sha256_verified=true`。

回归（`tests/test_forecast.py`）：篡改哈希被拒、空/重复 outputs 被拒、
声明行数不符被拒、CLI flag 可解析。

## 2. r5 复算

代码变化不影响真实数据的计数路径（真实阶段余额没有已证批次 → R1 不触发；
已映射期初全部数量已知 → R2 不触发；R3 只是新增校验），因此**重跑复算**而非改写：

| 指标 | 复审值 | 本次重跑 |
|---|---:|---:|
| 代码 commit | f730b162 | **2d312277**（R1–R3 + 明细下界列，`git_dirty=false`） |
| 净额键 / 行 | 545 / 5,450 | 545 / 5,450 |
| 期初合计 | 17,689 | 17,689 |
| 保护期需求 / 缺口 | 311.447713 / 34.867936 | 相同 |
| 保护期缺口键 | 71 | 71 |
| 视界末累计未满足 | 449.966544 | 449.966544 |
| 已证到货 | 0 | 0 |
| 供应事实行 / outside | 9,827 / 2,609 | 9,827 / 2,609 |
| 预测 | forecast-20261027-r2 | 相同，且窗口/manifest 哈希**已校验** |
| 逐桶 `opening_lower_bound` | 无此列 | 新增；2 个无基准键为 null |

新增 manifest 字段：`checks.opening_rows_unproven=0`、`checks.batch_split_conflicts=0`
（真实数据没有这两类输入）、`replenishment_review.opening_lower_bound`（543 个键等于期初，
2 个无基准键为 null）。`pack-2026-10-26-r5` 重跑后 545 行 / 71 缺口键 / 建议分布不变。

## 3. 测试

| 范围 | 数量 | 结果 |
|---|---|---|
| `supply_netting/tests`（含 R1–R3 回归 9、预测哈希拒绝 3） | 136 | 全通过 |
| `supply_chain_visibility/tests` | 23 | 全通过 |
| 合计 | **159** | 全通过 |

## 4. 仍然存在的缺口（与上一轮一致）

1. 历史订单全部早于 as_of，净额需求只来自预测；as_of 到预测起点 2.779 天无需求数据。
2. 在途/通途 PO 无逐行 ETA，已证到货全桶为 0；条件供应 11,305 不能直接抵缺口。
3. 未履约 SO 未接入；工厂 SO 管线只在动作层。
4. 预测只覆盖通过资格的 582 销售键；未覆盖键不能解释为零需求。
5. 阶段余额仍只有通途在途 193 条，无已证批次；R1 的机制由合成例证明。
6. F5 estimated 日期规则未做；服务缓冲未含实测提前期。
7. `batch_split_conflicts` 机制已就位但真实数据为 0，接入真实批次后需复核。

r5 仍只是 2026-10-26 快照 + 2026-10-29 预测起点的**条件情景**，
不构成采购指令，也不代表供应功能验收。
