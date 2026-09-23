---
okf: v0.1
type: Log
module: tongtool_order_shipping
created: 2026-09-22
updated: 2026-09-22
---

# tongtool_order_shipping — 变更日志

- **新增**: 本模块成立。定位：**通途订单导出 → 组合件合并成「每包裹一行」的承运商批量导入 csv/xlsx + 仓库背贴 PDF**。成立原因：此前这条线的知识被误挂在 `sellfox_shipping`（那是**赛狐侧**尾程打单），实际它属于**通途侧**的订单导出后处理，只是"都用 UPS/FedEx 面单"这点关系。
- **现状**: **本模块暂无代码** —— 流水线本体仍是同事的 Google Colab notebook（「订单处理 Overstock. 炸开SKU别名,不处理MyToys」）。本模块承载其硬约束与知识，并作为将来迁入的落点（先例 `pb_orders/`）。
- **沉淀**: 两条硬约束的学习正文登记在 `docs/solutions/integration-issues/`（字段长度上限 / 背贴品名补齐链），并已把 `module:` 从 `sellfox_shipping` 改为 `tongtool_order_shipping`。包裹号语义（`Description of Goods` = 订单号，**不要**剥后缀合并）写进 `AGENT_HANDOFF.md`，那是外系统读代码也看不出来的领域事实。
