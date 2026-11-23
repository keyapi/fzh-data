---
okf: v0.1
type: Report
title: 审核返修报告 — da4fa1e6 规范需求层的子仓资格与四列净额接口
description: 针对 Codex reject 的 P1/P2 修复、修复前后数字对照、测试与快照身份
tags: [review, canonical, netting, subwarehouse, report]
date: 2026-10-27
status: fixed-for-review
---

# 审核返修报告（针对 da4fa1e6）

- 审核报告：`C:/Users/zhang/.agent-ops/fzh-data/reviews/identity-review-da4fa1e6.md`
- 修复提交：`c4da3c33`
- 基线提交：`da4fa1e6`
- 工作区：`C:/Users/zhang/orca/workspaces/Cursor/self-fulfilled-demand-oct29`
- 未 push、未开 PR、未生产写入、未重拉订单。

## 1. 修复内容

### P1 #1 子仓净额资格

`resolve_warehouse` 对 `not_merged` 子仓返回 `not_merged_no_evidence` 时，新增阻断原因
`subwarehouse_identity_unproven`：

- 5 类子仓：`FZH-DANEEY-半成品仓`、`-成品仓`、`-皮壳仓库`、`-退货产品仓`、`FZHPoland-finished`。
- **保留原行、原数量、独立规范仓名**；不并入主仓、不删除。
- `netting_allowed=false`，`netting_block_primary=subwarehouse_identity_unproven`。
- 文档同步：`docs/reference/canonical-demand.md` 与 `warehouse_aliases.json` policy。

修复前获准、修复后阻断：**90,286 行 / 98,068 件**（审核报告数字完全一致）。

### P1 #2 四列主键

原 `demand_canonical.parquet` 是 13 列明细聚合，四列并不唯一。修复采用「双数据集」：

| 数据集 | 内容 | 四列唯一 |
|---|---|---|
| `demand_netting.parquet` | 仅 `netting_allowed=true`，先过滤再按四列汇总 | **是（重复 0）** |
| `demand_blocked.parquet` | 阻断账：四列 + 原因组合 + 数量 | 按原因组合分账 |
| `demand_canonical.parquet` | 13 列明细聚合（形态/来源/scope/资格） | **否**，manifest 明确禁止 upsert/按行连接供应 |

- 审核点名的键 `2025-07-01 / KS0390-CTTM-120x120x70-CREAMYBEIGE / FZH-DANEEY-半成品仓 / 个`：
  明细 2 行（semi_finished 1 + unknown 1，合计 2 件），阻断账 1 行 2 件，净额表 0 行。
  不把 2 件当 1 件，也不对同一份供应重复扣减。
- 新增 `supply_targets()`：拒绝 `<unknown>` 单位/仓库，只输出四列目标。

### P2 #3 快照一致性

- `build_canonical` 现在整次构建 `with store.pinned()`：`build_demand`、`en_kind_lookup`、
  `snapshot_identity` 共用同一个快照目录。
- `consumer.build_demand(..., store=...)` 支持传入同一 `ParquetStore`。
- manifest 新增 `sources.en_snapshot`：
  `commit_id`、`status`、`committed_at`、`orders_sha256`、`lines_sha256`、行数。
- 本次：`legacy-adopt-20261027T131556`，orders 27,503 行、lines 28,823 行，哈希均为 64 位。
- 新增模拟 CURRENT 切换的离线测试，固定目录读取不受新提交影响。

## 2. 修复前后数字对照

