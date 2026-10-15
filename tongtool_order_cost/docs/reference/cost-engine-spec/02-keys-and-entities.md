---
okf: v0.1
type: Reference
title: 键与实体体系（三套键 / 前缀实体 / 分流字段 / 去重键）
description: 成本引擎的三套键（品类尺寸面料编码 / 品类尺寸编码 / EN 重量模板编号）、各前缀实体含义、绍兴发货方式与成本来源编码字段、6 列去重键，以及键的坑（同键歧义 / 空键 / 命名不一致）
date: 2026-10-15
module: tongtool_order_cost
tags: [cost, keys, entities, encoding, reference]
---

# 键与实体体系

> 本页是「什么是这个键 / 这个前缀代表什么物料 / 拿什么去 join」的单一事实源。
> 取值规则见 [04-cost-decision-tables.md](04-cost-decision-tables.md)；数据源清单见 [03-data-sources.md](03-data-sources.md)。

## 1. 三套键

| 键 | 构成 | 出现处 | 说明 |
|---|---|---|---|
| **`品类尺寸面料编码`** | `品类尺寸编码 + "-" + 材料编码.replace("ML-","")` | 订单写回表、`import皮壳成本`、`测算 美中USTX二次加工成本` | **材料编码为空 → 只剩 `品类尺寸编码`**（无尾段 `-`）。是订单与 GS 成本表的**主 join 键** |
| **`品类尺寸编码`** | `品类编码 + "-" + 尺寸` | 同上（去掉面料段） | 比面料编码**粗一级**；用于面料列缺失时的 rematch（头程 USTX 表 77 个缺失键可经此修复） |
| **`重量模板编号`（EN 等价键）** | EN 侧的物料号 | EN `Item` / BOM | 并入通途订单时**改名为 `EN重量模板物料号`** 列；`ZLMB#` 前缀即重量模板物料 |

> **口径**：`品类尺寸面料编码` 与 EN 的 `重量模板编号` 是**同一概念的两种表达**——GS 侧写复合串，EN 侧写物料号。两套键在 `import皮壳成本` 表内**同表并存**（列 `品类尺寸面料编码` + 列 `EN重量模板物料号`），用于桥接。

**代码锚点**：`ustx_cost_compare.py:34`（`KEY_COL="品类尺寸面料编码"`）、`:53-54`（`SHELL_IMPORT_KEY` / `SHELL_IMPORT_WT="EN重量模板物料号"`）、`:681`（`品类尺寸编码` 作 `key_nofabric`）。

## 2. 前缀实体

| 前缀 | 含义 | 说明 |
|---|---|---|
| `PK#` | **皮壳**物料 | `doc_event.py:1371` 分流出 `cost_pk` |
| `SXBZBCP#` | 绍兴包装**半成品** | 绍兴侧加成「半成品档」源 |
| `SXBZCP#` | 绍兴包装**成品** | 绍兴侧加成「成品档」源 |
| `USNJBZCP#` | **美东**包装成品（国外包装成品） | 目的地加工成本 = 其 active+default BOM `total_cost` |
| `USTXBZCP#` | **美中**包装成品 | 同上 |
| `PLBZCP#` | **波兰**包装成品 | 同上 |
| `ZLMB#` | **重量模板**（= EN `重量模板编号`） | 物料组名；1228 个 `ZLMB#` 物料 `default_material_request_type=Purchase` |
| `ML-` | **材料编码**前缀 | 构成面料段时**剥掉**（`.replace("ML-","")`）；`ND#` 为内胆（`doc_event.py:1799` → `cost_nd`） |

> 实体组命名规律：`{目的地}包装成品#{item_group}`（`bom_cost_list_v2.py:279/318/503/758/796`）。
> ⚠️ **不存在**「国外加工**成品** BOM」——只有「国外**包装**成品」（见 [09](09-known-issues-register.md) D3）。

## 3. 分流字段

