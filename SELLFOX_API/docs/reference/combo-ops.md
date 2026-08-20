---
okf: v0.1
type: Reference
title: EN 套件 / 赛狐组合商品操作手册（CLI·硬规则·停手）
date: 2026-08-20
module: SELLFOX_API
tags: [sellfox, combo, product-bundle, tj, sync-combos, runbook]
resource: SELLFOX_API/sellfox_combo_ops.py
description: 稳定操作参考：默认命令、硬规则、对账 action、报告、停手与代码地图。冻结对象见 AGENT_HANDOFF 热区。
---

# EN 套件 / 赛狐组合商品操作手册

> **OKF Reference（稳定，随脚本变）。** 当前冻结对象（KS0443 / FXLSSF3030 等）→ [AGENT_HANDOFF.md](../../AGENT_HANDOFF.md)「EN 套件 / 赛狐组合商品（热区）」。
> 背景与配对 API → [sellfox-combo-sku-create-pairing-workflow.md](../../../docs/solutions/conventions/sellfox-combo-sku-create-pairing-workflow.md)。

脚本：`SELLFOX_API/sellfox_combo_ops.py`；对账 `combo_reconcile.py`；EN REST `combo_en.py`。

```bash
cd SELLFOX_API
uv run --project .. python sellfox_combo_ops.py <command>
```

所有赛狐/EN 写命令默认 dry-run。`--apply` 前必须用户确认范围。EN `--env` 默认 `prod`。

## 默认命令（按场景）

| 场景 | 命令 | 写入 |
|------|------|------|
| 还没有 EN Bundle | `en-preview --child "SKU:qty"` 然后 `en-create --child "SKU:qty"` | `--apply` 才写 EN |
| 已有 EN Bundle，对账赛狐 | `sync-combos --like "TJ#KS0525%"` 或 `--sku TJ#...` | `--apply` 才写赛狐 |
| 确认计划并落盘 | 同上 + `--apply --report sync_report.json` | 是 |
| 单条赛狐创建（已有 EN 回读 TJ#） | `create --sku --name --child --full-cid 428697-` | `--apply` |
| 只改分类 | `set-category --sku --full-cid 428697-` | `--apply` |
| 查底层 / 查组合 | `check-bottoms` / `check-combo` | 否 |

## 命令详表

| 命令 | 作用 | 写入 |
|------|------|------|
| `en-preview --child SKU:qty` | 调 `get_bundle_serial_preview`，查是否重复、下一序号 | 否 |
| `en-create --child SKU:qty` | POST Product Bundle，**body 只有 `items`** | `--apply` |
| `sync-combos --like TJ#KS0443%` | 拉 EN Bundle → 对账赛狐 → 计划 → 可选执行 | `--apply` |
| `sync-combos --sku TJ#...` | 同上，精确 SKU，可重复 | `--apply` |
| `check-bottoms --sku ...` | 底层 SKU 是否存在 | 否 |
| `check-combo --sku ...` | 组合 SKU 回读 | 否 |
| `create --sku --name --child` | 单条赛狐组合创建；已存在则断言 | `--apply` |
| `set-category --sku --full-cid` | 改分类，必须带原 `childSkus` | `--apply` |

`sync-combos` **必须**带 `--like` 或 `--sku`。禁止无范围全量。

## 硬规则

1. **先 EN，后赛狐。** 赛狐组合 SKU = EN 已保存并回读确认的 `TJ#...-NNN`（`name == new_item_code == Item.item_code`）。
2. **EN REST 创建只传 `items`。** 禁止 `new_item_code` / `new_item_code_name` / `name`；禁止先 POST 空单再 PUT；禁止 PUT 改已有套件组成或编号。组成变化 → 新建 Bundle（只传 items，服务端生成编号）。
3. **去重**以完整 `(item_code, qty)` 为准；编号与名称保留 `-001/-002/-003` 后缀。预览 `is_duplicate=true` → 停止，使用 `existing_bundle`。
4. **写操作默认 dry-run。** `--apply` 仅在用户明确授权范围后使用。
5. **赛狐分类 `套件#` 已存在**（`fullCid=428697-`），不要重复建分类。`edit.json` 改分类必须带原 `childSkus`。
6. **`sync-combos --apply` 只执行** `create` 与 `set_category`。`mismatch` / `blocked_en` / `blocked_bottoms` / `blocked_duplicate` **永不自动改组成或名称**。
7. **已存在组合若组成不一致**，`create` 断言失败退出，不当成功跳过。
8. **已发货订单包裹** `updateMatch.json` 会被拒；如实报告，不绕过。
9. **底层 SKU 缺失** → 停，走 `missing-products` / `multi-attr`，不要继续创建组合。
10. **在线/订单配对**不自动跑；写配对前用户单独确认（见工作流文档）。

