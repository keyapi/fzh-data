---
okf: v0.1
type: Reference
title: 有界 Item/BOM 证据 producer（20 变体样本）
description: 只读 Item/BOM 采样、结构证据 manifest、预算与历史边界；current_structure_only 不改写 Apr–Sep
date: 2026-10-21
tags: [supply-chain, evidence, item, bom, producer, bounded, historical]
---

# 有界 Item/BOM 证据 producer（20 变体样本）

> 目的：为 `en_family_poc.py --variant-manifest` 生产**结构证据**样本，
> 验证 producer/consumer 契约与预算控制。**不是** G1 验收、销量等价或补货数量。

## 1. 边界与预算

- commit `d8c473fe`，只读 EN（GET），单并发，请求间隔 ≥0.2s，timeout 30s。
- 首样本 **20 个变体**：14 个 PK（皮壳）、6 个 ND（内胆）；其中 6 个 base 不在
  family manifest（suspicious）。
- Item list：`name in exact_codes`，34 行 / 1 页，chunk 50。
- BOM list：`item in (KS bases + variants)`，43 行 / 1 页；**不按 active/default 过滤**。
- 详情：34 个 Item 父单 + 43 个 BOM 父单（BOM Item 子表 list 生产 403，必须逐单取父单）。
- 实际 **79/500 HTTP**，**19.8/900 秒**；`http_ok=79`，无错误、无预算超限。
- 无 Version 查询；无全表扫描、无大 IN、无写入。

## 2. 结果

| 项 | 数值 |
|---|---:|
| 采样变体 | 20 |
| `resolution=consistent` | 14（全部 PK，base 在 family） |
| `resolution=not_family` | 6（ND，base 不在 KS manifest） |
| 结构比例 | 14/14 `ratio=1`（BOM output 1 × 组件 1） |
| 方向 | 14/14 `ks_parent_variant_component` |
| BOM 状态 | 43 个全部 `docstatus=1`、`is_active=1`、`is_default=37/43` |
| `evidence_scope` | 14 `current_structure_only`；6 `historical_unknown` |

- `PK#KS0001-…` 的 canonical KS 有唯一父 BOM，组件行含该 PK# 与一个 ND#；
  结构 1:1，`ratio=1`。
- `ND#KS0001-100-CYF-WHITE` 等内胆码是**多个成品 BOM 的共享子件**，
  base `KS0001-100-CYF-WHITE` 不在 969 个 KS 成品清单，故 `not_family`；
  这不是缺失，而是“内胆不是独立成品 family”的表现。内胆独立销售不产生皮壳需求。

## 3. Consumer 校验（本地，无生产）

- `fp.load_variant_evidence(v3)` 通过：`entries=20`、`schema=variant_evidence/1`、
  `rule=variant-evidence/1`、`site=https://erpnext.vilavi.cn`、payload hash 匹配。
- 用 v3 对 d8 R1 的 2,024 行做本地分类：
  - `pending=1,769`：`variant_base_not_family 956` +
    `variant_not_in_manifest 694` + `variant_current_structure_only 119`；
  - `family=132`（全部裸 KS），`out_of_scope=123`；
  - **PK/ND 进入 family 的行数 = 0**。
- 即：当前结构证据被正确识别为 `current_structure_only`，不会放行 Apr–Sep 历史关系。

## 4. 历史证据边界（Codex 结论，已遵守）

- 当前 BOM 只证明**抓取时点**的结构；不能凭 `creation/modified/active/default`
  或 Version 空集升级为 Apr–Sep 2026 的历史事实。
- 项目存在 `update_modified=False` 写入路径，`modified` 不是可靠历史见证。
- `historical_verified` 需要：可信历史内容锚点 + 覆盖时段完整重建/有效期；
  或仅对明确绑定不可变 BOM 版本的交易给 event 范围证据，**不能泛化六个月**。
- 无历史锚点 → 保持 `current_structure_only` / `historical_unknown`，历史关系 pending。
  本 producer 不查 Version，也不把当前 BOM 回填为历史真值。

## 5. 踩坑

1. **EN 返回 1/0 整数，不是 JSON boolean**：`is_active`/`is_default` 用 `is True`
   会把 43 个 active BOM 全判成 inactive（v1 得到 14 个 `missing_evidence`）。
   必须 `bool(...)`；v2/v3 修正后 14 个 `consistent`。
2. **BOM Item 子表不能 list**：生产 403，只能 `GET /api/resource/BOM/{name}` 取父单。
3. **BOM list 按 `item in` 会带出 bases 与 variants 的 BOM**；分析前先按
   `bom.item in (base, code)` 过滤，否则 `excluded_boms` 充满无关 BOM（v2 噪声）。
4. **同一 ND# 有 2–3 个父 BOM 且 default 不唯一**；default 不能消解冲突，
   本样本按 canonical/base 过滤后没有冲突，但规则必须保留。
5. **ND# 不是成品 family**：base 常不在 KS manifest；不要强制映射为某个成品，
   也不要用内胆独立销售生成皮壳需求。
6. **数量归一**：用组件 stock 累计 ÷ 输出 stock 数量；同 UOM 需 `qty==stock_qty`，
   factor 只能为 1。BOM 里 `qty=1` 不能直接当 1:1，需按 stock 数量计算。
7. **预算**：list 1 页、Item/BOM 详情各 34/43，总计 79 HTTP；后续扩样要保持
   ≤500 HTTP、≤15 分钟、单并发。

## 6. 离线单测

`test_en_variant_evidence.py`（9 条，不联网）：整数 flag 归一、inactive 判定、
stock 比例、反向方向记录、consistent/conflict/not_family、consumer 深度校验
（补历史锚点后 14/14 通过）、选择确定性。加上 consumer 的 44 条，共 53 条全绿。

## 7. 产物与 hash

| 产物 | 路径 | SHA256 |
|---|---|---|
| evidence v3 | `out/family_poc/evidence_d8c473fe_v3/variant_evidence.json` | `0f365b99f4c3b6b93761637b3c2f8650fe67b012cdac31bb095fba9d7e70a49d` |
| payload hash | 同上 manifest | `fe8f5912990917213e039b2ba2b343e5f5c1d18bef64aa2c93d0d7dede9451e5` |
| summary v3 | `.../variant_evidence_summary.json` | 由报告引用 |
| raw items | `.../raw/items.jsonl` | `0a6a0db6d32e31c62350b30b68683d5d0d58abd8e5583e15bdc26fc77f82d620` |
| raw boms | `.../raw/boms.jsonl` | `f2a731181f412ec175012e88bb8b8879c5e6924e87e258edfa2800f763c7e0e0` |
| zip v3 | `out/family_poc/evidence_d8c473fe_v3.zip` | `69b679af286aa1bbc942266789bb783aed2721217bd0e705141d037fd27bd2fa` |
| producer | `en_variant_evidence.py` | `b35e758ee24b39fc930956fb60f5b52efb9ea7749ea1e55c6c7aadef7a0c27a1` |

v1（boolean bug）evidence `603b9a6e…`、v2（无关 BOM 噪声）`31104f7e…` 仅作踩坑对照，
不作为最终产物。

## 8. 未做

- 未查 Version/归档，未重建历史有效期；历史关系仍 pending。
- 未扩样到全量 PK/ND；20 个只是样本，不是总体比例。
- 未输出终端需求/补货量；`cover_equivalent_factor` 不参与聚合。
- U01 与旧 T 保持关闭。
