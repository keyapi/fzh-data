---
okf: v0.1
type: Reference
title: 「特殊规则改赛狐入库成本」执行记录 —— 下调成本受批次剩余货值约束，越消耗越改不动
date: 2026-09-20
category: workflow-issues
module: cost_adjust
problem_type: workflow_issue
component: sellfox-inventory-cost
severity: high
applies_when:
  - "要把某个 (仓库,SKU) 的入库成本按激励价下调（低于 EN 实际成本）"
  - "成本补录单审核报「货值不能为负数」"
  - "同一 SKU 报「存在待审核的补录单」"
  - "用海外仓批次表的 goodsAva 当当前库存用"
  - "要把规则表（共享 Google Sheet）里的目标成本批量落到赛狐单据上"
---

# 「特殊规则改赛狐入库成本」执行记录（2026-09-20）

## 背景

运营要在赛狐看到**低于 EN 实际成本**的激励价（按仓库 + SKU 维度）。
目标值来自共享 Google Sheet「和财务部共享」/ ws `Jeck特殊规则-订单改销售额成本` 第 844-874 行，
换算口径（见 `CONCEPTS.md`「特殊规则（订单改销售额成本）」）：

```
赛狐「采购成本」   = (发货数量1皮壳成本×系数参考值 + 发货数量1二次加工成本×系数参考值) × 汇率
赛狐「单个头程」   =  发货数量1头程运费参考值 × 汇率
汇率 = 6.8（收款币种 USD → 赛狐 CNY）
发货数量1订单尾程运费 —— 赛狐入库成本覆盖不到，本轮不管
```

**通途SKU → 赛狐SKU** 走 EN BOM 成本表的「客户物料号 → 产品编号」
（`en_bom_cost_list/EN产品BOM成本列表_*.xlsx`，本次快照 3315 行，28/28 命中）。
**发货仓 → 赛狐仓库** 走 `docs/company-context.md` 的仓库映射（USTX分公司→DANEEY、
波兰分公司→POLAND、USNJ分公司→CENTRADE）。

## 本轮结论：清单能生成，但**大部分行改不动**

生成的待执行清单：
`cost_adjust/out/特殊规则改赛狐入库成本_待执行清单.xlsx`
（56 明细行 / 6 张备货单 / 3 个 sheet：待执行明细、按备货单汇总、说明；xlsx 已被 `.gitignore` 排除，本地保留）

| 仓库 | 备货单 | 需改 SKU 数 |
|---|---|---|
| DANEEY | `OWS294A9T700007` | 19 |
| DANEEY | `OWS291A9T700003` | 19 |
| DANEEY | `OWS294A9T700008` | 3 |
| DANEEY | `OWS291A9T700004` | 3 |
| POLAND | `OWS294A9T700009` | 6 |
| POLAND | `OWS291A9T700005` | 6 |

**为什么 6 张单就够**：目标 vs 当前值比对后，只有这些备货单真的需要改。
但**「需要改」≠「改得动」** —— 见下。

### 结构性拦路虎：可下调幅度 = 当前单价 × 剩余占比

成本补录单**改的是整张备货单行，扣的是该批次此刻剩余的货值**。
所以能往下改多少，被「批次还剩多少」锁死：

```
单件可下调幅度 ≲ 当前单价 × (批次剩余可用量 / 备货单备货量)
```

实测（`KS0001-HLR-153-GINGER`，备货量 1000、可用仅 7、当前单价 179.30）：
理论下限 `179.30 × 7/1000 = 1.2551` → 最多降到 **178.045**。
试 `178.05` 过校验；试目标值 `123.76`（‑55.54/件 × 1000 = ‑55,540，而批次只剩 7×179.30 = 1,255 货值）
被直接拒：`失败原因: SKU[KS0001-HLR-153-GINGER], FnSku[], 货值不能为负数。`

