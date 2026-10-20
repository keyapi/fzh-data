---
okf: v0.1
type: Research
title: demand_forecast 子项目数据可行性调研（通途订单 Google Sheet + EN ERPNext）
description: 评估公司级 SKU 需求预测子项目（demand_forecast）的数据地基：通途订单月度表 2023-01 至今、通途SKU↔EN 映射、EN 物料组/生命周期、断货信号；结论：数据可行，先建通用读取层再选型建模
tags: [demand-forecast, tongtool, erpnext, google-sheet, sku, forecasting, feasibility]
date: 2026-08-31
---

# demand_forecast 子项目数据可行性调研

> 目标：公司级（非仅 PB 渠道）SKU **需求**预测，给补货用。前置数据调研（阶段 A），建模选型见 [2026-08-31-ts-forecast-methods.md](2026-08-31-ts-forecast-methods.md)。

## 结论摘要

- **数据地基可行**。已确认三大块：通途订单月度 Google Sheet（**2023-01 ~ 2026-07 连续 43 张月表**，含逐日订单行）、EN/ERPNext 产品主数据（15,190 物料、410 个叶子物料组、disabled 标记），以及通途库存导出（可做断货信号）。
- **通途SKU ↔ EN 映射路径已存在**：EN Item 子表 `customer_items.ref_code`（客户物料号）+ 剥离已知后缀（`-淘汰/-out/-Cover/-Foam`），`missing_products` 三方审计已跑通过，可直接复用。
- **关键缺口**（阶段 B 必须处理）：① 通途 SKU 历史改名会让精确匹配断裂（项目已有教训）；② 断货=截断需求，需用通途库存导出打"断货月"标记，不能当普通 0；③ 新品无历史 → 冷启动，需按物料组聚合或生命周期分桶；④ PB 渠道是独立数据源（已有 `sku_forecast.py`）。
- **建议**：可行，值得新开 `demand_forecast/` 子项目。先做"通用订单读取层 + EN 映射 + SKU 生命周期标注"，再做方法管线（阶段 B）。

## 1. 数据源 A：通途订单 Google Sheet（2023 至今）

- 服务账号可见 **43 张月表 `通途订单YYYYMM`（202301~202607）**，另有 `通途订单及发货仓对应成本2022`、`合并多月份通途订单`、`新FBA多月通途原始订单`、`非FBA多月通途原始订单` 等跨月表，以及每月若干 `-区分清仓/-特殊规则/-区分大类` 变体。
- 月表结构（以 `通途订单202301` 为例，9 个 tab）：
  - **原始订单行**（`2023年1月订单`）：87 列 / 约 1.1 万行/月。关键列：`发货日期`(YYYY-MM-DD)、`通途SKU`、`解析后SKU`(=平台SKU)、`产品名称`、`品类`、`发货数量`、`渠道`、`渠道账号`、`销售站点`、`发货仓库`、`包裹号`、`跟踪号`。→ **逐日逐行，可直接按 通途SKU×月 聚合出需求序列**。
  - **写回/成本行**（`写回2023年1月FBA订单和非FBA订单`）：59 列，含 `品类编码`（如 SX-KZPT / SX-KZSJ）、`产品名称`、成本列。
  - **FBA 汇总**（`2023年1月FBA订单`）：26 列，按 SKU 月销量（`销量`、`订单数量`、`销售额`），仅 FBA。
- **tab 命名随月份演变**（2026 年月表 tab 为 `2026年6月FBA订单`/`写回...` 等）→ 读取层需按列名启发式找 tab，不能写死。
- **SKU 覆盖**：主营三角靠枕（`品类编码` SX-KZSJ 等），与 EN 顶部物料组（皮壳#三角靠枕 991、三角靠枕 814）一致。
- 读取复用：`tongtool_order_cost/tongtool_order_cost/gsheets.py` 的 `gsheet2df(gc, title, tab)`（服务账号，首行表头）。凭证：`GSPREAD_SERVICE_ACCOUNT_FILE` 指向父仓库 `D:\Work\赛狐\Cursor\secrets\gsheets-service-account.json`（worktree 无凭证，直接指过去）。

## 2. 数据源 B：通途SKU ↔ EN 映射（已存在）

