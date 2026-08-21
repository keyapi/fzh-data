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
  updated: 2026-08-21
---

# 赛狐皮壳共享库存代理

## Read First

1. `docs/solutions/conventions/sellfox-cover-shared-inventory-transition.md` — 唯一完整事实源。
2. `sellfox_cover_inventory/AGENT_HANDOFF.md` — 接手顺序、决策边界、代码地图。
3. `sellfox_cover_inventory/README.md` — 单 SKU 配置与命令。

## 当前决定

- 通途仍是并行期库存事实源；共享池仓库必须由用户点名，不能从示例抄。
- `PK#` 不天然必须是组合商品；当前通途并行且现场只有一个未拆分数量池，所以默认推荐 `KS` 普通库存 + `PK# -> KS x1` 组合代理。
- 该关系仅是销售库存代理，不是 EN BOM/Product Bundle。
- 加工商品会产生独立库存和加工单，本阶段不用。
- 美中通途另有皮壳仓库；不要默认用 DANEEY / FZH-DANEEY 主仓当三角皮壳共享池。
- 赛狐 `POLAND` 对应通途 covers 仓，不对应 `FZHPoland-finished`。
- 组合商品「关联子商品采购成本」复选框 / `purchaseCostLock` 只改 `PK#` 商品主数据，不能按仓、不能按 `-Cover` 切片。
- 订单若吃到子件 `KS` 仓批次，对皮壳 Listing 仍不是 EN Tongtool Cost Review 的部分成本。赛狐没有后缀/交付形态定制。利润与库存代理分开验收；vanilla 赛狐利润项预期失败。
- 禁止把同一通途库存完整复制给赛狐普通 `KS` 和普通 `PK#`；一对多目标 ATP 总和不得超过物理池。多属性商品也不提供共享库存。
- FBM 智能推荐优先采用导入采购成本；公开 OpenAPI 未找到对应写端点。优先验证 Excel/UI 订单成本覆盖，再评估 Playwright 或私有请求。
- 公开 API 支持数量调整、灰度 SKU 调整和批量确认；加工单没有完整创建/分配/完成写链，不能承诺无人值守转换。
- `--live` 只查仓库和两个 SKU，不查 Listing，不创建、不配对。库存测试单等关系建好后另批；成本覆盖可先找已有皮壳 FBM 订单，不必请运营新下单。
- 先验证一个 SKU、一个已确认仓；用户确认前不扩大。
- FBA、名称含退货/不良的仓，只读审计会 blocked。
- 审计发现 `PK#` 已是普通/加工商品时，只阻断当前组合候选自动写入；应转入独立库存模型评估，不得解释成该类型永久非法。

## 默认动作

运行只读审计并报告 `input/matched/missing/blocked`。任何创建组合商品、配对、调整库存、改同步任务或请人下测试单都须另行确认。库存沙盒只验数量代理；成本沙盒另用真实皮壳 FBM 订单验证导入采购成本、`mergePurchaseCost` 和利润更新。

## 路由排除

- `TJ#`、EN Product Bundle 镜像到赛狐组合商品：`sellfox-combo-create`。
- 通途完整 SKU 的 EN 客户码与赛狐产品缺口：`missing-products`。
- 赛狐库存初始值全量导入：`stock-init`。
