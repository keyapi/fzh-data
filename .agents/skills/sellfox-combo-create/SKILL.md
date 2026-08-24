---
name: sellfox-combo-create
description: >
  EN Product Bundle（套件# / TJ#）与赛狐组合商品的创建、对账、回读断言。
  当用户提到"组合商品"、"组合SKU"、"套件SKU"、"EN套件"、"Product Bundle"、
  "TJ#"、"childSkus"、"sync-combos"、"赛狐创建套件"、"底层商品检测"、
  "套件#分类"或"订单配对错误"时触发。
  不要用于普通多属性 SPU 创建（用 multi-attr），不要用于通途有库存三方主线
  （用 missing-products），不要把三角皮壳 `PK# -> KS x1` 库存代理当成套件
  （用 sellfox-cover-inventory / cover_combo_ops.py），不要直接改已发货订单包裹配对（API 会拒绝）。
compatibility: >
  SELLFOX_API/sellfox_combo_ops.py、combo_reconcile.py、combo_en.py；
  代理 Key 在根 .env 的 SELLFOX_PROXY_API_KEY；EN 凭证在 EN_API/.env。
  所有写操作默认 dry-run，--apply 前必须用户确认范围。
metadata:
  module: SELLFOX_API
  scripts: SELLFOX_API/sellfox_combo_ops.py
  updated: 2026-08-24
---

# EN 套件 / 赛狐组合商品

## Read First（按顺序）

1. **`SELLFOX_API/docs/reference/combo-ops.md`** — 稳定操作手册：默认命令、硬规则、action 表、停手、代码地图。
2. **`SELLFOX_API/AGENT_HANDOFF.md` →「EN 套件 / 赛狐组合商品（热区）」** — 当前冻结对象、读哪、接手 30 秒。
3. `docs/solutions/conventions/sellfox-combo-sku-create-pairing-workflow.md` — 背景、配对 API、生产修复记录（按需）。
4. `docs/solutions/workflow-issues/soft-wall-combo-batch-staging.md` — 批量分阶段创建（软包墙围 6×4 等登记表场景）。
5. `docs/solutions/workflow-issues/zipper-combo-batch-staging.md` — 无捆绑SKU 时合成唯一客户物料号（`基码-EN物料码-Npcs`）。
6. 缺底层 SKU → `missing-products` / `multi-attr`；赛狐连通性 → `sellfox-api`。
7. 三角皮壳 `PK#` 组合代理 → `sellfox-cover-inventory` + `cover-combo-ops.md`，禁止对本手册 `sync-combos`。

先跑脚本拿当前事实。不要凭聊天记忆、旧 Excel 或临时编号写 EN/赛狐。

## 硬约束（摘要）

- **先 EN，后赛狐**；赛狐 SKU = EN 回读确认的 `TJ#...-NNN`。
- EN REST 创建 **只传 `items`**；禁止临时编号、空单 PUT、PUT 改组成。
- `sync-combos` **必须** `--like` 或 `--sku`；禁止无范围全量。
- 写操作默认 dry-run；`--apply` 须用户确认范围。EN 默认 **prod**。
- `mismatch` / `blocked_*` 只报告，不自动修组成；遵守 HANDOFF 热区冻结表。
- EN 套件创建后**必须**把完整通途SKU 登记到上层 Item `customer_items`（`register-customer-code`，默认 dry-run）。
- 整批“无捆绑SKU”时，合成客户物料号必须包含 EN 物料码保证唯一，并记录基码来源；未确认合成规则前不要 apply。

## 日常三步（概要）

工作目录 `SELLFOX_API`，命令前缀：`uv run --project .. python sellfox_combo_ops.py …`

1. **新建 EN 套件**：`en-preview` → `en-create`（dry-run）→ 用户确认 → `--apply`。
2. **对账赛狐（主路径）**：`sync-combos --like "TJ#KSxxxx%"` → 用户确认 JSON 计划 → `--apply --report …`。
3. **配对**（不自动跑）：见工作流文档；写配对前单独确认。
4. **批量续跑**：`soft_wall_stage.py` / `zipper_stage.py` 的 `plan --full` / `plan` → `status` → `apply --only SKU...`（默认 dry-run），阶段记录 Excel 是唯一进度事实。

命令细节与完成关口 → **combo-ops.md**；冻结对象 → **HANDOFF 热区**。

## 自主边界

**能**：按用户范围拉 EN → 对账赛狐 → 输出计划 → dry-run → 确认后 `--apply` create/set_category → 回读断言。

**不能**：全量扫描、PUT 改组成、自动配对、改冻结对象、发明文档未写的 API。遇未知边界 → 停 → 带 EN/赛狐回读证据报告用户。
