---
okf: v0.1
type: Reference
title: 重量模板映射规格 · 品类尺寸面料编码 ↔ EN 重量模板物料号（ZLMB#）
description: 只读调查结果：GS「品类尺寸面料编码」与 EN「重量模板物料号 ZLMB#」之间的权威映射机制、尺寸档规则来源、对 723 组好行的反推复现率、以及 161 个空键的可补性
date: 2026-10-15
module: tongtool_order_cost
tags: [cost, ustx, weight-template, zlmb, erpnext, mapping, reference]
---

# 重量模板映射规格 · 品类尺寸面料编码 ↔ EN 重量模板物料号

> 调查对象：`tongtool_order_cost/out/profitability_audit/2026年7月订单_ustx2/shell_cost_import_values/import皮壳成本.csv`
> 两侧键：GS 侧 `品类尺寸面料编码`（形如 `SX-KZSJ-45-DM`）↔ EN 侧 `EN重量模板物料号`（形如 `ZLMB#KS0001-DM-45`）。
> 只读产出于 2026-10-15；EN 全程只 SELECT，未写任何表。

## 结论摘要

1. **权威映射是「两段拼装」，EN 只固化其中两段。** EN 里真正权威的关联是 **`Item Group.custom_item_group_code`（= GS 品类编码 `SX-KZSJ`）↔ 同行 `custom_model_id`（= KS 号 `KS0001`）**；面料侧权威表是 **`Item Attribute Value All Fabric`（中文名 ↔ EN 缩写 abbr）**。ZLMB 名称 = `ZLMB#{KS}-{面料abbr}-{尺寸档}`。
2. **尺寸档（原始尺寸→ZLMB 档位）规则不在 EN 里**：既无字段也无 DocType。它是「按(品类,面料)分别测算」的经验函数，源头在 GS/Colab 的人工测算表，**无法由 EN 独立再生**。
3. **反推复现率（对 723 组好行，留一法）**：只认 EN 权威字段 + 全局经验尺寸档规则 = **455/723 = 62.9%**；若只允许「尺寸本身即档位」则 31.7%。
4. **161 个空键：可补 45（高 40 / 中 5），另 116 个不能补**（EN 无对应重量模板或面料/品类未登记），已逐行给出原因，**不硬凑**。
5. 反面字段 `Item.weight_template_variant` 存在但 **15210 行全空**，**不是**映射机制。

## EN 里的权威映射机制（是什么、在哪）

GS 侧重在 `sx_processing_values/绍兴二次加工成本.csv`（含 `品类,面料,尺寸,品类编码,尺寸编码,品类尺寸面料编码`）；EN 侧 ZLMB = `重量模板#<品类>` 分组下、带 `<品类>面料` + `<品类>尺寸` 两个变体属性的 **Item Variant**。

三段的权威级别不同：

| 段 | GS 侧 | EN 侧权威载体 | 权威级别 |
|---|---|---|---|
| 品类（`SX-KZSJ`）→ KS（`KS0001`） | `品类编码` | `tabItem Group`：`custom_item_group_code` 与 `custom_model_id` **同一行** | **权威**（可 SQL 直查） |
| 面料（`DM` / `纯棉印花`） | `面料` / 编码第 3 段 | DocType `Item Attribute Value All Fabric`（`FAB-####`）：`attribute_value`(中文) ↔ `abbr`(缩写)；ZLMB 变体属性 `<品类>面料` 存**中文名** | **半权威**：中文↔缩写可查，但 **GS 面料码 ↔ EN 缩写无官方对照表**（见「存疑」） |
| 尺寸（`45`）→ 尺寸档 | `尺寸` | ZLMB 变体属性 `<品类>尺寸` = 名称第 3 段 | **非权威**：档位由外部规则决定，EN 不存规则（见下节） |

拼装公式（EN 侧代码即这么做的）：
```
ZLMB#{KS}-{面料abbr}-{尺寸档}
```

