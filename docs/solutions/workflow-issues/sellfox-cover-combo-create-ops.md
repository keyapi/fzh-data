---
title: 三角皮壳 PK# 组合代理批量创建（不是 EN 套件）
date: 2026-08-24
category: workflow-issues
module: SELLFOX_API
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - "要把赛狐皮壳 Listing 挂到 PK# 组合商品而不是成品 KS"
  - "同事在普通商品里搜皮壳# 找不到刚建的 PK#"
  - "有人想用 sync-combos 或套件# 分类去建 PK# -> KS x1"
  - "批量 create.json 时 pageList total=0 或重复写入"
tags: [sellfox, cover, combo, pk, inventory-alias, triangle-wedge]
---

# 三角皮壳 PK# 组合代理批量创建

## Context

[#191](https://github.com/keyapi/fzh-data/pull/191) 已把通途/赛狐并行期的库存模型写成「`KS` 普通库存 + `PK# -> KS x1` 组合代理」。那是架构决定。2026-08-21 在生产把三角靠枕 `KS0001`、三角靠枕无扣 `KS0248` 的组合代理真正建完之后，操作层还有一套不能混进 `sellfox-combo-create` / `sync-combos` 的做法。

同事在赛狐「普通商品」里搜「皮壳#」会得到 0 条。这些 SKU 是组合商品，界面路径是组合商品或 SKU 前缀 `PK#`。

## Guidance

走 `SELLFOX_API/cover_combo_ops.py`，不要走 `sellfox_combo_ops.py sync-combos`。稳定命令见 [cover-combo-ops.md](../../../SELLFOX_API/docs/reference/cover-combo-ops.md)。决策背景见 [共享库存代理](../conventions/sellfox-cover-shared-inventory-transition.md)。

创建形状（生产已验证）：

- 赛狐 SKU = EN 皮壳码 `PK#KS…`，`isGroup=1`，唯一子件为对应成品 `KS… × 1`
- 分类用成品 `KS` 的 `fullCid`（靠枕类），**不是** `套件#` 的 `428697-`
- 名称用 EN 皮壳 `item_name`
- `autoCalcWeight` 必须是字符串 `"false"`，不要 `"0"`
- `purchaseCostLock=0`；采购成本 = BOM 皮壳成本 + (USNJ+USTX+PL)/3
- EN 成品 `disabled=1` 仍可建代理：事实源是赛狐已有普通 `KS`，不是 EN 启用状态
- 没有批量创建 API；`--batch-size 50` 只是本地循环 + 进度文件
- 代理默认约 2 秒 1 次；不要并行开第二个 `apply`
- `pairing-candidates` 只出 Excel/JSON，不调用 `matchByMsku.json`

对账必须用 `searchField=sku` + `searchValue=PK#KS0001` / `PK#KS0248`。空 `skus:[]` 的 `pageList` 会漏掉组合商品。该搜索经常 `total=0` 但仍返回行：只要本页满 `pageSize` 就继续翻页，短页再停。见 `page_sellfox_sku_search`。

## Why This Matters

混用 `sync-combos` 会把库存代理当成 EN Product Bundle：错误分类、错误 TJ# 编码、错误「先 EN 后赛狐」顺序。只杀 PowerShell 包装进程而留下 Python 子进程，会在 UI 里看起来停了、后台仍在 create，再开第二个 `apply` 就会 `商品SKU已存在` 并打满超时。运营按普通商品/「皮壳#」去找，会误报「没建成功」。

## When to Apply

- 三角靠枕 / 无扣皮壳 Listing 需要扣同一仓 `KS` 库存
- 用户已确认范围（本批是这两个 SPU 的已有普通 `KS`，不是全类目）
- 配对尚未授权写入时，只许出候选表

不要用于：拉链/墙围等真正的 EN 套件、有库存普通 `PK#`、FBA/退货仓共享池。

## Examples

错误路径：

```text
uv run --project .. python sellfox_combo_ops.py sync-combos --like "PK#KS0001%" --apply
```

正确路径（工作目录 `SELLFOX_API`）：

```text
uv run --project .. python cover_combo_ops.py plan --report ..\.codex_tmp\cover_combo_plan.json
uv run --project .. python cover_combo_ops.py status --plan ..\.codex_tmp\cover_combo_plan.json
uv run --project .. python cover_combo_ops.py apply --plan ..\.codex_tmp\cover_combo_plan.json --apply --batch-size 50 --until-done
uv run --project .. python cover_combo_ops.py pairing-candidates --plan ..\.codex_tmp\cover_combo_plan.json
```

2026-08-21 生产回读（`status`，不写入）：计划创建 955；线上 `PK#KS0001` 814 + `PK#KS0248` 143 = 957，全部 `isGroup=1`；`need_create=0`、`mismatch=0`。多出的 2 条是事先已建的 `PK#KS0001-HLR-153-TAN` / `BLACK`。只读配对候选 604 条（在售 Active 91），当时 0 条已挂到 `PK#`，未调用配对写接口。

## Related

- [三角类皮壳共享库存代理](../conventions/sellfox-cover-shared-inventory-transition.md)
- [赛狐组合商品/EN 套件工作流](../conventions/sellfox-combo-sku-create-pairing-workflow.md) — 仅 TJ# 套件
- [cover-combo-ops.md](../../../SELLFOX_API/docs/reference/cover-combo-ops.md)
- [soft-wall-combo-batch-staging.md](soft-wall-combo-batch-staging.md) — 另一条 EN 套件批量线，不要复用到 PK#