| 指标 | 修复前（da4fa1e6） | 修复后（c4da3c33） |
|---|---:|---:|
| 输入行 / 件 | 413,561 / 440,179 | 413,561 / 440,179 |
| 明细聚合行 / 件 | 250,105 / 440,179 | 250,111 / 440,179 |
| 可净额行 / 件 | 402,494 / 428,576 | **312,208 / 330,508** |
| 阻断行 / 件 | 11,067 / 11,603 | **101,353 / 109,671** |
| 四列唯一净额行 | 未输出（四列重复 1,322） | **191,701（重复 0）** |
| 阻断账行 | — | 57,088 |
| 子仓阻断行 / 件 | 0（90,286 行曾获准） | **91,413 / 99,167** |
| FBA 排除 | 2,453 / 2,558 | 2,453 / 2,558 |
| 3PL 保留 | 5,419 / 5,702 | 5,419 / 5,702 |
| unknown scope | 7,940 / 8,233 | 7,940 / 8,233 |

### 90,286 行去向（按子仓）

| 子仓 | 保留行 | 数量 | 修复前获准行 |
|---|---:|---:|---:|
| FZH-DANEEY-半成品仓 | 10,179 | 10,249 | 9,163 |
| FZH-DANEEY-成品仓 | 11,757 | 16,430 | 11,732 |
| FZH-DANEEY-皮壳仓库 | 66,771 | 69,639 | 66,718 |
| FZH-DANEEY-退货产品仓 | 2,644 | 2,760 | 2,617 |
| FZHPoland-finished | 62 | 89 | 56 |
| **合计** | **91,413** | **99,167** | **90,286** |

说明：91,413 行是五类子仓全部行；其中 90,286 行此前获准，现全部阻断。剩余 1,127 行
此前已因 SKU/UOM 等原因阻断，现在原因列表中同时带 `subwarehouse_identity_unproven`。
阻断后总量 101,353 = 11,067 + 90,286。

阻断 primary 计数：子仓 90,286、仓库未知 6,627、SKU 缺失 4,203、SKU 一对多 237。

## 3. 新增回归测试

`uv run pytest self_fulfilled_demand/tests -q` → **52 passed**（原 31，新增 21）。

新增覆盖：

- 完整 `build_canonical` 守恒：净额 + 阻断 = 输入；明细 = 输入；manifest 快照身份。
- 四列键唯一性；审核点名重复键的 2 件不被压成 1 件，且供应目标只出现一次。
- 五类子仓逐一断言 `netting_allowed=false` + 原因。
- 全部未知仓（含空名/空白名）。
- FBA 在 canonical 端到端排除。
- GS 无匹配保持 unknown；多条同形态可沿用。
- UOM 缺失/空串/空白/非件类。
- 复合阻断原因顺序与 primary。
- 空输入、缺日期、无效数量。
- SKU TSV 空字段（`keep_default_na=False`）。
- 模拟 CURRENT 切换的快照一致性。
- 供应适配器 `supply_targets()` 过滤 `<unknown>`。

## 4. 重跑与产物

只用本地数据重跑，未重拉订单：

```bash
uv run python -m self_fulfilled_demand.canonical \
  --store D:/Work/fzh-order-store/en-demand-v1 \
  --gs-path D:/Work/fzh-order-store/gs_orders.parquet \
  --start 2022-12-01 --end 2026-10-31 \
  --out D:/Work/fzh-order-store/en-demand-v1/canonical
```

产物：`D:/Work/fzh-order-store/en-demand-v1/canonical/`
（`demand_netting` / `demand_blocked` / `demand_canonical` / `demand_line_disposition` /
`sku_coverage` / `ambiguity_list` / `identity_manifest` / `cases.md`）。

修复前 manifest 保留为 `identity_manifest.before-fix.json`。

## 5. 未解决 / 需业务裁定

1. 五类子仓身份证据（是否应并入主仓、是否可独立净额）需业务/主数据确认；补齐前保持阻断。
2. `sku_map.tsv` 为既有缓存，302 个未映射 SKU 需补登。
3. UOM 只证明物料单位；订单数量与「套/包/对」的换算比例仍需业务证据。
4. GS 历史 389,579 行无发货形态证据，保持 unknown。
5. 与 b08acc05 的跨模块净额合成测试不在本仓库；本层已提供四列唯一净额表与过滤入口。
