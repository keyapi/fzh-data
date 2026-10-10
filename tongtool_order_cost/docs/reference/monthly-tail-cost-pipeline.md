---
okf: v0.1
type: Reference
title: 月度尾程补齐流水线（通途导出→EN 预估→键值合并→GSheet）
description: 每月把通途自发货订单的真实尾程补齐到固定 Google Sheet 月度 ws 的完整链路、命令、覆盖率口径与「缺尾清单」整理方式
tags: [tongtu, erpnext, gsheet, tail-cost, monthly, pipeline, reference]
resource: tongtool_order_cost/scripts/upload_monthly_order_sheet.py
---

# 月度尾程补齐流水线

## 目标

每月把通途 ERP2.0 自发货订单的**真实尾程（`物流商运费`）**补齐到固定 Google Sheet（`通途订单YYYYMM` 的
ws `YYYY年M月订单`），供 Colab 读取；缺失的用 EN 的**历史预估尾程**兜底，并标出**仍缺**的给运营/物流商对账。

## 六步（命令）

```bash
# 1) 通途导出（web_automation 能力；有限流，脚本默认复用今日同范围结果）
uv run python web_automation/scripts/dispatch.py tongtu.orderdetail.export -- --month 2026-07 --auto-login
#    → web_automation/downloads/订单详情统计_<月>_<ts>.zip

# 2) 清表头 → 「只用尾程 通途非FBA订单YYYYMM <ts>.xlsx」（去掉表头上方元数据，表头为第一行）

# 3) EN「上传通途订单Excel」（列表入口 process_order_excel_for_costs，base64 进出、不落库）
#    产出「EN上传Cost Review预估尾程 只用尾程 通途非FBA订单YYYYMM <ts>.xlsx」

# 4) 核验 EN：needs=1 行数 / 来源分布 / 仍缺多少（见下「覆盖率口径」）

# 5) 键值合并进「GS导出 只看尾程 通途订单YYYYMM.xlsx」（源文件不改）
#    主键 通途SKU+包裹号；兜底 平台SKU+包裹号（解析后SKU 实测无增益）
#    → 「GS再次上传 通途非FBA订单YYYYMM 修改尾程(EN预估尾程 YYYYMMDD).xlsx」+ 对账文件

# 6) 写回 gsheet（原地覆盖「物流商运费」列；ws 留在 FBA 表左侧）
export PYTHONPATH=tongtool_order_cost; export GSPREAD_SERVICE_ACCOUNT_FILE=<父仓库>/secrets/gsheets-service-account.json
uv run python tongtool_order_cost/scripts/upload_monthly_order_sheet.py \
    --xlsx "GS再次上传 …(EN预估尾程 YYYYMMDD).xlsx" --month YYYYMM --in-place
```

## 覆盖率口径（判断“这个月补全了没”）

**分母只看 `是否需要尾程=1`** 的行（`needs=0` 是平台付尾程/站内单，合法为 0，不能算缺口）。

| 指标 | 202606（前同事李惠模式） | 202607（首轮 09-14） | 202607（09-18 再导后） |
|---|---:|---:|---:|
| 需尾程=1 | 5775 | 6913 | 6913 |
| 通途**有真实尾程** | 5754（**99.6%**） | 5182（75.0%） | 6034（**87.3%**） |
| 缺口 | 21（她预估补齐，0 遗漏） | 1731 | 862（EN 历史预估补 833，**仍缺 25**） |

> 结论：6 月“实际账单已导入”程度接近满分；7 月在 09-18 后仍只有 ~87%，剩余靠 EN 历史预估 + 25 行人工。

## 「缺尾清单」给运营/物流商（WXP 用法）

筛选：`是否需要尾程=1` 且 `尾程费用来源 ∈ {历史预估尾程费用, 通途运费}`（即**还没有真实账单**的行）。

- **统计单位**：行（SKU 级）与**包裹号**；一份 837 行/814 包裹的月度清单里，主战场是 **GLS 波兰（737 行/714 包裹）** 与 **US-FedEx（91）**。
- **列**：`序号, 包裹号, 行数, 发货方式, 发货仓库, 邮寄方式, 渠道, 渠道账号, 发货日期, 发货时间, 跟踪号, 历史预估尾程合计`
- **分组/排序**：`发货方式 → 邮寄方式 → 发货日期 → 发货时间 → 包裹号`
  （先按“账单来源”，再按批次时间，最后逐票定位；**冻结首行**）。
- **另单列**：`needs=1` 但连“历史预估/通途运费”都没有的行（本项目 202607 为 25 行）——需人工确认。
- **用途**：**核对账单是否已到/是否漏单**（物流商是自动发账单或后台下载，**不会替你逐票查**）。

