---
okf: v0.1
type: Reference
title: EN 套件 / 赛狐组合商品 CLI 与对账动作
date: 2026-08-20
module: SELLFOX_API
tags: [sellfox, combo, product-bundle, tj, sync-combos]
resource: SELLFOX_API/sellfox_combo_ops.py
---

# EN 套件 / 赛狐组合商品 CLI

脚本入口：`SELLFOX_API/sellfox_combo_ops.py`。纯对账逻辑在 `combo_reconcile.py`，EN REST 在 `combo_en.py`。

```bash
cd SELLFOX_API
uv run --project .. python sellfox_combo_ops.py <command>
```

所有赛狐/EN 写命令默认 dry-run。`--apply` 前必须用户确认范围。EN `--env` 默认 `prod`。

## 命令

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

## 对账动作

| action | 含义 | `--apply` 会不会写 |
|--------|------|-------------------|
| `create` | EN 合法，赛狐没有，底层 SKU 都在 | 创建组合 SKU |
| `ok` | 组成、`isGroup`、分类都一致 | 否 |
| `set_category` | 组成一致，分类不是 `428697-` | `edit.json` 改分类 |
| `mismatch` | 赛狐已有但组成或 `isGroup` 不同 | **永不自动改组成** |
| `blocked_en` | EN `name/new_item_code/Item` 或子表不合法 | 否 |
| `blocked_bottoms` | 要创建但赛狐缺底层 SKU | 否 |
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

## 回读断言

写入后必须同时满足：

- `sku` 为目标 `TJ#...-NNN`
- `isGroup` 为 1
- `fullCid` 为 `428697-`（若要求分类）
- `childSkus` 的 `(sku, num)` 多重集合与 EN `items` 一致（顺序无关）

## 停手

遇到 mismatch、blocked、预览重复、底层缺失、已发货配对拒绝、或文档未覆盖的 API 行为：打印回读证据，不要猜，不要发明调用。需要改脚本时走 `feature/` 分支 + PR。

操作入口、冻结对象（KS0443 / FXLSSF3030 / KS0003·KS0395）、Issue 模板 → [AGENT_HANDOFF.md](../../AGENT_HANDOFF.md)「EN 套件 / 赛狐组合商品」。
