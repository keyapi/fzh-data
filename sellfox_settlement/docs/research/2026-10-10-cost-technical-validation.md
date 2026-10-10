---
okf: v0.1
type: Research
title: Amazon 非 V2 账单订单与成本技术验证
description: 2026 年 8 月完整账单与生产 EN 订单、包裹、真实 Cost Review 源码的只读覆盖率验证。
tags: [amazon, settlement, tax, cost-review, readonly, fba, fbm]
resource: sellfox_settlement/cost_validation.py
timestamp: 2026-10-10
---

# 订单与成本技术验证

T06 的订单与 SKU 连接可用，但必须保留拆单歧义。T07 的生产 Cost Review 确有 FBA 产品与头程分量，通用 `item_cost` 在本批 FBA 样本全为零，不能作为 FBA 商品成本入口。当前 BOM 可计算不等于已经恢复 8 月历史成本。

## 验证范围与数据留存

- 输入是 65 份非 V2 CSV 的完整标准化输出，11,580 行，没有抽样删除。费用、划款等非订单成本连接行也保留。
- 生产 EN 使用 REST 读取六个真实 DocType 元数据、40 条仓库配置，并通过 SSH 参数化 SELECT 取得账单范围内 Amazon 订单、子件成本和包裹关系。数据库会话使用 `START TRANSACTION READ ONLY`，结束 rollback；没有插入或更新业务数据。
- 订单查询按账单 Order/Refund 中全部基础平台订单号，不限制下单月份，避免漏掉跨期退款。`SUBSTRING_INDEX(platform_order_id, '_', 1)` 仅作为候选搜索，匹配器只认可尾部 `_数字` 的拆单后缀。
- 业务输入、生产源码副本、订单号、SKU、包裹号、原始接口结果及逐行未匹配明细均保存在用户账单目录下的 `技术验证/20261010/cost/`，不进入 Git。
- 仓库中的匹配器只读取已有 JSON 并写出报告，拒绝向仓库内输出业务明细。

## 全量连接结果

分母是有 `order_id` 的 Order/Refund 交易行，不是 EN 月度单数，也不是去重销售笔数。Released/Deferred、退款及重复账单出现次数在此均按输入行保留，不能将以下行数直接用来汇总成本。

| 结果 | 全部 | FBA | FBM |
|---|---:|---:|---:|
| 有订单号的 Order/Refund | 10,116 | 2,337 | 7,779 |
| 订单号 + 精确平台 SKU 连接成功 | 9,969 | 2,282 | 7,687 |
| 无对应 EN 基础订单号 | 53 | 53 | 0 |
| 有订单但平台 SKU 不符 | 3 | 2 | 1 |
| 无后缀父单与后缀子单并存 | 91 | 0 | 91 |

输入 11,580 = 可连接分母 10,116 + 明确排除 1,464。可连接分母 10,116 = 成功 9,969 + 订单缺失 53 + SKU 不符 3 + 父子歧义 91。每个排除/异常都保留输入来源和原因。按 `(source_file, order_id, sku)` 去重后为 9,631 对；此键只是来源内技术去重，尚不是跨账期财务交易唯一键。

生产候选快照为 9,614 单、9,823 子件和 7,439 条包裹关系。候选包括拆单父子，不能相加计算成本；其中 FBA 2,112 单、自发货 7,502 单。91 条歧义交易对应 55 个基础订单号，同账号中父子同时存在，当前保留歧义，未武断删除父单或子单。3 条 SKU 不符均不是大小写/空格或通途 SKU 同名可修复。

上述 9,969 是全局平台订单号与 SKU 的候选连接，尚未把财务文件账号别名完整映射成通途实际同步 `account` 后逐行约束。后述实际 API 已证实同一 order id 可跨 account 出现；账单管道落地时必须加入经验证的 native account，不能仅因当前 EN 恰好只有一个候选就宣称账号层完全正确。

9,969 条成功连接行中：7,591 条有包裹；9,682 条全部对应子件有 EN 物料；9,451 条全部子件产品分量正值；9,381 条全部子件头程分量正值；账单 FBA/FBM 与 EN 类型冲突 0。金额零值与缺失需要领域规则解释，正值覆盖率只说明字段可用性。