### 一键出「待追尾程清单」单一工作簿（`scripts/make_missing_tail_lists.py`）

把某月所有缺口（`needs=1 且 物流商运费=0`）整理成**一个** Excel 给 WXP，含 **3 个 sheet**：

```bash
uv run python tongtool_order_cost/scripts/make_missing_tail_lists.py \
    --en-xlsx "EN上传Cost Review预估尾程 只用尾程 通途非FBA订单YYYYMM <ts>.xlsx" \
    --month YYYYMM --out "D:\Work\王忠于\成本核算"
# → 「YYYYMM 待追尾程清单 给WXP YYYYMMDD.xlsx」
```

- **汇总**：按「账单来源/供应商」统计 包裹数 / 预估合计 / 优先级（高/中/待确认）。
- **明细**（可直接给 WXP）：逐包裹 `序号, 账单来源, 优先级, 包裹号, 跟踪号, 发货日期, 发货时间, 发货方式, 邮寄方式, 渠道, 渠道账号, 通途SKU, 平台SKU, 订单号, 发货数量, 历史预估尾程费用, 备注`。
  排序 `优先级 → 账单来源 → 发货日期 → 发货时间 → 包裹号`，冻结首行。`备注` 标出「无跟踪号→按账号+日期反查」「无预估」等。
- **无需追-平台付(待确认)**：平台付尾程（OSTK/Wayfair）的行——默认不追，但**保留不丢**（对账：待追 + 无需追 = 全部缺口）。

**账单来源判定**（按「邮寄方式」链，如 `M6180蜴国际>>M6180蜴国际-Fedex` 子串匹配，**OSTK 必须排在通用 FedEx 前**）：

| 账单来源 | 判据 | 优先级 | 说明 |
|---|---|---|---|
| **蜴国际 FedEx（货代）** | 链含「蜴国际」 | 高 | **重点**；找蜴国际/YIGlobal 要账单 |
| **GLS 波兰** | 链含 `GLS` | 高 | **重点**；GLS 账单/后台 |
| 「7条」尾程供应商 | 链含「7条」（如 `美国尾程7条>>FEDEX Economy TX`） | 中 | 美国尾程供应商「7条」结算 |
| CENTRADE | 链含 `CENTRADE` | 中 | Centrade 结算 |
| 疑似官方 FedEx（待确认） | 仅剩的 `US-FedEx>>US-FedEx` | 待确认 | 可能是公司自有 FedEx 账号 |
| 平台付尾程（OSTK/Wayfair） | 链含 `OSTK` | **不追** | 平台付尾程，无需导入（单列 sheet 备查） |

> **领域口径（2026-10 确认）**：
> - **OSTK/Wayfair 不用导入尾程**（平台付）。
> - `美国尾程7条` 是**独立尾程供应商「7条」**，不是官方 FedEx。
> - `US-FedEx>>US-FedEx` **可能是官方 FedEx，待确认** → 若是，去 **FedEx Billing Online** 下载（`fedex-billing-online-download.md`）。
> - **重点追查：蜴国际 FedEx + GLS 波兰**（量大）。202608 缺口 527 包裹 = 蜴国际 250 + GLS 228 + CENTRADE 36 + 「7条」5 + 疑似官方FedEx 1 + 无需追(OSTK/Wayfair) 7。

> **FedEx 无账单 API、官网自动化登录被反爬拦截**（2026-10-10 实测）→ 官方账单只能**人工**下载。
> 详见 `fedex-billing-online-download.md` 与 `../research/2026-10-10-fedex-invoice-api-and-official-parcels.md`。

## 注意

- **通途报表生成有限流**：不要短时间反复生成；`tongtu.orderdetail.export` 默认复用「今日同范围已完成」结果（`--no-reuse` 强制新生成），并在提交后 90s 内未出现新行时报 `RATE_LIMITED`/`NO_NEW_JOB`。
- **行序会变**：两次通途导出的包裹级顺序可能不同（实测 192/9390、302/9604 位置不同），**必须键值合并、不要按位置粘贴**。
- **SKU 会改名**（如 `CEN003-DPBLUE-100-old` → `CEN003-DPBLUE-100`）：主键未命中用 平台SKU+包裹号 兜底。
- **无落库副作用**（列表入口）：EN 侧只返回 base64，不建 File/单据。

## 关联

- 导出能力：`web_automation/docs/reference/orderdetail-export.md`（含限流/复用/选择器）
- GSheet 上传：`docs/reference/gsheet-monthly-sheet-upload.md`
- EN 尾程规则与 REST：`docs/solutions/architecture-patterns/tongtu-orderdetail-export-row-anchor.md`（下载识别）、
  以及 `EN_API`/issue `keyapi/tongtool_integration#1`（表单入口漂移）