**这些备货单大多已被订单/调整单吃掉大半，所以目标值根本降不到。**
这不是脚本问题，是单据模型决定的 —— 与
[`sellfox-inventory-sync-cost-drift.md`](sellfox-inventory-sync-cost-drift.md) 是同一枚硬币的两面：
那边说「可修正的批次被 FIFO 持续吃掉」，这边说「被吃掉的批次就再也降不了价」。

**推论：下调成本有强时效性 —— 要在批次还没被消耗时做（新入库单收货后立刻改）。**

### 第二个拦路虎：同 SKU 只能有一张待审核补录单

```
SKU：KS0001-HLR-153-GINGER 存在待审核的补录单
```

批量执行时必须**按 SKU 串行排队**：前一张 `audit` 通过（或 `delete`）后才能建下一张，
不能并发建单。完整约束见
[`../integration-issues/sellfox-cost-adjust-api.md`](../integration-issues/sellfox-cost-adjust-api.md)。

## 两条数据可信度教训（本轮踩到）

### ① 海外仓批次表的 `goodsAva` **不能当当前库存用**

`POST /api/overseaBatch/page.json` 的 `goodsAva` 看起来是「该批次可用量」，
抽样 30 行里 **21 行**与【库存明细】/【查询库存明细】的可用数**对不上**：

| SKU | 批次表 `goodsAva` | 库存明细可用 | 差 |
|---|---|---|---|
| `test001-white` @POLAND | 1997 | 1997 | ✅ |
| `KS0001-DM-60-ANTHRACITE` @POLAND | 1035 | 36 | ❌ |
| POLAND 组（`OWS294A9T700009` 批次） | 1000 | 实际已被 `AD2608140015` 等扣走 | ❌ 整组差约 1000 |

**要用「当前库存」就去查库存明细，不要从批次表推。**
批次表的可靠用途只有一个：**看这个 SKU 的库存由哪些来源单构成 + 该批次的历史成本**
（这正是 `probe_batches.py` 的用途），数量必须另行核对。

### ② 备货单**列表**接口的 `items` 只返回 3 条预览

据此判断「某 SKU 在不在某张备货单里」会误判成「搜不到」。
要全量明细必须用**详情**接口（`/api/oversea/detail/v2.json?id=<pickId>`，返回全部 items）。
三个「按 SKU 搜备货单」的调用面写法还各不相同，见
[`../integration-issues/sellfox-restock-headfee-api.md`](../integration-issues/sellfox-restock-headfee-api.md)
的「`searchType` 三个调用面三种约定」。

> 本轮因此连续两次误报「某 SKU 没有备货单」，用户两次纠正才查对。
> **教训：在赛狐说「没有」之前，先换一个接口/入口复核一遍。**

## 建议的下一步

1. **不要在已消耗的备货单上硬调**。要么接受「只改还有货的那部分」（改完均价也到不了目标值），
   要么等下一批入库时**在收货前/收货后立刻**把 `指定采购单价` / `单个头程费用` 填成激励价。
2. 若确实需要立刻生效，只剩「清零重入」这条重路径（成本高，用户已明确列为万不得已）。
3. 数量同步侧按 [`sellfox-inventory-sync-cost-drift.md`](sellfox-inventory-sync-cost-drift.md)
   的选项 B/C 处理，否则新入库的成本也会被调整单快照稀释。

## 相关

- [`../integration-issues/sellfox-cost-adjust-api.md`](../integration-issues/sellfox-cost-adjust-api.md) — 成本补录单两条硬约束的完整契约
- [`../integration-issues/sellfox-restock-headfee-api.md`](../integration-issues/sellfox-restock-headfee-api.md) — 改头程的唯一路径 + `searchType` 三面约定
- [`sellfox-inventory-sync-cost-drift.md`](sellfox-inventory-sync-cost-drift.md) — 数量同步让成本越来越改不动
- [`../../research/2026-09-18-sellfox-cost-accounting-fifo.md`](../../research/2026-09-18-sellfox-cost-accounting-fifo.md) — FIFO 批次与加权平均口径
- `cost_adjust/AGENT_HANDOFF.md` — 模块接手文档（含本轮新增的坑）