成本分母显式限于 Order/Refund。`Refund_Retrocharge`、`Chargeback Refund` 各有 1 行有订单号，作为补充连接探针单独保留，未归入利润或改变主成本分母。额外参数化只读 SSH 查询取得两条 EN 订单，保存为私有 `supplemental_en_orders.json`：前者能连到订单但没有账单 SKU，结果 `sku_missing`；后者可精确连 SKU，结果 `matched`。初始 REST 补查返回 500，未将其等同于业务缺单。

数量与组件风险：同一平台 SKU 可炸开为多个通途组件，`order_items.quantity` 不能直接累加后当作平台销量；同一订单也可能有多个包裹及拆包系数。退款账单的数量不能未经确认就自动冲回产品/头程/尾程成本。主快照和离线计算均保留原始数量、完整 SKU、拆包系数，但本轮没有汇总任何成本金额，没有声称已证明每件销量等于每个组件的成本数量。

## 生产已有成本分量

以下分母是查询得到的候选子件快照，含父子候选和未连接行，不能与上表交易行混用，也不用于金额加总。

| 生产字段或关系 | FBA（2,122 子件） | FBM（7,701 子件） |
|---|---:|---:|
| 缺 EN 物料 | 250 | 92 |
| 产品 `sx_shipping_cost` 正值 | 1,872 | 7,368 |
| 头程 `first_freight` 正值 | 1,806 | 7,368 |
| 加工 `valuation_rate` 正值 | 0 | 7,063 |
| 通用 `item_cost` 正值 | 0 | 7,626 |
| 尾程 `last_leg_fee` 正值 | 0 | 7,508 |
| 历史预估作为最终尾程来源 | 0 | 4,972 |
| 物流商实际费用作为最终尾程来源 | 0 | 2,536 |
| 尾程来源为空 | 2,122 | 193 |

FBA 候选订单无包裹，尾程为零；这与源码明确跳过 FBA 尾程一致。FBM 7,502 候选单中 7,379 单有包裹。上传物流商分摊人民币费用在本批样本均为零，不代表系统不存在这个优先入口。

## 真实 Cost Review 源码与只读计算

生产应用 `tongtool_integration` 的以下源码通过 SSH 只读复制到私有目录：

- `tongtool_integration/tongtool_integration/doctype/tongtool_cost_review/tongtool_cost_review.py`，SHA-256 `706b10188c87527ce00aa0060f4df7783d8aa000fb54be11848d4c677afb6cb2`。
- `tongtool_integration/sync/order_sync.py`，SHA-256 `72e9360c7647ba5b5978f78f8fb43786561ed630292038b5fe7f795f7fe0b903`。

`_calculate_single_item_cost` 是返回字典的计算函数，读仓库配置、BOM 标签映射及交付形态；FBA 使用绍兴总成本与成品头程。FBM 按皮壳/成品/半成品及 `-Cover`、`-Foam`、`-PPCotton` 选择分量；数量和拆包系数由调用方传入。源码末尾会回填全部对照分量，展示字段与最终选中成本不能混为一谈。特殊规则 `engine_170.py` 未被使用，也不是此实现的替代品。

直接调用文档 `update_costs`、`rematch_skus`、`upload_tongtool_excel` 会保存记录；`process_cover_excel` 会更新物料客户码。本轮均未调用。Excel 成本处理函数还调用汇率、SKU 匹配等辅助逻辑，错误分支存在 `frappe.log_error`，因此没有仅凭接口名称就断言其完全无数据库副作用。

实际执行的是私有离线探针：从生产源码 AST 原样提取 `_calculate_single_item_cost` 和 `_fill_missing_bom_cost_data`，注入只读取得的真实仓库配置、BOM、当前启用的重量模板兜底设置。`frappe.flt` 使用本地 round 兼容适配，验证覆盖率，不声称得到审计定稿金额。没有创建 Cost Review、File 或订单。

当前 BOM 3,694 行、兜底后仍为 3,694 行；40 个仓库配置。9,823 候选子件的执行结果：

| 结果 | 子件数 |
|---|---:|
| 可以计算 | 9,340 |
| 缺 EN 物料 | 342 |
| 缺仓库配置 | 141 |
| 无 BOM 行或无成本配置列 | 0 |