**证据（SQL）**
```sql
-- ① 品类编码 ↔ KS 的权威关联
SELECT name, custom_model_id, custom_item_group_code
FROM `tabItem Group`
WHERE custom_item_group_code IN ('SX-KZSJ','SX-KZPT','SX-KZPTBDYT');
-- 三角靠枕|KS0001|SX-KZSJ ; 平条靠枕|KS0002|SX-KZPT
-- 平条靠枕无压条|KS0249|SX-KZPTBDYT ; 圆滚靠枕|KS0004|SX-KZYG

-- ② ZLMB 的结构：分组 + 两个变体属性
SELECT parent, attribute, attribute_value
FROM `tabItem Variant Attribute` WHERE parent='ZLMB#KS0001-DM-45';
-- ZLMB#KS0001-DM-45 | 三角靠枕面料 | 涤麻
-- ZLMB#KS0001-DM-45 | 三角靠枕尺寸 | 45

-- ③ 面料权威表
SELECT name, attribute_value, abbr, fabric_translation
FROM `tabItem Attribute Value All Fabric` LIMIT 5;
-- FAB-0001|涤麻|DM ; FAB-0004|纯棉印花|CMYH ; FAB-0002|荷兰绒|HLR

-- ④ 反面字段：weight_template_variant 全空，不是机制
SELECT COUNT(*) total,
       SUM(weight_template_variant IS NOT NULL AND weight_template_variant<>'') filled
FROM tabItem;   -- 15210 | 0
```

**代码出处**（服务器只读查看，未改）：
- `.../apps/work_order_task/work_order_task/work_order_task/report/bom_cost_list_v2/bom_cost_list_v2.py:356` `get_zlmb_info()`：
  `item_parts = item["name"].split("-")` → `item_zlmb = f"ZLMB#{item_parts[0]}-{item_parts[1]}-{item_parts[2]}"`（与 `key_test/.../bom_cost_list/bom_cost_list.py:307` 同规则）。
- `EN_API/bom_weight_template/weight_template_tools.py`：报表侧按 `item.name.split('-')[:3]` 复原 ZLMB，读 `weight_template_variant`（该字段实际未用）。
- 本地 `sellfox_shipping/carriers/lizard/zlmb.py::commodity_sku_to_zlmb_item_name`：取 Sellfox SKU 前 3 段拼 `ZLMB#{key}`（同构，佐证命名三段结构）。

**结论**：EN 里不存在「重量模板 ↔ 基础产品/尺寸」的专用映射 DocType；唯一可 SQL 化的权威环节是 **`Item Group` 的 `custom_item_group_code ↔ custom_model_id`**。

## 尺寸档规则（来源与完整度）

**规则不在 EN**。`tabItem` 的 custom fields 里只有尺寸（`custom_size/sfg/fg_*` 长宽高）与重量，没有「原始尺寸→档位」的映射字段；`tabItem Group` 的自定义字段里也没有。全库未见相关 DocType。

从好行反推，观察到的档位与合并（**来自 GS 侧 723 组好行，不是 EN 声明**）：

- 主档位集（三角靠枕 KS0001 全量）：`45,60,80,100,120,140,153,160,183,194,200`。
- 观察到的合并：`90→100`、`123→120`、`138→140`、`150→153`、`180→183`。
- **但同一原始尺寸在不同面料下映射不同**（关键反例）：
  - `SX-KZSJ-80-CMM → ZLMB#KS0001-CMM-100`（80→**100**）
  - `SX-KZSJ-120-QRJL → ZLMB#KS0001-QRJL-140`（120→**140**）
  - `SX-KZSJ-160-QRJL → ZLMB#KS0001-QRJL-153`（160→**153**）
  - `SX-KZSJ-45-CMYH → ZLMB#KS0001-CMYH-60`（45→**60**）
  - 而 `SX-KZSJ-80-*`（多数面料）→ `-80`。

**结论**：尺寸档是 **按 (品类,面料) 分别测算** 的函数，且**不是纯字符串变换**（与 `11-plan-new-ustx-processing-table.md` 的既有结论一致）。EN 无完整规则，**缺一张「(品类编码/KS + 面料) → (原始尺寸→档位)」对照表**；若要在管道里稳定复现，必须由业务在 GS/Colab 侧把该表**显式落成数据**。

