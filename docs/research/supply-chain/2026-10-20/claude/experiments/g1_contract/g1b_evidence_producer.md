---
okf: v0.1
type: Reference
title: 有界 Item/BOM 证据 producer（20 变体样本，v5）
description: 只读 Item/BOM 采样、结构证据 manifest、严格 flag/方向/共享组件语义与历史边界
date: 2026-10-21
tags: [supply-chain, evidence, item, bom, producer, bounded, historical]
---

# 有界 Item/BOM 证据 producer（20 变体样本，v5）

> 目的：为 `en_family_poc.py --variant-manifest` 生产**结构证据**样本，
> 验证 producer/consumer 契约、方向语义、共享组件与预算控制。
> **不是** G1 验收、销量等价或补货数量。

## 1. 边界与预算

- commit 基座 `e2f9c680`；producer P1 修正后 v5。
- 只读 EN（GET），单并发，请求间隔 ≥0.2s，timeout 30s。
- 首样本 **20 个变体**：14 PK（皮壳）、6 ND（内胆）；6 个 ND 的剥前缀 base
  不在 family manifest。
- Item list：`name in exact_codes`，34 行 / 1 页；BOM list：`item in (bases+variants)`，
  43 行 / 1 页；**不按 active/default 过滤**。
- 详情：34 Item + 43 BOM（BOM Item 子表 list 生产 403，逐单取父单）。
- 实际 **79/500 HTTP**、**19.8/900 秒**；`http_ok=79`，无错误、无预算超限。
- 无 Version 查询；无全表扫描、无大 IN、无写入；无样本扩张。

## 2. 结果（v5）

| 项 | 数值 |
|---|---:|
| 采样变体 | 20（14 PK / 6 ND） |
| `resolution=consistent` | 14（全部 PK，base 在 family） |
| `resolution=unresolved_canonical_mapping` | 6（全部 ND） |
| 结构比例 | 14/14 `ratio=1`；方向全部 `ks_parent_variant_component` |
| BOM 状态 | 43 个 `docstatus=1`、`is_active=1`、`is_default=37/43` |
| `evidence_scope` | 14 `current_structure_only`；6 `historical_unknown` |

6 个 ND 的 reason_code（共享组件，父 KS 边来自已抓 43 份 raw BOM）：

| reason_code | 数量 | 父 KS 边数 |
|---|---:|---:|
| `shared_component_multiple_parents` | 2 | 8（100 尺寸）、5（153 尺寸） |
| `shared_component_single_parent` | 1 | 1（194 尺寸） |
| `unresolved_canonical_mapping_no_parent` | 3 | 0（140/60/183，样本内未找到） |

- 不把 ND 的剥前缀 base 当 canonical；保留 `shared_parent_ks` 与
  `candidate_boms` 的实际 KS→ND 父边，多重父 BOM 视为组件复用，不随便选一个 KS。
- 有限样本未找到父边 → `no_parent`，不推断不存在。

## 3. Producer P1 修正

| 项 | 修正 |
|---|---|
| 反向 BOM | `variant_parent_ks_component` 只进 `excluded_boms`，reason `unsupported_direction`；不得进入合格候选，不得 `consistent`/`current_planning_eligible=True`；正反混合 → `conflict_mixed_direction`。 |
| 共享 ND | base 不在 `ks_items` → `unresolved_canonical_mapping`，reason_code 区分多父/单父/无父；保留 raw 父边与 `shared_parent_ks`；不再 `not_family`。 |
| 严格 flag | 只接受 bool、整数 **0/1**、浮点 **0.0/1.0**（与 0/1 等价）；字符串 `0/1/true/false` 显式解析；`2/-1/0.5/NaN/Inf` 与未知字符串 → `bom_flag_invalid` / `item_flag_invalid`。Item `disabled`/`has_variants` 同一解析。 |
| reason_code | 每条记录都有 `reason_code/reason_detail`；summary 增加 `by_reason_code`。 |

Consumer 增加 `variant_unresolved_canonical_mapping`：有该 resolution 的记录在
Apr–Sep 窗口仍 pending，不再笼统落到 `variant_base_not_family`。

## 4. Consumer / 回放（v5）

本地回放复用 d8 R1 的 2,024 行 SO 审计快照，**不新增生产查询**：

- `pending=1,769`：`variant_unresolved_canonical_mapping 537` +
  `variant_not_in_manifest 694` + `variant_base_not_family 419` +
  `variant_current_structure_only 119`；
