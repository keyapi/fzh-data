---
okf: v0.1
type: Reference
title: SKU 归一、单位层级、套件与拆包成品：供应链补货的复用规则
date: 2026-10-30
category: best-practices
module: supply_chain
problem_type: best_practice
component: tooling
severity: high
applies_when:
  - "通途 SKU / EN 物料 / 客户物料号对不上，怀疑大小写或后缀"
  - "遇到 TJ# 套件、-2PCS/-3PCS、Cover/Foam、拆包成品"
  - "订单、库存、EN SO/DN 的数量口径不一致"
tags: [sku-matching, uom, bundle, split-package, shared-code, casefold]
---

# SKU 归一、单位层级、套件与拆包成品

## Context

供应链里同一个东西至少有四种写法：

1. EN 物料：`KS...` / `PK#...` / `ND#...` / `HM...` / `TJ#...`；
2. 通途 SKU：`TT...`、`C/...-wow`、`XINGQIU-...`、带 `-2PCS/-3PCS/-Cover/-new/-1/-2` 的变体；
3. 客户物料号：平台/客户侧的别名，一个 EN 可有几十个；
4. 订单/单据行：可能按套、按件、按成品、按皮壳、按组件记录。

如果直接按字符串等值匹配，或按后缀猜件数，就会反复出现「EN 明明有、系统说没有」「库存 0 被当缺失」「一套被乘了两次」。本文是把这些坑收敛成可复用规则。

## Guidance

### 1. 大小写与后缀归一

- 所有 SKU 比较先 `casefold()`；EN/通途都存在 `TT...` 与 `tt...`、`-2PCS` 与 `-2pcs`。
- 匹配前按顺序去掉：`OLD_` 前缀、`-new`、`-Cover/-cover/-C`、`-c`、`-1/-2`（裸数字，若没有 PCS 语义）；保留基础码。
- 用 `SKU/SKU别名` 别名表（通途商品导出）建索引；一个别名可能对应多个 SKU，冲突时保留全部候选，不取第一个。
- 匹配命中后必须记录 `mapping_basis`（sku / alias / old_prefix_strip / casefold），方便回查。

### 2. 零库存不是缺失

- `available=0` 的行不阻塞供给、不进入「隔离/待补证」清单；只有非零且无法映射/无法组装的行才需要处理。
- 没有该 SKU 的库存行 → `unknown/uncovered`，不是 0；有行且 0 → 已证零。
- 共享码库存为 0 时，不要因为产品上登记过共享码就把它判成共享待核。

### 3. 单一形态是正常的

- 一个产品在通途只有成品、或只有皮壳，是正常的最初形态；`-Cover` 只是为单独卖皮壳加的 SKU，没有也正常。
- 发货方式决定补货形态：皮壳模式补皮壳（成品库存也算供给）；成品/半成品模式补成品；单一形态不构成 partial。
- 只有「该模式要求的形态缺失/未知」才是 partial；缺非必需形态不算。

### 4. HM 海绵

- HM 是独立海绵，不是成品的附属行；有海绵库存即可作为海绵供给/独立需求处理，不要求成品行。
- HM 与成品需求不能相加；共享 Foam 只保留一个数量池。

### 5. 套件 TJ#

- TJ# 是 EN Product Bundle，不是库存物料；必须读 Product Bundle 子表（item_code, qty）。
- 套件需求按「套」，组件供给按「个」；`set_qty × component_qty` 换算；套件本身不作为库存。
- 套件绝不能标 `unknown/unmapped`；EN 不活跃但有库存时标 `mapped_inactive/old_set`。
- 分公司补货通常按下单单件；套件拆解只用于库存/供给换算，不覆盖订单历史。

### 6. 拆包成品（Cover + Foam）

- 大件成品可能在通途拆成 Cover/Foam/基础码存储；EN 的客户物料号会列出全部组件。
- 成品可组装数 = 按仓对必需组件取 `min`（例如 `min(Cover, Foam)`）；只有 Cover 且缺 Foam → `component_partial_nonblocking`，Cover 仍可单独补皮壳，不阻塞。
- 有成品库存时优先用成品；组件与成品都记录原始量，避免重复计数。
- 默认绍兴下单成品，但允许单独补皮壳/海绵；这是业务例外，不是数据错误。

### 7. 订单/库存/单证的三层单位

