---
okf: v0.1
type: Research
title: 非V2尾程选路与父拆单重复风险技术验证
date: 2026-10-10
resource: sellfox_settlement/tail_validation.py
---

# 尾程选路诊断

只读生产 `order_sync.py` 快照与已有 EN 订单快照，未改设置或费用；没有生成最终成本。`tail_validation.py` 离线逐行复现 `_calculate_last_leg_fee` 的选路：上传物流商人民币费用优先，其次 allocated 物流商人民币费用，再按传入设置选择历史预估或通途人民币费用。历史预估为零时没有通途 fallback。FBA、对方付尾程及多渠道仓库返回零。

默认参数“历史预估尾程费用”是本次诊断条件；重跑时应明确 `--priority`，不能将脚本默认值当作生产设置实时证据。生产源码的 `flt(value, 4)` 用 float 四位舍入复现，再用 Decimal 比较；此模块不是新的账务舍入规则。

| 分母或结果 | 数量 | 解释 |
|---|---:|---|
| CSV 交易输入 | 11,580 | 每一行都有关联诊断或排除理由 |
| 已匹配交易 | 9,969 | 展开 EN 子表后存在多行及重复交易引用 |
| 排除交易 | 1,611 | 非订单/缺订单号 1,464；原拆单歧义 91；无订单 53；无SKU 3 |
| 已匹配 item occurrences | 10,001 | 非唯一订单行，禁止直接汇总为成本 |
| 唯一 EN item | 9,522 | 订单名+子表序号 |
| FBA 返回零 | 2,286 | 即使字段存在费用也不选尾程 |
| 历史预估选中 | 5,079 | 两类实际物流商字段均无正值 |
| 实际物流商选中 | 2,518 | 上传优先于 allocated |
| 无选中来源 | 118 | 配置来源为零且无 fallback |
| 复现与持久化金额不一致 | 0 | 10,001 occurrences 全部一致 |

此前“115 行有通途费用但未用”是 **115 item occurrences**，对应 **113 CSV 交易、114 唯一 EN item**。115 项全部记录 source file/line、字段来源、selected、available not selected、quantity、split factor、持久化金额和来源。52 项 quantity 不为 1；allocated 字段是已经落在子表的人民币金额，诊断不再乘数量，不把可用但未选的费用补到最终成本。

# 原单与拆单尾程

55 个账号+订单号原拆单组中，51 组两边尾程均为正，19 组正金额相等。本快照没有原拆单共享 package id 的组。金额相等本身不足以证明同一张物流费用；包裹 id 不重合也不足以证明费用独立。

技术门禁为：原单与拆单尾程不能直接相加，全部标 `hold_fee_unit_or_allocation_unproven`。只有取得物流商账单费用唯一键、包裹与费用关联、原单到拆单分摊及子表金额单位，才能按唯一费用及明确分摊规则选择；当前仅提供逐组风险和双方证据。产品成本的“只加拆单”不能自动套到尾程。

# 复跑和私有产物

```powershell
uv run python -m sellfox_settlement.tail_validation --orders <private>/cost/en_orders.json --coverage <private>/cost/cost_coverage_details.json --output-dir <private>/cost/tail --priority 历史预估尾程费用
uv run python -m pytest tests/sellfox_settlement/test_tail_validation.py -q
```

私有 `cost/tail/tail_validation.json` 包含 summary、逐 item occurrence 明细、全部排除清单、115项未选通途费用、55组原拆单风险及两个输入 SHA256。所有金额明细和业务标识留在仓库外。字段缺失、重复订单名或非有限金额会报错，不猜列或静默丢弃。

9 项测试先失败后通过，覆盖优先级/no fallback、四类尾程豁免、等额原拆单仍 hold、交易与唯一 item 分母、缺关联保留和非有限金额拒绝。对应源码与既有成本边界：[成本调研](2026-10-10-cost-technical-validation.md)。

## 严格账号桥的最终集成分母

上表为此前全局候选诊断，保留为历史证据。最终按每文件原生账号唯一证据连接：11,580输入，9,970匹配，1,610排除；10,002 item occurrences、9,523唯一EN item。FBA 2,286、历史预估5,079、实际物流商2,519、来源为零118；持久化差异仍0。115未选通途费用仍为113交易／114唯一item，不能跨分母相加。
