# platform_account_reconciliation — Agent 交接文档

> **用途**：新对话接手平台账期对账任务的入口。读完本文档即可理解 OSTKUS 账期 → EN/Tongtool Order 对账的背景、字段口径、拆单规则、当前结果与下一步。
> **代码位置**：`platform_account_reconciliation/`
> **最后更新**：2026-08-17

---

## 1. 背景与目标

财务同事提供 Overstock / OSTK 的账期文件（`OSTKUS-*.xlsx`），内部含 `Payment Summary`、`Detail`、`Mozart Reports` 三个 sheet。它们不是平台订单导出，而是**结算/回款文件**。

对账目标：

1. 确认账期里的每个 `OS Order #` 都能在 EN 生产系统 `Tongtool Order` 找到对应订单。
2. 识别拆单、跨账号、重复主单等特殊关系。
3. 站在财务角度逐项核对 Sales、Returns、Adjustments、Supplier Oasis Fees，以及 EN 的 `platform_fee`、`shipping_fee`、`actual_total_price`、`gross_profit`。

本模块先覆盖 OSTKUS，未来扩展 Wayfair `WFUS`。

## 2. 关键文件结构

```
platform_account_reconciliation/
├── README.md
├── AGENT_HANDOFF.md
├── __init__.py
├── scripts/
│   └── reconcile_ostkus.py      # OSTKUS 账期费用级对账脚本
├── out/                          # gitignored 输出
└── docs/                         # OKF v0.1 bundle
    ├── index.md
    ├── log.md
    ├── reference/
    ├── research/
    ├── specs/
    └── lessons/
```

## 3. 数据流

```
Overstock OSTKUS 账期 xlsx
  ├─ Payment Summary          ← 结算汇总：Sales/Returns/Adjustments/Fees/Check Total
  └─ Detail                   ← 逐行：Line Type/OS Order #/SOFS Order #/SKU/金额
        ↓ 按 OS Order # / Supplier SKU / Quantity / 金额 匹配
EN 生产 ERPNext (https://erpnext.vilavi.cn)
  └─ Tongtool Order           ← 通途订单快照，含订单金额、平台费、毛利、包裹、仓库
```

- 凭证：`EN_API/.env` 的 `PROD_ERP_API_KEY` / `PROD_ERP_API_SECRET`（或通用 `ERP_API_KEY` / `ERP_API_SECRET`）。
- 默认生产环境 `https://erpnext.vilavi.cn`，只读 REST；不得修改生产数据。

## 4. 匹配字段

| 账期字段 | EN 对应字段 | 可用性 |
|----------|-------------|--------|
| `OS Order #` | `Tongtool Order.name` / `platform_order_id` | 可精确匹配，但需处理后缀 |
| `SOFS Order #` | EN 无对应字段 | 不可匹配（主表和 raw_data 中均无该值） |
| `Supplier SKU` | `order_items.platform_sku` / raw `webstoreSku` | 可精确匹配 |
| `Quantity` | raw `platformGoodsInfoList.quantity` | 可精确匹配；不要用 `order_items.quantity` |
| `Unit Price / Total` | `order_amount` / `products_total_price` | 可精确匹配 |
| `Order Date` | `sale_time` | 近似匹配，实测账期下单日通常早 0-2 天 |
| 仓库 | `warehouse_name` | 可精确匹配 |
| 发货时间 | `despatch_complete_time` | 可匹配 |
| P号 | `packages.package` | 可追溯物流 |

## 5. 拆单与特殊关系（重要）

- Overstock 多 SKU 或多件订单，在通途/EN 会拆成 `_1`、`_2`、`_3` 后缀子单。
- `platform_order_id` 会保留后缀，例如 `473799269_1`；用原始 `473799269` 精确查会漏。
- 另一个账号 `OSTK02US` 使用 `OSFD-` 前缀，例如 `OSFD-472619552`。
- 少数订单在 EN 同时存在“无后缀主单”和“拆分后缀子单”，且子单金额合计等于主单金额。汇总时必须把这种主单标记为重复主单并排除，否则金额会双算。
- 2026-08-17 实测发现 4 个重复主单：`473138160`、`473527814`、`473992805`、`474066326`。

## 6. EN 财务字段口径

| 字段 | 含义/注意 |
|------|-----------|
| `order_amount` / `products_total_price` | 订单商品额，与账期 Sales 合计一致 |
| `actual_total_price` | EN 里已退款/退货订单可能为 0，不能直接当实收加总 |
| `platform_fee` | 平台费用；与账期 `Marketing Allowance 8.25%` 接近但不完全相等，口径需确认 |
| `shipping_fee` | OSTKUS 当前数据为 0；账期运费纠正是账单级 charge，不能简单等同 |
| `gross_profit` | EN 毛利（收入-平台费-成本）；含 EN 成本口径，不能直接当经营亏损 |
| `total_item_cost` | 可能包含组件成本；多组件订单不要和单条账期金额直接比较 |
| `order_items.transaction_price` | 内部组件行金额，同一订单可能重复，不能加总 |

## 7. 当前结果快照（2026-08-17）

- `OSTKUS-2026-07-01.xlsx`：Check `469437`，Sales `10,240.44 USD`，EN 订单金额 `10,240.44 USD`，差异 `0.00`；EN 平台费 `819.19`，账期营销扣点 `844.92`，差 `-25.73`；EN 退货原单金额 `884.41` vs 账期货值 `812.41`。
- `OSTKUS-2026-07-16.xlsx`：Check `471881`，Sales `14,556.24 USD`，EN 订单金额 `14,556.24 USD`，差异 `0.00`；EN 平台费 `1,164.39`，账期营销扣点 `1,200.91`，差 `-36.52`；EN 退货原单金额 `526.32`，与账期货值一致。
- 两个账期共 350 个基础 OS 订单，订单级核对：338 个金额一致、16 个仅退货、0 个未匹配。
- 跨期退单 4 个：`473076088`、`473115387`、`473298864`、`473437955`，均在 `07-01` 销售、`07-16` 退货。

## 8. 运行方式

```bash
# 只读账期侧（不调用 EN）
uv run python platform_account_reconciliation/scripts/reconcile_ostkus.py \
  --account "D:/Work/尹/OSTKUS-2026-07-01.xlsx" \
  --no-en

# 完整费用级核对（默认 EN 生产只读）
uv run python platform_account_reconciliation/scripts/reconcile_ostkus.py \
  --account "D:/Work/尹/OSTKUS-2026-07-01.xlsx" \
  --account "D:/Work/尹/OSTKUS-2026-07-16.xlsx" \
  --out "D:/Work/尹/OSTKUS费用级核对.xlsx"
```

输出工作簿至少包含：`核对总览`、`PaymentSummary逐项`、`账期Detail`、`订单级费用核对`、`EN订单财务明细`。

## 9. 安全边界

- 只读 EN，不写生产。
- 不把账期原始 xlsx、EN 原始 JSON、地址/电话等 PII 写入 git。
- 输出 xlsx 在 `out/`（gitignored）或用户指定路径。
- 未匹配记录必须保留并说明原因，不能静默丢弃。

## 10. 下一步

1. 确认 `platform_fee` 与 `Marketing Allowance 8.25%` 的差异原因（约 -25.73 / -36.52）。
2. 核对 `07-01` EN 退货原单金额 `884.41` 与账期货值 `812.41` 的 `72.00` 差额。
3. 对 4 个跨期退单做“销售期 + 退货期”合并核对。
4. 扩展 Wayfair `WFUS` 账期：`Invoice #/PO #` 为 `CS.../CA...`，需要对应 Wayfair 订单导出与 EN 侧命名规则。
