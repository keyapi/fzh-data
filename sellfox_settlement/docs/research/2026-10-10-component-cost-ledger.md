---
type: Research
title: 非 V2 账单组件成本证据账本
date: 2026-10-10
module: sellfox_settlement
tags: [amazon, non-v2, cost, technical-validation]
---

# 技术账本已可离线复跑

实现 `sellfox_settlement/cost_ledger.py`，只读既有私有 JSON；不访问生产，不写财务系统，不生成申报成本总额。私有输出为 `cost/ledger/cost_technical_ledger.json`。

| 输入／输出 | 数量 |
|---|---:|
| EN 订单记录 | 9,614 |
| 原生账号＋基础订单分组 | 9,494 |
| 输入组件／输出组件证据 | 9,823／9,823 |
| 选择组件／保留但排除原单组件 | 9,722／101 |
| 输入账单引用／输出账单引用 | 11,580／11,580 |
| 原单＋拆单组 | 55 |
| 产品成本冲突 hold 组 | 23 |
| 其余仅选拆单产品快照组 | 32 |
| 所有分组中选中产品快照为零 | 492 |

产品、头程、加工、尾程逐个组件独立记录。拆单存在时只选拆单；原单证据始终保留，不与拆单相加，也不自动回填。23 组非零产品成本差异保留原单数、拆单数，`included_snapshot_amount=null`，不进入可并数。头程、加工、尾程仍保留各自拆单技术快照；这些并非财务确认金额。

`sx_shipping_cost`、`first_freight`、`valuation_rate`、`last_leg_fee` 按 EN 已保存字段求和，不再次乘数量。原始组件数量另列，明确不能把组件行数、包裹数或 EN quantity 当作已发货实物数量。零产品成本仍为零，通用 `item_cost` 不用于填补；尾程独立，零产品不抹掉已有尾程，也不追加原单尾程。尚未确认跨拆单包裹重复的财务扣重规则，因此不输出尾程财务总额。

退款、退货扣款、拒付退款仅保留引用并标记 `hold_refund_policy`，不按账单行重复分摊或自动冲减订单成本。每条匹配账单保留已有 EN 名称，并链接其原生账号／基础订单账本组；缺匹配记录仍完整保留。全部 EN 候选快照不意味着全部属于八月已确认销售成本。

当前 BOM 探针为 2026-10-09 技术证据，原样附录，不进入上述持久化快照求和，也不冒称八月历史成本。其 `order` 实为 EN 订单名称，`sku` 实为通途 SKU，必须用 `(EN name, tongtool_sku)` 关联，不能用平台订单号或平台 SKU。探针缺组件行键，两侧均唯一才附着；否则明确标记缺失或歧义。修正后 9,795 组件唯一附着，28 组件保留歧义状态。原生账号参与账本键，防止跨账号同订单号混并。

## 复跑

在仓库根目录执行（`PRIVATE_COST` 为仓库外私有成本目录）：

```powershell
uv run python -m sellfox_settlement.cost_ledger --cost-root PRIVATE_COST --out PRIVATE_COST/ledger
uv run python -m pytest tests/sellfox_settlement/test_cost_ledger.py -q
```

输出目录使用共用私有路径保护，拒绝任意 Git checkout 内的目的地。源文件 SHA-256 写入私有报告；缺身份、缺列、重复 EN 名称、非有限金额失败关闭。空金额为缺失，不能转为零；选中订单无组件时，四个成本组件均标为 `hold_missing_items`，不能用空列表求和得到零。12 项合成测试通过，覆盖拆单、23 类差异独立 hold、原生账号隔离、退款保留、重复拒绝、缺列／NaN、探针正确键及重复组件歧义、空组件、产品零与尾程独立。

待财务确认仍包括历史成本、退款冲减、数量分摊、包裹重复以及 23 组差异；当前实现只把已能验证的技术连接和证据固定下来。

## 原始组件位置重放（最终集成）

旧探针28个歧义保留，不改写旧证据。私有生产函数重放新增 `current_cost_probe_components.json`，用EN名称加原快照item_position精确关联9,823组件，源快照hash进入月度manifest。9,340可计算、342缺物料、141缺仓库；与旧探针状态及计算值逐项一致。精确关联不代表成本全可用，也不代表8月历史BOM。模块13项测试通过，整模块147项通过。总入口优先使用组件探针，完整分量留私有JSON。
