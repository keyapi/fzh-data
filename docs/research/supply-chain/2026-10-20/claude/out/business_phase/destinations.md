---
okf: v0.1
type: Report
title: Phase 1A 业务母集去向表（1,328 SKU）
date: 2026-10-22
owner: claude-worker
status: destination table only; no ranking, no quantity
inputs:
  - D:/Work/fzh-order-store/order_store.duckdb (read_only)
artifacts:
  - experiments/business_phase/build_destinations.py
  - out/business_phase/destinations.json
---

# Phase 1A：1,328 SKU 去向表

> 母集口径：`gs_orders.despatch_date` 落在 **2026-04..2026-09**（6 个完整月）的去重 `sku_tongtool`；不按 qty 过滤，零库存有销量照样在表内。
> 本阶段只做映射质量，不做销量排序、不出任何数量、不做补货判断。

## 1. 四类计数（必须相加）

| 去向 | 计数 |
|---|---:|
| `mapped_eligible` | 1,237 |
| `mapped_ineligible` | 29 |
| `unmapped` | 62 |
| `discontinued_excluded` | 0 |
| **合计** | **1,328** |

- 已映射 1,266（合格 1,237 + 不合格 29） / 未映射 62 = 与初始对账 1,266 / 62 一致，差额 **0**。
- **1,266「已映射」不等于已验证**：其中 29 个未通过检查（见 §3）。
- 零库存但有历史销量的 SKU：**246** 个，全部在表内。

## 2. 四项检查（逐行写入 `rows[].checks`）

| 检查 | 定义 | 命中行数 |
|---|---|---:|
| `duplicate_mapping` | 同一通途键多行映射或映射到多个 item_code | 0 |
| `one_code_multi_material` | 同一通途键解析出多个 EN 物料 | 0 |
| `alias_deleted` | 映射到的 item_code 不在 EN 物料主数据 | 0 |
| `uom_unknown` | 无 BOM 行，或 BOM 单位不是件/个/套 | 29 |
| `discontinued` | 物料在 nd_status 中标 disabled | 0 |

> 别名聚集（一个 item_code 被多个通途 SKU 引用）是正常现象，只作诊断字段 `item_alias_fan_in`，不作为失败码。

## 3. 已映射但不合格（逐条）