9,340 = FBA 1,872 + FBM 7,468；缺物料 342 = FBA 250 + FBM 92；缺仓配置 141 全部为 FBM。当前计算产品分量正值 9,240、头程正值 9,174、加工正值 7,093。这些是当前能力验证，没有回写现有单据。

## 真实尾程优先规则

`order_sync.py` 的最终尾程选择函数先排除 FBA、对方承担尾程的平台/账号和多渠道仓库，再按以下顺序选择正值：

1. `upload_allocated_carrier_fee_rmb`，上传物流商人民币费用。
2. `allocated_carrier_fee_rmb`，已分摊物流商人民币费用。
3. `Tongtool Settings.last_leg_fee_sources_priority` 指定的历史预估或通途人民币费用。

生产设置当前指定“历史预估尾程费用”，这个设置只作用于第 3 级。前两级是实际上传或已分摊的物流商费用；只有这两级都不是正值时，才会用历史预估。不能把设置理解成“历史预估优先于实际物流商费用”。

2026-08 已匹配自发货行里，最终来源为历史预估的行全部没有正值物流商费用。来源为空的行里，多数仍有通途运费，但源码里“历史预估为 0 时改用通途运费”的兜底已被注释，所以这些行停在 0。FBA 订单在这个函数里直接返回 0，不把自发货尾程加到 FBA。

## 历史成本与技术阻塞

当前设置指向 2026-10-09 BOM 快照，`_load_bom_cost_data` 加载一个指定 gzip 文件并按当前设置兜底，没有按订单日期自动选历史 BOM 的路径。站点找到 198 个匹配 BOM gzip 文件，文件修改时间均在 9 月或 10 月；仅凭这些名字/mtime 不能证明其中存在有效 8 月历史成本，也不能证明其他存储中完全不存在历史数据。

已有订单成本是读取时的可追溯快照，但订单可能被重算；没有由本轮证明它们就是 8 月原始值。技术上还需要历史 BOM/仓库配置的可用来源和版本时间，以及订单重算审计记录，才能声称恢复申报月份成本。FBA 所需平台销售/退款、Amazon 仓配费来自账单，产品和头程需使用明确分量；不能重复引入 FBM 尾程。

待逐笔关闭的技术异常起初是：53 条 FBA EN 订单缺失（52 个唯一订单号）、3 条 SKU 差异、55 个基础订单号的父子歧义、342 个候选子件物料缺失及 141 个候选子件仓库配置缺失。后续只读复核见同日私有清单 `2026-08-followup-lists.xlsx`，不把订单号和金额写入本文件。父子单按「拆单相加、不要再加原单」列出；产品成本两边不相等的 23 张单独留下。

55 张里还有 6 张产品成本看起来极端，都不是新口径：

- **只有拆单有产品成本（3 张）。** 不带后缀的原单没有发货仓库，发货方式也是空的，所以绍兴发货成本、头程、加工都是 0。`_1`/`_2` 有仓库和发货方式（皮壳或成品），产品成本在拆单上。原单仍可能带尾程；尾程不要因为产品成本在拆单上就再加一遍原单尾程。
- **原单和拆单的产品成本都是 0（3 张）。** 两边都有仓库和行，但发货方式仍是空的，EN 物料也是空的，成本函数没有进入皮壳/半成品/成品。原单上的通用 `item_cost` 不是产品成本，不能拿来填这 3 张。其中有的拆单已经有物流商尾程，尾程和产品成本是两列。SKU 差异里，一行是不换行空格，另一张单是账单店铺和 EN 里另一家店的同号订单被放在一起比较；通途 FBA 接口里账单店铺那一条的 SKU 与账单一致，EN 快照没有这条。53 条缺单的 SKU 大多已经出现在同账号其他 8 月 FBA 订单或商品主数据里，不是一批未登记 SKU。8 月购买日窗口之外的 50 个订单号，7 月窗口命中 45 个，6 月窗口再命中 1 个退款的原购买单，9 月和 5 月窗口没有新增命中。剩下 4 个：3 个账单站点是 `sim1.stores.amazon.com`、订单号以 `S01-` 开头；1 个加拿大账号订单在这些购买日窗口和 EN 里都没有，商品主数据里有对应 SKU。全部私有明细已保留。