**`SXBZCP#`/`USTXBZCP#` 与 ZLMB 尺寸档的关系（Q3）**：
`SXBZCP#KS0001-*` 与 `USTXBZCP#KS0001-*` 的尺寸后缀集合 = `{45,60,80,100,120,140,153,160,183,194,200}`，与 `ZLMB#KS0001` 的尺寸档集合**完全相同**（KS0001 逐值一致）。它们是绍兴 / 美中USTX 的「包装成品」，**只有尺寸、没有面料维度**，且部分 KS 含合并前的原始尺寸（如 KS0002 多出 `138,180`）。
→ 用途：可作为「该 KS 合法尺寸档集合」的旁证（校验档位是否合法）；**不能**据此推出面料，也**不能**给出原始尺寸→档位的合并规则。

## 反推复现率（对 705 组好行）

口径说明：`import皮壳成本.csv` 共 902 数据行，其中 `EN重量模板物料号` 非空 **723 行**（任务所称「705」为同一集合的近似值），空 **161 行**。复现测试 = 用 **EN 权威字段**（KS 走 `Item Group` 映射 + 面料走 `All Fabric` 缩写）+ **经验尺寸档规则** 推出 ZLMB 全名，与实际值逐字比对，并对学习到的规则做**留一（LOO）**，避免自证。

| 规则层 | 命中 | 占比 |
|---|---|---|
| 仅「原始尺寸本身即档位」（EN 精确） | 229 | 31.7% |
| + 全局经验合并规则（`90→100` 等） | 365 | 50.5% |
| + 维度串首段匹配（部分品类档位是 `100x60x10` 之类） | **455** | **62.9%** |
| 剩余未复现 | 268 | 37.1% |

**为什么不是 100%**：① 尺寸档因人而异（上一节反例），全局规则覆盖不到；② GS 面料码 ↔ EN 缩写无对照表（如 `CMYH` 与 `CMGDTH` 不可互推）；③ 少数品类码未在 `Item Group` 登记。留一法显示：即便允许「同 (品类,面料) 其它行」学到的尺寸重映射，**样本内**看似可达 ~89%，但**留一后增益近乎为零**（同一 `(品类,面料,尺寸)` 组合在好行里基本只出现一次）——**说明该规则无法由本数据集独立再生**，只能由业务提供。

## 161 个空键能否补全

产出：`tongtool_order_cost/out/ustx_wage_sim/blank_wt_filled.csv`（列：`品类尺寸面料编码,推导出的EN重量模板物料号,依据(SQL/字段/规则),置信度,备注`）。

| 结果 | 行数 | 说明 |
|---|---|---|
| **可补** | **45** | 高 40 + 中 5；全部经 **EN 实存校验**（推得的 ZLMB 名在 `tabItem` 中查得到） |
| 不可补 | 116 | 逐行给出原因，`推导串` 留空，置信度=低 |

可补 45 的置信度口径：
- **高（40）**：KS 来自 `Item Group` 权威映射，面料来自权威缩写或 `All Fabric` 表，且尺寸档**精确命中**现存 ZLMB（例 `SX-KZYG-54-BJR → ZLMB#KS0004-BJR-54`）。
- **中（5）**：尺寸档经**经验合并规则**得到（例 `SX-KZSJ-123-ZBM → ZLMB#KS0001-ZBM-120`；`SX-KZSJ-180-JDTHFH → ZLMB#KS0001-JDTHFH-183`），或面料缩写来自「好行学习」。

不可补 116 的原因分布：
- **面料无法归一（59）**：该 KS 下不存在此面料的重量模板（例 `SX-KZSJYZ-45-MH`：KS0003 只有 `DM/HLR`；`KS0398-100-HM`：KS0398 只有 `YRSZML`）。
- **尺寸档无对应（55）**：该 `(KS,面料)` 在 EN 无此尺寸的模板。典型：`SX-KZSJ-*-CMYH`（12 行）——`ZLMB#KS0001-CMYH` **仅存在 `-60`**，其余尺寸在 EN 无重量模板，**故不补**（这正是「塌缩到 -60」的错误做法，已显式避免）。
- **无 KS（2）**：`YCSOFA001-0-YCSFCPML`、`SZ-JZZT-0-JZZTML` 的品类码未在 `Item Group` 登记。

