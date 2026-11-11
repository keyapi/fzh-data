---
okf: v0.1
type: Reference
title: 自己拉 EN「BOM Cost List V2」报表 + 三时点对照（机制三重验证）
description: 给出用 EN REST 自行抓取 BOM Cost List V2 的确切配方（含必需的 item_group 过滤与 ignore_prepared_report），并用 9/3 冻结快照 / 自拉 20261016 / 用户导出 20261016 / 当前 DB BOM 做三时点对照，证明「同一时点上 美中加工成本 ≡ 该时点 active+default BOM 的 total_cost」
date: 2026-10-16
module: tongtool_order_cost
tags: [cost, erpnext, rest, report, timepoint, validation, reference]
---

# 自己拉 EN 报表 + 三时点对照

> **起因（我的反思）**：BOM 成本表这么核心，我却一直只用「别人给的 9/3 冻结快照」，
> 既没自己拉当期基线，也没做多时点交叉——**结果时点陷阱踩了两次**。
> 本页是**补课**：把「怎么自己拉」固化下来，并给出三时点对照。

## 1. ✅ 自己拉报表的确切配方（**已验证可用**）

```bash
# 凭证在父仓库 EN_API/.env（ERP_API_KEY / ERP_API_SECRET），基址 https://erpnext.vilavi.cn
POST /api/method/frappe.desk.query_report.run
Headers: Authorization: token <key>:<secret>  |  Content-Type: application/json
Body:
{
  "report_name": "BOM Cost List V2",
  "filters": { "item_group": "三角靠枕" },        # ★ 必需，否则报 ValidationError「请设置物料组过滤条件」
  "ignore_prepared_report": 1                      # ★ 必需，否则返回空
}
→ message.columns（73 列）+ message.result（该物料组的行）
```

**踩过的三个坑**（都实测）：
1. **URL 里的空格必须编码**（`/api/resource/Item Group` → 不编码会 `InvalidURL: control characters`）。
2. **`filters` 里必须给 `item_group`** —— 不给报 `ValidationError: 请设置物料组过滤条件`（来自 `work_order_task` app）。
3. **必须 `ignore_prepared_report=1`** —— 否则 `columns=0 / result=0`（静默空）。

**物料组枚举**：`GET /api/resource/Item Group?filters=[["custom_model_id","like","KS%"]]` → **401 个 KS 物料组**。
（本仓库脚本：`out/ustx_wage_sim/fetch_en_bom_now.py`，只读，产 `en_bom_cost_<date>.csv`。）

**报表列名与 GS 导出不同**：报表 label 无逗号/换行（`美中加工成本USTX`），GS 表是 `美中加工成本, USTX`。
**报表口径**：**排除 `disabled=1` 的物料**（`disabled → None`），所以按组拉的总数会**少于含禁用件的 GS 导出**。

## 2. 三时点对照（3479 行/时点级，**机制三重验证**）

| 对比 | 共同键 | 一致 | 不一致 |
|---|---:|---:|---:|
| **我自拉的 20261016 vs 用户手导的 20261016** | 2101 | **2101** | **0** |
| **我自拉的 20261016 vs 当前 DB BOM `total_cost`** | 1610 | **1610** | **0** |
| **9/3 冻结快照 vs 我自拉的 20261016** | 2098 | 2089 | **9（漂移 0.4%）** |

**结论**：
1. **机制成立且被三重证明**：**同一时点**上 `美中加工成本, USTX` **≡** 该时点 active+default BOM 的 `total_cost`（0 例外）。
2. **我自拉 == 用户手导**（2101/2101）→ **REST 拉取可信**，**不再需要等人喂数据**。
3. **9/3 → 10/16 只漂移 9 个产品（0.4%）**，全部是那三组：
   - `KS0437-…-120x200x45-*`：177.0 → **271.285333333**
   - `KS0455-FHXWXNE-92x56x75-*`：206.479 → **90.306**
   - `KS0481-CTTM-45x45-*`：**0 → 104.035333333**

## 3. 对上一步「474 行 source_unverified」的修正理解

v3 里 `unverified_*` 的 474 行，**大部分不是「值漂移」，而是「覆盖差异」**：
- `unverified_bom_changed`（87 行）→ **只对应上面那 9 个产品**（漂移 0.4%）；
- `unverified_no_current_bom`（82）+ `no_item`（306）→ 多为 **9/3 导出含禁用件 / 当前 BOM 清单不含**，
  **不是值可疑**。

→ 所以「474 行待业务」这个说法要收窄：**真正需要看的是「9 个漂移产品 + 少量歧义/套件/豁免」**，
其余是**口径与时点的记账问题**。详见 [21](21-offline-evidence-table.md)。

## 4. 从此建立的**做法**（我反思的直接产物）

| 做法 | 说明 |
|---|---|
| **每次分析先自拉当期 EN 报表** | 不再只用别人的快照；脚本 `fetch_en_bom_now.py` 已就绪 |
| **多时点交叉** | 至少「当前 + 分析目标时点」两份，**先对齐时点再比结论** |
| **冻结带日期的基线** | `en_bom_cost_<YYYYMMDD>.csv`，进 `out/`（gitignore），供回溯 |
| **报表配方写进文档** | 见本页 §1（含 3 个坑） |

## 5. 未证实 / 局限

- 我的按组拉取覆盖 9/3 快照产品的 **2106/2346（89.8%）**，缺口主要来自 **`disabled=1`**（报表按设计排除）；**这不是错误，是口径**。
- 9/3 那一份**当时**的 BOM 状态仍不可见（只能靠「同一时点 0 例外」的机制去**推断**其来源）。
- 报表是否需要 `other` 类物料组（非 KS%-model）**未穷举**。