- `family=132`（全裸 KS）、`out_of_scope=123`；**PK/ND family=0**；
- 所有 `evidence_scope` 无 `historical_verified`；14 PK 只到 `current_structure_only`；
- 两次回放忽略 `run_id` 的 audit SHA256 相同；
- 检查全绿：行守恒、PK/ND family 0、无历史升级、unresolved 原因、shared 父边保留、
  反向不 consistent。

## 5. 历史证据边界（不变）

- 当前 BOM 只证明抓取时点结构；不凭 `creation/modified/active/default` 或 Version
  空集升级 Apr–Sep 2026。
- 项目存在 `update_modified=False` 写入路径，`modified` 不是可靠历史见证。
- `historical_verified` 需可信历史内容锚点 + 覆盖时段完整重建/有效期，或仅对
  绑定不可变 BOM 版本的交易给 event 范围证据；不能泛化六个月。
- 无锚点保持 `current_structure_only` / `historical_unknown`，历史关系 pending。

## 6. 踩坑

1. **EN 返回 1/0 整数**：`is True` 会把 1 判 False；但 `bool('0')` 又会把字符串
   判 True。必须用严格 `flag()`，不能只靠 `bool()`。
2. **BOM Item 子表 list 403**：只能取 BOM 父单。
3. **反向 BOM 不能当合格结构**：`BOM.item=PK#…`、child=KS 是诊断边，不能 consistent。
4. **ND 是共享组件**：同一 ND# 可出现在多个 KS 成品 BOM；不能把剥前缀 base 当唯一
   canonical，也不能随便选一个父 KS。
5. **BOM list 混入无关父单**：分析前按 base/code 过滤；共享 ND 则按 `child==code`
   扫 KS 父单。
6. **数量归一**：组件 stock 累计 ÷ 输出 stock；同 UOM 需 `qty==stock_qty`，
   factor 只能为 1。

## 7. 离线单测

- `test_en_family_poc.py`（45 条）+ `test_en_variant_evidence.py`（21 条）
  = **66 条全绿**，不联网、不调 `main()`。
- 新增：反向 only/mixed、共享 ND 多父/单父、字符串 `'0'/'false'/'maybe'`、
  数值 `0.0/1.0` 等价与 `2/-1/0.5/NaN/Inf` invalid、Item disabled 非二值 invalid。

## 8. 产物与 hash（v5）

| 产物 | 路径 | SHA256 |
|---|---|---|
| evidence v5 | `out/family_poc/evidence_d8c473fe_v5/variant_evidence.json` | `1d6a7b33a16419d91d5a228921d3d4f37bc97e3e1326c2002544ab2ca0b2a590` |
| payload | 同上 manifest | `9d3c301ddd424bbc17d5acf012c9b19ba41a4c91793d4d43c96cd9e5342d7e4c` |
| raw items | `.../raw/items.jsonl` | `0a6a0db6d32e31c62350b30b68683d5d0d58abd8e5583e15bdc26fc77f82d620` |
| raw boms | `.../raw/boms.jsonl` | `f2a731181f412ec175012e88bb8b8879c5e6924e87e258edfa2800f763c7e0e0` |
| producer zip | `out/family_poc/evidence_d8c473fe_v5.zip` | `db44dadf081d83e28a1281ce778cecd201bfece02082ef9bc075f4c017ebdefe` |
| replay audit R1 | `out/family_poc/evidence_replay_e2f9c680_v5/line_audit.evidence.jsonl` | `e7c1a612cc746861039881194f8dc95ec2b367e4f02fd850e6f6e78770c5421a` |
| replay 归一化 audit | R1/R2 相同 | `26ea6041413fa543132ec32652ad1cea8ea33f1805417d8bbec5311854857c87` |
| replay zip | `out/family_poc/evidence_replay_e2f9c680_v5.zip` | `a3b23cf1684f056daea68f7e7988a12842b40528d61d74f5c5393afaed9bc13c` |

v1/v2/v3/v4 为踩坑与中间版本，不作最终产物。

## 9. 未做

- 未查 Version/归档，未重建历史有效期；历史关系仍 pending。
- 未扩样到全量 PK/ND；20 个只是样本。
- 未输出终端需求/补货量；`cover_equivalent_factor` 不参与聚合。
- U01 与旧 T 保持关闭。