| SKU | EN 物料 | reason_codes |
|---|---|---|
| `C/Leaves-Grey-100-684-wow` | `KS0001-CMGDTH-100-GREY` | uom_unknown |
| `C/Leaves-Grey-138-684-wow` | `KS0001-CMGDTH-140-GREY` | uom_unknown |
| `C/Leaves-Grey-153-684-wow` | `KS0001-CMGDTH-153-GREY` | uom_unknown |
| `C/Leaves-Grey-183-684-wow` | `KS0001-CMGDTH-183-GREY` | uom_unknown |
| `C/Linen-Natural-60-688-wow` | `KS0248-CMM-60-HEMPNATURAL` | uom_unknown |
| `CEN963Velvet-DKGreen-138` | `KS0001-HLR-140-DARKGREEN` | uom_unknown |
| `CENC/Linen1625-Yellow-138` | `KS0001-CMM-140-YELLOW` | uom_unknown |
| `CENC/Linen1625-Yellow-153` | `KS0001-CMM-153-YELLOW` | uom_unknown |
| `CENC/Linen1625-Yellow-183` | `KS0001-CMM-183-YELLOW` | uom_unknown |
| `CENC/Linen1625-Yellow-97` | `KS0001-CMM-100-YELLOW` | uom_unknown |
| `SXQC-CEN003-GREEN-150` | `KS0001-TR-153-GREEN` | uom_unknown |
| `SXQC-CEN003-NZAIBLUE-150` | `KS0001-TR-153-DENIMBLUE` | uom_unknown |
| `SXQC-CEN003-ROBLUE-150` | `KS0001-TR-153-ROYALBLUE` | uom_unknown |
| `SXQC-CEN003-ROSE-150` | `KS0001-TR-153-ROSERED` | uom_unknown |
| `SXQC-CEN003-YELLOW-150` | `KS0001-TR-153-YELLOW` | uom_unknown |
| `SXQC-CENKMM-Blue-153` | `KS0001-MM-153-BLUE` | uom_unknown |
| `SXQC-CENKZ1324-SkyBlue-153` | `KS0001-DM-153-SKYBLUE` | uom_unknown |
| `TT0000958K0011375` | `KS0002-HLR-120-DARKGREEN` | uom_unknown |
| `TT0000958K0011381` | `KS0002-HLR-183-DARKGREEN` | uom_unknown |
| `TT0000996K0010996` | `KS0001-QDKTR-120-RUSTYORANGE` | uom_unknown |
| `TT0031102-zuhe-all` | `TJ#KS0238x1_KS0240x1_KS0241x1_KS0242x1_KS0243x1-001` | uom_unknown |
| `TT0031112K0063738` | `KS0301-XER-100-GREYBEIGE` | uom_unknown |
| `TT0031112K0063739` | `KS0301-XER-153-GREYBEIGE` | uom_unknown |
| `TT0031112K0063740` | `KS0301-XER-194-GREYBEIGE` | uom_unknown |
| `TT0031112K0063741` | `KS0301-XER-140-GREYBEIGE` | uom_unknown |
| `TT0031112K0063742` | `KS0301-XER-200-GREYBEIGE` | uom_unknown |
| `TT0031192K0063867` | `TJ#KS0334x1_KS0335x1_KS0336x1-001` | uom_unknown |
| `TT0312566K0064133-2` | `KS0530-SZSRBCTTM-90x60x36-BEIGE` | uom_unknown |
| `TT0312639K0064284` | `KS0464-FHXYR-60x45x42-RED` | uom_unknown |

## 4. 未映射 62 个（逐个列出，不猜配）

