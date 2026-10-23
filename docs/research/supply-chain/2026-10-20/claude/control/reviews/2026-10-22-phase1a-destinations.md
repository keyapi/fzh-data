---
okf: v0.1
type: Review
title: Phase 1A 业务母集去向表（1,328 SKU）— 生成与对账记录
date: 2026-10-22
owner: claude-worker
status: 完成；只做映射质量，不做排序/数量
inputs:
  - D:/Work/fzh-order-store/order_store.duckdb（read_only）
artifacts:
  - experiments/business_phase/build_destinations.py
  - out/business_phase/destinations.json
  - out/business_phase/destinations.md
---

# Phase 1A：1,328 SKU 去向表

> 依据 D13/D14：业务母集固定 **1,328 个近 6 个月有销量的通途 SKU**；先出逐个去向表，
> **再做**销量排序。映射质量与销量排序不得在同一脚本 —— 本脚本只做前者，
> 不排序、不分 80/15/5、不出任何数量、不做补货判断。
> 未访问生产、未扩样、未下单；DB 只读，运行前后 sha256 一致。

## 1. 母集口径与复现

| 项 | 值 |
|---|---|
| 定义 | `gs_orders.sku_tongtool` 去重，`despatch_date` ∈ **2026-04..2026-09**（6 个完整月） |
| 日期字段 | `despatch_date`（不是 `sale_date`；后者同窗口只有 1,326 个 SKU，差 2 个，故明确固定） |
| 数量过滤 | **无**（qty≤0 的记录同样计入母集；按 `qty>0` 过滤会漏 1 个，等于先删后报） |
| 结果 | **1,328**，与冻结值一致；脚本内断言，不等即退出 |

## 2. 四类去向（相加 = 1,328）

| 去向 | 计数 | 说明 |
|---|---:|---|
| `mapped_eligible` | **1,237** | 恰好映射到一个 EN 物料，四项检查全过 |
| `mapped_ineligible` | **29** | 有映射，但 `uom_unknown` |
| `unmapped` | **62** | 两张映射表都无记录，逐个列出 |
| `discontinued_excluded` | **0** | 无明确停产证据（见 §6） |
| **合计** | **1,328** | 脚本断言 |

**与初始对账 1,266 / 62 的差额：0。**
已映射 = 1,237 + 29 = **1,266**；未映射 = **62**。没有调整、没有并入、没有先删后报。
**但「已映射」≠「已验证」**：1,266 里有 **29** 个过不了 UOM 检查（见 §3）。

零库存但有历史销量的 SKU：**246** 个，全部在表内（`zero_stock_with_sales=true`）。

## 3. 四项映射质量检查（逐行写进 `rows[].checks`）

| 检查 | 操作定义 | 命中 |
|---|---|---:|
| `duplicate_mapping` | 同一通途键出现多行（跨 `sku_map`/`sku_item`），或解析出多个不同 `item_code` | **0** |
| `one_code_multi_material` | 同一键解析出的 `item_code` 指向 **>1 个不同物料名**（`item_attr.item_name`） | **0** |
| `alias_deleted` | 映射到的 `item_code` 不在 EN 物料主数据 `item_attr` | **0** |
| `uom_unknown` | 映射到的物料没有 BOM 行，或 BOM 单位不是 件/个/套 | **29** |

> 两张映射表（`sku_map`、`sku_item`）键空间完全一致（各 3,482 键，互差 0 行），
> 因此 `duplicate_mapping` 与 `one_code_multi_material` 在本快照里结构性地为 0 ——
> 这是**查过之后的 0**，不是没查。
> **别名聚集是正常现象**：全表有 746 个 `item_code` 被 >1 个通途 SKU 引用
> （母集里命中 647 行），这是多平台别名指向同一物料，只写在诊断字段
> `item_alias_fan_in`，**不作为失败码**。

### 29 个 `mapped_ineligible`

全部是 `uom_unknown`：物料在主数据里存在、映射唯一，但 `bom` 表没有该物料的行，
所以「件/个/套」的单位基准无法确认。其中 2 个是套件（`TJ#KS0238x1_…`、`TJ#KS0334x1_…`），
其单位可能来自 Product Bundle 而不是 BOM —— 同样属于“本阶段未证”，不放行。

