---
okf: v0.1
type: Index
title: 评审与证据索引（Jack 协作分支）
date: 2026-10-23
---

# 评审与证据索引

> 本分支只收录与 **Jack W1/W2/W3** 直接相关的评审；完整评审列表在项目工作分支，
> 不在本公开分支重复。行级 CSV/JSON 留本地，不放公开仓库。

## 接口与样本

| 文档 | 内容 |
|---|---|
| [2026-10-23-jack-sample10](2026-10-23-jack-sample10.md) | 9 个冻结 SKU + 1 个缺额；逐 SKU 证据与仓库 |
| [2026-10-23-sc14-spec](2026-10-23-sc14-spec.md) | W1/W3 字段、阶段、五条边界语义、16 条验收用例 |
| [2026-10-22-jack-input-request](2026-10-22-jack-input-request.md) | 给 Jack 的最小输入清单（头程/ETA 等） |

## 供应阶段与单据

| 文档 | 内容 |
|---|---|
| [2026-10-23-sc04-supply-stage](2026-10-23-sc04-supply-stage.md) | 39 张 DN 的阶段归属、UOM 分列、ETA 证据等级 |
| [2026-10-23-dn-split](2026-10-23-dn-split.md) | SC03 分路：单据级 vs 数量级；`credited_qty` 不可用 |
| [2026-10-23-dn-bridge](2026-10-23-dn-bridge.md) | DN 状态接入与未证项 |
| [2026-10-23-dn-status](2026-10-23-dn-status.md) | DN 状态口径与空状态处理 |
| [2026-10-22-t19-wo-dn](2026-10-22-t19-wo-dn.md) | WO/DN 覆盖率：0 可验证 / 32 有材料不可用 / 2,277 无材料 |
| [2026-10-22-eta-cover-uom-evidence](2026-10-22-eta-cover-uom-evidence.md) | ETA 0/524、Cover 情景、UOM unknown |

## 映射与目录

| 文档 | 内容 |
|---|---|
| [2026-10-23-map-evidence](2026-10-23-map-evidence.md) | 58 直接 / 217 可推导 / 7 未映射；0/39 数量级证据 |
| [2026-10-23-sc10-catalog-diff](2026-10-23-sc10-catalog-diff.md) | 1,328 母集与完整目录差集 |
| [2026-10-23-sc10-entry-prep](2026-10-23-sc10-entry-prep.md) | 271 入批检查表；卡在快照间台账 |

## 下游与交付

| 文档 | 内容 |
|---|---|
| [2026-10-23-sc09-trial-pack-v1-frozen](2026-10-23-sc09-trial-pack-v1-frozen.md) | M1-TRIAL-v1：23 列、条件 2,058 + HOLD 251；怎么消费 `supply_*` |
| [2026-10-23-delivery-brief](2026-10-23-delivery-brief.md) | 交付简报：能做什么/不能做什么 |
| [2026-10-23-service-inventory-annex](2026-10-23-service-inventory-annex.md) | 服务—库存前沿：硬 95% 在可接受库存内不可行 |
| [2026-10-23-sku538-facts](2026-10-23-sku538-facts.md) | 538 未验证 SKU 分档事实（239/155/87 + 57 未映射） |
