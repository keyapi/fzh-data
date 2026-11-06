---
okf: v0.1
type: Reference
title: 通途订单全集：作废原单、拆分子单、原始表与 FBA 销量表的口径陷阱
date: 2026-11-05
category: workflow-issues
module: tongtool_order_cost
problem_type: workflow_issue
component: tooling
severity: high
symptoms:
  - "月度金额比财务/旧写回多出一截，或少了一块 FBA"
  - "同一个月重跑结果不一致；20 单没有发货时间"
  - "拿 写回YYYYMM 当订单全集，出现作废原单/重复拆分单"
root_cause: "订单全集混入 invalid 原单；GS 写回表是 Colab 输出而非原始数据；FBA 销量报表与 EN 明细粒度不同"
resolution_type: fix
tags: [order-universe, invalid-orders, split-orders, fba, raw-vs-writeback]
---

# 通途订单全集：作废原单、拆分子单、原始表与 FBA 销量表的口径陷阱

## Problem

做 8/9 月绍兴发货成本时，按 GS「写回…」表取订单号，结果把 **20 个作废原单**（`invalid=1`）也计入；同时发现写回演练 **FBA 行 = 0**，四列合计只是自发货口径。

## Symptoms

- EN 里 `invalid=1` 的原单仍有明细/金额；拆分子单 `_1/_2` 才是有效发货单。
- GS 原始 `2026年X月订单` 不含这些作废原单；`写回…` 是 Colab 加工后的输出，含原单。
- 20 个订单 EN `despatch_complete_time` 为空：原始报文 `orderStatus=waitPacking`、`packageInfoList=[]`、`despatchCompleteTime=""`，即通途侧未发货/无包裹；GS 的「发货日期」是表侧维护（销售日 +0~3 天），不是通途发货时间。
- 通途 FBA 原始 ws 是**按 MSKU/SKU 汇总的销量报表**，不是订单明细；EN 自动同步 FBA 明细，因此 EN 数量常比旧导出多。

## What Didn't Work

- 用 EN 订单行存储成本"重算"再和 EN 存储 `sx_shipping_cost` 比：规则自洽，但输入是同步时点值（会陈旧），不能证明成本正确。
- 拿 `写回YYYYMM` 当订单全集：把 Colab 的作废原单/合并结果一起带入。
- 用 FBA 销量报表的「成本/头程费用」做 canary 旧值：这是报表汇总口径，不是写回四列，制造了 +12.49/−43.35 的假差异。

## Solution

1. **订单全集用 EN 有效单**：`invalid=0`；`invalid=1` 原单只作 aux 校验（原单件数/金额 vs 有效子单之和，实测 18/18 相等），不参与成本。
2. **保留拆分子单**：`_1/_2` 是有效单；件数按 Cover/整件口径，不把组件行 qty 相加；无载体时用原单锚定，原单不得与子单叠加。
3. **GS 原始表 vs 写回表**：业务骨架用原始 `2026年X月订单` + `2026年X月FBA订单`；`写回…` 只作历史对拍，不作订单全集。
4. **FBA 成本用 EN 明细**：GS FBA 销量表作 78 列输出骨架；建桥接（月/账号/站点/MSKU/SKU/数量/EN 行/产品/Bundle），同 MSKU 多行按 qty 分摊；合并表带 `fulfillment` 与唯一键。
5. **重导 FBA 验证**：2026-08 新导出 147 行/2,066 件 vs 旧 146/1,966（+100），已更新 GS；09 无变化。
6. **无发货时间单**：20 单是通途侧未发货（无包裹），不是同步窗口漏；用 GS 日期补月份并在核对页标注，不能当通途发货时间。

## Why This Works

- 作废原单与有效子单是"同一业务"的两种表示，同时计入必然重复；只留有效子单与"件数守恒"一致。
- EN 是订单权威源、能补 FBA 明细；GS 销量报表只保留业务粒度，不承担成本粒度。
- 原始表与写回表分离，避免 Colab 的历史合并逻辑污染成本全集。

## Prevention

- 每个 run 记录 manifest/hash：订单、EN 明细、BOM、Bundle、仓库映射、白名单版本。
- 输出 `未匹配/待审/重复` 三类清单；FBA vs 自发货按 `fulfillment+月份+账号/平台+业务键` 去重。
- canary 旧值只从目标写回表取，不从上游销量报表取。

## Related

- `docs/solutions/architecture-patterns/tongtu-cost-engine-local-migration.md`
- `docs/reference/cost-engine-spec/34-phase4-run-package-canary.md`
- `docs/reference/cost-engine-spec/35-phase4-fba-shadow.md`
