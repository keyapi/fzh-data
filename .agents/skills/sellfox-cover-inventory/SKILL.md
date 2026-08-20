---
name: sellfox-cover-inventory
description: >
  三角类皮壳在通途与赛狐并行期的共享库存代理、PK# 组合/加工商品选型与单 SKU 沙盒。
  当用户提到“赛狐皮壳商品”、“PK# 商品”、“Cover 共享库存”、“皮壳组合商品”、
  “皮壳加工商品”、“三角靠枕库存”、“通途赛狐库存校准”、shared inventory 或 inventory alias 时触发。
  EN Product Bundle/TJ# 套件同步用 sellfox-combo-create；普通三方缺失登记用 missing-products；
  全量库存初始化用 stock-init。
metadata:
  module: sellfox_cover_inventory
  scripts: sellfox_cover_inventory/audit_sandbox.py
  compatibility: SELLFOX_API/client.py；默认只读
  updated: 2026-08-20
---

# 赛狐皮壳共享库存代理

## Read First

1. `docs/solutions/conventions/sellfox-cover-shared-inventory-transition.md` — 唯一完整事实源。
2. `sellfox_cover_inventory/AGENT_HANDOFF.md` — 接手顺序、冻结边界、代码地图。
3. `sellfox_cover_inventory/README.md` — 单 SKU 配置与命令。

## 当前决定

- 通途仍是分公司普通仓库存事实源。
- 赛狐 `KS` 为普通有库存商品；`PK#` 为 `KS x1` 组合商品。
- 该关系仅是销售库存代理，不是 EN BOM/Product Bundle。
- 加工商品会产生独立库存和加工单，本阶段不用。
- 先验证一个 SKU、一个普通仓、一条皮壳 Listing；用户确认前不扩大。

## 默认动作

运行只读审计并报告 `input/matched/missing/blocked`。任何创建组合商品、配对、调整库存或改同步任务都须另行确认。

## 路由排除

- `TJ#`、EN Product Bundle 镜像到赛狐组合商品：`sellfox-combo-create`。
- 通途完整 SKU 的 EN 客户码与赛狐产品缺口：`missing-products`。
- 赛狐库存初始值全量导入：`stock-init`。