| SKU | 名称形态 | 订单行 | 库存行 |
|---|---|---:|---:|
| `Buttonkit` | descriptive_name_key | 16 | 4 |
| `Buttonkit-pl` | other_unmapped_key | 1 | 1 |
| `C/Cord-Black-194-707-wow-Cover` | cover_alias_suffix | 3 | 1 |
| `C/Cord-White-138-706-wow-Cover` | cover_alias_suffix | 7 | 1 |
| `C/Linen-DKBlue-194-660-WOW-Cover` | cover_alias_suffix | 1 | 1 |
| `C/Linen-DKGrey-60-651-WOW-Cover` | cover_alias_suffix | 1 | 1 |
| `C/Linen-LTGrey-194-658-WOW-Cover` | cover_alias_suffix | 1 | 1 |
| `C/Linen-Natural-138-688-wow-Cover` | cover_alias_suffix | 1 | 1 |
| `C/Linen-White-153-662-WOW-Cover` | cover_alias_suffix | 2 | 1 |
| `C/Linen-White-183-662-WOW-Cover` | cover_alias_suffix | 1 | 1 |
| `C/Linen-White-194-662-WOW-Cover` | cover_alias_suffix | 4 | 1 |
| `C/Velvet-DKBlue-100-700-wow-Cover` | cover_alias_suffix | 4 | 1 |
| `C/Velvet-Yellow-100-698-wow-Cover` | cover_alias_suffix | 1 | 1 |
| `C/Velvet-Yellow-183-698-wow-Cover` | cover_alias_suffix | 1 | 1 |
| `CEN-No/B-Velvet-Grey-138-Cover` | cover_alias_suffix | 1 | 1 |
| `CEN-PPCotton-5lb` | other_unmapped_key | 1 | 2 |
| `CENC/Linen1626-Coffee-153-Cover` | cover_alias_suffix | 1 | 1 |
| `CENVel1612-Black-194-Cover-out` | other_unmapped_key | 1 | 2 |
| `Cotton-EU` | other_unmapped_key | 1 | 1 |
| `Cotton-US` | other_unmapped_key | 1 | 2 |
| `DLZYFX001` | other_unmapped_key | 2 | 4 |
| `InvitationLetter` | descriptive_name_key | 4 | 2 |
| `PP10LB` | PP_weight_key | 13 | 1 |
| `PP15LB` | PP_weight_key | 2 | 1 |
| `PP2.2LB` | PP_weight_key | 6 | 1 |
| `PP20LB` | PP_weight_key | 7 | 1 |
| `PP30LB` | PP_weight_key | 3 | 1 |
| `PP5LB` | PP_weight_key | 9 | 1 |
| `PPL-RockStone-7PCS-Cover` | cover_alias_suffix | 1 | 2 |
| `T2398P154414` | T_P_numeric_key | 1 | None |
| `T2398P154418` | T_P_numeric_key | 12 | None |
| `T2398P154419` | T_P_numeric_key | 3 | None |
| `T2398P154421` | T_P_numeric_key | 6 | None |
| `T2398P154422` | T_P_numeric_key | 2 | None |
| `T2398P154423` | T_P_numeric_key | 1 | None |
| `T2398P154427` | T_P_numeric_key | 3 | None |
| `T2398P154428` | T_P_numeric_key | 1 | None |
| `T2398P154445` | T_P_numeric_key | 3 | None |
| `T2398P154450` | T_P_numeric_key | 2 | None |
| `T2398P272089` | T_P_numeric_key | 2 | None |
| `T2398P272100` | T_P_numeric_key | 2 | None |
| `T2398P272102` | T_P_numeric_key | 3 | None |
| `T2398P310005` | T_P_numeric_key | 1 | None |
| `TT0000668K0063798-Cover` | cover_alias_suffix | 1 | 1 |
| `TT0000670K0063784-Cover` | cover_alias_suffix | 1 | 1 |
| `TT0000752K0062989-Cover` | cover_alias_suffix | 1 | 1 |
| `TT0020018K0062867-Clip` | tt_numeric_key_without_mapping | 1 | 1 |
| `TT0031154K0063859-Cover` | cover_alias_suffix | 1 | 1 |
| `TT0312599K0064196-Cover` | cover_alias_suffix | 1 | 1 |
| `TT0312614K0064240` | tt_numeric_key_without_mapping | 4 | 1 |
| `TT0312687K0064377-Cover` | cover_alias_suffix | 12 | 3 |
| `TT0312687K0064377-Foam` | foam_alias_suffix | 11 | 3 |
| `W1247125571` | other_unmapped_key | 2 | None |
| `W1247P160451` | other_unmapped_key | 1 | 1 |
| `W1247P289796` | other_unmapped_key | 2 | None |
| `W1885P306886` | other_unmapped_key | 1 | None |
| `W1960P402914` | other_unmapped_key | 1 | None |
| `W1960P412224` | other_unmapped_key | 1 | None |
| `W2824S00039` | other_unmapped_key | 1 | None |
| `W3723P344016` | other_unmapped_key | 1 | None |
| `W3723P344022` | other_unmapped_key | 1 | None |
| `W3723P345018` | other_unmapped_key | 1 | None |

每个未映射行的 `evidence_pointer` 给出 `gs_orders` 抽样行键与 `stock_latest` 行数；`unmapped_evidence.absence` 给出两张映射表都不存在的断言；`prefix_candidates_not_adopted` 只记录形近键，**不用来配映射**。

## 5. 对账

| 项 | 值 |
|---|---|
| 入 / 出 | 1,328 / 1,328，0 丢弃 |
| 四类相加 | 1237 + 29 + 62 + 0 = 1328 |
| 与 1,266 / 62 | 一致，差额 0；无调整 |
| DB 只读 | 运行前后 sha256 一致（`25579c5dcd80…`） |

## 6. 本阶段不做

- 不做销量排序、不分 80/15/5、不算 90 天节奏、不出任何数量或补货结论。
- 不猜配未映射 SKU；不把“无销量/低销量”当停产，停产类只认明确证据（当前证据源只有 nd_status，命中 0）。