完整清单见 `destinations.json → ineligible_detail`，并带 `evidence_pointer`
（两张映射表行键 + `item_attr` + `bom` 查询位置）。

## 4. 62 个未映射（逐个列出，不猜配）

每个未映射行都有：

- `unmapped_evidence.absence`：两张映射表均无该键的断言（原文写进 JSON）；
- `unmapped_evidence.name_pattern`：键形态的客观标签（不是映射推断）；
- `unmapped_evidence.prefix_candidates_not_adopted`：形近键（严格前缀匹配），
  **只作上下文，绝不用来配映射**；24 行有这类形近键；
- `evidence_pointer`：`gs_orders` 抽样行键 + `stock_latest` 行数。

形态分布（62）：

| 形态 | 数量 | 说明 |
|---|---:|---|
| `cover_alias_suffix`（`-Cover`） | 21 | 皮壳别名，KS 物料表里没有独立映射 |
| `T_P_numeric_key`（`T2398P…`） | 14 | 纯数字/平台内部键 |
| `other_unmapped_key` | 16 | 其余（如 `Buttonkit`、`InvitationLetter`、`PP*` 之外的杂项） |
| `PP_weight_key`（`PP10LB` 等） | 6 | 按重量计的辅料键 |
| `descriptive_name_key` | 2 | 纯描述词 |
| `tt_numeric_key_without_mapping` | 2 | 通途数字键但映射表里确实没有 |
| `foam_alias_suffix`（`-Foam`） | 1 | 海绵别名 |

39/62 在 `stock_latest` 里仍有库存行（合计非零的 21 个）——它们不是“无货可忽略”，
所以必须留在表内等待人工核实，而不是静默丢弃。

## 5. 对账与可复现

| 项 | 结果 |
|---|---|
| 入 / 出 | 1,328 / 1,328，`dropped=[]`，无静默丢弃 |
| 四类相加 | 1,237 + 29 + 62 + 0 = 1,328 |
| 与 1,266 / 62 | 一致，差额 0，无解释性调整 |
| 每个 SKU 唯一 | 1,328 行、1,328 个不同 SKU |
| 每行必备字段 | `destination` + `reason_codes` + `evidence_pointer` 全量非空 |
| 重复生成 | 连跑两次，除 `generated_at` 外 **逐字节等价** |
| DB | 只读打开；运行前后 sha256 一致，变则拒绝发布 |
| 凭证 | `uv run python scripts/check_secrets.py` 零输出 |
| 临时文件 | 仓库根与 `out/business_phase/` 均无残留 |

## 6. 为什么 `discontinued_excluded = 0`

冻结快照里唯一的停用证据源是 `nd_status(item_code, disabled)`，覆盖的是 **ND# 内胆**，
不是成品 KS/TJ 物料；对 1,266 个已映射物料查询 `disabled='1'` 命中 **0**。
因此本阶段不产出停产类，**并且拒绝把“无销量/低销量/无库存”当作停产**——
那属于猜测，D13 明确禁止。若后续拿到 EN 的 `disabled`/`end_of_life` 字段，
本脚本加一个证据源即可，不改分类框架。

## 7. 已知边界（下一阶段处理，不在本阶段）

1. **未映射 62 个的人工核实**是独立工作流（D13：单独核实、不猜配）。
2. **UOM 29 个**需要补 BOM 或补“套件单位”规则；在此之前它们停在 `mapped_ineligible`。
3. 本脚本**不判断**“这个物料是否真的被这些平台别名共同指代”的业务合理性——
   只判断映射表的机械一致性（唯一性、主数据存在性、单位可读性）。
4. 销量排序 / 80-15-5 分层 / 90 天节奏是**另一个脚本**（D14 要求分开）。
5. 未把 `sale_date` 口径的 2 个差额 SKU 并入：母集口径固定为 `despatch_date`，
   差额已在此记录，不静默切换。

## 8. 复现

```bash
uv run python docs/research/supply-chain/2026-10-20/claude/experiments/business_phase/build_destinations.py
uv run python scripts/check_secrets.py
```

产物：`out/business_phase/destinations.json`（1.8 MB，逐行）与
`out/business_phase/destinations.md`（精简摘要）。

DONE P1A