- **EN/ERPNext 是产品主数据标准**。通途 SKU 由销售团队随意维护、常带人工后缀（`-淘汰/-out`=停产、`-Cover`=皮壳半成品 ~450、`-Foam`=海绵 ~28）。
- 映射路径：EN Item 子表 **`customer_items.ref_code`（客户物料号）** 即通途/赛狐 SKU；无客户物料号时靠**产品名匹配 + 剥后缀**。`docs/company-context.md` 记录了 SKU 定义差异与后缀表；`missing_products/audit_three_systems.py` 已实现并跑过三方一致性审计。
- **风险**：历史导出保留**旧 SKU 名**，通途改名后精确匹配断裂（`tongtool_order_cost/docs/lessons/sku-rename-and-rule-typos.md` 已有教训）；部分通途 SKU 是 `TT0...` 编码需核实、或平台 SKU（`解析后SKU`）才能映射。

## 3. 数据源 C：EN/ERPNext 产品主数据（生命周期骨架）

- 实测（只读 API，2026-08-31）：**15,190 物料**（3,603 模板 + 11,145 变体），**1,167 已 disabled**（约 7.7%），3,614 个 item_group，**410 个带 custom_model_id 的叶子物料组**（如 KS0347 BBL坐趴两用枕、KS0468 BetterRest靠卧枕）。
- 生命周期信号：Item `disabled`；通途 `-淘汰/-out` 后缀；BOM 成本列表 `show_disabled=1`（否则漏 200+ 停产行）。
- 访问复用：`missing_products/audit_three_systems.py` 的 `en_session()` + `fetch_en_items()`/`fetch_en_item_groups()`；凭证在父仓库 `D:\Work\赛狐\Cursor\EN_API\.env`。

## 4. 数据源 D：库存 / 断货信号

- **EN/ERPNext 不提供现成库存余额读取**（代码里无 Stock Ledger/Bin 读取）。
- 实际做法（missing_products 审计在用）：**通途库存导出** `通途合并库存结存清单*.xlsx`（列 `SKU`、`可用库存`、`仓库`、`SKU别名`），**断货 ≈ 可用库存 ≤ 0**。另有 Google Sheet `通途订单202511-库存结余` 可作为月度库存残量参考。
- 仓库口径：公司上下文约定"哪个仓有此 SKU 比库存多少更可信"（`docs/company-context.md`）。

## 5. 对阶段 B（建模）的含义

- 序列单元：**EN 物料**（客户物料号）聚合通途订单；PB 渠道单列（CENKZ... 走 Invoice to PB）。
- 需求形态：主营三角靠枕为**间歇/零膨胀**需求 → Croston/SBA/TSB 或 LightGBM 零膨胀特征 + Conformal 分位数区间（方法细节见 ts-forecast-methods 调研）。
- 必须打的标签：**断货月**（用通途库存导出）、**生命周期**（disabled/新品/停售/死库存）、**渠道**。
- 冷启动新品：按物料组（custom_model_id）聚合历史或先给经验区间。

## 6. 关键缺口与下一步

- [ ] 通途 43 张月表 tab 结构不一致 → 阶段 B 先写"自动发现订单行 tab + 列名映射"的读取层。
- [ ] 通途SKU→EN 映射覆盖度量化（有多少 SKU 能对到 EN 客户物料号）→ 阶段 B 建映射缓存 + 校验报告。
- [ ] 断货标记数据源选型（通途库存导出频率、库存结余表）→ 补货同事对特殊情况的例外录入层。
- [ ] 待用户确认后建 `demand_forecast/` 子项目骨架（OKF 文档 + 读取层 + 映射 + 首个序列 EDA）。

## 原始来源 / 证据

- 服务账号可见 130 个 Spreadsheet，含 43 张 `通途订单YYYYMM`（202301–202607）+ 跨月订单表（实测 list_spreadsheet_files）。
- 月表结构与列名：`通途订单202301` 实测（原始订单行 87 列/1.1 万行、写回行 59 列、FBA 汇总 26 列）。
- EN 数据：ERPNext 生产 API `/api/resource/Item`、`/api/resource/Item Group`（2026-08-31 只读实测，见上数字）。
- 复用代码：`tongtool_order_cost/tongtool_order_cost/gsheets.py`；`missing_products/audit_three_systems.py`（en_session/fetch_en_items/fetch_en_item_groups/通途库存导出）；`docs/company-context.md`（SKU 定义、后缀表、仓库映射）。