## 对账动作

| action | 含义 | `--apply` 会不会写 |
|--------|------|-------------------|
| `create` | EN 合法，赛狐没有，底层 SKU 都在 | 创建组合 SKU |
| `ok` | 组成、`isGroup`、名称、分类都一致 | 否 |
| `set_category` | 组成与名称一致，分类不是 `428697-` | `edit.json` 改分类 |
| `mismatch` | 赛狐已有但组成、`isGroup` 或名称不同 | **永不自动改组成/名称** |
| `blocked_en` | EN `name/new_item_code/Item` 或子表不合法（含空名称） | 否 |
| `blocked_bottoms` | 要创建但赛狐缺底层 SKU | 否 |
| `blocked_duplicate` | 赛狐组合 SKU 或多条底层 SKU 重复 | 否 |
| `skip_historical` | 如 `FXLSSF3030` | 否 |

已存在组合如果组成不一致，**不再当成功跳过**；`create` 会断言失败退出。

## 报告

`sync-combos` 打印 JSON，可用 `--report path.json` 落盘。字段：

| 字段 | 含义 |
|------|------|
| `input_en` | 拉到的 EN Bundle 数 |
| `output_rows` | 计划行数，应等于 `input_en` |
| `counts` | 各 action 计数 |
| `rows` | 每条 SKU 的 action / reason / children / problems |
| `unmatched` | 非 ok/create/set_category 的行，不得丢弃 |
| `--apply` 后 `applied` / `failed` / `assertion_failures` / `blocked` | 部分失败清单 |

数量对账：入 N 行必须出 N 行；差数只能出现在 `unmatched` 的 reason 里。

## EN 创建禁令

合法 payload：

```json
{"items": [{"item_code": "KS0525-QQFSB-80x80x65-DEEPGREY", "qty": 2}]}
```

禁止：`new_item_code`、`new_item_code_name`、`name`、空 `items`、先 POST 再 PUT。组成变化必须新建 Bundle。预览 `is_duplicate=true` 时使用已有套件。

## 回读断言与完成关口

写入后必须同时满足：

- `sku` 为目标 `TJ#...-NNN`
- `isGroup` 为 1
- `fullCid` 为 `428697-`（若要求分类）
- `childSkus` 的 `(sku, num)` 多重集合与 EN `items` 一致（顺序无关）
- EN Bundle：`name == new_item_code == Item.item_code`，子表非空，物料组 `套件#`
- `sync-combos` 报告：`input_en == output_rows`；非 ok 行都在 `unmatched`
- 无用户授权的写入、无改动冻结对象、无发明新 API

## 停手

立即停止并报告（附 EN/赛狐回读 JSON）：

- `mismatch` / `blocked_en` / `blocked_bottoms` / `blocked_duplicate`
- 赛狐 `pageList` 同 SKU 跨页重复、底层 SKU 重复（不得任选 childId）
- 预览重复、底层缺失、权限 40021（代理 token 缓存，见工作流 Proxy 章节）
- 已发货配对拒绝、文档与脚本未覆盖的 API 行为

不要 PUT 修组成、不要临时编号、不要无范围扫描、不要猜。

改脚本 → [CONTRIBUTING.md](../../../CONTRIBUTING.md)（`feature/` 分支 + PR）。Issue 须带范围、dry-run JSON、回读摘要；不要贴密钥。

## 代码地图

| 文件 | 职责 |
|------|------|
| `sellfox_combo_ops.py` | CLI：`sync-combos`、`en-preview`、`en-create`、`create`、`set-category` |
| `combo_reconcile.py` | 纯对账：`plan_sync`、action 枚举、`HISTORICAL_SKIP_SKUS` |
| `combo_en.py` | EN REST：items-only 创建、预览、拉 Bundle |
| `client.py` | 赛狐代理 API |
| `tests/sellfox_api/test_combo_reconcile.py` | 对账逻辑单测 |
