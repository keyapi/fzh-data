---
okf: v0.1
type: Reference
title: 赛狐海外仓备货单改「单个头程费用」——无 Excel 路径，只能走私有接口
date: 2026-09-18
category: integration-issues
module: cost_adjust
problem_type: integration_issue
component: sellfox-openapi
severity: high
applies_when:
  - "要改赛狐海外仓备货单的「单个头程费用」（库存单位费用的驱动力）"
  - "想知道备货单修改能不能用 Excel 上传"
  - "改完头程后库存单位费用没到预期值，需要算清覆盖比例"
  - "海外仓批次为什么改一张单拉不动整个 SKU 的均价"
---

# 备货单改「单个头程费用」：无 Excel 路径，只能走私有接口

## Context

库存的「单位费用」由批次头程驱动，而**头程无法走成本补录单**（海外仓备货单类型不许填单位费用）。
剩下两条路：Excel 上传、页面点击编辑。前者此前只有客服口述「不能上传修改」，说法可靠性存疑；
后者是纯点击，不可编程。

本次把两条路都验死了。

## Guidance

### Excel 两条路都堵死（实测模板表头）

| 模板端点 | 表头 | 能改头程？ |
|---|---|---|
| `/api/excelTemplate/pickingOrderUpdateTemplate.json` | `*备货单号 头程物流 头程分摊方式 税费分摊方式 体积参数 实际发货时间 预计到货时间 单据备注` | ❌ **零个费用字段**，只改单据头 |
| `/api/excelTemplate/overseaPickingListFee.json` | `*备货单号 跟踪号 物流商单号 实际计费重 实际物流单价 实际物流费用 实际报关税费 实际其他费用 预估计费重 预估物流单价 …` | ⚠️ 是**「物流信息」层**的费用（`logistics[]`），非 `items[].headFee`；且前端无入口、上传端点未知 |

**「更新模板」不含费用字段**，所以「修改不能上传」在费用维度上成立 —— 客服的说法结论对，理由未必。

### 私有接口三步（undocumented internal API）

```
① GET  /api/oversea/detail.json?id=<pickId>   → 整个单据对象（含 items[]）
② 改   items[].headFee                        → 单个头程费用
        items[].logisticsCost / totalHeadFee  → 派生值 = headFee × quantity，两位小数字符串
③ POST /api/oversea/edit.json                 → 整坨发回
```

同族端点：`save.json`=创建（`createStockOrder`）、`detail.json`=读、`page.json`=列表。

### 五个实测坑

1. **`singleLogisticsCost` 是服务端派生**。照旧值发回去，服务端仍按新 `headFee` 重算，别手动改。
2. **payload 是 `detail.json` 的整坨回填**（含 `shelfIn` / `logistics[]` / `customInfo` / 装箱规格等上百字段）。
   少传很可能被当作全量覆盖。
3. **耗时随明细行数超线性增长**：1 行瞬时；**500 行 / 1.06 MB 实测 16~18 秒**。
   Playwright `page.request` 默认 30s 超时，行数再多就会超。必须显式放宽，且不要并发。
4. **`page.json` 的 `searchType` 必须传 `'sku'`**。传 `commoditySku` 等其它值会被**静默忽略**，
   返回未过滤的全量列表 —— 会让人误判「搜不到」。`data.totalSize` 也不可信，用 `rows`。
5. **`pickId` 不由 URL 传**：前端靠 localStorage（`EditStockOrder_edit` /
   `DetailStockOrder_detail` 里的 `{"params":{"id":N}}`）取目标单，URL 上的 `?id=` 被忽略。
   走 API 时直接带 `?id=` 不受影响，但**做 UI 自动化必须知道这点**，否则会莫名打开错单。

### 生效口径：只按「本批次占比」加权

改一张备货单的头程，**不会**把这个 SKU 的单位费用整体拉到目标值：

```
Δ单位费用 = ΔheadFee × (该备货单批次的可用量 / 该SKU总可用量)
```

实测：`KS0248-DM-60-WHITE` @ DANEEY 改 `8.12 → 4.08`，本批次占 `139/150`，
单位费用 `8.12 → 4.3763`（=`(139×4.08 + 11×8.12)/150`），**完全吻合**。

**为什么另外 11 件不跟**（本次查清，纠正了旧文档的笼统说法）——看批次 `type`：

| type | 含义 | 批次行为 |
|---|---|---|
| 5 | 海外仓备货单 | 自带批次 |
| 3 | 库存调整-**增加** | **新建独立批次**，成本冻结在创建时 → **不跟随**备货单后续改动 |
| 4 | 库存调整-**减少** | 引用已有批次，共享同一份成本 → 跟随 |

实测该 SKU 在库 4 个批次：备货单批次 139 件 + **3 张库存调整单各自新建的批次** 7/3/1 件。
那 3 个批次头程仍是 8.12。**而调整单没有「单个头程费用」字段 → 这 11 件目前没有自动化入口。**

> 旧记录 `sellfox-cost-accounting-fifo.md` / `sellfox-pitfalls.md` 说「调整单批次会跟随备货单成本」——
> 那只对 **type=4（减少）** 成立，**对 type=3（增加）不成立**。不要笼统照抄。

## Why This Matters

- 以为「改一张单就能把整个 SKU 的单位费用拉到目标值」会算错账 —— 实际只有本批次那部分。
- 18 秒的写耗时若没预留，批处理会大面积超时，且重试可能重复提交。
- `searchType` 被静默忽略会导致「明明有数据却搜不到」，进而误判为无权限/无数据。

## When to Apply

- 要改备货单头程（唯一自动化路径）。
- 改完发现库存单位费用没到预期，需按批次构成反推。
- 备货单相关的 UI 自动化取不到目标单时。

## Examples

### 2026-09-18 两次生产实测

| | 单行单 | 500 行单 |
|---|---|---|
| 备货单 | `OWS294A9T700030`（id 11498，POLAND） | `OWS294A9T700007`（id 11462，DANEEY） |
| SKU | `test001-white` ×1000 | `KS0248-DM-60-WHITE` ×1000 |
| payload | 1 行 | **500 行 / 1,063,587 字节** |
| 读 / 写耗时 | — / 瞬时 | 1,082 ms / **16,118~18,118 ms** |
| headFee | 0.20 → 0.25 | 8.12 → 9.12 → **4.08** |
| 库存单位费用 | 0.6006 → 0.6256 | 8.12 → 9.0467 → **4.3763** |

单位费用全部与 `Δ × 批次占比` 的预测值**分毫不差**。

工具：`cost_adjust/sellfox_restock_headfee_api.py`（默认 dry-run；会打印批次构成与预测值）

## Related

- [`sellfox-cost-adjust-api.md`](sellfox-cost-adjust-api.md) — 成本补录单（改采购单价）的私有接口契约，同样「读→改→整坨回发」
- [`../research/2026-09-18-sellfox-private-api-terminology.md`](../../research/2026-09-18-sellfox-private-api-terminology.md) — 私有接口 vs 公开 OpenAPI 的术语与判据
- [`../../research/2026-09-18-sellfox-cost-accounting-fifo.md`](../../research/2026-09-18-sellfox-cost-accounting-fifo.md) — 赛狐成本口径与 FIFO 批次
- [`../../../web_automation/docs/reference/sellfox-pitfalls.md`](../../../web_automation/docs/reference/sellfox-pitfalls.md) — 备货单编辑页的 vxe-table 与批次警告
