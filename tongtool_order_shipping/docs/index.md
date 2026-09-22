---
okf: v0.1
type: Index
module: tongtool_order_shipping
created: 2026-09-22
updated: 2026-09-22
---

# tongtool_order_shipping — 文档索引

| 文档 | 说明 |
|------|------|
| [../README.md](../README.md) | 人读：这条线是什么、三条硬约束、不要做什么 |
| [../AGENT_HANDOFF.md](../AGENT_HANDOFF.md) | Agent 交接：数据流、包裹号语义、访问性坑、迁移落点 |
| [log.md](log.md) | 变更日志 |
| [../../docs/solutions/integration-issues/carrier-label-batch-field-length-limits.md](../../docs/solutions/integration-issues/carrier-label-batch-field-length-limits.md) | 学习正文：UPS 35 / FedEx poNumber 30，合并后必须截断 |
| [../../docs/solutions/integration-issues/sku-name-backfill-via-en-customer-code.md](../../docs/solutions/integration-issues/sku-name-backfill-via-en-customer-code.md) | 学习正文：背贴品名缺失怎么补、通途SKU 在 EN 的两种写法 |

## 相关

- `.agents/skills/tongtool-order-shipping/SKILL.md` — 触发词入口
- `.agents/skills/colab-kit/` — 改这条流水线（它还在同事的 Colab notebook 里）要用它
- `pb_orders/` — 同类流水线从 Colab 迁入仓库的先例
- `sellfox_shipping/sku_label/` — 背贴 PDF 与品名查询的现成实现
