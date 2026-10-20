---
okf: v0.1
type: Reference
title: SKU 销量预估（sku_forecast.py）— 数据口径 + 三种方法 + 局限
tags: [pb, reconciliation, forecast, sku, sales, replenish]
timestamp: 2026-08-31
---

# SKU 销量预估（sku_forecast.py）

## 目的

根据 PB `Invoice to PB` 表的 **PO 下单量**（作为销量代理），对指定 Vendor Style 预估未来 N 个月销量，给补货同事备货用。脚本设计为按 SKU 复用，之后可批量预估多个 SKU。

## 数据来源与口径（重要）

- **文件**：`D:\Work\美国\Tracy Miller\PB orders\payment advice\给财务\PB Remittance Advice Payment Date 20240430-YYYYMMDD.xlsx`（顶部常量 `PB_WB_GLOB` 定位，排除"验证"副本）。
- **工作表 `Invoice to PB`**：
  - 第 1 行表头；行间有空行，读取时跳过。
  - 每张发票 = 1 行 **Record Type = H**（列 X）头行 + 若干 **D** 明细行。
  - 关键列（1 基）：**A 发票号、E PO Date（H 行）、M Qty Ordered（D 行）、R Vendor Style（D 行）**。
  - **PO Date 是 `MM/DD/YYYY` 文本**，不是日期值，解析按 `/` 切分；个别可能是 datetime，已兼容。
  - **Vendor Style 全大写**（如 `CENKZ1325-YELLOW-97`，不是 `Yellow-97`），匹配用 `.upper()`。
- **销量口径**：D 行的 Qty Ordered 按 PO Date 汇总到 (年,月)。近期 PO 可能未全部开票入表 → 最近 1-2 个月略低估。
- **发票覆盖**：数据按发票日期完整覆盖到 2026-06，2026-07 为部分月（截止 7/13）。

## 用法

```bash
uv run python pb_reconciliation/sku_forecast.py --sku CENKZ1325-YELLOW-97          # dry-run 打印
uv run python pb_reconciliation/sku_forecast.py --sku CENKZ1325-YELLOW-97 --write  # 写 xlsx+md
uv run python pb_reconciliation/sku_forecast.py --sku A,B --months 6 --include-family --write
uv run python pb_reconciliation/sku_forecast.py --sku CENKZ1325-YELLOW-97 --start 2026-09
```

- `--sku` 可多次/逗号分隔；`--months` 默认 6；`--start` 指定窗口起始 `YYYY-MM`（默认下个月）；`--include-family` 附加同族尺寸对照（取去尺寸后缀的前缀，如 `CENKZ1325-YELLOW-`）。
- 输出到 `D:\Work\美国\Tracy Miller\PB orders\sales_forecast\`：`sales_forecast_<SKU>_<ts>.xlsx` + `.md`。

## 三种方法

| 方法 | 口径 | 备注 |
|------|------|------|
| M1 运行率 | 最近 12 个月平均月量 × 窗口月数，±25% 区间 | 反映当前节奏，最直白 |
| M2 同比窗口 | 去年同期同月份窗口量 × 近期同比调整系数 | 调整系数 = (当年/去年 YTD) 与 (上次窗口/上上次窗口) 平均，体现下滑 |
| M3 线性趋势 | 对月度序列一次线性回归外推 | 低销量易过拟合，警惕 |
| M3b 季节平均 | 窗口各月取历年同月平均 | 含 2024 年较高水平，偏乐观，仅作参考 |

**推荐值** = M1/M2 中间值取平均；区间取三种主方法（M1/M2/M3）低-高；**建议备货** = 推荐值上浮约 20%（覆盖断货/波动）。

## 局限（写进交付文档）

1. **断货低估需求**：PO 下单量 = 已开票/已发货量；断货时未满足订单不入账，真实需求可能更高。当前无库存备份可量化（通途库存 API 未接入）。
2. **数据滞后**：近期 PO 未全部开票，最近月量偏低。
3. **样本小**：月量 0-13 件、仅两年多数据，预估供参考，建议留缓冲并每月复核。
4. **未来增强**：`tongtool_order_cost` 项目的通途订单数据可交叉核对/辅助预测；脚本序列读取已独立成函数（`load_series`），后续可加数据源。

## 本次结果（CENKZ1325-YELLOW-97，窗口 2026-09 ~ 2027-02）

- 历史：2024（4月起）=57，2025=50，2026（1-7月）=19；近 12 月速率 3.0 件/月。
- 三方法：M1=18、M2=12、M3=8（M3b=28 仅参考）。
- **推荐 ≈ 15 件（区间 6-22），建议备货 ≈ 19 件**。