| 字段 | 值域 / 取值 | 载体 | 说明 |
|---|---|---|---|
| `custom_shipment_type_to_branch` | `皮壳` / `成品` / `半成品`（Select，label `Shipment Type To Branch`） | `Item Group` 自定义字段 | = **「绍兴给（国外）分公司的发货方式」**。由 KS 码 → Item Group `custom_model_id` 解析（`get_shipment_type_by_ks_code` `bom_cost_list_v2.py:723`；入口 `extract_ks_code_from_item_code` `:621`） |
| `二次加工成本来源编码` | `2CJG-US`(美东) / `2CJG-PL`(波兰) / `2CJG-SX`(绍兴) / `2CJG-USNJ-TEST` / `2CJG-USTX-TEST` | 订单写回表列 / GS `订单发货仓库对应成本来源` | 决定「二次加工成本」走哪一侧来源 |
| `头程运费来源编码` | `HEAD-US` / `HEAD-USTX` / **`HEAD-USTX-PK`** / `HEAD-PL` / `HEAD-USFBA` / `HEAD-USHWC` / `HEAD-EUHWC` / `HEAD-EUFBA` / `HEAD-JPFBA` / `HEAD-CAHWC` / `HEAD-UKFBA` / `HEAD-SX` | 同上 | 决定头程取「皮壳/半成品/成品」哪一列；`HEAD-SX`→0 |
| `default_material_request_type` | `Purchase` / `Manufacture` / `Material Transfer` / `Material Issue` / `Phantom`(残留选项) | `Item` 原生字段 | **不是业务标记**（多数为未改动的默认 `Purchase`）；详见 [../en-material-request-type-spec.md](../en-material-request-type-spec.md) 与 [09](09-known-issues-register.md) C8 |

### 3.1 绍兴发货方式分布（401 个 KS Item Group，2026-10-15 线上态）

| 取值 | 数量 | 备注 |
|---|---:|---|
| 成品 | 165 | 「成品」是**单一桶**，混「绍兴直接采购 / 不用加工 / 仍需加工」，三者不可区分（[09](09-known-issues-register.md) C9） |
| 皮壳 | 156 | — |
| 半成品 | 62 | — |
| 空 / NULL | 18 | （NULL 12 + 空串 6） |

来源：[../en-shaoxing-ship-method-taxonomy-spec.md](../en-shaoxing-ship-method-taxonomy-spec.md)。

## 4. 6 列去重键

用于**规则表**（`Jeck特殊规则-订单改销售额成本` 等）匹配订单行、以及重写引擎内部去重：

```
运营人员 + 发货区域 + 通途SKU + 渠道账号不含国家 + 渠道账号 + 发货仓按销售汇总分类
```

- **`渠道账号不含国家`** 由 `渠道账号` 派生：`渠道账号.str.strip().str[:-2]`（去掉末尾 2 位国家码；`io_loaders.py:32-33`）。
- **代码锚点**：`engine_170.py:33-40`（`DUP_COLS`）；匹配逻辑 `:186-205`（逐列非空则参与 AND 过滤，`通途SKU` 必需）。
- `发货区域` 值域：`美国 / 欧洲 / 日本 / 加拿大 / 其它`（`engine_170.py:41`）。
- **去重选项** `keep=last|first`（规则表同键取最后/首条）。

## 5. 键的坑

| # | 坑 | 现象 | 处置 |
|---|---|---|---|
| K1 | **同键指向不同重量模板** | `import皮壳成本` 同 `品类尺寸面料编码` 指向多个 `EN重量模板物料号`；**7 月有 3 个**冲突键 | **不猜首/末行**：该键不进索引，对应订单行按 `ambiguous_shell_key` 排除（`ustx_cost_compare.py:207-213`；见 [04](04-cost-decision-tables.md) §7、产出 `08_重复歧义键`） |
| K2 | **空键** | 7 月订单 75 行 `品类尺寸面料编码` 为空 | 单独统计，不并入匹配（详见 [../old-system-source-coverage-audit.md](../old-system-source-coverage-audit.md)） |
| K3 | **命名不一致** | 重量模板 `ZLMB#KS0383-HLR- 140*50*24`（含空格 + `*`）vs 规范式 `...-140x50x24` | 直连会漏匹配；需归一化（[09](09-known-issues-register.md) C7） |
| K4 | **面料段可缺** | 材料编码为空 → 键退化为 `品类尺寸编码` | rematch 时用 `品类尺寸编码` 兜底（如头程 USTX 表 77 个缺失键） |
| K5 | **同键在报表 vs 订单同步口径不同** | 同一物料在两链路得到**不同绍兴成本**（非键本身问题，是取数口径） | 见 [04](04-cost-decision-tables.md) §4、[09](09-known-issues-register.md) A1 |

## 6. 证据清单

- `ustx_cost_compare.py`：`:34, :53-54, :207-213, :681`
- `engine_170.py`：`:33-40, :41, :186-205, :259-264`
- `io_loaders.py`：`:32-33`
- `bom_cost_list_v2.py`：`:279, :318, :503, :621, :723, :758, :796`
- `doc_event.py`：`:1371, :1799`
- [../en-shaoxing-ship-method-taxonomy-spec.md](../en-shaoxing-ship-method-taxonomy-spec.md)、[../en-material-request-type-spec.md](../en-material-request-type-spec.md)、[../old-system-source-coverage-audit.md](../old-system-source-coverage-audit.md)