- 交易层（订单行）：套/成品/皮壳/海绵/组件；
- 库存层（实际存储）：套/成品/皮壳/海绵/组件；
- 组件层（BOM 底层）：统一比较用。
- 每笔数量保留 `raw_qty/raw_uom/txn_level`，另存 `conversion_factor/conversion_basis/component_qty/sellable_qty`；**绝不覆盖原始值**。
- 订单可能是套 SKU、也可能是基础码+qty=件数；优先用通途订单子项/组合明细，没有则用 `platform_sku + qty` 推断；无法判断标 `ambiguous`，不猜。
- 预测按可售单位（套/成品/皮壳），净额换到组件；两者都保留。

### 8. CG 仓

- `Wayfair CG Stock Latest` 的 `warehouse_id='CG'` 是 10 个分仓的汇总行；**只取这一行**，不再累加分仓。
- CG 只服务 Wayfair；按 EN owner 归 `CG-USNJ/CG-USTX`；无 owner=`CG-unknown`；分仓明细只做对账。
- 调拨到 CG 不是当前主线；只留 `transfer_flag` 未来候选，不进当前净额。

### 9. 共享码与身份

- 身份按**库存源 SKU**判：源 SKU 唯一映射一个活跃 EN → 身份唯一；源 SKU 本身多候选/共享池有正库存并进入该行 → 才标共享。
- 共享池保留全部候选，不向单一产品分配；零库存共享码不阻塞。
- 60cm 三角靠枕才做 KS0248/KS0001/PK# 同物合并；153/194 等不合并。

## 已推翻/修正的旧结论（务必不要再犯）

| 旧说法 | 修正 |
|---|---|
| 「不凭当前库存仓反推经营责任」 | 库存仓是投放证据（低置信），可用于市场存在性；只有两侧美国仓都有货且无订单/DN 决胜才冲突 |
| 「共享码任取第一个」 | 保留全部候选，共享池只保留一份；零库存共享码不阻塞 |
| 「缺成品行就是 partial」 | 单一形态正常；只有该发货方式要求的形态缺失才 partial；成品可替代皮壳 |
| 「皮壳库存单位未证，贡献记 0」 | 默认按个；皮壳/HM/成品都按个；只有 TJ# 按套；PCS 后缀才乘 N（星球抱枕整组 1:1） |
| 「CG 各分仓累加」 | 只取 `warehouse_id='CG'` 汇总行；分仓只对账 |
| 「TJ# 是未知产品」 | 拆 Product Bundle；套件需求按套、组件供给按个 |
| 「0 库存也要列隔离」 | 0 库存忽略；只有非零且无法映射/组装才处理 |
| 「DN 双美国客户数笔数」 | 看时间段/迁移日，不能只数笔数 |
| 「KS0248 153/194 与 KS0001 共享库存」 | 库存源 SKU 是 No/B 专属码；共享 cover 码库存 0，分开处理、join_full |

## Why This Matters

这些规则每一条都对应一次真实误判：共享码取首个会把几百行订单塞进单一产品；缺行=0 会把有库存的产品判成断货；套件不拆会让库存永远对不上；CG 分仓累加会重复计数；大小写/后缀不归一会让 EN 明明存在的物料变成 unmapped。

## When to Apply

- 任何 SKU 匹配、库存归并、订单/单据对账；
- 新建或修改 B/C/D 脚本；
- 财务核算复用同一套 SKU/套件/拆包口径时。

## Examples

- `TT0031038K0062927-2PCS` → `TJ#KS0156x2-001` → 2× `KS0156-NYBDSFH-52x52x5-BLACK`；CG 8 套 = 16 件。
- `TT0031159K0063865-Cover`：波兰只有 Cover、美中 Cover+Foam（Foam 0）；Cover 是关键组件，可单独补，缺 Foam 不阻塞。
- `KS0342-HLR-50-DEEPBLUE`：美中 Cover 41 + Foam 29 → 29 个成品；波兰 Cover 46、Foam 0 → 0。
- `OLD_C/Linen-Natural-153-688-wow` → 去 `OLD_` 后 47/47 个 CG SKU 可匹配 EN。

## Related

- `docs/solutions/architecture-patterns/supply-chain-a-b-c-data-pipeline.md`
- `docs/solutions/workflow-issues/supply-chain-review-and-human-escalation.md`
- `docs/solutions/conventions/sellfox-cover-shared-inventory-transition.md`
