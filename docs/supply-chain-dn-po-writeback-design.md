---
type: Reference
title: DN↔通途PO 关系与 EN 回填设计（2026-11-06）
date: 2026-11-06
---

# 结论

**暂不回填 EN DN 主字段。** 先建独立映射表；只有“DN 已确认唯一 PO、无冲突、回填规则获批”时才写
`Delivery Note.custom_tongtool_purchase_order`，并保留回滚记录。

## 已知证据

- 13 个 EN DN 的 `custom_tongtool_purchase_order` 有值，对应 13 个唯一通途 PO，样本呈 1:1；
- EN `Tongtool PO Creation` 仅 2 条创建审计，均 1 DN，样本呈 1:1；
- 更早的 PO 没有该字段；客户 PO（NJHY/TXHY/PL）不是通途 PO，不能反推；
- 钉钉 `2026年下单表/物流信息表` 提供 PO→ZMT 物流号/方式/目的地/件数/签收，可补运输链，但不直接给 DN；
- 历史 DN 可能一 PO 多 DN，也可能多 PO 一 DN，**基数未证实**。

## 为什么不直接写

- 该字段是单值字符串：一 DN 多 PO 无法完整表达，会丢关系；
- 覆盖/错配风险高，缺值不等于无关联；
- 旧 PO 无字段，物流号/时间接近只能辅助，不能当确认依据。

## 映射表最小字段

`dn, tongtool_po, dn_item/qty, po_line/qty, evidence_source, evidence_ref,
cardinality, status(未找到/候选/已确认/冲突), operator, updated_at, rollback_note`

## 回填边界

| 情况 | 处理 |
|---|---|
| DN 唯一 PO、双方单据/明细/数量校验通过 | 可自动写映射表；主字段需规则获批后写 |
| 多 PO、多 DN、数量冲突、已有值不一致 | 必须人工确认，不写主字段 |
| 只有客户 PO/物流号/时间接近 | 仅候选，不写 |
| 旧 PO 无任何通途关联 | 标“未找到”，不补 0、不删 |

## 下一轮三步

1. 对现有 13 DN 去重并追溯原始关联依据（PO Creation、DN 字段、明细数量）。
2. 定向核查拆单/合单/部分发货，分别检验 DN→PO、PO→DN 两个方向的基数。
3. 生成只读试算清单，人工验收后按边界分批回填；保留操作日志与回滚。

## 当前只读试算

- 13 DN → 13 PO；71 条 PO 行；51 条可接 Shipment；
- 文件：`analysis/po_dn_stage_audit_20261106.csv`；
- 本轮不写 EN。