官方 `platformordersquery` 最初对缺失单和 EN 已有 FBA 阳性控制均返回 `code=200`、零条。阳性控制不通过后，立即停止批量扫空，没有将其当作“通途确实缺单”的证据。生产同步源码说明 Amazon FBA 使用不同的 `/openapi/tongtool/fbaOrderQuery`：按 `purchaseDateFrom/To` 和可选 `account` 查询。官方 MCP 对应 `erp2_orders_fbaorderquery`，显式 8 月日期窗的阳性查询成功，每页 100 条，实际包含 `sku`、`goodsSku`、`quantityPurchased`、`firstTariff`、`firstShippingFeeUnit`、`orderFinancial`。请求按商户 15 秒/次限流，逐页最小字段输出保存在私有目录。

## 真实通途 FBA 月度完整性

查询参数 `purchaseDateFrom=2026-08-01 00:00:00`、`purchaseDateTo=2026-08-31 23:59:59`、`pageSize=100`，22 页全部成功（21 页各 100 条，末页 37 条）。这验证的是通途 purchase-date 窗口，不能与账单 transaction-date 自然月直接等同。

| 分母/结果 | 数量 |
|---|---:|
| API 订单行 | 2,137 |
| 唯一 `(account, order id)` | 2,137 |
| 全球唯一 order id | 2,136 |
| API 子件行 | 2,150 |
| 按真实 account + order id + sku 连接 EN 成功的完整单 | 2,048 |
| 上游有而 EN 全局缺失的单 | 89 |
| 子件 SKU 连接成功 | 2,058 |
| 随缺失订单保留的子件 | 92 |

2,137 = 2,048 + 89；2,150 = 2,058 + 92，没有静默丢单。EN 全局查询按此次全部 API order id 取得 2,048 单，也与 EN sale-time 8 月总量探针一致，但日期字段的确切时区同一性没有仅凭总量相等得到证明。89 个缺单分布在 6 个真实 account，数量为 81、3、2、1、1、1；没有执行导入或同步。

同一 order id 有 2 条内容不同、account 不同的订单行，并非已证明的同账号重复，必须保留两个账号键。实际 API 子件 `firstShippingFeeUnit` 有 1,486 行正值，`firstTariff` 均为零；字段虽存在，仍需确认它们的成本口径、币种和计量单位，不能自动替代 Cost Review 头程分量。

账单 53 条 EN 缺行共 52 个唯一订单号，类型为 Order 51 行、Refund 2 行，Released 40 行、Deferred 13 行。与此次 API 对照后，有 2 个订单号（对应 2 条账单行）确实上游本月有而 EN 全局缺失，私有 `fba_bill_missing_august_upstream_evidence.json` 保存逐笔证据；另外 50 个订单号未出现在本次 8 月 purchase-date 窗口，只能标记为跨月或其他未判原因，不能声称通途全局缺失。未扩展到 7 月全商户查询。

完整月度总览及逐单结果保存在私有 `fba_month_scope_summary.json`、`fba_month_scope_details.json`。此处对真实上游 account 的精确验证与上文账单全局候选连接分开列账，避免把两个分母混用。

## 验证与复跑

匹配器测试覆盖拆单组件和包裹关系、父子同时存在、SKU 不符、跨账号歧义、FBA/FBM 冲突、输入行守恒、缺列报错、任意 Git 工作树的输出保护、补充连接不改变主成本分母、无 SKU 的补充订单不冒充 SKU 匹配。先红后绿，10 个测试通过。报告可离线复跑，无需再次读取生产。

```powershell
$env:PYTHONPATH = '<checkout>'
uv --project '<data-root>' run python -m sellfox_settlement.cost_validation --transactions '<private>/normalized_transactions.json' --orders '<private>/cost/en_orders.json' --supplemental-orders '<private>/cost/supplemental_en_orders.json' --output-dir '<private>/cost'
uv --project '<data-root>' run pytest tests/sellfox_settlement/test_cost_validation.py -q
```

此验证没有选定收入、法人、汇率或会计成本计价口径；财务确认仍需独立完成。
