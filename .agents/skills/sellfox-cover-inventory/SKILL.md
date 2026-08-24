---
name: sellfox-cover-inventory
description: >
  三角类皮壳在通途与赛狐并行期的共享库存代理、PK# 组合/加工商品选型、
  PK#->KS x1 组合创建与只读配对候选、单 SKU 沙盒。
  当用户提到“赛狐皮壳商品”、“PK# 商品”、“Cover 共享库存”、“皮壳组合商品”、
  “皮壳加工商品”、“三角靠枕库存”、“通途赛狐库存校准”、shared inventory、
  inventory alias、“创建皮壳组合”或“PK#KS0001”时触发。
  EN Product Bundle/TJ# 套件同步用 sellfox-combo-create；普通三方缺失登记用 missing-products；
  全量库存初始化用 stock-init。
metadata:
  module: sellfox_cover_inventory
  scripts: >
    sellfox_cover_inventory/audit_sandbox.py;
    SELLFOX_API/cover_combo_ops.py
  compatibility: SELLFOX_API/client.py；审计默认只读；组合创建须 --apply
  updated: 2026-08-24
---

# 赛狐皮壳共享库存代理

## Read First

1. `docs/solutions/conventions/sellfox-cover-shared-inventory-transition.md` — 架构事实源。
2. `SELLFOX_API/docs/reference/cover-combo-ops.md` — 创建/对账/只读配对命令。
3. `docs/solutions/workflow-issues/sellfox-cover-combo-create-ops.md` — 生产踩坑（普通商品搜不到、禁止并行 apply）。
4. `sellfox_cover_inventory/AGENT_HANDOFF.md` — 接手顺序与冻结边界。
5. `sellfox_cover_inventory/README.md` — 单 SKU 库存沙盒。

## 当前决定

- 通途仍是并行期库存事实源；共享池仓库必须由用户点名，不能从示例抄。
- 默认推荐 `KS` 普通库存 + `PK# -> KS x1` 组合代理。不是 EN BOM / Product Bundle，禁止 `sync-combos`。
- `KS0001` / `KS0248` 组合已在 2026-08-21 生产建完（957 个 `isGroup=1`）。不要再全量 apply。界面搜**组合商品** / SKU `PK#`，不是普通商品、不是名称「皮壳#」。
- 写配对（`matchByMsku`）须用户另批；`pairing-candidates` 只出表。
- 加工商品本阶段不用。FBA/退货/不良仓不进共享池。美中不要默认 DANEEY 主仓。赛狐 `POLAND` = 通途 covers。
- 库存扣减沙盒与利润覆盖仍是两条链；`--live` 审计不创建、不配对。

## 默认动作

- **查库存模型 / 单 SKU 沙盒**：跑 `audit_sandbox.py`，报告 `input/matched/missing/blocked`。
- **查或补 PK# 组合**：`cover_combo_ops.py status`；仅当 `need_create>0` 且用户确认范围后 `--apply`。
- **配对**：只跑 `pairing-candidates`，把 xlsx 交给业务；不要写配对接口。

## 路由排除

- `TJ#`、EN Product Bundle 镜像到赛狐组合商品：`sellfox-combo-create`。
- 通途完整 SKU 的 EN 客户码与赛狐产品缺口：`missing-products`。
- 赛狐库存初始值全量导入：`stock-init`。
