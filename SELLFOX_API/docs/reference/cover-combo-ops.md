---
okf: v0.1
type: Reference
title: 赛狐皮壳 PK# 组合代理操作手册（CLI·硬规则·停手）
date: 2026-08-24
module: SELLFOX_API
tags: [sellfox, cover, combo, pk, inventory-alias]
resource: SELLFOX_API/cover_combo_ops.py
description: 三角类 PK# -> KS x1 库存代理的稳定命令、硬规则与停手。不是 EN Product Bundle / sync-combos。
---

# 赛狐皮壳 PK# 组合代理操作手册

> **OKF Reference（稳定，随脚本变）。** 架构决定 → [共享库存代理](../../../docs/solutions/conventions/sellfox-cover-shared-inventory-transition.md)。创建踩坑 → [sellfox-cover-combo-create-ops.md](../../../docs/solutions/workflow-issues/sellfox-cover-combo-create-ops.md)。冻结对象 → [AGENT_HANDOFF.md](../../AGENT_HANDOFF.md)。

脚本：`SELLFOX_API/cover_combo_ops.py`；纯计划 `cover_combo_plan.py`。

```text
cd SELLFOX_API
uv run --project .. python cover_combo_ops.py <command>
```

写操作必须带 `--apply`。默认 env 是 prod。禁止对同一范围并行开两个 `apply`。

## 默认命令

| 场景 | 命令 | 写入 |
|------|------|------|
| 从赛狐普通 KS + EN 皮壳 + BOM 出计划 | `plan --report ..\.codex_tmp\cover_combo_plan.json` | 否 |
| 线上 PK# 对账 | `status --plan … --report …` | 否 |
| 创建缺失组合（每批 50） | `apply --plan … --apply --batch-size 50 --report …` | 是 |
| 连续建完剩余 | 同上再加 `--until-done` | 是 |
| 皮壳 Listing → PK# 候选 | `pairing-candidates --plan … --report …` | 否（禁止 `matchByMsku`） |

## 硬规则

1. **不是 EN 套件。** 不要 `sync-combos`，不要 `TJ#`，不要分类 `428697-`。
2. **子件是成品 KS ×1**，分类抄该 KS 的 `fullCid`。
3. **`autoCalcWeight` 用字符串 `"false"`**，不要 `"0"`。
4. **`purchaseCostLock=0`。** 成本缺列则跳过该 SKU，除非 `--allow-missing-cost`。
5. **对账用 SKU 搜索** `PK#KS0001` / `PK#KS0248`。空 `skus:[]` 会漏组合。`total=0` 时仍按满页翻页。
6. **`商品SKU已存在` 当 skip**，不当致命失败；不要为此再开第二个 writer。
7. **只杀 pwsh 包装不够** — 必须确认 Python 子进程已退出。
8. **组合商品不出现在普通商品。** 界面用组合商品或 SKU `PK#`，不要搜名称「皮壳#」。
9. **配对默认只读。** `pairing-candidates` 可出 xlsx；写配对必须用户另批。
10. **进度 JSON / BOM xlsx / `.codex_tmp` 不提交。**

## 2026-08-21 生产结果（KS0001 / KS0248）

| 项 | 值 |
|----|----|
| 计划 `create` | 955（KS0001 812 + KS0248 143） |
| 线上 `isGroup=1` | 957（含事先 TAN/BLACK） |
| `need_create` / `mismatch` | 0 / 0 |
| 只读配对候选 | 604（Active 91）；当时 0 条已挂 PK# |

不要对这两个 SPU 再全量 `--apply`，除非 `status` 重新出现缺口。

## 停手

- `mismatch`（已有 PK# 但不是 `KS x1` 组合）
- 第二个 `apply` 已在跑
- 有人要把结果同步成 EN Product Bundle
- 用户还没确认配对写入

## 代码地图

| 文件 | 职责 |
|------|------|
| `cover_combo_ops.py` | `plan` / `status` / `apply` / `pairing-candidates` |
| `cover_combo_plan.py` | 无网络计划：create/ok/blocked/mismatch |
| `client.py` | 代理限流与重试 |
| `tests/sellfox_api/test_cover_combo_ops.py` | 计划纯函数单测 |