## 未证实 / 存疑

1. **尺寸档规则的完整来源未证实**：EN 内无出处；本文的合并样例仅由 723 组好行反推，**覆盖不到**全部 `(品类,面料)`；结论是「EN 无此规则」，而非「规则表已找到」。
2. **GS 面料码 ↔ EN 缩写的对照表未证实**：`All Fabric` 表只有 `中文↔缩写`；GS 编码段（`CMYH2403`、`CMPR`）与 EN 缩写（`CMYH`、`PR`）的等价关系**靠好行学习**得出，无官方表；`CMPR→PR` 属推断，已降到「中」。
3. **「同品类不同面料可共用同一重量模板」的假设未证实**：对 `SX-KZSJ-*-CMYH` 等缺档行，是否可借用同 KS 其他面料的档位模板，**无 EN 依据，未采用**。
4. **`SXBZCP#/USTXBZCP#` 是否可用于校验档位**：仅证实尺寸词汇一致，**未证实**其 BOM 与 ZLMB 存在一对一指认关系。
5. **`Item.weight_template_variant` 的预期用途**：字段被建出但 0/15210 使用，是历史遗留还是待回填，**未知**。

## 证据清单（SQL / 路径:行号）

**EN（只读，站点 `erpnext.vilavi.cn`）**
| # | 证据 | SQL / 位置 |
|---|---|---|
| 1 | 品类编码↔KS 权威映射 | `SELECT name, custom_model_id, custom_item_group_code FROM \`tabItem Group\` WHERE custom_item_group_code<>''` → `三角靠枕\|KS0001\|SX-KZSJ` |
| 2 | ZLMB 结构与属性 | `SELECT name, variant_of, item_group FROM tabItem WHERE name LIKE 'ZLMB#%'`（1228 条）；`SELECT parent, attribute, attribute_value FROM \`tabItem Variant Attribute\` WHERE parent='ZLMB#KS0001-DM-45'` |
| 3 | 面料权威表 | DocType `Item Attribute Value All Fabric`（表 `tabItem Attribute Value All Fabric`，列 `attribute_value`,`abbr`,`fabric_translation`） |
| 4 | 反面字段全空 | `SELECT COUNT(*), SUM(weight_template_variant<>'') FROM tabItem` → `15210 \| 0` |
| 5 | 包装成品尺寸词汇 | `SELECT ... FROM tabItem WHERE name LIKE 'SXBZCP#%' / 'USTXBZCP#%'`（KS0001 = ZLMB 同套档位；KS0002 SXBZCP 多 `138,180`） |
| 6 | ZLMB 命名规则（代码） | `.../report/bom_cost_list_v2/bom_cost_list_v2.py:356`；`key_test/.../bom_cost_list/bom_cost_list.py:307` |

**仓库内文件**
| # | 证据 | 路径:行号 |
|---|---|---|
| 7 | 空键来源 + 好行 | `tongtool_order_cost/out/profitability_audit/2026年7月订单_ustx2/shell_cost_import_values/import皮壳成本.csv`（列1 编码 / 列2 重量模板号；902 数据行：好 723 / 空 161） |
| 8 | GS 品类·面料·尺寸三列 | `.../sx_processing_values/绍兴二次加工成本.csv`（列 `品类,面料,尺寸,品类编码,尺寸编码,品类尺寸面料编码`） |
| 9 | 既有结论（尺寸非纯字符串） | `tongtool_order_cost/docs/reference/cost-engine-spec/11-plan-new-ustx-processing-table.md` |
| 10 | ZLMB 命名同构（本地） | `sellfox_shipping/carriers/lizard/zlmb.py::commodity_sku_to_zlmb_item_name` |
| 11 | 本次产出 | `tongtool_order_cost/out/ustx_wage_sim/blank_wt_filled.csv`（161 行：可补 45 / 不可补 116） |

> 复现脚本（临时，未入库）：`%TEMP%/rep_final.py`、`%TEMP%/fill2.py`、`%TEMP%/zlmb_all.tsv`、`%TEMP%/ig_code.tsv`、`%TEMP%/fabric_master.tsv`。
